# Cable Discovery Examples

This document contains practical LLDP cable scenarios and expected behavior.

## Example 1: Two Connected Switches (Confirmed)

Input:
1. `switch1` sees `switch2` on `Gi0/1`.
2. `switch2` sees `switch1` on `Gi0/1`.

Expected:
1. One cable candidate after deduplication.
2. Confidence is `confirmed`.
3. NetBox cable created with label `LLDP auto-discovered`.

## Example 2: One-Sided Neighbor (Partial)

Input:
1. `switch1` sees `switch2`.
2. `switch2` does not advertise `switch1`.

Expected:
1. One cable candidate.
2. Confidence is `partial`.
3. Candidate is reviewable and writable depending on workflow.

## Example 3: Unknown Neighbor (Unresolvable)

Input:
1. `switch1` reports neighbor hostname not found in discovery or NetBox.

Expected:
1. No cable created.
2. Skip entry reason: `neighbor_device_not_found`.
3. `unresolvable` counter increments.

## Example 4: Interface Name Mismatch (Unresolvable)

Input:
1. Neighbor interface cannot be normalized/matched.

Expected:
1. No cable created.
2. Skip entry reason: `interface_name_mismatch`.

## Example 5: Existing Cable (Idempotent Skip)

Input:
1. Candidate endpoints already exist as cable in NetBox.

Expected:
1. No duplicate cable created.
2. Skip entry reason: `already_exists`.
3. `skipped` counter increments.

## Example 6: Feature Flag Disabled

Input:
1. `ORBWEAVER_CABLES_ENABLED=false` or policy-level disable.

Expected:
1. Cable workflow does not write new cables.
2. Summary includes `ingestion_disabled=true`.

## Example 7: Review Workflow Selective Approval

Input:
1. Discovery-for-review session contains 5 cable items.
2. Operator accepts 3 and rejects 2.

Expected:
1. Only accepted cable items are ingested by `POST /api/v1/reviews/{id}/ingest-cables`.
2. Rejected cables remain uncreated in NetBox.

## Example 8: NetBox Write Error and Rollback

Input:
1. First cable write succeeds.
2. Next cable write fails due to API error.

Expected:
1. Previously created cable is deleted in rollback phase.
2. Summary `created` resets to `0`.
3. `ingestion_error` contains failure context.
