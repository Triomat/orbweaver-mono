# orbweaver/tests/test_seed_models.py
"""Tests for orbweaver seed model extensions (interfaces, VLANs)."""
import pytest
import yaml as pyyaml
from pydantic import ValidationError

from orbweaver.seed.models import SeedData, SeedDevice, SeedInterface, SeedVLAN


# ────────────────────────────────────────────────────────────────────────────
# SeedVLAN Model Tests
# ────────────────────────────────────────────────────────────────────────────


def test_seedvlan_valid():
    """Test SeedVLAN creation with valid data."""
    vlan = SeedVLAN(vid=100, name="Users", site="site-a")
    assert vlan.vid == 100
    assert vlan.name == "Users"
    assert vlan.site == "site-a"


def test_seedvlan_global_vlan():
    """Test SeedVLAN without site (global VLAN)."""
    vlan = SeedVLAN(vid=200, name="Management")
    assert vlan.vid == 200
    assert vlan.name == "Management"
    assert vlan.site is None


def test_seedvlan_vid_range_lower_bound():
    """Test SeedVLAN vid < 1 is rejected."""
    with pytest.raises(ValidationError):
        SeedVLAN(vid=0, name="Invalid")


def test_seedvlan_vid_range_upper_bound():
    """Test SeedVLAN vid > 4094 is rejected."""
    with pytest.raises(ValidationError):
        SeedVLAN(vid=4095, name="Invalid")


def test_seedvlan_name_required():
    """Test SeedVLAN name is required."""
    with pytest.raises(ValidationError):
        SeedVLAN(vid=100, name="")


def test_seedvlan_name_max_length():
    """Test SeedVLAN name max 64 chars."""
    with pytest.raises(ValidationError):
        SeedVLAN(vid=100, name="x" * 65)


def test_seedvlan_name_within_length():
    """Test SeedVLAN name 64 chars is accepted."""
    vlan = SeedVLAN(vid=100, name="x" * 64)
    assert len(vlan.name) == 64


# ────────────────────────────────────────────────────────────────────────────
# SeedInterface Model Tests
# ────────────────────────────────────────────────────────────────────────────


def test_seedinterface_minimal():
    """Test SeedInterface with only required name field."""
    iface = SeedInterface(name="GigabitEthernet0/1")
    assert iface.name == "GigabitEthernet0/1"
    assert iface.description is None
    assert iface.mac_address is None
    assert iface.type == "1000base-t"
    assert iface.mode is None


def test_seedinterface_with_description():
    """Test SeedInterface with description."""
    iface = SeedInterface(name="GigabitEthernet0/1", description="Uplink to Core")
    assert iface.description == "Uplink to Core"


def test_seedinterface_description_max_length():
    """Test SeedInterface description max 200 chars."""
    with pytest.raises(ValidationError):
        SeedInterface(name="GigabitEthernet0/1", description="x" * 201)


def test_seedinterface_name_required():
    """Test SeedInterface name is required and non-empty."""
    with pytest.raises(ValidationError):
        SeedInterface(name="")


def test_seedinterface_name_max_length():
    """Test SeedInterface name cannot exceed 64 chars."""
    with pytest.raises(ValidationError):
        SeedInterface(name="x" * 65)


def test_seedinterface_mac_address_valid_format():
    """Test SeedInterface mac_address EUI-48 format."""
    iface = SeedInterface(name="GigabitEthernet0/1", mac_address="00:11:22:33:44:55")
    assert iface.mac_address == "00:11:22:33:44:55"


def test_seedinterface_mac_address_hyphen_format():
    """Test SeedInterface mac_address with hyphens."""
    iface = SeedInterface(name="GigabitEthernet0/1", mac_address="00-11-22-33-44-55")
    assert iface.mac_address == "00-11-22-33-44-55"


def test_seedinterface_mac_address_invalid_format():
    """Test SeedInterface mac_address invalid format rejected."""
    with pytest.raises(ValidationError):
        SeedInterface(name="GigabitEthernet0/1", mac_address="00:11:22:33:44")


def test_seedinterface_mode_access():
    """Test SeedInterface mode access."""
    iface = SeedInterface(name="GigabitEthernet0/1", mode="access", access_vlan=100)
    assert iface.mode == "access"
    assert iface.access_vlan == 100


def test_seedinterface_mode_access_requires_access_vlan():
    """Test mode=access requires access_vlan."""
    with pytest.raises(ValidationError):
        SeedInterface(name="GigabitEthernet0/1", mode="access")


def test_seedinterface_mode_tagged():
    """Test SeedInterface mode tagged."""
    iface = SeedInterface(name="GigabitEthernet0/1", mode="tagged", tagged_vlans=[10, 20])
    assert iface.mode == "tagged"
    assert iface.tagged_vlans == [10, 20]


def test_seedinterface_mode_tagged_requires_tagged_vlans():
    """Test mode=tagged requires a non-empty tagged_vlans list."""
    with pytest.raises(ValidationError):
        SeedInterface(name="GigabitEthernet0/1", mode="tagged")


def test_seedinterface_mode_tagged_rejects_empty_tagged_vlans():
    """Test mode=tagged rejects empty tagged_vlans list."""
    with pytest.raises(ValidationError):
        SeedInterface(name="GigabitEthernet0/1", mode="tagged", tagged_vlans=[])


def test_seedinterface_mode_tagged_all():
    """Test SeedInterface mode tagged-all."""
    iface = SeedInterface(name="GigabitEthernet0/1", mode="tagged-all")
    assert iface.mode == "tagged-all"


def test_seedinterface_mode_tagged_all_ignores_vlan_fields():
    """Test mode=tagged-all clears access/tagged VLAN fields."""
    iface = SeedInterface(
        name="GigabitEthernet0/1",
        mode="tagged-all",
        access_vlan=100,
        tagged_vlans=[10, 20],
    )
    assert iface.mode == "tagged-all"
    assert iface.access_vlan is None
    assert iface.tagged_vlans is None


def test_seedinterface_mode_invalid():
    """Test SeedInterface mode invalid value rejected."""
    with pytest.raises(ValidationError):
        SeedInterface(name="GigabitEthernet0/1", mode="invalid")


def test_seedinterface_conflicting_vlan_modes():
    """Test SeedInterface both access_vlan and tagged_vlans rejected."""
    with pytest.raises(ValidationError):
        SeedInterface(
            name="GigabitEthernet0/1",
            mode="access",
            access_vlan=100,
            tagged_vlans=[10, 20]
        )


def test_seedinterface_tagged_vlan_range():
    """Test SeedInterface tagged_vlans out of range rejected."""
    with pytest.raises(ValidationError):
        SeedInterface(
            name="GigabitEthernet0/1",
            mode="tagged",
            tagged_vlans=[10, 4095]
        )


# ────────────────────────────────────────────────────────────────────────────
# SeedDevice with Interfaces
# ────────────────────────────────────────────────────────────────────────────


def test_seeddevice_with_interfaces():
    """Test SeedDevice with interfaces list."""
    iface1 = SeedInterface(name="Gi0/1", description="Link to Switch-2")
    iface2 = SeedInterface(name="Gi0/2", description="Link to Switch-3")
    dev = SeedDevice(
        name="Switch-1",
        device_type="Catalyst 9300",
        manufacturer="Cisco",
        role="Access",
        site="DC1",
        interfaces=[iface1, iface2]
    )
    assert len(dev.interfaces) == 2
    assert dev.interfaces[0].name == "Gi0/1"


def test_seeddevice_duplicate_interface_names():
    """Test SeedDevice duplicate interface names rejected."""
    iface1 = SeedInterface(name="Gi0/1")
    iface2 = SeedInterface(name="Gi0/1")  # Duplicate
    with pytest.raises(ValidationError):
        SeedDevice(
            name="Switch-1",
            device_type="Catalyst 9300",
            manufacturer="Cisco",
            role="Access",
            site="DC1",
            interfaces=[iface1, iface2]
        )


# ────────────────────────────────────────────────────────────────────────────
# SeedData with VLANs and Devices
# ────────────────────────────────────────────────────────────────────────────


def test_seeddata_with_vlans():
    """Test SeedData with vlans list."""
    vlan1 = SeedVLAN(vid=10, name="Data")
    vlan2 = SeedVLAN(vid=20, name="Voice")
    data = SeedData(vlans=[vlan1, vlan2])
    assert len(data.vlans) == 2
    assert data.vlans[0].vid == 10


def test_seeddata_vlans_optional():
    """Test SeedData vlans field is optional."""
    data = SeedData()
    assert data.vlans is None


def test_seeddata_vlans_accepts_none():
    """Test SeedData vlans field accepts explicit None."""
    data = SeedData(vlans=None)
    assert data.vlans is None


def test_seeddata_parse_yaml_with_vlans():
    """Test SeedData parsing YAML with VLANs."""
    yaml_str = """
vlans:
  - vid: 100
    name: Users
    site: site-a
  - vid: 200
    name: Management
devices: []
"""
    raw = pyyaml.safe_load(yaml_str)
    data = SeedData.model_validate(raw)
    assert len(data.vlans) == 2
    assert data.vlans[0].vid == 100
    assert data.vlans[1].site is None
