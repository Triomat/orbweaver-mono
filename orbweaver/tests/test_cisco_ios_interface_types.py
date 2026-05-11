from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from orbweaver.collectors.cisco_ios import CiscoCollector, CiscoConfig
from orbweaver.models.common import (
    DeviceStatus,
    InterfaceType,
    NormalizedDevice,
    NormalizedDeviceRole,
    NormalizedDeviceType,
    NormalizedManufacturer,
    NormalizedSite,
)


@pytest.fixture
def collector() -> CiscoCollector:
    return CiscoCollector(CiscoConfig(hosts=["192.0.2.10"], username="user", password="pass"))


@pytest.fixture
def device() -> NormalizedDevice:
    manufacturer = NormalizedManufacturer(name="Cisco", slug="cisco")
    return NormalizedDevice(
        name="switch1",
        device_type=NormalizedDeviceType(
            manufacturer=manufacturer,
            model="Catalyst 9300",
            slug="catalyst-9300",
        ),
        role=NormalizedDeviceRole(name="Access Switch", slug="access-switch"),
        site=NormalizedSite(name="Lab", slug="lab"),
        status=DeviceStatus.ACTIVE,
    )


def _collect_interfaces(
    collector: CiscoCollector,
    device: NormalizedDevice,
    raw_ifaces: dict,
    raw_ips: dict | None = None,
):
    collector._current_host = "192.0.2.10"
    with patch(
        "orbweaver.collectors.cisco_ios.napalm_get_interfaces",
        return_value=(raw_ifaces, raw_ips or {}),
    ), patch.object(collector, "_enrich_switchport_data"):
        return collector._collect_interfaces(connection=object(), device=device)


def test_collect_interfaces_keeps_gigabitethernet_type_at_full_speed(
    collector: CiscoCollector, device: NormalizedDevice
) -> None:
    interfaces = _collect_interfaces(
        collector,
        device,
        {
            "GigabitEthernet1/0/20": {
                "is_enabled": True,
                "description": "Uplink",
                "mac_address": "4001.7a93.8a94",
                "speed": 1000,
                "mtu": 1500,
            }
        },
    )

    interface = interfaces[0]
    assert interface.type is InterfaceType.ONETHOUSANDBASE_T
    assert interface.speed == 1_000_000


def test_collect_interfaces_keeps_gigabitethernet_type_when_negotiated_down(
    collector: CiscoCollector, device: NormalizedDevice
) -> None:
    interfaces = _collect_interfaces(
        collector,
        device,
        {
            "GigabitEthernet1/0/20": {
                "is_enabled": True,
                "description": "Sensor",
                "mac_address": "4001.7a93.8a94",
                "speed": 100,
                "mtu": 1500,
            }
        },
    )

    interface = interfaces[0]
    assert interface.type is InterfaceType.ONETHOUSANDBASE_T
    assert interface.speed == 100_000


def test_collect_interfaces_keeps_abbreviated_gi_type_when_negotiated_down(
    collector: CiscoCollector, device: NormalizedDevice
) -> None:
    interfaces = _collect_interfaces(
        collector,
        device,
        {
            "Gi1/0/1": {
                "is_enabled": True,
                "description": "Access port",
                "mac_address": "4001.7a93.8a95",
                "speed": 100,
                "mtu": 1500,
            }
        },
    )

    interface = interfaces[0]
    assert interface.type is InterfaceType.ONETHOUSANDBASE_T
    assert interface.speed == 100_000


def test_collect_interfaces_keeps_fastethernet_type_without_reported_speed(
    collector: CiscoCollector, device: NormalizedDevice
) -> None:
    interfaces = _collect_interfaces(
        collector,
        device,
        {
            "FastEthernet0/1": {
                "is_enabled": True,
                "description": "Legacy endpoint",
                "mac_address": "4001.7a93.8a96",
                "speed": 0,
                "mtu": 1500,
            }
        },
    )

    interface = interfaces[0]
    assert interface.type is InterfaceType.ONEHUNDREDBASE_TX
    assert interface.speed is None


def test_collect_interfaces_keeps_abbreviated_fa_type_without_reported_speed(
    collector: CiscoCollector, device: NormalizedDevice
) -> None:
    interfaces = _collect_interfaces(
        collector,
        device,
        {
            "Fa0/1": {
                "is_enabled": True,
                "description": "Legacy endpoint",
                "mac_address": "4001.7a93.8a97",
                "speed": 0,
                "mtu": 1500,
            }
        },
    )

    interface = interfaces[0]
    assert interface.type is InterfaceType.ONEHUNDREDBASE_TX
    assert interface.speed is None


def test_collect_interfaces_corrects_mixed_gi_and_fa_names_independently(
    collector: CiscoCollector, device: NormalizedDevice
) -> None:
    interfaces = _collect_interfaces(
        collector,
        device,
        {
            "Gi1/0/1": {
                "is_enabled": True,
                "description": "Negotiated down",
                "mac_address": "4001.7a93.8a98",
                "speed": 100,
                "mtu": 1500,
            },
            "Fa0/1": {
                "is_enabled": True,
                "description": "Legacy endpoint",
                "mac_address": "4001.7a93.8a99",
                "speed": 0,
                "mtu": 1500,
            },
        },
    )

    iface_map = {interface.name: interface for interface in interfaces}
    assert iface_map["Gi1/0/1"].type is InterfaceType.ONETHOUSANDBASE_T
    assert iface_map["Gi1/0/1"].speed == 100_000
    assert iface_map["Fa0/1"].type is InterfaceType.ONEHUNDREDBASE_TX
    assert iface_map["Fa0/1"].speed is None


def test_collect_interfaces_leaves_unknown_names_unchanged(
    collector: CiscoCollector, device: NormalizedDevice
) -> None:
    interfaces = _collect_interfaces(
        collector,
        device,
        {
            "Port1": {
                "is_enabled": True,
                "description": "Unknown naming",
                "mac_address": "4001.7a93.8b00",
                "speed": 0,
                "mtu": 1500,
            }
        },
    )

    interface = interfaces[0]
    assert interface.type is InterfaceType.OTHER
    assert interface.speed is None


def test_collect_interfaces_logs_type_corrections(
    collector: CiscoCollector, device: NormalizedDevice, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="device_discovery.collectors.cisco_ios"):
        interfaces = _collect_interfaces(
            collector,
            device,
            {
                "GigabitEthernet1/0/20": {
                    "is_enabled": True,
                    "description": "Sensor",
                    "mac_address": "4001.7a93.8b01",
                    "speed": 100,
                    "mtu": 1500,
                }
            },
        )

    assert interfaces[0].type is InterfaceType.ONETHOUSANDBASE_T
    assert "Corrected interface type" in caplog.text
    assert "GigabitEthernet1/0/20" in caplog.text
    assert "100base-tx" in caplog.text
    assert "1000base-t" in caplog.text
    assert "100000" in caplog.text


def test_collect_interfaces_skips_correction_log_when_type_already_matches(
    collector: CiscoCollector, device: NormalizedDevice, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="device_discovery.collectors.cisco_ios"):
        interfaces = _collect_interfaces(
            collector,
            device,
            {
                "GigabitEthernet1/0/20": {
                    "is_enabled": True,
                    "description": "Uplink",
                    "mac_address": "4001.7a93.8b02",
                    "speed": 1000,
                    "mtu": 1500,
                }
            },
        )

    assert interfaces[0].type is InterfaceType.ONETHOUSANDBASE_T
    assert "Corrected interface type" not in caplog.text