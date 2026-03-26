"""Seed a fake review session for UI testing (no real devices needed)."""

import json
import pathlib
import sys
import uuid
from datetime import datetime, timezone

review_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("reviews")
review_dir.mkdir(exist_ok=True)

review_id = str(uuid.uuid4())

devices = [
    {
        "name": "sw-core-01",
        "serial_number": "FDO2248A0GX",
        "status": "active",
        "device_type": {
            "model": "Catalyst 9300-48P",
            "part_number": "C9300-48P",
            "manufacturer": {"name": "Cisco"},
        },
        "platform": {"name": "IOS-XE 17.9.3", "manufacturer": None},
        "site": {"name": "DC1"},
        "role": {"name": "access-switch"},
        "interfaces": [
            {
                "name": "GigabitEthernet1/0/1",
                "type": "1000base-t",
                "enabled": True,
                "description": "Server uplink",
                "mtu": 1500,
                "speed": 1000000000,
                "ip_addresses": [{"address": "10.0.0.1/30", "role": None, "primary": True}],
                "vlan_mode": "access",
                "untagged_vlan": {"vid": 100, "name": "MGMT", "status": "active"},
                "tagged_vlans": [],
            },
            {
                "name": "GigabitEthernet1/0/2",
                "type": "1000base-t",
                "enabled": True,
                "description": "AP-floor-1",
                "mtu": 1500,
                "speed": 1000000000,
                "ip_addresses": [],
                "vlan_mode": "tagged",
                "untagged_vlan": None,
                "tagged_vlans": [
                    {"vid": 10, "name": "CORP", "status": "active"},
                    {"vid": 20, "name": "GUEST", "status": "active"},
                ],
            },
            {
                "name": "Loopback0",
                "type": "virtual",
                "enabled": True,
                "description": "",
                "mtu": None,
                "speed": None,
                "ip_addresses": [{"address": "192.168.255.1/32", "role": "loopback", "primary": False}],
                "vlan_mode": None,
                "untagged_vlan": None,
                "tagged_vlans": [],
            },
        ],
        "vlans": [
            {"vid": 10, "name": "CORP", "status": "active"},
            {"vid": 20, "name": "GUEST", "status": "active"},
            {"vid": 100, "name": "MGMT", "status": "active"},
        ],
    },
    {
        "name": "sw-access-02",
        "serial_number": "FDO2248B1HY",
        "status": "active",
        "device_type": {
            "model": "Catalyst 9200-24T",
            "part_number": "C9200-24T",
            "manufacturer": {"name": "Cisco"},
        },
        "platform": {"name": "IOS-XE 17.6.1", "manufacturer": None},
        "site": {"name": "DC1"},
        "role": {"name": "access-switch"},
        "interfaces": [
            {
                "name": "GigabitEthernet1/0/1",
                "type": "1000base-t",
                "enabled": True,
                "description": "",
                "mtu": 1500,
                "speed": 1000000000,
                "ip_addresses": [],
                "vlan_mode": "access",
                "untagged_vlan": {"vid": 100, "name": "MGMT", "status": "active"},
                "tagged_vlans": [],
            },
        ],
        "vlans": [{"vid": 100, "name": "MGMT", "status": "active"}],
    },
    {
        "name": "rtr-edge-01",
        "serial_number": None,
        "status": "active",
        "device_type": {
            "model": "ASR 1001-X",
            "part_number": "ASR1001-X",
            "manufacturer": {"name": "Cisco"},
        },
        "platform": {"name": "IOS-XE 16.12.4", "manufacturer": None},
        "site": {"name": "DC1"},
        "role": {"name": "router"},
        "interfaces": [
            {
                "name": "GigabitEthernet0/0/0",
                "type": "1000base-t",
                "enabled": True,
                "description": "WAN uplink",
                "mtu": 1500,
                "speed": 1000000000,
                "ip_addresses": [{"address": "203.0.113.2/30", "role": None, "primary": True}],
                "vlan_mode": None,
                "untagged_vlan": None,
                "tagged_vlans": [],
            },
        ],
        "vlans": [],
    },
]

review = {
    "id": review_id,
    "policy_name": "test-seed",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "status": "ready",
    "defaults": {"site": "DC1", "role": "access-switch"},
    "devices": [
        {"index": i, "status": "pending", "data": d}
        for i, d in enumerate(devices)
    ],
    "error": None,
}

out = review_dir / f"{review_id}.json"
out.write_text(json.dumps(review, indent=2))
print(review_id)
