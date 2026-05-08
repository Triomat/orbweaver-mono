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

All dev commands are in `justfile` — read it for full syntax. Key areas:

- **Services**: `just start [diode-target]`, `just stop`, `just restart`, `just ps`, `just backend-restart [diode-target]`, `just ui-restart`, `just backend-logs`, `just ui-logs`
- **Testing/lint**: `just test`, `just test-cov`, `just test-legacy` (upstream tests only), `just lint`, `just check-syntax`, `just check-imports`, `just seed` (seed fake review session for UI)
- **Docker**: `just docker-up` (backend :8072, UI :3000), `just docker-down`, `just docker-logs`

Runtime files: `/tmp/orbweaver-{backend,ui}.{pid,log}`, `/tmp/orbweaver-reviews/`

---

## Frontend (orbweaver-ui)

Stack: Nuxt 4, shadcn-nuxt, Tailwind CSS, VueUse

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
