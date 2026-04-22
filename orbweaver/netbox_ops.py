"""Post-Diode NetBox operations via pynetbox.

Used for things Diode cannot do reliably — specifically rack assignment.
Diode's reconciler matches racks by location+name (not site+name), so it
always creates new rack stubs instead of finding the existing rack. The
NetBox REST API (via pynetbox) has no such limitation.

See docs/upstream-issues.md for root cause and the upstream fix that would
make this module unnecessary.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_HOST_VAR = "NETBOX_HOST"
_PORT_VAR = "NETBOX_PORT"
_TOKEN_VAR = "NETBOX_TOKEN"


def _pynetbox_client():
    """Return a pynetbox.api instance built from env vars, or None if unconfigured."""
    import pynetbox

    host = os.environ.get(_HOST_VAR, "").strip()
    port = os.environ.get(_PORT_VAR, "8000").strip()
    token = os.environ.get(_TOKEN_VAR, "").strip()

    if not host or not token:
        return None

    return pynetbox.api(f"http://{host}:{port}", token=token)


def assign_device_rack(device_name: str, site_name: str, rack_name: str) -> bool:
    """
    Set the rack on a NetBox device using the NetBox REST API.

    Looks up device and rack by name+site (no location needed). Logs a
    warning and returns False if either is not found or the update fails.
    """
    nb = _pynetbox_client()
    if nb is None:
        logger.warning(
            "Rack assignment skipped for '%s': %s and %s must be set.",
            device_name, _HOST_VAR, _TOKEN_VAR,
        )
        return False

    try:
        racks = list(nb.dcim.racks.filter(name=rack_name))
        rack = next(
            (r for r in racks if r.site and r.site.name == site_name),
            racks[0] if racks else None,
        )
        if rack is None:
            logger.warning("Rack '%s' (site '%s') not found in NetBox", rack_name, site_name)
            return False

        devices = list(nb.dcim.devices.filter(name=device_name))
        device = next(
            (d for d in devices if d.site and d.site.name == site_name),
            None,
        )
        if device is None:
            logger.warning("Device '%s' (site '%s') not found in NetBox for rack assignment", device_name, site_name)
            return False

        device.rack = rack.id
        device.save()
        logger.info("Assigned device '%s' to rack '%s'", device_name, rack_name)
        return True

    except Exception as exc:
        logger.error("Rack assignment failed for '%s': %s", device_name, exc)
        return False
