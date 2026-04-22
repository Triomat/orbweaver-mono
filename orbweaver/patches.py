"""
orbweaver runtime patches.

Applied once at startup BEFORE device_discovery.server is imported.
Extends upstream classes without modifying any upstream files.
"""
from __future__ import annotations

import dataclasses
import logging
import time

logger = logging.getLogger(__name__)

# ── 1. Add collector field to upstream Napalm model ──────────────────────────
#
# Pydantic v2 allows adding fields at runtime via model_rebuild().
# The upstream Napalm model is extended in-place; no upstream file is touched.

from pydantic.fields import FieldInfo  # noqa: E402
from device_discovery.policy.models import Config, Defaults, Napalm, Policy, PolicyRequest  # noqa: E402

# model_rebuild() uses __annotations__ as its source of truth, so we must update
# it alongside model_fields — otherwise the new field is silently dropped.

# ── 1a. Add collector field to Napalm ────────────────────────────────────────
Napalm.__annotations__["collector"] = str | None
Napalm.model_fields["collector"] = FieldInfo(
    default=None,
    annotation=str | None,
    description=(
        "Vendor collector name (cisco_ios, aruba_aoscx, napalm). "
        "When set, uses the orbweaver collector framework instead of the generic NAPALM path."
    ),
)

# ── 1c. Add rack field to Napalm (per-device rack override) ─────────────────
Napalm.__annotations__["rack"] = str | None
Napalm.model_fields["rack"] = FieldInfo(
    default=None,
    annotation=str | None,
    description="Rack name to assign this device to in NetBox. Overrides defaults.rack.",
)

# ── 1d. Add rack field to Defaults (policy-level rack default) ───────────────
Defaults.__annotations__["rack"] = str | None
Defaults.model_fields["rack"] = FieldInfo(
    default=None,
    annotation=str | None,
    description="Rack name to assign all devices in this policy to in NetBox.",
)

# ── 1b. Add auto_ingest flag to Config ───────────────────────────────────────
Config.__annotations__["auto_ingest"] = bool
Config.model_fields["auto_ingest"] = FieldInfo(
    default=False,
    annotation=bool,
    description=(
        "When True, skip the manual review step and ingest all discovered devices "
        "directly into NetBox via Diode. A review session is still created for audit."
    ),
)

# Rebuild all models that embed the patched types so their cached validators
# reflect the new fields. Defaults must come before Config (Config embeds Defaults).
Defaults.model_rebuild(force=True)
Napalm.model_rebuild(force=True)
Config.model_rebuild(force=True)
Policy.model_rebuild(force=True)
PolicyRequest.model_rebuild(force=True)


# ── 2. Extend PolicyRunner with vendor collector support ──────────────────────
#
# Three methods are patched onto the class:
#   _select_collector             — picks the right vendor collector (or None)
#   _collect_device_data_via_collector — runs the COM collector path
#   _collect_device_data          — wraps the upstream method to try collector first

from device_discovery.policy.runner import PolicyRunner  # noqa: E402
from device_discovery.client import Client, MAX_MESSAGE_SIZE_BYTES  # noqa: E402
from device_discovery.entity_metadata import apply_run_id_to_entities  # noqa: E402
from device_discovery.metrics import get_metric  # noqa: E402
from netboxlabs.diode.sdk import create_message_chunks, estimate_message_size  # noqa: E402
from orbweaver.collectors.registry import get_collector, list_collectors  # noqa: E402
from orbweaver.diode_translate import translate_primary_ip_entities, translate_single_device  # noqa: E402


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
    _defaults = config.defaults or Defaults()
    normalized_device.rack = getattr(scope, "rack", None) or getattr(_defaults, "rack", None) or ""
    entities = translate_single_device(normalized_device, _defaults)
    primary_ip_ents = translate_primary_ip_entities(normalized_device, _defaults)
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

    # Second ingest call: set primary_ip4/ip6 after the interface IP assignments
    # are committed. A delay lets the Diode reconciler process pass 1 before
    # pass 2 tries to designate a primary IP (NetBox rejects it if the IP isn't
    # yet assigned to a device interface).
    if primary_ip_ents:
        time.sleep(10)
        if run_id:
            apply_run_id_to_entities(primary_ip_ents, run_id)
        response = client.diode_client.ingest(
            entities=primary_ip_ents,
            metadata={**metadata, "pass": "primary_ips"},
        )
        if response.errors:
            raise RuntimeError(
                f"Primary IP ingest failed for {sanitized_hostname}: {response.errors}"
            )
        logger.info("Hostname %s: primary IPs set", sanitized_hostname)

    # Pass 3: assign rack via pynetbox. Diode cannot match existing racks by
    # site+name (see docs/upstream-issues.md), so rack is excluded from Diode
    # entities and set here instead using the NetBox REST API directly.
    if normalized_device.rack:
        site_name = ""
        if _defaults and _defaults.site and _defaults.site != "undefined":
            site_name = _defaults.site
        elif normalized_device.site:
            site_name = normalized_device.site.name
        if site_name:
            from orbweaver.netbox_ops import assign_device_rack
            assign_device_rack(normalized_device.name, site_name, normalized_device.rack)

    discovery_success = get_metric("discovery_success")
    if discovery_success:
        discovery_success.add(1, {"policy": self.name})

    return entity_count


_original_collect_device_data = PolicyRunner._collect_device_data


def _collect_device_data(self, scope, sanitized_hostname, config, run_id=None):
    """
    Extended _collect_device_data: tries vendor collector first, falls back to upstream NAPALM path.
    """
    if self._select_collector(scope) is not None:
        return self._collect_device_data_via_collector(scope, sanitized_hostname, config, run_id)
    return _original_collect_device_data(self, scope, sanitized_hostname, config, run_id)


PolicyRunner._select_collector = _select_collector
PolicyRunner._collect_device_data_via_collector = _collect_device_data_via_collector
PolicyRunner._collect_device_data = _collect_device_data
