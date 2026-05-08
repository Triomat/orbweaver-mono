# Design: Cisco Interface Type/Speed Mismatch Fix

## Objective

Correct Cisco IOS/IOS-XE interface normalization so `NormalizedInterface.type` is derived from known Cisco interface name patterns, while `NormalizedInterface.speed` continues to reflect the device's active negotiated state.

## Root Cause

The current path is:

1. `CiscoCollector._collect_interfaces()` calls `napalm_get_interfaces()`.
2. `build_interfaces_from_napalm()` converts NAPALM output into `NormalizedInterface` objects.
3. `build_interfaces_from_napalm()` uses `infer_interface_type(name, speed_mbps)`.
4. For physical Cisco ports, `infer_interface_type()` falls back to `speed_to_type(speed_mbps)`.

Because the fallback is speed-based, a `GigabitEthernet` interface negotiated down to 100 Mbps is emitted as `100base-tx` instead of `1000base-t`.

## Design Decisions

### Collector-local correction

The correction stays in `orbweaver/collectors/cisco_ios.py` so the fix is vendor-specific and does not alter shared behavior for Aruba or generic NAPALM collectors.

### Explicit Cisco name rules

The first implementation supports these rules:

- `GigabitEthernet*` and `Gi*` -> `1000base-t`
- `FastEthernet*` and `Fa*` -> `100base-tx`

Unknown names are left unchanged.

### Independent type and speed

The collector will treat these fields independently:

- `type`: authoritative from Cisco interface class/name
- `speed`: authoritative from NAPALM's active/negotiated interface speed

Example: `GigabitEthernet1/0/20` negotiated at 100 Mbps becomes `type=1000base-t`, `speed=100000`.

### Audit logging

When the collector changes an interface type, it will log a correction event with:

- host
- interface name
- original type
- corrected type
- negotiated speed

This creates a clear audit trail without adding persistence or API changes.

## Implementation Phases

### Phase 1: Test-first coverage

- Add an orbweaver collector test module.
- Create failing tests for gigabit interfaces at full speed and negotiated-down speed.
- Add regression tests for `FastEthernet`, mixed interface sets, and unknown names.

### Phase 2: Cisco collector correction pass

- Add a private helper in `CiscoCollector` that returns an authoritative Cisco type for recognized names.
- Apply the helper after `build_interfaces_from_napalm()` has created the COM objects.
- Keep speed untouched.
- Emit a log entry only when the helper changes `iface.type`.

### Phase 3: Validation and repo wiring

- Ensure the new orbweaver tests are runnable with repo-standard commands.
- Re-run orbweaver collector tests, import checks, syntax checks, and upstream legacy tests.

## File Impact Map

| File | Planned Change |
|------|----------------|
| `orbweaver/collectors/cisco_ios.py` | Add Cisco name-based type correction helper and audit logging in `_collect_interfaces()` |
| `orbweaver/tests/test_cisco_ios_interface_types.py` | Add collector-focused unit tests for corrected mapping behavior |
| `justfile` | Update or extend test commands so orbweaver tests run in the normal workflow |
| `orbweaver/collectors/napalm_helpers.py` | No planned behavior change; referenced as the root cause path |
| `backend/**` | No changes |

## Validation Strategy

- Unit test direct correction behavior for recognized Cisco names.
- Verify `speed` values remain unchanged when `type` is corrected.
- Verify unknown interface names are skipped.
- Verify upstream tests still pass, confirming no global behavior drift.