from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_HOST_VAR = "NETBOX_HOST"
_PORT_VAR = "NETBOX_PORT"
_TOKEN_VAR = "NETBOX_TOKEN"
_MGMT_INTERFACE_NAME = "mgmt0"
_MGMT_INTERFACE_TYPE = "virtual"


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
        "devices": 0, "tags": 0, "vlans": 0, "interfaces": 0,
    })
    skipped: dict[str, int] = field(default_factory=lambda: {
        "tenants": 0, "sites": 0, "racks": 0, "manufacturers": 0,
        "device_types": 0, "device_roles": 0, "platforms": 0,
        "devices": 0, "tags": 0, "vlans": 0, "interfaces": 0,
    })
    updated: dict[str, int] = field(default_factory=lambda: {
        "tenants": 0, "sites": 0, "racks": 0, "manufacturers": 0,
        "device_types": 0, "device_roles": 0, "platforms": 0,
        "devices": 0, "tags": 0, "vlans": 0, "interfaces": 0,
    })
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"created": self.created, "skipped": self.skipped, "updated": self.updated, "errors": self.errors}


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
        lookup_kwargs = {"name": rack.name}
        create_kwargs = {"name": rack.name, "u_height": rack.u_height, "status": rack.status}
        if site_obj:
            lookup_kwargs["site_id"] = site_obj.id
            create_kwargs["site"] = site_obj.id
        obj = _get_or_create(
            nb.dcim.racks,
            lookup_kwargs,
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

    # ── 9. VLANs ─────────────────────────────────────────────────────────
    if data.vlans:
        _seed_vlans(nb, data.vlans, result)

    # ── 10. Interfaces ───────────────────────────────────────────────────
    for dev in data.devices:
        if not dev.interfaces:
            continue
        device_obj = device_map.get(dev.name)
        if not device_obj:
            result.errors.append(f"interface device='{dev.name}': device not found")
            continue
        created, updated, skipped, iface_errors = _seed_interfaces(nb, device_obj, dev.interfaces)
        result.created["interfaces"] += created
        result.updated["interfaces"] += updated
        result.skipped["interfaces"] += skipped
        for err in iface_errors:
            result.errors.append(
                f"interface device='{err['device']}' name='{err['name']}': {err['reason']}"
            )

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
            rack_obj = rack_map.get(dev.rack)
            if rack_obj:
                create_kwargs["rack"] = rack_obj.id

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
    try:
        interface_obj = _get_or_create_management_interface(nb, device_obj, result)
        if interface_obj is None:
            return

        ip_obj = _get_or_create_ip_for_interface(nb, interface_obj, address, result)
        if ip_obj is None:
            return

        current_primary = getattr(device_obj, "primary_ip4", None)
        current_primary_id = getattr(current_primary, "id", current_primary)
        if current_primary_id != ip_obj.id:
            device_obj.primary_ip4 = ip_obj.id
            device_obj.save()
    except Exception as exc:
        result.errors.append(f"ip_address '{address}': {exc}")


def _get_or_create_management_interface(nb, device_obj, result: SeedResult):
    try:
        interfaces = list(
            nb.dcim.interfaces.filter(device_id=device_obj.id, name=_MGMT_INTERFACE_NAME)
        )
        if interfaces:
            return interfaces[0]

        return nb.dcim.interfaces.create(
            device=device_obj.id,
            name=_MGMT_INTERFACE_NAME,
            type=_MGMT_INTERFACE_TYPE,
        )
    except Exception as exc:
        result.errors.append(
            f"device '{getattr(device_obj, 'name', device_obj.id)}' interface '{_MGMT_INTERFACE_NAME}': {exc}"
        )
        return None


def _get_or_create_ip_for_interface(nb, interface_obj, address: str, result: SeedResult):
    try:
        ip_obj = nb.ipam.ip_addresses.get(address=address)
        if not ip_obj:
            return nb.ipam.ip_addresses.create(
                address=address,
                assigned_object_type="dcim.interface",
                assigned_object_id=interface_obj.id,
            )

        current_type = getattr(ip_obj, "assigned_object_type", None)
        current_id = getattr(ip_obj, "assigned_object_id", None)

        if current_type in (None, "") and current_id in (None, ""):
            ip_obj.assigned_object_type = "dcim.interface"
            ip_obj.assigned_object_id = interface_obj.id
            ip_obj.save()
            return ip_obj

        if current_type == "dcim.interface" and current_id == interface_obj.id:
            return ip_obj

        result.errors.append(
            f"ip_address '{address}' is already assigned to a different object"
        )
        return None
    except Exception as exc:
        result.errors.append(f"ip_address '{address}': {exc}")
        return None


def _find_vlan(nb, vlan_spec) -> object | None:
    """Find VLAN by (vid, site) tuple where site is optional (global when None)."""
    try:
        filters = {"vid": vlan_spec.vid}
        if vlan_spec.site:
            site_obj = nb.dcim.sites.get(name=vlan_spec.site)
            if not site_obj:
                return None
            filters["site_id"] = site_obj.id
        else:
            # Global VLAN: site must be None
            filters["site_id"] = None
        return nb.ipam.vlans.get(**filters)
    except Exception:
        return None


def _seed_vlans(nb, vlans_list: list, result: SeedResult) -> None:
    """Seed VLANs into NetBox. Updates result counters in place."""

    for vlan_spec in vlans_list:
        try:
            vlan_obj = _find_vlan(nb, vlan_spec)
            if vlan_obj:
                result.skipped["vlans"] += 1
                continue

            # Create new VLAN
            vlan_data = {
                "vid": vlan_spec.vid,
                "name": vlan_spec.name,
            }
            if vlan_spec.site:
                site_obj = nb.dcim.sites.get(name=vlan_spec.site)
                if site_obj:
                    vlan_data["site"] = site_obj.id

            nb.ipam.vlans.create(**vlan_data)
            result.created["vlans"] += 1
        except Exception as exc:
            result.errors.append(f"vlan vid={vlan_spec.vid}: {exc}")


def _find_interface(nb, device_obj, name: str):
    """Find existing interface by device and name."""
    interfaces = list(nb.dcim.interfaces.filter(device_id=device_obj.id, name=name))
    return interfaces[0] if interfaces else None


def _apply_fill_in_blank(existing_iface, iface_spec) -> int:
    """Fill empty interface fields from seed data. Returns number of fields updated."""
    updates: dict[str, object] = {}
    for field_name in ["description", "mac_address", "type", "mode"]:
        seeded_value = getattr(iface_spec, field_name, None)
        current_value = getattr(existing_iface, field_name, None)
        if seeded_value is None:
            continue
        if current_value is None or (
            isinstance(current_value, str) and current_value.strip() == ""
        ):
            updates[field_name] = seeded_value

    if updates:
        existing_iface.update(updates)

    return len(updates)


def _create_interface(nb, device_obj, iface_spec):
    """Create a new interface on a device from seed data."""
    payload = {
        "device": device_obj.id,
        "name": iface_spec.name,
        "type": iface_spec.type,
    }
    if iface_spec.description is not None:
        payload["description"] = iface_spec.description
    if iface_spec.mac_address is not None:
        payload["mac_address"] = iface_spec.mac_address
    if iface_spec.mode is not None:
        payload["mode"] = iface_spec.mode
    return nb.dcim.interfaces.create(**payload)


def _extract_site_id(device_obj) -> int | None:
    """Extract site id from a pynetbox device object that may shape site differently."""
    site = getattr(device_obj, "site", None)
    if site is None:
        return None
    if isinstance(site, int):
        return site
    if isinstance(site, dict):
        return site.get("id")
    return getattr(site, "id", None)


def _resolve_vlan_for_interface(nb, device_obj, vlan_vid: int):
    """Resolve VLAN by site-scoped lookup first, then global fallback."""
    site_id = _extract_site_id(device_obj)
    if site_id is not None:
        vlan_obj = nb.ipam.vlans.get(vid=vlan_vid, site_id=site_id)
        if vlan_obj:
            return vlan_obj
    return nb.ipam.vlans.get(vid=vlan_vid, site_id=None)


def _assign_vlans_to_interface(nb, iface_obj, iface_spec, device_obj) -> list[dict]:
    """Assign access/tagged VLANs and mode to an interface. Returns assignment errors."""
    errors: list[dict] = []
    if not iface_spec.mode:
        return errors

    try:
        if iface_spec.mode == "access":
            updates: dict[str, object] = {"mode": "access"}
            if iface_spec.access_vlan is not None:
                vlan_obj = _resolve_vlan_for_interface(nb, device_obj, iface_spec.access_vlan)
                if vlan_obj is None:
                    errors.append(
                        {
                            "entity": "interface",
                            "device": getattr(device_obj, "name", str(device_obj.id)),
                            "name": iface_spec.name,
                            "reason": f"Could not assign access VLAN {iface_spec.access_vlan}: VLAN not found",
                        }
                    )
                else:
                    updates["untagged_vlan"] = vlan_obj.id
            iface_obj.update(updates)

        elif iface_spec.mode == "tagged":
            updates = {"mode": "tagged"}
            vlan_ids: list[int] = []
            for vlan_vid in iface_spec.tagged_vlans or []:
                vlan_obj = _resolve_vlan_for_interface(nb, device_obj, vlan_vid)
                if vlan_obj is None:
                    errors.append(
                        {
                            "entity": "interface",
                            "device": getattr(device_obj, "name", str(device_obj.id)),
                            "name": iface_spec.name,
                            "reason": f"Could not assign tagged VLAN {vlan_vid}: VLAN not found",
                        }
                    )
                    continue
                vlan_ids.append(vlan_obj.id)
            if vlan_ids:
                updates["tagged_vlans"] = vlan_ids
            iface_obj.update(updates)

        elif iface_spec.mode == "tagged-all":
            iface_obj.update({"mode": "tagged-all"})
    except Exception as exc:
        errors.append(
            {
                "entity": "interface",
                "device": getattr(device_obj, "name", str(device_obj.id)),
                "name": iface_spec.name,
                "reason": str(exc),
            }
        )

    return errors


def _seed_interfaces(nb, device_obj, interfaces_list: list) -> tuple[int, int, int, list[dict]]:
    """Seed interfaces on a device. Returns (created, updated, skipped, errors)."""
    created = 0
    updated = 0
    skipped = 0
    errors: list[dict] = []

    for iface_spec in interfaces_list:
        try:
            iface_obj = _find_interface(nb, device_obj, iface_spec.name)
            if iface_obj:
                updated_fields = _apply_fill_in_blank(iface_obj, iface_spec)
                if updated_fields > 0:
                    updated += 1
                else:
                    skipped += 1
            else:
                iface_obj = _create_interface(nb, device_obj, iface_spec)
                created += 1

            errors.extend(_assign_vlans_to_interface(nb, iface_obj, iface_spec, device_obj))
        except Exception as exc:
            errors.append(
                {
                    "entity": "interface",
                    "device": getattr(device_obj, "name", str(device_obj.id)),
                    "name": iface_spec.name,
                    "reason": str(exc),
                }
            )

    return created, updated, skipped, errors
