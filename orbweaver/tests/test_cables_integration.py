"""Integration tests for cable discovery workflows."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from orbweaver.cables.ingest import ingest_cables_direct
from orbweaver.cables.resolve import resolve_cables
from orbweaver.models.common import (
    DeviceStatus,
    DiscoveryResult,
    NormalizedDevice,
    NormalizedDeviceRole,
    NormalizedDeviceType,
    NormalizedInterface,
    NormalizedLLDPNeighbor,
    NormalizedManufacturer,
    NormalizedSite,
)


@dataclass
class _CableRecord:
    id: int
    a_device: str
    a_interface: str
    b_device: str
    b_interface: str

    @property
    def termination_a_device(self):
        return SimpleNamespace(name=self.a_device)

    @property
    def termination_a_interface(self):
        return SimpleNamespace(name=self.a_interface)

    @property
    def termination_b_device(self):
        return SimpleNamespace(name=self.b_device)

    @property
    def termination_b_interface(self):
        return SimpleNamespace(name=self.b_interface)


class _NetBoxFake:
    class _Devices:
        def __init__(self, parent: _NetBoxFake):
            self._parent = parent

        def filter(self, **kwargs):
            name = kwargs.get("name")
            if not name:
                return []
            key = name.lower()
            if key not in self._parent.device_ids:
                return []
            return [SimpleNamespace(id=self._parent.device_ids[key], name=key)]

    class _Interfaces:
        def __init__(self, parent: _NetBoxFake):
            self._parent = parent

        def filter(self, **kwargs):
            if "device__name" in kwargs and "name" in kwargs:
                device = kwargs["device__name"].lower()
                iface = kwargs["name"]
                iid = self._parent.interface_ids.get((device, iface))
                return [SimpleNamespace(id=iid, name=iface)] if iid else []

            if "mac_address" in kwargs:
                return []

            return []

    class _CableItem:
        def __init__(self, parent: _NetBoxFake, cable_id: int):
            self._parent = parent
            self._id = cable_id

        def delete(self):
            self._parent.cables = [c for c in self._parent.cables if c.id != self._id]
            return True

    class _Cables:
        def __init__(self, parent: _NetBoxFake):
            self._parent = parent
            self.fail_on_create_at: int | None = None
            self._create_calls = 0

        def all(self):
            return list(self._parent.cables)

        def create(self, **kwargs):
            self._create_calls += 1
            if self.fail_on_create_at == self._create_calls:
                raise RuntimeError("simulated netbox failure")

            a_id = kwargs["termination_a_id"]
            b_id = kwargs["termination_b_id"]
            a = self._parent.interface_lookup[a_id]
            b = self._parent.interface_lookup[b_id]
            cable = _CableRecord(
                id=self._parent.next_cable_id,
                a_device=a[0],
                a_interface=a[1],
                b_device=b[0],
                b_interface=b[1],
            )
            self._parent.next_cable_id += 1
            self._parent.cables.append(cable)
            return SimpleNamespace(id=cable.id)

        def get(self, cable_id: int):
            for cable in self._parent.cables:
                if cable.id == cable_id:
                    return _NetBoxFake._CableItem(self._parent, cable_id)
            return None

        def delete(self, cable_id: int):
            before = len(self._parent.cables)
            self._parent.cables = [c for c in self._parent.cables if c.id != cable_id]
            return len(self._parent.cables) != before

    def __init__(self):
        self.device_ids = {"switch1": 1, "switch2": 2}
        self.interface_ids = {
            ("switch1", "GigabitEthernet0/1"): 101,
            ("switch2", "GigabitEthernet0/1"): 201,
        }
        self.interface_lookup = {
            101: ("switch1", "GigabitEthernet0/1"),
            201: ("switch2", "GigabitEthernet0/1"),
        }
        self.next_cable_id = 1000
        self.cables: list[_CableRecord] = []

        self.dcim = SimpleNamespace(
            devices=_NetBoxFake._Devices(self),
            interfaces=_NetBoxFake._Interfaces(self),
            cables=_NetBoxFake._Cables(self),
        )


def _neighbor(
    local: str, remote_device: str, remote_intf: str, mac: str
) -> NormalizedLLDPNeighbor:
    return NormalizedLLDPNeighbor(
        local_interface=local,
        neighbor_device_name=remote_device,
        neighbor_interface=remote_intf,
        neighbor_chassis_mac=mac,
    )


def _device(name: str, neighbors: list[NormalizedLLDPNeighbor]) -> NormalizedDevice:
    manufacturer = NormalizedManufacturer(name="Cisco", slug="cisco")
    dev = NormalizedDevice(
        name=name,
        device_type=NormalizedDeviceType(
            manufacturer=manufacturer, model="C9300", slug="c9300"
        ),
        role=NormalizedDeviceRole(name="Switch", slug="switch"),
        site=NormalizedSite(name="Lab", slug="lab"),
        status=DeviceStatus.ACTIVE,
        interfaces=[NormalizedInterface(name="GigabitEthernet0/1")],
        lldp_neighbors=neighbors,
    )
    return dev


def _build_two_switch_discovery() -> DiscoveryResult:
    dev1 = _device(
        "switch1", [_neighbor("Gi0/1", "switch2", "Gi0/1", "aa:bb:cc:dd:ee:01")]
    )
    dev2 = _device(
        "switch2", [_neighbor("Gi0/1", "switch1", "Gi0/1", "aa:bb:cc:dd:ee:02")]
    )
    return DiscoveryResult(devices=[dev1, dev2])


def _rules() -> dict:
    return {"vendor": "cisco", "mappings": {"cisco": {"Gi": "GigabitEthernet"}}}


def test_discovery_run_creates_cables() -> None:
    nb = _NetBoxFake()
    result = _build_two_switch_discovery()
    candidates, _ = resolve_cables(result, nb, _rules())

    summary = ingest_cables_direct(candidates, nb)

    assert summary.created == 1
    assert len(nb.cables) == 1


def test_repeated_discovery_run_idempotent() -> None:
    nb = _NetBoxFake()
    result = _build_two_switch_discovery()

    for _ in range(3):
        candidates, _ = resolve_cables(result, nb, _rules())
        ingest_cables_direct(candidates, nb)

    assert len(nb.cables) == 1


def test_discovery_run_after_manual_deletion() -> None:
    nb = _NetBoxFake()
    result = _build_two_switch_discovery()

    candidates, _ = resolve_cables(result, nb, _rules())
    first = ingest_cables_direct(candidates, nb)
    assert first.created == 1

    cable_id = nb.cables[0].id
    nb.dcim.cables.delete(cable_id)
    assert len(nb.cables) == 0

    candidates_again, _ = resolve_cables(result, nb, _rules())
    second = ingest_cables_direct(candidates_again, nb)
    assert second.created == 1
    assert len(nb.cables) == 1


def test_discovery_run_with_cables_disabled() -> None:
    nb = _NetBoxFake()
    result = _build_two_switch_discovery()
    candidates, _ = resolve_cables(result, nb, _rules())

    summary = ingest_cables_direct(candidates, nb, write_enabled=False)
    assert summary.ingestion_disabled is True
    assert len(nb.cables) == 0


def test_netbox_api_error_atomic_rollback() -> None:
    nb = _NetBoxFake()
    # Add a second unique cable candidate path so we can create >1 before failure.
    nb.interface_ids[("switch1", "GigabitEthernet0/2")] = 102
    nb.interface_ids[("switch2", "GigabitEthernet0/2")] = 202
    nb.interface_lookup[102] = ("switch1", "GigabitEthernet0/2")
    nb.interface_lookup[202] = ("switch2", "GigabitEthernet0/2")

    manufacturer = NormalizedManufacturer(name="Cisco", slug="cisco")
    dev1 = NormalizedDevice(
        name="switch1",
        device_type=NormalizedDeviceType(
            manufacturer=manufacturer, model="C9300", slug="c9300"
        ),
        role=NormalizedDeviceRole(name="Switch", slug="switch"),
        site=NormalizedSite(name="Lab", slug="lab"),
        status=DeviceStatus.ACTIVE,
        interfaces=[
            NormalizedInterface(name="GigabitEthernet0/1"),
            NormalizedInterface(name="GigabitEthernet0/2"),
        ],
        lldp_neighbors=[
            _neighbor("Gi0/1", "switch2", "Gi0/1", "aa:bb:cc:dd:ee:01"),
            _neighbor("Gi0/2", "switch2", "Gi0/2", "aa:bb:cc:dd:ee:01"),
        ],
    )
    dev2 = NormalizedDevice(
        name="switch2",
        device_type=NormalizedDeviceType(
            manufacturer=manufacturer, model="C9300", slug="c9300"
        ),
        role=NormalizedDeviceRole(name="Switch", slug="switch"),
        site=NormalizedSite(name="Lab", slug="lab"),
        status=DeviceStatus.ACTIVE,
        interfaces=[
            NormalizedInterface(name="GigabitEthernet0/1"),
            NormalizedInterface(name="GigabitEthernet0/2"),
        ],
        lldp_neighbors=[
            _neighbor("Gi0/1", "switch1", "Gi0/1", "aa:bb:cc:dd:ee:02"),
            _neighbor("Gi0/2", "switch1", "Gi0/2", "aa:bb:cc:dd:ee:02"),
        ],
    )

    candidates, _ = resolve_cables(DiscoveryResult(devices=[dev1, dev2]), nb, _rules())
    # Fail on second create: first is written then rollback should delete it.
    nb.dcim.cables.fail_on_create_at = 2
    summary = ingest_cables_direct(candidates, nb)

    assert summary.created == 0
    assert summary.ingestion_error is not None
    assert len(nb.cables) == 0
