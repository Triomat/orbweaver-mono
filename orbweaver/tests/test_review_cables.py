"""Tests for review workflow cable integration."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

from orbweaver.cables.ingest import ingest_cables_from_review
from orbweaver.cables.models import CableCandidate, ResolutionConfidence
from orbweaver.cables.resolve import resolve_cables
from orbweaver.models.common import (
	DeviceStatus,
	DiscoveryResult,
	NormalizedCable,
	NormalizedDevice,
	NormalizedDeviceRole,
	NormalizedDeviceType,
	NormalizedInterface,
	NormalizedLLDPNeighbor,
	NormalizedManufacturer,
	NormalizedSite,
)
from orbweaver.review.models import ItemStatus, ReviewItem
from orbweaver.review.rebuild import cable_candidate_to_dict, dict_to_cable_candidate
from orbweaver.review.store import ReviewStore


def _device(name: str, neighbors: list[NormalizedLLDPNeighbor]) -> NormalizedDevice:
	manufacturer = NormalizedManufacturer(name="Cisco", slug="cisco")
	return NormalizedDevice(
		name=name,
		device_type=NormalizedDeviceType(manufacturer=manufacturer, model="C9300", slug="c9300"),
		role=NormalizedDeviceRole(name="Switch", slug="switch"),
		site=NormalizedSite(name="Lab", slug="lab"),
		status=DeviceStatus.ACTIVE,
		interfaces=[NormalizedInterface(name="GigabitEthernet0/1")],
		lldp_neighbors=neighbors,
	)


def _neighbor(local: str, remote_device: str, remote_intf: str, mac: str) -> NormalizedLLDPNeighbor:
	return NormalizedLLDPNeighbor(
		local_interface=local,
		neighbor_device_name=remote_device,
		neighbor_interface=remote_intf,
		neighbor_chassis_mac=mac,
	)


def _candidate() -> CableCandidate:
	return CableCandidate(
		cable=NormalizedCable(
			device_a_name="switch1",
			interface_a_name="GigabitEthernet0/1",
			device_b_name="switch2",
			interface_b_name="GigabitEthernet0/1",
		),
		confidence=ResolutionConfidence.CONFIRMED,
		device_a_discovered=True,
		device_b_discovered=True,
	)


class _FakeNetBox:
	def __init__(self):
		from types import SimpleNamespace

		self.created = []
		self.dcim = SimpleNamespace()
		self.dcim.devices = SimpleNamespace(
			filter=lambda **kwargs: [SimpleNamespace(id=1 if kwargs.get("name") == "switch1" else 2)]
		)
		self.dcim.interfaces = SimpleNamespace(
			filter=lambda **kwargs: [SimpleNamespace(id=11 if kwargs.get("device__name") == "switch1" else 22)]
		)
		self.dcim.cables = SimpleNamespace(
			all=lambda: [],
			create=lambda **kwargs: SimpleNamespace(id=999),
			get=lambda _id: SimpleNamespace(delete=lambda: True),
			delete=lambda _id: True,
		)


def test_review_session_includes_cable_candidates(tmp_path) -> None:
	store = ReviewStore(tmp_path)
	session = store.create("test-policy")

	dev1 = _device("switch1", [_neighbor("Gi0/1", "switch2", "Gi0/1", "aa:bb:cc:dd:ee:01")])
	dev2 = _device("switch2", [_neighbor("Gi0/1", "switch1", "Gi0/1", "aa:bb:cc:dd:ee:02")])
	candidates, summary = resolve_cables(
		DiscoveryResult(devices=[dev1, dev2]),
		netbox_client=None,
		normalization_rules={"vendor": "cisco", "mappings": {"cisco": {"Gi": "GigabitEthernet"}}},
	)

	session.cables = [
		ReviewItem(index=idx, status=ItemStatus.PENDING, data=dataclasses.asdict(candidate))
		for idx, candidate in enumerate(candidates)
	]
	session.cable_summary = dataclasses.asdict(summary)
	store.save(session)

	assert len(session.cables) == 1
	assert session.cable_summary is not None


def test_review_session_serialization(tmp_path) -> None:
	store = ReviewStore(tmp_path)
	session = store.create("test-policy")

	candidate = _candidate()
	session.cables.append(ReviewItem(index=0, status=ItemStatus.PENDING, data=cable_candidate_to_dict(candidate)))
	session.cable_summary = {"created": 0, "skipped": 0}
	store.save(session)

	loaded = store.get(session.id)
	assert loaded is not None
	rebuilt = dict_to_cable_candidate(loaded.cables[0].data)
	assert rebuilt.cable.device_a_name == "switch1"
	assert loaded.cable_summary == {"created": 0, "skipped": 0}


def test_cable_candidate_approval(tmp_path) -> None:
	store = ReviewStore(tmp_path)
	session = store.create("test-policy")

	candidate = _candidate()
	session.cables.append(ReviewItem(index=0, status=ItemStatus.ACCEPTED, data=dataclasses.asdict(candidate)))

	approved = [dict_to_cable_candidate(item.data) for item in session.cables if item.status == ItemStatus.ACCEPTED]
	summary = ingest_cables_from_review(approved, _FakeNetBox(), write_enabled=True)

	assert summary.created == 1


def test_cable_candidate_rejection(tmp_path) -> None:
	store = ReviewStore(tmp_path)
	session = store.create("test-policy")

	candidate = _candidate()
	session.cables.append(ReviewItem(index=0, status=ItemStatus.REJECTED, data=dataclasses.asdict(candidate)))

	approved = [dict_to_cable_candidate(item.data) for item in session.cables if item.status == ItemStatus.ACCEPTED]
	summary = ingest_cables_from_review(approved, _FakeNetBox(), write_enabled=True)

	assert summary.created == 0


def test_cable_summary_in_review_session(tmp_path) -> None:
	store = ReviewStore(tmp_path)
	session = store.create("test-policy")
	session.cable_summary = {"discovered": 2, "candidates": 1, "created": 0, "unresolvable": 1}
	store.save(session)

	loaded = store.get(session.id)
	assert loaded is not None
	assert loaded.cable_summary is not None
	assert loaded.cable_summary["discovered"] == 2