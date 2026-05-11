"""Tests for cable resolution helpers and algorithm."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from orbweaver.cables.resolve import (
    build_discovered_device_indexes,
    cable_exists_in_netbox,
    dedupe_key,
    determine_lldp_direction,
    is_ambiguous_mac,
    is_bidirectional_match,
    is_self_loop,
    lookup_device_in_netbox,
    match_interface_on_device,
    resolve_cables,
)
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


def _device(
    name: str, neighbors: list[NormalizedLLDPNeighbor] | None = None
) -> NormalizedDevice:
    manufacturer = NormalizedManufacturer(name="Cisco", slug="cisco")
    device = NormalizedDevice(
        name=name,
        device_type=NormalizedDeviceType(
            manufacturer=manufacturer, model="C9300", slug="c9300"
        ),
        role=NormalizedDeviceRole(name="Switch", slug="switch"),
        site=NormalizedSite(name="Lab", slug="lab"),
        status=DeviceStatus.ACTIVE,
        lldp_neighbors=neighbors or [],
    )
    return device


def _neighbor(
    local: str, remote_device: str, remote_intf: str, chassis_mac: str
) -> NormalizedLLDPNeighbor:
    return NormalizedLLDPNeighbor(
        local_interface=local,
        neighbor_device_name=remote_device,
        neighbor_interface=remote_intf,
        neighbor_chassis_mac=chassis_mac,
    )


def test_dedupe_key_bidirectional_symmetry() -> None:
    a_to_b = dedupe_key("switch1", "Gi0/1", "switch2", "Gi0/2")
    b_to_a = dedupe_key("switch2", "Gi0/2", "switch1", "Gi0/1")
    assert a_to_b == b_to_a


def test_self_loop_detection() -> None:
    assert is_self_loop("Switch1.Example.com", "switch1")


def test_bidirectional_match_detection() -> None:
    a = _device(
        "switch1",
        [
            NormalizedLLDPNeighbor(
                local_interface="Gi0/1",
                neighbor_device_name="switch2",
                neighbor_interface="Gi0/1",
                neighbor_chassis_mac="aabbccddeeff",
            )
        ],
    )
    b = _device(
        "switch2",
        [
            NormalizedLLDPNeighbor(
                local_interface="Gi0/1",
                neighbor_device_name="switch1",
                neighbor_interface="Gi0/1",
                neighbor_chassis_mac="ffeeddccbbaa",
            )
        ],
    )
    result = DiscoveryResult(devices=[a, b])

    assert is_bidirectional_match("switch1", "switch2", result)
    assert determine_lldp_direction("switch1", "switch2", result) == "bidirectional"


def test_build_discovered_device_indexes_by_hostname_and_mac() -> None:
    dev = _device("switch1")
    dev.custom_fields["chassis_mac"] = "aa:bb:cc:dd:ee:ff"
    by_name, by_mac = build_discovered_device_indexes(DiscoveryResult(devices=[dev]))

    assert by_name["switch1"] is dev
    assert by_mac["aabbccddeeff"][0] is dev


def test_ambiguous_mac_detection() -> None:
    d1 = _device("switch1")
    d2 = _device("switch2")
    d1.custom_fields["chassis_mac"] = "aa:bb:cc:dd:ee:ff"
    d2.custom_fields["chassis_mac"] = "aa-bb-cc-dd-ee-ff"

    assert is_ambiguous_mac("switch1", DiscoveryResult(devices=[d1, d2]))


def test_match_interface_on_device_with_normalization() -> None:
    dev = _device("switch2")
    dev.interfaces = [NormalizedInterface(name="GigabitEthernet0/1")]

    rules = {
        "vendor": "cisco",
        "mappings": {
            "cisco": {
                "Gi": "GigabitEthernet",
            }
        },
    }

    assert match_interface_on_device(dev, "Gi0/1", rules) == "GigabitEthernet0/1"


def test_lookup_device_in_netbox_prefers_hostname_then_mac() -> None:
    netbox = MagicMock()
    netbox.dcim.devices.filter.return_value = [SimpleNamespace(name="switch2")]

    found = lookup_device_in_netbox(netbox, "switch2.example.com", "aa:bb:cc:dd:ee:ff")
    assert found.name == "switch2"


def test_lookup_device_in_netbox_uses_mac_fallback() -> None:
    netbox = MagicMock()
    netbox.dcim.devices.filter.return_value = []
    netbox.dcim.interfaces.filter.return_value = [
        SimpleNamespace(device=SimpleNamespace(name="switch3"))
    ]

    found = lookup_device_in_netbox(netbox, "missing", "aa:bb:cc:dd:ee:ff")
    assert found.name == "switch3"


def test_cable_exists_in_netbox_by_endpoint_pairs() -> None:
    cable = NormalizedCable(
        device_a_name="switch1",
        interface_a_name="GigabitEthernet0/1",
        device_b_name="switch2",
        interface_b_name="GigabitEthernet0/1",
    )

    netbox = MagicMock()
    existing = SimpleNamespace(
        termination_a_device=SimpleNamespace(name="switch2"),
        termination_a_interface=SimpleNamespace(name="GigabitEthernet0/1"),
        termination_b_device=SimpleNamespace(name="switch1"),
        termination_b_interface=SimpleNamespace(name="GigabitEthernet0/1"),
    )
    netbox.dcim.cables.all.return_value = [existing]

    assert cable_exists_in_netbox(netbox, cable)


def test_resolve_two_connected_switches() -> None:
    a = _device(
        "switch1", [_neighbor("Gi0/1", "switch2", "Gi0/1", "aa:bb:cc:dd:ee:01")]
    )
    b = _device(
        "switch2", [_neighbor("Gi0/1", "switch1", "Gi0/1", "aa:bb:cc:dd:ee:02")]
    )
    a.interfaces = [NormalizedInterface(name="GigabitEthernet0/1")]
    b.interfaces = [NormalizedInterface(name="GigabitEthernet0/1")]

    candidates, summary = resolve_cables(
        DiscoveryResult(devices=[a, b]),
        netbox_client=None,
        normalization_rules={
            "vendor": "cisco",
            "mappings": {"cisco": {"Gi": "GigabitEthernet"}},
        },
    )

    assert len(candidates) == 1
    assert candidates[0].confidence.value == "confirmed"
    assert summary.discovered == 2
    assert summary.candidates == 1


def test_resolve_one_sided_neighbor_is_partial() -> None:
    a = _device(
        "switch1", [_neighbor("Gi0/1", "switch2", "Gi0/1", "aa:bb:cc:dd:ee:01")]
    )
    b = _device("switch2", [])
    a.interfaces = [NormalizedInterface(name="GigabitEthernet0/1")]
    b.interfaces = [NormalizedInterface(name="GigabitEthernet0/1")]

    candidates, _ = resolve_cables(
        DiscoveryResult(devices=[a, b]),
        netbox_client=None,
        normalization_rules={
            "vendor": "cisco",
            "mappings": {"cisco": {"Gi": "GigabitEthernet"}},
        },
    )

    assert len(candidates) == 1
    assert candidates[0].confidence.value == "partial"


def test_resolve_unknown_neighbor_marks_unresolvable() -> None:
    a = _device(
        "switch1", [_neighbor("Gi0/1", "missing", "Gi0/1", "aa:bb:cc:dd:ee:01")]
    )
    a.interfaces = [NormalizedInterface(name="GigabitEthernet0/1")]

    candidates, summary = resolve_cables(
        DiscoveryResult(devices=[a]),
        netbox_client=None,
        normalization_rules={
            "vendor": "cisco",
            "mappings": {"cisco": {"Gi": "GigabitEthernet"}},
        },
    )

    assert candidates == []
    assert summary.unresolvable == 1
    assert summary.skip_entries[0].reason == "neighbor_device_not_found"


def test_resolve_self_loop_is_skipped() -> None:
    a = _device(
        "switch1", [_neighbor("Gi0/1", "switch1", "Gi0/1", "aa:bb:cc:dd:ee:01")]
    )
    a.interfaces = [NormalizedInterface(name="GigabitEthernet0/1")]

    candidates, summary = resolve_cables(
        DiscoveryResult(devices=[a]),
        netbox_client=None,
        normalization_rules={
            "vendor": "cisco",
            "mappings": {"cisco": {"Gi": "GigabitEthernet"}},
        },
    )

    assert candidates == []
    assert summary.unresolvable == 1
    assert summary.skip_entries[0].reason == "self_loop_detected"


def test_resolve_bidirectional_deduplication() -> None:
    a = _device(
        "switch1", [_neighbor("Gi0/1", "switch2", "Gi0/1", "aa:bb:cc:dd:ee:01")]
    )
    b = _device(
        "switch2", [_neighbor("Gi0/1", "switch1", "Gi0/1", "aa:bb:cc:dd:ee:02")]
    )
    a.interfaces = [NormalizedInterface(name="GigabitEthernet0/1")]
    b.interfaces = [NormalizedInterface(name="GigabitEthernet0/1")]

    candidates, summary = resolve_cables(
        DiscoveryResult(devices=[a, b]),
        netbox_client=None,
        normalization_rules={
            "vendor": "cisco",
            "mappings": {"cisco": {"Gi": "GigabitEthernet"}},
        },
    )

    assert len(candidates) == 1
    assert summary.candidates == 1
