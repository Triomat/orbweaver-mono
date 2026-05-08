# Feature Specification: Seed API — Interface and VLAN Population

**Feature Branch**: `001-seed-interfaces-vlans`
**Created**: 2026-05-07
**Status**: Draft
**Input**: User description: "addition to the seed api endpoint to populate devices with additional interfaces and corresponding interface descriptions and vlans. If the interface already exists, it should ignore the import and leave the information in netbox as is."

## Clarifications

### Session 2026-05-07

- Q: When a seed payload lists interfaces for a device that already has matching interfaces in NetBox (e.g. auto-created from device type templates), what should happen? → A: Skip creation; fill-in-blank — update `description`, `mac_address`, `mode`, and VLAN fields only when the existing NetBox value is empty/None.
- Q: Should `mac_address` be a first-class optional field on seeded interfaces? → A: Yes — `mac_address: str | None = None` on `SeedInterface`; supports pre-populating known MACs from inventory alongside description.
- Q: How should response counters reflect an existing interface that received fill-in-blank updates? → A: Add an `updated` counter; interfaces fall into exactly one of `created`, `skipped`, or `updated` per seed call.
- Q: Where should orbweaver-specific seed tests live? → A: `orbweaver/tests/`; new seed tests cover orbweaver-owned code and must not add new edits under `backend/`.
- Q: How should duplicate interface names under the same device in one payload be handled? → A: Reject the payload at schema validation time with HTTP 422.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Seed Device Interfaces with Descriptions (Priority: P1)

A network engineer maintains a YAML seed file that describes a lab environment. She wants to
pre-populate NetBox with specific interfaces on each device — including the interface description —
so that when the orbweaver discovery run completes, the discovered data can be correlated against
pre-seeded interfaces. She POSTs the YAML to `/api/v1/seed`. Interfaces that do not yet exist
are created; interfaces that already exist are either enriched via the fill-in-blank rule or
silently skipped when all seeded fields are already populated.

**Why this priority**: Core ask. Interface names + descriptions are the minimum useful unit.
Without this, the feature delivers no value.

**Independent Test**: Can be tested by seeding a device with two interfaces, verifying both are
created, then re-posting and verifying the result shows both skipped and no errors.

**Acceptance Scenarios**:

1. **Given** a seed payload with a device and two interfaces under that device,
   **When** the payload is POSTed to `/api/v1/seed`,
   **Then** both interfaces are created in NetBox under the correct device, and the response
   `created.interfaces` count equals 2.

2. **Given** a device in NetBox that already has an interface named `GigabitEthernet0/1`
   (e.g. auto-created from a device type template) with no description,
   **When** a seed payload referencing that same device and interface name is POSTed with a
   description value,
   **Then** the interface is not re-created, the description is written to NetBox (fill-in-blank),
  the response `updated.interfaces` count is 1, and no errors are returned.

3. **Given** a device in NetBox that already has an interface named `GigabitEthernet0/1`
   with a description already set,
   **When** a seed payload referencing that interface is POSTed with a different description,
  **Then** the existing description is preserved unchanged (no overwrite) and the interface
  appears in `skipped.interfaces`.

4. **Given** a seed payload with an interface that has a description of up to 200 characters,
   **When** the payload is POSTed,
   **Then** the interface is created with that description exactly as provided.

---

### User Story 2 — Seed VLANs as Top-Level Objects (Priority: P2)

A network engineer wants to define VLANs in the seed file so they exist in NetBox before interfaces
are configured. VLANs have a numeric ID (vid), a name, and an optional site scope. VLANs that
already exist in NetBox (matched by vid + site) are skipped.

**Why this priority**: VLANs must be present in NetBox before they can be assigned to interfaces.
This story is a prerequisite for US3.

**Independent Test**: Can be tested by seeding a VLAN list with no devices/interfaces. Verify
NetBox contains the correct VLAN records. Re-post and verify the result shows skipped, no created.

**Acceptance Scenarios**:

1. **Given** a seed payload with a `vlans` list containing two VLANs (one site-scoped, one global),
   **When** the payload is POSTed,
   **Then** both VLANs are created in NetBox and `created.vlans` equals 2.

2. **Given** a VLAN with vid=100 already exists for the given site in NetBox,
   **When** a seed payload containing that same vid + site is POSTed,
   **Then** the VLAN is skipped (`skipped.vlans` equals 1) and not modified.

---

### User Story 3 — Assign VLANs to Interfaces (Priority: P3)

A network engineer wants to assign access or trunk VLANs to seeded interfaces so that NetBox
reflects the intended switchport configuration. The seed payload specifies VLAN mode (`access`,
`tagged`, or `tagged-all`) and which VLANs apply.

**Why this priority**: Enhances the seeded data with switchport context, but only meaningful once
US1 and US2 are complete.

**Independent Test**: Can be tested by seeding a device with an interface in access mode
referencing a specific VLAN, then verifying the interface in NetBox has the correct mode and
access VLAN set.

**Acceptance Scenarios**:

1. **Given** an interface with `mode: access` and `access_vlan: 100` where VLAN 100 exists,
   **When** the payload is POSTed,
   **Then** the interface is created with access mode and VLAN 100 assigned as its access VLAN.

2. **Given** an interface with `mode: tagged` and `tagged_vlans: [10, 20]` where both VLANs exist,
   **When** the payload is POSTed,
   **Then** the interface is created with tagged mode and both VLANs in the tagged list.

3. **Given** an interface references a VLAN that is not present in NetBox (not seeded),
   **When** the payload is POSTed,
   **Then** the interface is still created (without the missing VLAN assignment), and an error
   entry is added to `errors` describing which VLAN could not be resolved.

---

### Edge Cases

- What happens when an interface is listed under a device that does not exist in NetBox? → The
  interface creation is skipped and an error is recorded; other items in the payload continue.
- What happens when the same interface name appears twice under the same device in the payload? →
  Payload validation rejects the request with HTTP 422 before any seed operation is attempted.
- What happens when `access_vlan` and `tagged_vlans` are both specified? → Payload validation
  rejects this as a schema error (422).
- What happens when mode is `tagged-all`? → No VLAN list is required; tagged_vlans and
  access_vlan are ignored even if provided.

## Requirements *(mandatory)*

### Functional Requirements

**FR-1**: The `SeedData` schema MUST accept an optional top-level `vlans` list. Each VLAN entry
MUST have a numeric `vid` (1–4094) and a `name`. An optional `site` field scopes the VLAN to a
specific site by name. When `site` is absent the VLAN is created without a site (global).

**FR-2**: Each `SeedDevice` MUST accept an optional `interfaces` list. Each interface entry MUST
have a `name` field. Optional fields: `description` (string), `mac_address` (string, EUI-48 format),
`type` (string, default `"1000base-t"`), `mode` (`access` | `tagged` | `tagged-all`),
`access_vlan` (int), `tagged_vlans` (list of int). Interface names within a single device payload
MUST be unique; duplicates are a schema validation error (422).

**FR-3**: The `run_seed()` function MUST process VLANs before interfaces so VLAN lookups during
interface assignment can succeed within the same seed call.

**FR-4**: Interface existence MUST be checked by device ID + interface name. If the interface
already exists, creation is skipped but a **fill-in-blank update** is applied: the fields
`description`, `mac_address`, `mode`, `access_vlan`, and `tagged_vlans` are written to NetBox
only when the corresponding value currently stored in NetBox is empty/None/blank. Fields that
already carry data in NetBox are never overwritten. This allows device-type template-generated
interfaces (auto-created by NetBox on device provisioning) to receive seeded metadata without
risking data loss.

**FR-5**: VLAN existence MUST be checked by `vid` + `site` (or absence of site for global VLANs).
If the VLAN already exists, it MUST be skipped without modification.

**FR-6**: The `SeedResult` response MUST include `interfaces` and `vlans` keys in `created`,
`skipped`, and a new `updated` counter. `updated.interfaces` increments when an existing interface
receives at least one fill-in-blank field write. An interface is counted in exactly one of
`created`, `skipped`, or `updated` per seed call — never more than one.

**FR-7**: When `mode` is `access`, `access_vlan` MUST reference a VID that resolves to a known
NetBox VLAN. When `mode` is `tagged`, `tagged_vlans` MUST contain at least one entry. Providing
both `access_vlan` and `tagged_vlans` simultaneously MUST be rejected at schema validation (422).

**FR-8**: Failures to create or look up an individual interface or VLAN MUST append to `errors`
and MUST NOT abort processing of subsequent items.

**FR-9**: All existing seed behavior (devices, sites, racks, etc.) MUST remain unchanged and all
existing upstream tests MUST continue to pass.

### Non-Functional Requirements

**NFR-1**: The existing `_get_or_create` helper pattern MUST be reused or extended; no duplicate
get-or-create logic should be introduced.

**NFR-2**: No new dependencies beyond what is already available in the orbweaver virtualenv.

## Success Criteria *(mandatory)*

1. A seed payload containing a device with two interfaces results in both interfaces visible in
   NetBox under that device, with the correct names and descriptions.
2. Re-posting the same payload after all fields are filled results in zero created, zero updated, zero errors; all interfaces appear in `skipped`.
3. A seed payload containing a `vlans` list results in those VLANs appearing in NetBox.
4. An interface with `mode: access` and a VLAN assignment shows the correct access VLAN in NetBox.
5. An interface with `mode: tagged` and a list of VLANs shows the tagged VLAN list in NetBox.
6. Invalid payloads (both `access_vlan` and `tagged_vlans` specified) return HTTP 422 with a
   clear validation message.
7. A template-generated interface with no description receives the seeded description and appears
   in `updated.interfaces`, not `skipped.interfaces`.
8. Invalid payloads containing duplicate interface names under the same device return HTTP 422
  before any objects are created or updated.
9. All pre-existing upstream test suite tests continue to pass after the changes.

## Key Entities *(optional)*

| Entity | Fields | Notes |
|--------|--------|-------|
| `SeedVLAN` | `vid: int`, `name: str`, `site: str \| None` | New Pydantic model in `models.py` |
| `SeedInterface` | `name: str`, `description: str`, `mac_address: str \| None`, `type: str`, `mode: str \| None`, `access_vlan: int \| None`, `tagged_vlans: list[int]` | New Pydantic model in `models.py` |
| `SeedDevice.interfaces` | `list[SeedInterface]` | New optional field on existing model |
| `SeedData.vlans` | `list[SeedVLAN]` | New optional top-level field |
| `SeedResult` | `created/skipped/updated` extended with `interfaces`, `vlans` | `updated` is new top-level counter; interfaces fall into exactly one bucket per call |

## Assumptions *(optional)*

- Interface `type` defaults to `"1000base-t"` when not specified; this is the most common physical
  type in the NetBox interface type list and avoids requiring the caller to always specify it.
- VLAN matching uses vid + site name (not site slug) for consistency with the rest of the seed
  YAML format.
- Global (non-site-scoped) VLANs are matched by vid alone when no site is specified.
- Interface VLAN assignment and MAC address apply the fill-in-blank rule: they are written only
  when the NetBox interface currently has no value for that field. This allows device-type
  template-generated interfaces to be enriched by seed without risk of overwriting data set
  outside of seed. It is intentional that seed never degrades existing NetBox data.
- The `mgmt0` management interface created by the existing `_assign_primary_ip` path is
  unaffected; `interfaces` items are additive and do not interact with that path.

## Scope *(optional)*

**In scope**:
- `orbweaver/seed/models.py` — new `SeedVLAN`, `SeedInterface` models; extend `SeedDevice` and
  `SeedData`
- `orbweaver/seed/loader.py` — VLAN and interface seeding steps in `run_seed()`; extend
  `SeedResult` counters
- `orbweaver/tests/test_seed_models.py` — new test cases for interface/VLAN schema validation
- `orbweaver/tests/test_seed_loader.py` — new test cases for interface/VLAN seeding behavior

**Out of scope**:
- Modifying existing interface records that were created outside of seed
- IP address assignment on seeded interfaces (that is handled by `primary_ip4` + the management
  interface path)
- Front-end UI changes
- Any changes under `backend/device_discovery/` (upstream immutability, Principle I)
