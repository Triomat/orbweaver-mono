"""
Abstract base collector.

Every vendor collector inherits from this and implements the abstract methods.
The base class provides:
- Config loading and validation
- Logging setup
- Connection lifecycle management (connect/disconnect context manager)
- The public `discover()` method that orchestrates the full flow
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

from extensions.models.common import (
    DeviceStatus,
    DiscoveryResult,
    NormalizedDevice,
    NormalizedDeviceRole,
    NormalizedDeviceType,
    NormalizedInterface,
    NormalizedLLDPNeighbor,
    NormalizedManufacturer,
    NormalizedPrefix,
    NormalizedSite,
    NormalizedVLAN,
)


@dataclass
class CollectorConfig:
    """
    Vendor-agnostic connection/discovery configuration.

    Vendor-specific collectors can extend this with additional fields
    via dataclass inheritance.
    """

    hosts: list[str] = field(default_factory=list)  # IPs or hostnames to discover
    username: str = ""
    password: str = ""
    site_name: str = ""  # default site assignment
    verify_ssl: bool = True
    timeout: int = 30
    # Optional: limit what gets collected
    collect_interfaces: bool = True
    collect_vlans: bool = True
    collect_ip_addresses: bool = True
    collect_prefixes: bool = True
    collect_lldp_neighbors: bool = True
    # Vendor-specific overrides as a dict for flexibility
    vendor_options: dict[str, Any] = field(default_factory=dict)


class BaseCollector(ABC):
    """
    Abstract base for all vendor collectors.

    Subclasses MUST implement:
        - _connect(host) -> connection handle
        - _disconnect(connection)
        - _collect_device_facts(connection, host) -> NormalizedDevice
        - _collect_interfaces(connection, device) -> list[NormalizedInterface]
        - _collect_vlans(connection, device) -> list[NormalizedVLAN]

    Subclasses MAY override:
        - _collect_prefixes(connection, device) -> list[NormalizedPrefix]
        - _post_process(result) -> DiscoveryResult  (for vendor-specific enrichment)
    """

    vendor_name: str = "unknown"

    def __init__(self, config: CollectorConfig):
        self.config = config
        self.logger = logging.getLogger(f"device_discovery.collectors.{self.vendor_name}")

    # -------------------------------------------------------------------
    # Abstract methods — vendors MUST implement these
    # -------------------------------------------------------------------

    @abstractmethod
    def _connect(self, host: str) -> Any:
        """Establish connection to the device. Return a connection handle."""
        ...

    @abstractmethod
    def _disconnect(self, connection: Any) -> None:
        """Clean up the connection."""
        ...

    @abstractmethod
    def _collect_device_facts(self, connection: Any, host: str) -> NormalizedDevice:
        """
        Collect device-level facts (hostname, model, serial, etc.)
        and return a NormalizedDevice.

        This is the most critical method — it must translate vendor-specific
        output into the COM.
        """
        ...

    @abstractmethod
    def _collect_interfaces(
        self, connection: Any, device: NormalizedDevice
    ) -> list[NormalizedInterface]:
        """Collect all interfaces and return normalized list."""
        ...

    @abstractmethod
    def _collect_vlans(self, connection: Any, device: NormalizedDevice) -> list[NormalizedVLAN]:
        """Collect all VLANs and return normalized list."""
        ...

    @abstractmethod
    def _collect_lldp_neighbors(
        self, connection: Any, device: NormalizedDevice
    ) -> list[NormalizedLLDPNeighbor]:
        """
        Collect LLDP neighbors and return normalized list.

        Uses LLDP (Link Layer Discovery Protocol) to discover physical
        connections to neighboring devices. This data is used to create
        cable connections in NetBox.

        If LLDP is not supported or unavailable, return an empty list.
        """
        ...

    # -------------------------------------------------------------------
    # Optional overrides
    # -------------------------------------------------------------------

    def _collect_prefixes(
        self, connection: Any, device: NormalizedDevice
    ) -> list[NormalizedPrefix]:
        """
        Override to collect IP prefixes/subnets from the device directly.

        Default implementation: derive prefixes from interface IPs.
        Most collectors won't need to override this — the derivation logic
        handles VLAN association, deduplication, and site linking automatically.
        """
        return self._derive_prefixes_from_ips(device)

    def _derive_prefixes_from_ips(self, device: NormalizedDevice) -> list[NormalizedPrefix]:
        """
        Walk all interface IPs and derive the subnet prefix for each.

        For example, interface Vlan110 with IP 10.0.110.1/24 produces:
          - NormalizedPrefix(prefix="10.0.110.0/24", vlan=VLAN 110, site=device.site)

        SVI interfaces (Vlan*, vlan*) get their prefix linked to the
        corresponding VLAN. Physical/loopback interfaces get a plain prefix.

        Deduplicates by network address — multiple IPs in the same /24
        only produce one prefix.
        """
        import ipaddress as _ipaddress
        import re as _re

        seen: dict[str, NormalizedPrefix] = {}

        for iface in device.interfaces:
            for ip in iface.ip_addresses:
                try:
                    iface_obj = _ipaddress.ip_interface(ip.address)
                except (ValueError, TypeError):
                    continue

                network = iface_obj.network
                prefix_str = str(network)

                # Skip host routes (/32, /128) and link-local
                if (
                    network.prefixlen in (32, 128)
                    and ip.description
                    and "mask unknown" in ip.description
                ):
                    continue
                if iface_obj.ip.is_link_local:
                    continue

                if prefix_str in seen:
                    continue

                # VLAN association: if this is an SVI (Vlan100, vlan100),
                # link the prefix to that VLAN
                vlan = None
                vlan_match = _re.match(r"(?i)vlan\s*(\d+)", iface.name)
                if vlan_match:
                    vid = int(vlan_match.group(1))
                    # Try to find the VLAN in the device's discovered VLANs
                    for dv in device.vlans:
                        if dv.vid == vid:
                            vlan = dv
                            break
                    if not vlan:
                        # Create a minimal VLAN reference
                        vlan = NormalizedVLAN(vid=vid, name=f"VLAN{vid}", site=device.site)

                # Also check if the interface has an untagged VLAN assigned
                if not vlan and iface.untagged_vlan:
                    vlan = iface.untagged_vlan

                description = f"Discovered on {iface.name}"
                if vlan:
                    description += f" (VLAN {vlan.vid})"

                seen[prefix_str] = NormalizedPrefix(
                    prefix=prefix_str,
                    vlan=vlan,
                    site=device.site,
                    description=description,
                )

        prefixes = list(seen.values())
        if prefixes:
            self.logger.info(f"  Derived {len(prefixes)} prefixes from interface IPs")
        return prefixes

    def _post_process(self, result: DiscoveryResult) -> DiscoveryResult:
        """
        Hook for vendor-specific post-processing.
        E.g., deduplicating VLANs, resolving LAG memberships, etc.
        """
        return result

    def _create_unreachable_device(self, host: str, error: Exception) -> NormalizedDevice:
        """
        Create a minimal device stub for an unreachable host.

        This allows unreachable devices to be tracked in NetBox with an
        "unreachable" tag rather than silently disappearing from inventory.
        """
        # Truncate error message to fit in comments field
        error_msg = str(error)
        if len(error_msg) > 200:
            error_msg = error_msg[:197] + "..."

        # Create placeholder site if needed
        site = NormalizedSite(name=self.config.site_name or "Unknown")

        # Create minimal device with OFFLINE status
        device = NormalizedDevice(
            name=host,
            device_type=NormalizedDeviceType(
                manufacturer=NormalizedManufacturer(name="Unknown"),
                model="Unreachable",
            ),
            role=NormalizedDeviceRole(name="Unknown"),
            site=site,
            status=DeviceStatus.OFFLINE,
            comments=f"Unreachable during discovery: {error_msg}",
            interfaces=[],
            vlans=[],
        )

        return device

    # -------------------------------------------------------------------
    # Connection lifecycle
    # -------------------------------------------------------------------

    @contextmanager
    def _connection(self, host: str) -> Generator[Any, None, None]:
        """Context manager for safe connect/disconnect."""
        conn = None
        try:
            self.logger.info(f"Connecting to {host}")
            conn = self._connect(host)
            yield conn
        finally:
            if conn is not None:
                self.logger.info(f"Disconnecting from {host}")
                try:
                    self._disconnect(conn)
                except Exception as e:
                    self.logger.warning(f"Error during disconnect from {host}: {e}")

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    def discover(self) -> DiscoveryResult:
        """
        Run full discovery across all configured hosts.

        This is the main entry point. It:
        1. Iterates over all hosts
        2. Connects and collects facts, interfaces, VLANs, IPs, prefixes
        3. Aggregates everything into a DiscoveryResult
        4. Runs post-processing

        Returns a DiscoveryResult ready for the NetBox importer.
        """
        result = DiscoveryResult(vendor=self.vendor_name)

        for host in self.config.hosts:
            try:
                device, prefixes = self._discover_single_host(host)
                result.devices.append(device)
                result.vlans.extend(device.vlans)
                result.prefixes.extend(prefixes)
            except Exception as e:
                error_msg = f"Failed to discover {host}: {e}"
                self.logger.error(error_msg, exc_info=True)
                result.errors.append(error_msg)

                # Create unreachable device stub for tracking in NetBox
                unreachable_device = self._create_unreachable_device(host, e)
                result.devices.append(unreachable_device)

        # Deduplicate VLANs and prefixes across devices
        result.vlans = self._deduplicate_vlans(result.vlans)
        result.prefixes = self._deduplicate_prefixes(result.prefixes)

        return self._post_process(result)

    def discover_single(self, host: str) -> NormalizedDevice:
        """Discover a single host. Useful for testing."""
        device, _ = self._discover_single_host(host)
        return device

    # -------------------------------------------------------------------
    # Internal orchestration
    # -------------------------------------------------------------------

    def _discover_single_host(self, host: str) -> tuple[NormalizedDevice, list[NormalizedPrefix]]:
        """Full discovery pipeline for one host. Returns (device, prefixes)."""
        with self._connection(host) as conn:
            # Step 1: Device facts (hostname, model, serial, role)
            device = self._collect_device_facts(conn, host)
            self.logger.info(
                f"Discovered device: {device.name} "
                f"({device.device_type.model}, S/N: {device.serial})"
            )

            # Step 2: VLANs (before interfaces so SVIs can reference them)
            if self.config.collect_vlans:
                device.vlans = self._collect_vlans(conn, device)
                self.logger.info(f"  → {len(device.vlans)} VLANs")

            # Step 3: Interfaces (includes IP addresses)
            if self.config.collect_interfaces:
                device.interfaces = self._collect_interfaces(conn, device)
                total_ips = sum(len(i.ip_addresses) for i in device.interfaces)
                self.logger.info(
                    f"  → {len(device.interfaces)} interfaces, {total_ips} IP addresses"
                )

            # Step 4: LLDP neighbors (after interfaces exist)
            if self.config.collect_lldp_neighbors:
                device.lldp_neighbors = self._collect_lldp_neighbors(conn, device)
                self.logger.info(f"  → {len(device.lldp_neighbors)} LLDP neighbors")

            # Step 5: Prefixes (derived from interface IPs by default)
            prefixes: list[NormalizedPrefix] = []
            if self.config.collect_prefixes:
                prefixes = self._collect_prefixes(conn, device)
                self.logger.info(f"  → {len(prefixes)} prefixes")

            return device, prefixes

    @staticmethod
    def _deduplicate_vlans(vlans: list[NormalizedVLAN]) -> list[NormalizedVLAN]:
        """Remove duplicate VLANs based on unique_key."""
        seen: dict[str, NormalizedVLAN] = {}
        for vlan in vlans:
            key = vlan.unique_key
            if key not in seen:
                seen[key] = vlan
        return list(seen.values())

    @staticmethod
    def _deduplicate_prefixes(prefixes: list[NormalizedPrefix]) -> list[NormalizedPrefix]:
        """Remove duplicate prefixes based on unique_key (CIDR string)."""
        seen: dict[str, NormalizedPrefix] = {}
        for prefix in prefixes:
            key = prefix.unique_key
            if key not in seen:
                seen[key] = prefix
        return list(seen.values())
