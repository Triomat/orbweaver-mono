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
