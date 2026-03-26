"""
Aruba AOS-CX Collector (NAPALM primary, REST fallback).

Tries the ``napalm-aruba-cx`` community NAPALM driver first.  If that
fails (driver not installed, API version mismatch, etc.) the collector
falls back to pure REST API mode — the same approach used before the
NAPALM migration.

When NAPALM is available, REST API calls provide enrichment data that
NAPALM doesn't expose (switchport modes, VLAN descriptions, LAG
membership, subsystem serial numbers).

When NAPALM is unavailable, REST alone provides all data.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any

import requests
from urllib3.exceptions import InsecureRequestWarning

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
    normalize_mac,
    slugify,
)
from orbweaver.models.common import (
    DeviceStatus,
    InterfaceMode,
    InterfaceType,
    IPAddressRole,
    NormalizedDevice,
    NormalizedDeviceRole,
    NormalizedDeviceType,
    NormalizedIPAddress,
    NormalizedInterface,
    NormalizedLLDPNeighbor,
    NormalizedManufacturer,
    NormalizedPlatform,
    NormalizedSite,
    NormalizedVLAN,
)
from orbweaver.models.version_parser import parse_aruba_aoscx_version


# ---------------------------------------------------------------------------
# Aruba-specific config
# ---------------------------------------------------------------------------


@dataclass
class ArubaConfig(NapalmConfig):
    """Aruba AOS-CX configuration.

    Hardcodes ``driver="aoscx"`` and adds REST API options for enrichment.
    """

    driver: str = "aoscx"
    api_version: str = "v10.13"
    use_https: bool = True
    rest_api_port: int = 443


# ---------------------------------------------------------------------------
# VLAN mode mapping
# ---------------------------------------------------------------------------


def _map_vlan_mode(mode_str: str | None) -> InterfaceMode | None:
    if not mode_str:
        return None
    mode_map = {
        "access": InterfaceMode.ACCESS,
        "trunk": InterfaceMode.TAGGED,
        "native-tagged": InterfaceMode.TAGGED_ALL,
        "native-untagged": InterfaceMode.TAGGED,
    }
    return mode_map.get(mode_str.lower())


# ---------------------------------------------------------------------------
# Interface type mapping: Aruba speed/type -> COM InterfaceType
# ---------------------------------------------------------------------------

ARUBA_SPEED_MAP: dict[int, InterfaceType] = {
    1000: InterfaceType.ONETHOUSANDBASE_T,
    10000: InterfaceType.TENGBASE_X_SFP_PLUS,
    25000: InterfaceType.TWENTYFIVEGBASE_X_SFP28,
    40000: InterfaceType.FORTYGBASE_X_QSFP_PLUS,
    100000: InterfaceType.HUNDREDGBASE_X_QSFP28,
}


# Known AOS-CX REST API versions, newest first.  Used as a last-resort
# fallback when /rest/version discovery fails.
_AOSCX_API_VERSIONS = [
    "v10.13",
    "v10.12",
    "v10.11",
    "v10.10",
    "v10.09",
    "v10.08",
    "v10.04",
    "v1",
]


def _guess_interface_type(iface_data: dict) -> InterfaceType:
    """Map Aruba interface data to a COM InterfaceType."""
    iface_type = iface_data.get("type", "")
    if iface_type == "lag":
        return InterfaceType.LAG
    if iface_type in ("loopback", "vlan"):
        return InterfaceType.VIRTUAL

    speed = iface_data.get("link_speed", 0)
    if speed in ARUBA_SPEED_MAP:
        return ARUBA_SPEED_MAP[speed]

    return InterfaceType.OTHER


# ---------------------------------------------------------------------------
# Connection wrapper: holds both NAPALM device and REST session
# ---------------------------------------------------------------------------


class _ArubaConnection:
    """Bundles an optional NAPALM device handle and an AOS-CX REST session."""

    __slots__ = ("napalm", "rest", "base_url", "api_version")

    def __init__(
        self,
        napalm_device: Any | None,
        rest_session: requests.Session | None,
        base_url: str,
        api_version: str,
    ):
        self.napalm = napalm_device
        self.rest = rest_session
        self.base_url = base_url
        self.api_version = api_version

    @property
    def has_napalm(self) -> bool:
        return self.napalm is not None

    # Proxy NAPALM getters so callers can use conn.get_facts() etc.
    def __getattr__(self, name: str) -> Any:
        if self.napalm is not None:
            return getattr(self.napalm, name)
        raise AttributeError(f"NAPALM not available; no attribute '{name}'")


# ---------------------------------------------------------------------------
# Collector implementation
# ---------------------------------------------------------------------------


class ArubaCollector(BaseCollector):
    """
    Aruba AOS-CX collector: NAPALM primary + REST API fallback/enrichment.

    Connection handle is an ``_ArubaConnection`` wrapping both an optional
    NAPALM device object and a ``requests.Session`` for REST API calls.

    If the NAPALM aoscx driver is not installed or fails to connect, the
    collector falls back to pure REST API mode (the pre-NAPALM approach).
    """

    vendor_name = "aruba_aoscx"

    def __init__(self, config: ArubaConfig):
        super().__init__(config)
        self.config: ArubaConfig = config
        self._manufacturer = NormalizedManufacturer(name="Aruba", slug="aruba")
        self._default_site = NormalizedSite(
            name=config.site_name or "Default Site",
            slug=(
                config.site_name.lower().replace(" ", "-") if config.site_name else "default-site"
            ),
        )
        self._current_host: str = ""
        self._discovered_vlans: dict[int, NormalizedVLAN] = {}

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def _connect(self, host: str) -> _ArubaConnection:
        self._current_host = host
        self._discovered_vlans = {}
        self._active_api_version = self.config.api_version

        base_url = self._base_url(host)

        # 1. Try NAPALM connection (aoscx driver)
        napalm_device = None
        try:
            napalm_device = napalm_connect(self.config, host)
            self.logger.info(f"NAPALM (aoscx) connected to {host}")
        except Exception as e:
            self.logger.warning(
                f"NAPALM (aoscx) connection failed for {host}: {e}. Falling back to REST-only mode."
            )

        # 2. Open REST session (for enrichment or as primary if NAPALM failed)
        rest_session = self._open_rest_session(host, base_url)

        if napalm_device is None and rest_session is None:
            raise ConnectionError(f"Cannot connect to {host}: both NAPALM and REST API failed")

        return _ArubaConnection(napalm_device, rest_session, base_url, self._active_api_version)

    def _open_rest_session(self, host: str, base_url: str) -> requests.Session | None:
        """Authenticate to AOS-CX REST API, return session or None."""
        session = requests.Session()
        session.verify = self.config.verify_ssl
        if not self.config.verify_ssl:
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

        versions_to_try: list[str] = [self.config.api_version]

        discovered = self._discover_api_version(session, base_url)
        if discovered and discovered not in versions_to_try:
            versions_to_try.append(discovered)

        for v in _AOSCX_API_VERSIONS:
            if v not in versions_to_try:
                versions_to_try.append(v)

        for api_version in versions_to_try:
            if self._try_rest_login(session, base_url, api_version, host):
                self._active_api_version = api_version
                self.logger.info(f"REST API connected to {host} (API {api_version})")
                return session

        self.logger.warning(f"REST API login failed for {host}: no working API version found")
        session.close()
        return None

    def _try_rest_login(
        self, session: requests.Session, base_url: str, api_version: str, host: str
    ) -> bool:
        """Attempt REST login with a specific API version. Returns True on success."""
        login_url = f"{base_url}/rest/{api_version}/login"
        try:
            resp = session.post(
                login_url,
                data={"username": self.config.username, "password": self.config.password},
                timeout=self.config.timeout,
            )
            resp.raise_for_status()
            self.logger.debug(f"REST API authenticated to {host} (API {api_version})")
            return True
        except Exception as e:
            self.logger.debug(f"REST login failed for {host} with API {api_version}: {e}")
            return False

    def _discover_api_version(self, session: requests.Session, base_url: str) -> str | None:
        """Query /rest/version to find the latest supported API version."""
        try:
            resp = session.get(f"{base_url}/rest/version", timeout=self.config.timeout)
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, dict):
                latest = data.get("latest", {})
                if isinstance(latest, dict) and "version" in latest:
                    version = latest["version"]
                    self.logger.info(f"Discovered REST API version: {version}")
                    return version

                if "version" in data:
                    version = data["version"]
                    self.logger.info(f"Discovered REST API version: {version}")
                    return version

                versions = sorted(
                    (k for k in data if k.startswith("v")),
                    reverse=True,
                )
                if versions:
                    self.logger.info(
                        f"Discovered REST API versions: {versions}, using {versions[0]}"
                    )
                    return versions[0]

            self.logger.debug(f"Could not parse /rest/version response: {data}")
        except Exception as e:
            self.logger.debug(f"API version discovery failed: {e}")

        return None

    def _disconnect(self, connection: _ArubaConnection) -> None:
        # Logout REST session
        if connection.rest is not None:
            try:
                connection.rest.post(
                    f"{connection.base_url}/rest/{connection.api_version}/logout",
                    timeout=self.config.timeout,
                )
            except Exception:
                pass
            connection.rest.close()

        # Close NAPALM
        if connection.napalm is not None:
            napalm_disconnect(connection.napalm)

    # ------------------------------------------------------------------
    # REST API helpers
    # ------------------------------------------------------------------

    def _base_url(self, host: str) -> str:
        scheme = "https" if self.config.use_https else "http"
        return f"{scheme}://{host}:{self.config.rest_api_port}"

    def _rest_get(self, conn: _ArubaConnection, path: str, params: dict | None = None) -> dict:
        if conn.rest is None:
            return {}
        url = f"{conn.base_url}/rest/{conn.api_version}/{path.lstrip('/')}"
        resp = conn.rest.get(url, params=params or {}, timeout=self.config.timeout)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Device facts: NAPALM or REST
    # ------------------------------------------------------------------

    def _collect_device_facts(self, connection: _ArubaConnection, host: str) -> NormalizedDevice:
        if connection.has_napalm:
            return self._collect_device_facts_napalm(connection, host)
        return self._collect_device_facts_rest(connection, host)

    def _collect_device_facts_napalm(
        self, connection: _ArubaConnection, host: str
    ) -> NormalizedDevice:
        facts = napalm_get_facts(connection.napalm)

        hostname = facts.get("hostname") or host
        model = facts.get("model") or "Unknown Aruba"
        serial = facts.get("serial_number") or ""
        os_version = facts.get("os_version") or ""

        # REST fallback for serial number
        if not serial and connection.rest is not None:
            serial = self._fetch_serial_from_rest(connection)

        return self._build_device(hostname, model, serial, os_version, napalm_mode=True)

    def _collect_device_facts_rest(
        self, connection: _ArubaConnection, host: str
    ) -> NormalizedDevice:
        system = self._rest_get(connection, "/system", params={"depth": 2})

        hostname = system.get("hostname", host)
        model = system.get("platform_name", "Unknown Aruba")
        serial = system.get("other_config", {}).get("serial_number", "")
        os_version = system.get("software_version", "")

        if not serial:
            serial = self._fetch_serial_from_rest(connection)

        return self._build_device(hostname, model, serial, os_version, napalm_mode=False)

    def _build_device(
        self,
        hostname: str,
        model: str,
        serial: str,
        os_version: str,
        *,
        napalm_mode: bool,
    ) -> NormalizedDevice:
        parsed = parse_aruba_aoscx_version(os_version)

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
        role = self._infer_device_role(model)
        mode_label = "NAPALM (aoscx) + REST" if napalm_mode else "REST API"

        return NormalizedDevice(
            name=hostname,
            device_type=device_type,
            role=role,
            site=self._default_site,
            serial=serial,
            status=DeviceStatus.ACTIVE,
            platform=platform,
            comments=f"AOS-CX {parsed.full}. Discovered via {mode_label}.",
        )

    def _fetch_serial_from_rest(self, conn: _ArubaConnection) -> str:
        try:
            system = self._rest_get(conn, "/system", params={"depth": 2})
            serial = system.get("other_config", {}).get("serial_number", "")
            if serial:
                return serial
        except Exception:
            pass

        try:
            subsystems = self._rest_get(conn, "/system/subsystems")
            for name in subsystems:
                if "chassis" in name.lower() or "management_module" in name.lower():
                    try:
                        sub_data = self._rest_get(conn, f"/system/subsystems/{name}")
                        serial = sub_data.get("serial_number", "")
                        if serial:
                            return serial
                    except requests.HTTPError:
                        continue
        except requests.HTTPError:
            self.logger.debug("Subsystem endpoint not accessible, skipping serial lookup")

        return ""

    # ------------------------------------------------------------------
    # Interfaces: NAPALM base + REST enrichment, or REST-only
    # ------------------------------------------------------------------

    def _collect_interfaces(
        self, connection: _ArubaConnection, device: NormalizedDevice
    ) -> list[NormalizedInterface]:
        if connection.has_napalm:
            raw_ifaces, raw_ips = napalm_get_interfaces(connection.napalm)
            if not raw_ips:
                self.logger.warning("get_interfaces_ip() failed or returned empty")
            interfaces = build_interfaces_from_napalm(
                raw_ifaces, raw_ips, device, self._current_host
            )
            if connection.rest is not None:
                iface_map = {i.name: i for i in interfaces}
                self._enrich_interfaces_from_rest(connection, device, iface_map)
                interfaces = list(iface_map.values())
            return interfaces

        # REST-only mode
        return self._collect_interfaces_rest(connection, device)

    def _collect_interfaces_rest(
        self, connection: _ArubaConnection, device: NormalizedDevice
    ) -> list[NormalizedInterface]:
        """Collect interfaces purely from REST API (fallback mode)."""
        raw_interfaces = self._rest_get(connection, "/system/interfaces", params={"depth": 2})
        interfaces: list[NormalizedInterface] = []

        for iface_name, iface_ref in raw_interfaces.items():
            iface_data = self._rest_get(
                connection,
                f"/system/interfaces/{requests.utils.quote(iface_name, safe='')}",
            )
            iface = self._translate_rest_interface(iface_data, iface_name, device)
            interfaces.append(iface)

            # Primary IP detection
            if not device.primary_ip4 and self._current_host:
                for ip_obj in iface.ip_addresses:
                    try:
                        iface_addr = ipaddress.ip_interface(ip_obj.address)
                        if str(iface_addr.ip) == self._current_host:
                            device.primary_ip4 = ip_obj.address
                            self.logger.info(f"  Primary IPv4: {ip_obj.address} (on {iface_name})")
                            break
                    except (ValueError, TypeError):
                        continue

        return interfaces

    def _translate_rest_interface(
        self, iface_data: dict, iface_name: str, device: NormalizedDevice
    ) -> NormalizedInterface:
        """Translate a single Aruba REST interface dict -> NormalizedInterface."""
        enabled = iface_data.get("admin_state", "up") == "up"
        description = iface_data.get("description", "")
        mac = iface_data.get("mac_addr", "")
        mtu = iface_data.get("mtu", None)
        speed = iface_data.get("link_speed", None)

        vlan_mode = _map_vlan_mode(iface_data.get("vlan_mode"))
        untagged_vlan = None
        tagged_vlans = []

        vlan_tag = iface_data.get("vlan_tag")
        if vlan_tag and isinstance(vlan_tag, dict):
            for vlan_uri in vlan_tag:
                vid = self._extract_vlan_id(vlan_uri)
                if vid is not None:
                    untagged_vlan = NormalizedVLAN(vid=vid, name=f"VLAN{vid}", site=device.site)

        vlan_trunks = iface_data.get("vlan_trunks", {})
        if isinstance(vlan_trunks, dict):
            for vlan_uri in vlan_trunks:
                vid = self._extract_vlan_id(vlan_uri)
                if vid is not None:
                    tagged_vlans.append(
                        NormalizedVLAN(vid=vid, name=f"VLAN{vid}", site=device.site)
                    )

        ip_addresses = self._extract_ip_addresses(iface_data, iface_name, device.name)

        lag_parent = None
        bond_status = iface_data.get("bond_status", {})
        if bond_status and isinstance(bond_status, dict):
            lag_uri = bond_status.get("bond_active_member_of")
            if lag_uri:
                lag_parent = lag_uri.split("/")[-1]

        return NormalizedInterface(
            name=iface_name,
            type=_guess_interface_type(iface_data),
            enabled=enabled,
            description=description,
            mac_address=mac,
            mtu=mtu,
            speed=speed,
            mode=vlan_mode,
            untagged_vlan=untagged_vlan,
            tagged_vlans=tagged_vlans,
            ip_addresses=ip_addresses,
            lag=lag_parent,
        )

    def _enrich_interfaces_from_rest(
        self,
        conn: _ArubaConnection,
        device: NormalizedDevice,
        iface_map: dict[str, NormalizedInterface],
    ) -> None:
        try:
            raw_interfaces = self._rest_get(conn, "/system/interfaces", params={"depth": 2})
        except Exception as e:
            self.logger.warning(f"REST interface enrichment failed: {e}")
            return

        for iface_name in raw_interfaces:
            try:
                iface_data = self._rest_get(
                    conn,
                    f"/system/interfaces/{requests.utils.quote(iface_name, safe='')}",
                )
            except Exception:
                continue

            if iface_name not in iface_map:
                continue

            iface = iface_map[iface_name]

            # Switchport mode
            vlan_mode = _map_vlan_mode(iface_data.get("vlan_mode"))
            if vlan_mode:
                iface.mode = vlan_mode

            # Untagged VLAN
            vlan_tag = iface_data.get("vlan_tag")
            if vlan_tag and isinstance(vlan_tag, dict):
                for vlan_uri in vlan_tag:
                    vid = self._extract_vlan_id(vlan_uri)
                    if vid is not None:
                        iface.untagged_vlan = NormalizedVLAN(
                            vid=vid, name=f"VLAN{vid}", site=device.site
                        )

            # Tagged VLANs
            vlan_trunks = iface_data.get("vlan_trunks", {})
            if isinstance(vlan_trunks, dict):
                tagged = []
                for vlan_uri in vlan_trunks:
                    vid = self._extract_vlan_id(vlan_uri)
                    if vid is not None:
                        tagged.append(NormalizedVLAN(vid=vid, name=f"VLAN{vid}", site=device.site))
                if tagged:
                    iface.tagged_vlans = tagged

            # LAG membership
            bond_status = iface_data.get("bond_status", {})
            if bond_status and isinstance(bond_status, dict):
                lag_uri = bond_status.get("bond_active_member_of")
                if lag_uri:
                    iface.lag = lag_uri.split("/")[-1]

            # REST IP addresses (supplement NAPALM if missing)
            if not iface.ip_addresses:
                rest_ips = self._extract_ip_addresses(iface_data, iface_name, device.name)
                iface.ip_addresses.extend(rest_ips)

                # Primary IP detection
                if not device.primary_ip4 and self._current_host:
                    for ip_obj in rest_ips:
                        try:
                            iface_addr = ipaddress.ip_interface(ip_obj.address)
                            if str(iface_addr.ip) == self._current_host:
                                device.primary_ip4 = ip_obj.address
                                self.logger.info(
                                    f"  Primary IPv4: {ip_obj.address} (on {iface_name})"
                                )
                                break
                        except (ValueError, TypeError):
                            continue

    # ------------------------------------------------------------------
    # VLANs: NAPALM base + REST enrichment, or REST-only
    # ------------------------------------------------------------------

    def _collect_vlans(
        self, connection: _ArubaConnection, device: NormalizedDevice
    ) -> list[NormalizedVLAN]:
        if connection.has_napalm:
            raw_vlans = napalm_get_vlans(connection.napalm)
            if not raw_vlans:
                self.logger.warning("get_vlans() not supported or failed")
                vlans: list[NormalizedVLAN] = []
            else:
                vlans = build_vlans_from_napalm(raw_vlans, device.site)
            self._discovered_vlans = {v.vid: v for v in vlans}
            if connection.rest is not None:
                vlans = self._enrich_vlans_from_rest(connection, device, vlans)
            return vlans

        # REST-only mode
        return self._collect_vlans_rest(connection, device)

    def _collect_vlans_rest(
        self, connection: _ArubaConnection, device: NormalizedDevice
    ) -> list[NormalizedVLAN]:
        """Collect VLANs purely from REST API (fallback mode)."""
        raw_vlans = self._rest_get(connection, "/system/vlans")
        vlans: list[NormalizedVLAN] = []

        for vlan_id_str, vlan_ref in raw_vlans.items():
            vlan_data = self._rest_get(connection, f"/system/vlans/{vlan_id_str}")

            vid = int(vlan_data.get("id", vlan_id_str))
            name = vlan_data.get("name", f"VLAN{vid}")
            description = vlan_data.get("description", "")
            admin = vlan_data.get("admin_state", "up")
            status = "active" if admin == "up" else "reserved"

            vlan = NormalizedVLAN(
                vid=vid,
                name=name,
                site=device.site,
                description=description,
                status=status,
            )
            vlans.append(vlan)
            self._discovered_vlans[vid] = vlan

        return vlans

    def _enrich_vlans_from_rest(
        self,
        conn: _ArubaConnection,
        device: NormalizedDevice,
        vlans: list[NormalizedVLAN],
    ) -> list[NormalizedVLAN]:
        vlan_by_vid = {v.vid: v for v in vlans}

        try:
            raw_vlans = self._rest_get(conn, "/system/vlans")
        except Exception:
            return vlans

        for vid_str in raw_vlans:
            try:
                vlan_data = self._rest_get(conn, f"/system/vlans/{vid_str}")
            except Exception:
                continue

            vid = int(vlan_data.get("id", vid_str))
            description = vlan_data.get("description", "")
            admin = vlan_data.get("admin_state", "up")
            status = "active" if admin == "up" else "reserved"

            if vid in vlan_by_vid:
                vlan_by_vid[vid].description = description
                vlan_by_vid[vid].status = status
                rest_name = vlan_data.get("name", "")
                if rest_name:
                    vlan_by_vid[vid].name = rest_name
            else:
                vlan = NormalizedVLAN(
                    vid=vid,
                    name=vlan_data.get("name", f"VLAN{vid}"),
                    site=device.site,
                    description=description,
                    status=status,
                )
                vlan_by_vid[vid] = vlan
                self._discovered_vlans[vid] = vlan

        return list(vlan_by_vid.values())

    # ------------------------------------------------------------------
    # LLDP: NAPALM or REST
    # ------------------------------------------------------------------

    def _collect_lldp_neighbors(
        self, connection: _ArubaConnection, device: NormalizedDevice
    ) -> list[NormalizedLLDPNeighbor]:
        if connection.has_napalm:
            raw_lldp = napalm_get_lldp(connection.napalm)
            return build_lldp_from_napalm(raw_lldp, device)

        # REST-only mode
        return self._collect_lldp_rest(connection, device)

    def _collect_lldp_rest(
        self, connection: _ArubaConnection, device: NormalizedDevice
    ) -> list[NormalizedLLDPNeighbor]:
        """Collect LLDP neighbors via REST API (fallback mode)."""
        neighbors: list[NormalizedLLDPNeighbor] = []

        try:
            raw_interfaces = self._rest_get(connection, "/system/interfaces", params={"depth": 1})

            for iface_name in raw_interfaces:
                try:
                    lldp_data = self._rest_get(
                        connection,
                        f"/system/interfaces/{requests.utils.quote(iface_name, safe='')}"
                        f"/lldp_neighbors",
                    )

                    if not isinstance(lldp_data, dict):
                        continue

                    for neighbor_id, neighbor_data in lldp_data.items():
                        neighbor_info = neighbor_data.get("neighbor_info", {})
                        if not neighbor_info:
                            continue

                        chassis_mac = neighbor_info.get("chassis_id", "")
                        system_name = neighbor_info.get("system_name", "")
                        port_id = neighbor_info.get("port_id", "")
                        port_desc = neighbor_info.get("port_description", "")

                        neighbor_interface = port_desc if port_desc else port_id

                        if not all([chassis_mac, system_name, neighbor_interface]):
                            self.logger.debug(
                                f"Skipping incomplete LLDP entry on {iface_name}: {system_name}"
                            )
                            continue

                        chassis_mac_normalized = normalize_mac(chassis_mac)
                        if not chassis_mac_normalized:
                            chassis_mac_normalized = chassis_mac

                        mgmt_addrs = neighbor_info.get("management_addresses", [])
                        mgmt_ip = mgmt_addrs[0] if mgmt_addrs else ""
                        system_desc = neighbor_info.get("system_description", "")

                        neighbors.append(
                            NormalizedLLDPNeighbor(
                                local_interface=iface_name,
                                neighbor_device_name=system_name,
                                neighbor_interface=neighbor_interface,
                                neighbor_chassis_mac=chassis_mac_normalized,
                                neighbor_mgmt_ip=mgmt_ip,
                                neighbor_system_description=system_desc,
                            )
                        )

                except Exception as e:
                    self.logger.debug(f"Failed to query LLDP for {iface_name}: {e}")
                    continue

        except Exception as e:
            self.logger.warning(f"Failed to collect LLDP neighbors: {e}")
            return []

        return neighbors

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_ip_addresses(
        self, iface_data: dict, iface_name: str, device_name: str
    ) -> list[NormalizedIPAddress]:
        ips = []

        role = None
        iface_type = iface_data.get("type", "")
        if iface_type == "loopback" or iface_name.lower().startswith("loopback"):
            role = IPAddressRole.LOOPBACK

        ip4 = iface_data.get("ip4_address")
        if ip4:
            ips.append(
                NormalizedIPAddress(
                    address=ip4,
                    interface_name=iface_name,
                    device_name=device_name,
                    role=role,
                    description=f"Discovered on {iface_name}",
                )
            )

        ip4_secondary = iface_data.get("ip4_address_secondary", {})
        if isinstance(ip4_secondary, dict):
            for addr in ip4_secondary:
                ips.append(
                    NormalizedIPAddress(
                        address=addr,
                        interface_name=iface_name,
                        device_name=device_name,
                        role=IPAddressRole.SECONDARY,
                        description=f"Secondary IP on {iface_name}",
                    )
                )

        ip6_addrs = iface_data.get("ip6_addresses", {})
        if isinstance(ip6_addrs, dict):
            for addr in ip6_addrs:
                ips.append(
                    NormalizedIPAddress(
                        address=addr,
                        interface_name=iface_name,
                        device_name=device_name,
                        role=role,
                        description=f"Discovered on {iface_name}",
                    )
                )

        return ips

    @staticmethod
    def _extract_vlan_id(uri_or_key: str) -> int | None:
        match = re.search(r"/vlans/(\d+)", uri_or_key)
        if match:
            return int(match.group(1))
        try:
            return int(uri_or_key)
        except (ValueError, TypeError):
            return None

    def _infer_device_role(self, platform: str) -> NormalizedDeviceRole:
        platform_lower = platform.lower()
        if any(kw in platform_lower for kw in ["6300", "6200", "6100", "2930"]):
            return NormalizedDeviceRole(name="Access Switch", slug="access-switch", color="4caf50")
        elif any(kw in platform_lower for kw in ["8360", "8325", "8400", "6400"]):
            return NormalizedDeviceRole(
                name="Distribution Switch", slug="distribution-switch", color="2196f3"
            )
        elif any(kw in platform_lower for kw in ["8100", "9300"]):
            return NormalizedDeviceRole(name="Core Switch", slug="core-switch", color="f44336")
        elif any(kw in platform_lower for kw in ["gateway", "7xxx", "9004"]):
            return NormalizedDeviceRole(name="Router", slug="router", color="ff9800")
        else:
            return NormalizedDeviceRole(name="Network Device", slug="network-device")
