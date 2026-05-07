# Tasks: Seed API — Interface and VLAN Population

**Input**: Design documents from `/specs/001-seed-interfaces-vlans/`
**Feature Branch**: `001-seed-interfaces-vlans`
**Status**: Implementation-ready

**Total Tasks**: 51 | P1 Tasks: 17 | P2 Tasks: 16 | P3 Tasks: 12 | Setup/Polish: 6

---

## Format Reference

- **[P]**: Task can run in parallel (no dependencies, different files)
- **[US#]**: Which user story (US1, US2, US3)
- **File paths**: Always included for exact implementation location

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Review existing seed structure in orbweaver/seed/ to understand current patterns
- [x] T002 Verify test environment setup in orbweaver/tests/ for seed-related tests
- [x] T003 [P] Document seed API behavior (create, skip, updated counters) in project notes

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No critical blockers identified. The feature extends existing seed patterns.

**Note**: Seed infrastructure is already in place. Task generation can proceed directly to user stories.

- [x] T004 Review `SeedResult` current structure in orbweaver/seed/models.py and plan `updated` counter extension
- [x] T005 Review `run_seed()` implementation in orbweaver/seed/loader.py to understand VLAN placement in pipeline

---

## Phase 3: User Story 2 — Seed VLANs as Top-Level Objects (Priority: P2) 🎯

**Goal**: Enable seeding of VLANs as independent objects before interfaces can reference them

**Independent Test**: Seed VLAN list with no devices/interfaces → verify NetBox contains correct VLAN records → re-post and verify skipped

### Implementation for User Story 2

- [x] T006 [P] [US2] Create `SeedVLAN` Pydantic model with validation in orbweaver/seed/models.py
  - Fields: vid (1-4094), name (1-64 chars), site (optional, for scoping)
  - Validators: range check on vid, prevent empty name

- [x] T007 [P] [US2] Extend `SeedData` model with `vlans: list[SeedVLAN] | None` field in orbweaver/seed/models.py
  - Ensure backward compatibility (all new fields optional)

- [x] T008 [US2] Extend `SeedResult` model to add counters in orbweaver/seed/models.py
  - Extend `created`, `skipped` with `vlans: int` field
  - Add new `updated` top-level counter with same counter structure
  - Ensure SeedCounter includes: sites, racks, devices, interfaces, vlans

- [x] T009 [P] [US2] Implement `_find_vlan()` helper in orbweaver/seed/loader.py
  - Lookup VLAN by (vid, site) tuple where site is optional (global VLAN when None)
  - Use pynetbox filters: `{"vid": vlan_spec.vid, "site_id": site_obj.id}` or `None` for global

- [x] T010 [P] [US2] Implement `_seed_vlans()` function in orbweaver/seed/loader.py
  - Signature: `_seed_vlans(netbox, vlans_list) → tuple[int, int, list[dict]]` (created, skipped, errors)
  - Loop through vlans_list, call `_find_vlan()` for existing check
  - If not found: create via `netbox.ipam.vlans.create()` with vid, name, site (if provided)
  - If found: increment skipped counter
  - Catch exceptions per item; append to errors list

- [x] T011 [US2] Integrate `_seed_vlans()` call into `run_seed()` in orbweaver/seed/loader.py
  - Place call BEFORE `_seed_interfaces()` in processing pipeline
  - Order: sites → racks → devices → **vlans (NEW)** → interfaces
  - Unpack return values into SeedResult counters

- [x] T012 [P] [US2] Write schema validation tests in orbweaver/tests/test_seed_models.py
  - Test SeedVLAN: vid in range [1, 4094] accepted; 0 and 4095 rejected with 422
  - Test SeedVLAN: name 1-64 chars required; empty or >64 rejected
  - Test SeedVLAN: site field optional; accepts site name string or None
  - Test SeedData: vlans field optional; accepts list of SeedVLAN or None

- [x] T013 [P] [US2] Write VLAN seeding functional tests in orbweaver/tests/test_seed_loader.py
  - Test create: POST payload with 2 VLANs → both created → response shows created.vlans=2
  - Test skip existing: re-POST same payload → both skipped → response shows skipped.vlans=2, created.vlans=0
  - Test site scoping: seed VLAN 100 for site-a, verify VLAN 100 for site-b can coexist
  - Test global VLAN: seed VLAN with no site → verify created without site_id in NetBox
  - Test error handling: try to create duplicate VLAN → skipped, no error (VLAN already exists)

**Checkpoint**: VLANs can be seeded as independent objects; all VLAN references in interfaces will resolve

---

## Phase 4: User Story 1 — Seed Device Interfaces with Descriptions (Priority: P1) 🎯

**Goal**: Enable seeding of device interfaces with descriptions; implement fill-in-blank update strategy for existing interfaces

**Independent Test**: Seed device with 2 interfaces → verify both created → re-post → verify both skipped (or updated if fields were empty)

### Implementation for User Story 1

- [x] T014 [P] [US1] Create `SeedInterface` Pydantic model in orbweaver/seed/models.py
  - Fields:
    - name: str (required, 1-64 chars)
    - description: str | None (optional, max 200 chars)
    - mac_address: str | None (optional, EUI-48 format validation: `^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$`)
    - type: str (default "1000base-t")
    - mode: str | None (optional, enum: access|tagged|tagged-all)
    - access_vlan: int | None (optional, 1-4094 range)
    - tagged_vlans: list[int] | None (optional, each VLAN 1-4094)
  - Validators:
    - No both access_vlan and tagged_vlans simultaneously (raise ValueError)
    - VLAN IDs in valid range
    - Extra forbid policy

- [x] T015 [P] [US1] Extend `SeedDevice` model in orbweaver/seed/models.py
  - Add field: `interfaces: list[SeedInterface] | None = None`
  - Add validator: ensure no duplicate interface names under same device
  - Validator rejects payload with duplicate names → ValidationError (422 on POST)

- [x] T016 [P] [US1] Implement `_find_interface()` helper in orbweaver/seed/loader.py
  - Lookup existing interface by device_id + interface name
  - Signature: `_find_interface(netbox, device_obj, name) → Interface | None`
  - Use pynetbox filter: `{"device_id": device_obj.id, "name": name}`

- [x] T017 [P] [US1] Implement `_apply_fill_in_blank()` function in orbweaver/seed/loader.py
  - Signature: `_apply_fill_in_blank(netbox, existing_iface, iface_spec) → int` (returns number of fields updated)
  - For each field in [description, mac_address, type, mode]:
    - Get seeded value from iface_spec
    - Get current value from existing_iface
    - If seeded value is not None AND current value is None or empty string:
      - Append to updates dict
  - If updates dict is not empty:
    - Call existing_iface.update(updates)
  - Return len(updates) (0 if no updates, >0 if updates applied)

- [x] T018 [P] [US1] Implement `_create_interface()` function in orbweaver/seed/loader.py
  - Signature: `_create_interface(netbox, device_obj, iface_spec) → Interface`
  - Build interface payload:
    - device: device_obj.id
    - name: iface_spec.name
    - type: iface_spec.type (defaults to "1000base-t")
    - description: iface_spec.description (if provided)
    - mac_address: iface_spec.mac_address (if provided)
    - mode: iface_spec.mode (if provided)
  - Call `netbox.dcim.interfaces.create(**payload)`
  - Return created interface object

- [x] T019 [US1] Implement `_seed_interfaces()` function in orbweaver/seed/loader.py
  - Signature: `_seed_interfaces(netbox, device_obj, interfaces_list) → tuple[int, int, int, list[dict]]` (created, updated, skipped, errors)
  - For each interface in interfaces_list:
    - Try block:
      - Call `_find_interface()` to check if exists
      - If exists:
        - Call `_apply_fill_in_blank()` to update empty fields
        - If updates applied (return > 0): increment updated counter
        - Else: increment skipped counter
      - If does not exist:
        - Call `_create_interface()` to create new
        - Increment created counter
    - Except block:
      - Append error dict to errors list (entity: "interface", device: device_obj.name, name: iface_spec.name, reason: str(exception))
  - Return (created, updated, skipped, errors)

- [x] T020 [US1] Integrate interface seeding into `run_seed()` in orbweaver/seed/loader.py
  - Modify device seeding loop to extract interfaces_list from each device
  - After device creation/skip, call `_seed_interfaces(netbox, device_obj, device.interfaces)` if interfaces present
  - Aggregate created/updated/skipped counts into SeedResult
  - Extend SeedResult.created.interfaces, .skipped.interfaces, .updated.interfaces

- [x] T021 [P] [US1] Write `SeedInterface` schema validation tests in orbweaver/tests/test_seed_models.py
  - Test required name field: missing or empty rejected with 422
  - Test name length: 1-64 chars accepted; 0 or >64 rejected
  - Test description: optional, max 200 chars; >200 rejected with 422
  - Test mac_address: EUI-48 format validation; invalid format rejected
  - Test type: defaults to "1000base-t"; accepts any string value
  - Test mode: accepts null or values in {access, tagged, tagged-all}; other values rejected with 422
  - Test access_vlan: accepts int 1-4094 or None; 0/4095 rejected; raises if both access_vlan and tagged_vlans set
  - Test tagged_vlans: accepts list of ints 1-4094 or None; each VLAN range checked; raises if both access_vlan and tagged_vlans set
  - Test duplicate interface names under same device: SeedDevice with duplicate interface names rejected with 422

- [x] T022 [P] [US1] Write interface creation tests in orbweaver/tests/test_seed_loader.py
  - Test create new: seed device with 2 interfaces → both created → created.interfaces=2
  - Test preserve template-created: device with auto-created interface from template, seed with same name + description → interface appears in updated (not skipped) if description was empty
  - Test re-post skipped: re-post same payload with description already set → interface skipped (no update)
  - Test description field: interface created with description exactly as provided (up to 200 chars)
  - Test mac_address field: interface created with mac_address if provided
  - Test device not found: interface under non-existent device → skipped with error recorded
  - Test invalid interface name: interface name >64 chars rejected at schema validation (422)

- [x] T023 [P] [US1] Write fill-in-blank update tests in orbweaver/tests/test_seed_loader.py
  - Test description fill-in: existing interface with empty description, seed with description → updated counter incremented
  - Test mac_address fill-in: existing interface with empty mac_address, seed with mac → updated counter incremented
  - Test preserve non-empty: existing interface with description set, seed with different description → preserved, skipped counter incremented
  - Test multiple fields: existing interface missing description AND mac_address, seed both → updated counter incremented once (counts interface, not fields)
  - Test mode fill-in: existing interface with null mode, seed with mode → updated counter incremented

**Checkpoint**: Interfaces can be seeded and filled-in-blank; US1 independently functional

---

## Phase 5: User Story 3 — Assign VLANs to Interfaces (Priority: P3)

**Goal**: Enable assignment of access or trunk VLANs to seeded interfaces; handle missing VLAN references gracefully

**Independent Test**: Seed device with interface in access mode referencing a VLAN → verify interface has correct access VLAN in NetBox

### Implementation for User Story 3

- [x] T024 [P] [US3] Extend `SeedInterface` model validation for VLAN modes in orbweaver/seed/models.py
  - Ensure schema already includes: mode, access_vlan, tagged_vlans fields (added in T014)
  - Add validator: if mode is "tagged", tagged_vlans must have at least 1 entry (reject if empty list)
  - Add validator: mode "tagged-all" allows no VLAN list (access_vlan and tagged_vlans ignored)
  - Existing validators ensure no both access_vlan and tagged_vlans simultaneously

- [x] T025 [P] [US3] Implement `_assign_vlans_to_interface()` function in orbweaver/seed/loader.py
  - Signature: `_assign_vlans_to_interface(netbox, iface_obj, iface_spec) → list[dict]` (returns error list)
  - If no mode specified: return empty errors list
  - If mode is "access":
    - If access_vlan provided:
      - Try to find VLAN by vid (handle site scoping if needed)
      - Call iface_obj.update({"mode": "access", "untagged_vlan": vlan_obj.id})
      - On error: append error dict (entity: "interface", reason: "Could not assign access VLAN X: {error}")
  - If mode is "tagged":
    - If tagged_vlans provided:
      - Try to find each VLAN by vid
      - Collect VLAN IDs
      - Call iface_obj.update({"mode": "tagged", "tagged_vlans": vlan_ids})
      - On error: append error dict
  - If mode is "tagged-all":
    - Call iface_obj.update({"mode": "tagged-all"})
    - No VLAN list needed
  - Return error list

- [x] T026 [US3] Integrate VLAN assignment into `_seed_interfaces()` in orbweaver/seed/loader.py
  - After interface is created or updated, call `_assign_vlans_to_interface()` to handle VLAN assignment
  - If assignment errors: append to errors list (do not fail the interface, just record error)
  - Continue with next interface regardless of VLAN assignment success/failure

- [x] T027 [P] [US3] Write VLAN assignment validation tests in orbweaver/tests/test_seed_models.py
  - Test mode "access" requires access_vlan: mode=access, no access_vlan → ValidationError (422)
  - Test mode "tagged" requires tagged_vlans: mode=tagged, no tagged_vlans → ValidationError (422)
  - Test conflicting modes: both access_vlan and tagged_vlans set → ValidationError (422)
  - Test mode "tagged-all" ignores VLAN fields: mode=tagged-all, access_vlan and tagged_vlans set → accepted, VLAN fields ignored
  - Test tagged_vlans list: accepts [10, 20, 30]; rejects if contains VLAN outside 1-4094 range

- [x] T028 [P] [US3] Write VLAN assignment functional tests in orbweaver/tests/test_seed_loader.py
  - Test access mode: seed interface with mode=access, access_vlan=100 → interface in NetBox shows access mode, untagged_vlan=VLAN100
  - Test tagged mode: seed interface with mode=tagged, tagged_vlans=[10, 20] → interface shows tagged mode, tagged_vlans list contains both
  - Test tagged-all mode: seed interface with mode=tagged-all → interface shows tagged-all mode
  - Test missing VLAN (access): interface references non-existent VLAN 999 → interface created without VLAN, error in errors list, interface not failed
  - Test missing VLAN (tagged): interface references tagged_vlans including non-existent VLAN → error recorded, interface creation not blocked
  - Test VLAN assignment fill-in-blank: existing interface with no mode set, seed with mode=access + access_vlan → fill-in-blank applies, updated counter incremented
  - Test re-post with same VLAN: post interface with access VLAN 100, then re-post same → skipped or updated depending on whether mode field already set

- [x] T029 [P] [US3] Write edge case tests in orbweaver/tests/test_seed_loader.py
  - Test site-scoped VLAN: interface in device at site-a references VLAN 100 → must resolve to VLAN 100 scoped to site-a (not global VLAN 100)
  - Test global VLAN: interface references VLAN that has no site scope → correctly resolves
  - Test payload validation: duplicate interface names in payload rejected before any seeding → 422, no interfaces created
  - Test payload validation: both access_vlan and tagged_vlans in same interface → 422, no interfaces created

**Checkpoint**: VLANs can be assigned to interfaces; US3 independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Integration, documentation, and final validation

- [x] T030 [P] Update API documentation in orbweaver/app.py to document new seed payload fields
  - Document SeedVLAN structure in request body example
  - Document SeedInterface structure with all optional fields
  - Document new SeedResult counters (updated, interfaces, vlans)

- [x] T031 [P] Add integration test in orbweaver/tests/test_seed_loader.py
  - Full workflow test: single payload with sites, devices, vlans, interfaces, VLAN assignments
  - Verify all counters populated correctly
  - Verify NetBox contains all created objects with correct relationships
  - Verify re-posting same payload results in skipped (or updated) counts

- [x] T032 Run existing upstream seed tests to ensure backward compatibility
  - Execute `just test-legacy` or direct pytest on backend/tests/
  - Verify all existing `test_seed_*.py` tests pass unchanged
  - Verify no regressions to existing device/site/rack seeding

- [ ] T033 [P] Manual functional testing with Docker Compose
  - Start docker stack: `just docker-up`
  - POST seed payload with VLANs and interfaces to `/api/v1/seed`
  - Verify response structure (created, skipped, updated, errors)
  - Inspect NetBox UI to confirm VLANs and interfaces present with correct data
  - Test fill-in-blank: re-post and verify updated counters

- [x] T034 Add example seed payloads to documentation
  - Create orbweaver/docs/seed-examples.md or update docker/policy-example.yaml
  - Example 1: Bare device with interfaces (no VLANs)
  - Example 2: Device with interfaces + VLAN assignments (access mode)
  - Example 3: Device with interfaces + VLAN assignments (tagged mode)
  - Example 4: Pre-seeded VLANs at top level, then devices with interfaces referencing those VLANs

- [ ] T035 [P] Final code review and cleanup
  - Review orbweaver/seed/models.py for consistency with existing patterns
  - Review orbweaver/seed/loader.py for docstrings and inline comments
  - Verify error messages are clear and actionable
  - Check import organization (no circular dependencies)
  - Run `just lint` and `just check-syntax` to ensure no style violations

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup
- **User Story 2 - VLANs (Phase 3)**: Depends on Foundational
- **User Story 1 - Interfaces (Phase 4)**: Depends on US2 (must seed VLANs before interfaces reference them)
- **User Story 3 - VLAN Assignment (Phase 5)**: Depends on US1 and US2 (needs both interfaces and VLANs)
- **Polish (Phase 6)**: Depends on all user stories

### Task Dependencies Within Phases

**Phase 3 (VLANs)**:
- T006 (SeedVLAN model) → T007 (extend SeedData) → T008 (extend SeedResult)
- T009, T010 can run in parallel (both depend on T006)
- T011 depends on T010
- T012, T013 can run in parallel (both depend on T006, T007, T008, T010)

**Phase 4 (Interfaces)**:
- T014 (SeedInterface model) → T015 (extend SeedDevice)
- T016, T017, T018 can run in parallel (all depend on T014)
- T019 depends on T016, T017, T018
- T020 depends on T019
- T021, T022, T023 can run in parallel (all depend on T014, T015, T019)

**Phase 5 (VLAN Assignment)**:
- T024 depends on T014 (SeedInterface already has fields, just validate)
- T025 depends on T024, T010 (needs to find VLANs)
- T026 depends on T025, T019
- T027, T028, T029 can run in parallel (all depend on T024, T025, T026)

**Phase 6 (Polish)**:
- T030, T031, T033, T034, T035 can mostly run in parallel after Phase 5 complete
- T032 can run at any time (existing tests)

### Parallel Opportunities

**All Phase 1 tasks**: Can run in parallel (no dependencies on each other)

**Phase 3 VLAN seeding**:
- T009 & T010 (helpers) can run in parallel
- T012 & T013 (tests) can run in parallel while T011 (integration) is being done

**Phase 4 Interface seeding**:
- T016, T017, T018 (helpers) can run in parallel
- T021, T022, T023 (tests) can run in parallel while T020 (integration) is being done

**Phase 5 VLAN assignment**:
- T027, T028, T029 (tests) can run in parallel while T026 (integration) is being done

**Phase 6 Polish**:
- T030, T033, T034, T035 can run in parallel
- T032 (backward compatibility) can run anytime

### Optimal Execution Timeline

**Sequential (if one developer)**:
- Phase 1 (1 day)
- Phase 2 (1 day)
- Phase 3 VLANs (2 days: T006-T011 serial, then T012-T013 in parallel)
- Phase 4 Interfaces (3 days: T014-T020 serial with T021-T023 in parallel)
- Phase 5 VLAN Assignment (3 days: T024-T026 serial with T027-T029 in parallel)
- Phase 6 Polish (1-2 days)
- **Total: ~11-12 days**

**Parallel (if 2-3 developers)**:
- Phases 1-2 in parallel (2 days)
- Phase 3 fully parallel (2 days)
- Phase 4 fully parallel (3 days)
- Phase 5 fully parallel (3 days)
- Phase 6 parallel (1 day)
- **Total: ~8-9 days**

---

## Acceptance Criteria Summary

### User Story 2 (VLANs) - Complete When:
- ✓ Can POST VLAN list; both appear in NetBox
- ✓ Re-posting same payload results in skipped counters (no created)
- ✓ Invalid payloads (vid out of range, duplicate names) return HTTP 422
- ✓ Site-scoped VLANs are matched by (vid, site) tuple
- ✓ All schema validation tests pass

### User Story 1 (Interfaces) - Complete When:
- ✓ Can POST device with 2 interfaces; both created in NetBox
- ✓ Re-posting results in skipped or updated (if fields were empty)
- ✓ Template-generated interface with empty description receives seeded description (updated counter increments)
- ✓ Invalid payloads (duplicate names, description >200 chars) return HTTP 422
- ✓ All fill-in-blank update tests pass
- ✓ Existing interfaces with data set outside seed are never overwritten

### User Story 3 (VLAN Assignment) - Complete When:
- ✓ Interface with mode=access and access_vlan=100 shows correct access VLAN in NetBox
- ✓ Interface with mode=tagged and tagged_vlans=[10, 20] shows tagged list in NetBox
- ✓ Missing VLAN reference results in error recorded (not interface failure)
- ✓ Invalid payloads (both access_vlan and tagged_vlans) return HTTP 422
- ✓ All VLAN assignment tests pass

### Cross-Story:
- ✓ All existing upstream tests continue to pass (no regressions)
- ✓ SeedResult response includes created/skipped/updated with interfaces and vlans counters
- ✓ Errors recorded per item; single bad item does not block others
- ✓ Full integration test with sites, devices, VLANs, interfaces, assignments succeeds
