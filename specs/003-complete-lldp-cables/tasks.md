# Tasks: Complete LLDP Cable Discovery and NetBox Ingestion

**Feature Branch**: `feature/003-complete-lldp-cables`  
**Generated**: 2026-05-11  
**Tech Stack**: Python 3.10+, FastAPI, Pydantic 2.9, pytest, pynetbox, Nuxt 4

---

## Overview

This document contains all actionable tasks for implementing end-to-end LLDP cable resolution and NetBox ingestion. Tasks are organized by implementation phase and user story, with clear dependencies and independent test criteria for each story.

**Suggested MVP Scope**: Complete US1 (Auto-discover and ingest physical cables). US2–US5 follow as extensions.

---

## Phase 1: Setup & Initialization

- [ ] T001 Create cable module structure: `orbweaver/cables/` directory with `__init__.py`, `models.py`, `normalize.py`, `resolve.py`, `ingest.py`
- [ ] T002 Create test directory structure: `orbweaver/tests/test_cables_resolve.py`, `test_cables_normalize.py`, `test_cables_ingest.py`, `test_cables_integration.py`, `test_review_cables.py`
- [ ] T003 Set up pytest fixtures for mock LLDP neighbors, mock NormalizedDevice objects, and mock NetBox client in `orbweaver/tests/conftest.py`
- [ ] T004 Add pynetbox to `orbweaver/pyproject.toml` dependencies (if not already present) with version constraint

---

## Phase 2: Foundational Data Models & Normalization

### Core Data Models

- [ ] T005 Implement `ResolutionConfidence` enum (CONFIRMED, PARTIAL, UNRESOLVABLE) in `orbweaver/cables/models.py`
- [ ] T006 Implement `CableSkipEntry` dataclass in `orbweaver/cables/models.py` with fields: local_device, local_interface, neighbor_hostname, reason, neighbor_interface, neighbor_chassis_mac
- [ ] T007 Implement `CableCandidate` dataclass in `orbweaver/cables/models.py` with fields: cable, confidence, device_a_discovered, device_b_discovered, skip_reason, lldp_neighbor, resolution_notes, lldp_direction; add `is_writable` property
- [ ] T008 Implement `CableResolutionSummary` dataclass in `orbweaver/cables/models.py` with fields: discovered, candidates, created, skipped, unresolvable, skip_entries, ingestion_disabled, ingestion_error
- [ ] T009 Extend `DiscoveryResult` in `orbweaver/models/common.py` to add `cable_candidates: list[CableCandidate]` and `cable_summary: CableResolutionSummary | None` fields
- [ ] T010 Extend `ReviewSession` in `orbweaver/review/models.py` to add `cables: list[ReviewItem]` and `cable_summary: dict | None` fields

### Hostname & Interface Normalization

- [ ] T011 Implement `normalize_hostname(hostname: str) → str` in `orbweaver/cables/normalize.py`: strip domain suffixes, lowercase, trim whitespace (e.g., "switch1.example.com" → "switch1")
- [ ] T012 Implement `normalize_chassis_mac(mac: str) → str` in `orbweaver/cables/normalize.py`: lowercase, remove separators (hyphens, colons) for matching; store original format for logging
- [ ] T013 [P] Implement vendor-specific interface expansion mappings in `orbweaver/cables/normalize.py` for Cisco (e.g., "Gi0/1" → "GigabitEthernet0/1", "Eth1/1" → "Ethernet1/1") and Aruba (e.g., "1/1" → "1/1" if already canonical)
- [ ] T014 [P] Implement `normalize_interface_name(interface: str, vendor: str, mappings: dict) → tuple[str | None, bool]` in `orbweaver/cables/normalize.py`: return (normalized_name, is_canonical); return (None, False) if no mapping found
- [ ] T015 Implement caching layer for interface mappings in `orbweaver/cables/normalize.py` using `functools.lru_cache` to avoid repeated lookups

**Test Criteria for T011–T015**: 
- Hostname normalization correctly strips "domain.local" and lowercases
- MAC normalization produces consistent lowercase with no separators
- Cisco Gi0/1 expands to GigabitEthernet0/1; Aruba 1/1 is recognized as canonical
- Interface cache hits on repeated lookups

---

## Phase 3: Cable Resolution Algorithm

### Core Resolution Logic

- [x] T016 [P] [US1] Implement helper functions in `orbweaver/cables/resolve.py`:
  - `dedupe_key(dev_a: str, intf_a: str, dev_b: str, intf_b: str) → str`: create canonical key for bidirectional deduplication
  - `lookup_device_in_netbox(netbox_client, hostname: str, mac: str) → NormalizedDevice | None`: query NetBox for existing device by hostname or MAC
  - `match_interface_on_device(device, interface: str, normalization_rules) → str | None`: find matching interface name on a device

- [x] T017 [P] [US1] Implement device indexing logic in `orbweaver/cables/resolve.py`:
  - Build map of discovered devices indexed by normalized hostname
  - Build secondary map indexed by normalized chassis MAC
  - Pre-populate device maps before processing LLDP neighbors

- [x] T018 [US1] Implement main cable resolution algorithm in `orbweaver/cables/resolve.py` function `resolve_cables(discovery_result: DiscoveryResult, netbox_client, normalization_rules: dict) → tuple[list[CableCandidate], CableResolutionSummary]`:
  - Phase 1: Normalize all device identifiers (hostnames, MACs)
  - Phase 2: Build neighbor map for bidirectional deduplication
  - Phase 3a–d: For each LLDP neighbor:
    - Self-loop detection (skip if device sees itself)
    - Normalize neighbor identifiers
    - Device matching: hostname first, then MAC, then NetBox lookup
    - Interface normalization and matching
  - Phase 4: Validation and confidence tier assignment (CONFIRMED vs PARTIAL vs UNRESOLVABLE)
  - Phase 5: Bidirectional deduplication (A→B and B→A → one cable)
  - Phase 6: Create CableCandidate objects with metadata
  - Phase 7–9: Ambiguous MAC detection, one-sided neighbor detection, NetBox existing cable check
  - Phase 10: Finalize summary with created/skipped counts

- [x] T019 [P] [US1] Implement validation checks in `orbweaver/cables/resolve.py`:
  - `is_self_loop(device_name: str, neighbor_name: str) → bool`: detect self-referential neighbors
  - `is_ambiguous_mac(device_name: str, discovery_result, netbox_client) → bool`: detect same MAC on multiple devices
  - `is_bidirectional_match(dev_a: str, dev_b: str, discovery_result) → bool`: check if both endpoints see each other
  - `cable_exists_in_netbox(netbox_client, cable: NormalizedCable) → bool`: endpoint matching against existing cables

- [x] T020 [US1] Implement LLDP direction detection in `orbweaver/cables/resolve.py`:
  - `determine_lldp_direction(dev_a: str, dev_b: str, discovery_result) → str`: return "bidirectional", "a_to_b", or "b_to_a"

**Test Criteria for T016–T020**:
- Two directly connected switches produce one cable (not two)
- One-sided LLDP marks cable as PARTIAL, not CONFIRMED
- Unresolvable neighbors (missing device, interface mismatch) skip with correct reason
- Self-loops are detected and skipped
- Ambiguous MACs trigger unresolvable status

---

## Phase 4: Cable Ingestion (Direct & Review Modes)

### Direct Mode Ingestion

- [x] T021 [P] [US1] Implement `ingest_cables_direct(candidates: list[CableCandidate], netbox_client, write_enabled: bool, dry_run: bool) → CableResolutionSummary` in `orbweaver/cables/ingest.py`:
  - Filter candidates: only include those with confidence != UNRESOLVABLE
  - Check NetBox for existing cables by endpoint matching (device + interface pairs)
  - For each new cable:
    - Look up device IDs via `/api/dcim/devices/?name={device_name}`
    - Look up interface IDs via `/api/dcim/interfaces/?device__name={device_name}&name={interface_name}`
    - Create cable via `POST /api/dcim/cables/` with termination_a_id, termination_b_id, label="LLDP auto-discovered"
  - Increment created count on success; add skip entry on 409 Conflict (already exists)
  - Implement atomic rollback: on any error after first write, DELETE all previously created cables
  - Return updated summary

- [x] T022 [P] [US1] Implement helper functions in `orbweaver/cables/ingest.py`:
  - `get_device_id(netbox_client, device_name: str) → int`: return device ID or raise error
  - `get_interface_id(netbox_client, device_name: str, interface_name: str) → int`: return interface ID or raise error
  - `create_cable_in_netbox(netbox_client, device_a_id: int, intf_a_id: int, device_b_id: int, intf_b_id: int) → dict`: POST to cable endpoint; return response
  - `delete_cable_in_netbox(netbox_client, cable_id: int) → bool`: DELETE cable; used for rollback

- [x] T023 [US1] Implement `ingest_cables_from_review(approved_candidates: list[CableCandidate], netbox_client, write_enabled: bool) → CableResolutionSummary` in `orbweaver/cables/ingest.py`:
  - Pre-filtered list of approved candidates (from ReviewStore)
  - Delegate to `ingest_cables_direct()` with the filtered list

### Feature Flag Support

- [x] T024 [US5] Extend `orbweaver/patches.py` to read `cables_enabled` policy flag:
  - Check policy config for `cables_enabled: false` (default: true)
  - Skip cable resolution if disabled
  - Set `cable_summary.ingestion_disabled = True` in output

- [x] T025 [US5] Add environment variable override for cable ingestion: `ORBWEAVER_CABLES_ENABLED` (default: "true"); allow policy flag to override

**Test Criteria for T021–T025**:
- Cable creation succeeds with valid device/interface IDs
- Duplicate write triggers rollback of all cables in transaction
- Feature flag disabled produces zero cables and `ingestion_disabled=True`
- Existing cables are skipped without modification
- NetBox API errors are caught and surfaced with context

---

## Phase 5: PolicyRunner Integration

- [x] T026 [US1] Extend `orbweaver/patches.py` to patch `PolicyRunner._collect_device_data()`:
  - After Napalm/Diode collection, check if cable ingestion is enabled
  - Call `resolve_cables(discovery_result, netbox_client, normalization_rules)`
  - Populate `discovery_result.cable_candidates` with resolved cables
  - Call `ingest_cables_direct(discovery_result.cable_candidates, netbox_client, write_enabled)`
  - Populate `discovery_result.cable_summary` with ingestion results

- [x] T027 [US1] Pass NetBox client to cable resolution in `orbweaver/patches.py`:
  - Instantiate `netbox_client` via existing `_pynetbox_client()` method if not already passed
  - Handle case where `NETBOX_HOST` is unset (skip cable ingestion with warning)

- [x] T028 [US1] Add vendor-specific normalization rules to `orbweaver/patches.py`:
  - Build normalization_rules dict from collector metadata (vendor name, platform)
  - Pass to `resolve_cables()` for interface expansion

**Test Criteria for T026–T028**:
- PolicyRunner patch is applied at startup
- Cable workflow runs after device/VLAN/prefix ingestion
- NetBox unavailability skips cable resolution with warning
- Normalization rules are correctly passed to resolution algorithm

---

## Phase 6: Review Workflow Integration

- [x] T029 [US2] Extend `orbweaver/review/discover.py` function `run_discovery_for_review()`:
  - After device discovery completes, call `resolve_cables(discovery_result, netbox_client, normalization_rules)`
  - For each cable candidate, create `ReviewItem(index=idx, status=ItemStatus.PENDING, data=serialize(candidate))`
  - Append to `session.cables` list
  - Populate `session.cable_summary` with `CableResolutionSummary` serialized as dict

- [x] T030 [US2] Implement cable serialization in `orbweaver/review/rebuild.py`:
  - `cable_candidate_to_dict(candidate: CableCandidate) → dict`: serialize to JSON-compatible dict
  - `dict_to_cable_candidate(data: dict) → CableCandidate`: deserialize from dict using `dacite`

- [x] T031 [US2] Extend `orbweaver/app.py` to add cable ingestion endpoint:
  - `POST /api/v1/reviews/{session_id}/ingest-cables`: ingest only approved cables
  - Filter cables by `ItemStatus.ACCEPTED`
  - Reconstruct `CableCandidate` objects from serialized JSON
  - Call `ingest_cables_from_review(approved_candidates, netbox_client, write_enabled)`
  - Return updated summary

**Test Criteria for T029–T031**:
- Review session includes all cable candidates in `cables` list
- Approved cables ingest correctly; rejected cables are skipped
- Serialization/deserialization preserves cable candidate data
- Endpoint returns correct ingestion summary

---

## Phase 7: API Endpoints & Response Integration

- [x] T032 [US1] Extend `orbweaver/app.py` response for `POST /api/v1/policies`:
  - Populate `response["cables"]` with `cable_summary` data (discovered, created, skipped, unresolvable, skip_entries)
  - Ensure response schema includes cable fields

- [x] T033 [US4] Add `/api/v1/cables/summary` endpoint in `orbweaver/app.py`:
  - Return latest cable ingestion summary from last discovery run
  - Include skip entries with reason codes

- [x] T034 [US4] Add `/api/v1/cables/skip-reasons` endpoint in `orbweaver/app.py`:
  - Return list of all possible skip reason codes (for UI dropdown/filtering)
  - Example: ["neighbor_device_not_found", "interface_name_mismatch", "one_sided_neighbor", "already_exists", "self_loop_detected", "ambiguous_chassis_mac"]

**Test Criteria for T032–T034**:
- Policy response includes cable summary when cables are created
- Summary endpoint returns correct counters
- Skip-reasons endpoint lists all possible reasons

---

## Phase 8: Unit Tests for Core Modules

### Normalization Tests

- [x] T035 [P] [US1] Write unit tests in `orbweaver/tests/test_cables_normalize.py`:
  - `test_normalize_hostname_strips_domain()`: "switch1.example.com" → "switch1"
  - `test_normalize_hostname_lowercases()`: "SWITCH1" → "switch1"
  - `test_normalize_hostname_trims_whitespace()`: "  switch1  " → "switch1"
  - `test_normalize_mac_removes_separators()`: "aa:bb:cc:dd:ee:ff" → "aabbccddeeff"
  - `test_normalize_interface_cisco_gi_to_gigabit()`: ("Gi0/1", "cisco", mappings) → "GigabitEthernet0/1"
  - `test_normalize_interface_cisco_eth_to_ethernet()`: ("Eth1/1", "cisco", mappings) → "Ethernet1/1"
  - `test_normalize_interface_aruba_already_canonical()`: ("1/1", "aruba", mappings) → "1/1"
  - `test_normalize_interface_unknown_vendor_returns_none()`: ("Gi0/1", "juniper", {}) → (None, False)
  - `test_interface_mapping_cache_hits()`: repeated calls hit cache
  - 100% coverage of `normalize.py`

### Resolution Algorithm Tests

- [x] T036 [P] [US1] Write unit tests in `orbweaver/tests/test_cables_resolve.py` for helper functions:
  - `test_dedupe_key_bidirectional_symmetry()`: same key for A→B and B→A
  - `test_self_loop_detection()`: device name == neighbor name → self_loop_detected
  - `test_ambiguous_mac_detection()`: same MAC on two devices → ambiguous_chassis_mac
  - `test_bidirectional_match_detection()`: A sees B and B sees A → bidirectional=true
  - 100% coverage of helper functions

- [x] T037 [P] [US1] Write integration tests in `orbweaver/tests/test_cables_resolve.py` for full algorithm:
  - `test_resolve_two_connected_switches()`: Create discovery_result with 2 devices + bidirectional LLDP; expect 1 cable with CONFIRMED confidence
  - `test_resolve_one_sided_neighbor()`: Device A sees B, but B does not see A; expect PARTIAL confidence
  - `test_resolve_unknown_neighbor()`: Neighbor hostname not in discovered or NetBox; expect UNRESOLVABLE with reason="neighbor_device_not_found"
  - `test_resolve_interface_mismatch()`: Neighbor interface name not found after normalization; expect UNRESOLVABLE with reason="interface_name_mismatch"
  - `test_resolve_self_loop()`: Device sees itself; expect UNRESOLVABLE with reason="self_loop_detected"
  - `test_resolve_bidirectional_deduplication()`: A→B and B→A in same run; expect 1 cable (not 2)
  - `test_resolve_cross_device_cables()`: LLDP neighbor matched to existing NetBox device; expect PARTIAL confidence
  - `test_resolve_ambiguous_mac()`: Same MAC on two discovered devices; expect cable marked UNRESOLVABLE with reason="ambiguous_chassis_mac"
  - `test_resolve_existing_cable_skip()`: Cable already in NetBox; expect UNRESOLVABLE with reason="already_exists"
  - 100% coverage of `resolve.py`

### Ingestion Tests

- [x] T038 [P] [US1] Write unit tests in `orbweaver/tests/test_cables_ingest.py`:
  - `test_ingest_creates_new_cable()`: Mock NetBox client; create cable; verify POST called with correct payload
  - `test_ingest_skips_existing_cable()`: Cable already in NetBox; expect skipped counter incremented
  - `test_ingest_rollback_on_error()`: 3 cables queued; 2 created successfully; 3rd fails; expect all 3 deleted (rollback)
  - `test_ingest_disabled_flag()`: `write_enabled=False`; no cables created; `ingestion_disabled=True` in summary
  - `test_ingest_dry_run_mode()`: `dry_run=True`; no changes to NetBox; summary still populated
  - `test_ingest_netbox_unavailable()`: `netbox_client=None`; no cables created; error in summary
  - 100% coverage of `ingest.py`

**Test Criteria for T035–T038**:
- All normalization functions handle edge cases (empty strings, None, special chars)
- Resolution algorithm correctly identifies all cable types (confirmed, partial, unresolvable)
- Ingestion correctly creates cables and handles errors atomically
- Test coverage ≥ 90% for all cable modules

---

## Phase 9: Integration Tests

- [x] T039 [US1] Write integration tests in `orbweaver/tests/test_cables_integration.py`:
  - `test_discovery_run_creates_cables()`: Full discovery run against mocked NetBox; verify cables created in NetBox
  - `test_repeated_discovery_run_idempotent()`: Run discovery 3x back-to-back; verify cable count unchanged after run 1
  - `test_discovery_run_after_manual_deletion()`: Create cable; delete from NetBox manually; run discovery again; verify cable re-created
  - `test_discovery_run_with_review_workflow()`: Run discovery for review; approve subset of cables; ingest; verify only approved cables in NetBox
  - `test_discovery_run_with_cables_disabled()`: Cable ingestion disabled; run discovery; verify zero cables created and `ingestion_disabled=True`
  - `test_netbox_api_error_atomic_rollback()`: Simulate NetBox API failure after 2 cables written; verify all 2 cables rolled back
  - `test_concurrent_discovery_runs()`: Simulate 2 concurrent runs discovering same cable; verify database constraints prevent duplicates
  - 100% coverage of end-to-end cable workflow

- [x] T040 [US2] Write review workflow integration tests in `orbweaver/tests/test_review_cables.py`:
  - `test_review_session_includes_cable_candidates()`: Run discovery for review; verify cable candidates in session
  - `test_review_session_serialization()`: Serialize/deserialize review session with cables; verify data preserved
  - `test_cable_candidate_approval()`: Mark cable as ACCEPTED in review; ingest; verify in NetBox
  - `test_cable_candidate_rejection()`: Mark cable as REJECTED in review; ingest; verify not in NetBox
  - `test_cable_summary_in_review_session()`: Verify cable_summary populated in review session

- [x] T041 [P] Run upstream compatibility tests:
  - Execute `backend/tests/` suite to ensure no regressions
  - Verify all device, VLAN, prefix tests still pass
  - No modifications to upstream code paths

**Test Criteria for T039–T041**:
- End-to-end cable ingestion works with real (mocked) NetBox
- Repeated runs are idempotent (SC-001)
- All skip reasons are visible with machine-readable codes (SC-002)
- Review workflow allows selective cable approval (SC-003)
- Feature flag disables all cables (SC-004)
- All existing upstream tests pass (SC-005)

---

## Phase 10: Frontend UI — Cable Candidates in Review

- [x] T042 [US2] Extend `frontend/app/pages/review/[id].vue`:
  - Add "Cables" tab alongside "Devices" tab
  - Display cable candidates in a table with columns: local_device, local_interface, remote_device, remote_interface, confidence, status (PENDING/ACCEPTED/REJECTED)
  - Highlight CONFIRMED cables in green, PARTIAL in yellow, UNRESOLVABLE in red
  - Add per-cable checkbox for ACCEPTED/REJECTED toggle
  - Show skip reasons for UNRESOLVABLE cables (tooltip or collapsible row)

- [x] T043 [US2] Extend `frontend/app/composables/useReview.ts`:
  - Add `cables` reactive array to ReviewSession state
  - Implement `approveCable(cable_id)` function: mark cable status as ACCEPTED
  - Implement `rejectCable(cable_id)` function: mark cable status as REJECTED
  - Implement `filterCablesByConfidence(confidence: string)` for UI filtering
  - Add `cable_summary` to session state (discovered, created, skipped, unresolvable)

- [x] T044 [US2] Create new component `frontend/app/components/CableTable.vue`:
  - Table component displaying cable candidates
  - Columns: local_device, local_interface, remote_device, remote_interface, confidence_tier, skip_reason, action (checkbox)
  - Sorting by confidence (CONFIRMED first, PARTIAL, UNRESOLVABLE last)
  - Row highlighting based on confidence (green=confirmed, yellow=partial, red=unresolvable)
  - Tooltip for skip_reason on UNRESOLVABLE rows

- [x] T045 [US4] Create new component `frontend/app/components/CableSummary.vue`:
  - Display counters: discovered, created, skipped, unresolvable
  - Progress bar showing created/discovered ratio
  - Expandable section for skip_entries details (table of local_device, local_interface, neighbor_hostname, reason)

- [x] T046 [US2] Extend `frontend/app/types/index.ts`:
  - Add `CableCandidate` type definition with all fields
  - Add `CableResolutionSummary` type
  - Add `CableSkipEntry` type

**Test Criteria for T042–T046**:
- Cable candidates display in review UI with all required columns
- Confidence tiers are color-coded
- Operators can approve/reject individual cables
- Summary shows accurate counters

---

## Phase 11: Documentation & Cleanup

- [x] T047 Add inline documentation to `orbweaver/cables/` modules:
  - Module docstrings explaining purpose of each module
  - Function docstrings with Args, Returns, Raises sections
  - Example usage for public functions

- [x] T048 Create `docs/cable-resolution.md` user guide:
  - Overview of cable discovery feature
  - Configuration examples (cables_enabled in policy)
  - Example discovery output with cable summary
  - Example review session with cable candidates
  - Troubleshooting section (skip reasons explained)

- [x] T049 Create `docs/cable-examples.md` with test scenarios:
  - Example 1: Two directly connected switches (CONFIRMED cable)
  - Example 2: One-sided LLDP (PARTIAL cable)
  - Example 3: Unknown neighbor (UNRESOLVABLE cable)
  - Example 4: Feature flag disabled (no cables created)
  - Example 5: Review workflow (selective approval)

- [x] T050 Update main `README.md`:
  - Add cable discovery section to feature list
  - Link to cable resolution documentation
  - Show policy configuration example with cables_enabled

- [x] T051 Add changelog entry to `CHANGELOG.md`:
  - Feature: Complete LLDP cable discovery and NetBox ingestion
  - Includes cable resolution algorithm, review workflow support, observability, and feature flag
  - References user stories and success criteria

- [x] T052 Code cleanup & final validation:
  - Remove debug print statements
  - Ensure all imports are used (run `python orbweaver/scripts/check_imports.py`)
  - Run formatters: `black orbweaver/cables/ orbweaver/tests/test_cables_*.py`
  - Run linters: `ruff check orbweaver/cables/`
  - Final test run: `just test` (all tests pass, coverage ≥ 90%)

- [ ] T053 Final upstream compatibility check:
  - Merge current `develop` branch into feature branch
  - Run full upstream test suite: `just test-legacy`
  - Verify no regressions in device/VLAN/prefix discovery
  - Note: `just test-legacy` passed; merge from `develop` is pending manual branch management.

**Test Criteria for T047–T053**:
- All code is documented with docstrings
- User guide explains cable discovery, configuration, and troubleshooting
- Examples cover all cable types (confirmed, partial, unresolvable)
- Feature flag behavior is documented
- All tests pass locally
- Ready for PR review and merge to `develop`

---

## Dependency Graph

```
Phase 1: Setup (T001–T004)
    ↓
Phase 2: Data Models & Normalization (T005–T015)
    ├─→ T016 (helper functions) ─→ T018 (main resolution algorithm)
    └─→ T017 (device indexing) ──→ T018
    ↓
Phase 3: Resolution Algorithm (T016–T020)
    ↓
Phase 4: Ingestion (T021–T025)
    ├─→ T026–T028 (PolicyRunner integration)
    ├─→ T029–T031 (Review workflow integration)
    └─→ T032–T034 (API endpoints)
    ↓
Phase 5: Integration & Workflow (T026–T034)
    ↓
Phase 6: Testing (T035–T041)
    ↓
Phase 7: Frontend (T042–T046)
    ↓
Phase 8: Documentation & Cleanup (T047–T053)
```

---

## Parallel Execution Opportunities

**By User Story:**

### US1 (P1) — Auto-discover and ingest: T001–T040

**Parallel tracks within US1:**
1. **Models & Normalization** (T005–T015, ~4 hours):
   - T005–T010 (data models): 2 hours
   - T011–T015 (normalization): 2 hours
   - Can run in parallel

2. **Resolution Algorithm** (T016–T020, ~5 hours):
   - T016 (helpers): 1 hour
   - T017 (device indexing): 0.5 hours
   - T018 (main algorithm): 3 hours
   - T019–T020 (validation & LLDP direction): 1 hour
   - Dependent chain; sequential

3. **Ingestion & Workflow** (T021–T034, ~4 hours):
   - T021–T023 (ingestion logic): 2 hours
   - T026–T028 (PolicyRunner): 1 hour
   - T032–T034 (endpoints): 1 hour
   - Can overlap with T016–T020 after T015

4. **Testing** (T035–T041, ~6 hours):
   - T035 (normalization tests): 1 hour
   - T036–T037 (resolution tests): 2.5 hours
   - T038 (ingestion tests): 1 hour
   - T039 (integration tests): 1 hour
   - T040 (review tests): 0.5 hours
   - Can run in parallel with upstream compat (T041)

**Suggested Parallel Schedule:**
- Week 1: T001–T015 (Setup & Models) + T035 (normalization tests)
- Week 2: T016–T020 (Resolution) + T036–T037 (resolution tests)
- Week 3: T021–T034 (Ingestion & Workflow) + T038–T039 (ingestion tests)
- Week 4: T042–T046 (Frontend) + T047–T053 (Documentation)

### US2 (P2) — Review workflow: T029–T031, T042–T046

**Blocked by US1**: Review workflow requires cable resolution algorithm to be complete.  
**After US1 complete**: Can start US2 immediately; runs in parallel with frontend work.

### US3 (P2) — Idempotency: T039

**Test is part of US1 testing**: Idempotency validated in T039 "test_repeated_discovery_run_idempotent".  
**No additional implementation required**: Already handled by cable deduplication logic in T018.

### US4 (P3) — Observability: T033–T034, T045

**Blocked by US1**: Observability endpoints require cable resolution algorithm.  
**After US1 complete**: Can add endpoints T033–T034 independently; can add UI summary T045 after US2.

### US5 (P3) — Feature flag: T024–T025

**Independent from US1 implementation**: Feature flag can be added in parallel with core logic.  
**Suggested timing**: Add alongside T026–T028 (PolicyRunner integration).

---

## Success Metrics

**After Each User Story:**

| Story | Test | Success Metric | Coverage |
|-------|------|---|---|
| US1 | T039 | 2 directly-connected switches → 1 cable; repeated runs idempotent | 90%+ |
| US2 | T040 | Review session includes all candidates; operator can approve/reject | 85%+ |
| US3 | T039 | Run discovery 3x; NetBox state unchanged after 1st run | Built into US1 |
| US4 | T033–T034, T045 | All skips visible with reason codes; summary counters accurate | 80%+ |
| US5 | T024–T025, T039 | cables_enabled=false → zero cables created; ingestion_disabled=true | 85%+ |

**Final Metrics:**
- ✅ All cable modules at ≥90% test coverage
- ✅ Upstream tests all pass (T041)
- ✅ End-to-end integration test successful (T039)
- ✅ Frontend displays cable candidates and summaries (T042–T046)
- ✅ Documentation complete with examples (T047–T050)
- ✅ Ready for merge to `develop` and PR review

---

## Acceptance Criteria

### US1: Auto-discover and ingest physical cables from LLDP

- [ ] **AC-1.1**: Given two discovered devices exchanging LLDP frames, when discovery completes, exactly one cable record appears in NetBox with label "LLDP auto-discovered"
- [ ] **AC-1.2**: Given a cable already exists in NetBox, when discovery runs again, no duplicate is created
- [ ] **AC-1.3**: Given a device advertises an unresolvable neighbor, when discovery completes, no cable is created and a skip reason is recorded

### US2: Review proposed cables before NetBox write

- [ ] **AC-2.1**: Given a discovery-for-review run, all proposed cables are listed with both endpoints and resolution confidence
- [ ] **AC-2.2**: Given a review session, operator can reject cables and ingest only approved ones
- [ ] **AC-2.3**: Skipped cables are visible with human-readable reasons

### US3: Idempotent repeated discovery runs

- [ ] **AC-3.1**: Running discovery 3 times produces same NetBox cable state as 1 run
- [ ] **AC-3.2**: Cables deleted between runs are re-proposed on next run

### US4: Operator visibility — counters and skip reasons

- [ ] **AC-4.1**: Every discovery run response includes counters: discovered, created, skipped, unresolvable
- [ ] **AC-4.2**: Every skip entry includes: local_device, local_interface, neighbor_hostname, reason_code

### US5: Feature flag to disable cable ingestion

- [ ] **AC-5.1**: cables_enabled=false produces zero cables in NetBox
- [ ] **AC-5.2**: Response confirms `ingestion_disabled=true`

---

## Implementation Tips

1. **Start with normalization (T011–T015)**: Small, testable functions that validate hostname/MAC/interface handling before building the resolution algorithm.

2. **Build resolution algorithm incrementally (T018)**: Implement phases in order (normalize, device matching, interface matching, validation, deduplication). Test each phase with unit tests before moving to the next.

3. **Mock NetBox client for testing (T038–T039)**: Use pytest fixtures to mock `pynetbox.api` responses. Avoid real NetBox calls in tests.

4. **Atomic rollback is critical (T022)**: Implement `delete_cable_in_netbox()` helper and test the rollback path extensively. This prevents partial cable state on errors.

5. **Bidirectional deduplication (T019)**: Use a sorted tuple of device+interface pairs as the deduplication key. This ensures A→B and B→A produce one cable.

6. **Confidence tier assignment (T018)**: Assign CONFIRMED only if both endpoints are discovered in the current run AND they see each other bidirectionally. Everything else is PARTIAL or UNRESOLVABLE.

7. **Review UI simple start (T042)**: Start with a basic table of cables. Add color-coding and filtering after the basic display works.

8. **Document skip reasons thoroughly (T048–T049)**: Each skip reason code (neighbor_device_not_found, interface_name_mismatch, one_sided_neighbor, etc.) should have a clear explanation and example in the user guide.

---

## Known Risks & Mitigation

| Risk | Mitigation |
|---|---|
| Interface normalization doesn't cover all vendors | Fallback to unresolvable with reason; operator can override in UI. Test against real customer topologies. |
| NetBox API performance on large topologies (1000+ cables) | Batch writes; implement connection pooling; add timeouts. |
| Concurrent discovery runs create duplicates | Rely on NetBox DB unique constraints; atomic exception handling. |
| Operator accidentally ingests wrong cables | Require explicit per-cable approval; show confidence tiers clearly. |

---

## Total Task Effort Estimate

| Phase | Tasks | Estimate | Notes |
|-------|-------|----------|-------|
| Setup | T001–T004 | 1h | Directory structure, fixtures |
| Data Models | T005–T010 | 2h | COM extensions, review session |
| Normalization | T011–T015 | 3h | Hostname/MAC/interface mapping |
| Resolution Helpers | T016–T020 | 5h | Device matching, validation, LLDP direction |
| Ingestion | T021–T025 | 4h | Direct + review mode, rollback, feature flag |
| PolicyRunner | T026–T028 | 2h | Patch integration, client setup |
| Review Workflow | T029–T031 | 2h | Discovery hold, serialization, endpoint |
| API Endpoints | T032–T034 | 2h | Policy response, summary endpoint, skip reasons |
| Normalization Tests | T035 | 1h | Comprehensive unit tests |
| Resolution Tests | T036–T037 | 2.5h | Unit + integration tests |
| Ingestion Tests | T038 | 1h | CRUD, rollback, error handling |
| Integration Tests | T039–T040 | 2h | E2E workflows, idempotency |
| Upstream Compat | T041 | 0.5h | Run existing test suite |
| Frontend UI | T042–T046 | 4h | Cable table, summary, types |
| Documentation | T047–T053 | 3h | Docs, guides, changelog, cleanup |
| **TOTAL** | | **~34 hours** | Can parallelize to ~3 weeks |

---

## Success Definition

**FEATURE COMPLETE**: 
- ✅ All 5 user stories implemented and tested
- ✅ Cable candidates created, reviewed, and ingested via direct mode
- ✅ All skip reasons documented and visible to operators
- ✅ Feature flag allows safe opt-out of cable ingestion
- ✅ End-to-end idempotent across repeated runs
- ✅ Review UI surfaces cables for operator approval
- ✅ Test coverage ≥ 90% for all cable modules
- ✅ Upstream tests all pass (no regressions)
- ✅ Comprehensive documentation and examples
- ✅ Ready for merge to `develop` and production deployment

---

## Reference Documents

- **Spec**: [spec.md](spec.md)
- **Plan**: [plan.md](plan.md)
- **Data Model**: [data-model.md](data-model.md)
- **Cable Resolution Contract**: [contracts/cable-resolution.md](contracts/cable-resolution.md)
- **Cable Ingestion Contract**: [contracts/cable-ingestion.md](contracts/cable-ingestion.md)
- **Quickstart**: [quickstart.md](quickstart.md)
