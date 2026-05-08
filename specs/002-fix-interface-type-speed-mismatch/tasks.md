# Tasks: Cisco Interface Type/Speed Mismatch Fix

**Input**: Design documents from `/specs/002-fix-interface-type-speed-mismatch/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md, contracts/

**Tests**: Required. The plan and constitution require test-first coverage for each behavior change in orbweaver.
**Organization**: Tasks are grouped by user story so each story can be implemented and validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: User story label for story-specific phases only
- Every task includes an exact file path

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare the feature slice and validation surface for implementation.

- [x] T001 Review current Cisco interface normalization path in `orbweaver/collectors/cisco_ios.py` and shared inference usage in `orbweaver/collectors/napalm_helpers.py`
- [x] T002 Review current test wiring in `justfile` and confirm orbweaver collector tests are not yet included in the default workflow

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the test harness and fixture structure that all user-story work depends on.

**⚠️ CRITICAL**: No user story implementation should begin until this phase is complete.

- [x] T003 Create test module scaffold for Cisco collector normalization in `orbweaver/tests/test_cisco_ios_interface_types.py`
- [x] T004 [P] Add reusable mocked NAPALM interface payload fixtures in `orbweaver/tests/test_cisco_ios_interface_types.py`
- [x] T005 [P] Add helper setup for constructing or mocking `CiscoCollector` behavior in `orbweaver/tests/test_cisco_ios_interface_types.py`

**Checkpoint**: Test harness ready; story work can begin.

---

## Phase 3: User Story 1 - Correct Type Classification for Gigabit Interfaces (Priority: P1) 🎯 MVP

**Goal**: Ensure Cisco GigabitEthernet interfaces normalize to the correct interface type while preserving negotiated speed.

**Independent Test**: Run focused orbweaver tests proving a Cisco `GigabitEthernet` or `Gi` interface is always emitted as `1000base-t`, while speed remains whatever active/negotiated value the collector reports.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T006 [P] [US1] Add failing test for `GigabitEthernet*` at 1000 Mbps in `orbweaver/tests/test_cisco_ios_interface_types.py`
- [x] T007 [P] [US1] Add failing test for `GigabitEthernet*` negotiated down to 100 Mbps in `orbweaver/tests/test_cisco_ios_interface_types.py`
- [x] T008 [P] [US1] Add failing test for abbreviated `Gi*` interface names in `orbweaver/tests/test_cisco_ios_interface_types.py`

### Implementation for User Story 1

- [x] T009 [US1] Add a private Cisco name-to-type mapping helper in `orbweaver/collectors/cisco_ios.py`
- [x] T010 [US1] Apply the Cisco type correction pass after shared NAPALM normalization in `orbweaver/collectors/cisco_ios.py`
- [x] T011 [US1] Preserve negotiated speed unchanged while correcting only interface type in `orbweaver/collectors/cisco_ios.py`
- [x] T012 [US1] Run `.venv/bin/pytest orbweaver/tests/test_cisco_ios_interface_types.py -v` and fix failures until the US1 cases pass

**Checkpoint**: User Story 1 is functional and independently testable.

---

## Phase 4: User Story 2 - Fast Ethernet/100BASE-TX Validation (Priority: P2)

**Goal**: Prevent over-correction by keeping FastEthernet mappings intact and leaving unknown Cisco names unchanged.

**Independent Test**: Run focused tests proving `FastEthernet` and `Fa` interfaces remain `100base-tx`, mixed `Gi`/`Fa` sets normalize correctly together, and unknown names are left unchanged.

### Tests for User Story 2 ⚠️

- [x] T013 [P] [US2] Add failing test for `FastEthernet*` normalization in `orbweaver/tests/test_cisco_ios_interface_types.py`
- [x] T014 [P] [US2] Add failing test for abbreviated `Fa*` interface names in `orbweaver/tests/test_cisco_ios_interface_types.py`
- [x] T015 [P] [US2] Add failing mixed-interface regression test covering `Gi*` and `Fa*` together in `orbweaver/tests/test_cisco_ios_interface_types.py`
- [x] T016 [P] [US2] Add failing test proving unknown interface names are not rewritten in `orbweaver/tests/test_cisco_ios_interface_types.py`

### Implementation for User Story 2

- [x] T017 [US2] Extend the Cisco mapping helper to cover `FastEthernet*` and `Fa*` in `orbweaver/collectors/cisco_ios.py`
- [x] T018 [US2] Ensure unknown or unsupported Cisco interface names are skipped without type changes in `orbweaver/collectors/cisco_ios.py`
- [x] T019 [US2] Run `.venv/bin/pytest orbweaver/tests/test_cisco_ios_interface_types.py -v` and fix failures until the US1 and US2 cases pass

**Checkpoint**: User Stories 1 and 2 both work independently and together.

---

## Phase 5: User Story 3 - Type/Speed Consistency Validation (Priority: P3)

**Goal**: Emit an audit trail when Cisco interface type corrections are applied.

**Independent Test**: Run focused tests proving a correction log entry is emitted only when Cisco name-based authority changes the normalized type, and that already-correct values do not produce noise.

### Tests for User Story 3 ⚠️

- [x] T020 [P] [US3] Add failing log assertion for corrected interface types in `orbweaver/tests/test_cisco_ios_interface_types.py`
- [x] T021 [P] [US3] Add failing regression test proving already-correct interfaces do not emit correction logs in `orbweaver/tests/test_cisco_ios_interface_types.py`

### Implementation for User Story 3

- [x] T022 [US3] Add correction audit logging with host, interface name, original type, corrected type, and negotiated speed in `orbweaver/collectors/cisco_ios.py`
- [x] T023 [US3] Run `.venv/bin/pytest orbweaver/tests/test_cisco_ios_interface_types.py -v` and fix failures until logging behavior passes

**Checkpoint**: All user stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Integrate the new tests into normal repo validation and run full feature checks.

- [x] T024 Modify `justfile` so orbweaver collector tests are runnable through the normal validation workflow
- [x] T025 [P] Run `just check-syntax` and fix any feature-related syntax issues
- [x] T026 [P] Run `just check-imports` and fix any feature-related import issues
- [x] T027 Run `just test-legacy` to confirm upstream `backend/` behavior remains unchanged
- [x] T028 Run the updated repo test path from `justfile` to validate orbweaver and legacy tests together
- [x] T029 [P] Verify the implementation steps and expected outcome in `specs/002-fix-interface-type-speed-mismatch/quickstart.md` still match the final behavior

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion; blocks all user story work
- **User Story 1 (Phase 3)**: Depends on Foundational completion
- **User Story 2 (Phase 4)**: Depends on Foundational completion and benefits from the helper introduced in US1
- **User Story 3 (Phase 5)**: Depends on US1 correction behavior being implemented
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: MVP; no dependency on other stories after the foundational phase
- **US2 (P2)**: Depends on the same Cisco helper path as US1 but remains independently testable once implemented
- **US3 (P3)**: Depends on the correction pass from US1 so it can log only real corrections

### Within Each User Story

- Tests must be written and fail before implementation
- Helper logic before collector integration
- Collector behavior before repo-wide validation
- Story validation must pass before moving to the next dependent story

### Parallel Opportunities

- T004 and T005 can run in parallel after T003
- T006, T007, and T008 can run in parallel
- T013, T014, T015, and T016 can run in parallel
- T020 and T021 can run in parallel
- T025, T026, and T029 can run in parallel after implementation is complete

---

## Parallel Example: User Story 1

```bash
# Launch the US1 failing tests in parallel:
Task: "Add failing test for `GigabitEthernet*` at 1000 Mbps in orbweaver/tests/test_cisco_ios_interface_types.py"
Task: "Add failing test for `GigabitEthernet*` negotiated down to 100 Mbps in orbweaver/tests/test_cisco_ios_interface_types.py"
Task: "Add failing test for abbreviated `Gi*` interface names in orbweaver/tests/test_cisco_ios_interface_types.py"
```

---

## Parallel Example: User Story 2

```bash
# Launch the US2 regression tests in parallel:
Task: "Add failing test for `FastEthernet*` normalization in orbweaver/tests/test_cisco_ios_interface_types.py"
Task: "Add failing test for abbreviated `Fa*` interface names in orbweaver/tests/test_cisco_ios_interface_types.py"
Task: "Add failing mixed-interface regression test covering `Gi*` and `Fa*` together in orbweaver/tests/test_cisco_ios_interface_types.py"
Task: "Add failing test proving unknown interface names are not rewritten in orbweaver/tests/test_cisco_ios_interface_types.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Stop and validate with `.venv/bin/pytest orbweaver/tests/test_cisco_ios_interface_types.py -v`
5. Demo the corrected GigabitEthernet behavior before expanding scope

### Incremental Delivery

1. Finish Setup + Foundational to establish the test harness
2. Deliver US1 for the core GigabitEthernet correction
3. Deliver US2 for regression coverage and safe skip behavior
4. Deliver US3 for audit logging
5. Finish with repo-wide validation and `justfile` wiring

### Suggested MVP Scope

Implement **User Story 1 only** first. It fixes the reported production bug with the smallest safe change and provides the basis for the regression and observability follow-up work.
