"""Tests for cable ingestion helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from orbweaver.cables.ingest import ingest_cables_direct, ingest_cables_from_review
from orbweaver.cables.models import CableCandidate, ResolutionConfidence
from orbweaver.models.common import NormalizedCable


def _candidate(a_dev: str, a_if: str, b_dev: str, b_if: str) -> CableCandidate:
    return CableCandidate(
        cable=NormalizedCable(
            device_a_name=a_dev,
            interface_a_name=a_if,
            device_b_name=b_dev,
            interface_b_name=b_if,
        ),
        confidence=ResolutionConfidence.CONFIRMED,
        device_a_discovered=True,
        device_b_discovered=True,
    )


def _netbox_with_devices_and_interfaces() -> MagicMock:
    netbox = MagicMock()

    def devices_filter(*args, **kwargs):
        name = kwargs.get("name")
        return [SimpleNamespace(id=1 if name == "switch1" else 2, name=name)]

    def interfaces_filter(*args, **kwargs):
        device = kwargs.get("device__name")
        iface = kwargs.get("name")
        if device == "switch1":
            return [SimpleNamespace(id=101, name=iface)]
        return [SimpleNamespace(id=201, name=iface)]

    netbox.dcim.devices.filter.side_effect = devices_filter
    netbox.dcim.interfaces.filter.side_effect = interfaces_filter
    netbox.dcim.cables.all.return_value = []
    netbox.dcim.cables.create.return_value = SimpleNamespace(id=999)
    netbox.dcim.cables.get.return_value = SimpleNamespace(delete=lambda: True)
    return netbox


def test_ingest_creates_new_cable() -> None:
    netbox = _netbox_with_devices_and_interfaces()
    summary = ingest_cables_direct(
        [_candidate("switch1", "Gi0/1", "switch2", "Gi0/1")], netbox
    )

    assert summary.created == 1
    assert summary.skipped == 0
    netbox.dcim.cables.create.assert_called_once()


def test_ingest_skips_existing_cable() -> None:
    netbox = _netbox_with_devices_and_interfaces()
    existing = SimpleNamespace(
        termination_a_device=SimpleNamespace(name="switch1"),
        termination_a_interface=SimpleNamespace(name="Gi0/1"),
        termination_b_device=SimpleNamespace(name="switch2"),
        termination_b_interface=SimpleNamespace(name="Gi0/1"),
    )
    netbox.dcim.cables.all.return_value = [existing]

    summary = ingest_cables_direct(
        [_candidate("switch1", "Gi0/1", "switch2", "Gi0/1")], netbox
    )

    assert summary.created == 0
    assert summary.skipped == 1
    netbox.dcim.cables.create.assert_not_called()


def test_ingest_rollback_on_error() -> None:
    netbox = _netbox_with_devices_and_interfaces()

    created_1 = SimpleNamespace(id=901)
    created_2 = SimpleNamespace(id=902)
    netbox.dcim.cables.create.side_effect = [created_1, created_2, RuntimeError("boom")]

    deleted_ids: list[int] = []

    def get_cable(cable_id: int):
        return SimpleNamespace(delete=lambda: deleted_ids.append(cable_id) or True)

    netbox.dcim.cables.get.side_effect = get_cable

    candidates = [
        _candidate("switch1", "Gi0/1", "switch2", "Gi0/1"),
        _candidate("switch1", "Gi0/2", "switch2", "Gi0/2"),
        _candidate("switch1", "Gi0/3", "switch2", "Gi0/3"),
    ]
    summary = ingest_cables_direct(candidates, netbox)

    assert summary.created == 0
    assert "boom" in (summary.ingestion_error or "")
    assert deleted_ids == [901, 902]


def test_ingest_disabled_flag() -> None:
    netbox = _netbox_with_devices_and_interfaces()
    summary = ingest_cables_direct(
        [_candidate("switch1", "Gi0/1", "switch2", "Gi0/1")],
        netbox,
        write_enabled=False,
    )

    assert summary.ingestion_disabled is True
    assert summary.created == 0
    netbox.dcim.cables.create.assert_not_called()


def test_ingest_dry_run_mode() -> None:
    netbox = _netbox_with_devices_and_interfaces()
    summary = ingest_cables_direct(
        [_candidate("switch1", "Gi0/1", "switch2", "Gi0/1")], netbox, dry_run=True
    )

    assert summary.created == 0
    netbox.dcim.cables.create.assert_not_called()


def test_ingest_netbox_unavailable() -> None:
    summary = ingest_cables_direct(
        [_candidate("switch1", "Gi0/1", "switch2", "Gi0/1")], None
    )
    assert summary.created == 0
    assert summary.ingestion_error == "NetBox client not configured"


def test_ingest_from_review_delegates_to_direct() -> None:
    netbox = _netbox_with_devices_and_interfaces()
    summary = ingest_cables_from_review(
        [_candidate("switch1", "Gi0/1", "switch2", "Gi0/1")], netbox
    )
    assert summary.created == 1
