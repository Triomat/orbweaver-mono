"""NetBox cable ingestion helpers."""

from __future__ import annotations

from typing import Any

from orbweaver.cables.models import (
    CableCandidate,
    CableResolutionSummary,
    CableSkipEntry,
)
from orbweaver.cables.resolve import cable_exists_in_netbox


def get_device_id(netbox_client: Any, device_name: str) -> int:
    """
    Resolve a NetBox device ID by device name.

    Args:
            netbox_client: Pynetbox client instance.
            device_name: NetBox device name.

    Returns:
            Device numeric ID.

    Raises:
            ValueError: If no matching device exists.

    """
    devices = list(netbox_client.dcim.devices.filter(name=device_name))
    if not devices:
        raise ValueError(f"Device not found in NetBox: {device_name}")
    return int(devices[0].id)


def get_interface_id(netbox_client: Any, device_name: str, interface_name: str) -> int:
    """
    Resolve a NetBox interface ID by device and interface names.

    Args:
            netbox_client: Pynetbox client instance.
            device_name: NetBox device name.
            interface_name: Interface name on the target device.

    Returns:
            Interface numeric ID.

    Raises:
            ValueError: If no matching interface exists.

    """
    interfaces = list(
        netbox_client.dcim.interfaces.filter(
            device__name=device_name, name=interface_name
        )
    )
    if not interfaces:
        raise ValueError(
            f"Interface not found in NetBox: {device_name}:{interface_name}"
        )
    return int(interfaces[0].id)


def create_cable_in_netbox(
    netbox_client: Any,
    device_a_id: int,
    intf_a_id: int,
    device_b_id: int,
    intf_b_id: int,
) -> Any:
    """
    Create a cable in NetBox using two interface terminations.

    Args:
            netbox_client: Pynetbox client instance.
            device_a_id: Device A ID (kept for call-site symmetry).
            intf_a_id: Interface A ID.
            device_b_id: Device B ID (kept for call-site symmetry).
            intf_b_id: Interface B ID.

    Returns:
            The created cable object returned by pynetbox.

    Raises:
            Any exception raised by the NetBox API client.

    """
    _ = device_a_id
    _ = device_b_id
    payload = {
        "termination_a_type": "dcim.interface",
        "termination_a_id": intf_a_id,
        "termination_b_type": "dcim.interface",
        "termination_b_id": intf_b_id,
        "label": "LLDP auto-discovered",
        "status": "connected",
    }
    return netbox_client.dcim.cables.create(**payload)


def delete_cable_in_netbox(netbox_client: Any, cable_id: int) -> bool:
    """
    Delete a cable in NetBox.

    Args:
            netbox_client: Pynetbox client instance.
            cable_id: NetBox cable ID.

    Returns:
            True if deletion succeeded, otherwise False.

    Raises:
            This function intentionally suppresses API errors.

    """
    try:
        cable = netbox_client.dcim.cables.get(cable_id)
        if cable is None:
            return False
        cable.delete()
        return True
    except Exception:
        try:
            return bool(netbox_client.dcim.cables.delete(cable_id))
        except Exception:
            return False


def ingest_cables_direct(
    candidates: list[CableCandidate],
    netbox_client: Any,
    write_enabled: bool = True,
    dry_run: bool = False,
) -> CableResolutionSummary:
    """
    Create LLDP-derived cables in NetBox with rollback-on-error semantics.

    Args:
            candidates: Candidate cables produced by cable resolution.
            netbox_client: Pynetbox client instance, or None.
            write_enabled: Feature flag to allow or block writes.
            dry_run: If True, calculate outcomes without writing to NetBox.

    Returns:
            A cable resolution summary with created/skipped/error counters.

    Raises:
            This function captures NetBox write exceptions and stores them in
            ``summary.ingestion_error`` instead of re-raising.

    Example:
            >>> ingest_cables_direct(candidates, netbox_client, write_enabled=True)

    """
    summary = CableResolutionSummary(candidates=len(candidates))
    if not write_enabled:
        summary.ingestion_disabled = True
        return summary

    if netbox_client is None:
        summary.ingestion_error = "NetBox client not configured"
        return summary

    writable = [candidate for candidate in candidates if candidate.is_writable]
    queued: list[CableCandidate] = []

    for candidate in writable:
        if cable_exists_in_netbox(netbox_client, candidate.cable):
            summary.skipped += 1
            summary.skip_entries.append(
                CableSkipEntry(
                    local_device=candidate.cable.device_a_name,
                    local_interface=candidate.cable.interface_a_name,
                    neighbor_hostname=candidate.cable.device_b_name,
                    neighbor_interface=candidate.cable.interface_b_name,
                    reason="already_exists",
                )
            )
            continue
        queued.append(candidate)

    if dry_run:
        return summary

    created_ids: list[int] = []
    try:
        for candidate in queued:
            dev_a_id = get_device_id(netbox_client, candidate.cable.device_a_name)
            dev_b_id = get_device_id(netbox_client, candidate.cable.device_b_name)
            intf_a_id = get_interface_id(
                netbox_client,
                candidate.cable.device_a_name,
                candidate.cable.interface_a_name,
            )
            intf_b_id = get_interface_id(
                netbox_client,
                candidate.cable.device_b_name,
                candidate.cable.interface_b_name,
            )

            created = create_cable_in_netbox(
                netbox_client, dev_a_id, intf_a_id, dev_b_id, intf_b_id
            )
            created_ids.append(int(getattr(created, "id")))
            summary.created += 1

    except Exception as exc:
        for created_id in created_ids:
            delete_cable_in_netbox(netbox_client, created_id)
        summary.created = 0
        summary.ingestion_error = str(exc)

    return summary


def ingest_cables_from_review(
    approved_candidates: list[CableCandidate],
    netbox_client: Any,
    write_enabled: bool = True,
) -> CableResolutionSummary:
    """
    Ingest only review-approved cable candidates.

    Args:
            approved_candidates: Accepted cable candidates from a review session.
            netbox_client: Pynetbox client instance, or None.
            write_enabled: Feature flag to allow or block writes.

    Returns:
            A cable resolution summary produced by direct ingestion.

    Raises:
            No direct exceptions are raised by this wrapper.

    """
    return ingest_cables_direct(
        candidates=approved_candidates,
        netbox_client=netbox_client,
        write_enabled=write_enabled,
        dry_run=False,
    )


__all__ = [
    "create_cable_in_netbox",
    "delete_cable_in_netbox",
    "get_device_id",
    "get_interface_id",
    "ingest_cables_direct",
    "ingest_cables_from_review",
]
