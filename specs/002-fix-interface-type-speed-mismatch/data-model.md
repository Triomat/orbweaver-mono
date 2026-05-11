# Data Model: Cisco Interface Type/Speed Mismatch Fix

## Overview

This feature does not introduce new persisted models. It changes how existing `NormalizedInterface` objects are populated by the Cisco collector.

## Entity: NormalizedInterface

**Source**: `orbweaver/models/common.py`

**Relevant fields**:

| Field | Type | Source after fix | Notes |
|------|------|------------------|-------|
| `name` | `str` | NAPALM interface key | Used as the authoritative signal for Cisco type correction |
| `type` | `InterfaceType` | Cisco collector correction pass | Derived from known Cisco name patterns when recognized |
| `speed` | `int | None` | NAPALM negotiated speed | Stored in Kbps; not overwritten by the type correction |
| `enabled` | `bool` | NAPALM | Unchanged |
| `description` | `str` | NAPALM | Unchanged |
| `mac_address` | `str` | NAPALM | Unchanged |
| `mtu` | `int | None` | NAPALM | Unchanged |

## Derived Rule Set: Cisco Interface Type Mapping

This rule set is internal to `CiscoCollector` and is not persisted.

| Name Pattern | Authoritative Type | Applies? |
|-------------|--------------------|----------|
| `GigabitEthernet*` | `1000base-t` | Yes |
| `Gi*` | `1000base-t` | Yes |
| `FastEthernet*` | `100base-tx` | Yes |
| `Fa*` | `100base-tx` | Yes |
| Any other name | No override | Skip |

## Transient Audit Event

Corrections are surfaced as log events, not stored data.

| Field | Source |
|------|--------|
| `host` | Current collector host |
| `interface_name` | `NormalizedInterface.name` |
| `original_type` | Pre-correction COM value |
| `corrected_type` | Cisco authoritative type |
| `speed_kbps` | `NormalizedInterface.speed` |

## Validation Rules

- A recognized Cisco interface name may override `type`.
- `speed` must remain whatever negotiated value the device reported.
- Unknown interface names must not be rewritten.
- If the current `type` already matches the authoritative Cisco type, no functional change is applied.

## State Transitions

1. Raw NAPALM interface data is converted into `NormalizedInterface` by `build_interfaces_from_napalm()`.
2. `CiscoCollector` evaluates each interface name against the Cisco rule set.
3. If a recognized name implies a different authoritative type, the collector updates `NormalizedInterface.type` and logs the correction.
4. The corrected `NormalizedInterface` continues through normal orbweaver translation and ingestion flows.