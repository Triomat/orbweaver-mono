"""
NAPALM Generic Collector.

Standalone collector that uses NAPALM helper functions for generic,
driver-agnostic device discovery. The specific NAPALM driver is configured
per-group via the ``driver`` option in the YAML config.

For vendor-specific enrichment (switchport modes, VLAN descriptions,
role heuristics, etc.) use the dedicated Aruba or Cisco collectors
instead — they use NAPALM as their primary backend too.
"""

from __future__ import annotations

from typing import Any

from orbweaver.collectors.base import BaseCollector
from orbweaver.collectors.napalm_helpers import (
    DRIVER_VENDOR_HINTS,
    NapalmConfig,
    build_device_from_napalm,
    build_interfaces_from_napalm,
    build_lldp_from_napalm,
    build_vlans_from_napalm,
    infer_interface_type,
    manufacturer_from_vendor,
    napalm_connect,
    napalm_disconnect,
    napalm_get_facts,
    napalm_get_interfaces,
    napalm_get_lldp,
    napalm_get_vlans,
    normalize_mac,
    slugify,
    speed_to_type,
)
from orbweaver.models.common import (
    NormalizedDevice,
    NormalizedInterface,
    NormalizedLLDPNeighbor,
    NormalizedSite,
    NormalizedVLAN,
)

# Re-export for backwards compatibility
__all__ = [
    "NapalmCollector",
    "NapalmConfig",
    "_infer_interface_type",
    "_manufacturer_from_vendor",
    "_normalize_mac",
    "_slugify",
    "_speed_to_type",
]

# Backwards-compatible aliases
_infer_interface_type = infer_interface_type
_manufacturer_from_vendor = manufacturer_from_vendor
_normalize_mac = normalize_mac
_slugify = slugify
_speed_to_type = speed_to_type


class NapalmCollector(BaseCollector):
    """
    Generic collector using the NAPALM library.

    Supports any device reachable via a NAPALM driver. The driver name
    is specified in ``NapalmConfig.driver``. All collection methods use
    shared helper functions from ``napalm_helpers``.
    """

    vendor_name = "napalm"

    def __init__(self, config: NapalmConfig):
        super().__init__(config)
        self.config: NapalmConfig = config
        self._default_site = NormalizedSite(
            name=config.site_name or "Default Site",
            slug=slugify(config.site_name) if config.site_name else "default-site",
        )
        self._current_host: str = ""
        self._discovered_vlans: dict[int, NormalizedVLAN] = {}

    def _connect(self, host: str) -> Any:
        self._current_host = host
        self._discovered_vlans = {}
        return napalm_connect(self.config, host)

    def _disconnect(self, connection: Any) -> None:
        napalm_disconnect(connection)

    def _collect_device_facts(self, connection: Any, host: str) -> NormalizedDevice:
        facts = napalm_get_facts(connection)
        vendor_hint = DRIVER_VENDOR_HINTS.get(self.config.driver, "")
        device = build_device_from_napalm(
            facts, host, self._default_site, vendor_hint, driver=self.config.driver
        )

        from orbweaver.models.version_parser import parse_version

        os_version = facts.get("os_version") or ""
        parsed = parse_version(os_version, vendor_hint=vendor_hint)
        self.logger.info(f"  Version tree: {' -> '.join(parsed.tree)}")

        return device

    def _collect_interfaces(
        self, connection: Any, device: NormalizedDevice
    ) -> list[NormalizedInterface]:
        raw_ifaces, raw_ips = napalm_get_interfaces(connection)
        if not raw_ips:
            self.logger.warning("get_interfaces_ip() failed or returned empty")
        interfaces = build_interfaces_from_napalm(raw_ifaces, raw_ips, device, self._current_host)
        return interfaces

    def _collect_vlans(self, connection: Any, device: NormalizedDevice) -> list[NormalizedVLAN]:
        raw_vlans = napalm_get_vlans(connection)
        if not raw_vlans:
            self.logger.warning("get_vlans() not supported or failed")
        vlans = build_vlans_from_napalm(raw_vlans, device.site)
        self._discovered_vlans = {v.vid: v for v in vlans}
        return vlans

    def _collect_lldp_neighbors(
        self, connection: Any, device: NormalizedDevice
    ) -> list[NormalizedLLDPNeighbor]:
        raw_lldp = napalm_get_lldp(connection)
        if not raw_lldp:
            self.logger.warning("get_lldp_neighbors_detail() failed or returned empty")
        return build_lldp_from_napalm(raw_lldp, device)
