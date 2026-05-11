# Contract: Cable Ingestion

**Module**: `orbweaver/cables/ingest.py`  
**Purpose**: Create/skip cables in NetBox via pynetbox REST API  
**Modes**: Direct (PolicyRunner) and Review-Mode (ReviewStore)

---

## Overview

The cable ingestion module handles writing `CableCandidate` objects to NetBox. It:

1. Filters candidates by confidence and approval status
2. Checks NetBox for existing cables (by endpoint matching)
3. Creates new cables via pynetbox
4. Handles NetBox API errors with atomic rollback
5. Returns updated `CableResolutionSummary` with created/skipped counts

---

## Function Signatures

### ingest_cables_direct()

```python
async def ingest_cables_direct(
    candidates: list[CableCandidate],
    netbox_client: pynetbox.api,
    write_enabled: bool = True,
    dry_run: bool = False,
) -> CableResolutionSummary:
    """
    Create/skip cables in NetBox based on CableCandidate list.
    
    Direct mode: Called by PolicyRunner during discovery post-processing.
    
    Args:
        candidates: List of CableCandidate objects from resolution algorithm.
                   Only writable candidates (confidence != UNRESOLVABLE) will be processed.
        
        netbox_client: pynetbox.api instance (e.g., from _pynetbox_client()).
                      If None, operation is skipped (logged as warning) and
                      summary.ingestion_error is set; returns summary with
                      created=0, skipped=0.
        
        write_enabled: If False, cables are not written to NetBox (feature flag).
                      Summary will have ingestion_disabled=True; created=0.
        
        dry_run: If True, simulate cable creation without writing to NetBox.
                 Useful for testing and validation.
    
    Returns:
        CableResolutionSummary with updated created/skipped counts and any errors.
    
    Raises:
        No exceptions are raised. All errors are captured in summary.ingestion_error.
        On complete failure, all cables are rolled back (see Atomicity section).
    
    Algorithm:
        1. Filter candidates: only confidence != UNRESOLVABLE
        2. For each candidate:
           a. Check if cable already exists in NetBox (by endpoint matching)
           b. If exists: increment skipped; add skip entry to summary
           c. If not exists: queue for creation
        3. Begin transaction (conceptual; NetBox has no native transaction support)
        4. For each queued cable:
           a. Create cable via netbox_client.dcim.cables.create()
           b. On success: increment created
           c. On failure: log error; rollback all previously created cables (see Atomicity)
        5. Return updated summary
    """
```

**Signature for `ingest_cables_from_review()`:**

```python
async def ingest_cables_from_review(
    approved_candidates: list[CableCandidate],
    netbox_client: pynetbox.api,
    write_enabled: bool = True,
) -> CableResolutionSummary:
    """
    Create only approved cables from review session.
    
    Review mode: Called after operator approves cables in UI.
    
    Args:
        approved_candidates: CableCandidate objects with status=ACCEPTED (pre-filtered).
        netbox_client: pynetbox.api instance.
        write_enabled: Feature flag for cable ingestion.
    
    Returns:
        CableResolutionSummary with created/skipped counts.
    
    Implementation:
        Simply delegates to ingest_cables_direct() with the filtered list.
    """
```

---

## NetBox API Contract

### Cable Creation

**Endpoint**: `POST /api/dcim/cables/`

**Payload**:

```json
{
  "termination_a_type": "dcim.interface",
  "termination_a_id": 123,
  "termination_b_type": "dcim.interface",
  "termination_b_id": 456,
  "label": "LLDP auto-discovered",
  "description": "",
  "color": "0091da",
  "status": "connected"
}
```

**Response** (201 Created):

```json
{
  "id": 789,
  "termination_a": {
    "name": "GigabitEthernet0/1",
    "device": {
      "name": "switch1"
    }
  },
  "termination_b": {
    "name": "GigabitEthernet0/1",
    "device": {
      "name": "switch2"
    }
  },
  "label": "LLDP auto-discovered",
  "status": {
    "value": "connected",
    "label": "Connected"
  }
}
```

### Cable Lookup (for Idempotency)

**Endpoint**: `GET /api/dcim/cables/?limit=0`

**Query Parameters**: No direct filter by endpoint pair; must iterate and compare.

**Response**: List of all cables; client filters by endpoint device+interface names.

### Device Lookup (for Resolving Interface IDs)

**Endpoint**: `GET /api/dcim/devices/?name={device_name}`

**Response**:

```json
{
  "results": [
    {
      "id": 1,
      "name": "switch1"
    }
  ]
}
```

### Interface Lookup (for Resolving Interface IDs)

**Endpoint**: `GET /api/dcim/interfaces/?device__name={device_name}&name={interface_name}`

**Response**:

```json
{
  "results": [
    {
      "id": 123,
      "name": "GigabitEthernet0/1",
      "device": {
        "id": 1,
        "name": "switch1"
      }
    }
  ]
}
```

---

## Implementation Flow

### Direct Mode

```
ingest_cables_direct(candidates, netbox_client, write_enabled=True)
    ↓
[if not write_enabled]
    summary.ingestion_disabled = True
    return summary (with created=0)
    ↓
[if not netbox_client]
    summary.ingestion_error = "NetBox client not configured"
    return summary (with created=0)
    ↓
filter_writable = [c for c in candidates if c.is_writable]
    ↓
FOR each candidate:
    ├─ lookup_device_a = netbox_client.dcim.devices.get(name=candidate.cable.device_a_name)
    ├─ lookup_interface_a = netbox_client.dcim.interfaces.filter(
    │                         device_id=lookup_device_a.id,
    │                         name=candidate.cable.interface_a_name
    │                       )
    │
    ├─ [same for device_b / interface_b]
    │
    ├─ check_existing_cable()
    │   └─ [query all cables; compare endpoints]
    │
    ├─ [if exists]
    │   summary.skipped += 1
    │   summary.skip_entries.append(CableSkipEntry(..., reason="already_exists"))
    │   continue
    │
    └─ [if not exists]
        queue_for_creation(candidate, interface_a.id, interface_b.id)
    ↓
[BEGIN error handling transaction]
    ↓
FOR each queued_cable:
    └─ TRY
        ├─ netbox_client.dcim.cables.create(
        │     termination_a_type="dcim.interface",
        │     termination_a_id=interface_a_id,
        │     termination_b_type="dcim.interface",
        │     termination_b_id=interface_b_id,
        │     label="LLDP auto-discovered",
        │     status="connected"
        │   )
        ├─ log: "Created cable: {device_a}:{interface_a} ↔ {device_b}:{interface_b}"
        ├─ summary.created += 1
        │
        EXCEPT Exception as e:
        ├─ log ERROR: "Cable creation failed: {e}"
        ├─ summary.ingestion_error = str(e)
        │
        ├─ [ATOMIC ROLLBACK: delete all created cables]
        │   FOR each created_cable_id in created_so_far:
        │     └─ netbox_client.dcim.cables.delete(created_cable_id)
        │        log: "Rolled back cable {created_cable_id}"
        │
        ├─ summary.created = 0  # Reset to reflect rollback
        └─ RETURN summary (with error set)
    ↓
RETURN summary (success)
```

### Review Mode

```
ingest_cables_from_review(approved_candidates, netbox_client, write_enabled=True)
    ↓
[Simply call ingest_cables_direct()]
return ingest_cables_direct(approved_candidates, netbox_client, write_enabled)
```

---

## Atomicity & Error Handling

### Atomic Rollback

If any cable creation fails during the write phase, all successfully created cables are deleted and `summary.created` is reset to 0. This ensures idempotent behavior: a failed run leaves NetBox in the same state as before the run started.

**Implementation**:

```python
async def ingest_cables_direct(...):
    created_cable_ids = []
    
    try:
        for queued_cable in queued:
            cable_obj = netbox_client.dcim.cables.create(...)
            created_cable_ids.append(cable_obj.id)
            summary.created += 1
            
    except Exception as e:
        # Rollback all created cables
        for cable_id in created_cable_ids:
            try:
                netbox_client.dcim.cables.delete(cable_id)
                logger.info(f"Rolled back cable {cable_id}")
            except Exception as rollback_error:
                logger.error(f"Failed to rollback cable {cable_id}: {rollback_error}")
        
        summary.created = 0
        summary.ingestion_error = str(e)
        return summary
    
    return summary
```

### Error Categories

| Error | Status Code | Handling | Recovery |
|---|---|---|---|
| Device not found | 404 | Log warning; skip cable | Operator checks NetBox device names |
| Interface not found | 404 | Log warning; skip cable | Operator checks NetBox interface names |
| Duplicate cable (409 Conflict) | 409 | Treat as "already exists"; increment skipped | Safe due to DB constraints; counts as idempotent skip |
| NetBox API timeout | Connection error | Log error; rollback all created; fail run | Retry on next discovery run |
| NetBox authentication error | 401 | Log error; fail run | Check NETBOX_TOKEN env var |
| NetBox API rate limit | 429 | Log error; implement exponential backoff retry | Wait and retry (3x) |

### Error Logging

```
[ERROR] Cable creation failed for switch1:Gi0/1 ↔ switch2:Gi0/1: 404 Device not found
[ERROR] Rolling back 2 previously created cables due to error
[ERROR] Cable creation complete: 3 created, 2 skipped, 1 failed (error: 404 Device not found)
```

---

## Idempotency

**Guarantee**: Running the same discovery policy N times produces the same NetBox state as running it once.

**Implementation**:

1. **Before write**: Check NetBox for existing cables by endpoint matching (not by label or ID)
2. **Existing cables**: Skip without modification (preserve operator's cable metadata)
3. **Atomic rollback**: If write fails, no partial state is left in NetBox
4. **Repeated runs**: Second run finds cables from first run; skips them (increments skipped count)

**Test Case**:

```python
# Run 1: Creates 3 cables
summary1 = ingest_cables_direct(candidates, netbox_client)
assert summary1.created == 3
assert summary1.skipped == 0

# Run 2: Finds existing cables; skips
summary2 = ingest_cables_direct(candidates, netbox_client)
assert summary2.created == 0
assert summary2.skipped == 3

# Run 3: Same result as Run 2
summary3 = ingest_cables_direct(candidates, netbox_client)
assert summary3.created == 0
assert summary3.skipped == 3

# NetBox state unchanged across all runs
```

---

## pynetbox Usage Patterns

### Connect to NetBox

```python
import pynetbox
import os

def _pynetbox_client() -> pynetbox.api | None:
    """Build pynetbox client from environment variables."""
    host = os.environ.get("NETBOX_HOST", "").strip()
    port = os.environ.get("NETBOX_PORT", "8000").strip()
    token = os.environ.get("NETBOX_TOKEN", "").strip()
    
    if not host or not token:
        return None
    
    return pynetbox.api(f"http://{host}:{port}", token=token)
```

### Query Devices

```python
devices = netbox_client.dcim.devices.filter(name="switch1")
if devices:
    device = devices[0]
    print(device.id, device.name)
```

### Query Interfaces

```python
interfaces = netbox_client.dcim.interfaces.filter(
    device_id=device.id,
    name="GigabitEthernet0/1"
)
if interfaces:
    interface = interfaces[0]
    print(interface.id, interface.name, interface.device.name)
```

### Create Cable

```python
cable = netbox_client.dcim.cables.create(
    termination_a_type="dcim.interface",
    termination_a_id=interface_a.id,
    termination_b_type="dcim.interface",
    termination_b_id=interface_b.id,
    label="LLDP auto-discovered",
    status="connected"
)
print(f"Created cable {cable.id}")
```

### Query All Cables

```python
cables = list(netbox_client.dcim.cables.all())
for cable in cables:
    print(f"{cable.termination_a_device.name}:{cable.termination_a_interface.name} "
          f"↔ {cable.termination_b_device.name}:{cable.termination_b_interface.name}")
```

### Delete Cable

```python
netbox_client.dcim.cables.delete(cable.id)
```

---

## Configuration

### Environment Variables

```bash
NETBOX_HOST=netbox.example.com       # Required for cable ingestion
NETBOX_PORT=8000                     # Default
NETBOX_TOKEN=abcd1234efgh5678        # Required; must have dcim.add_cable permission
ORBWEAVER_CABLES_ENABLED=true        # Default; set false to disable
```

### Policy YAML

```yaml
config:
  cables_enabled: true               # Override env var (optional)
```

---

## Testing Patterns

### Unit Test: Cable Creation

```python
@pytest.mark.asyncio
async def test_ingest_cables_creates_new_cable(mocker):
    """Test that new cables are created in NetBox."""
    candidate = CableCandidate(
        cable=NormalizedCable(
            device_a_name="switch1",
            interface_a_name="Gi0/1",
            device_b_name="switch2",
            interface_b_name="Gi0/1"
        ),
        confidence=ResolutionConfidence.CONFIRMED,
        device_a_discovered=True,
        device_b_discovered=True
    )
    
    # Mock netbox_client
    mock_client = MagicMock()
    mock_client.dcim.devices.filter.side_effect = [
        [MagicMock(id=1, name="switch1")],  # device_a
        [MagicMock(id=2, name="switch2")]   # device_b
    ]
    mock_client.dcim.interfaces.filter.side_effect = [
        [MagicMock(id=101, name="Gi0/1", device=MagicMock(id=1))],  # interface_a
        [MagicMock(id=201, name="Gi0/1", device=MagicMock(id=2))]   # interface_b
    ]
    mock_client.dcim.cables.create.return_value = MagicMock(id=999)
    
    summary = await ingest_cables_direct([candidate], mock_client)
    
    assert summary.created == 1
    assert summary.skipped == 0
    mock_client.dcim.cables.create.assert_called_once()
```

### Integration Test: Idempotency

```python
@pytest.mark.asyncio
async def test_ingest_cables_idempotent(netbox_live_client):
    """Test that repeated ingest produces same state."""
    candidates = [...]  # realistic candidates from resolve_cables()
    
    # Run 1
    summary1 = await ingest_cables_direct(candidates, netbox_live_client)
    cable_count_1 = len(list(netbox_live_client.dcim.cables.all()))
    
    # Run 2
    summary2 = await ingest_cables_direct(candidates, netbox_live_client)
    cable_count_2 = len(list(netbox_live_client.dcim.cables.all()))
    
    assert cable_count_1 == cable_count_2  # Same cable count
    assert summary2.created == 0            # No new cables
    assert summary2.skipped == summary1.created  # All cables skipped
```

---

## Appendix: Cable Label and Metadata

### Suggested Fields

| Field | Value | Rationale |
|---|---|---|
| `label` | `"LLDP auto-discovered"` | Identifies auto-created cables; helps operators filter |
| `description` | `""` (empty) | Reserved for operator notes; we don't populate |
| `status` | `"connected"` | Indicates cable is active (not planned, decommissioned) |
| `color` | `"0091da"` (NetBox default blue) | Optional; makes auto-cables visually distinct |

### Optional Future Enhancement

Store LLDP metadata as custom fields (NetBox 3.5+):

```json
{
  "custom_fields": {
    "lldp_discovery_date": "2026-05-11T14:30:00Z",
    "lldp_discovery_policy": "site-dc1-discovery",
    "lldp_local_chassis_mac": "aa:bb:cc:dd:ee:00",
    "lldp_remote_chassis_mac": "aa:bb:cc:dd:ee:ff"
  }
}
```

---

**Status**: ✅ Contract Complete  
**Ready for**: Implementation
