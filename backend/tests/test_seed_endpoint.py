# backend/tests/test_seed_endpoint.py
import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import orbweaver.app  # registers orbweaver routes onto device_discovery.server.app
from device_discovery.server import app

client = TestClient(app)

SEED_JSON = json.dumps({
    "sites": [{"name": "theBASEMENT", "slug": "thebasement"}],
    "manufacturers": [{"name": "Cisco", "slug": "cisco"}],
    "device_types": [{"manufacturer": "Cisco", "model": "Meraki MX67", "slug": "cisco-meraki-mx67", "u_height": 1}],
    "device_roles": [{"name": "Firewall", "slug": "firewall", "color": "f44336"}],
    "racks": [{"name": "theRACK", "site": "theBASEMENT", "u_height": 42}],
    "devices": [{"name": "fw-01", "device_type": "Meraki MX67", "manufacturer": "Cisco", "role": "Firewall", "site": "theBASEMENT", "status": "active"}],
})


@patch("orbweaver.seed.loader._pynetbox_client")
def test_seed_endpoint_returns_200(mock_client):
    nb = MagicMock()
    for ep in [nb.tenancy.tenants, nb.dcim.sites, nb.dcim.racks,
               nb.dcim.manufacturers, nb.dcim.device_types, nb.dcim.device_roles,
               nb.dcim.platforms, nb.dcim.devices, nb.extras.tags, nb.ipam.ip_addresses]:
        ep.get.return_value = None
        created = MagicMock()
        created.id = 1
        ep.create.return_value = created
    nb.dcim.racks.filter.return_value = [MagicMock(id=1)]
    mock_client.return_value = nb

    response = client.post(
        "/api/v1/seed",
        content=SEED_JSON,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "created" in body
    assert "skipped" in body
    assert "errors" in body
    assert body["created"]["sites"] == 1
    assert body["created"]["devices"] == 1


def test_seed_endpoint_invalid_json_returns_400():
    response = client.post(
        "/api/v1/seed",
        content="{ not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400


def test_seed_endpoint_invalid_schema_returns_422():
    response = client.post(
        "/api/v1/seed",
        content=json.dumps({"devices": [{"missing_required": True}]}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
