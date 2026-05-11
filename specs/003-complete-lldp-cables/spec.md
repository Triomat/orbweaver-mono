# Feature Specification: Complete LLDP Cable Discovery and NetBox Ingestion

**Feature Branch**: `feature/003-complete-lldp-cables`
**Created**: 2026-05-11
**Status**: Draft
**Input**: User description: "Complete end-to-end LLDP cable resolution and ingestion into NetBox — including matching rules, deduplication policy, review workflow support, observability, and safety controls. LLDP collection and data models are already in place. The missing part is the end-to-end resolution and ingestion of cables into NetBox."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Auto-discover and ingest physical cables from LLDP (Priority: P1)

A network operator runs a discovery policy against a set of switches. The switches exchange
LLDP frames with their neighbors. After discovery, the operator expects NetBox to contain
cable records that represent the physical connections between devices — without having to
manually enter each cable. The system determines which neighbor advertisements constitute a
valid, unambiguous cable endpoint pair and writes those cables into NetBox, skipping any it
cannot resolve confidently.

**Why this priority**: This is the entire value of the feature. Without end-to-end cable
ingestion, the LLDP data collected during discovery has no effect on NetBox.

**Independent Test**: Run discovery against two directly-connected switches. Verify that a
cable record appears in NetBox linking the correct interfaces on both devices. Re-run
discovery and verify no duplicate cable is created.

**Acceptance Scenarios**:

1. **Given** two discovered devices each advertising the other via LLDP on matching interfaces,
   **When** the discovery run completes,
   **Then** exactly one cable record appears in NetBox connecting those two interfaces, labelled
   as LLDP auto-discovered.

2. **Given** a cable already exists in NetBox between two interfaces,
   **When** the same discovery run is repeated,
   **Then** no duplicate cable is created and the existing cable is left unchanged.

3. **Given** a device advertises a neighbor whose hostname cannot be matched to any discovered
   or existing device in NetBox,
   **Then** no cable is created for that neighbor and a structured skip reason is recorded
   in the discovery output.

4. **Given** a one-sided LLDP advertisement (only device A sees device B, not the reverse),
   **When** cable resolution runs,
   **Then** the operator is informed of the asymmetric neighbor and no cable is created
   without explicit confirmation.

---

### User Story 2 — Review proposed cables before NetBox write (Priority: P2)

A network operator uses the review workflow to run discovery in "hold" mode. Instead of
writing cables directly to NetBox, the system presents the operator with a list of proposed
cable connections — including both endpoints, the resolution confidence, and any skips with
reasons. The operator approves or rejects individual cables before anything is written.

**Why this priority**: In production environments, auto-creating cables without review can
corrupt the physical topology record in NetBox. Operators must be able to inspect and approve
before committing.

**Independent Test**: Run a discovery-for-review. Verify the review session lists proposed
cables with both endpoints and resolution status. Reject one cable and approve the rest.
Ingest and verify only the approved cables appear in NetBox.

**Acceptance Scenarios**:

1. **Given** a discovery-for-review run that resolves three cable candidates,
   **When** the operator opens the review session in the UI,
   **Then** all three cables are listed with device name, interface name for both endpoints,
   and a resolution confidence indicator.

2. **Given** a review session with mixed cables (some resolved, some partially resolved),
   **When** the operator rejects a partially-resolved cable and approves the rest,
   **Then** only the approved cables are written to NetBox upon ingest.

3. **Given** a review session that includes skip entries (unresolvable neighbors),
   **When** the operator views the review,
   **Then** skipped cables are visible with a human-readable reason (e.g., "neighbor device
   not found in NetBox", "ambiguous interface match").

---

### User Story 3 — Idempotent repeated discovery runs (Priority: P2)

A network operator schedules discovery to run daily. On each run, the system checks which
cables already exist in NetBox and skips creating duplicates. Cables discovered on a previous
run but since deleted in NetBox will be re-proposed on the next run. The outcome of each run
is predictable and reversible regardless of how many times it has been executed.

**Why this priority**: Scheduled/automated discovery runs must be safe to repeat. Without
idempotency, repeated runs accumulate duplicate cable records.

**Independent Test**: Run discovery three times back-to-back. Verify the cable count in NetBox
does not increase on the second or third run. Delete one cable manually, run again, verify it
is re-created (or re-proposed in review mode).

**Acceptance Scenarios**:

1. **Given** cables from a previous run already exist in NetBox,
   **When** the same discovery policy runs again,
   **Then** the `cables.skipped` counter reflects the existing cables and no new records
   are created.

2. **Given** a cable was deleted manually from NetBox between runs,
   **When** the next discovery run completes,
   **Then** the cable is proposed again (created in direct mode, listed for review in review mode).

---

### User Story 4 — Operator visibility: counters and skip reasons (Priority: P3)

After every discovery run (direct or review mode), the operator can see a summary of cable
outcomes: how many cables were resolved and created, how many were skipped and why, and how
many candidates were found but could not be resolved. This information appears in the discovery
response and in the review session summary.

**Why this priority**: Without observability, operators have no way to know whether the cable
discovery is working correctly or silently failing.

**Independent Test**: Run discovery against a topology with a mix of clean LLDP pairs,
one-sided neighbors, and an unknown neighbor. Verify the response includes separate counters
for discovered, created, skipped, and unresolvable — and that each skip has a reason.

**Acceptance Scenarios**:

1. **Given** a discovery run that resolves 5 cables, skips 2 (already in NetBox), and cannot
   resolve 1 (unknown neighbor),
   **When** the run completes,
   **Then** the response contains `cables.discovered: 6`, `cables.created: 5`,
   `cables.skipped: 2`, `cables.unresolvable: 1`.

2. **Given** a cable is skipped because the neighbor device was not found,
   **When** the operator reads the discovery output,
   **Then** the skip entry includes the local device name, local interface, advertised
   neighbor hostname, and a reason code such as `"neighbor_device_not_found"`.

---

### User Story 5 — Feature flag to disable cable ingestion (Priority: P3)

An operator can run discovery without cable creation by disabling cable ingestion via a
policy-level or environment-level setting. When cable ingestion is disabled, LLDP data is
still collected and visible in the review session, but no cable records are written to NetBox
and the cable resolution step is noted as skipped in the output.

**Why this priority**: Some environments already manage cables in NetBox manually. Operators
need a safe opt-out that does not require removing LLDP from the discovery scope.

**Independent Test**: Set the cable ingestion feature flag to disabled. Run discovery against
a topology with resolvable LLDP neighbors. Verify zero cables are created in NetBox and the
response confirms cable ingestion was disabled.

**Acceptance Scenarios**:

1. **Given** cable ingestion is disabled in the policy configuration,
   **When** discovery runs and resolves LLDP neighbors,
   **Then** no cable records are written to NetBox and the response notes
   `cables.ingestion_disabled: true`.

2. **Given** cable ingestion is disabled and a review-mode discovery runs,
   **When** the operator views the review session,
   **Then** LLDP neighbor data is visible but no cable candidates are listed for approval.

---

### Edge Cases

- What if the same cable is independently resolved from both endpoints in the same discovery
  run (device A sees B, and device B sees A)? → Only one cable record must be created.
- What if two interfaces on different devices share the same LLDP chassis MAC? → The system
  must flag this as ambiguous and skip cable creation for the affected neighbors.
- What if a neighbor's advertised interface name differs in format from the NetBox interface
  name (e.g., "Gi0/1" vs "GigabitEthernet0/1")? → Vendor-specific canonical expansion is
  attempted; if no match is found after normalization, the candidate is marked unresolvable
  with reason `"interface_name_mismatch"`. The operator is informed and can manually correct
  either the NetBox interface name or the LLDP data source.
- What if a device advertises itself as a neighbor (loop)? → Self-referential neighbors are
  skipped and logged with reason `"self_loop_detected"`.
- What if the NetBox API is unavailable during cable ingestion in direct mode? → The entire
  run fails and any successfully written cables are rolled back; the error is surfaced to
  the operator for manual intervention.
- What if an operator manually modifies a cable that was created by a previous discovery run
  (e.g., adds a label, changes status)? → On subsequent discovery runs, that cable is
  recognized as existing and skipped without modification. The operator's changes are
  preserved. If the operator needs to discard the cable and re-discover it fresh, they must
  delete it manually from NetBox.
- What if a newly discovered device advertises a neighbor whose chassis MAC matches an
  existing device in NetBox (not in the current discovery run)? → The LLDP neighbor is
  resolved to the existing NetBox device and the cable is created, linking the newly
  discovered device to the existing inventory. This cable will have Partial confidence
  because the existing device was not discovered in the current run. The operator can review
  and approve the cable in the UI before it is written to NetBox.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST resolve `NormalizedLLDPNeighbor` records into `NormalizedCable`
  candidates as part of the discovery post-processing step, operating on the full
  `DiscoveryResult` (not per-device) to enable bidirectional deduplication. Resolution MUST
  match advertised neighbors against both newly discovered devices and existing NetBox
  inventory, allowing cables to span between discovered and pre-existing devices.

- **FR-002**: Hostname matching MUST normalize LLDP-advertised hostnames and NetBox device
  names by stripping domain suffixes and lowercasing before comparison. Chassis MAC MUST be
  used as a fallback or supplementary identifier when hostname matching fails or when resolving
  neighbors against both newly discovered devices and existing NetBox inventory. A match to an
  existing NetBox device (not in the discovery run) MUST be treated as a valid cable endpoint.

- **FR-003**: Interface name matching MUST attempt vendor-specific canonical expansion of
  abbreviated names (e.g., Cisco "Gi0/1" → "GigabitEthernet0/1", Aruba "1/1" → "1/1" if
  already canonical) before declaring an interface unresolvable. If no canonical form matches
  a NetBox interface, the candidate MUST be marked unresolvable with reason
  `"interface_name_mismatch"`.

- **FR-004**: Bidirectional cable deduplication MUST ensure that a cable discovered from
  both endpoints in the same run produces exactly one `NormalizedCable` record.

- **FR-005**: The system MUST check NetBox for existing cables before creating new ones by
  matching on endpoint pairs (device name + interface name for both ends). Cables that
  already exist MUST be skipped without modification, even if their metadata (label,
  description, status) differs from LLDP-derived data. The `cables.skipped` counter MUST
  be incremented for each existing cable encountered. Operators retain full control over
  cable metadata.

- **FR-006**: One-sided LLDP neighbors (seen by only one endpoint) MUST NOT result in
  automatic cable creation; they MUST be surfaced to the operator with reason
  `"one_sided_neighbor"`.

- **FR-007**: The review workflow MUST include cable candidates as a reviewable entity type,
  with per-cable accept/reject controls visible in the UI.

- **FR-008**: Review sessions MUST display for each cable candidate: both device names,
  both interface names, a resolution confidence tier (Confirmed, Partial, or Unresolvable),
  and any skip/conflict reason. Confirmed cables are bidirectional matches with both
  endpoints discovered in the current run; Partial are one-sided discoveries, hostname-only
  matches, or cables where one endpoint is an existing NetBox device not in the current run;
  Unresolvable include a reason code.

- **FR-009**: Cable ingestion MUST be controllable via a feature flag at the policy or
  environment level; when disabled, no cables are written and the output confirms
  `ingestion_disabled`.

- **FR-010**: Every discovery run (direct and review mode) MUST produce structured output
  containing counters: `discovered`, `created`, `skipped`, `unresolvable`; and per-skip
  entries with `local_device`, `local_interface`, `neighbor_hostname`, and `reason`.

- **FR-011**: Self-referential neighbors (a device advertising itself) MUST be detected and
  skipped with reason `"self_loop_detected"`.

- **FR-012**: Ambiguous chassis MAC matches (same MAC seen on multiple devices) MUST result
  in the affected cable candidates being marked unresolvable with reason
  `"ambiguous_chassis_mac"`.

- **FR-013**: The system MUST remain idempotent across repeated discovery runs against the
  same topology; running the same policy N times MUST produce the same NetBox state as
  running it once.

- **FR-014**: Cable ingestion failures (NetBox API errors, timeouts, or network failures)
  MUST result in atomic rollback of all written cables for that run; no partial cable
  state MUST be left in NetBox. The error MUST be surfaced to the operator with context
  for manual recovery.

- **FR-015**: Cable records in NetBox MUST NEVER be updated by discovery runs. Existing
  cables are skipped without modification, preserving any operator-added metadata
  (labels, descriptions, status changes, etc.). This ensures idempotency and operator
  agency over cable properties.

### Key Entities

- **NormalizedLLDPNeighbor**: Raw LLDP advertisement from one interface — local interface,
  advertised neighbor hostname, remote interface, chassis MAC, optional management IP.
  Already part of the COM; produced by collectors.

- **NormalizedCable**: Resolved cable with two fully-qualified endpoints (device name +
  interface name). Already part of the COM; produced by the resolution step.

- **CableCandidate** *(new)*: Intermediate resolution artifact — holds a `NormalizedCable`
  plus metadata: a resolution confidence tier (Confirmed: both endpoints discovered in
  the current run with bidirectional match on hostname + interface; Partial: one-sided
  discovery, hostname-only match, or one endpoint from existing NetBox inventory;
  Unresolvable: skipped with reason), and provenance flags indicating which endpoints were
  newly discovered vs. resolved against existing NetBox inventory. Unresolvable candidates
  are not written to NetBox.

- **CableResolutionSummary** *(new)*: Aggregated counters and per-skip detail for a
  discovery run — `discovered`, `created`, `skipped`, `unresolvable`, and a list of skip
  detail entries.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A discovery run against a topology of N directly-connected switch pairs produces
  exactly N cable records in NetBox, with zero duplicates after any number of repeated runs.

- **SC-002**: Every skip — whether due to an unknown neighbor, a one-sided advertisement, or
  an ambiguous match — is visible in the discovery output with a machine-readable reason code
  and a human-readable description.

- **SC-003**: The review workflow surfaces all cable candidates before write; operators can
  approve a subset and only those approved cables appear in NetBox after ingest.

- **SC-004**: Disabling cable ingestion via feature flag produces zero cable writes across
  any number of discovery runs, with the disabled state confirmed in each run's output.

- **SC-005**: All existing orbweaver tests continue to pass after this feature is implemented;
  new test coverage includes: LLDP-to-cable resolution, hostname/interface normalization,
  bidirectional deduplication, one-sided neighbor detection, idempotency, and feature-flag
  behavior.

## Assumptions

- LLDP data collection is already implemented in the vendor collectors (`NormalizedLLDPNeighbor`
  is populated for Cisco IOS and Aruba AOS-CX devices). This feature adds the resolution and
  ingestion layer only.
- Diode SDK does not currently support cable entity ingestion; the direct ingestion path for
  cables will use the NetBox REST API via `pynetbox` (same pattern as rack assignment in
  `netbox_ops.py`). If Diode adds cable support in a future release, the ingestion path can
  be migrated without changing the resolution logic.
- The NetBox instance is reachable via `NETBOX_HOST`, `NETBOX_PORT`, and `NETBOX_TOKEN`
  environment variables (already used by `netbox_ops.py`).
- Cable deduplication against existing NetBox cables uses endpoint matching (device name +
  interface name for both ends), not cable ID or label.
- The cable resolution algorithm matches LLDP-advertised hostnames and chassis MACs against
  both newly discovered devices and existing NetBox inventory, enabling immediate visibility
  of how new infrastructure integrates into existing topology. Cables may have one endpoint
  from the current discovery run and the other from pre-existing NetBox records.
- Concurrent discovery runs are safe due to NetBox's database-level uniqueness constraints on
  cable endpoints; duplicate cable writes fail atomically and are handled gracefully without
  distributed locking.
- The review UI (Nuxt frontend) can be extended to display cable candidates alongside device
  candidates using the existing review session model.
- Out of scope for this feature: automatic cable deletion (removing cables from NetBox when
  LLDP no longer advertises them) — this is a destructive operation requiring a separate
  feature with explicit operator controls.

## Clarifications

### Session 2026-05-11

- Q: When two discovery runs execute simultaneously and both identify the same physical cable, how should the system handle potential race conditions? → A: Option B - Rely on NetBox database constraints (unique on device+interface pairs) to reject duplicate writes atomically.
- Q: When the NetBox API is unavailable or returns errors during cable ingestion (direct mode), what should the discovery run do? → A: Option A - Fail the entire discovery run; roll back any successfully written cables; surface the error to the operator.
- Q: How should cables be categorized by resolution confidence? → A: Option B - Three-tier system: Confirmed (bidirectional match on hostname + interface), Partial (one-sided or hostname-only match), Unresolvable (skipped with reason).
- Q: How comprehensive should interface name normalization be? → A: Option B - Vendor-specific canonical mappings (Cisco, Aruba, etc.); attempt expansion; if no match found after expansion, mark unresolvable with reason `"interface_name_mismatch"`.
- Q: Should the discovery run update existing cables or only create new ones? → A: Option A - Leave existing cables unchanged (create-or-skip only). Operators retain control over cable metadata; existing cables are skipped even if their metadata differs from LLDP-derived data.
- Q: Should cable resolution match LLDP chassis MACs to existing NetBox devices, creating cross-device cables in a single run? → A: Yes. The algorithm should match LLDP-advertised chassis MACs against both newly discovered devices and existing NetBox inventory, enabling immediate visibility of how new switches integrate into the existing topology.
