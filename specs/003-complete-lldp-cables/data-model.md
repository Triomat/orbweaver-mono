# Data Model: LLDP Cable Discovery and Resolution

**Last Updated**: 2026-05-11

## Overview

This document details the data model extensions required to support LLDP cable discovery, resolution, and ingestion into NetBox. The design builds on the existing Common Object Model (COM) and integrates with the review workflow.

---

## New COM Dataclasses

### 1. ResolutionConfidence (Enum)

Confidence tier for cable endpoint matching.

```python
from enum import Enum

class ResolutionConfidence(str, Enum):
    """Confidence tier for cable resolution."""
    
    CONFIRMED = "confirmed"
    """Both endpoints discovered in current run with bidirectional LLDP match on hostname + interface."""
    
    PARTIAL = "partial"
    """
    One of:
    - One-sided LLDP discovery (only A sees B, not vice versa)
    - Hostname-only match (no interface normalization possible)
    - One endpoint resolved against existing NetBox inventory (not in current discovery)
    """
    
    UNRESOLVABLE = "unresolvable"
    """Skipped due to missing neighbor device, interface name mismatch, or other validation error."""
```

### 2. CableCandidate (Dataclass)

Intermediate representation of a resolved cable with confidence tier and provenance.

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class CableCandidate:
    """
    Resolved cable with confidence tier and discovery provenance.
    
    Represents a cable candidate after LLDP neighbor resolution but before NetBox write.
    Includes metadata for operator review and skip tracking.
    """
    
    # Core resolved cable
    cable: NormalizedCable
    """The endpoint pair that will (or will not) be written to NetBox."""
    
    # Resolution confidence and provenance
    confidence: ResolutionConfidence
    """Confidence tier based on discovery scope and match types."""
    
    device_a_discovered: bool
    """True if device_a was discovered in the current run; False if resolved from existing NetBox."""
    
    device_b_discovered: bool
    """True if device_b was discovered in the current run; False if resolved from existing NetBox."""
    
    # Skip reason (only populated if confidence == UNRESOLVABLE)
    skip_reason: Optional[str] = None
    """
    Reason code for unresolvable candidates. Examples:
    - "neighbor_device_not_found"
    - "interface_name_mismatch"
    - "one_sided_neighbor"
    - "ambiguous_chassis_mac"
    - "self_loop_detected"
    - "already_exists"
    """
    
    # Debug context
    lldp_neighbor: Optional[NormalizedLLDPNeighbor] = None
    """Original LLDP neighbor that triggered this cable candidate (for debugging)."""
    
    resolution_notes: str = ""
    """Human-readable resolution steps (e.g., 'Hostname match on switch1; interface normalized Gi0/1 → GigabitEthernet0/1')."""
    
    # For review UI: which direction was the LLDP neighbor discovered?
    # (Helpful for understanding one-sided neighbors)
    lldp_direction: str = ""
    """
    Direction of LLDP neighbor advertisement:
    - "bidirectional": A sees B and B sees A
    - "a_to_b": Only A advertises B
    - "b_to_a": Only B advertises A
    """
    
    @property
    def is_writable(self) -> bool:
        """True if cable should be written to NetBox (not unresolvable)."""
        return self.confidence in (ResolutionConfidence.CONFIRMED, ResolutionConfidence.PARTIAL)
```

### 3. CableSkipEntry (Dataclass)

Detail record for a skipped cable candidate.

```python
from dataclasses import dataclass

@dataclass
class CableSkipEntry:
    """
    Detailed skip information for a single cable candidate.
    
    Exposed to operators for visibility into why cables were not created.
    """
    
    local_device: str
    """Device name on the side that discovered the LLDP neighbor."""
    
    local_interface: str
    """Interface name on the local side."""
    
    neighbor_hostname: str
    """Hostname advertised in LLDP by the remote device."""
    
    reason: str
    """
    Reason code. Standard values:
    - "neighbor_device_not_found": Advertised hostname not found in NetBox or discovery
    - "interface_name_mismatch": Remote interface name could not be matched after normalization
    - "one_sided_neighbor": Only local device advertises remote, not vice versa
    - "ambiguous_chassis_mac": Chassis MAC matches multiple devices
    - "self_loop_detected": Device advertising itself
    - "already_exists": Cable already in NetBox (skipped, not failed)
    - "ingestion_disabled": Cable ingestion disabled by feature flag
    """
    
    neighbor_interface: str = ""
    """Remote interface name advertised in LLDP (if available)."""
    
    neighbor_chassis_mac: str = ""
    """Remote device chassis MAC (for MAC-based matching lookup)."""
    
    neighbor_mgmt_ip: str = ""
    """Management IP advertised in LLDP (for context)."""
```

### 4. CableResolutionSummary (Dataclass)

Aggregated counters and per-skip details from a discovery run.

```python
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class CableResolutionSummary:
    """
    Aggregated outcome of cable resolution for a single discovery run.
    
    Returned by the cable resolution module and exposed in discovery responses
    and review session summaries. Provides operator-facing observability into
    cable discovery outcomes.
    """
    
    # Counters: resolution pipeline
    discovered: int = 0
    """Total LLDP neighbor advertisements found across all discovered devices."""
    
    candidates: int = 0
    """Cable candidates generated from LLDP neighbors (before filtering/validation)."""
    
    # Counters: write outcome
    created: int = 0
    """Cables successfully written to NetBox (confirmed + approved partial candidates)."""
    
    skipped: int = 0
    """
    Cables not written because they already exist in NetBox.
    These are idempotent skips (safe to repeat).
    """
    
    unresolvable: int = 0
    """
    Candidates that failed resolution (missing device, interface mismatch, etc.).
    These are failure cases; operator should review skip reasons.
    """
    
    # Detailed skip entries
    skip_entries: List[CableSkipEntry] = field(default_factory=list)
    """
    Detailed records for skipped and unresolvable candidates.
    Operators can drill down into skip_entries to understand why each cable was not created.
    """
    
    # Feature flag state
    ingestion_disabled: bool = False
    """True if cable ingestion was disabled (feature flag or policy config)."""
    
    # Error state
    ingestion_error: Optional[str] = None
    """
    NetBox API error message, if any. Non-None indicates partial or complete failure
    during cable write (with atomic rollback).
    """
    
    # Metadata
    resolution_duration_ms: float = 0.0
    """Time (in milliseconds) to resolve cables from LLDP neighbors."""
    
    ingestion_duration_ms: float = 0.0
    """Time (in milliseconds) to write cables to NetBox."""
```

---

## COM Integration: DiscoveryResult

Extend [DiscoveryResult](orbweaver/models/common.py) to include cable candidates and resolution metadata.

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

@dataclass
class DiscoveryResult:
    """
    Aggregated output of a single discovery run.
    
    Includes devices, VLANs, prefixes, and now cable candidates.
    """
    
    # Existing fields
    devices: List[NormalizedDevice] = field(default_factory=list)
    vlans: List[NormalizedVLAN] = field(default_factory=list)
    prefixes: List[NormalizedPrefix] = field(default_factory=list)
    cables: List[NormalizedCable] = field(default_factory=list)
    sites: List[NormalizedSite] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    vendor: str = ""
    errors: List[str] = field(default_factory=list)
    
    # NEW: Cable resolution artifacts
    cable_candidates: List[CableCandidate] = field(default_factory=list)
    """
    Intermediate cable candidates before write.
    
    Populated after cable resolution step. Includes candidates that will be
    written (confidence != UNRESOLVABLE) and those that won't, with reasons.
    Used by review workflow to display cable candidates for operator approval.
    """
    
    cable_summary: Optional[CableResolutionSummary] = None
    """
    Aggregated cable resolution outcome.
    
    Populated after cable resolution + ingestion. Contains counters and per-skip
    details for operator visibility.
    """
    
    # ... existing methods ...
```

---

## Review Workflow Integration

### ReviewSession Extension

Extend [ReviewSession](orbweaver/review/models.py) to include cable candidates alongside device candidates.

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime, timezone

class ReviewSession(BaseModel):
    """
    Holds discovery results for operator review before NetBox ingest.
    """
    
    # Existing fields
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    policy_name: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: ReviewStatus = ReviewStatus.PENDING
    defaults: Dict = Field(default_factory=dict)
    
    # Existing review items (devices, VLANs, prefixes)
    devices: List[ReviewItem] = Field(default_factory=list)
    
    # NEW: Cable review items
    cables: List[ReviewItem] = Field(default_factory=list)
    """
    Serialized CableCandidate objects with review status (pending/accepted/rejected).
    
    Each item.data field contains:
    {
        "cable": {...},              # NormalizedCable (serialized)
        "confidence": "confirmed",   # ResolutionConfidence
        "device_a_discovered": true,
        "device_b_discovered": true,
        "skip_reason": null,
        "lldp_neighbor": {...},
        "resolution_notes": "...",
        "lldp_direction": "bidirectional"
    }
    """
    
    # NEW: Cable resolution summary
    cable_summary: Optional[Dict] = None
    """
    Serialized CableResolutionSummary containing counters and skip details.
    
    Example:
    {
        "discovered": 6,
        "candidates": 5,
        "created": 0,  # 0 because not yet ingested (review mode)
        "skipped": 0,
        "unresolvable": 1,
        "skip_entries": [
            {
                "local_device": "switch1",
                "local_interface": "Gi0/1",
                "neighbor_hostname": "unknown-switch",
                "reason": "neighbor_device_not_found"
            }
        ],
        "ingestion_disabled": false,
        "ingestion_error": null,
        "resolution_duration_ms": 42.5,
        "ingestion_duration_ms": 0
    }
    """
    
    error: Optional[str] = None
    
    # ... existing methods ...
    
    @property
    def summary(self) -> Dict:
        """Lightweight dict for list views."""
        return {
            "id": self.id,
            "policy_name": self.policy_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "device_count": len(self.devices),
            "cable_count": len(self.cables),  # NEW
            "accepted_devices": sum(1 for d in self.devices if d.status == ItemStatus.ACCEPTED),
            "accepted_cables": sum(1 for c in self.cables if c.status == ItemStatus.ACCEPTED),  # NEW
            "error": self.error,
        }
```

---

## Policy Configuration Extension

### Policy Cables Configuration

Extend [Policy.Config](backend/device_discovery/policy/models.py) to support cable ingestion control.

```python
from pydantic import BaseModel, Field
from typing import Optional

class PolicyDefaults(BaseModel):
    """Default values for all devices in a policy."""
    
    site: str
    role: str
    # ... existing fields ...
    
    cables_enabled: Optional[bool] = None
    """
    Enable/disable cable ingestion for all devices in policy.
    
    If not set, defaults to environment variable ORBWEAVER_CABLES_ENABLED (default: true).
    Per-device setting overrides this.
    """


class Napalm(BaseModel):
    """Configuration for a single device in policy scope."""
    
    hostname: str
    username: str
    password: str
    driver: Optional[str] = None
    collector: Optional[str] = None
    timeout: int = 60
    # ... existing fields ...
    
    cables_enabled: Optional[bool] = None
    """
    Per-device cable ingestion override.
    
    If not set, defaults to policy.config.defaults.cables_enabled.
    Allows granular control: disable cables for certain devices while enabling for others.
    """
```

**Example YAML:**

```yaml
policies:
  site-dc1:
    config:
      defaults:
        site: "DC1"
        role: "access-switch"
        cables_enabled: true  # Enable cables for all devices (or set globally)
    scope:
      - hostname: 192.168.1.1
        username: admin
        password: secret
        collector: cisco_ios
      - hostname: 192.168.1.2
        username: admin
        password: secret
        collector: cisco_ios
        cables_enabled: false  # Disable cables for this device only

  site-dc2:
    config:
      defaults:
        site: "DC2"
        role: "core-router"
        cables_enabled: false  # Disable cables for entire policy
    scope:
      - hostname: 10.0.0.1
        username: admin
        password: secret
        collector: cisco_ios
```

---

## Entity Relationships

```
                    NormalizedDevice
                          |
                          | contains
                          v
              NormalizedLLDPNeighbor (raw LLDP advertisements)
                          |
                          | (cable resolution algorithm)
                          v
                   CableCandidate
                    /          \
            (confidence tiers)   (skip reasons)
              /    |    \         |
         Confirmed Partial    Unresolvable
             |       |            |
             +-------+--------+---+
                     |
                     v
              NormalizedCable (if writable)
                     |
                     | (ingest step)
                     v
            NetBox Cable Entity


          ReviewSession
             /        \
      devices[]    cables[]  ← NEW
         |             |
    ReviewItem   ReviewItem  ← Includes CableCandidate (serialized)
         |             |
         v             v
    [device_dict] [cable_dict]
```

---

## Serialization Contracts

### CableCandidate → JSON (for ReviewItem.data)

```json
{
  "cable": {
    "device_a_name": "switch1",
    "interface_a_name": "GigabitEthernet0/1",
    "device_b_name": "switch2",
    "interface_b_name": "GigabitEthernet0/1",
    "label": "LLDP auto-discovered",
    "description": "",
    "color": ""
  },
  "confidence": "confirmed",
  "device_a_discovered": true,
  "device_b_discovered": true,
  "skip_reason": null,
  "lldp_neighbor": {
    "local_interface": "GigabitEthernet0/1",
    "neighbor_device_name": "switch2",
    "neighbor_interface": "GigabitEthernet0/1",
    "neighbor_chassis_mac": "aa:bb:cc:dd:ee:ff",
    "neighbor_mgmt_ip": "10.0.0.2",
    "neighbor_system_description": "Cisco IOS..."
  },
  "resolution_notes": "Bidirectional hostname match; interfaces normalized successfully",
  "lldp_direction": "bidirectional"
}
```

### CableResolutionSummary → JSON (for ReviewSession.cable_summary)

```json
{
  "discovered": 6,
  "candidates": 5,
  "created": 3,
  "skipped": 2,
  "unresolvable": 1,
  "skip_entries": [
    {
      "local_device": "switch1",
      "local_interface": "GigabitEthernet0/1",
      "neighbor_hostname": "unknown-switch",
      "reason": "neighbor_device_not_found",
      "neighbor_interface": "Gi0/1",
      "neighbor_chassis_mac": "aa:bb:cc:dd:ee:00",
      "neighbor_mgmt_ip": ""
    },
    {
      "local_device": "switch2",
      "local_interface": "GigabitEthernet0/2",
      "neighbor_hostname": "switch3",
      "reason": "already_exists",
      "neighbor_interface": "Gi0/2",
      "neighbor_chassis_mac": "aa:bb:cc:dd:ee:11",
      "neighbor_mgmt_ip": "10.0.0.3"
    }
  ],
  "ingestion_disabled": false,
  "ingestion_error": null,
  "resolution_duration_ms": 42.5,
  "ingestion_duration_ms": 125.3
}
```

---

## Data Flow: Direct Discovery Mode

```
PolicyRunner.discover()
    ↓
Collectors (NAPALM + Cisco/Aruba enrichment)
    ↓
DiscoveryResult (with devices + LLDP neighbors)
    ↓
cable_resolve.resolve_cables()
    ├─ normalize hostnames, interface names, chassis MACs
    ├─ match neighbors against discovered + existing devices
    ├─ deduplicate bidirectionally
    ├─ check existing NetBox cables
    └─ populate CableCandidate list + CableResolutionSummary
    ↓
DiscoveryResult.cable_candidates[]
DiscoveryResult.cable_summary
    ↓
[if cables_enabled] cable_ingest.ingest_cables_direct()
    ├─ filter writable candidates (confidence != UNRESOLVABLE)
    ├─ check NetBox for existing cables (skip if found)
    ├─ write new cables via pynetbox
    └─ update cable_summary with created/skipped counts
    ↓
diode_translate.translate() [unchanged]
    ↓
Diode SDK ingest (devices, VLANs, IPs)
    ↓
NetBox (devices + cables)
```

---

## Data Flow: Review Mode

```
run_discovery_for_review()
    ↓
[same as direct mode up to cable resolution]
    ↓
cable_resolve.resolve_cables()
    ↓
CableCandidate[] + CableResolutionSummary
    ↓
ReviewSession.cables[] ← serialized CableCandidate objects
ReviewSession.cable_summary ← serialized summary
    ↓
ReviewStore.save(session)
    ↓
[operator reviews in UI]
    ↓
POST /api/v1/reviews/{id}/ingest
    ├─ load session
    ├─ filter cable items by ItemStatus.ACCEPTED
    ├─ reconstruct CableCandidate objects
    ├─ cable_ingest.ingest_cables_from_review()
    │   └─ [same write logic as direct mode]
    └─ continue with device ingest
    ↓
NetBox (cables + devices)
```

---

## Backward Compatibility

- **Existing DiscoveryResult**: New fields (`cable_candidates`, `cable_summary`) are optional; old code ignores them
- **Existing ReviewSession**: New fields (`cables`, `cable_summary`) are optional; old UI still works (just doesn't display cables)
- **Existing policies**: No `cables_enabled` field → defaults to environment variable (default: true); backward compatible
- **Existing collectors**: No changes required; LLDP neighbors already populated

---

## Testing Data Model

### Unit Test: CableCandidate Serialization

```python
def test_cable_candidate_serialization():
    candidate = CableCandidate(
        cable=NormalizedCable(
            device_a_name="switch1",
            interface_a_name="Gi0/1",
            device_b_name="switch2",
            interface_b_name="Gi0/1"
        ),
        confidence=ResolutionConfidence.CONFIRMED,
        device_a_discovered=True,
        device_b_discovered=True,
        lldp_direction="bidirectional"
    )
    
    # Serialize to dict
    data = dataclasses.asdict(candidate)
    
    # Verify all fields present and JSON-serializable
    assert data["cable"]["device_a_name"] == "switch1"
    assert data["confidence"] == "confirmed"
    assert json.dumps(data)  # Must not raise
```

### Unit Test: ReviewSession Cable Integration

```python
def test_review_session_with_cables():
    session = ReviewSession(
        policy_name="test-policy",
        cables=[
            ReviewItem(
                index=0,
                status=ItemStatus.PENDING,
                data={
                    "cable": {...},
                    "confidence": "confirmed",
                    "device_a_discovered": True,
                    "device_b_discovered": True
                }
            )
        ]
    )
    
    summary = session.summary
    assert summary["cable_count"] == 1
    assert summary["accepted_cables"] == 0
    
    session.cables[0].status = ItemStatus.ACCEPTED
    assert session.summary["accepted_cables"] == 1
```

---

**Status**: ✅ Design Complete  
**Ready for**: Implementation (Phase 1–3)
