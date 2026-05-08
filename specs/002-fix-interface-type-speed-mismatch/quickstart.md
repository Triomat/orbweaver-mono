# Quickstart: Cisco Interface Type/Speed Mismatch Fix

## Goal

Implement and validate the Cisco IOS/IOS-XE interface type correction without changing shared upstream code under `backend/`.

## Implementation Steps

1. Add a new orbweaver test module for Cisco interface normalization behavior.
2. Write failing tests for:
   - `GigabitEthernet` at 1000 Mbps -> `type=1000base-t`, `speed=1000000`
   - `GigabitEthernet` at 100 Mbps -> `type=1000base-t`, `speed=100000`
   - `FastEthernet` -> `type=100base-tx`
   - mixed `Gi` and `Fa` interfaces on the same device
   - unknown names left unchanged
3. Add a Cisco-only correction helper in `orbweaver/collectors/cisco_ios.py`.
4. Apply the correction after `build_interfaces_from_napalm()` returns interfaces.
5. Log only actual type corrections.
6. Update test command wiring if needed so orbweaver tests are part of the normal backend validation path.

## Suggested Validation Commands

Run the narrowest checks first:

```bash
# Linux/macOS venv
./.venv/bin/python -m pytest orbweaver/tests/test_cisco_ios_interface_types.py -v

# Windows-style venv checked out into this workspace
./.venv/Scripts/python.exe -m pytest orbweaver/tests/test_cisco_ios_interface_types.py -v

just check-syntax
just check-imports
just test-legacy
```

If the feature updates repo test wiring, finish with:

```bash
just test
```

## Expected Outcome

- Cisco `GigabitEthernet` interfaces always normalize to `1000base-t`.
- Cisco `FastEthernet` interfaces normalize to `100base-tx`.
- Negotiated speed remains independent from type.
- Automatic corrections are visible in collector logs.