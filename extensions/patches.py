"""
orbweaver runtime patches.

Applied once at startup BEFORE device_discovery.server is imported.
Extends upstream classes without modifying any upstream files.
"""
from __future__ import annotations

import dataclasses
import logging

logger = logging.getLogger(__name__)

# ── 1. Add collector field to upstream Napalm model ──────────────────────────
#
# Pydantic v2 allows adding fields at runtime via model_rebuild().
# The upstream Napalm model is extended in-place; no upstream file is touched.

from pydantic.fields import FieldInfo  # noqa: E402
from device_discovery.policy.models import Napalm  # noqa: E402

Napalm.model_fields["collector"] = FieldInfo(
    default=None,
    annotation=str | None,
    description=(
        "Vendor collector name (cisco_ios, aruba_aoscx, napalm). "
        "When set, uses the orbweaver collector framework instead of the generic NAPALM path."
    ),
)
Napalm.model_rebuild(force=True)


# ── 2. Extend PolicyRunner with vendor collector support ──────────────────────
#
# Three methods are patched onto the class:
#   _select_collector             — picks the right vendor collector (or None)
#   _collect_device_data_via_collector — runs the COM collector path
#   _collect_device_data          — wraps the upstream method to try collector first

from device_discovery.policy.runner import PolicyRunner  # noqa: E402
from device_discovery.client import Client, MAX_MESSAGE_SIZE_BYTES  # noqa: E402
from device_discovery.entity_metadata import apply_run_id_to_entities  # noqa: E402
from device_discovery.policy.models import Defaults  # noqa: E402
from device_discovery.metrics import get_metric  # noqa: E402
from netboxlabs.diode.sdk import create_message_chunks, estimate_message_size  # noqa: E402
from extensions.collectors.registry import get_collector, list_collectors  # noqa: E402
from extensions.diode_translate import translate_single_device  # noqa: E402


def _select_collector(self, scope):
    """
    Select a vendor collector based on scope.collector or scope.driver.

    Returns (collector_class, config_class) if a named collector is registered,
    or None to fall through to the generic NAPALM path.
    """
    if scope.collector:
        try:
            return get_collector(scope.collector)
        except KeyError:
            available = list_collectors()
            logger.warning(
                "Policy %s: Unknown collector '%s'. Available: %s. "
                "Falling back to generic NAPALM path.",
                self.name, scope.collector, available,
            )
            return None

    if scope.driver:
        try:
            return get_collector(scope.driver)
        except KeyError:
            pass

    return None


def _collect_device_data_via_collector(self, scope, sanitized_hostname, config, run_id=None):
    """
    Collect device data via the orbweaver vendor collector framework (COM path).

    Produces a NormalizedDevice, translates it to Diode entities, and ingests.
    Bypasses Client().ingest() because our entities are pre-translated.
    """
    collector_class, config_class = self._select_collector(scope)
    config_field_names = {f.name for f in dataclasses.fields(config_class)}

    collector_kwargs = {
        "hosts": [scope.hostname],
        "username": scope.username,
        "password": scope.password,
        "site_name": config.defaults.site if config.defaults and config.defaults.site else "",
        "timeout": scope.timeout,
    }
    if "driver" in config_field_names and scope.driver:
        collector_kwargs["driver"] = scope.driver
    if "optional_args" in config_field_names and scope.optional_args:
        collector_kwargs["optional_args"] = scope.optional_args

    collector_config = config_class(
        **{k: v for k, v in collector_kwargs.items() if k in config_field_names}
    )
    collector = collector_class(collector_config)

    logger.info(
        "Policy %s, Hostname %s: Collecting via %s collector",
        self.name, sanitized_hostname, collector.vendor_name,
    )

    normalized_device = collector.discover_single(sanitized_hostname)
    entities = translate_single_device(normalized_device, config.defaults or Defaults())
    metadata = {"policy_name": self.name, "hostname": sanitized_hostname}

    client = Client()
    entities_list = list(entities)
    if run_id:
        apply_run_id_to_entities(entities_list, run_id)
    entity_count = len(entities_list)
    size_bytes = estimate_message_size(entities_list)

    if size_bytes > MAX_MESSAGE_SIZE_BYTES:
        chunks = create_message_chunks(entities_list)
        for i, chunk in enumerate(chunks, 1):
            response = client.diode_client.ingest(entities=chunk, metadata=metadata)
            if response.errors:
                raise RuntimeError(
                    f"Ingestion failed for {sanitized_hostname} chunk {i}: {response.errors}"
                )
        logger.info(
            "Hostname %s: Successfully ingested %d entities in %d chunks",
            sanitized_hostname, entity_count, len(chunks),
        )
    else:
        response = client.diode_client.ingest(entities=entities_list, metadata=metadata)
        if response.errors:
            raise RuntimeError(f"Ingestion failed for {sanitized_hostname}: {response.errors}")
        logger.info(
            "Hostname %s: Successfully ingested %d entities",
            sanitized_hostname, entity_count,
        )

    discovery_success = get_metric("discovery_success")
    if discovery_success:
        discovery_success.add(1, {"policy": self.name})


_original_collect_device_data = PolicyRunner._collect_device_data


def _collect_device_data(self, scope, sanitized_hostname, config, run_id=None):
    """
    Extended _collect_device_data: tries vendor collector first, falls back to upstream NAPALM path.
    """
    if self._select_collector(scope) is not None:
        self._collect_device_data_via_collector(scope, sanitized_hostname, config, run_id)
        return
    return _original_collect_device_data(self, scope, sanitized_hostname, config, run_id)


PolicyRunner._select_collector = _select_collector
PolicyRunner._collect_device_data_via_collector = _collect_device_data_via_collector
PolicyRunner._collect_device_data = _collect_device_data
