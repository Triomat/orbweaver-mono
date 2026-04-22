# Rack Assignment for Imported Devices

**Date:** 2026-04-22
**Status:** Approved

## Summary

Add support for assigning a NetBox rack to imported devices. Rack is specified by name only; devices appear in the rack's "Non-racked Devices" section (no U position or face). Rack can be set at the policy defaults level (applies to all devices in the policy) or overridden per device in the scope. Both YAML and the UI form expose the field.

## Architecture

Rack flows through the same three-layer pipeline used by tenant:

```
Policy YAML (defaults.rack / scope[].rack)
  ↓ patches.py  — monkey-patch Defaults + Napalm; inject into NormalizedDevice
  ↓ COM         — NormalizedDevice.rack: str
  ↓ diode_translate.py — Rack(name, site) → Device(rack=...)
  ↓ Diode SDK   → NetBox
```

Rack is not discoverable from the device itself. It is purely a policy-supplied value.

## Components

### 1. `orbweaver/models/common.py`

Add to `NormalizedDevice`:
```python
rack: str = ""
```

The default ensures existing review session JSON files (which lack this key) deserialize without error via dacite.

### 2. `orbweaver/patches.py`

Two Pydantic model patches (same pattern as `Napalm.collector`):

- `Defaults.rack: str | None = None` — policy-level default
- `Napalm.rack: str | None = None` — per-device override in scope

After `collector.discover_single()` in `_collect_device_data_via_collector`, inject rack into the COM:
```python
normalized_device.rack = scope.rack or getattr(_defaults, "rack", None) or ""
```
Per-device value wins; defaults is the fallback; empty string means no rack assigned.

### 3. `orbweaver/diode_translate.py`

In `_translate_device()`, build a `Rack` object when rack is set:
```python
rack_obj = Rack(name=device.rack, site=site_name) if device.rack else None
```
Pass `rack=rack_obj` to `Device(...)`.

Apply rack consistently to all three `Device(...)` constructions to prevent reconciler clobbering:
- `_translate_device()` — main device entity (pass 1)
- `device_ref` in `_translate_interface()` — nested device ref in interface/IP entities
- `translate_primary_ip_entities()` — pass-2 primary IP entity

### 4. `frontend/app/composables/useConfig.ts`

- Add `rack: string` to `PolicyForm.defaults`
- Add `rack: string` to `DeviceEntry`
- `defaultPolicy()` and `defaultDevice()` initialise rack to `''`
- `_buildPolicyObject()`: emit `defaults.rack` if non-empty; emit `rack` on each scope entry if non-empty
- `yamlToForm()`: parse `defaults.rack` and per-device `rack` from scope entries

### 5. `frontend/app/pages/config.vue`

- **Defaults section**: add a "Rack" text input after the Tenant field
- **Device table**: add a "Rack" column; blank means "use default"

## Data Flow Example

Policy YAML:
```yaml
policies:
  dc1-access:
    config:
      defaults:
        site: DC1
        rack: Rack-A1        # all devices default to this rack
    scope:
      - hostname: 10.0.0.1
        username: admin
        password: secret
        collector: cisco_ios
      - hostname: 10.0.0.2
        username: admin
        password: secret
        collector: cisco_ios
        rack: Rack-A2        # this device overrides to a different rack
```

Results in NetBox:
- `10.0.0.1` → assigned to Rack-A1 (non-racked)
- `10.0.0.2` → assigned to Rack-A2 (non-racked)

## Review Sessions

`NormalizedDevice.rack` is serialized to disk as part of the review session JSON. Review sessions created after this change will include rack. Existing sessions without rack deserialize correctly via dacite (field has a default of `""`). When a review session is ingested, rack passes through `device_from_dict()` → `diode_translate` → Diode automatically.

## Out of Scope

- Rack U position and face (device always placed as non-racked)
- Auto-discovering rack from device (not possible via CLI/SNMP)
- Rack creation — Diode will create the rack in NetBox if it does not exist
