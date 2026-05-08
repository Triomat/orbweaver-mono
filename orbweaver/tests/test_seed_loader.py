# orbweaver/tests/test_seed_loader.py
"""Tests for orbweaver seed loader VLAN seeding."""
from unittest.mock import MagicMock, patch

import pytest

from orbweaver.seed.loader import (
    SeedResult,
    _find_interface,
    _find_vlan,
    _seed_interfaces,
    _seed_vlans,
    run_seed,
)
from orbweaver.seed.models import SeedData, SeedDevice, SeedInterface, SeedVLAN


def _make_nb():
    """Build a mock pynetbox API with required endpoints."""
    nb = MagicMock()
    nb.dcim.sites.get.return_value = None
    nb.ipam.vlans.get.return_value = None
    created = MagicMock()
    created.id = 1
    nb.ipam.vlans.create.return_value = created

    nb.dcim.interfaces.filter.return_value = []
    iface_created = MagicMock()
    iface_created.id = 101
    iface_created.name = "GigabitEthernet0/1"
    iface_created.update = MagicMock()
    nb.dcim.interfaces.create.return_value = iface_created

    return nb


def _make_device(name: str = "sw1", site_id: int | None = 1):
    device = MagicMock()
    device.id = 500
    device.name = name
    if site_id is None:
        device.site = None
    else:
        site = MagicMock()
        site.id = site_id
        device.site = site
    return device


# ────────────────────────────────────────────────────────────────────────────
# _find_vlan Helper Tests
# ────────────────────────────────────────────────────────────────────────────


def test_find_vlan_global():
    """Test _find_vlan finds global VLAN by vid."""
    nb = _make_nb()
    vlan_obj = MagicMock(id=1, vid=100)
    nb.ipam.vlans.get.return_value = vlan_obj
    
    vlan_spec = SeedVLAN(vid=100, name="Users")
    result = _find_vlan(nb, vlan_spec)
    
    assert result is not None
    nb.ipam.vlans.get.assert_called_once_with(vid=100, site_id=None)


def test_find_vlan_site_scoped():
    """Test _find_vlan finds site-scoped VLAN."""
    nb = _make_nb()
    site_obj = MagicMock(id=10)
    vlan_obj = MagicMock(id=1, vid=100)
    
    nb.dcim.sites.get.return_value = site_obj
    nb.ipam.vlans.get.return_value = vlan_obj
    
    vlan_spec = SeedVLAN(vid=100, name="Users", site="site-a")
    result = _find_vlan(nb, vlan_spec)
    
    assert result is not None
    nb.dcim.sites.get.assert_called_once_with(name="site-a")
    nb.ipam.vlans.get.assert_called_once_with(vid=100, site_id=10)


def test_find_vlan_site_not_found():
    """Test _find_vlan returns None when site not found."""
    nb = _make_nb()
    nb.dcim.sites.get.return_value = None
    
    vlan_spec = SeedVLAN(vid=100, name="Users", site="nonexistent")
    result = _find_vlan(nb, vlan_spec)
    
    assert result is None


def test_find_vlan_exception_returns_none():
    """Test _find_vlan returns None on exception."""
    nb = _make_nb()
    nb.ipam.vlans.get.side_effect = Exception("Network error")
    
    vlan_spec = SeedVLAN(vid=100, name="Users")
    result = _find_vlan(nb, vlan_spec)
    
    assert result is None


# ────────────────────────────────────────────────────────────────────────────
# _seed_vlans Function Tests
# ────────────────────────────────────────────────────────────────────────────


def test_seed_vlans_create_new():
    """Test _seed_vlans creates new VLANs."""
    nb = _make_nb()
    result = SeedResult()
    
    vlans = [
        SeedVLAN(vid=10, name="Data"),
        SeedVLAN(vid=20, name="Voice"),
    ]
    
    _seed_vlans(nb, vlans, result)
    
    assert result.created["vlans"] == 2
    assert result.skipped["vlans"] == 0
    assert nb.ipam.vlans.create.call_count == 2


def test_seed_vlans_skip_existing():
    """Test _seed_vlans skips existing VLANs."""
    nb = _make_nb()
    result = SeedResult()
    
    vlan_obj = MagicMock(id=1, vid=10)
    nb.ipam.vlans.get.return_value = vlan_obj
    
    vlans = [SeedVLAN(vid=10, name="Data")]
    
    _seed_vlans(nb, vlans, result)
    
    assert result.created["vlans"] == 0
    assert result.skipped["vlans"] == 1
    assert nb.ipam.vlans.create.call_count == 0


def test_seed_vlans_site_scoped():
    """Test _seed_vlans creates site-scoped VLAN."""
    nb = _make_nb()
    result = SeedResult()
    
    site_obj = MagicMock(id=10)
    nb.dcim.sites.get.return_value = site_obj
    nb.ipam.vlans.get.return_value = None
    
    vlans = [SeedVLAN(vid=100, name="Users", site="site-a")]
    
    _seed_vlans(nb, vlans, result)
    
    assert result.created["vlans"] == 1
    # Check that site was passed to create call
    call_kwargs = nb.ipam.vlans.create.call_args[1]
    assert call_kwargs["site"] == 10


def test_seed_vlans_mixed_create_and_skip():
    """Test _seed_vlans mixes create and skip."""
    nb = _make_nb()
    result = SeedResult()
    
    def get_side_effect(**kwargs):
        # First call (vid=10): returns None (not found, will create)
        # Second call (vid=20): returns existing (will skip)
        if kwargs.get("vid") == 20:
            return MagicMock(id=1)
        return None
    
    nb.ipam.vlans.get.side_effect = get_side_effect
    
    vlans = [
        SeedVLAN(vid=10, name="Data"),
        SeedVLAN(vid=20, name="Voice"),
    ]
    
    _seed_vlans(nb, vlans, result)
    
    assert result.created["vlans"] == 1
    assert result.skipped["vlans"] == 1


def test_seed_vlans_error_handling():
    """Test _seed_vlans records errors but continues."""
    nb = _make_nb()
    result = SeedResult()
    
    # Mock create to raise exception on first call
    call_count = [0]
    def create_side_effect(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("Database error on create")
        created = MagicMock()
        created.id = call_count[0]
        return created
    
    nb.ipam.vlans.get.return_value = None  # VLANs don't exist
    nb.ipam.vlans.create.side_effect = create_side_effect
    
    vlans = [
        SeedVLAN(vid=10, name="Data"),
        SeedVLAN(vid=20, name="Voice"),
    ]
    
    _seed_vlans(nb, vlans, result)
    
    # First VLAN create fails, second succeeds
    assert len(result.errors) == 1
    assert "vid=10" in result.errors[0]
    assert result.created["vlans"] == 1
    assert result.skipped["vlans"] == 0


# ────────────────────────────────────────────────────────────────────────────
# Integration Tests with run_seed
# ────────────────────────────────────────────────────────────────────────────


@patch("orbweaver.seed.loader._pynetbox_client")
def test_run_seed_with_vlans_only(mock_client):
    """Test run_seed with VLAN list and no devices."""
    nb = _make_nb()
    mock_client.return_value = nb
    
    data = SeedData(
        vlans=[
            SeedVLAN(vid=10, name="Data"),
            SeedVLAN(vid=20, name="Voice"),
        ]
    )
    
    result = run_seed(data)
    
    assert result.created["vlans"] == 2
    assert result.skipped["vlans"] == 0
    assert nb.ipam.vlans.create.call_count == 2


@patch("orbweaver.seed.loader._pynetbox_client")
def test_run_seed_vlan_repost_shows_skipped(mock_client):
    """Test re-posting VLAN payload shows skipped counters."""
    nb = _make_nb()
    mock_client.return_value = nb
    
    # First call: VLANs don't exist, will create
    nb.ipam.vlans.get.return_value = None
    
    data = SeedData(
        vlans=[
            SeedVLAN(vid=10, name="Data"),
            SeedVLAN(vid=20, name="Voice"),
        ]
    )
    
    # First run
    result1 = run_seed(data)
    assert result1.created["vlans"] == 2
    assert result1.skipped["vlans"] == 0
    
    # Second run: VLANs now exist
    def get_side_effect(**kwargs):
        # Return existing VLAN objects
        return MagicMock(id=1, vid=kwargs.get("vid"))
    
    nb.ipam.vlans.get.side_effect = get_side_effect
    
    result2 = run_seed(data)
    assert result2.created["vlans"] == 0
    assert result2.skipped["vlans"] == 2


# ────────────────────────────────────────────────────────────────────────────
# Interface helper and seeding tests
# ────────────────────────────────────────────────────────────────────────────


def test_find_interface_by_device_and_name():
    nb = _make_nb()
    device = _make_device()
    iface = MagicMock(id=1000, name="Gi0/1")
    nb.dcim.interfaces.filter.return_value = [iface]

    result = _find_interface(nb, device, "Gi0/1")

    assert result is iface
    nb.dcim.interfaces.filter.assert_called_once_with(device_id=device.id, name="Gi0/1")


def test_seed_interfaces_create_new_interfaces():
    nb = _make_nb()
    device = _make_device()
    interfaces = [
        SeedInterface(name="Gi0/1", description="Uplink"),
        SeedInterface(name="Gi0/2", description="Downlink"),
    ]

    created, updated, skipped, errors = _seed_interfaces(nb, device, interfaces)

    assert created == 2
    assert updated == 0
    assert skipped == 0
    assert errors == []
    assert nb.dcim.interfaces.create.call_count == 2


def test_seed_interfaces_fill_in_blank_updates_description_and_mac():
    nb = _make_nb()
    device = _make_device()

    existing = MagicMock()
    existing.id = 222
    existing.name = "Gi0/1"
    existing.description = ""
    existing.mac_address = None
    existing.type = "1000base-t"
    existing.mode = None
    existing.update = MagicMock()
    nb.dcim.interfaces.filter.return_value = [existing]

    interfaces = [
        SeedInterface(
            name="Gi0/1",
            description="To Core",
            mac_address="00:11:22:33:44:55",
        )
    ]

    created, updated, skipped, errors = _seed_interfaces(nb, device, interfaces)

    assert created == 0
    assert updated == 1
    assert skipped == 0
    assert errors == []
    existing.update.assert_called_once()
    sent = existing.update.call_args[0][0]
    assert sent["description"] == "To Core"
    assert sent["mac_address"] == "00:11:22:33:44:55"


def test_seed_interfaces_preserve_non_empty_values():
    nb = _make_nb()
    device = _make_device()

    existing = MagicMock()
    existing.id = 223
    existing.name = "Gi0/1"
    existing.description = "Existing description"
    existing.mac_address = "00:aa:bb:cc:dd:ee"
    existing.type = "1000base-t"
    existing.mode = "access"
    existing.update = MagicMock()
    nb.dcim.interfaces.filter.return_value = [existing]
    nb.ipam.vlans.get.return_value = MagicMock(id=700)

    interfaces = [
        SeedInterface(name="Gi0/1", description="New description", access_vlan=100, mode="access")
    ]

    created, updated, skipped, errors = _seed_interfaces(nb, device, interfaces)

    assert created == 0
    assert updated == 0
    assert skipped == 1
    assert errors == []
    # Mode/VLAN assignment still applies through assignment step, but fill-in-blank should not update description.
    assert existing.update.call_count >= 1


def test_seed_interfaces_assign_access_vlan_success():
    nb = _make_nb()
    device = _make_device(site_id=10)

    iface = MagicMock(id=200, name="Gi0/1")
    iface.update = MagicMock()
    nb.dcim.interfaces.create.return_value = iface

    def vlan_lookup_side_effect(**kwargs):
        if kwargs == {"vid": 100, "site_id": 10}:
            return MagicMock(id=900)
        return None

    nb.ipam.vlans.get.side_effect = vlan_lookup_side_effect

    interfaces = [SeedInterface(name="Gi0/1", mode="access", access_vlan=100)]
    _, _, _, errors = _seed_interfaces(nb, device, interfaces)

    assert errors == []
    iface.update.assert_called_once_with({"mode": "access", "untagged_vlan": 900})


def test_seed_interfaces_assign_tagged_vlans_success():
    nb = _make_nb()
    device = _make_device(site_id=10)

    iface = MagicMock(id=201, name="Gi0/1")
    iface.update = MagicMock()
    nb.dcim.interfaces.create.return_value = iface

    def vlan_lookup_side_effect(**kwargs):
        if kwargs == {"vid": 10, "site_id": 10}:
            return MagicMock(id=910)
        if kwargs == {"vid": 20, "site_id": 10}:
            return MagicMock(id=920)
        return None

    nb.ipam.vlans.get.side_effect = vlan_lookup_side_effect

    interfaces = [SeedInterface(name="Gi0/1", mode="tagged", tagged_vlans=[10, 20])]
    _, _, _, errors = _seed_interfaces(nb, device, interfaces)

    assert errors == []
    iface.update.assert_called_once_with({"mode": "tagged", "tagged_vlans": [910, 920]})


def test_seed_interfaces_missing_access_vlan_records_error():
    nb = _make_nb()
    device = _make_device(site_id=10)
    iface = MagicMock(id=202, name="Gi0/1")
    iface.update = MagicMock()
    nb.dcim.interfaces.create.return_value = iface
    nb.ipam.vlans.get.return_value = None

    interfaces = [SeedInterface(name="Gi0/1", mode="access", access_vlan=999)]
    _, _, _, errors = _seed_interfaces(nb, device, interfaces)

    assert len(errors) == 1
    assert "Could not assign access VLAN 999" in errors[0]["reason"]
    iface.update.assert_called_once_with({"mode": "access"})


def test_seed_interfaces_site_scoped_vlan_preferred_over_global():
    nb = _make_nb()
    device = _make_device(site_id=42)
    iface = MagicMock(id=203, name="Gi0/1")
    iface.update = MagicMock()
    nb.dcim.interfaces.create.return_value = iface

    def vlan_lookup_side_effect(**kwargs):
        if kwargs == {"vid": 100, "site_id": 42}:
            return MagicMock(id=333)
        if kwargs == {"vid": 100, "site_id": None}:
            return MagicMock(id=444)
        return None

    nb.ipam.vlans.get.side_effect = vlan_lookup_side_effect

    interfaces = [SeedInterface(name="Gi0/1", mode="access", access_vlan=100)]
    _, _, _, errors = _seed_interfaces(nb, device, interfaces)

    assert errors == []
    iface.update.assert_called_once_with({"mode": "access", "untagged_vlan": 333})


def test_seed_interfaces_global_vlan_fallback_when_no_site_vlan():
    nb = _make_nb()
    device = _make_device(site_id=42)
    iface = MagicMock(id=204, name="Gi0/1")
    iface.update = MagicMock()
    nb.dcim.interfaces.create.return_value = iface

    def vlan_lookup_side_effect(**kwargs):
        if kwargs == {"vid": 100, "site_id": 42}:
            return None
        if kwargs == {"vid": 100, "site_id": None}:
            return MagicMock(id=555)
        return None

    nb.ipam.vlans.get.side_effect = vlan_lookup_side_effect

    interfaces = [SeedInterface(name="Gi0/1", mode="access", access_vlan=100)]
    _, _, _, errors = _seed_interfaces(nb, device, interfaces)

    assert errors == []
    iface.update.assert_called_once_with({"mode": "access", "untagged_vlan": 555})


@patch("orbweaver.seed.loader._pynetbox_client")
@patch("orbweaver.seed.loader._create_device")
def test_run_seed_interface_device_not_found_records_error(mock_create_device, mock_client):
    nb = _make_nb()
    mock_client.return_value = nb
    mock_create_device.return_value = None

    data = SeedData(
        sites=[{"name": "DC1", "slug": "dc1"}],
        manufacturers=[{"name": "Cisco", "slug": "cisco"}],
        device_types=[{"manufacturer": "Cisco", "model": "C9300", "slug": "c9300"}],
        device_roles=[{"name": "Access", "slug": "access"}],
        devices=[
            SeedDevice(
                name="sw1",
                device_type="C9300",
                manufacturer="Cisco",
                role="Access",
                site="DC1",
                interfaces=[SeedInterface(name="Gi0/1")],
            )
        ],
    )

    result = run_seed(data)
    assert any("device='sw1': device not found" in err for err in result.errors)


@patch("orbweaver.seed.loader._pynetbox_client")
@patch("orbweaver.seed.loader._create_device")
def test_run_seed_full_workflow_with_repost(mock_create_device, mock_client):
    """Full workflow: create VLAN + interface, then re-post and verify skips."""
    nb = _make_nb()
    mock_client.return_value = nb

    device_obj = _make_device(name="sw1", site_id=None)
    mock_create_device.return_value = device_obj

    state = {"vlan_exists": False, "run": 1}

    def vlan_get_side_effect(**kwargs):
        if kwargs == {"vid": 100, "site_id": None}:
            if state["vlan_exists"]:
                vlan = MagicMock()
                vlan.id = 1000
                return vlan
            return None
        return None

    def vlan_create_side_effect(**kwargs):
        created = MagicMock()
        created.id = 1000
        state["vlan_exists"] = True
        return created

    created_iface = MagicMock()
    created_iface.id = 2000
    created_iface.name = "Gi0/1"
    created_iface.description = "Seeded"
    created_iface.update = MagicMock()

    existing_iface = MagicMock()
    existing_iface.id = 2000
    existing_iface.name = "Gi0/1"
    existing_iface.description = "Seeded"
    existing_iface.mac_address = None
    existing_iface.type = "1000base-t"
    existing_iface.mode = "access"
    existing_iface.update = MagicMock()

    def interface_filter_side_effect(**kwargs):
        if state["run"] == 1:
            return []
        return [existing_iface]

    nb.ipam.vlans.get.side_effect = vlan_get_side_effect
    nb.ipam.vlans.create.side_effect = vlan_create_side_effect
    nb.dcim.interfaces.create.return_value = created_iface
    nb.dcim.interfaces.filter.side_effect = interface_filter_side_effect

    data = SeedData(
        sites=[{"name": "DC1", "slug": "dc1"}],
        manufacturers=[{"name": "Cisco", "slug": "cisco"}],
        device_types=[{"manufacturer": "Cisco", "model": "C9300", "slug": "c9300"}],
        device_roles=[{"name": "Access", "slug": "access"}],
        vlans=[SeedVLAN(vid=100, name="Users")],
        devices=[
            SeedDevice(
                name="sw1",
                device_type="C9300",
                manufacturer="Cisco",
                role="Access",
                site="DC1",
                interfaces=[
                    SeedInterface(
                        name="Gi0/1",
                        description="Seeded",
                        mode="access",
                        access_vlan=100,
                    )
                ],
            )
        ],
    )

    result1 = run_seed(data)
    assert result1.created["vlans"] == 1
    assert result1.created["interfaces"] == 1

    state["run"] = 2
    result2 = run_seed(data)
    assert result2.skipped["vlans"] == 1
    assert result2.skipped["interfaces"] == 1
