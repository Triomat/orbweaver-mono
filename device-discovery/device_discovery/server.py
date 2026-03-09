#!/usr/bin/env python
# Copyright 2024 NetBox Labs Inc
"""Device Discovery Server."""


import os
import subprocess
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

import yaml
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from device_discovery.collectors.registry import list_collectors, get_collector
from device_discovery.discovery import supported_drivers
from device_discovery.metrics import get_metric
from device_discovery.policy.manager import PolicyManager
from device_discovery.policy.models import Defaults, PolicyRequest, PolicyStatus
from device_discovery.review.discover import run_discovery_for_review
from device_discovery.review.models import ItemStatus, ReviewItem, ReviewSession, ReviewStatus
from device_discovery.review.store import ReviewStore
from device_discovery.version import version_semver


class ReviewCounts(BaseModel):
    """Summary counts across all review sessions."""

    total: int = 0
    pending: int = 0
    ready: int = 0
    ingested: int = 0
    failed: int = 0


class StatusResponse(BaseModel):
    """Enhanced status response with policy runs."""

    version: str
    up_time_seconds: int
    policies: list[PolicyStatus] = []
    diode_target: str | None = None
    dry_run: bool = False
    reviews: ReviewCounts = ReviewCounts()


manager = PolicyManager()
start_time = datetime.now()

# Review store: data dir configurable via ORBWEAVER_REVIEW_DIR env var
_review_dir = os.environ.get("ORBWEAVER_REVIEW_DIR", "reviews")
review_store = ReviewStore(data_dir=_review_dir)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Context manager for the lifespan of the server.

    Args:
    ----
        app (FastAPI): The FastAPI app.

    """
    # Startup
    yield
    # Clean up
    manager.stop()


app = FastAPI(lifespan=lifespan)

# ---------------------------------------------------------------------------
# CORS — origins configurable via ORBWEAVER_CORS_ORIGINS (comma-separated)
# Default: allow all origins (development-friendly)
# ---------------------------------------------------------------------------
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


# Add middleware to track API requests and latency
@app.middleware("http")
async def add_metrics(request: Request, call_next):
    """
    Add middleware to track API requests and latency.

    Args:
    ----
        request (Request): The request object.
        call_next: The next middleware or route handler.

    Returns:
    -------
        response: The response object.

    """
    api_requests = get_metric("api_requests")
    api_response_latency = get_metric("api_response_latency")
    if api_requests is None or api_response_latency is None:
        return await call_next(request)
    api_requests.add(1, {"path": request.url.path, "method": request.method})

    start_time = time.perf_counter()
    response = await call_next(request)
    duration = (time.perf_counter() - start_time) * 1000

    api_response_latency.record(
        duration,
        {
            "path": request.url.path,
            "method": request.method,
            "status_code": response.status_code,
        },
    )

    return response


async def parse_yaml_body(request: Request) -> PolicyRequest:
    """
    Parse the YAML body of the request.

    Args:
    ----
        request (Request): The request object.

    Returns:
    -------
        PolicyRequest: The policy request object.

    """
    if request.headers.get("content-type") != "application/x-yaml":
        raise HTTPException(
            status_code=400,
            detail="invalid Content-Type. Only 'application/x-yaml' is supported",
        )
    body = await request.body()
    try:
        return manager.parse_policy(body)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail="Invalid YAML format") from e
    except ValidationError as e:
        errors = []
        for error in e.errors():
            field_path = ".".join(str(part) for part in error["loc"])
            message = error["msg"]
            errors.append(
                {"field": field_path, "type": error["type"], "error": message}
            )
        raise HTTPException(status_code=403, detail=errors) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Existing endpoints (unchanged from upstream)
# ---------------------------------------------------------------------------

@app.get("/api/v1/status")
def read_status():
    """
    Get the status of the server with policy run history.

    Returns
    -------
        dict: The status of the server including policy runs.

    """
    time_diff = datetime.now() - start_time

    # Get policy statuses with run history
    policy_statuses = manager.get_policy_statuses()

    _diode_target = os.environ.get("DIODE_TARGET") or None

    # Review session counts
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

    response = StatusResponse(
        version=version_semver(),
        up_time_seconds=round(time_diff.total_seconds()),
        policies=policy_statuses,
        diode_target=_diode_target,
        dry_run=_diode_target is None,
        reviews=reviews,
    )

    return response.model_dump()


@app.get("/api/v1/capabilities")
def read_capabilities():
    """
    Get the supported drivers.

    Returns
    -------
        dict: The supported drivers.

    """
    return {"supported_drivers": supported_drivers}


@app.post("/api/v1/policies", status_code=201)
async def write_policy(request: PolicyRequest = Depends(parse_yaml_body)):
    """
    Write a policy to the server.

    Args:
    ----
        request (PolicyRequest): The policy request object.

    Returns:
    -------
        dict: The result of the policy write.

    """
    started_policies = []
    policies = request.policies
    for name, policy in policies.items():
        try:
            manager.start_policy(name, policy)
            started_policies.append(name)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except Exception as e:
            for policy_name in started_policies:
                manager.delete_policy(policy_name)
            raise HTTPException(status_code=400, detail=str(e)) from e

    if not started_policies:
        raise HTTPException(status_code=400, detail="no policies found in request")

    if len(started_policies) == 1:
        return {"detail": f"policy '{started_policies[0]}' was started"}
    return {"detail": f"policies {started_policies} were started"}


@app.delete("/api/v1/policies/{policy_name}", status_code=200)
def delete_policy(policy_name: str):
    """
    Delete a policy by name.

    Args:
    ----
        policy_name (str): The name of the policy to delete.

    Returns:
    -------
        dict: The result of the deletion

    """
    try:
        manager.delete_policy(policy_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"detail": f"policy '{policy_name}' was deleted"}


# ---------------------------------------------------------------------------
# NEW: Collectors
# ---------------------------------------------------------------------------

@app.get("/api/v1/collectors")
def read_collectors():
    """List all registered vendor collectors."""
    collectors = []
    for name in list_collectors():
        try:
            collector_class, config_class = get_collector(name)
            collectors.append({
                "name": name,
                "vendor": getattr(collector_class, "vendor_name", name),
            })
        except Exception:
            collectors.append({"name": name, "vendor": name})
    return {"collectors": collectors}


# ---------------------------------------------------------------------------
# NEW: One-shot discover-and-hold
# ---------------------------------------------------------------------------

class DiscoverResponse(BaseModel):
    id: str
    status: str
    detail: str


def _background_discover(policy_request: PolicyRequest, policy_name: str, review_id: str) -> None:
    """Background task: run discovery and update the review session."""
    session = review_store.get(review_id)
    if session is None:
        return

    policy = policy_request.policies.get(policy_name)
    if policy is None:
        session.status = ReviewStatus.FAILED
        session.error = f"Policy '{policy_name}' not found in request"
        review_store.save(session)
        return

    # run_discovery_for_review creates its own session; we've already created one.
    # Reuse the existing session by running collection directly.
    from device_discovery.review.discover import run_discovery_for_review as _run
    # Re-create a fresh run, then copy results into the pre-created session
    tmp_session = _run(policy, policy_name=policy_name, review_store=review_store)

    # tmp_session was saved with its own ID; copy results into pre-created session and delete tmp
    session.devices = tmp_session.devices
    session.defaults = tmp_session.defaults
    session.status = tmp_session.status
    session.error = tmp_session.error
    review_store.save(session)
    review_store.delete(tmp_session.id)


@app.post("/api/v1/discover", status_code=202)
async def trigger_discover(
    background_tasks: BackgroundTasks,
    request: PolicyRequest = Depends(parse_yaml_body),
):
    """
    Trigger a one-shot discovery run that stores results for review.

    Returns 202 immediately with a review session ID.
    Poll GET /api/v1/discover/{id} (or GET /api/v1/reviews/{id}) for status.
    """
    if not request.policies:
        raise HTTPException(status_code=400, detail="no policies found in request")

    # Use the first policy
    policy_name = next(iter(request.policies))
    policy = request.policies[policy_name]

    defaults_dict: dict = {}
    if policy.config and policy.config.defaults:
        defaults_dict = policy.config.defaults.model_dump(exclude_none=True)

    session = review_store.create(policy_name=policy_name, defaults=defaults_dict)
    background_tasks.add_task(
        _background_discover, request, policy_name, session.id
    )

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


# ---------------------------------------------------------------------------
# NEW: Review CRUD
# ---------------------------------------------------------------------------

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
    """Body for PUT /api/v1/reviews/{id} — replace full review data."""
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
    action: ItemStatus  # accepted or rejected
    indices: list[int] | None = None  # None = apply to all


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


# ---------------------------------------------------------------------------
# NEW: Ingest
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    dry_run: bool = False
    # Which item statuses to include; default is accepted + pending (non-rejected)
    statuses: list[ItemStatus] = [ItemStatus.ACCEPTED, ItemStatus.PENDING]


class IngestSummary(BaseModel):
    """Counts of what was ingested, by object type."""

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


@app.post("/api/v1/reviews/{review_id}/ingest")
def ingest_review(review_id: str, body: IngestRequest):
    """
    Ingest accepted device items into NetBox via the Diode SDK.

    By default ingests devices with status=accepted or status=pending.
    Pass statuses=["accepted"] to only ingest explicitly accepted items.
    Set dry_run=true to preview without writing.
    """
    session = review_store.get(review_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found")
    if session.status == ReviewStatus.PENDING:
        raise HTTPException(
            status_code=409, detail="Discovery is still in progress for this review"
        )

    # Rebuild defaults from stored dict
    defaults = Defaults.model_validate(session.defaults) if session.defaults else Defaults()

    # Import here to avoid circular import at module level
    from device_discovery.client import Client
    from device_discovery.diode_translate import translate_single_device
    from device_discovery.review.rebuild import device_from_dict

    entities_to_ingest = []
    ingest_errors: list[str] = []
    skipped = 0

    for item in session.devices:
        if item.status not in body.statuses:
            skipped += 1
            continue
        try:
            device = device_from_dict(item.data)
            entities = list(translate_single_device(device, defaults))
            entities_to_ingest.extend(entities)
        except Exception as exc:
            name = item.data.get("name", f"index={item.index}")
            ingest_errors.append(f"{name}: {exc}")

    ingested = len([i for i in session.devices if i.status in body.statuses]) - len(ingest_errors) - skipped

    if not body.dry_run and entities_to_ingest:
        try:
            client = Client()
            response = client.diode_client.ingest(
                entities=entities_to_ingest,
                metadata={"review_id": review_id},
            )
            if response.errors:
                ingest_errors.extend(response.errors)
            else:
                session.status = ReviewStatus.INGESTED
                review_store.save(session)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Ingest failed: {exc}") from exc
    elif body.dry_run:
        # Dry run: don't change session status, just report what would be ingested
        pass

    # Build summary counts by entity type
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

    # Count LLDP neighbors from source data (not in Diode entities)
    for item in session.devices:
        if item.status in body.statuses:
            summary.lldp_neighbors += len(item.data.get("lldp_neighbors", []))

    return IngestResponse(
        review_id=review_id,
        dry_run=body.dry_run,
        ingested_count=len(entities_to_ingest),
        skipped_count=skipped,
        summary=summary,
        errors=ingest_errors,
    ).model_dump()


# ---------------------------------------------------------------------------
# NEW: Compare review with NetBox
# ---------------------------------------------------------------------------


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
    """
    Compare a review session's discovered data against live NetBox state.

    Returns per-object diffs showing which fields differ, which objects are new,
    and which are already in sync.
    """
    session = review_store.get(review_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found")
    if session.status == ReviewStatus.PENDING:
        raise HTTPException(
            status_code=409, detail="Discovery is still in progress for this review"
        )

    from device_discovery.review.compare import CompareConfig, compare_review_with_netbox

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


# ---------------------------------------------------------------------------
# NEW: orb-agent config management (showcase workaround)
# ---------------------------------------------------------------------------

_orb_agent_yml = os.environ.get("ORBWEAVER_ORB_AGENT_YML", "")
_orb_container = os.environ.get("ORBWEAVER_ORB_CONTAINER", "orb-agent")


@app.get("/api/v1/orb-agent/status")
def get_orb_agent_status():
    """
    Query the orb-agent container's running state and internal API status.

    Returns container state from docker inspect and, if running, the
    device-discovery /api/v1/status from inside the container.
    """
    import json as _json

    result = {
        "container": _orb_container,
        "running": False,
        "state": None,
        "discovery_status": None,
        "error": None,
    }

    # 1. Container state via docker inspect
    try:
        proc = subprocess.run(
            ["docker", "inspect", "--format", "{{json .State}}", _orb_container],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            state = _json.loads(proc.stdout.strip())
            result["running"] = state.get("Running", False)
            result["state"] = state.get("Status", "unknown")
        else:
            result["error"] = proc.stderr.strip() or "container not found"
            return result
    except Exception as exc:
        result["error"] = str(exc)
        return result

    # 2. If running, fetch internal API status via docker exec
    if result["running"]:
        try:
            _py_status = (
                "import urllib.request, sys\n"
                "try:\n"
                "  resp = urllib.request.urlopen('http://localhost:8072/api/v1/status', timeout=5)\n"
                "  sys.stdout.write(resp.read().decode())\n"
                "except Exception as e:\n"
                "  sys.stderr.write(str(e))\n"
                "  sys.exit(1)\n"
            )
            proc = subprocess.run(
                ["docker", "exec", _orb_container, "python3", "-c", _py_status],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                result["discovery_status"] = _json.loads(proc.stdout.strip())
        except Exception:
            pass  # Non-critical; we still return container state

    return result


@app.get("/api/v1/orb-agent/config")
def get_orb_agent_config():
    """Return current orb-agent YAML config from disk."""
    if not _orb_agent_yml:
        raise HTTPException(status_code=404, detail="ORBWEAVER_ORB_AGENT_YML not configured")
    try:
        with open(_orb_agent_yml) as f:
            content = f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {_orb_agent_yml}")
    return {"yaml": content, "path": _orb_agent_yml, "container": _orb_container}


@app.post("/api/v1/orb-agent/config")
async def set_orb_agent_config(request: Request):
    """Write a new orb-agent YAML config to disk and restart the container."""
    if not _orb_agent_yml:
        raise HTTPException(status_code=404, detail="ORBWEAVER_ORB_AGENT_YML not configured")
    body = await request.body()
    body_str = body.decode()
    try:
        yaml.safe_load(body_str)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")
    with open(_orb_agent_yml, "w") as f:
        f.write(body_str)
    result = subprocess.run(
        ["docker", "restart", _orb_container],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"docker restart failed: {result.stderr.strip()}")
    return {"detail": f"Config written and container '{_orb_container}' restarted"}


@app.post("/api/v1/orb-agent/trigger")
async def trigger_orb_agent(request: Request):
    """
    Force the orb-agent to run a policy immediately by POSTing YAML to its
    internal API via docker exec (bypassing the missing external port).
    Deletes any existing policy of the same name first to force a fresh run.
    """
    import json as _json
    body = await request.body()
    body_str = body.decode()
    try:
        doc = yaml.safe_load(body_str)
        policies = (doc or {}).get("policies", {})
        if not policies:
            raise HTTPException(status_code=400, detail="No policies found in YAML")
        policy_name = next(iter(policies))
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")

    _py_delete = (
        f"import urllib.request, urllib.error\n"
        f"req = urllib.request.Request('http://localhost:8072/api/v1/policies/{policy_name}', method='DELETE')\n"
        f"try: urllib.request.urlopen(req)\n"
        f"except urllib.error.HTTPError: pass\n"
    )
    subprocess.run(
        ["docker", "exec", _orb_container, "python3", "-c", _py_delete],
        capture_output=True, timeout=10,
    )

    _py_post = (
        "import urllib.request, sys\n"
        "data = sys.stdin.buffer.read()\n"
        "req = urllib.request.Request('http://localhost:8072/api/v1/policies', data=data,"
        " headers={'Content-Type': 'application/x-yaml'}, method='POST')\n"
        "print(urllib.request.urlopen(req).read().decode())\n"
    )
    result = subprocess.run(
        ["docker", "exec", "-i", _orb_container, "python3", "-c", _py_post],
        input=body,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.decode().strip() or "docker exec failed")
    try:
        return _json.loads(result.stdout)
    except Exception:
        return {"detail": result.stdout.decode().strip()}
