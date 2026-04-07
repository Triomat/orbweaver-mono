"""
orbweaver FastAPI extensions.

Extends the upstream device_discovery app in-place, without modifying any
upstream file. Import this module AFTER orbweaver.patches has been applied.

Adds:
  - CORS middleware
  - Enhanced /api/v1/status (review counts, dry_run, diode_target)
  - GET  /api/v1/collectors
  - POST /api/v1/discover                      (discover-and-hold)
  - GET  /api/v1/discover/{job_id}
  - CRUD /api/v1/reviews/*
  - POST /api/v1/reviews/{id}/ingest
  - POST /api/v1/reviews/{id}/compare
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

from fastapi import BackgroundTasks, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.routing import Route

# ── Upstream imports ──────────────────────────────────────────────────────────
# Importing device_discovery.server here triggers the module to load (and
# register all upstream routes). Patches are already applied at this point.
from device_discovery.client import Client
from device_discovery.policy.models import Defaults, PolicyRequest
from device_discovery.server import app, manager, parse_yaml_body, start_time
from device_discovery.version import version_semver

# ── Orbweaver imports ─────────────────────────────────────────────────────────
from orbweaver.collectors.registry import get_collector, list_collectors
from orbweaver.diode_translate import translate_primary_ip_entities, translate_single_device
from orbweaver.review.compare import CompareConfig, compare_review_with_netbox
from orbweaver.review.models import ItemStatus, ReviewItem, ReviewStatus
from orbweaver.review.rebuild import device_from_dict
from orbweaver.review.store import ReviewStore

# ── Review store ──────────────────────────────────────────────────────────────
_review_dir = os.environ.get("ORBWEAVER_REVIEW_DIR", "reviews")
review_store = ReviewStore(data_dir=_review_dir)

# ── CORS ──────────────────────────────────────────────────────────────────────
_cors_origins_raw = os.environ.get("ORBWEAVER_CORS_ORIGINS", "*")
_cors_origins = (
    ["*"]
    if _cors_origins_raw.strip() == "*"
    else [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins_raw.strip() != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Override /api/v1/status ───────────────────────────────────────────────────

class ReviewCounts(BaseModel):
    """Summary counts across all review sessions."""

    total: int = 0
    pending: int = 0
    ready: int = 0
    ingested: int = 0
    failed: int = 0


class EnhancedStatusResponse(BaseModel):
    """Enhanced status response with review counts and Diode target."""

    version: str
    up_time_seconds: int
    policies: list = []
    diode_target: str | None = None
    dry_run: bool = False
    reviews: ReviewCounts = ReviewCounts()


# Remove the upstream /api/v1/status route so we can replace it.
app.router.routes = [
    r for r in app.router.routes
    if not (isinstance(r, Route) and getattr(r, "path", None) == "/api/v1/status")
]


@app.get("/api/v1/status")
def read_status():
    """Enhanced status: adds review counts, dry_run flag, and diode_target."""
    from datetime import datetime

    time_diff = datetime.now() - start_time
    policy_statuses = manager.get_policy_statuses()
    _diode_target = os.environ.get("DIODE_TARGET") or None

    reviews = ReviewCounts()
    try:
        sessions = review_store.list_all()
        reviews.total = len(sessions)
        for s in sessions:
            if s.status == ReviewStatus.PENDING:
                reviews.pending += 1
            elif s.status == ReviewStatus.READY:
                reviews.ready += 1
            elif s.status == ReviewStatus.INGESTED:
                reviews.ingested += 1
            elif s.status == ReviewStatus.FAILED:
                reviews.failed += 1
    except Exception:
        pass

    return EnhancedStatusResponse(
        version=version_semver(),
        up_time_seconds=round(time_diff.total_seconds()),
        policies=policy_statuses,
        diode_target=_diode_target,
        dry_run=_diode_target is None,
        reviews=reviews,
    ).model_dump()


# ── Collectors ────────────────────────────────────────────────────────────────

@app.get("/api/v1/collectors")
def read_collectors():
    """List all registered vendor collectors."""
    collectors = []
    for name in list_collectors():
        try:
            collector_class, _ = get_collector(name)
            collectors.append({
                "name": name,
                "vendor": getattr(collector_class, "vendor_name", name),
            })
        except Exception:
            collectors.append({"name": name, "vendor": name})
    return {"collectors": collectors}


# ── Discover-and-hold ─────────────────────────────────────────────────────────

class DiscoverResponse(BaseModel):
    id: str
    status: str
    detail: str


def _background_discover(policy_request: PolicyRequest, policy_name: str, review_id: str) -> None:
    """Background task: run discovery and update the review session."""
    from orbweaver.review.discover import run_discovery_for_review as _run

    session = review_store.get(review_id)
    if session is None:
        return

    policy = policy_request.policies.get(policy_name)
    if policy is None:
        session.status = ReviewStatus.FAILED
        session.error = f"Policy '{policy_name}' not found in request"
        review_store.save(session)
        return

    tmp_session = _run(policy, policy_name=policy_name, review_store=review_store)
    session.devices = tmp_session.devices
    session.defaults = tmp_session.defaults
    session.status = tmp_session.status
    session.error = tmp_session.error
    review_store.delete(tmp_session.id)

    auto_ingest = bool(policy.config and getattr(policy.config, "auto_ingest", False))
    if auto_ingest and session.status == ReviewStatus.READY:
        logger.info("Review %s: auto_ingest=true, skipping review and ingesting directly", review_id)
        for item in session.devices:
            item.status = ItemStatus.ACCEPTED
        defaults = Defaults.model_validate(session.defaults) if session.defaults else Defaults()
        result = _execute_ingest(session, defaults, [ItemStatus.ACCEPTED])
        if result["errors"]:
            session.status = ReviewStatus.FAILED
            session.error = "; ".join(result["errors"])
            logger.warning("Review %s: auto-ingest completed with errors: %s", review_id, session.error)
        else:
            session.status = ReviewStatus.INGESTED
            logger.info("Review %s: auto-ingest complete — %d entities ingested", review_id, result["ingested_count"])

    review_store.save(session)


@app.post("/api/v1/discover", status_code=202)
async def trigger_discover(
    background_tasks: BackgroundTasks,
    request: PolicyRequest = Depends(parse_yaml_body),
):
    """Trigger a one-shot discovery run that stores results for review."""
    if not request.policies:
        raise HTTPException(status_code=400, detail="no policies found in request")

    policy_name = next(iter(request.policies))
    policy = request.policies[policy_name]

    defaults_dict: dict = {}
    if policy.config and policy.config.defaults:
        defaults_dict = policy.config.defaults.model_dump(exclude_none=True)

    session = review_store.create(policy_name=policy_name, defaults=defaults_dict)
    background_tasks.add_task(_background_discover, request, policy_name, session.id)

    return DiscoverResponse(
        id=session.id,
        status=session.status,
        detail=f"Discovery started for policy '{policy_name}'. Poll /api/v1/reviews/{session.id} for status.",
    )


@app.get("/api/v1/discover/{job_id}")
def poll_discover(job_id: str):
    """Poll the status of a discover job (alias for GET /api/v1/reviews/{id})."""
    session = review_store.get(job_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Review '{job_id}' not found")
    return session.summary


# ── Review CRUD ───────────────────────────────────────────────────────────────

@app.get("/api/v1/reviews")
def list_reviews():
    """List all review sessions (summary view, no device data)."""
    sessions = review_store.list_all()
    return {"reviews": [s.summary for s in sessions]}


@app.get("/api/v1/reviews/{review_id}")
def get_review(review_id: str):
    """Get a full review session including all device data."""
    session = review_store.get(review_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found")
    return session.model_dump()


class ReviewUpdate(BaseModel):
    devices: list[ReviewItem] | None = None
    status: ReviewStatus | None = None
    error: str | None = None


@app.put("/api/v1/reviews/{review_id}")
def update_review(review_id: str, body: ReviewUpdate):
    """Replace review fields (devices list, status, error)."""
    session = review_store.get(review_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found")
    if body.devices is not None:
        session.devices = body.devices
    if body.status is not None:
        session.status = body.status
    if body.error is not None:
        session.error = body.error
    review_store.save(session)
    return session.model_dump()


class ItemUpdate(BaseModel):
    status: ItemStatus | None = None
    data: dict | None = None


@app.patch("/api/v1/reviews/{review_id}/items/devices/{index}")
def patch_device_item(review_id: str, index: int, body: ItemUpdate):
    """Update a single device item's status or data."""
    session = review_store.get(review_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found")
    if index < 0 or index >= len(session.devices):
        raise HTTPException(status_code=404, detail=f"Device index {index} out of range")
    item = session.devices[index]
    if body.status is not None:
        item.status = body.status
    if body.data is not None:
        item.data = body.data
    review_store.save(session)
    return item.model_dump()


class BulkAction(BaseModel):
    action: ItemStatus
    indices: list[int] | None = None


@app.post("/api/v1/reviews/{review_id}/bulk")
def bulk_update(review_id: str, body: BulkAction):
    """Bulk accept or reject device items."""
    session = review_store.get(review_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found")
    indices = body.indices if body.indices is not None else list(range(len(session.devices)))
    updated = 0
    for idx in indices:
        if 0 <= idx < len(session.devices):
            session.devices[idx].status = body.action
            updated += 1
    review_store.save(session)
    return {"updated": updated}


@app.delete("/api/v1/reviews/{review_id}", status_code=200)
def delete_review(review_id: str):
    """Delete a review session."""
    deleted = review_store.delete(review_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found")
    return {"detail": f"review '{review_id}' was deleted"}


# ── Ingest ────────────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    dry_run: bool = False
    statuses: list[ItemStatus] = [ItemStatus.ACCEPTED, ItemStatus.PENDING]


class IngestSummary(BaseModel):
    devices: int = 0
    interfaces: int = 0
    ip_addresses: int = 0
    vlans: int = 0
    prefixes: int = 0
    lldp_neighbors: int = 0


class IngestResponse(BaseModel):
    review_id: str
    dry_run: bool
    ingested_count: int
    skipped_count: int
    summary: IngestSummary = IngestSummary()
    errors: list[str] = []


def _execute_ingest(session, defaults: Defaults, statuses: list, dry_run: bool = False) -> dict:
    """
    Translate accepted review items and push entities to Diode.

    Returns an IngestResponse-compatible dict. Does not raise HTTP exceptions —
    callers decide how to surface errors.
    """
    entities_to_ingest = []
    primary_ip_entities: list = []
    ingest_errors: list[str] = []
    skipped = 0

    logger.info("Review %s: ingesting %d device(s)", session.id, len(session.devices))

    for item in session.devices:
        if item.status not in statuses:
            skipped += 1
            continue
        try:
            device = device_from_dict(item.data)
            entities = list(translate_single_device(device, defaults))
            entities_to_ingest.extend(entities)
            primary_ip_entities.extend(translate_primary_ip_entities(device, defaults))
        except Exception as exc:
            name = item.data.get("name", f"index={item.index}")
            ingest_errors.append(f"{name}: {exc}")

    if not dry_run and entities_to_ingest:
        client = Client()
        # First call: device, interfaces, IPs, VLANs — everything except primary IPs.
        response = client.diode_client.ingest(
            entities=entities_to_ingest,
            metadata={"review_id": session.id},
        )
        if response.errors:
            ingest_errors.extend(str(e) for e in response.errors)

    if not dry_run and primary_ip_entities and not ingest_errors:
        # Second call: set primary_ip4/ip6 after the interface IP assignments are
        # committed. The Diode reconciler processes batches concurrently, so sending
        # primary IPs in the same batch as the interface assignments causes a race
        # condition ("IP not assigned to this device" error from NetBox).
        client = Client()
        response = client.diode_client.ingest(
            entities=primary_ip_entities,
            metadata={"review_id": session.id, "pass": "primary_ips"},
        )
        if response.errors:
            ingest_errors.extend(str(e) for e in response.errors)

    summary = IngestSummary()
    for entity in entities_to_ingest:
        if getattr(entity, "device", None) is not None:
            summary.devices += 1
        elif getattr(entity, "interface", None) is not None:
            summary.interfaces += 1
        elif getattr(entity, "ip_address", None) is not None:
            summary.ip_addresses += 1
        elif getattr(entity, "vlan", None) is not None:
            summary.vlans += 1
        elif getattr(entity, "prefix", None) is not None:
            summary.prefixes += 1

    for item in session.devices:
        if item.status in statuses:
            summary.lldp_neighbors += len(item.data.get("lldp_neighbors", []))

    if ingest_errors:
        logger.warning("Review %s: ingest completed with errors: %s", session.id, ingest_errors)
    else:
        logger.info(
            "Review %s: ingested %d entities (devices=%d interfaces=%d ips=%d vlans=%d prefixes=%d)",
            session.id, len(entities_to_ingest),
            summary.devices, summary.interfaces, summary.ip_addresses,
            summary.vlans, summary.prefixes,
        )

    return IngestResponse(
        review_id=session.id,
        dry_run=dry_run,
        ingested_count=len(entities_to_ingest),
        skipped_count=skipped,
        summary=summary,
        errors=ingest_errors,
    ).model_dump()


@app.post("/api/v1/reviews/{review_id}/ingest")
def ingest_review(review_id: str, body: IngestRequest):
    """Ingest accepted device items into NetBox via the Diode SDK."""
    session = review_store.get(review_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found")
    if session.status == ReviewStatus.PENDING:
        raise HTTPException(status_code=409, detail="Discovery is still in progress for this review")

    defaults = Defaults.model_validate(session.defaults) if session.defaults else Defaults()

    try:
        result = _execute_ingest(session, defaults, body.statuses, dry_run=body.dry_run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ingest failed: {exc}") from exc

    if not body.dry_run and not result["errors"]:
        session.status = ReviewStatus.INGESTED
        review_store.save(session)

    return result


# ── Compare ───────────────────────────────────────────────────────────────────

class CompareRequest(BaseModel):
    netbox_url: str
    netbox_token: str
    verify_ssl: bool = True
    statuses: list[ItemStatus] = [ItemStatus.ACCEPTED, ItemStatus.PENDING]


class CompareFieldDiff(BaseModel):
    field_name: str
    discovered_value: str
    netbox_value: str


class CompareObjectDiff(BaseModel):
    object_type: str
    unique_key: str
    display_name: str
    is_new: bool
    fields: list[CompareFieldDiff] = []
    errors: list[str] = []


class CompareResponse(BaseModel):
    review_id: str
    compared_count: int
    new_count: int
    changed_count: int
    in_sync_count: int
    error_count: int
    diffs: list[CompareObjectDiff]


@app.post("/api/v1/reviews/{review_id}/compare")
def compare_review(review_id: str, body: CompareRequest):
    """Compare a review session's discovered data against live NetBox state."""
    session = review_store.get(review_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found")
    if session.status == ReviewStatus.PENDING:
        raise HTTPException(status_code=409, detail="Discovery is still in progress for this review")

    cfg = CompareConfig(
        netbox_url=body.netbox_url,
        netbox_token=body.netbox_token,
        verify_ssl=body.verify_ssl,
    )
    items = [item.model_dump() for item in session.devices]
    include = tuple(s.value for s in body.statuses)
    raw_diffs = compare_review_with_netbox(items, cfg, include_statuses=include)

    diffs = [
        CompareObjectDiff(
            object_type=d.object_type,
            unique_key=d.unique_key,
            display_name=d.display_name,
            is_new=d.is_new,
            fields=[
                CompareFieldDiff(
                    field_name=f.field_name,
                    discovered_value=f.discovered_value,
                    netbox_value=f.netbox_value,
                )
                for f in d.fields
            ],
            errors=d.errors,
        )
        for d in raw_diffs
    ]

    new_count = sum(1 for d in diffs if d.is_new)
    error_count = sum(1 for d in diffs if d.errors)
    changed_count = sum(1 for d in diffs if d.fields and not d.is_new)
    in_sync_count = len(diffs) - new_count - error_count - changed_count

    return CompareResponse(
        review_id=review_id,
        compared_count=len(diffs),
        new_count=new_count,
        changed_count=changed_count,
        in_sync_count=in_sync_count,
        error_count=error_count,
        diffs=diffs,
    ).model_dump()
