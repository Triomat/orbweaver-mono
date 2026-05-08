# Contracts

This feature does not change any external API, CLI, or persisted data contract.

Scope is limited to internal Cisco collector normalization behavior inside `orbweaver/collectors/cisco_ios.py`.

Affected contract surface:

- Existing COM output remains `NormalizedInterface`
- Existing FastAPI routes remain unchanged
- Existing Diode translation interface remains unchanged

Result: no external contract artifact is required beyond this note.