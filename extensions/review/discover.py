"""One-shot discovery that holds results for review instead of immediately ingesting.

Usage
-----
    from extensions.review.discover import run_discovery_for_review
    session = run_discovery_for_review(policy, policy_name="my-policy", review_store=store)
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import datetime
from enum import Enum
from typing import Any

from extensions.collectors.registry import get_collector, list_collectors
from device_discovery.policy.models import Config, Napalm, Policy
from extensions.review.models import ItemStatus, ReviewItem, ReviewSession, ReviewStatus
from extensions.review.store import ReviewStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _to_dict(obj: Any) -> Any:
    """Recursively convert dataclass/enum/datetime to JSON-serializable types."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------------------
# Collector selection (mirrors PolicyRunner._select_collector without self)
# ---------------------------------------------------------------------------

def _select_collector(scope: Napalm):
    """Return (collector_class, config_class) or None if no match."""
    if scope.collector:
        try:
            return get_collector(scope.collector)
        except KeyError:
            logger.warning(
                "Unknown collector '%s'. Available: %s. Will raise error.",
                scope.collector,
                list_collectors(),
            )
            return None

    if scope.driver:
        try:
            return get_collector(scope.driver)
        except KeyError:
            pass

    return None


# ---------------------------------------------------------------------------
# Per-device collection
# ---------------------------------------------------------------------------

def _collect_single(scope: Napalm, config: Config) -> dict:
    """
    Collect from one device and return a JSON-serializable dict of NormalizedDevice.

    Raises ValueError if no suitable collector is registered.
    """
    entry = _select_collector(scope)
    if entry is None:
        raise ValueError(
            f"No collector available for '{scope.hostname}' "
            f"(driver={scope.driver!r}, collector={scope.collector!r}). "
            "Set 'collector: cisco_ios' (or another registered collector) in your policy."
        )

    collector_class, config_class = entry
    config_field_names = {f.name for f in dataclasses.fields(config_class)}

    kwargs: dict[str, Any] = {
        "hosts": [scope.hostname],
        "username": scope.username,
        "password": scope.password,
        "site_name": (config.defaults.site if config.defaults and config.defaults.site else ""),
        "timeout": scope.timeout,
    }
    if "driver" in config_field_names and scope.driver:
        kwargs["driver"] = scope.driver
    if "optional_args" in config_field_names and scope.optional_args:
        kwargs["optional_args"] = scope.optional_args

    collector_config = config_class(
        **{k: v for k, v in kwargs.items() if k in config_field_names}
    )
    collector = collector_class(collector_config)

    logger.info("Collecting %s via %s collector", scope.hostname, collector.vendor_name)
    normalized_device = collector.discover_single(scope.hostname)
    return _to_dict(normalized_device)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_discovery_for_review(
    policy: Policy,
    policy_name: str,
    review_store: ReviewStore,
) -> ReviewSession:
    """
    Run one-shot discovery for every device in *policy* and store results for review.

    Unlike the scheduled PolicyRunner this function:
    - Does NOT ingest to Diode
    - Stores collected COM objects (serialized) in the ReviewStore
    - Returns a ReviewSession with status=READY (or FAILED on complete error)
    """
    defaults_dict: dict = {}
    if policy.config and policy.config.defaults:
        defaults_dict = policy.config.defaults.model_dump(exclude_none=True)

    session = review_store.create(policy_name=policy_name, defaults=defaults_dict)
    errors: list[str] = []

    for scope in policy.scope:
        hostname = scope.hostname
        try:
            device_dict = _collect_single(scope, policy.config or Config())
            session.devices.append(
                ReviewItem(index=len(session.devices), data=device_dict)
            )
        except Exception as exc:
            msg = f"{hostname}: {exc}"
            logger.error("Discovery failed for %s: %s", hostname, exc)
            errors.append(msg)

    if errors and not session.devices:
        session.status = ReviewStatus.FAILED
        session.error = "; ".join(errors)
    else:
        session.status = ReviewStatus.READY
        if errors:
            session.error = "Partial failure — " + "; ".join(errors)

    review_store.save(session)
    return session
