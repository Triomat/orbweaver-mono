# backend/tests/test_seed_loader.py
from unittest.mock import MagicMock, patch

import pytest

from orbweaver.seed.loader import SeedResult, run_seed
from orbweaver.seed.models import (
    SeedData,
    SeedDevice,
    SeedDeviceRole,
    SeedDeviceType,
    SeedManufacturer,
    SeedPlatform,
    SeedRack,
    SeedSite,
    SeedTenant,
)


def _make_nb():
    """Build a mock pynetbox API with all required endpoints."""
    nb = MagicMock()
    # Default: .get() returns None (object doesn't exist yet)
    for endpoint in [
        nb.tenancy.tenants,
        nb.dcim.sites,
        nb.dcim.racks,
        nb.dcim.manufacturers,
        nb.dcim.device_types,
        nb.dcim.device_roles,
        nb.dcim.platforms,
        nb.dcim.devices,
        nb.dcim.interfaces,
        nb.extras.tags,
        nb.ipam.ip_addresses,
    ]:
        endpoint.get.return_value = None
        created = MagicMock()
        created.id = 1
        endpoint.create.return_value = created
    return nb


@patch("orbweaver.seed.loader._pynetbox_client")
def test_creates_site(mock_client):
    nb = _make_nb()
    mock_client.return_value = nb
    data = SeedData(sites=[SeedSite(name="theBASEMENT", slug="thebasement")])
    result = run_seed(data)
    nb.dcim.sites.create.assert_called_once()
    assert result.created["sites"] == 1
    assert result.skipped["sites"] == 0


@patch("orbweaver.seed.loader._pynetbox_client")
def test_skips_existing_site(mock_client):
    nb = _make_nb()
    mock_client.return_value = nb
    nb.dcim.sites.get.return_value = MagicMock(id=1)  # already exists
    data = SeedData(sites=[SeedSite(name="theBASEMENT", slug="thebasement")])
    result = run_seed(data)
    nb.dcim.sites.create.assert_not_called()
    assert result.skipped["sites"] == 1


@patch("orbweaver.seed.loader._pynetbox_client")
def test_creates_tenant(mock_client):
    nb = _make_nb()
    mock_client.return_value = nb
    data = SeedData(tenant=SeedTenant(name="SVA-DEV", slug="sva-dev"))
    result = run_seed(data)
    nb.tenancy.tenants.create.assert_called_once()
    assert result.created["tenants"] == 1


@patch("orbweaver.seed.loader._pynetbox_client")
def test_creates_device_with_rack(mock_client):
    nb = _make_nb()
    mock_client.return_value = nb

    site_obj = MagicMock(id=10)
    rack_obj = MagicMock(id=20)
    role_obj = MagicMock(id=30)
    mfr_obj = MagicMock(id=40)
    dt_obj = MagicMock(id=50)

    nb.dcim.sites.get.return_value = site_obj
    nb.dcim.racks.filter.return_value = [rack_obj]
    nb.dcim.racks.create.return_value = rack_obj
    nb.dcim.device_roles.get.return_value = role_obj
    nb.dcim.manufacturers.get.return_value = mfr_obj
    nb.dcim.device_types.get.return_value = dt_obj

    data = SeedData(
        sites=[SeedSite(name="theBASEMENT", slug="thebasement")],
        racks=[SeedRack(name="theRACK", site="theBASEMENT")],
        manufacturers=[SeedManufacturer(name="Cisco", slug="cisco")],
        device_types=[
            SeedDeviceType(
                manufacturer="Cisco",
                model="Meraki MX67",
                slug="cisco-meraki-mx67",
            )
        ],
        device_roles=[SeedDeviceRole(name="Firewall", slug="firewall")],
        devices=[
            SeedDevice(
                name="fw-01",
                device_type="Meraki MX67",
                manufacturer="Cisco",
                role="Firewall",
                site="theBASEMENT",
                rack="theRACK",
                position=10,
                face="front",
                serial="ABC123",
                status="active",
            )
        ]
    )
    result = run_seed(data)
    nb.dcim.devices.create.assert_called_once()
    call_kwargs = nb.dcim.devices.create.call_args[1]
    assert call_kwargs["name"] == "fw-01"
    assert call_kwargs["rack"] == 20
    assert call_kwargs["position"] == 10
    assert call_kwargs["serial"] == "ABC123"
    assert result.created["devices"] == 1


@patch("orbweaver.seed.loader._pynetbox_client")
def test_creates_primary_ip_on_mgmt_interface(mock_client):
    nb = _make_nb()
    mock_client.return_value = nb

    device_obj = MagicMock(id=101, name="fw-01")
    ip_obj = MagicMock(id=201, assigned_object_type=None, assigned_object_id=None)
    iface_obj = MagicMock(id=301, name="mgmt0")

    nb.dcim.devices.create.return_value = device_obj
    nb.dcim.interfaces.filter.return_value = []
    nb.dcim.interfaces.create.return_value = iface_obj
    nb.ipam.ip_addresses.get.return_value = None
    nb.ipam.ip_addresses.create.return_value = ip_obj

    data = SeedData(
        sites=[SeedSite(name="theBASEMENT", slug="thebasement")],
        manufacturers=[SeedManufacturer(name="Cisco", slug="cisco")],
        device_types=[
            SeedDeviceType(
                manufacturer="Cisco",
                model="Meraki MX67",
                slug="cisco-meraki-mx67",
            )
        ],
        device_roles=[SeedDeviceRole(name="Firewall", slug="firewall")],
        devices=[
            SeedDevice(
                name="fw-01",
                device_type="Meraki MX67",
                manufacturer="Cisco",
                role="Firewall",
                site="theBASEMENT",
                primary_ip4="192.0.2.10/24",
            )
        ],
    )

    result = run_seed(data)

    nb.dcim.interfaces.create.assert_called_once_with(
        device=device_obj.id,
        name="mgmt0",
        type="virtual",
    )
    nb.ipam.ip_addresses.create.assert_called_once_with(
        address="192.0.2.10/24",
        assigned_object_type="dcim.interface",
        assigned_object_id=iface_obj.id,
    )
    assert device_obj.primary_ip4 == ip_obj.id
    device_obj.save.assert_called_once()
    assert result.errors == []


@patch("orbweaver.seed.loader._pynetbox_client")
def test_reuses_existing_mgmt_interface_for_primary_ip(mock_client):
    nb = _make_nb()
    mock_client.return_value = nb

    device_obj = MagicMock(id=101, name="fw-01")
    ip_obj = MagicMock(id=201, assigned_object_type=None, assigned_object_id=None)
    iface_obj = MagicMock(id=301, name="mgmt0")

    nb.dcim.devices.create.return_value = device_obj
    nb.dcim.interfaces.filter.return_value = [iface_obj]
    nb.ipam.ip_addresses.get.return_value = ip_obj

    data = SeedData(
        sites=[SeedSite(name="theBASEMENT", slug="thebasement")],
        manufacturers=[SeedManufacturer(name="Cisco", slug="cisco")],
        device_types=[
            SeedDeviceType(
                manufacturer="Cisco",
                model="Meraki MX67",
                slug="cisco-meraki-mx67",
            )
        ],
        device_roles=[SeedDeviceRole(name="Firewall", slug="firewall")],
        devices=[
            SeedDevice(
                name="fw-01",
                device_type="Meraki MX67",
                manufacturer="Cisco",
                role="Firewall",
                site="theBASEMENT",
                primary_ip4="192.0.2.10/24",
            )
        ],
    )

    result = run_seed(data)

    nb.dcim.interfaces.create.assert_not_called()
    ip_obj.save.assert_called_once()
    assert ip_obj.assigned_object_type == "dcim.interface"
    assert ip_obj.assigned_object_id == iface_obj.id
    assert device_obj.primary_ip4 == ip_obj.id
    device_obj.save.assert_called_once()
    assert result.errors == []


@patch("orbweaver.seed.loader._pynetbox_client")
def test_no_client_returns_error(mock_client):
    mock_client.return_value = None
    data = SeedData(sites=[SeedSite(name="X", slug="x")])
    result = run_seed(data)
    assert len(result.errors) == 1
    assert "NETBOX_HOST" in result.errors[0]
