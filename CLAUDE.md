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
├── backend/                   ← upstream device-discovery (100% unmodified)
│   ├── device_discovery/      ✓ every file identical to upstream
│   │   ├── policy/
│   │   │   ├── runner.py      ✓ upstream, untouched
│   │   │   ├── models.py      ✓ upstream, untouched
│   │   │   ├── manager.py     ✓ upstream, untouched
│   │   │   ├── run.py         ✓ upstream, untouched
│   │   │   └── portscan.py    ✓ upstream, untouched
│   │   ├── server.py          ✓ upstream, untouched
│   │   ├── client.py          ✓ upstream, untouched
│   │   ├── main.py            ✓ upstream, untouched
│   │   ├── entity_metadata.py ✓ upstream, untouched
│   │   ├── translate.py       ✓ upstream, untouched
│   │   ├── interface.py       ✓ upstream, untouched
│   │   ├── defaults.py        ✓ upstream, untouched
│   │   ├── metrics.py         ✓ upstream, untouched
│   │   └── version.py         ✓ upstream, untouched
│   ├── tests/                 ✓ upstream tests, untouched
│   ├── scripts/
│   ├── seed_review.py
│   └── pyproject.toml         ✓ upstream, untouched
│
├── orbweaver/                 ✦ orbweaver-only extension package
│   ├── patches.py             ✦ runtime patches (Napalm model + PolicyRunner)
│   ├── app.py                 ✦ extends upstream FastAPI app in-place
│   ├── main.py                ✦ entry point: patches → app → upstream main()
│   ├── pyproject.toml         ✦ package config (entry point: orbweaver CLI)
│   ├── collectors/            ✦ vendor collector framework
│   │   ├── base.py            ✦ BaseCollector ABC + CollectorConfig
│   │   ├── napalm_helpers.py  ✦ NAPALM helper functions (COM builders)
│   │   ├── napalm_collector.py ✦ generic NAPALM collector
│   │   ├── cisco_ios.py       ✦ Cisco IOS/IOS-XE: NAPALM + CLI enrichment
│   │   ├── aruba_aoscx.py     ✦ Aruba AOS-CX: NAPALM + REST API
│   │   └── registry.py        ✦ pluggable collector registry
│   ├── models/                ✦ Common Object Model (COM)
│   │   ├── common.py          ✦ NormalizedDevice, NormalizedInterface, etc.
│   │   └── version_parser.py  ✦ vendor OS version string parsers
│   ├── review/                ✦ review workflow
│   │   ├── models.py          ✦ ReviewSession, ReviewItem, ReviewStatus
│   │   ├── store.py           ✦ ReviewStore: JSON-on-disk persistence
│   │   ├── discover.py        ✦ run_discovery_for_review(): discover-and-hold
│   │   ├── rebuild.py         ✦ device_from_dict(): dacite reconstruction
│   │   └── compare.py         ✦ compare vs live NetBox (pynetbox)
│   └── diode_translate.py     ✦ COM → Diode SDK entity bridge
│
├── frontend/                  ← orbweaver UI (Nuxt 4, shadcn-nuxt, Tailwind)
│   ├── app/
│   │   ├── pages/             (config, reviews, review/[id])
│   │   ├── composables/       (useApi, useReview, useConfig)
│   │   └── components/ui/
│   ├── nuxt.config.ts
│   └── package.json
│
├── docker/                    ← integration Docker Compose stack
├── scripts/                   ← bash service wrappers (orbweaver-backend, orbweaver-ui)
└── justfile                   ← all dev commands live here

Legend: ✓ upstream untouched  /  ✦ orbweaver-only
```

---

## Upstream compatibility

**Rule: backend/ is 100% upstream. Do not modify any file under backend/. All orbweaver logic lives in orbweaver/.**

### How extensions work (zero upstream modifications)

orbweaver extends the upstream backend via runtime patching at process startup:

```
orbweaver/main.py
  │
  ├── import orbweaver.patches
  │     ├── Napalm.model_fields["collector"] = ...  (adds collector field)
  │     ├── Napalm.model_rebuild(force=True)
  │     ├── PolicyRunner._select_collector = ...
  │     ├── PolicyRunner._collect_device_data_via_collector = ...
  │     └── PolicyRunner._collect_device_data = ...  (wraps upstream method)
  │
  ├── import orbweaver.app
  │     ├── from device_discovery.server import app   (triggers upstream app creation)
  │     ├── app.add_middleware(CORSMiddleware, ...)
  │     ├── removes upstream /api/v1/status route
  │     └── adds enhanced /api/v1/status + all new routes
  │
  └── device_discovery.main.main()    (starts uvicorn with the extended app)
```

### Upstream merge workflow

orbweaver tracks `netboxlabs/orb-discovery` as a git remote named `upstream`.

Since backend/ path differs from upstream's device-discovery/ path, direct `git merge upstream/develop` does not apply cleanly. Use a patch-based approach:

```bash
git fetch upstream

# See what changed in the latest upstream commit
git diff upstream/develop~1 upstream/develop -- device-discovery/

# For any changed file: extract and apply directly to backend/
git show upstream/develop:device-discovery/device_discovery/client.py > backend/device_discovery/client.py
git show upstream/develop:device-discovery/pyproject.toml > backend/pyproject.toml
# etc.
```

**Never edit backend/ files by hand** — always take them verbatim from upstream.

---

## Architecture: the orbweaver layer

### orbweaver/patches.py — Napalm model extension

Adds `collector: str | None` field to the upstream `Napalm` Pydantic model at runtime using Pydantic v2's `model_rebuild()`. This lets YAML policies use `collector: cisco_ios` without touching `policy/models.py`.

### orbweaver/patches.py — PolicyRunner extension

Three methods are monkey-patched onto `PolicyRunner`:
- `_select_collector(scope)` — picks vendor collector by `scope.collector` or `scope.driver`
- `_collect_device_data_via_collector(scope, hostname, config, run_id)` — runs COM collector path
- `_collect_device_data(scope, hostname, config, run_id)` — wraps upstream: tries collector first, falls back to NAPALM

### orbweaver/app.py — FastAPI extension

Imports the upstream `app` object and extends it in-place:
- CORS middleware (origins from `ORBWEAVER_CORS_ORIGINS` env var)
- Overrides `/api/v1/status` with enhanced response (adds `reviews`, `dry_run`, `diode_target`)
- New routes: collectors, discover, reviews CRUD, ingest, compare

### Data flow

```
POST /api/v1/policies (YAML)
  ↓
runner.py._collect_device_data()   [upstream, patched at startup]
  ├── scope.collector = "cisco_ios"   → orbweaver.collectors.CiscoCollector → NormalizedDevice
  │                                   → orbweaver.diode_translate → list[Entity] → Diode SDK
  ├── scope.collector = "aruba_aoscx" → orbweaver.collectors.ArubaCollector
  │                                   → same path
  └── scope.collector = None          → original NAPALM-only path (unchanged)
                                      → device_discovery.translate + interface → Diode SDK

POST /api/v1/discover (YAML)          → review workflow (discover-and-hold)
  ↓ background task
  orbweaver collector → NormalizedDevice → ReviewSession (JSON on disk)
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

### Installation

```bash
# Create venv and install both packages
python3 -m venv .venv
just install-backend   # installs backend/ (device-discovery) + orbweaver/
just install-ui        # installs frontend node deps
```

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
| `backend/device_discovery/` | Upstream Python package (unmodified) |
| `orbweaver/` | orbweaver extension package |
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
| `just check-syntax` | Syntax-check key orbweaver Python files |
| `just check-imports` | Verify orbweaver module imports work |
| `just seed` | Seed a fake review session for UI testing |

### Docker (integration stack)

| Command | What it does |
|---|---|
| `just docker-up` | Build + start orbweaver stack (backend port 8072, UI port 3000) |
| `just docker-down` | Stop all Docker containers |
| `just docker-logs` | Tail backend container logs |

---

## Frontend (orbweaver-ui)

Stack: Nuxt 4, shadcn-nuxt, Tailwind CSS, VueUse

| Path | Purpose |
|---|---|
| `frontend/app/pages/config.vue` | Trigger discover-and-hold |
| `frontend/app/pages/reviews.vue` | List all review sessions |
| `frontend/app/pages/review/[id].vue` | Review, accept/reject, ingest |
| `frontend/app/composables/useApi.ts` | Base HTTP client |
| `frontend/app/composables/useReview.ts` | Review session state |
| `frontend/app/composables/useConfig.ts` | Discovery config state |

API base URL: `NUXT_PUBLIC_API_BASE` env var (default: `http://localhost:8073`)

The frontend calls `/api/v1/status` and all orbweaver-only endpoints. The upstream-only endpoints (`/api/v1/capabilities`, `/api/v1/policies`) are available but not directly used by the UI.

---

## Source provenance

| Files | Source |
|---|---|
| Everything under `backend/` | `netboxlabs/orb-discovery` upstream (kept identical) |
| `orbweaver/models/common.py`, `models/version_parser.py` | Ported from `Triomat/netbox-discovery` (imports updated) |
| `orbweaver/collectors/*.py` | Ported from `Triomat/netbox-discovery` (imports updated) |
| `orbweaver/diode_translate.py` | Original orbweaver code |
| `orbweaver/review/` | Original orbweaver code |
| `orbweaver/patches.py` | Original orbweaver code |
| `orbweaver/app.py` | Original orbweaver code |
| `orbweaver/main.py` | Original orbweaver code |
| `frontend/` | Original orbweaver UI (was separate repo `orbweaver-ui`) |

All `netbox_discovery.*` imports were updated to `orbweaver.*` or `device_discovery.*` during the port.
