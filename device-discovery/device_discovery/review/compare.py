"""
Compare discovered review data with the current NetBox state.

Ported from netbox_discovery.ui.compare — adapted for orbweaver's
ReviewSession model (ReviewItem list instead of nested review_data dict).

Requires pynetbox.  NetBox connection details are passed via CompareConfig.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("device_discovery.review.compare")


@dataclass
class FieldDiff:
    """A single field that differs between discovered and NetBox values."""

    field_name: str
    discovered_value: str
    netbox_value: str


@dataclass
class ObjectDiff:
    """Differences for one discovered object vs. its NetBox counterpart."""

    object_type: str  # "device", "vlan", "prefix"
    unique_key: str
    display_name: str
    is_new: bool
    fields: list[FieldDiff] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class CompareConfig:
    """NetBox connection parameters for comparison."""

    netbox_url: str
    netbox_token: str
    verify_ssl: bool = True


# ── Helpers ──────────────────────────────────────────────────────────────────


def _str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _nested(obj: object, *keys: str) -> str:
    for key in keys:
        if obj is None:
            return ""
        if isinstance(obj, dict):
            obj = obj.get(key)
        else:
            obj = getattr(obj, key, None)
    return _str(obj)


# ── Main comparison function ─────────────────────────────────────────────────


def compare_review_with_netbox(
    devices: list[dict],
    cfg: CompareConfig,
    *,
    include_statuses: tuple[str, ...] = ("accepted", "pending"),
) -> list[ObjectDiff]:
    """Compare device review items against live NetBox.

    Args:
        devices: List of dicts, each with "status" and "data" keys
                 (i.e. [item.model_dump() for item in session.devices]).
        cfg: NetBox connection parameters.
        include_statuses: Which item statuses to include in comparison.

    Returns:
        List of ObjectDiff — one per discovered object (devices, vlans, prefixes).
    """
    try:
        import pynetbox

        nb = pynetbox.api(cfg.netbox_url, token=cfg.netbox_token)
        if not cfg.verify_ssl:
            import urllib3

            urllib3.disable_warnings()
            nb.http_session.verify = False
    except Exception as exc:
        return [
            ObjectDiff(
                object_type="connection",
                unique_key="netbox",
                display_name="NetBox connection",
                is_new=False,
                errors=[f"Cannot connect to NetBox: {exc}"],
            )
        ]

    diffs: list[ObjectDiff] = []

    for item in devices:
        status = item.get("status", "")
        if status not in include_statuses:
            continue
        data = item.get("data", {})

        _compare_device(nb, data, diffs)
        _compare_vlans(nb, data.get("vlans", []), data, diffs)
        _compare_prefixes(nb, data.get("prefixes", []), diffs)

    return diffs


# ── Device comparison ────────────────────────────────────────────────────────


def _compare_device(nb: object, data: dict, diffs: list[ObjectDiff]) -> None:
    name = data.get("name", "")
    serial = data.get("serial_number", "") or data.get("serial", "")
    unique_key = serial or name
    if not unique_key:
        return

    try:
        nb_device = None
        if serial:
            results = list(nb.dcim.devices.filter(serial=serial))
            if results:
                nb_device = results[0]
        if nb_device is None and name:
            results = list(nb.dcim.devices.filter(name=name))
            if results:
                nb_device = results[0]

        if nb_device is None:
            diffs.append(
                ObjectDiff(
                    object_type="device",
                    unique_key=unique_key,
                    display_name=name or serial,
                    is_new=True,
                )
            )
            return

        field_diffs: list[FieldDiff] = []

        # site
        disc_site = _nested(data, "site", "name")
        nb_site = _nested(nb_device, "site", "name")
        if disc_site and disc_site != nb_site:
            field_diffs.append(FieldDiff("site", disc_site, nb_site))

        # device_type (model)
        disc_model = _nested(data, "device_type", "model")
        nb_model = _nested(nb_device, "device_type", "model")
        if disc_model and disc_model != nb_model:
            field_diffs.append(FieldDiff("device_type", disc_model, nb_model))

        # role
        disc_role = _nested(data, "role", "name")
        nb_role = _nested(nb_device, "role", "name")
        if disc_role and disc_role != nb_role:
            field_diffs.append(FieldDiff("role", disc_role, nb_role))

        # platform
        disc_platform = _nested(data, "platform", "name")
        nb_platform = _nested(nb_device, "platform", "name")
        if disc_platform and disc_platform != nb_platform:
            field_diffs.append(FieldDiff("platform", disc_platform, nb_platform))

        # status
        disc_status = _str(data.get("status", ""))
        nb_status = _nested(nb_device, "status", "value") or _str(
            getattr(nb_device, "status", "")
        )
        if disc_status and disc_status != nb_status:
            field_diffs.append(FieldDiff("status", disc_status, nb_status))

        # serial
        disc_serial = _str(serial)
        nb_serial = _str(getattr(nb_device, "serial", ""))
        if disc_serial and disc_serial != nb_serial:
            field_diffs.append(FieldDiff("serial", disc_serial, nb_serial))

        # comments
        disc_comments = _str(data.get("comments", ""))
        nb_comments = _str(getattr(nb_device, "comments", ""))
        if disc_comments and disc_comments != nb_comments:
            field_diffs.append(FieldDiff("comments", disc_comments, nb_comments))

        diffs.append(
            ObjectDiff(
                object_type="device",
                unique_key=unique_key,
                display_name=name or serial,
                is_new=False,
                fields=field_diffs,
            )
        )

    except Exception as exc:
        logger.warning("Error comparing device %s: %s", unique_key, exc)
        diffs.append(
            ObjectDiff(
                object_type="device",
                unique_key=unique_key,
                display_name=name or serial,
                is_new=False,
                errors=[str(exc)],
            )
        )


# ── VLAN comparison ──────────────────────────────────────────────────────────


def _compare_vlans(
    nb: object, vlans: list[dict], device_data: dict, diffs: list[ObjectDiff]
) -> None:
    site_name = _nested(device_data, "site", "name")

    for vlan in vlans:
        vid = vlan.get("vid")
        if vid is None:
            continue
        unique_key = f"vlan-{vid}-{site_name}"
        display_name = f"VLAN {vid} ({site_name or 'global'})"

        try:
            nb_vlan = None
            if site_name:
                try:
                    results = list(nb.ipam.vlans.filter(vid=vid, site=site_name))
                    nb_vlan = results[0] if results else None
                except Exception:
                    results = list(nb.ipam.vlans.filter(vid=vid))
                    nb_vlan = results[0] if results else None
            else:
                results = list(nb.ipam.vlans.filter(vid=vid))
                nb_vlan = results[0] if results else None

            if nb_vlan is None:
                diffs.append(
                    ObjectDiff(
                        object_type="vlan",
                        unique_key=unique_key,
                        display_name=display_name,
                        is_new=True,
                    )
                )
                continue

            field_diffs: list[FieldDiff] = []

            disc_name = _str(vlan.get("name", ""))
            nb_name = _str(getattr(nb_vlan, "name", ""))
            if disc_name != nb_name:
                field_diffs.append(FieldDiff("name", disc_name, nb_name))

            disc_desc = _str(vlan.get("description", ""))
            nb_desc = _str(getattr(nb_vlan, "description", ""))
            if disc_desc and disc_desc != nb_desc:
                field_diffs.append(FieldDiff("description", disc_desc, nb_desc))

            diffs.append(
                ObjectDiff(
                    object_type="vlan",
                    unique_key=unique_key,
                    display_name=display_name,
                    is_new=False,
                    fields=field_diffs,
                )
            )

        except Exception as exc:
            logger.warning("Error comparing VLAN %s: %s", unique_key, exc)
            diffs.append(
                ObjectDiff(
                    object_type="vlan",
                    unique_key=unique_key,
                    display_name=display_name,
                    is_new=False,
                    errors=[str(exc)],
                )
            )


# ── Prefix comparison ────────────────────────────────────────────────────────


def _compare_prefixes(nb: object, prefixes: list[dict], diffs: list[ObjectDiff]) -> None:
    for pfx in prefixes:
        prefix = pfx.get("prefix", "")
        if not prefix:
            continue
        unique_key = prefix
        display_name = prefix

        try:
            nb_prefix = None
            results = list(nb.ipam.prefixes.filter(prefix=prefix))
            if results:
                nb_prefix = results[0]

            if nb_prefix is None:
                diffs.append(
                    ObjectDiff(
                        object_type="prefix",
                        unique_key=unique_key,
                        display_name=display_name,
                        is_new=True,
                    )
                )
                continue

            field_diffs: list[FieldDiff] = []

            disc_desc = _str(pfx.get("description", ""))
            nb_desc = _str(getattr(nb_prefix, "description", ""))
            if disc_desc and disc_desc != nb_desc:
                field_diffs.append(FieldDiff("description", disc_desc, nb_desc))

            diffs.append(
                ObjectDiff(
                    object_type="prefix",
                    unique_key=unique_key,
                    display_name=display_name,
                    is_new=False,
                    fields=field_diffs,
                )
            )

        except Exception as exc:
            logger.warning("Error comparing prefix %s: %s", unique_key, exc)
            diffs.append(
                ObjectDiff(
                    object_type="prefix",
                    unique_key=unique_key,
                    display_name=display_name,
                    is_new=False,
                    errors=[str(exc)],
                )
            )
