# orbweaver — Claude Code Project Context

## What this repo is

**orbweaver** is a private fork of [`netboxlabs/orb-discovery`](https://github.com/netboxlabs/orb-discovery).

It is an orb-agent backend: receives policy YAML via FastAPI, schedules NAPALM-based device discovery with APScheduler, and ingests entities into NetBox via the Diode SDK (gRPC).

**This repo must remain private.** It is not to be made public on GitHub.

## Upstream compatibility

orbweaver tracks `netboxlabs/orb-discovery` upstream. The rule is:

> **Do not modify files that exist verbatim in upstream unless absolutely necessary.**

Files that are intentionally kept identical to upstream (safe to cherry-pick):
- `server.py`, `main.py`, `client.py`, `metrics.py`, `version.py`
- `policy/manager.py`, `policy/run.py`, `policy/portscan.py`
- `translate.py`, `interface.py`, `defaults.py`

Files that diverge from upstream (do NOT expect clean cherry-picks):
- `policy/runner.py` — rewired `_collect_device_data()` to use vendor collectors
- `policy/models.py` — added `collector` field to `Napalm` model
- `pyproject.toml` — added `requests` dep and new packages

When pulling upstream changes:
1. Cherry-pick/merge unchanged files freely
2. For `runner.py` and `models.py`, apply upstream diffs manually and preserve the vendor-collector additions

## Architecture: what was added (the "orbweaver layer")

The original orb-discovery does generic NAPALM collection only. orbweaver adds:

### New modules (not in upstream)

```
device-discovery/device_discovery/
├── models/
│   ├── __init__.py
│   ├── common.py              ← Common Object Model (COM) dataclasses
│   └── version_parser.py      ← Vendor version string parsers
├── collectors/
│   ├── __init__.py
│   ├── base.py                ← BaseCollector ABC + CollectorConfig
│   ├── napalm_helpers.py      ← NAPALM helper functions (COM builders)
│   ├── napalm_collector.py    ← Generic NAPALM collector
│   ├── cisco_ios.py           ← Cisco IOS/IOS-XE: NAPALM + CLI enrichment
│   ├── aruba_aoscx.py         ← Aruba AOS-CX: NAPALM + REST API
│   └── registry.py            ← Pluggable collector registry
└── diode_translate.py         ← COM → Diode SDK entity bridge (NEW CODE)
```

These modules were ported from [`Triomat/netbox-discovery`](https://github.com/Triomat/netbox-discovery) with imports updated from `netbox_discovery.*` → `device_discovery.*`.

`diode_translate.py` is original code: it replaces netbox-discovery's pynetbox importer with a Diode SDK translation layer.

### How the data flow works

```
POST /api/v1/policies (YAML)
  ↓
runner.py._collect_device_data()
  ├── scope.collector = "cisco_ios" → CiscoCollector → NormalizedDevice
  │                                  → diode_translate → list[Entity]
  │                                  → Client().ingest()
  ├── scope.collector = "aruba_aoscx" → ArubaCollector (NAPALM + REST)
  │                                    → same path
  └── scope.collector = None (no match) → existing NAPALM-only path
                                          → translate.py + interface.py
                                          → Client().ingest()  (unchanged)
```

### Policy YAML: using the new collectors

```yaml
policies:
  my-cisco-policy:
    config:
      defaults:
        site: "DC1"
        role: "access-switch"
    scope:
      - hostname: 192.168.1.1
        username: admin
        password: secret
        collector: cisco_ios    # ← new field; uses vendor collector
      - hostname: 192.168.1.2
        username: admin
        password: secret
        driver: ios             # ← no collector field; uses legacy NAPALM path
```

## Key design decisions

1. **Backward compatibility**: Existing policies without `collector:` field use the original NAPALM-only path. Nothing breaks.

2. **Upstream cherry-pick safety**: New code lives in new files (`models/`, `collectors/`, `diode_translate.py`). Only `runner.py`, `models.py`, and `pyproject.toml` diverge from upstream — and the divergence is additive (new methods, new field, new dep).

3. **COM as the contract**: All vendor collectors produce `NormalizedDevice` objects. `diode_translate.py` consumes them. This means adding new vendors (Juniper, Arista, etc.) only requires writing a new collector — the translation layer stays the same.

4. **Registry pattern**: Collectors are registered by name. Policy YAML uses `collector: cisco_ios` etc. Adding a new vendor = write collector + call `register_collector()`.

## Dependencies added

- `requests~=2.31` — required by `aruba_aoscx.py` for REST API calls

## What `diode_translate.py` does

Maps COM objects → Diode SDK entities:

| COM class | Diode entity |
|---|---|
| `NormalizedDevice` | `Entity(device=Device(...))` |
| `NormalizedInterface` | `Entity(interface=Interface(...))` |
| `NormalizedIPAddress` | `Entity(ip_address=IPAddress(...))` |
| `NormalizedVLAN` | `Entity(vlan=VLAN(...))` |
| `NormalizedPrefix` | `Entity(prefix=Prefix(...))` |

`defaults.site` and `defaults.role` from the policy config override COM-derived values.

## Source provenance

| Files | Source |
|---|---|
| Everything not listed below | `netboxlabs/orb-discovery` (upstream, kept identical) |
| `models/common.py`, `models/version_parser.py` | `Triomat/netbox-discovery` (imports updated) |
| `collectors/*.py` | `Triomat/netbox-discovery` (imports updated) |
| `diode_translate.py` | Original orbweaver code |
| `policy/runner.py` additions | Original orbweaver code |
| `policy/models.py` `collector` field | Original orbweaver code |

## GitHub

- Repo: **private**, hosted under the Triomat GitHub account
- Do NOT make this repo public
- Do NOT push to `netboxlabs/orb-discovery` upstream

## Running tests

```bash
cd device-discovery
pytest tests/
```

Existing upstream tests should pass unchanged (the legacy NAPALM path is untouched).

---

## Showcase: orbweaver vs standard orb-agent (side-by-side)

### Running services

| Service | What it is | Port | Started by |
|---|---|---|---|
| orbweaver backend | Local dev (full orbweaver with review workflow) | 8073 | `just start grpc://...` |
| orbweaver-ui | Nuxt dev server | 3000 | `just start` |
| orbweaver-device-discovery-1 | Docker standalone (orbweaver fork, no review) | 8072 | `just docker-up` |
| orbweaver-agent-1 | Docker orbweaver agent | — | `just docker-up-agent` |
| orb-agent | Standard netboxlabs orb-agent (external container) | internal only | `docker start orb-agent` |

### The two paths being compared

**Standard orb-agent** (`netboxlabs/orb-agent:latest`, container `orb-agent`):
- Configured via `/home/cheddar/projects/netbox/orb/agent.yml`
- Scheduled cron is set to `0 0 1 1 *` (disabled for showcase — manual only)
- Internal device-discovery API at `localhost:8072` inside the container (NOT exposed externally)
- Triggered from orbweaver-ui `/orb-agent` page via `POST /api/v1/orb-agent/trigger`
  → orbweaver backend uses `docker exec -i orb-agent python3 -c "..."` to POST to internal API
- Uses standard NAPALM only (`driver: ios`), ingests directly to NetBox via Diode

**orbweaver** (local dev backend at :8073):
- Triggered from orbweaver-ui `/config` page → Discover Now
- Uses vendor collectors (`collector: cisco_ios`) for richer data
- Stores results in a review session, requires human accept/ingest step

### orb-agent container lifecycle

The `orb-agent` container is NOT managed by orbweaver's docker-compose. It must be started manually:
```bash
docker start orb-agent
```
If it crashes (exit code 1, "9 is not running"), restart it the same way.

The container reads `/home/cheddar/projects/netbox/orb/agent.yml` (mounted read-only).
To update the config without the UI: edit the file then `docker restart orb-agent`.

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

**Policy YAML** (standalone API format — what `POST /api/v1/policies` accepts):
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

### Key server.py endpoints added for showcase

- `GET  /api/v1/orb-agent/config` — reads `ORBWEAVER_ORB_AGENT_YML` from disk
- `POST /api/v1/orb-agent/config` — writes file + runs `docker restart ORBWEAVER_ORB_CONTAINER`
- `POST /api/v1/orb-agent/trigger` — extracts policy from YAML body, docker-execs python3 into orb-agent to DELETE+POST it (forcing immediate run)

Env vars required for these endpoints (set in justfile):
- `ORBWEAVER_ORB_AGENT_YML=/home/cheddar/projects/netbox/orb/agent.yml`
- `ORBWEAVER_ORB_CONTAINER=orb-agent`

### Nuxt server proxy

`orbweaver-ui/server/api/orb/[...path].ts` proxies `/api/orb/*` → `NUXT_PUBLIC_ORB_API_BASE/api/v1/*`
to avoid CORS when the browser checks orb-agent status. Currently only used for status polling.

---

## Development workflow (justfile)

All service management is via `just` recipes in `/home/cheddar/projects/netbox/orbweaver/justfile`.
The UI repo has no justfile — it's managed from the orbweaver justfile.

### Service management

| Command | What it does |
|---|---|
| `just start` | Start backend (dry-run) + UI |
| `just start grpc://host:8080/diode` | Start backend against a real Diode target + UI |
| `just stop` | Stop both |
| `just restart` | Stop + start both |
| `just ps` | Show status of both services |
| `just backend-restart` | Restart backend only (reloads code changes) |
| `just backend-restart grpc://...` | Restart backend with Diode target |
| `just ui-restart` | Restart UI only (reloads frontend changes) |
| `just backend-logs` | Tail backend logs (`/tmp/orbweaver-backend.log`) |
| `just ui-logs` | Tail UI logs (`/tmp/orbweaver-ui.log`) |

### Deploy changes to live services

- **Backend code changes**: `just backend-restart` (or `just backend-restart grpc://...` for live Diode)
- **Frontend code changes**: `just ui-restart` (Nuxt dev server auto-reloads on file save, but restart if HMR misses something)
- **Both**: `just restart`

### Key paths

- PID files: `/tmp/orbweaver-backend.pid`, `/tmp/orbweaver-ui.pid`
- Log files: `/tmp/orbweaver-backend.log`, `/tmp/orbweaver-ui.log`
- Review data: `/tmp/orbweaver-reviews/`
- Backend port: 8073, UI port: 3000
- Scripts: `scripts/orbweaver-backend`, `scripts/orbweaver-ui` (bash service wrappers)

### Testing & CI

| Command | What it does |
|---|---|
| `just test` | Run all backend tests |
| `just test-cov` | Tests with coverage report |
| `just test-legacy` | Run only upstream tests |
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
