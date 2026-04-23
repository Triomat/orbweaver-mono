# NetBox Seed Infrastructure — Design Spec

**Date:** 2026-04-23  
**Status:** Approved  
**Scope:** orbweaver-only (no upstream backend/ changes)

---

## Goal

Enable a live showcase demo that populates a fresh NetBox instance from scratch. The flow is:

1. User pastes/submits YAML → **"Seed Infrastructure"** button → sites, racks, devices appear in NetBox
2. User runs orbweaver **Discover** → switches appear in racks with full COM data (interfaces, IPs, VLANs)

Orbweaver is the hero of step 2. Step 1 is silent infrastructure setup.

---

## API

```
POST /api/v1/seed
Content-Type: application/x-yaml

<raw YAML body>
```

**Response:**
```json
{
  "created": { "tenants": 1, "sites": 1, "manufacturers": 5, "device_types": 12, "device_roles": 10, "platforms": 1, "racks": 2, "devices": 15 },
  "skipped": { "tenants": 0, ... },
  "errors": []
}
```

Idempotent — safe to call multiple times. Existing objects (matched by name/slug) are skipped, never duplicated.

CLI equivalent:
```bash
curl -X POST http://localhost:8073/api/v1/seed \
  -H "Content-Type: application/x-yaml" \
  --data-binary @orbweaver/seed/seed.yaml
```

---

## Seed YAML schema

```yaml
tenant:          # single tenant applied to all devices (optional)
  name: string
  slug: string

sites:
  - name: string
    slug: string
    description: string
    status: active | planned | retired

racks:
  - name: string
    site: string          # site name (must exist)
    u_height: int
    status: active | planned | reserved | deprecated

manufacturers:
  - name: string
    slug: string

device_types:
  - manufacturer: string  # manufacturer name (must exist)
    model: string
    slug: string
    u_height: int

device_roles:
  - name: string
    slug: string
    color: string         # hex color without #

platforms:
  - name: string
    slug: string
    manufacturer: string  # optional

devices:
  - name: string
    device_type: string   # model name (must exist)
    manufacturer: string  # used to resolve device_type unambiguously
    role: string          # role name (must exist)
    site: string          # site name (must exist)
    rack: string          # rack name (optional)
    position: int         # rack unit (optional)
    face: front | rear    # (optional)
    airflow: string       # passive | front-to-rear | rear-to-front | left-to-right | right-to-left | side-to-rear | passive (optional)
    serial: string        # (optional)
    tenant: string        # tenant name (optional, overrides top-level tenant)
    platform: string      # platform name (optional)
    status: active | planned | staged | failed | decommissioning | offline
    primary_ip4: string   # CIDR notation (optional — created if provided)
    comments: string      # (optional)
    tags:                 # list of tag names (optional — created if missing)
      - string
    parent_device: string # parent device name for device-bay children (optional)
    parent_bay: string    # bay name on parent device (optional)
```

---

## New files

### `orbweaver/seed/models.py`
Pydantic v2 models matching the YAML schema above. Validated before any pynetbox calls.

### `orbweaver/seed/loader.py`
Core seeder logic. Dependency order:

```
tenant → sites → manufacturers → device_types → device_roles
→ platforms → racks → devices (two-pass: parents first, then bay children)
```

Each object type uses a `get_or_create(endpoint, lookup_kwargs, create_kwargs)` helper that:
1. Calls `endpoint.get(**lookup_kwargs)`
2. If found → increments `skipped` counter, returns existing object
3. If not found → calls `endpoint.create(**create_kwargs)`, increments `created` counter

pynetbox is initialized from `NETBOX_HOST`, `NETBOX_PORT`, and `NETBOX_TOKEN` env vars (already used by `netbox_ops.py`). The loader reuses the same pynetbox client construction as `netbox_ops.py`.

**Two-pass device creation:** Devices with `parent_device` are created after all devices without it. Then the bay assignment is made via `nb.dcim.device_bays.get(device_id=parent.id, name=parent_bay)` followed by `bay.save()` with `installed_device` set.

**Primary IP creation:** If `primary_ip4` is set on a device, the loader creates the IP address via `nb.ipam.ip_addresses.create(address=..., assigned_object_type="dcim.interface", ...)` — but only as a bare IP (no interface assignment, since the interface doesn't exist yet at seed time). The device's `primary_ip4` is then set via a separate `device.save()` call.

**Tags:** Created on-the-fly via the same `get_or_create` helper (`nb.extras.tags`, lookup by `name`, create with `name` + auto-slug).

### `orbweaver/app.py` (extended)
New route added:

```python
@app.post("/api/v1/seed")
async def seed_infrastructure(request: Request) -> dict:
    body = await request.body()
    raw = yaml.safe_load(body)
    seed_data = SeedData.model_validate(raw)
    result = run_seed(seed_data)
    return result
```

---

## UI change

On the existing config/status page, add a collapsible "Seed Infrastructure" panel:
- YAML textarea pre-populated from a default template embedded in the frontend
- "Seed" button → `POST /api/v1/seed` with textarea content as body
- Summary toast on response: *"Created 15 devices, 2 racks, 1 site — ready for discovery."*

---

## Environment variables

Uses existing vars from `netbox_ops.py`:
- `NETBOX_HOST` — e.g. `10.42.42.140`
- `NETBOX_PORT` — e.g. `80` (default: `8000`)
- `NETBOX_TOKEN` — NetBox API token

No new env vars needed.

---

## What is NOT in scope

- Seeding interfaces, IP ranges, prefixes, or cables (these come from orbweaver discovery)
- Deleting or resetting NetBox before seeding (out of scope — manual wipe if needed)
- VLAN or prefix seeding (covered by orbweaver's discover→ingest flow)
