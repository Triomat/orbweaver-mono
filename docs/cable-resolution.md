# Cable Resolution Guide

This guide explains how LLDP cable discovery works in orbweaver, how to configure it, and how to troubleshoot skipped cables.

## What It Does

The cable workflow resolves LLDP neighbor data into cable candidates and writes only valid candidates into NetBox.

Pipeline:
1. Collect LLDP neighbors from discovered devices.
2. Normalize hostnames, MAC addresses, and interface names.
3. Match remote endpoints against discovered devices first, then existing NetBox devices.
4. Deduplicate bidirectional sightings into one cable.
5. Skip existing cables in NetBox (idempotent behavior).
6. In direct mode, ingest writable candidates.
7. In review mode, store candidates for manual approval.

## Confidence Levels

Cable candidates include one of three confidence values:
1. `confirmed`: bidirectional match and both endpoints discovered in current run.
2. `partial`: one-sided observation or one endpoint resolved from existing NetBox.
3. `unresolvable`: candidate cannot be safely created.

## Skip Reason Codes

Unresolvable or skipped candidates include reason codes.

Common codes:
1. `neighbor_device_not_found`: remote hostname/MAC could not be mapped.
2. `interface_name_mismatch`: remote interface could not be normalized/matched.
3. `self_loop_detected`: device reports itself as neighbor.
4. `ambiguous_chassis_mac`: same chassis MAC maps to multiple devices.
5. `already_exists`: equivalent cable already exists in NetBox.
6. `one_sided_neighbor`: only one side reports the link.
7. `ingestion_disabled`: cable writes disabled by policy/env flag.

## Configuration

Global flag:

```bash
export ORBWEAVER_CABLES_ENABLED=true
```

Policy-level default override:

```yaml
policies:
  dc1-cisco:
    config:
      defaults:
        site: DC1
        role: access-switch
        cables_enabled: true
```

Per-device override:

```yaml
policies:
  dc1-cisco:
    scope:
      - hostname: 192.0.2.10
        username: admin
        password: secret
        collector: cisco_ios
        cables_enabled: false
```

Resolution order for enable/disable:
1. Scope entry `cables_enabled`
2. Policy defaults `cables_enabled`
3. Environment variable `ORBWEAVER_CABLES_ENABLED`

## API Endpoints

Discovery and review:
1. `POST /api/v1/policies`
2. `POST /api/v1/discover`
3. `GET /api/v1/reviews/{id}`
4. `PATCH /api/v1/reviews/{id}/items/cables/{index}`
5. `POST /api/v1/reviews/{id}/ingest-cables`

Observability:
1. `GET /api/v1/cables/summary`
2. `GET /api/v1/cables/skip-reasons`

## Troubleshooting

### `neighbor_device_not_found`

Checks:
1. Confirm LLDP neighbor hostname normalization (shortname vs FQDN).
2. Verify neighbor device exists in NetBox or was discovered in same run.
3. Confirm chassis MAC in LLDP is valid and consistent.

### `interface_name_mismatch`

Checks:
1. Compare advertised interface with NetBox interface naming.
2. Verify vendor mapping supports abbreviation expansion.
3. Correct interface naming in NetBox or source platform.

### API errors during ingestion

Behavior:
1. Successfully created cables in the current run are rolled back.
2. Error is captured in `ingestion_error`.
3. Re-running after issue resolution is safe.

## Operational Notes

1. Existing cables are create-or-skip only; metadata is never overwritten.
2. Repeated runs are expected to increase `skipped` and keep cable count stable.
3. Review mode allows selective cable approval before writing to NetBox.
