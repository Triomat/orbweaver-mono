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
    try:
        existing = None
        if dev.serial:
            existing = nb.dcim.devices.get(serial=dev.serial)
        if not existing:
            site_obj = site_map.get(dev.site)
            lookup = {"name": dev.name}
            if site_obj:
                lookup["site_id"] = site_obj.id
            # Scope by tenant so same-named devices in different tenants are distinct
            if dev.tenant:
                tenant_results = list(nb.tenancy.tenants.filter(name=dev.tenant))
                if tenant_results:
                    lookup["tenant_id"] = tenant_results[0].id
            elif tenant_obj:
                lookup["tenant_id"] = tenant_obj.id
            existing = nb.dcim.devices.get(**lookup)
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
                site_name = dev.site
                rack = next(
                    (r for r in rack_results if r.site and r.site.name == site_name),
                    rack_results[0],
                )
                create_kwargs["rack"] = rack.id

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

        obj = nb.dcim.devices.create(**create_kwargs)
        result.created["devices"] += 1

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
    # Creates the IP object in NetBox but does NOT set it as primary_ip4.
    # NetBox rejects primary_ip4 until the IP is assigned to a device interface,
    # which only happens after orbweaver discovery runs.
    try:
        existing_ip = nb.ipam.ip_addresses.get(address=address)
        if not existing_ip:
            nb.ipam.ip_addresses.create(address=address)
    except Exception as exc:
        result.errors.append(f"ip_address '{address}': {exc}")
