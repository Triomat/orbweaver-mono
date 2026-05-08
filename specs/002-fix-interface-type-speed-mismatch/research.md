# Research: Cisco Interface Type/Speed Mismatch Fix

## Decision 1

**Decision**: Implement the correction in `orbweaver/collectors/cisco_ios.py` after shared NAPALM normalization.

**Rationale**: The current misclassification is caused by shared speed-based type inference in `napalm_helpers.py`, but changing that shared behavior would affect every NAPALM-backed collector. The feature scope is Cisco IOS/IOS-XE only, so the collector is the narrowest safe place to enforce Cisco-specific rules.

**Alternatives considered**:

- Change `infer_interface_type()` globally: rejected because it risks regressions for non-Cisco collectors.
- Patch the COM model or translation layer: rejected because the bug originates during collector normalization, not downstream translation.

## Decision 2

**Decision**: Use Cisco interface name patterns as the authoritative source for `type` and keep NAPALM speed as the authoritative source for `speed`.

**Rationale**: The clarified requirement explicitly separates capability from current negotiated state. Interface class is encoded in Cisco naming, while NAPALM speed reflects live state.

**Alternatives considered**:

- Force speed to match interface type: rejected because it would hide negotiated-down links.
- Continue deriving type from speed: rejected because it causes the current bug.

## Decision 3

**Decision**: Support only explicit known Cisco name prefixes in the first fix: `GigabitEthernet`/`Gi` and `FastEthernet`/`Fa`.

**Rationale**: The spec explicitly limits the first implementation to known patterns and says to skip unknown names. A conservative rule set prevents false positives on ambiguous names.

**Alternatives considered**:

- Infer unknown names from speed: rejected because speed is not the authoritative source for type.
- Add a broad table for all Cisco interface families immediately: rejected as unnecessary scope expansion.

## Decision 4

**Decision**: Log applied corrections in the Cisco collector when the authoritative Cisco type differs from the current COM value.

**Rationale**: The feature requires an audit trail for automatic corrections. Logging only on changed values keeps the signal useful and avoids noisy logs for already-correct interfaces.

**Alternatives considered**:

- Log every recognized interface evaluation: rejected as too noisy.
- Skip logs entirely: rejected because it fails the observability requirement.

## Decision 5

**Decision**: Add a new orbweaver-side test module and include test command wiring in the implementation scope.

**Rationale**: The constitution requires orbweaver functionality to be covered by orbweaver tests, and the current repo test recipe is centered on `backend/tests`. This feature should leave behind a reliable regression guard.

**Alternatives considered**:

- Add tests under `backend/tests`: rejected because `backend/` must remain upstream-verbatim.
- Rely on manual testing only: rejected because the bug is deterministic and well-suited to unit tests.