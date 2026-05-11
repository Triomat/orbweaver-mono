# Implementation Plan: Complete LLDP Cable Discovery and NetBox Ingestion

**Branch**: `feature/003-complete-lldp-cables`  
**Status**: Ready for Implementation  
**Last Updated**: 2026-05-11

## Executive Summary

This plan details the implementation of end-to-end LLDP cable resolution and NetBox ingestion for orbweaver. The feature enables automated discovery of physical network topology from LLDP neighbor advertisements, with safe review-workflow integration, comprehensive observability, and strict idempotency guarantees.

---

## Technical Context

### Resolved Clarifications (Q1-Q6)

1. **Concurrent discovery runs**: Use NetBox database constraints (unique on device+interface pairs) to reject duplicate writes atomically
2. **NetBox unavailability**: Fail entire discovery run; roll back any successfully written cables; surface error to operator
3. **Confidence tiers**: Three-tier system (Confirmed, Partial, Unresolvable)
4. **Interface normalization**: Vendor-specific canonical mappings (Cisco, Aruba); if no match after expansion, mark unresolvable with `"interface_name_mismatch"`
5. **Cable updates**: Create-or-skip only; operators retain full control over cable metadata
6. **Cross-device resolution**: Match LLDP chassis MACs against both newly discovered devices AND existing NetBox inventory, enabling cables to span discovered-to-existing endpoints

### Architecture Context

```
orbweaver/
├── models/common.py              ← NormalizedDevice, NormalizedCable, NormalizedLLDPNeighbor
├── collectors/                    ← Cisco, Aruba producing NormalizedLLDPNeighbor
├── review/
│   ├── models.py                 ← ReviewSession, ReviewItem (to be extended for cables)
│   ├── discover.py               ← run_discovery_for_review() entry point
│   ├── rebuild.py                ← device_from_dict() deserialization
│   └── store.py                  ← ReviewStore persistence
├── cables/                        ← NEW
│   ├── resolve.py                ← cable resolution algorithm
│   ├── normalize.py              ← hostname/interface normalization
│   └── ingest.py                 ← NetBox cable creation via pynetbox
└── diode_translate.py            ← existing COM→Diode bridge

backend/
├── device_discovery/
│   ├── discovery.py              ← PolicyRunner (to patch with cable workflow)
│   └── translate.py              ← existing Diode translation
```

---

## Phase 1: Design

### 1.1 Data Model Extensions

**New COM Dataclass: CableCandidate**

Intermediate artifact representing a resolved cable with confidence tier and provenance.

```python
@dataclass
class CableCandidate:
    """Resolved cable with confidence tier and source provenance."""
    
    cable: NormalizedCable              # The resolved cable endpoint pair
    confidence: ResolutionConfidence    # Confirmed | Partial | Unresolvable
    
    # Provenance: which endpoints were discovered in this run vs. resolved from NetBox
    device_a_discovered: bool           # True if device_a is in current discovery
    device_b_discovered: bool           # True if device_b is in current discovery
    
    # Skip reason (only populated if confidence == Unresolvable)
    skip_reason: str | None = None      # e.g., "interface_name_mismatch", "neighbor_device_not_found"
    
    # Debug context
    lldp_neighbor: NormalizedLLDPNeighbor | None = None  # Original LLDP neighbor if known
    resolution_notes: str = ""          # Human-readable resolution steps (for logging)
```

**New Enum: ResolutionConfidence**

```python
class ResolutionConfidence(str, Enum):
    CONFIRMED = "confirmed"       # Both endpoints discovered in current run + bidirectional match
    PARTIAL = "partial"           # One-sided, hostname-only, or one endpoint from existing NetBox
    UNRESOLVABLE = "unresolvable" # Skipped with reason
```

**New Dataclass: CableResolutionSummary**

Aggregated counters and per-skip details from a discovery run.

```python
@dataclass
class CableResolutionSummary:
    """Aggregated output of cable resolution for a single discovery run."""
    
    discovered: int = 0                # Total LLDP neighbors found
    candidates: int = 0                # Cable candidates created (before filtering)
    created: int = 0                   # Cables actually written to NetBox (confirmed + some partial)
    skipped: int = 0                   # Cables not written (already in NetBox)
    unresolvable: int = 0              # Candidates that couldn't be resolved
    
    # Detailed skip entries for operator visibility
    skip_entries: list[CableSkipEntry] = field(default_factory=list)
    
    # Ingestion status
    ingestion_disabled: bool = False   # True if cable ingestion was disabled
    ingestion_error: str | None = None # NetBox API error message, if any
```

**New Dataclass: CableSkipEntry**

```python
@dataclass
class CableSkipEntry:
    """Detail entry for a skipped cable candidate."""
    
    local_device: str              # Device name on local discovery
    local_interface: str           # Interface name on local side
    neighbor_hostname: str         # Advertised neighbor hostname from LLDP
    reason: str                    # Reason code: "already_exists", "one_sided_neighbor", "interface_name_mismatch", etc.
    neighbor_interface: str = ""   # Remote interface name (if available)
    neighbor_chassis_mac: str = ""  # Remote chassis MAC (if available)
```

**ReviewSession Extension**

Add cable candidates to the existing review workflow:

```python
class ReviewSession(BaseModel):
    # ... existing fields ...
    devices: list[ReviewItem] = Field(default_factory=list)
    cables: list[ReviewItem] = Field(default_factory=list)  # NEW: cable candidates
    cable_summary: dict | None = None  # NEW: CableResolutionSummary serialized
```

### 1.2 DiscoveryResult Extension

Extend [DiscoveryResult](orbweaver/models/common.py) to include cable resolution:

```python
@dataclass
class DiscoveryResult:
    # ... existing fields ...
    devices: list[NormalizedDevice] = field(default_factory=list)
    vlans: list[NormalizedVLAN] = field(default_factory=list)
    prefixes: list[NormalizedPrefix] = field(default_factory=list)
    cables: list[NormalizedCable] = field(default_factory=list)  # Already present
    cable_candidates: list[CableCandidate] = field(default_factory=list)  # NEW: before write
    cable_summary: CableResolutionSummary | None = None  # NEW: aggregated outcome
```

### 1.3 Policy Configuration Extension

Extend [Policy](backend/device_discovery/policy/models.py) to support cable ingestion flag:

```yaml
policies:
  my-policy:
    config:
      defaults:
        site: "DC1"
        role: "access-switch"
        cables_enabled: true          # NEW: default is true; set false to disable cable ingestion
    scope:
      - hostname: 192.168.1.1
        username: admin
        password: secret
        collector: cisco_ios
        cables_enabled: false         # Per-device override (optional)
```

---

## Phase 2: Implementation Components

### 2.1 Cable Resolution Algorithm (`orbweaver/cables/resolve.py`)

**Inputs:**
- `DiscoveryResult` from collectors (contains newly discovered devices + LLDP neighbors)
- Optionally: live NetBox inventory (devices not in this discovery)

**Algorithm Steps:**

1. **Normalize all device identifiers** (hostnames, chassis MACs) in discovered devices
2. **For each LLDP neighbor** in each device:
   - Normalize neighbor hostname and chassis MAC
   - Attempt bidirectional device matching:
     - Match against newly discovered devices first (preferred for Confirmed tier)
     - Match against existing NetBox devices as fallback (for Partial tier)
   - Normalize interface names (vendor-specific expansion)
   - Check for self-loops, ambiguous MACs, one-sided neighbors
3. **Deduplicate bidirectionally** (ensure A→B and B→A produce one cable)
4. **Check NetBox for existing cables** (skip if already present)
5. **Assign confidence tiers** based on discovery scope and match types
6. **Aggregate skip reasons** into `CableResolutionSummary`

**Output:**
- `list[CableCandidate]` with metadata and skip reasons
- `CableResolutionSummary` with counters and skip details

See [contracts/cable-resolution.md](contracts/cable-resolution.md) for detailed algorithm spec.

### 2.2 Hostname/Interface Normalization (`orbweaver/cables/normalize.py`)

**Hostname normalization:**
- Strip domain suffixes (e.g., "switch1.example.com" → "switch1")
- Lowercase
- Trim whitespace

**Interface normalization:**
- Vendor-specific canonical expansion (Cisco "Gi0/1" → "GigabitEthernet0/1", Aruba "1/1" unchanged)
- Cached mapping: `{"Gi0/1": "GigabitEthernet0/1", ...}` per vendor/platform
- If no match found after expansion, return with mismatch reason

**Chassis MAC normalization:**
- Lowercase, remove separators (hyphens, colons) for matching
- Store original format for logging

### 2.3 Cable Ingestion (`orbweaver/cables/ingest.py`)

**Direct Mode (PolicyRunner):**

```python
async def ingest_cables_direct(
    candidates: list[CableCandidate],
    netbox_client: pynetbox.api,
    write_enabled: bool = True,
) -> CableResolutionSummary:
    """
    Create/skip cables in NetBox based on CableCandidate list.
    
    - Checks existing cables by endpoint matching (device + interface on both ends)
    - Skips if already exists (no update)
    - Writes confirmed + partial candidates (not unresolvable)
    - Atomic rollback on NetBox errors
    - Returns updated summary with created/skipped counts
    """
```

**Review Mode (ReviewStore):**

```python
async def ingest_cables_from_review(
    session: ReviewSession,
    netbox_client: pynetbox.api,
    write_enabled: bool = True,
) -> CableResolutionSummary:
    """
    Create only approved cables from review session.
    
    - Filters cable items by ItemStatus.ACCEPTED
    - Reconstructs CableCandidate from JSON
    - Calls ingest_cables_direct() with filtered list
    """
```

See [contracts/cable-ingestion.md](contracts/cable-ingestion.md) for NetBox API contract.

### 2.4 PolicyRunner Integration (`orbweaver/patches.py`)

Extend `PolicyRunner._collect_device_data()` to resolve and ingest cables:

```python
# Pseudo-code: existing logic + cable workflow

async def _collect_device_data(self, ...):
    # ... existing Napalm/Diode collection ...
    
    # NEW: Resolve cables from LLDP neighbors
    if self.ingestion_enabled:
        candidates = resolve_cables(discovery_result, netbox_client)
        discovery_result.cable_candidates = candidates
        
        # Write cables in direct mode
        summary = await ingest_cables_direct(candidates, netbox_client)
        discovery_result.cable_summary = summary
    
    # ... continue with existing Diode ingest ...
```

### 2.5 Review Workflow Integration

**Discovery phase:** `run_discovery_for_review()` already produces `DiscoveryResult` with LLDP neighbors.

**New:** Add cable resolution step in `run_discovery_for_review()`:

```python
def run_discovery_for_review(...) -> ReviewSession:
    # ... existing device discovery ...
    
    # NEW: Resolve cables
    candidates = resolve_cables(discovery_result, netbox_client)
    
    # Store cable candidates in session
    for idx, candidate in enumerate(candidates):
        session.cables.append(
            ReviewItem(
                index=idx,
                status=ItemStatus.PENDING,
                data=_to_dict(candidate)
            )
        )
    
    # Store cable summary
    session.cable_summary = _to_dict(summary)
```

**Ingest phase:** New endpoint `/api/v1/reviews/{id}/ingest` already handles device ingest.

**New:** Extend to handle cable ingest:

```python
async def ingest_review(session_id: str, ...):
    session = store.load(session_id)
    
    # Filter approved cables
    approved_cables = [
        item for item in session.cables
        if item.status == ItemStatus.ACCEPTED
    ]
    
    # Ingest approved cables
    summary = await ingest_cables_from_review(approved_cables, ...)
```

### 2.6 Feature Flag Control

**Environment variable:**
```bash
ORBWEAVER_CABLES_ENABLED=true   # Default; set false to disable
```

**Policy-level override:**
```yaml
config:
  cables_enabled: false  # Per-policy override
```

**Per-device override:**
```yaml
scope:
  - hostname: 192.168.1.1
    cables_enabled: false  # Per-device override
```

Check in order: per-device → per-policy → environment (default true).

---

## Phase 3: Integration Points

### 3.1 FastAPI Endpoint Extensions (`orbweaver/app.py`)

New endpoints for cable operations:

**GET /api/v1/cables/candidates**
- List all cable candidates from a given discovery run or review session
- Returns: `list[CableCandidate]` with confidence tier and skip reasons

**POST /api/v1/cables/resolve** (optional; for manual testing)
- Trigger cable resolution against a policy
- Returns: `CableResolutionSummary` with outcome

**PATCH /api/v1/reviews/{id}/cables/{index}**
- Accept/reject individual cable candidates
- Updates `session.cables[index].status`

### 3.2 Frontend UI Integration (`frontend/app/pages/reviews.vue`)

**New UI sections:**

1. **Cable Candidates Tab** (alongside Devices tab)
   - Table: Device A | Interface A | Device B | Interface B | Confidence | Action
   - Confidence indicators: green (Confirmed), yellow (Partial), gray (Unresolvable)
   - Reason tooltips on hover
   - Accept/Reject buttons per row
   - Bulk accept/reject actions

2. **Cable Summary Card**
   - Counter display: Discovered | Candidates | Created | Skipped | Unresolvable
   - Skip details modal: clickable expand for each skip reason

3. **Review Submit Button**
   - Clarified: "Ingest Devices and Cables" (shows counts)
   - Logs: "X devices + Y cables submitted to NetBox"

### 3.3 Test Coverage

**Unit tests** (`orbweaver/tests/cables/`):

- `test_hostname_normalization.py` — stripping, lowercasing, domain suffix removal
- `test_interface_normalization.py` — vendor-specific expansion, fallback handling
- `test_cable_resolution.py` — bidirectional matching, deduplication, confidence tiers
- `test_cable_deduplication.py` — A→B and B→A produce same cable
- `test_one_sided_neighbor_detection.py` — one-sided neighbors marked unresolvable
- `test_ambiguous_mac_detection.py` — same chassis MAC on multiple devices
- `test_self_loop_detection.py` — device advertising itself
- `test_cross_device_resolution.py` — matching against existing NetBox inventory
- `test_cable_idempotency.py` — repeated runs produce same state

**Integration tests** (`orbweaver/tests/test_cables_integration.py`):

- Discovery run with real (mocked) NetBox
- Cables created on first run, skipped on second run
- Cables deleted in NetBox, re-proposed on third run
- Review workflow: approve/reject cables, ingest subset
- Feature flag disabled: no cables written
- NetBox API error: atomic rollback of partially written cables

**Upstream compatibility:**

- Run existing `backend/tests/` suite to ensure no regressions
- Verify all device/VLAN/prefix tests still pass

---

## Phase 4: Observability & Error Handling

### 4.1 Logging

**Debug level:**
```
[DEBUG] Resolving 12 LLDP neighbors for device 'switch1'
[DEBUG] Neighbor 'switch2' (MAC aa:bb:cc:dd:ee:ff) matched to discovered device 'switch2'
[DEBUG] Interface 'Gi0/1' normalized to 'GigabitEthernet0/1'
[DEBUG] Cable candidate: switch1:GigabitEthernet0/1 ↔ switch2:GigabitEthernet0/2 (Confirmed)
```

**Info level:**
```
[INFO] Cable resolution complete: 6 discovered, 5 created, 1 skipped (already in NetBox)
[INFO] Created cable: switch1:Gi0/1 ↔ switch2:Gi0/2 in NetBox
```

**Warning level:**
```
[WARNING] Unresolvable cable: switch1:Gi0/1 → neighbor 'unknown-switch' (reason: neighbor_device_not_found)
[WARNING] One-sided LLDP: switch1 sees switch2, but switch2 does not see switch1 (reason: one_sided_neighbor)
```

**Error level:**
```
[ERROR] NetBox API error during cable ingestion: 500 Internal Server Error
[ERROR] Rolling back 3 successfully written cables due to API error
```

### 4.2 Metrics

Prometheus metrics (if metrics are in scope):

```
orbweaver_cables_discovered_total        # Counter: total LLDP neighbors found
orbweaver_cables_created_total           # Counter: cables written to NetBox
orbweaver_cables_skipped_total           # Counter: cables not written (already exist)
orbweaver_cables_unresolvable_total      # Counter: candidates that failed resolution
orbweaver_cable_ingestion_errors_total   # Counter: NetBox API errors
orbweaver_cable_ingestion_duration_ms    # Histogram: time to resolve and ingest
```

### 4.3 Error Handling

| Scenario | Behavior | Outcome |
|---|---|---|
| Neighbor device not found in NetBox | Mark unresolvable with `neighbor_device_not_found` | Visible in skip reasons; operator can review |
| Interface name mismatch after normalization | Try canonical expansion; if still no match, mark unresolvable with `interface_name_mismatch` | Operator can manually correct NetBox interface name |
| One-sided LLDP (only A sees B) | Mark unresolvable with `one_sided_neighbor` | Operator can review; can force-ingest if needed |
| Ambiguous chassis MAC (same MAC on 2+ devices) | Mark unresolvable with `ambiguous_chassis_mac` | Operator must resolve MAC conflict in NetBox |
| Self-loop (device sees itself) | Skip with `self_loop_detected` | Logged as warning; no cable created |
| NetBox API unavailable (direct mode) | Fail entire discovery run; roll back any written cables | Error message to operator; manual recovery needed |
| NetBox API 409 Conflict (duplicate write) | Catch exception; treat as "already exists"; increment skipped count | Safe due to database constraints; counted as idempotent skip |
| NetBox API timeout | Retry 3x with exponential backoff; if all fail, atomic rollback | Error to operator; retry on next run |

---

## Phase 5: Deliverables

### 5.1 Files to Create/Modify

**Create:**
- `orbweaver/cables/` (new module)
  - `__init__.py`
  - `resolve.py` — cable resolution algorithm
  - `normalize.py` — hostname/interface normalization
  - `ingest.py` — NetBox cable creation via pynetbox
  - `models.py` — `CableCandidate`, `CableResolutionSummary`, `CableSkipEntry`, `ResolutionConfidence`

**Modify:**
- `orbweaver/models/common.py` — extend `DiscoveryResult` with cable fields
- `orbweaver/review/models.py` — extend `ReviewSession` with cable fields
- `orbweaver/patches.py` — integrate cable workflow into `PolicyRunner`
- `orbweaver/app.py` — add cable resolution endpoints
- `orbweaver/review/discover.py` — resolve cables in `run_discovery_for_review()`
- `backend/device_discovery/policy/models.py` — add `cables_enabled` policy field (if not upstream)

**Tests to Create:**
- `orbweaver/tests/test_cables_resolve.py`
- `orbweaver/tests/test_cables_normalize.py`
- `orbweaver/tests/test_cables_ingest.py`
- `orbweaver/tests/test_cables_integration.py`
- `orbweaver/tests/test_review_cables.py`

**Frontend:**
- `frontend/app/pages/review/[id].vue` — extend to display cable candidates
- `frontend/app/composables/useReview.ts` — add cable filtering/approval logic
- `frontend/app/components/CableTable.vue` — new component for cable display

### 5.2 Success Criteria

✅ **SC-001**: 100% cable discovery accuracy (N switch pairs → N cables, zero duplicates after repeated runs)  
✅ **SC-002**: Every skip visible with machine-readable reason code and human-readable description  
✅ **SC-003**: Review workflow surfaces all cable candidates; only approved cables written  
✅ **SC-004**: Feature flag disables cables with zero writes across repeated runs  
✅ **SC-005**: All existing tests pass; new test coverage ≥ 90% for cable modules  
✅ **SC-006**: Operator can run discovery 3x back-to-back with identical NetBox state (idempotent)

---

## Phase 6: Development Timeline Estimate

| Phase | Component | Estimate | Dependencies |
|---|---|---|---|
| P1 | Data models (CableCandidate, etc.) | 2h | None |
| P2 | Hostname/interface normalization | 3h | P1 |
| P3 | Cable resolution algorithm | 4h | P2 |
| P4 | NetBox cable ingestion | 3h | P3 |
| P5 | PolicyRunner integration | 2h | P4 |
| P6 | Review workflow integration | 2h | P5 |
| P7 | FastAPI endpoints | 2h | P6 |
| P8 | Unit tests (cables modules) | 4h | P3-P6 |
| P9 | Integration tests | 3h | P8 |
| P10 | Frontend UI (cable candidates) | 4h | P7 |
| P11 | Frontend UI (cable summary) | 2h | P10 |
| P12 | Documentation + cleanup | 2h | All |
| **Total** | | **33h** | — |

**Sequencing:**
1. Start P1–P4 in parallel
2. After P4: P5–P6 in parallel
3. After P6: P7–P8 in parallel
4. After P8: P9–P11 in parallel
5. Final: P12

---

## Design Documents

Supporting specifications:

- [data-model.md](data-model.md) — Detailed data model extensions and COM integration
- [contracts/cable-resolution.md](contracts/cable-resolution.md) — Cable resolution algorithm spec with examples
- [contracts/cable-ingestion.md](contracts/cable-ingestion.md) — NetBox API contract and pynetbox usage patterns
- [quickstart.md](quickstart.md) — Usage examples and workflows

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Interface name normalization incomplete (rare vendors) | Low | Medium | Fallback to unresolvable with reason; operator can override via UI |
| NetBox API performance on large topology (1000+ cables) | Low | Medium | Batch writes; implement connection pooling; add timeouts |
| Concurrent discovery runs cause duplicate cables | Low | High | Rely on NetBox DB constraints; atomic exception handling |
| Operator accidentally ingests wrong cables (review mode) | Medium | High | Require explicit per-cable approval; show confidence tiers clearly |
| Circular reference in cable resolution (A→B→C→A) | Low | Low | Already prevented by matching only on direct LLDP neighbors |
| Domain suffix stripping breaks real hostnames | Very Low | Low | Test against real customer topologies; make suffix list configurable |

---

## Next Steps

1. **Immediate:** Create data model files and unit tests for normalization (P1–P2)
2. **Follow-up:** Implement cable resolution algorithm with full test coverage (P3–P4)
3. **Integration:** Wire into PolicyRunner and review workflow (P5–P6)
4. **Polish:** Add endpoints, UI, and comprehensive integration tests (P7–P11)
5. **Release:** Merge to `develop` after full test pass and upstream compatibility check

---

## Appendix: Configuration Examples

### Example 1: Enable cables in a policy

```yaml
policies:
  site-dc1-discovery:
    config:
      defaults:
        site: "DC1"
        role: "access-switch"
    scope:
      - hostname: 192.168.1.1
        username: admin
        password: secret
        collector: cisco_ios
      - hostname: 192.168.1.2
        username: admin
        password: secret
        collector: cisco_ios
```

After discovery, 2 cables auto-created in NetBox (or proposed for review).

### Example 2: Disable cables in a policy

```yaml
config:
  cables_enabled: false  # Disables all cable ingestion
```

Discovery runs; LLDP data collected; no cables created.

### Example 3: Review workflow

```bash
POST /api/v1/discover
{
  "policy": "site-dc1-discovery",
  "mode": "review"
}

# Returns: ReviewSession with devices + cables
{
  "id": "session-123",
  "devices": [...],
  "cables": [
    {
      "cable": {"device_a": "switch1", "interface_a": "Gi0/1", "device_b": "switch2", "interface_b": "Gi0/1"},
      "confidence": "confirmed",
      "device_a_discovered": true,
      "device_b_discovered": true
    },
    ...
  ]
}

# Operator reviews in UI; selects "Accept" on 2 cables, "Reject" on 1

PATCH /api/v1/reviews/session-123/cables/0
{ "status": "accepted" }

PATCH /api/v1/reviews/session-123/cables/1
{ "status": "accepted" }

PATCH /api/v1/reviews/session-123/cables/2
{ "status": "rejected" }

POST /api/v1/reviews/session-123/ingest

# Result: 2 cables created in NetBox, 1 skipped
```

---

**Status**: ✅ Ready for Phase 2 implementation  
**Owner**: Orbweaver Team  
**Review**: Approved by @rspengle (2026-05-11)
