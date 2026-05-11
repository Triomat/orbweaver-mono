"""Shared pytest fixtures for cable discovery tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from orbweaver.models.common import (
    DeviceStatus,
    NormalizedDevice,
    NormalizedDeviceRole,
    NormalizedDeviceType,
    NormalizedLLDPNeighbor,
    NormalizedManufacturer,
    NormalizedSite,
)


@pytest.fixture
def lldp_neighbor() -> NormalizedLLDPNeighbor:
    return NormalizedLLDPNeighbor(
        local_interface="Gi0/1",
        neighbor_device_name="switch2.example.com",
        neighbor_interface="Gi0/2",
        neighbor_chassis_mac="aa:bb:cc:dd:ee:ff",
        neighbor_mgmt_ip="192.0.2.2",
    )


@pytest.fixture
def normalized_device(lldp_neighbor: NormalizedLLDPNeighbor) -> NormalizedDevice:
    manufacturer = NormalizedManufacturer(name="Cisco", slug="cisco")
    return NormalizedDevice(
        name="switch1.example.com",
        device_type=NormalizedDeviceType(
            manufacturer=manufacturer,
            model="Catalyst 9300",
            slug="c9300",
        ),
        role=NormalizedDeviceRole(name="Access Switch", slug="access-switch"),
        site=NormalizedSite(name="Lab", slug="lab"),
        status=DeviceStatus.ACTIVE,
        lldp_neighbors=[lldp_neighbor],
    )


@pytest.fixture
def netbox_client() -> MagicMock:
    client = MagicMock()
    client.dcim.devices.filter.return_value = []
    client.dcim.interfaces.filter.return_value = []
    client.dcim.cables.all.return_value = []
    client.dcim.cables.create.return_value = SimpleNamespace(id=999)
    return client