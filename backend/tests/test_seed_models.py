# backend/tests/test_seed_models.py
import pytest
import yaml as pyyaml
from pydantic import ValidationError
from orbweaver.seed.models import SeedData, SeedDevice, SeedDeviceType, SeedManufacturer


MINIMAL_YAML = """
sites:
  - name: theBASEMENT
    slug: thebasement
manufacturers:
  - name: Cisco
    slug: cisco
device_types:
  - manufacturer: Cisco
    model: Meraki MX67
    slug: cisco-meraki-mx67
    u_height: 1
device_roles:
  - name: Firewall
    slug: firewall
    color: f44336
racks:
  - name: theRACK
    site: theBASEMENT
    u_height: 42
devices:
  - name: fw-01
    device_type: Meraki MX67
    manufacturer: Cisco
    role: Firewall
    site: theBASEMENT
    status: active
"""


def test_parse_minimal_yaml():
    raw = pyyaml.safe_load(MINIMAL_YAML)
    data = SeedData.model_validate(raw)
    assert len(data.sites) == 1
    assert data.sites[0].name == "theBASEMENT"
    assert len(data.devices) == 1
    assert data.devices[0].name == "fw-01"


def test_tenant_is_optional():
    raw = pyyaml.safe_load(MINIMAL_YAML)
    data = SeedData.model_validate(raw)
    assert data.tenant is None


def test_device_optional_fields_default():
    raw = pyyaml.safe_load(MINIMAL_YAML)
    data = SeedData.model_validate(raw)
    dev = data.devices[0]
    assert dev.rack is None
    assert dev.position is None
    assert dev.face is None
    assert dev.serial is None
    assert dev.tags == []
    assert dev.parent_device is None
    assert dev.parent_bay is None


def test_invalid_missing_required_field():
    raw = pyyaml.safe_load(MINIMAL_YAML)
    raw["devices"][0].pop("name")
    with pytest.raises(ValidationError):
        SeedData.model_validate(raw)


def test_invalid_unknown_device_reference():
  raw = pyyaml.safe_load(MINIMAL_YAML)
  raw["devices"][0]["device_type"] = "Meraki MR45"
  with pytest.raises(ValidationError):
    SeedData.model_validate(raw)
