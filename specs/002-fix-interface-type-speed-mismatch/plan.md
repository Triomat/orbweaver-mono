# Implementation Plan: Cisco Interface Type/Speed Mismatch Fix

**Branch**: `002-fix-interface-type-speed-mismatch` | **Date**: 2026-05-08 | **Spec**: `specs/002-fix-interface-type-speed-mismatch/spec.md`
**Input**: Feature specification from `/specs/002-fix-interface-type-speed-mismatch/spec.md`

## Summary

Cisco interface normalization currently inherits interface `type` from the shared NAPALM helper's speed-based inference, which misclassifies `GigabitEthernet` ports as `100base-tx` when the negotiated speed is 100 Mbps. The fix will add a Cisco-only post-normalization correction pass inside `CiscoCollector._collect_interfaces()` that maps recognized Cisco interface names to authoritative COM interface types while preserving negotiated speed from device state. The implementation will log each applied correction for auditability, skip unknown names, keep `backend/` untouched, and add focused orbweaver-side tests plus test-runner wiring.

## Technical Context

**Language/Version**: Python 3.10+ package target, pytest-based development workflow  
**Primary Dependencies**: orbweaver collector layer, NAPALM `ios` driver, FastAPI extension package, pytest  
**Storage**: N/A  
**Testing**: pytest, existing `just test` / `just test-legacy`, direct orbweaver pytest invocation until repo test recipe includes orbweaver tests  
**Target Platform**: Linux server running the orbweaver backend  
**Project Type**: Python monorepo backend extension package  
**Performance Goals**: No material regression in per-device interface collection time; correction remains a single in-memory pass over collected Cisco interfaces  
**Constraints**: No edits under `backend/`; Cisco IOS/IOS-XE only; only recognized Cisco interface names are corrected; interface `type` and `speed` remain independent; correction logs must not include secrets  
**Scale/Scope**: One vendor collector (`orbweaver/collectors/cisco_ios.py`), one new orbweaver test module, minimal test command wiring, no API contract changes  

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Upstream Immutability**: PASS. The fix is isolated to `orbweaver/` and test tooling; `backend/` remains untouched.
- **II. Extension Over Modification**: PASS. Vendor-specific behavior stays in `orbweaver/collectors/cisco_ios.py` instead of changing upstream or monkey-patched backend code.
- **III. COM as Canonical Data Layer**: PASS. The collector still emits `NormalizedInterface`; only the derivation of its `type` changes for Cisco interfaces.
- **IV. Pluggable Collector Registry**: PASS. No registry or collector selection changes are required.
- **V. Simplicity & YAGNI**: PASS. The design adds a small Cisco-only correction helper and avoids introducing a new shared abstraction or cross-vendor policy engine.
- **VI. Test-Driven Development**: PASS. Implementation starts with focused failing tests for Cisco interface normalization and includes test-runner coverage updates.

**Post-Design Re-check**: PASS. The selected design remains collector-local, COM-preserving, and fully testable without broadening vendor scope.

## Project Structure

### Documentation (this feature)

```text
specs/002-fix-interface-type-speed-mismatch/
├── plan.md
├── design.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── README.md
└── tasks.md
```

### Source Code (repository root)

```text
orbweaver/
├── collectors/
│   ├── cisco_ios.py
│   └── napalm_helpers.py
├── models/
│   └── common.py
└── tests/
    └── test_cisco_ios_interface_types.py

backend/
└── tests/                     # untouched upstream tests

justfile                       # test recipe wiring
```

**Structure Decision**: Keep the bug fix in the Cisco collector after shared NAPALM normalization, introduce orbweaver-local tests for the collector behavior, and make only the minimum repo-level test command change needed to execute the new orbweaver tests.

## Technical Decisions

### 1. Correct type in the Cisco collector, not in shared NAPALM helpers

The root cause lives in the shared `build_interfaces_from_napalm()` path, where `infer_interface_type()` falls back to speed-based classification. Changing that shared helper would affect every NAPALM-backed collector. To preserve vendor boundaries and avoid regressions, `CiscoCollector._collect_interfaces()` will apply a Cisco-only correction step after `build_interfaces_from_napalm()` returns `NormalizedInterface` objects.

### 2. Name is authoritative for Cisco interface type; speed remains negotiated state

For recognized Cisco IOS/IOS-XE interface families, the collector will derive `type` from the interface name pattern and preserve `speed` from NAPALM's reported active speed. That keeps the clarified rule intact: `GigabitEthernet` can remain `1000base-t` while reporting `100000` Kbps.

### 3. Correct only known Cisco patterns and skip unknown names

The correction pass will handle explicit Cisco prefixes first: `GigabitEthernet` and `Gi` to `1000base-t`, `FastEthernet` and `Fa` to `100base-tx`. Unknown names such as `eth0`, `port1`, or other unlisted Cisco families will be left unchanged to avoid false positives.

### 4. Emit audit logs only when a correction changes the COM value

When a recognized Cisco interface name implies a different interface type than the current COM value, the collector will emit a structured log entry containing host, interface name, original type, corrected type, and negotiated speed. No log entry is needed when the inferred type is already correct.

### 5. Add orbweaver-side tests and ensure they are runnable through repo tooling

The feature requires focused unit tests for the Cisco collector's correction logic and regression checks for mixed interface sets. Because the current repo test recipe targets upstream `backend/tests`, the plan includes a minimal justfile adjustment so orbweaver tests can run consistently alongside existing checks.

## Phase Plan

### Phase 0: Research and Test Surface Confirmation

- Confirm the current root cause path: `napalm_helpers.build_interfaces_from_napalm()` derives `NormalizedInterface.type` from speed-based inference.
- Confirm the collector insertion point: `CiscoCollector._collect_interfaces()` already owns Cisco-specific enrichment and is the narrowest safe correction location.
- Confirm test harness gap: add new orbweaver-side collector tests and wire them into the repo workflow.

### Phase 1: Failing Tests First

- Add a new orbweaver test module for Cisco interface normalization.
- Cover `GigabitEthernet` at 1000 Mbps and 100 Mbps negotiated speeds.
- Cover `FastEthernet` retaining `100base-tx`.
- Cover mixed interface sets on the same device.
- Cover unknown interface names remaining unchanged.
- Decide whether to test the correction helper directly, `_collect_interfaces()` end-to-end with mocks, or both.

### Phase 2: Collector Implementation

- Add a private Cisco helper that maps recognized interface names to authoritative `InterfaceType` values.
- Call that helper from `_collect_interfaces()` after `build_interfaces_from_napalm()` and before switchport enrichment is finalized.
- Preserve `NormalizedInterface.speed` as collected from NAPALM.
- Log each applied correction with before/after values and negotiated speed.
- Keep `napalm_helpers.py` unchanged unless a tiny, clearly reusable utility extraction proves necessary during implementation.

### Phase 3: Validation and Regression Protection

- Run the new orbweaver test module directly.
- Run repo validation commands for syntax and imports.
- Run upstream legacy tests to confirm Cisco-specific behavior did not leak into `backend/` behavior.
- If justfile wiring is updated, validate the new combined test path through `just test`.

## File Impact Map

| Path | Change Type | Reason |
|------|-------------|--------|
| `orbweaver/collectors/cisco_ios.py` | Modify | Add Cisco-specific name-to-type correction pass and audit logging |
| `orbweaver/tests/test_cisco_ios_interface_types.py` | Add | Cover corrected type mapping, speed independence, mixed interfaces, and skip behavior |
| `justfile` | Modify | Ensure orbweaver tests are runnable through repo-standard commands |
| `orbweaver/collectors/napalm_helpers.py` | Reference only by default | Root cause source, but shared behavior should remain unchanged unless implementation proves a tiny reusable helper is worth extracting |
| `orbweaver/models/common.py` | Reference only | Existing `InterfaceType` and `NormalizedInterface` contracts remain unchanged |
| `backend/**` | No change allowed | Constitution rule: upstream code remains verbatim |

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Global helper change accidentally affects Aruba or generic NAPALM collectors | Cross-vendor regression | Keep correction in `CiscoCollector` only |
| Logs become noisy for already-correct interfaces | Reduced signal in audit trail | Log only when a correction actually changes `type` |
| Unknown Cisco interface families get over-corrected | Incorrect NetBox data | Restrict to explicit known prefixes and skip everything else |
| New orbweaver tests are not run by default | Regression risk | Update repo test wiring or document direct pytest command as an immediate validation path |

## Complexity Tracking

No constitution violations or special complexity exemptions are required for this feature.