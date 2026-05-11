# Quickstart: LLDP Cable Discovery & Ingestion

**Last Updated**: 2026-05-11

---

## Installation

Ensure you have orbweaver installed with cables support:

```bash
cd /path/to/orbweaver-mono
python3 -m venv .venv
source .venv/bin/activate
just install-backend   # Installs both backend and orbweaver packages
```

---

## Configuration

### Environment Variables

```bash
export NETBOX_HOST=netbox.example.com
export NETBOX_PORT=8000
export NETBOX_TOKEN=your-netbox-api-token
export ORBWEAVER_CABLES_ENABLED=true  # Default; set false to disable cables globally
```

### Policy YAML

Create a policy file with LLDP-enabled collectors:

```yaml
policies:
  site-dc1-discovery:
    config:
      defaults:
        site: "DC1"
        role: "access-switch"
        cables_enabled: true         # Enable cable discovery for this policy
    scope:
      - hostname: 192.168.1.1
        username: admin
        password: secret
        collector: cisco_ios         # LLDP supported collectors
      - hostname: 192.168.1.2
        username: admin
        password: secret
        collector: cisco_ios
```

---

## Workflow 1: Direct Cable Discovery & Ingestion

Run discovery and automatically create cables in NetBox.

### Step 1: Run Discovery

```bash
# Send policy to discovery API
curl -X POST http://localhost:8072/api/v1/policies \
  -H "Content-Type: application/yaml" \
  -d @policy.yaml

# Response includes cable summary:
{
  "policy_name": "site-dc1-discovery",
  "status": "complete",
  "devices": {
    "discovered": 2,
    "created": 2
  },
  "cables": {
    "discovered": 2,
    "candidates": 2,
    "created": 2,
    "skipped": 0,
    "unresolvable": 0,
    "skip_entries": [],
    "ingestion_disabled": false
  }
}
```

### Step 2: Verify Cables in NetBox

```bash
# Query NetBox for newly created cables
curl -X GET http://netbox:8000/api/dcim/cables/?limit=0 \
  -H "Authorization: Token $NETBOX_TOKEN" | jq '.results[] | "\(.termination_a_device.name):\(.termination_a_interface.name) ↔ \(.termination_b_device.name):\(.termination_b_interface.name)"'

# Output:
# "switch1:GigabitEthernet0/1 ↔ switch2:GigabitEthernet0/1"
# "switch1:GigabitEthernet0/2 ↔ switch3:GigabitEthernet0/1"
```

### Step 3: Repeat Discovery (Idempotency Test)

```bash
# Run discovery again with same policy
curl -X POST http://localhost:8072/api/v1/policies \
  -H "Content-Type: application/yaml" \
  -d @policy.yaml

# Response: cables.created=0, cables.skipped=2 (already exist)
# NetBox cable count unchanged
```

---

## Workflow 2: Review-Before-Ingest

Run discovery in "hold" mode; operator reviews and approves cables.

### Step 1: Trigger Discovery-for-Review

```bash
# POST to /discover endpoint (triggers review mode)
curl -X POST http://localhost:8072/api/v1/discover \
  -H "Content-Type: application/yaml" \
  -d @policy.yaml

# Response:
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "policy_name": "site-dc1-discovery",
  "status": "ready",
  "device_count": 2,
  "cable_count": 2,
  "accepted_devices": 0,
  "accepted_cables": 0,
  "created_at": "2026-05-11T14:30:00Z"
}
```

### Step 2: Review Cables in UI

Navigate to the UI at `http://localhost:3000/reviews/{session_id}`:

1. Click **Cables** tab
2. View cable candidates with confidence indicators:
   - 🟢 **Confirmed**: Both endpoints discovered bidirectionally
   - 🟡 **Partial**: One-sided or one endpoint existing
   - ⚪ **Unresolvable**: Skipped (hover to see reason)
3. Click **Accept** or **Reject** on each cable row
4. Bulk actions: "Accept All", "Reject All"

**Cable Table Example:**

| Device A | Interface A | Device B | Interface B | Confidence | Action |
|---|---|---|---|---|---|
| switch1 | Gi0/1 | switch2 | Gi0/1 | Confirmed 🟢 | ✓ |
| switch1 | Gi0/2 | switch3 | Gi0/1 | Confirmed 🟢 | ✓ |
| switch2 | Gi0/1 | unknown-box | Gi0/1 | Unresolvable ⚪ | ✗ |

**Skip Reason Tooltip** (hover on Unresolvable):

```
❌ Unresolvable
Reason: neighbor_device_not_found
Neighbor hostname: "unknown-box"
Chassis MAC: aa:bb:cc:dd:ee:99
```

### Step 3: Query Review Session

```bash
# Fetch session details via API
curl -X GET http://localhost:8072/api/v1/reviews/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN"

# Response includes cables array:
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "cables": [
    {
      "index": 0,
      "status": "pending",
      "data": {
        "cable": {
          "device_a_name": "switch1",
          "interface_a_name": "GigabitEthernet0/1",
          "device_b_name": "switch2",
          "interface_b_name": "GigabitEthernet0/1",
          "label": "LLDP auto-discovered"
        },
        "confidence": "confirmed",
        "device_a_discovered": true,
        "device_b_discovered": true,
        "lldp_direction": "bidirectional"
      }
    },
    ...
  ],
  "cable_summary": {
    "discovered": 3,
    "candidates": 3,
    "created": 0,
    "skipped": 0,
    "unresolvable": 1,
    "skip_entries": [
      {
        "local_device": "switch2",
        "local_interface": "Gi0/1",
        "neighbor_hostname": "unknown-box",
        "reason": "neighbor_device_not_found"
      }
    ]
  }
}
```

### Step 4: Approve/Reject Cables

```bash
# Approve cable 0 (accept)
curl -X PATCH http://localhost:8072/api/v1/reviews/550e8400-e29b-41d4-a716-446655440000/cables/0 \
  -H "Content-Type: application/json" \
  -d '{"status": "accepted"}'

# Reject cable 2 (reject unresolvable)
curl -X PATCH http://localhost:8072/api/v1/reviews/550e8400-e29b-41d4-a716-446655440000/cables/2 \
  -H "Content-Type: application/json" \
  -d '{"status": "rejected"}'
```

### Step 5: Ingest Approved Cables

```bash
# POST to ingest endpoint
curl -X POST http://localhost:8072/api/v1/reviews/550e8400-e29b-41d4-a716-446655440000/ingest \
  -H "Content-Type: application/json"

# Response:
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ingested",
  "devices_created": 2,
  "cables_created": 2,
  "cables_skipped": 0,
  "ingestion_summary": {
    "devices": {
      "created": 2,
      "skipped": 0,
      "failed": 0
    },
    "cables": {
      "created": 2,
      "skipped": 0,
      "failed": 0
    }
  }
}
```

### Step 6: Verify Cables in NetBox

Only the 2 approved cables are now in NetBox; the unresolvable cable was not created.

---

## Workflow 3: Disable Cable Ingestion

For environments where cables are managed manually, disable cable discovery.

### Via Environment Variable

```bash
export ORBWEAVER_CABLES_ENABLED=false

# Run discovery
curl -X POST http://localhost:8072/api/v1/policies \
  -H "Content-Type: application/yaml" \
  -d @policy.yaml

# Response includes: "cables": { "ingestion_disabled": true }
```

### Via Policy Configuration

```yaml
config:
  cables_enabled: false  # Disable cables for this policy
```

Result: LLDP data is collected and visible in review workflow, but no cables are created in NetBox.

---

## Workflow 4: Troubleshooting

### Scenario: Cable Not Created — Neighbor Device Not Found

**Symptom**: One cable candidate is unresolvable with reason `"neighbor_device_not_found"`.

**Cause**: LLDP neighbor hostname does not match any device in NetBox or discovery.

**Resolution**:

1. Check NetBox device name vs. LLDP advertisement:
   ```bash
   # From device log or LLDP capture:
   # Local device (switch1) sees neighbor: "unknown-switch.example.com"
   
   # Check NetBox:
   curl -X GET http://netbox:8000/api/dcim/devices/?name=unknown-switch \
     -H "Authorization: Token $NETBOX_TOKEN"
   
   # If empty: device doesn't exist in NetBox; create it manually or
   # include it in the next discovery run
   ```

2. If device exists in NetBox but hostname doesn't match:
   - Update LLDP device's hostname in config
   - Or manually create device in NetBox with matching name
   - Re-run discovery

### Scenario: Cable Not Created — Interface Name Mismatch

**Symptom**: Cable unresolvable with reason `"interface_name_mismatch"`.

**Cause**: Interface name from LLDP doesn't match any interface in NetBox.

**Resolution**:

1. Check interface name normalization:
   ```bash
   # LLDP advertises: "Gi0/1" (Cisco abbreviation)
   # Should normalize to: "GigabitEthernet0/1"
   # But NetBox interface is named: "GigabitEthernet0/01" (different!)
   
   # Fix: Update NetBox interface name to "GigabitEthernet0/1"
   curl -X PATCH http://netbox:8000/api/dcim/interfaces/123/ \
     -H "Authorization: Token $NETBOX_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "GigabitEthernet0/1"}'
   ```

2. Or update LLDP source (device config) to advertise matching name

### Scenario: Cable Already Exists — Duplicate Prevention

**Symptom**: Cable count doesn't increase on repeated discovery runs.

**Expectation**: This is correct idempotent behavior.

**Verification**:

```bash
# Run 1
curl -X POST http://localhost:8072/api/v1/policies -d @policy.yaml
# Response: cables.created=2

# Run 2
curl -X POST http://localhost:8072/api/v1/policies -d @policy.yaml
# Response: cables.created=0, cables.skipped=2

# NetBox cable count: still 2 (unchanged)
```

### Scenario: NetBox API Unreachable

**Symptom**: Discovery fails; error message: "NetBox API error during cable ingestion".

**Cause**: `NETBOX_HOST`, `NETBOX_PORT`, or `NETBOX_TOKEN` misconfigured, or NetBox is down.

**Resolution**:

1. Check connectivity:
   ```bash
   curl -X GET http://$NETBOX_HOST:$NETBOX_PORT/api/status/ \
     -H "Authorization: Token $NETBOX_TOKEN"
   ```

2. Verify token has `dcim.add_cable` permission:
   ```bash
   curl -X GET http://$NETBOX_HOST:$NETBOX_PORT/api/users/tokens/$NETBOX_TOKEN/ \
     -H "Authorization: Token $NETBOX_TOKEN" | jq '.permissions'
   ```

3. Retry discovery after NetBox is online

---

## Workflow 5: Performance & Monitoring

### Check Discovery Logs

```bash
# Tail backend logs
just backend-logs

# Filter for cable-related messages
just backend-logs | grep -i cable
```

**Expected log output**:

```
[INFO] Resolving 12 LLDP neighbors for discovery run
[DEBUG] Neighbor 'switch2' (MAC aa:bb:cc:dd:ee:ff) matched to discovered device 'switch2'
[DEBUG] Cable candidate: switch1:GigabitEthernet0/1 ↔ switch2:GigabitEthernet0/1 (Confirmed)
[INFO] Cable resolution complete: 12 discovered, 10 candidates, 8 created, 2 skipped
[INFO] Created cable: switch1:Gi0/1 ↔ switch2:Gi0/1 in NetBox (id=999)
```

### Monitor Cable Counts

```bash
# Get summary from last discovery
curl -X GET http://localhost:8072/api/v1/status \
  -H "Authorization: Bearer $TOKEN" | jq '.last_discovery.cables'

# Output:
{
  "discovered": 12,
  "candidates": 10,
  "created": 8,
  "skipped": 2,
  "unresolvable": 0,
  "resolution_duration_ms": 42.5,
  "ingestion_duration_ms": 125.3
}
```

### Performance Benchmarks

| Operation | Expected Time | Notes |
|---|---|---|
| Resolve 100 LLDP neighbors | < 100ms | Includes normalization + deduplication |
| Ingest 50 cables to NetBox | 1–5s | Depends on NetBox API latency |
| Review 50 cables in UI | < 1s | Table render + cable filtering |

---

## Workflow 6: Custom Interface Normalization

If your network uses non-standard interface name abbreviations, extend the normalization rules.

**File**: `orbweaver/cables/normalize.py`

```python
VENDOR_INTERFACE_RULES = {
    "cisco": {
        "Gi": "GigabitEthernet",
        "Fa": "FastEthernet",
        "Et": "Ethernet",
        "Te": "TenGigabitEthernet",
    },
    "aruba": {
        # Aruba uses canonical names already
    },
    "juniper": {
        "ge": "ge-",  # Not typically abbreviated
    },
    "custom_vendor": {
        "X": "CustomInterfaceType",  # Your custom abbreviation
    },
}
```

Add your vendor's rules and restart the backend:

```bash
just backend-restart
```

Re-run discovery; interface names should now normalize correctly.

---

## API Reference

### GET /api/v1/status

Returns discovery status and cable summary.

**Response**:

```json
{
  "policy_name": "site-dc1-discovery",
  "status": "complete",
  "last_discovery_time": "2026-05-11T14:30:00Z",
  "devices": {
    "discovered": 2,
    "created": 2,
    "skipped": 0,
    "failed": 0
  },
  "cables": {
    "discovered": 3,
    "candidates": 3,
    "created": 2,
    "skipped": 0,
    "unresolvable": 1,
    "ingestion_disabled": false,
    "skip_entries": [
      {
        "local_device": "switch2",
        "local_interface": "Gi0/1",
        "neighbor_hostname": "unknown-box",
        "reason": "neighbor_device_not_found"
      }
    ]
  }
}
```

### POST /api/v1/discover

Run discovery in review mode (hold results for approval).

**Request**:

```yaml
# YAML policy format (same as /api/v1/policies)
```

**Response**:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "policy_name": "site-dc1-discovery",
  "status": "ready"
}
```

### GET /api/v1/reviews/{session_id}

Retrieve review session details (devices + cables).

### PATCH /api/v1/reviews/{session_id}/cables/{index}

Approve or reject a cable candidate.

**Request**:

```json
{
  "status": "accepted" | "rejected"
}
```

### POST /api/v1/reviews/{session_id}/ingest

Ingest approved cables (and devices) to NetBox.

**Response**:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ingested",
  "cables_created": 2,
  "cables_skipped": 0
}
```

---

## Testing & Validation

### Unit Test: Cable Resolution

```bash
pytest -xvs orbweaver/tests/test_cables_resolve.py
```

### Integration Test: Full Workflow

```bash
pytest -xvs orbweaver/tests/test_cables_integration.py
```

### Manual End-to-End Test

1. Prepare policy with 2–3 switches
2. Run direct discovery: `curl -X POST .../api/v1/policies`
3. Verify cables in NetBox
4. Run again; verify idempotency
5. Delete one cable manually from NetBox
6. Run discovery again; verify cable is re-created

---

## Best Practices

✅ **Do:**
- Enable cable discovery in non-production environments first (test/lab)
- Review cables in UI before approving large batches (> 50 cables)
- Check NetBox interface names match LLDP advertisements (avoid mismatches)
- Run discovery repeatedly to validate idempotency
- Monitor cable creation logs for warnings/errors

❌ **Don't:**
- Create duplicate cables manually while auto-discovery is enabled
- Modify auto-created cable endpoints (NetBox will reject duplicate on next discovery)
- Run concurrent discovery policies against overlapping device scopes (may cause conflicts)
- Delete all cables to "reset" — instead, disable cable ingestion and manually clean up NetBox

---

## Support & Troubleshooting

For issues, check:

1. Backend logs: `just backend-logs | grep cable`
2. NetBox API logs: Check NetBox container logs
3. Review UI console: Check browser dev tools for errors
4. Policy YAML: Validate syntax and device connectivity

For persistent issues, collect:
- `discovery_result.cable_summary` JSON
- Last 50 lines of backend logs
- List of devices and interfaces in NetBox

---

**Status**: ✅ Quickstart Complete  
**Ready for**: User adoption & feedback
