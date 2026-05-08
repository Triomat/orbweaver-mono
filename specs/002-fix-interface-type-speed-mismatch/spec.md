# Feature Specification: Interface Type/Speed Mismatch Fix

**Feature Branch**: `002-fix-interface-type-speed-mismatch`  
**Created**: 2026-05-08  
**Status**: Draft  
**Input**: Bug report - Interface type incorrectly mapped during discovery

## Clarifications

### Session 2026-05-08

- Q: Should correction address TYPE only, SPEED only, or BOTH when mismatch detected? → A: TYPE is determined by interface name (authoritative). SPEED is taken from actual device state as reported by collector. Example: GigabitEthernet interface with 100 Mbps active speed has type=1000base-t but speed=100000 kbps.
- Q: For interface SPEED, use configured speed or active/negotiated speed? → A: Use active/negotiated speed (what device is currently running at, reflects actual state).
- Q: Should this fix apply to Cisco only, or multiple vendors? → A: Cisco only. Apply type/speed correction only to Cisco IOS/IOS-XE interfaces (GigabitEthernet, FastEthernet, etc.).
- Q: For Cisco interfaces with unknown names (e.g., eth0, port1), skip correction or infer? → A: Correct known names only. Only apply corrections to recognized Cisco interface patterns (GigabitEthernet, FastEthernet); skip unknown names.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Correct Type Classification for Gigabit Interfaces (Priority: P1)

Network operators discover Cisco Catalyst switches with gigabit interfaces (GigabitEthernet1/0/x) via orbweaver. Currently, these interfaces are being incorrectly classified with type `100base-tx` (100 Mbit/s) when they should be classified as `1000base-t` (1000 Mbit/s) based on the interface name and actual device capabilities.

**Why this priority**: Incorrect interface type classification directly impacts NetBox data accuracy and downstream automation. Operators rely on accurate interface type to make routing, sizing, and capacity planning decisions. P1 because this affects core discovery data integrity.

**Independent Test**: Discover a Cisco Catalyst switch with gigabit interfaces via a collector. Verify that:
- Interface type is correctly mapped to `1000base-t` (based on GigabitEthernet name)
- Speed reflects actual device state (e.g., 100000 kbps if device reports 100 Mbps active speed, or 1000000 kbps if running at full speed)
- NetBox ingestion receives correct type and speed information

**Acceptance Scenarios**:

1. **Given** a Cisco IOS device with interface named `GigabitEthernet1/0/20` running at 1000 Mbps, **When** discovered via cisco_ios collector, **Then** the interface type is set to `1000base-t` with speed 1000000 kbps
2. **Given** the same interface running at 100 Mbps (negotiated down), **When** discovered, **Then** type is still `1000base-t` but speed is 100000 kbps (reflects actual device state)
3. **Given** a Cisco NX-OS device with interface named `Eth1/1`, **When** discovered via collector, **Then** interface type reflects the interface class (not upstream NAPALM misclassification)

---

### User Story 2 - Fast Ethernet/100BASE-TX Validation (Priority: P2)

Network operators discover older switches or interfaces that genuinely operate at 100 Mbps. The fix must not over-correct—interfaces named FastEthernet or with type 100base-tx that are actually 100 Mbit should remain classified as such.

**Why this priority**: Ensure the fix only corrects GigabitEthernet interfaces; genuine FastEthernet interfaces must not be misclassified. P2 because this affects backward compatibility.

**Independent Test**: Discover a mix of interface types on the same device. Verify:
- FastEthernet interfaces retain type `100base-tx` regardless of actual speed
- GigabitEthernet interfaces have type `1000base-t` regardless of actual speed
- Speed values accurately reflect current device state
- No regression in existing correct mappings

**Acceptance Scenarios**:

1. **Given** an interface named `FastEthernet0/1` on a legacy device, **When** discovered, **Then** type remains `100base-tx` with speed 100000 kbps
2. **Given** mixed interfaces (Gi1/0/1 = gigabit, Fa0/1 = fast) on same device, **When** discovered, **Then** each is correctly classified by its actual type

---

### User Story 3 - Type/Speed Consistency Validation (Priority: P3)

Add validation logic to detect and log type/speed mismatches during discovery. This helps identify future bugs and data quality issues from upstream NAPALM.

**Why this priority**: Improves observability and helps catch similar issues in the future. P3 because this is observability/debugging, not a functional requirement for correctness.

**Independent Test**: Discovery logs include warnings for any detected type/speed mismatches that weren't corrected. Operators can audit discovery logs for data quality.

**Acceptance Scenarios**:

1. **Given** upstream NAPALM returns conflicting type/speed data, **When** collector processes it, **Then** a log entry records the mismatch (before and after correction)
2. **Given** a successful discovery, **When** operator reviews logs, **Then** they can identify which interfaces had automatic corrections applied

---

### Edge Cases

- Interfaces with unknown/non-standard Cisco names (e.g., `eth0`, `port1`): correction skipped; interface left as-is from NAPALM
- GigabitEthernet interface with active speed slower than 1000 Mbps: type=1000base-t, speed reflects actual negotiated speed
- FastEthernet interface: correction skipped (assumed correct as 100base-tx)
- Mixed interfaces on same device: each corrected independently by name pattern matching

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST determine Cisco interface TYPE based on interface name/class (e.g., GigabitEthernet → `1000base-t`, FastEthernet → `100base-tx`) regardless of upstream NAPALM classification
- **FR-002**: System MUST set interface SPEED from actual active/negotiated device state as reported by collector (authoritative source)
- **FR-003**: System MUST log any type corrections applied during discovery for audit and observability
- **FR-004**: Correction logic MUST apply to Cisco IOS/IOS-XE interfaces (Cisco devices only; Aruba and other vendors out of scope)
- **FR-005**: Example: GigabitEthernet interface at 100 Mbps negotiated speed MUST have type=`1000base-t` but speed=100000 kbps
- **FR-006**: System MUST NOT introduce regressions—interfaces with correct name-based mappings must remain unchanged

### Key Entities *(include if feature involves data)*

- **NormalizedInterface**: Device interface representation, contains `name`, `type`, `speed` attributes. The bug manifests in incorrect `type` value relative to actual device capability.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All Cisco Catalyst GigabitEthernet interfaces discovered from real devices must have type `1000base-t` (100% accuracy vs. current 0%)
- **SC-002**: Speed values accurately reflect actual device state, not forced to match type classification (100% accuracy)
- **SC-003**: No regression in existing FastEthernet interface mappings—type remains `100base-tx` (100% accuracy maintained)
- **SC-004**: Discovery includes audit log entries for any type corrections (100% traceability)
- **SC-005**: All existing tests pass; new tests cover the corrected mappings and speed independence (100% test coverage for fix)

## Assumptions

- Interface TYPE is authoritative based on Cisco interface name/class (GigabitEthernet → 1000base-t, FastEthernet → 100base-tx)
- Interface SPEED is authoritative from actual active/negotiated device state as reported by collector
- TYPE and SPEED are independent—an interface can have 1000base-t type but 100000 kbps speed if device is negotiated down
- The bug occurs in the collector mapping layer, not in upstream NAPALM device drivers
- Cisco IOS/IOS-XE interface naming conventions are stable (GigabitEthernet, FastEthernet, Ethernet naming schemes)
- **SCOPE: Cisco devices only** — fix applies to cisco_ios collector and NAPALM when collecting from Cisco devices
- Aruba AOS-CX and other non-Cisco vendors are out of scope for this fix
- Existing data in NetBox is not corrected retroactively; only new discoveries apply the fix
