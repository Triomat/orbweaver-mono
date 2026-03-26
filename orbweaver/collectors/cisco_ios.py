"""
Cisco IOS / IOS-XE Collector (NAPALM + CLI enrichment).

Uses the NAPALM ``ios`` driver as the primary data backend, with
CLI commands (via ``connection.cli()``) for enrichment data that
NAPALM doesn't expose (switchport modes, VLAN assignments, OS
family detection).

Translation mapping:
  - NAPALM get_facts()              -> NormalizedDevice (hostname, model, serial)
  - NAPALM get_interfaces()         -> NormalizedInterface[] (base)
  - NAPALM get_interfaces_ip()      -> NormalizedIPAddress[] (merged)
  - NAPALM get_vlans()              -> NormalizedVLAN[]
  - NAPALM get_lldp_neighbors_detail() -> NormalizedLLDPNeighbor[]
  - CLI "show version"              -> OS family detection (IOS vs IOS-XE)
  - CLI "show interfaces switchport"-> switchport mode + VLAN assignments
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any

from orbweaver.collectors.base import BaseCollector
from orbweaver.collectors.napalm_helpers import (
    NapalmConfig,
    build_interfaces_from_napalm,
    build_lldp_from_napalm,
    build_vlans_from_napalm,
    napalm_connect,
    napalm_disconnect,
    napalm_get_facts,
    napalm_get_interfaces,
    napalm_get_lldp,
    napalm_get_vlans,
    slugify,
)
from orbweaver.models.common import (
    DeviceStatus,
    InterfaceMode,
    NormalizedDevice,
    NormalizedDeviceRole,
    NormalizedDeviceType,
    NormalizedInterface,
    NormalizedLLDPNeighbor,
    NormalizedManufacturer,
    NormalizedPlatform,
    NormalizedPrefix,
    NormalizedSite,
    NormalizedVLAN,
)
from orbweaver.models.version_parser import parse_version


# ---------------------------------------------------------------------------
# Cisco-specific config
# ---------------------------------------------------------------------------


@dataclass
class CiscoConfig(NapalmConfig):
    """Cisco IOS/IOS-XE configuration.

    Hardcodes ``driver="ios"`` and adds Cisco-specific SSH options.
    """

    driver: str = "ios"
    device_type: str = "cisco_ios"  # kept for backwards compat / role heuristics
    ssh_config_file: str | None = None


# ---------------------------------------------------------------------------
# Collector implementation
# ---------------------------------------------------------------------------


class CiscoCollector(BaseCollector):
    """
    Cisco IOS/IOS-XE collector: NAPALM primary + CLI enrichment.

    The NAPALM ``ios`` driver uses Netmiko internally, so ``connection.cli()``
    gives access to arbitrary CLI commands for enrichment.
    """

    vendor_name = "cisco_ios"

    def __init__(self, config: CiscoConfig):
        super().__init__(config)
        self.config: CiscoConfig = config
        self._manufacturer = NormalizedManufacturer(name="Cisco", slug="cisco")
        self._default_site = NormalizedSite(
            name=config.site_name or "Default Site",
            slug=(
                config.site_name.lower().replace(" ", "-") if config.site_name else "default-site"
            ),
        )
        self._current_host: str = ""
        self._discovered_vlans: dict[int, NormalizedVLAN] = {}

    # ------------------------------------------------------------------
    # Connection: NAPALM ios driver with optional SSH config
    # ------------------------------------------------------------------

    def _connect(self, host: str) -> Any:
        self._current_host = host
        self._discovered_vlans = {}

        # Inject SSH config into optional_args
        if self.config.ssh_config_file:
            self.config.optional_args.setdefault("ssh_config_file", self.config.ssh_config_file)

        return napalm_connect(self.config, host)

    def _disconnect(self, connection: Any) -> None:
        napalm_disconnect(connection)

    # ------------------------------------------------------------------
    # Device facts: NAPALM + OS family detection + role heuristics
    # ------------------------------------------------------------------

    def _collect_device_facts(self, connection: Any, host: str) -> NormalizedDevice:
        facts = napalm_get_facts(connection)

        hostname = facts.get("hostname") or host
        model = facts.get("model") or "Unknown"
        serial = facts.get("serial_number") or ""
        os_version = facts.get("os_version") or ""

        # Detect IOS vs IOS-XE via CLI
        vendor_hint = self._detect_os_family(connection)

        parsed = parse_version(os_version, vendor_hint=vendor_hint)

        platform = NormalizedPlatform(
            name=parsed.platform_name,
            slug=parsed.platform_slug,
            family=parsed.family,
            version_major=parsed.major,
            version_minor=parsed.minor,
            version_full=parsed.full,
            version_raw=os_version,
            manufacturer=self._manufacturer,
            description=f"Discovered from {hostname} ({model})",
        )

        self.logger.info(f"  Version tree: {' -> '.join(parsed.tree)}")

        device_type = NormalizedDeviceType(
            manufacturer=self._manufacturer,
            model=model,
            slug=slugify(model),
        )

        role = self._infer_role(model)

        return NormalizedDevice(
            name=hostname,
            device_type=device_type,
            role=role,
            site=self._default_site,
            serial=serial,
            status=DeviceStatus.ACTIVE,
            platform=platform,
            comments=f"{parsed.family} {parsed.full}. Discovered via NAPALM (ios).",
        )

    # ------------------------------------------------------------------
    # Interfaces: NAPALM base + CLI switchport enrichment
    # ------------------------------------------------------------------

    def _collect_interfaces(
        self, connection: Any, device: NormalizedDevice
    ) -> list[NormalizedInterface]:
        raw_ifaces, raw_ips = napalm_get_interfaces(connection)
        if not raw_ips:
            self.logger.warning("get_interfaces_ip() failed or returned empty")

        interfaces = build_interfaces_from_napalm(raw_ifaces, raw_ips, device, self._current_host)
        iface_map = {i.name: i for i in interfaces}

        # Enrich with switchport data via CLI
        self._enrich_switchport_data(connection, device, iface_map)

        # If primary IP still not found, store management IP for post-processing
        if not device.primary_ip4:
            device.custom_fields["management_ip"] = self._current_host
            self.logger.info(
                f"  Management IP not found in device output, "
                f"storing for post-processing: {self._current_host}"
            )

        interfaces = list(iface_map.values())
        total_ips = sum(len(iface.ip_addresses) for iface in interfaces)
        self.logger.info(f"  -> {total_ips} IP addresses across {len(interfaces)} interfaces")

        return interfaces

    # ------------------------------------------------------------------
    # VLANs
    # ------------------------------------------------------------------

    def _collect_vlans(self, connection: Any, device: NormalizedDevice) -> list[NormalizedVLAN]:
        raw_vlans = napalm_get_vlans(connection)
        if raw_vlans:
            vlans = build_vlans_from_napalm(raw_vlans, device.site)
            self._discovered_vlans = {v.vid: v for v in vlans}
            return vlans

        # Fallback: use CLI "show vlan brief" parsed via TextFSM
        self.logger.info("NAPALM get_vlans() empty, falling back to CLI 'show vlan brief'")
        vlans = self._collect_vlans_cli(connection, device)
        self._discovered_vlans = {v.vid: v for v in vlans}
        return vlans

    def _collect_vlans_cli(self, connection: Any, device: NormalizedDevice) -> list[NormalizedVLAN]:
        """Parse 'show vlan brief' via CLI + TextFSM as fallback for NAPALM."""
        try:
            # NAPALM ios driver exposes the underlying Netmiko connection
            netmiko_conn = connection.device
            raw = netmiko_conn.send_command("show vlan brief", use_textfsm=True)
        except Exception as e:
            self.logger.warning(f"CLI VLAN fallback failed: {e}")
            return []

        vlans: list[NormalizedVLAN] = []
        if isinstance(raw, list):
            for entry in raw:
                try:
                    vid = int(entry.get("vlan_id", 0))
                    name = entry.get("name", f"VLAN{vid}")
                    status = "active" if entry.get("status", "active") == "active" else "reserved"
                    vlans.append(
                        NormalizedVLAN(vid=vid, name=name, site=device.site, status=status)
                    )
                except (ValueError, TypeError):
                    continue

        self.logger.info(f"  -> {len(vlans)} VLANs from CLI fallback")
        return vlans

    # ------------------------------------------------------------------
    # LLDP neighbors
    # ------------------------------------------------------------------

    def _collect_lldp_neighbors(
        self, connection: Any, device: NormalizedDevice
    ) -> list[NormalizedLLDPNeighbor]:
        raw_lldp = napalm_get_lldp(connection)
        if not raw_lldp:
            self.logger.warning("get_lldp_neighbors_detail() failed or returned empty")
        return build_lldp_from_napalm(raw_lldp, device)

    # ------------------------------------------------------------------
    # Switchport enrichment
    # ------------------------------------------------------------------

    def _enrich_switchport_data(
        self,
        connection: Any,
        device: NormalizedDevice,
        iface_map: dict[str, NormalizedInterface],
    ) -> None:
        try:
            cli_output = connection.cli(["show interfaces switchport"])
            raw = cli_output.get("show interfaces switchport", "")
        except Exception as e:
            self.logger.warning(f"CLI switchport enrichment failed: {e}")
            return

        if not raw:
            return

        entries = self._parse_switchport_raw(raw)

        for entry in entries:
            iface_name = entry.get("interface", "")
            if not iface_name:
                continue

            iface_name = self._normalize_iface_name(iface_name, iface_map)
            if iface_name not in iface_map:
                continue

            iface = iface_map[iface_name]
            mode_str = entry.get("switchport_mode", "").lower()

            # Fall back to administrative mode when operational mode is "down"
            if not mode_str or mode_str == "down":
                mode_str = entry.get("admin_mode", "").lower()

            if not mode_str:
                continue

            if "trunk" in mode_str:
                iface.mode = InterfaceMode.TAGGED

                native_vid = self._parse_int(entry.get("native_vlan", ""))
                if native_vid and native_vid in self._discovered_vlans:
                    iface.untagged_vlan = self._discovered_vlans[native_vid]

                trunk_vlans_str = entry.get("trunking_vlans", "")
                if isinstance(trunk_vlans_str, list):
                    trunk_vlans_str = ",".join(trunk_vlans_str)
                vlan_ids = self._expand_vlan_range(trunk_vlans_str)
                iface.tagged_vlans = [
                    self._discovered_vlans[vid] for vid in vlan_ids if vid in self._discovered_vlans
                ]

            elif "access" in mode_str:
                iface.mode = InterfaceMode.ACCESS
                access_vid = self._parse_int(entry.get("access_vlan", ""))
                if access_vid and access_vid in self._discovered_vlans:
                    iface.untagged_vlan = self._discovered_vlans[access_vid]

    # ------------------------------------------------------------------
    # Prefix derivation (override to link SVI VLANs)
    # ------------------------------------------------------------------

    def _collect_prefixes(
        self, connection: Any, device: NormalizedDevice
    ) -> list[NormalizedPrefix]:
        seen_prefixes: dict[str, NormalizedPrefix] = {}

        for iface in device.interfaces:
            for ip in iface.ip_addresses:
                try:
                    network = ipaddress.ip_interface(ip.address).network
                    prefix_str = str(network)

                    if network.prefixlen in (32, 128):
                        continue

                    if prefix_str not in seen_prefixes:
                        linked_vlan = None
                        if iface.untagged_vlan:
                            linked_vlan = iface.untagged_vlan
                        elif iface.name.lower().startswith("vlan"):
                            vlan_match = re.match(r"[Vv]lan(\d+)", iface.name)
                            if vlan_match:
                                vid = int(vlan_match.group(1))
                                linked_vlan = self._discovered_vlans.get(vid)

                        seen_prefixes[prefix_str] = NormalizedPrefix(
                            prefix=prefix_str,
                            vlan=linked_vlan,
                            site=device.site,
                            description=f"Discovered from {iface.name} on {device.name}",
                        )
                except (ValueError, TypeError) as e:
                    self.logger.debug(f"Could not derive prefix from {ip.address}: {e}")

        prefixes = list(seen_prefixes.values())
        self.logger.info(f"  -> {len(prefixes)} prefixes derived from interface IPs")
        return prefixes

    # ------------------------------------------------------------------
    # OS family detection
    # ------------------------------------------------------------------

    def _detect_os_family(self, connection: Any) -> str:
        try:
            cli_output = connection.cli(["show version"])
            raw = cli_output.get("show version", "")
        except Exception:
            return "cisco_ios"

        return self._detect_os_family_from_text(raw)

    @staticmethod
    def _detect_os_family_from_text(raw: str) -> str:
        raw_lower = raw.lower()
        if "ios-xe" in raw_lower or "iosxe" in raw_lower:
            return "cisco_iosxe"
        if any(
            train in raw_lower
            for train in [
                "denali",
                "everest",
                "fuji",
                "gibraltar",
                "amsterdam",
                "bengaluru",
                "cupertino",
                "dublin",
            ]
        ):
            return "cisco_iosxe"
        if "nx-os" in raw_lower or "nexus" in raw_lower:
            return "cisco_nxos"
        return "cisco_ios"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _infer_role(self, model: str) -> NormalizedDeviceRole:
        model_lower = model.lower()
        if any(kw in model_lower for kw in ["2960", "3560", "9200", "1000"]):
            return NormalizedDeviceRole(name="Access Switch", slug="access-switch", color="4caf50")
        elif any(kw in model_lower for kw in ["3650", "3850", "9300"]):
            return NormalizedDeviceRole(
                name="Distribution Switch", slug="distribution-switch", color="2196f3"
            )
        elif any(kw in model_lower for kw in ["9500", "6500", "4500"]):
            return NormalizedDeviceRole(name="Core Switch", slug="core-switch", color="f44336")
        elif any(kw in model_lower for kw in ["isr", "asr", "csr", "4331", "4431"]):
            return NormalizedDeviceRole(name="Router", slug="router", color="ff9800")
        return NormalizedDeviceRole(name="Network Device", slug="network-device")

    @staticmethod
    def _normalize_iface_name(name: str, iface_map: dict[str, NormalizedInterface]) -> str:
        if name in iface_map:
            return name

        abbreviations = {
            "fa": "FastEthernet",
            "gi": "GigabitEthernet",
            "te": "TenGigabitEthernet",
            "fo": "FortyGigabitEthernet",
            "hu": "HundredGigE",
            "po": "Port-channel",
            "lo": "Loopback",
            "vl": "Vlan",
        }

        name_lower = name.lower()
        for short, full in abbreviations.items():
            if name_lower.startswith(short) and not name_lower.startswith(full.lower()):
                suffix = name[len(short) :]
                candidate = f"{full}{suffix}"
                if candidate in iface_map:
                    return candidate
            if name_lower.startswith(full.lower()):
                suffix = name[len(full) :]
                candidate_short = f"{short.capitalize()}{suffix}"
                if candidate_short in iface_map:
                    return candidate_short

        return name

    @staticmethod
    def _expand_vlan_range(vlan_str: str) -> list[int]:
        if not vlan_str or vlan_str.upper() in ("ALL", "NONE", ""):
            return []

        vlan_ids: list[int] = []
        for part in vlan_str.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    start, end = part.split("-", 1)
                    start_int = int(start.strip())
                    end_int = int(end.strip())
                    if (end_int - start_int) > 500:
                        continue
                    vlan_ids.extend(range(start_int, end_int + 1))
                except (ValueError, TypeError):
                    continue
            else:
                try:
                    vlan_ids.append(int(part))
                except (ValueError, TypeError):
                    continue
        return vlan_ids

    @staticmethod
    def _parse_switchport_raw(raw: str) -> list[dict]:
        entries: list[dict] = []
        current: dict = {}

        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("Name:"):
                if current:
                    entries.append(current)
                current = {"interface": line.split(":", 1)[1].strip()}
            elif "Administrative Mode:" in line:
                current["admin_mode"] = line.split(":", 1)[1].strip().lower()
            elif "Operational Mode:" in line:
                current["switchport_mode"] = line.split(":", 1)[1].strip().lower()
            elif "Access Mode VLAN:" in line:
                vid = re.search(r"(\d+)", line.split(":", 1)[1])
                if vid:
                    current["access_vlan"] = vid.group(1)
            elif "Trunking Native Mode VLAN:" in line:
                vid = re.search(r"(\d+)", line.split(":", 1)[1])
                if vid:
                    current["native_vlan"] = vid.group(1)
            elif "Trunking VLANs Enabled:" in line:
                current["trunking_vlans"] = line.split(":", 1)[1].strip()

        if current:
            entries.append(current)
        return entries

    @staticmethod
    def _parse_int(value: str | int) -> int | None:
        if isinstance(value, int):
            return value
        if not value:
            return None
        try:
            return int(str(value).strip())
        except (ValueError, TypeError):
            return None
