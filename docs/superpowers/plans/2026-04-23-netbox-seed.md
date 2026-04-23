# NetBox Seed Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `POST /api/v1/seed` to orbweaver that accepts a raw YAML body and creates sites, racks, manufacturers, device types, device roles, platforms, and devices in NetBox via pynetbox — plus a UI panel on the config page to paste and submit the YAML.

**Architecture:** Three new Python files (`orbweaver/seed/models.py`, `orbweaver/seed/loader.py`, `orbweaver/seed/__init__.py`) handle validation and pynetbox creation. The endpoint is added to `orbweaver/app.py`. The frontend gets a `seedInfrastructure` method in `useApi.ts` and a collapsible panel in `config.vue`.

**Tech Stack:** Python 3.10+, Pydantic v2, pynetbox 7.3, FastAPI, Vue 3 / Nuxt 4, TypeScript

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `orbweaver/seed/__init__.py` | Create | Package marker |
| `orbweaver/seed/models.py` | Create | Pydantic v2 models for YAML schema |
| `orbweaver/seed/loader.py` | Create | pynetbox upsert logic, dependency order |
| `orbweaver/app.py` | Modify | Add `POST /api/v1/seed` route |
| `orbweaver/pyproject.toml` | Modify | Add `orbweaver.seed` to packages list |
| `backend/tests/test_seed_models.py` | Create | Unit tests for Pydantic models |
| `backend/tests/test_seed_loader.py` | Create | Unit tests for loader (mocked pynetbox) |
| `backend/tests/test_seed_endpoint.py` | Create | Integration test for the endpoint |
| `frontend/app/types/api.ts` | Modify | Add `SeedResult` type |
| `frontend/app/composables/useApi.ts` | Modify | Add `seedInfrastructure()` method |
| `frontend/app/pages/config.vue` | Modify | Add collapsible Seed Infrastructure panel |

---

## Task 1: Pydantic seed models

**Files:**
- Create: `orbweaver/seed/__init__.py`
- Create: `orbweaver/seed/models.py`
- Create: `backend/tests/test_seed_models.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_seed_models.py
import pytest
import yaml as pyyaml
from orbweaver.seed.models import SeedData, SeedDevice, SeedDeviceType, SeedManufacturer


MINIMAL_YAML = """
sites:
  - name: theBASEMENT
    slug: thebasement
manufacturers:
  - name: Cisco
    slug: cisco
device_types:
  - manufacturer: Cisco
    model: Meraki MX67
    slug: cisco-meraki-mx67
    u_height: 1
device_roles:
  - name: Firewall
    slug: firewall
    color: f44336
racks:
  - name: theRACK
    site: theBASEMENT
    u_height: 42
devices:
  - name: fw-01
    device_type: Meraki MX67
    manufacturer: Cisco
    role: Firewall
    site: theBASEMENT
    status: active
"""


def test_parse_minimal_yaml():
    raw = pyyaml.safe_load(MINIMAL_YAML)
    data = SeedData.model_validate(raw)
    assert len(data.sites) == 1
    assert data.sites[0].name == "theBASEMENT"
    assert len(data.devices) == 1
    assert data.devices[0].name == "fw-01"


def test_tenant_is_optional():
    raw = pyyaml.safe_load(MINIMAL_YAML)
    data = SeedData.model_validate(raw)
    assert data.tenant is None


def test_device_optional_fields_default():
    raw = pyyaml.safe_load(MINIMAL_YAML)
    data = SeedData.model_validate(raw)
    dev = data.devices[0]
    assert dev.rack is None
    assert dev.position is None
    assert dev.face is None
    assert dev.serial is None
    assert dev.tags == []
    assert dev.parent_device is None
    assert dev.parent_bay is None


def test_invalid_missing_required_field():
    raw = pyyaml.safe_load(MINIMAL_YAML)
    raw["devices"][0].pop("name")
    with pytest.raises(Exception):
        SeedData.model_validate(raw)
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend && ../.venv/bin/pytest tests/test_seed_models.py -v
```
Expected: `ModuleNotFoundError: No module named 'orbweaver.seed'`

- [ ] **Step 3: Create package marker**

```python
# orbweaver/seed/__init__.py
```
(empty file)

- [ ] **Step 4: Create models**

```python
# orbweaver/seed/models.py
from __future__ import annotations

from pydantic import BaseModel, Field


class SeedTenant(BaseModel):
    name: str
    slug: str


class SeedSite(BaseModel):
    name: str
    slug: str
    description: str = ""
    status: str = "active"


class SeedRack(BaseModel):
    name: str
    site: str
    u_height: int = 42
    status: str = "active"


class SeedManufacturer(BaseModel):
    name: str
    slug: str


class SeedDeviceType(BaseModel):
    manufacturer: str
    model: str
    slug: str
    u_height: int = 1


class SeedDeviceRole(BaseModel):
    name: str
    slug: str
    color: str = "9e9e9e"


class SeedPlatform(BaseModel):
    name: str
    slug: str
    manufacturer: str | None = None


class SeedDevice(BaseModel):
    name: str
    device_type: str
    manufacturer: str
    role: str
    site: str
    rack: str | None = None
    position: int | None = None
    face: str | None = None
    airflow: str | None = None
    serial: str | None = None
    tenant: str | None = None
    platform: str | None = None
    status: str = "active"
    primary_ip4: str | None = None
    comments: str = ""
    tags: list[str] = Field(default_factory=list)
    parent_device: str | None = None
    parent_bay: str | None = None


class SeedData(BaseModel):
    tenant: SeedTenant | None = None
    sites: list[SeedSite] = Field(default_factory=list)
    racks: list[SeedRack] = Field(default_factory=list)
    manufacturers: list[SeedManufacturer] = Field(default_factory=list)
    device_types: list[SeedDeviceType] = Field(default_factory=list)
    device_roles: list[SeedDeviceRole] = Field(default_factory=list)
    platforms: list[SeedPlatform] = Field(default_factory=list)
    devices: list[SeedDevice] = Field(default_factory=list)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && ../.venv/bin/pytest tests/test_seed_models.py -v
```
Expected: 4 PASSED

- [ ] **Step 6: Register the package**

In `orbweaver/pyproject.toml`, add `"orbweaver.seed"` to the `packages` list:

```toml
[tool.setuptools]
package-dir = {"" = ".."}
packages = [
    "orbweaver",
    "orbweaver.collectors",
    "orbweaver.models",
    "orbweaver.review",
    "orbweaver.seed",
]
```

Then reinstall:
```bash
.venv/bin/pip install -e orbweaver/ --quiet
```

- [ ] **Step 7: Commit**

```bash
git add orbweaver/seed/__init__.py orbweaver/seed/models.py orbweaver/pyproject.toml backend/tests/test_seed_models.py
git commit -m "feat: add seed Pydantic models and package"
```

---

## Task 2: pynetbox loader

**Files:**
- Create: `orbweaver/seed/loader.py`
- Create: `backend/tests/test_seed_loader.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_seed_loader.py
from unittest.mock import MagicMock, call, patch

import pytest

from orbweaver.seed.loader import SeedResult, run_seed
from orbweaver.seed.models import (
    SeedData,
    SeedDevice,
    SeedDeviceRole,
    SeedDeviceType,
    SeedManufacturer,
    SeedPlatform,
    SeedRack,
    SeedSite,
    SeedTenant,
)


def _make_nb():
    """Build a mock pynetbox API with all required endpoints."""
    nb = MagicMock()
    # Default: .get() returns None (object doesn't exist yet)
    for endpoint in [
        nb.tenancy.tenants,
        nb.dcim.sites,
        nb.dcim.racks,
        nb.dcim.manufacturers,
        nb.dcim.device_types,
        nb.dcim.device_roles,
        nb.dcim.platforms,
        nb.dcim.devices,
        nb.extras.tags,
        nb.ipam.ip_addresses,
    ]:
        endpoint.get.return_value = None
        created = MagicMock()
        created.id = 1
        endpoint.create.return_value = created
    return nb


@patch("orbweaver.seed.loader._pynetbox_client")
def test_creates_site(mock_client):
    nb = _make_nb()
    mock_client.return_value = nb
    data = SeedData(sites=[SeedSite(name="theBASEMENT", slug="thebasement")])
    result = run_seed(data)
    nb.dcim.sites.create.assert_called_once()
    assert result.created["sites"] == 1
    assert result.skipped["sites"] == 0


@patch("orbweaver.seed.loader._pynetbox_client")
def test_skips_existing_site(mock_client):
    nb = _make_nb()
    mock_client.return_value = nb
    nb.dcim.sites.get.return_value = MagicMock(id=1)  # already exists
    data = SeedData(sites=[SeedSite(name="theBASEMENT", slug="thebasement")])
    result = run_seed(data)
    nb.dcim.sites.create.assert_not_called()
    assert result.skipped["sites"] == 1


@patch("orbweaver.seed.loader._pynetbox_client")
def test_creates_tenant(mock_client):
    nb = _make_nb()
    mock_client.return_value = nb
    from orbweaver.seed.models import SeedTenant
    data = SeedData(tenant=SeedTenant(name="SVA-DEV", slug="sva-dev"))
    result = run_seed(data)
    nb.tenancy.tenants.create.assert_called_once()
    assert result.created["tenants"] == 1


@patch("orbweaver.seed.loader._pynetbox_client")
def test_creates_device_with_rack(mock_client):
    nb = _make_nb()
    mock_client.return_value = nb

    site_obj = MagicMock(id=10)
    rack_obj = MagicMock(id=20)
    role_obj = MagicMock(id=30)
    mfr_obj = MagicMock(id=40)
    dt_obj = MagicMock(id=50)

    nb.dcim.sites.get.return_value = site_obj
    nb.dcim.racks.filter.return_value = [rack_obj]
    nb.dcim.device_roles.get.return_value = role_obj
    nb.dcim.manufacturers.get.return_value = mfr_obj
    nb.dcim.device_types.get.return_value = dt_obj

    data = SeedData(
        devices=[
            SeedDevice(
                name="fw-01",
                device_type="Meraki MX67",
                manufacturer="Cisco",
                role="Firewall",
                site="theBASEMENT",
                rack="theRACK",
                position=10,
                face="front",
                serial="ABC123",
                status="active",
            )
        ]
    )
    result = run_seed(data)
    nb.dcim.devices.create.assert_called_once()
    call_kwargs = nb.dcim.devices.create.call_args[1]
    assert call_kwargs["name"] == "fw-01"
    assert call_kwargs["rack"] == 20
    assert call_kwargs["position"] == 10
    assert call_kwargs["serial"] == "ABC123"
    assert result.created["devices"] == 1


@patch("orbweaver.seed.loader._pynetbox_client")
def test_no_client_returns_error(mock_client):
    mock_client.return_value = None
    data = SeedData(sites=[SeedSite(name="X", slug="x")])
    result = run_seed(data)
    assert len(result.errors) == 1
    assert "NETBOX_HOST" in result.errors[0]
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd backend && ../.venv/bin/pytest tests/test_seed_loader.py -v
```
Expected: `ImportError: cannot import name 'run_seed' from 'orbweaver.seed.loader'`

- [ ] **Step 3: Implement the loader**

```python
# orbweaver/seed/loader.py
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_HOST_VAR = "NETBOX_HOST"
_PORT_VAR = "NETBOX_PORT"
_TOKEN_VAR = "NETBOX_TOKEN"


def _pynetbox_client():
    import pynetbox
    host = os.environ.get(_HOST_VAR, "").strip()
    port = os.environ.get(_PORT_VAR, "8000").strip()
    token = os.environ.get(_TOKEN_VAR, "").strip()
    if not host or not token:
        return None
    return pynetbox.api(f"http://{host}:{port}", token=token)


@dataclass
class SeedResult:
    created: dict[str, int] = field(default_factory=lambda: {
        "tenants": 0, "sites": 0, "racks": 0, "manufacturers": 0,
        "device_types": 0, "device_roles": 0, "platforms": 0,
        "devices": 0, "tags": 0,
    })
    skipped: dict[str, int] = field(default_factory=lambda: {
        "tenants": 0, "sites": 0, "racks": 0, "manufacturers": 0,
        "device_types": 0, "device_roles": 0, "platforms": 0,
        "devices": 0, "tags": 0,
    })
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"created": self.created, "skipped": self.skipped, "errors": self.errors}


def _get_or_create(endpoint, lookup: dict, create: dict, result: SeedResult, key: str):
    """Return existing object or create it. Updates result counters."""
    try:
        obj = endpoint.get(**lookup)
        if obj:
            result.skipped[key] += 1
            return obj
        obj = endpoint.create(**create)
        result.created[key] += 1
        return obj
    except Exception as exc:
        result.errors.append(f"{key}: {exc}")
        return None


def run_seed(data) -> SeedResult:
    from orbweaver.seed.models import SeedData
    result = SeedResult()

    nb = _pynetbox_client()
    if nb is None:
        result.errors.append(
            f"NetBox not configured: set {_HOST_VAR} and {_TOKEN_VAR} env vars."
        )
        return result

    # ── 1. Tenant ────────────────────────────────────────────────────────
    tenant_obj = None
    if data.tenant:
        tenant_obj = _get_or_create(
            nb.tenancy.tenants,
            {"slug": data.tenant.slug},
            {"name": data.tenant.name, "slug": data.tenant.slug},
            result, "tenants",
        )

    # ── 2. Sites ─────────────────────────────────────────────────────────
    site_map: dict[str, object] = {}
    for site in data.sites:
        obj = _get_or_create(
            nb.dcim.sites,
            {"slug": site.slug},
            {"name": site.name, "slug": site.slug,
             "description": site.description, "status": site.status},
            result, "sites",
        )
        if obj:
            site_map[site.name] = obj

    # ── 3. Manufacturers ─────────────────────────────────────────────────
    mfr_map: dict[str, object] = {}
    for mfr in data.manufacturers:
        obj = _get_or_create(
            nb.dcim.manufacturers,
            {"slug": mfr.slug},
            {"name": mfr.name, "slug": mfr.slug},
            result, "manufacturers",
        )
        if obj:
            mfr_map[mfr.name] = obj

    # ── 4. Device types ──────────────────────────────────────────────────
    dt_map: dict[str, object] = {}
    for dt in data.device_types:
        mfr_obj = mfr_map.get(dt.manufacturer)
        create_kwargs: dict = {"model": dt.model, "slug": dt.slug, "u_height": dt.u_height}
        if mfr_obj:
            create_kwargs["manufacturer"] = mfr_obj.id
        obj = _get_or_create(
            nb.dcim.device_types,
            {"slug": dt.slug},
            create_kwargs,
            result, "device_types",
        )
        if obj:
            dt_map[dt.model] = obj

    # ── 5. Device roles ──────────────────────────────────────────────────
    role_map: dict[str, object] = {}
    for role in data.device_roles:
        obj = _get_or_create(
            nb.dcim.device_roles,
            {"slug": role.slug},
            {"name": role.name, "slug": role.slug, "color": role.color},
            result, "device_roles",
        )
        if obj:
            role_map[role.name] = obj

    # ── 6. Platforms ─────────────────────────────────────────────────────
    platform_map: dict[str, object] = {}
    for plat in data.platforms:
        create_kwargs = {"name": plat.name, "slug": plat.slug}
        if plat.manufacturer:
            mfr_obj = mfr_map.get(plat.manufacturer)
            if mfr_obj:
                create_kwargs["manufacturer"] = mfr_obj.id
        obj = _get_or_create(
            nb.dcim.platforms,
            {"slug": plat.slug},
            create_kwargs,
            result, "platforms",
        )
        if obj:
            platform_map[plat.name] = obj

    # ── 7. Racks ─────────────────────────────────────────────────────────
    rack_map: dict[str, object] = {}
    for rack in data.racks:
        site_obj = site_map.get(rack.site)
        create_kwargs = {"name": rack.name, "u_height": rack.u_height, "status": rack.status}
        if site_obj:
            create_kwargs["site"] = site_obj.id
        obj = _get_or_create(
            nb.dcim.racks,
            {"name": rack.name},
            create_kwargs,
            result, "racks",
        )
        if obj:
            rack_map[rack.name] = obj

    # ── 8. Devices (two-pass: parents first) ─────────────────────────────
    device_map: dict[str, object] = {}
    parents = [d for d in data.devices if not d.parent_device]
    children = [d for d in data.devices if d.parent_device]

    for dev in parents:
        obj = _create_device(nb, dev, site_map, rack_map, role_map, dt_map, platform_map,
                             tenant_obj, result)
        if obj:
            device_map[dev.name] = obj

    for dev in children:
        obj = _create_device(nb, dev, site_map, rack_map, role_map, dt_map, platform_map,
                             tenant_obj, result)
        if obj and dev.parent_device and dev.parent_bay:
            _assign_device_bay(nb, obj, dev.parent_device, dev.parent_bay, device_map, result)

    return result


def _create_device(nb, dev, site_map, rack_map, role_map, dt_map, platform_map,
                   tenant_obj, result: SeedResult):
    """Create or skip a single device. Returns the pynetbox object or None."""
    # Check existing by serial (most reliable) or name
    existing = None
    if dev.serial:
        existing = nb.dcim.devices.get(serial=dev.serial)
    if not existing:
        existing = nb.dcim.devices.get(name=dev.name)
    if existing:
        result.skipped["devices"] += 1
        return existing

    create_kwargs: dict = {
        "name": dev.name,
        "status": dev.status,
        "comments": dev.comments,
    }

    site_obj = site_map.get(dev.site)
    if site_obj:
        create_kwargs["site"] = site_obj.id

    dt_obj = dt_map.get(dev.device_type)
    if dt_obj:
        create_kwargs["device_type"] = dt_obj.id

    role_obj = role_map.get(dev.role)
    if role_obj:
        create_kwargs["role"] = role_obj.id

    if dev.rack:
        rack_results = list(nb.dcim.racks.filter(name=dev.rack))
        if rack_results:
            create_kwargs["rack"] = rack_results[0].id

    if dev.position is not None:
        create_kwargs["position"] = dev.position

    if dev.face:
        create_kwargs["face"] = dev.face

    if dev.airflow:
        create_kwargs["airflow"] = dev.airflow

    if dev.serial:
        create_kwargs["serial"] = dev.serial

    if dev.platform:
        plat_obj = platform_map.get(dev.platform)
        if plat_obj:
            create_kwargs["platform"] = plat_obj.id

    if dev.tenant:
        tenant_results = list(nb.tenancy.tenants.filter(name=dev.tenant))
        if tenant_results:
            create_kwargs["tenant"] = tenant_results[0].id
    elif tenant_obj:
        create_kwargs["tenant"] = tenant_obj.id

    # Tags: get or create each tag, collect IDs
    if dev.tags:
        tag_ids = []
        for tag_name in dev.tags:
            tag = nb.extras.tags.get(name=tag_name)
            if not tag:
                slug = tag_name.lower().replace(" ", "-")
                tag = nb.extras.tags.create(name=tag_name, slug=slug, color="9e9e9e")
                result.created["tags"] += 1
            if tag:
                tag_ids.append(tag.id)
        create_kwargs["tags"] = tag_ids

    try:
        obj = nb.dcim.devices.create(**create_kwargs)
        result.created["devices"] += 1

        # Primary IP: create bare IP then assign to device
        if dev.primary_ip4 and obj:
            _assign_primary_ip(nb, obj, dev.primary_ip4, result)

        return obj
    except Exception as exc:
        result.errors.append(f"device '{dev.name}': {exc}")
        return None


def _assign_device_bay(nb, child_obj, parent_name: str, bay_name: str,
                       device_map: dict, result: SeedResult) -> None:
    parent_obj = device_map.get(parent_name)
    if not parent_obj:
        result.errors.append(f"parent device '{parent_name}' not found for bay assignment")
        return
    try:
        bays = list(nb.dcim.device_bays.filter(device_id=parent_obj.id, name=bay_name))
        if not bays:
            result.errors.append(f"bay '{bay_name}' not found on device '{parent_name}'")
            return
        bay = bays[0]
        bay.installed_device = child_obj.id
        bay.save()
    except Exception as exc:
        result.errors.append(f"bay assignment '{parent_name}/{bay_name}': {exc}")


def _assign_primary_ip(nb, device_obj, address: str, result: SeedResult) -> None:
    try:
        existing_ip = nb.ipam.ip_addresses.get(address=address)
        if not existing_ip:
            existing_ip = nb.ipam.ip_addresses.create(address=address)
        device_obj.primary_ip4 = existing_ip.id
        device_obj.save()
    except Exception as exc:
        result.errors.append(f"primary_ip4 '{address}' for device: {exc}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && ../.venv/bin/pytest tests/test_seed_loader.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add orbweaver/seed/loader.py backend/tests/test_seed_loader.py
git commit -m "feat: add seed loader with pynetbox upsert logic"
```

---

## Task 3: FastAPI endpoint

**Files:**
- Modify: `orbweaver/app.py`
- Create: `backend/tests/test_seed_endpoint.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_seed_endpoint.py
from unittest.mock import MagicMock, patch

import yaml as pyyaml
from fastapi.testclient import TestClient

from device_discovery.server import app

client = TestClient(app)

SEED_YAML = """
sites:
  - name: theBASEMENT
    slug: thebasement
manufacturers:
  - name: Cisco
    slug: cisco
device_types:
  - manufacturer: Cisco
    model: Meraki MX67
    slug: cisco-meraki-mx67
    u_height: 1
device_roles:
  - name: Firewall
    slug: firewall
    color: f44336
racks:
  - name: theRACK
    site: theBASEMENT
    u_height: 42
devices:
  - name: fw-01
    device_type: Meraki MX67
    manufacturer: Cisco
    role: Firewall
    site: theBASEMENT
    status: active
"""


@patch("orbweaver.seed.loader._pynetbox_client")
def test_seed_endpoint_returns_200(mock_client):
    nb = MagicMock()
    for ep in [nb.tenancy.tenants, nb.dcim.sites, nb.dcim.racks,
               nb.dcim.manufacturers, nb.dcim.device_types, nb.dcim.device_roles,
               nb.dcim.platforms, nb.dcim.devices, nb.extras.tags, nb.ipam.ip_addresses]:
        ep.get.return_value = None
        created = MagicMock()
        created.id = 1
        ep.create.return_value = created
    nb.dcim.racks.filter.return_value = [MagicMock(id=1)]
    mock_client.return_value = nb

    response = client.post(
        "/api/v1/seed",
        content=SEED_YAML,
        headers={"Content-Type": "application/x-yaml"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "created" in body
    assert "skipped" in body
    assert "errors" in body
    assert body["created"]["sites"] == 1
    assert body["created"]["devices"] == 1


def test_seed_endpoint_invalid_yaml_returns_400():
    response = client.post(
        "/api/v1/seed",
        content="{ not: [valid yaml",
        headers={"Content-Type": "application/x-yaml"},
    )
    assert response.status_code == 400


def test_seed_endpoint_invalid_schema_returns_422():
    response = client.post(
        "/api/v1/seed",
        content="devices:\n  - name: 123\n    missing_required: true\n",
        headers={"Content-Type": "application/x-yaml"},
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend && ../.venv/bin/pytest tests/test_seed_endpoint.py -v
```
Expected: `404 Not Found` for the seed endpoint

- [ ] **Step 3: Add the route to `orbweaver/app.py`**

Add these imports near the top of the orbweaver imports section (after the existing `from orbweaver.*` imports):

```python
from orbweaver.seed.loader import run_seed
from orbweaver.seed.models import SeedData
```

Add the route after the existing routes (before any closing code):

```python
@app.post("/api/v1/seed")
async def seed_infrastructure(request: Request):
    """
    Populate NetBox with infrastructure objects from a YAML body.

    Accepts raw YAML describing sites, racks, manufacturers, device types,
    device roles, platforms, and devices. Creates missing objects via pynetbox;
    skips existing ones (idempotent).
    """
    body = await request.body()
    try:
        raw = yaml.safe_load(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="YAML body must be a mapping")
    try:
        seed_data = SeedData.model_validate(raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = run_seed(seed_data)
    return result.as_dict()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && ../.venv/bin/pytest tests/test_seed_endpoint.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
cd backend && ../.venv/bin/pytest tests/ -v --tb=short
```
Expected: all existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add orbweaver/app.py backend/tests/test_seed_endpoint.py
git commit -m "feat: add POST /api/v1/seed endpoint"
```

---

## Task 4: Frontend — type + useApi

**Files:**
- Modify: `frontend/app/types/api.ts`
- Modify: `frontend/app/composables/useApi.ts`

- [ ] **Step 1: Add `SeedResult` to `frontend/app/types/api.ts`**

Append to the end of the file:

```typescript
// ── Seed ─────────────────────────────────────────────────────────────────

export interface SeedCounts {
  tenants: number
  sites: number
  racks: number
  manufacturers: number
  device_types: number
  device_roles: number
  platforms: number
  devices: number
  tags: number
}

export interface SeedResult {
  created: SeedCounts
  skipped: SeedCounts
  errors: string[]
}
```

- [ ] **Step 2: Add `seedInfrastructure` to `frontend/app/composables/useApi.ts`**

Add the import at the top of the file with the other type imports:

```typescript
import type {
  BackendStatus,
  CollectorInfo,
  DiscoverJobResponse,
  IngestRequest,
  IngestResponse,
  ItemStatus,
  ReviewItem,
  ReviewSession,
  ReviewSummary,
  SeedResult,
} from '~/types/api'
```

Add the method in the `useApi` body after `triggerDiscover`:

```typescript
function seedInfrastructure(yamlBody: string): Promise<SeedResult> {
  return $fetch(url('/api/v1/seed'), {
    method: 'POST',
    body: yamlBody,
    headers: { 'Content-Type': 'application/x-yaml' },
  })
}
```

Add `seedInfrastructure` to the return object:

```typescript
return {
  getStatus,
  listCollectors,
  triggerDiscover,
  seedInfrastructure,
  pollDiscoverJob,
  listReviews,
  getReview,
  deleteReview,
  patchDeviceItem,
  bulkUpdate,
  ingest,
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/types/api.ts frontend/app/composables/useApi.ts
git commit -m "feat: add seedInfrastructure API method and SeedResult type"
```

---

## Task 5: Frontend — Seed Infrastructure panel

**Files:**
- Modify: `frontend/app/pages/config.vue`

- [ ] **Step 1: Add seed state to the `<script setup>` block**

Add at the bottom of the existing `<script setup>` section in `config.vue`, before `</script>`:

```typescript
const DEFAULT_SEED_YAML = `tenant:
  name: SVA-DEV
  slug: sva-dev

sites:
  - name: theBASEMENT
    slug: thebasement
    description: Bastel Keller
    status: active

racks:
  - name: theMAST
    site: theBASEMENT
    u_height: 42
  - name: theRACK
    site: theBASEMENT
    u_height: 42

manufacturers:
  - name: Cisco
    slug: cisco
  - name: Opengear
    slug: opengear
  - name: APC
    slug: apc
  - name: Kentix
    slug: kentix
  - name: Generic
    slug: generic

device_types:
  - manufacturer: Cisco
    model: Meraki MX67
    slug: cisco-meraki-mx67
    u_height: 1
  - manufacturer: Cisco
    model: Meraki MR45
    slug: cisco-meraki-mr45
    u_height: 1
  - manufacturer: Cisco
    model: Meraki MS120-8FP
    slug: cisco-meraki-ms120-8fp
    u_height: 1
  - manufacturer: Cisco
    model: Meraki MV13
    slug: meraki-mv13
    u_height: 1
  - manufacturer: Cisco
    model: Meraki MG21
    slug: cisco-meraki-mg21
    u_height: 1
  - manufacturer: Cisco
    model: WS-C3650-24PS
    slug: ws-c3650-24ps
    u_height: 1
  - manufacturer: Opengear
    model: OM1204-4E-L
    slug: opengear-om1204-4e-l
    u_height: 1
  - manufacturer: Opengear
    model: OM1208-8E-L
    slug: opengear-om1208-8e-l
    u_height: 1
  - manufacturer: APC
    model: SCL500
    slug: apc-scl500
    u_height: 2
  - manufacturer: Kentix
    model: KPMDU-RC-1600C13C19-2-16-H
    slug: kentix-kpmdu-rc-1600c13c19-2-16-h
    u_height: 1
  - manufacturer: Generic
    model: Rack shelf
    slug: rack-shelf
    u_height: 1
  - manufacturer: Generic
    model: Cable Duct
    slug: calbe-duct
    u_height: 1

device_roles:
  - name: Switch
    slug: switch
    color: 2196f3
  - name: Firewall
    slug: firewall
    color: f44336
  - name: Console Server
    slug: console-server
    color: 9c27b0
  - name: Access Point
    slug: access-point
    color: 4caf50
  - name: PDU
    slug: pdu
    color: ff9800
  - name: UPS
    slug: ups
    color: 795548
  - name: Rack Shelf
    slug: rack-shelf
    color: 9e9e9e
  - name: Cable Duct
    slug: cable-duct
    color: 607d8b
  - name: Cam
    slug: cam
    color: 00bcd4
  - name: WAN Gateway
    slug: wan-gateway
    color: 673ab7

platforms:
  - name: Cisco IOS-XE 16.12.10a
    slug: cisco-ios-xe-161210a
    manufacturer: Cisco

devices:
  - name: DC-Rack
    device_type: OM1204-4E-L
    manufacturer: Opengear
    role: Console Server
    site: theBASEMENT
    rack: theMAST
    position: 1
    face: front
    airflow: passive
    serial: "12042503319976"
    tenant: SVA-DEV
    status: active
  - name: Duct 1
    device_type: Cable Duct
    manufacturer: Generic
    role: Cable Duct
    site: theBASEMENT
    rack: theMAST
    position: 2
    face: front
    status: active
  - name: Duct 2
    device_type: Cable Duct
    manufacturer: Generic
    role: Cable Duct
    site: theBASEMENT
    rack: theMAST
    position: 5
    face: front
    status: active
  - name: DC Rack PDU
    device_type: KPMDU-RC-1600C13C19-2-16-H
    manufacturer: Kentix
    role: PDU
    site: theBASEMENT
    rack: theMAST
    position: 6
    face: front
    airflow: passive
    serial: "3012001510294"
    tenant: SVA-DEV
    status: active
  - name: Rack Shelf 1
    device_type: Rack shelf
    manufacturer: Generic
    role: Rack Shelf
    site: theBASEMENT
    rack: theMAST
    position: 6
    face: rear
    tenant: SVA-DEV
    status: active
  - name: DC-Rack-USV
    device_type: SCL500
    manufacturer: APC
    role: UPS
    site: theBASEMENT
    rack: theMAST
    position: 8
    face: front
    airflow: passive
    serial: "5S2511T97670"
    tenant: SVA-DEV
    status: active
  - name: DC-MX
    device_type: Meraki MX67
    manufacturer: Cisco
    role: Firewall
    site: theBASEMENT
    rack: theMAST
    airflow: passive
    serial: "Q2FY-7LVE-TR23"
    tenant: SVA-DEV
    status: active
    parent_device: Rack Shelf 1
    parent_bay: Bay 1
  - name: DC-WiFi
    device_type: Meraki MR45
    manufacturer: Cisco
    role: Access Point
    site: theBASEMENT
    rack: theMAST
    airflow: passive
    serial: "Q3AA-RELF-Y97N"
    tenant: SVA-DEV
    status: active
  - name: theRACK-Rack
    device_type: OM1208-8E-L
    manufacturer: Opengear
    role: Console Server
    site: theBASEMENT
    rack: theRACK
    position: 1
    face: front
    airflow: front-to-rear
    serial: "12082104119430"
    tenant: SVA-DEV
    status: active
  - name: theRACK-theROUTER
    device_type: Meraki MX67
    manufacturer: Cisco
    role: Firewall
    site: theBASEMENT
    rack: theRACK
    airflow: passive
    serial: "Q2FY-CN7E-4K5K"
    tenant: SVA-DEV
    status: active
  - name: thRACK-theSWITCH
    device_type: Meraki MS120-8FP
    manufacturer: Cisco
    role: Switch
    site: theBASEMENT
    rack: theRACK
    face: front
    airflow: front-to-rear
    serial: "Q2CX-DJYA-EKUU"
    tenant: SVA-DEV
    status: active
  - name: theRACK-theWIFI
    device_type: Meraki MR45
    manufacturer: Cisco
    role: Access Point
    site: theBASEMENT
    rack: theRACK
    airflow: passive
    serial: "Q3AA-4JKZ-UBPS"
    tenant: SVA-DEV
    status: active
    comments: "Mounted on top of theRACK."
  - name: theRACK-theCAM
    device_type: Meraki MV13
    manufacturer: Cisco
    role: Cam
    site: theBASEMENT
    rack: theRACK
    serial: "Q4EE-5HBF-Q6F7"
    tenant: SVA-DEV
    status: active
    comments: "Mounted on the top."
  - name: theRACK-theGATEWAY
    device_type: Meraki MG21
    manufacturer: Cisco
    role: WAN Gateway
    site: theBASEMENT
    rack: theRACK
    airflow: passive
    serial: "Q2VY-UBTR-V2XH"
    tenant: SVA-DEV
    status: active
  - name: C3650
    device_type: WS-C3650-24PS
    manufacturer: Cisco
    role: Switch
    site: theBASEMENT
    platform: Cisco IOS-XE 16.12.10a
    serial: "FDO2125Q10A"
    tenant: SVA-DEV
    status: active
    primary_ip4: "192.168.12.100/24"
    tags:
      - orbweaver-2
      - prod-test
`

const seedYaml = ref(DEFAULT_SEED_YAML)
const seedExpanded = ref(false)
const seeding = ref(false)
const seedResult = ref<import('~/types/api').SeedResult | null>(null)
const seedError = ref<string | null>(null)

async function runSeed() {
  seeding.value = true
  seedResult.value = null
  seedError.value = null
  try {
    seedResult.value = await api.seedInfrastructure(seedYaml.value)
  } catch (err: unknown) {
    seedError.value = err instanceof Error ? err.message : String(err)
  } finally {
    seeding.value = false
  }
}
```

- [ ] **Step 2: Add the Seed Infrastructure panel to the `<template>`**

In `config.vue`, find the closing `</div>` of the outer grid wrapper (the very last `</div>` before `</template>`). Insert the following panel block **before** that closing `</div>`:

```html
    <!-- Seed Infrastructure panel (full width, below the two columns) -->
    <div class="col-span-1 lg:col-span-2 rounded-lg border">
      <button
        class="flex w-full items-center justify-between px-4 py-3 text-sm font-medium hover:bg-muted/30 transition-colors"
        @click="seedExpanded = !seedExpanded"
      >
        <span>Seed Infrastructure</span>
        <span class="text-muted-foreground text-xs">{{ seedExpanded ? '▲ collapse' : '▼ expand' }}</span>
      </button>

      <div v-if="seedExpanded" class="border-t px-4 py-4 space-y-3">
        <p class="text-xs text-muted-foreground">
          Paste your infrastructure YAML below and click Seed to create sites, racks, manufacturers,
          device types, roles, and devices in NetBox via the REST API.
          Safe to run multiple times — existing objects are skipped.
        </p>

        <textarea
          v-model="seedYaml"
          rows="20"
          class="w-full rounded-md border bg-background px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-ring"
          spellcheck="false"
        />

        <div v-if="seedError" class="rounded-md bg-destructive/10 border border-destructive/30 p-3 text-xs text-destructive font-mono whitespace-pre-wrap">
          {{ seedError }}
        </div>

        <div v-if="seedResult" class="rounded-md bg-muted/30 border p-3 text-xs font-mono space-y-1">
          <p class="font-medium text-foreground">Seed complete</p>
          <p class="text-muted-foreground">
            Created — sites: {{ seedResult.created.sites }}, racks: {{ seedResult.created.racks }},
            manufacturers: {{ seedResult.created.manufacturers }},
            device types: {{ seedResult.created.device_types }},
            roles: {{ seedResult.created.device_roles }},
            devices: {{ seedResult.created.devices }}
          </p>
          <p class="text-muted-foreground">
            Skipped — sites: {{ seedResult.skipped.sites }}, devices: {{ seedResult.skipped.devices }}
          </p>
          <div v-if="seedResult.errors.length > 0" class="text-destructive mt-1">
            <p class="font-medium">Errors:</p>
            <p v-for="(e, i) in seedResult.errors" :key="i">{{ e }}</p>
          </div>
        </div>

        <button
          :disabled="seeding"
          class="w-full rounded-md bg-primary py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          @click="runSeed"
        >
          {{ seeding ? 'Seeding…' : 'Seed Infrastructure' }}
        </button>
      </div>
    </div>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/pages/config.vue
git commit -m "feat: add Seed Infrastructure panel to config page"
```

---

## Task 6: Smoke test end-to-end

- [ ] **Step 1: Start the backend**

```bash
just backend-start
```

- [ ] **Step 2: Test the endpoint via curl**

```bash
curl -s -X POST http://localhost:8073/api/v1/seed \
  -H "Content-Type: application/x-yaml" \
  -d 'sites:
  - name: TestSite
    slug: testsite
' | python3 -m json.tool
```

Expected response shape:
```json
{
  "created": { "sites": 1, "devices": 0, ... },
  "skipped": { "sites": 0, ... },
  "errors": []
}
```

If `NETBOX_HOST` is not set, expected:
```json
{ "created": {...}, "skipped": {...}, "errors": ["NetBox not configured: set NETBOX_HOST and NETBOX_TOKEN env vars."] }
```

- [ ] **Step 3: Open UI and verify panel**

Navigate to `http://localhost:3000/config`, scroll to the bottom, click "Seed Infrastructure" to expand it, verify the default YAML appears in the textarea and the "Seed Infrastructure" button is present.

- [ ] **Step 4: Run full test suite one final time**

```bash
just test
```
Expected: all tests pass

- [ ] **Step 5: Final commit**

```bash
git add -p  # stage any unstaged cleanup
git commit -m "chore: final smoke test verification for seed feature"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ `POST /api/v1/seed` with raw YAML body → Task 3
- ✅ Pydantic validation before pynetbox calls → Task 1
- ✅ Dependency order (tenant→site→mfr→dt→role→platform→rack→device) → Task 2
- ✅ Two-pass device creation (parents before bay children) → Task 2
- ✅ Idempotent get-or-create → Task 2
- ✅ Primary IP creation → Task 2 (`_assign_primary_ip`)
- ✅ Tag creation → Task 2 (`_create_device` tags block)
- ✅ `NETBOX_HOST` / `NETBOX_PORT` / `NETBOX_TOKEN` env vars → Task 2
- ✅ UI textarea with default YAML → Task 5
- ✅ UI result summary toast → Task 5 (inline result block)
- ✅ `orbweaver.seed` registered in pyproject.toml → Task 1 Step 6
- ✅ `SeedResult` frontend type → Task 4
- ✅ `seedInfrastructure` in useApi → Task 4
