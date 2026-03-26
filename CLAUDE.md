# orbweaver — Claude Code Project Context

## What this repo is

**orbweaver** is a private monorepo that extends [`netboxlabs/orb-discovery`](https://github.com/netboxlabs/orb-discovery) with a vendor collector framework, a review workflow, and a management UI.

**This repo must remain private.** Do not make it public or push to any public remote.

---

## What orb-agent is (upstream context)

`netboxlabs/orb-agent` is the upstream umbrella container that orchestrates multiple discovery backends:
- **device-discovery** (Python/FastAPI) — the component orbweaver extends
- network-discovery (Go)
- snmp-discovery
- worker

The orb-agent container loads configuration (local YAML or Git), manages secrets (e.g. HashiCorp Vault), and starts the backends. orbweaver **replaces the device-discovery backend** with an enhanced version. The orb-agent container itself is never modified by orbweaver.

---

## Monorepo structure

```
orbweaver-mono/
├── backend/                   ← orbweaver's enhanced device-discovery backend
│   ├── device_discovery/
│   │   ├── policy/
│   │   │   ├── runner.py      ⚠ diverges from upstream
│   │   │   ├── models.py      ⚠ diverges from upstream
│   │   │   ├── manager.py     ✓ upstream, untouched
│   │   │   ├── run.py         ✓ upstream, untouched
│   │   │   └── portscan.py    ✓ upstream, untouched
│   │   ├── server.py          ⚠ diverges from upstream
│   │   ├── collectors/        ✦ orbweaver-only (vendor collector framework)
│   │   ├── models/            ✦ orbweaver-only (Common Object Model)
│   │   ├── review/            ✦ orbweaver-only (review workflow)
│   │   ├── diode_translate.py ✦ orbweaver-only (COM → Diode SDK bridge)
│   │   ├── client.py          ✓ upstream, untouched
│   │   ├── main.py            ✓ upstream, untouched
│   │   ├── translate.py       ✓ upstream, untouched
│   │   ├── interface.py       ✓ upstream, untouched
│   │   ├── defaults.py        ✓ upstream, untouched
│   │   ├── metrics.py         ✓ upstream, untouched
│   │   └── version.py         ✓ upstream, untouched
│   ├── tests/
│   ├── scripts/
│   ├── seed_review.py
│   ├── pyproject.toml         ⚠ diverges from upstream (added deps + packages)
│   └── docker-upstream/       (Dockerfile for building as standalone container)
│
├── frontend/                  ← orbweaver UI (Nuxt 4, shadcn-nuxt, Tailwind)
│   ├── app/
│   │   ├── pages/             (config, reviews, review/[id], orb-agent)
│   │   ├── composables/       (useApi, useReview, useConfig)
│   │   └── components/ui/
│   ├── nuxt.config.ts
│   └── package.json
│
├── network-discovery/         ✓ upstream Go backend, completely untouched
├── snmp-discovery/            ✓ upstream, completely untouched
├── worker/                    ✓ upstream, completely untouched
│
├── docker/                    ← integration Docker Compose stack
├── scripts/                   ← bash service wrappers (orbweaver-backend, orbweaver-ui)
└── justfile                   ← all dev commands live here

Legend: ✓ upstream untouched  /  ⚠ diverges from upstream  /  ✦ orbweaver-only
```

---

## Two distinct services (do NOT confuse them)

| Service | What it is | Port | Managed by |
|---|---|---|---|
| **orbweaver** | This repo — enhanced device-discovery + review workflow | 8073 (dev), 8072 (Docker) | `just start` / `just docker-up` |
| **orb-agent** | Original `netboxlabs/orb-agent:latest` — unmodified, for showcase | internal only | `just orb-agent-create` (once), then `just orb-agent-start` |

- `orb-agent` is NOT managed by orbweaver's docker-compose — it is a standalone container
- The `ORB_CONTAINER` justfile variable always refers to the original `orb-agent` container
- orbweaver backend uses `docker exec -i orb-agent` to trigger discovery inside the original agent for the showcase comparison

---

## Upstream compatibility

orbweaver tracks `netboxlabs/orb-discovery` as a git remote named `upstream`.

> **Rule: Do not modify files that exist verbatim in upstream unless absolutely necessary. New code lives in new files.**

### Files that diverge from upstream (manual merge required)

| File | What was changed |
|---|---|
| `backend/device_discovery/policy/runner.py` | Added `_select_collector()`, `_collect_device_data_via_collector()`, wired into `_collect_device_data()` |
| `backend/device_discovery/policy/models.py` | Added `collector: str | None` field to `Napalm` model |
| `backend/device_discovery/server.py` | Added CORS middleware, `ReviewCounts`, extended `/api/v1/status`, all review/ingest/compare/orb-agent endpoints |
| `backend/pyproject.toml` | Added `dacite`, `requests`, `pynetbox` deps; added collectors/models/review to packages |

### Files safe to take from upstream without review

All files not listed above in `backend/device_discovery/`:
`client.py`, `main.py`, `translate.py`, `interface.py`, `defaults.py`, `metrics.py`, `version.py`,
`policy/manager.py`, `policy/run.py`, `policy/portscan.py`

### Upstream merge workflow (after monorepo path rename)

Direct `git merge upstream/develop` does **not** apply cleanly — upstream uses `device-discovery/` as path, this repo uses `backend/`. Use a patch-based approach:

```bash
git fetch upstream

# See what changed in the latest upstream commit
git diff upstream/develop~1 upstream/develop -- device-discovery/

# For unchanged files: extract and apply manually
git show upstream/develop:device-discovery/device_discovery/client.py > backend/device_discovery/client.py

# For diverged files (runner.py, models.py, server.py, pyproject.toml):
# View upstream version, manually apply relevant changes, preserve orbweaver additions
git show upstream/develop:device-discovery/device_discovery/policy/runner.py
```

---

## Architecture: the orbweaver layer

The original orb-discovery does generic NAPALM collection only. orbweaver adds on top:

### New modules (not in upstream)

```
backend/device_discovery/
├── models/
│   ├── common.py              ← Common Object Model (COM) dataclasses (NormalizedDevice, etc.)
│   └── version_parser.py      ← Vendor OS version string parsers
├── collectors/
│   ├── base.py                ← BaseCollector ABC + CollectorConfig
│   ├── napalm_helpers.py      ← NAPALM helper functions (COM builders)
│   ├── napalm_collector.py    ← Generic NAPALM collector
│   ├── cisco_ios.py           ← Cisco IOS/IOS-XE: NAPALM + CLI enrichment
│   ├── aruba_aoscx.py         ← Aruba AOS-CX: NAPALM + REST API
│   └── registry.py            ← Pluggable collector registry
├── review/
│   ├── models.py              ← ReviewSession, ReviewItem, ReviewStatus, ItemStatus
│   ├── store.py               ← ReviewStore: JSON-on-disk persistence
│   ├── discover.py            ← run_discovery_for_review(): one-shot, no immediate ingest
│   ├── rebuild.py             ← device_from_dict(): dacite-based reconstruction for ingest
│   └── compare.py             ← compare review data vs live NetBox (pynetbox)
└── diode_translate.py         ← COM → Diode SDK entity bridge
```

### Data flow

```
POST /api/v1/policies (YAML)
  ↓
runner.py._collect_device_data()
  ├── scope.collector = "cisco_ios"   → CiscoCollector → NormalizedDevice
  │                                   → diode_translate → list[Entity] → Diode SDK
  ├── scope.collector = "aruba_aoscx" → ArubaCollector (NAPALM + REST)
  │                                   → same path
  └── scope.collector = None          → original NAPALM-only path (unchanged)
                                      → translate.py + interface.py → Diode SDK

POST /api/v1/discover (YAML)          → review workflow (discover-and-hold)
  ↓ background task
  collector → NormalizedDevice → ReviewSession (JSON on disk)
  ↓ user reviews in UI
POST /api/v1/reviews/{id}/ingest      → device_from_dict → diode_translate → Diode SDK
```

### Policy YAML: using vendor collectors

```yaml
policies:
  my-policy:
    config:
      defaults:
        site: "DC1"
        role: "access-switch"
    scope:
      - hostname: 192.168.1.1
        username: admin
        password: secret
        collector: cisco_ios    # orbweaver field — uses vendor collector
      - hostname: 192.168.1.2
        username: admin
        password: secret
        driver: ios             # no collector field — uses legacy NAPALM path
```

### COM → Diode entity mapping

| COM class | Diode entity |
|---|---|
| `NormalizedDevice` | `Entity(device=Device(...))` |
| `NormalizedInterface` | `Entity(interface=Interface(...))` |
| `NormalizedIPAddress` | `Entity(ip_address=IPAddress(...))` |
| `NormalizedVLAN` | `Entity(vlan=VLAN(...))` |
| `NormalizedPrefix` | `Entity(prefix=Prefix(...))` |

---

## Key design decisions

1. **Backward compatibility**: Existing policies without `collector:` use the original NAPALM-only path unchanged.
2. **Upstream safety**: New code lives in new files. Only `runner.py`, `models.py`, `server.py`, `pyproject.toml` diverge — all changes are additive.
3. **COM as the contract**: All vendor collectors produce `NormalizedDevice`. Adding new vendors (Juniper, Arista) only requires a new collector — translation layer stays the same.
4. **Registry pattern**: Collectors are registered by name. `collector: cisco_ios` in YAML maps to `CiscoCollector`. New vendor = write collector + call `register_collector()`.

---

## Git identity

```
user.name  = Triomat
user.email = Triomat@users.noreply.github.com
```

Remote repository (GitLab internal) will be configured later. Currently local only.

`upstream` remote = `https://github.com/netboxlabs/orb-discovery.git`

---

## Development workflow (justfile)

All service management via `just` from the monorepo root.

### Service management

| Command | What it does |
|---|---|
| `just start` | Start backend (dry-run) + UI |
| `just start grpc://host:8080/diode` | Start backend with live Diode target + UI |
| `just stop` | Stop both services |
| `just restart` | Stop + start both |
| `just ps` | Status of all services |
| `just backend-restart` | Restart backend only |
| `just backend-restart grpc://...` | Restart backend with Diode target |
| `just ui-restart` | Restart UI only |
| `just backend-logs` | Tail backend logs |
| `just ui-logs` | Tail UI logs |

### Key paths

| Path | What it is |
|---|---|
| `backend/device_discovery/` | Python package |
| `frontend/` | Nuxt 4 UI |
| `docker/` | Docker Compose integration stack |
| `scripts/` | Bash service wrappers |
| `.venv/` | Python virtualenv (monorepo root) |
| `/tmp/orbweaver-backend.pid` | Backend PID file |
| `/tmp/orbweaver-ui.pid` | UI PID file |
| `/tmp/orbweaver-backend.log` | Backend log |
| `/tmp/orbweaver-ui.log` | UI log |
| `/tmp/orbweaver-reviews/` | Review session data |

### Testing & CI

| Command | What it does |
|---|---|
| `just test` | Run all backend tests |
| `just test-cov` | Tests with coverage report |
| `just test-legacy` | Run only upstream tests (verify nothing broke) |
| `just lint` | Run ruff linter |
| `just check-syntax` | Syntax-check key Python files |
| `just seed` | Seed a fake review session for UI testing |

### Docker (integration stack)

| Command | What it does |
|---|---|
| `just docker-up` | Build + start standalone orbweaver (port 8072) |
| `just docker-up-agent` | Build + start orbweaver inside orb-agent |
| `just docker-down` | Stop all Docker containers |
| `just docker-logs` | Tail standalone container logs |

---

## Frontend (orbweaver-ui)

Stack: Nuxt 4, shadcn-nuxt, Tailwind CSS, VueUse

| Path | Purpose |
|---|---|
| `frontend/app/pages/config.vue` | Trigger discover-and-hold |
| `frontend/app/pages/reviews.vue` | List all review sessions |
| `frontend/app/pages/review/[id].vue` | Review, accept/reject, ingest |
| `frontend/app/pages/orb-agent.vue` | orb-agent config + trigger (showcase) |
| `frontend/app/composables/useApi.ts` | Base HTTP client |
| `frontend/app/composables/useReview.ts` | Review session state |
| `frontend/app/composables/useConfig.ts` | Discovery config state |

API base URL: `NUXT_PUBLIC_API_BASE` env var (default: `http://localhost:8073`)

The frontend calls only one upstream endpoint (`/api/v1/status`). All other endpoints are orbweaver-only.

---

## Showcase: orbweaver vs standard orb-agent (side-by-side)

### The two paths being compared

**Standard orb-agent** (`netboxlabs/orb-agent:latest`, container `orb-agent`):
- Configured via `/home/cheddar/projects/netbox/orb/agent.yml`
- Triggered from orbweaver-ui `/orb-agent` page via `POST /api/v1/orb-agent/trigger`
  → orbweaver backend uses `docker exec -i orb-agent python3 -c "..."` to POST to internal API
- Uses standard NAPALM only (`driver: ios`), ingests directly to NetBox via Diode

**orbweaver** (local dev backend at :8073):
- Triggered from orbweaver-ui `/config` page
- Uses vendor collectors (`collector: cisco_ios`) for richer data
- Stores results in a review session — requires human accept/ingest step

### YAML format differences

**agent.yml** (orb-agent format — nested under `orb.policies.device_discovery`):
```yaml
orb:
  policies:
    device_discovery:
      discovery_1:
        config:
          schedule: "* * * * *"
          defaults:
            site: netboxlabs
        scope:
          - driver: ios
            hostname: 192.168.110.10
```

**Policy YAML** (standalone API format — `POST /api/v1/policies`):
```yaml
policies:
  discovery_1:
    config:
      defaults:
        site: netboxlabs
    scope:
      - driver: ios
        hostname: 192.168.110.10
```

The orbweaver-ui `/orb-agent` page handles this conversion automatically when triggering.

### orb-agent endpoints added to server.py

- `GET  /api/v1/orb-agent/status`  — docker inspect + docker exec status
- `GET  /api/v1/orb-agent/config`  — reads `ORBWEAVER_ORB_AGENT_YML` from disk
- `POST /api/v1/orb-agent/config`  — writes file + runs `docker restart ORBWEAVER_ORB_CONTAINER`
- `POST /api/v1/orb-agent/trigger` — docker-execs python3 into orb-agent to DELETE+POST policy

Required env vars (set in justfile):
- `ORBWEAVER_ORB_AGENT_YML=/home/cheddar/projects/netbox/orb/agent.yml`
- `ORBWEAVER_ORB_CONTAINER=orb-agent`

---

## Source provenance

| Files | Source |
|---|---|
| Everything not listed below | `netboxlabs/orb-discovery` upstream (kept identical) |
| `backend/device_discovery/models/common.py`, `models/version_parser.py` | Ported from `Triomat/netbox-discovery` (imports updated) |
| `backend/device_discovery/collectors/*.py` | Ported from `Triomat/netbox-discovery` (imports updated) |
| `backend/device_discovery/diode_translate.py` | Original orbweaver code |
| `backend/device_discovery/review/` | Original orbweaver code |
| Additions in `policy/runner.py` | Original orbweaver code |
| `collector` field in `policy/models.py` | Original orbweaver code |
| `frontend/` | Original orbweaver UI (was separate repo `orbweaver-ui`) |

All `netbox_discovery.*` imports were updated to `device_discovery.*` during the port.
