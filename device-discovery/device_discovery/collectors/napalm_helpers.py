"""
NAPALM helper functions — shared utilities for NAPALM-backed collectors.

This module provides **plain functions** (not a base class) for:
- NAPALM connection management
- Raw data collection via NAPALM getters
- Translation of NAPALM dicts into COM (Common Object Model) objects
- Interface type inference and MAC normalization

Collectors compose these functions instead of inheriting from a shared base.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from device_discovery.collectors.base import CollectorConfig
from device_discovery.models.common import (
    DeviceStatus,
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
from device_discovery.models.version_parser import parse_version


# ---------------------------------------------------------------------------
# NAPALM-specific config
# ---------------------------------------------------------------------------


@dataclass
class NapalmConfig(CollectorConfig):
    """NAPALM collector configuration.

    The ``driver`` field specifies which NAPALM driver to use (e.g. ``eos``,
    ``junos``, ``ios``, ``nxos``, ``iosxr``).  Additional driver kwargs can
    be passed via ``optional_args``.
    """

    driver: str = ""
    enable_secret: str = ""
    optional_args: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DRIVER_VENDOR_HINTS: dict[str, str] = {
    "ios": "cisco_ios",
    "iosxr": "cisco_iosxr",
    "iosxr_netconf": "cisco_iosxr",
    "nxos": "cisco_nxos",
    "nxos_ssh": "cisco_nxos",
    "eos": "arista_eos",
    "junos": "juniper_junos",
    "aoscx": "aruba_aoscx",
}

VENDOR_MANUFACTURERS: dict[str, tuple[str, str]] = {
    "arista": ("Arista", "arista"),
    "cisco": ("Cisco", "cisco"),
    "juniper": ("Juniper", "juniper"),
    "aruba": ("Aruba", "aruba"),
    "hp": ("HP", "hp"),
    "huawei": ("Huawei", "huawei"),
}

IFACE_NAME_PATTERNS: list[tuple[re.Pattern[str], InterfaceType]] = [
    (
        re.compile(r"(?i)^(vlan|loopback|lo\d|null|tunnel|bvi)", re.IGNORECASE),
        InterfaceType.VIRTUAL,
    ),
    (re.compile(r"(?i)^(port-channel|ae|bond|lag)", re.IGNORECASE), InterfaceType.LAG),
]


# ---------------------------------------------------------------------------
# Pure utility functions
# ---------------------------------------------------------------------------


def speed_to_type(speed_mbps: float) -> InterfaceType:
    """Map interface speed in Mbps to a COM InterfaceType."""
    if speed_mbps <= 0:
        return InterfaceType.OTHER
    if speed_mbps <= 100:
        return InterfaceType.ONEHUNDREDBASE_TX
    if speed_mbps <= 1_000:
        return InterfaceType.ONETHOUSANDBASE_T
    if speed_mbps <= 10_000:
        return InterfaceType.TENGBASE_X_SFP_PLUS
    if speed_mbps <= 25_000:
        return InterfaceType.TWENTYFIVEGBASE_X_SFP28
    if speed_mbps <= 40_000:
        return InterfaceType.FORTYGBASE_X_QSFP_PLUS
    return InterfaceType.HUNDREDGBASE_X_QSFP28


def infer_interface_type(name: str, speed_mbps: float) -> InterfaceType:
    """Infer InterfaceType from the interface name, falling back to speed."""
    for pattern, itype in IFACE_NAME_PATTERNS:
        if pattern.match(name):
            return itype
    return speed_to_type(speed_mbps)


def normalize_mac(mac: str) -> str:
    """Normalize any MAC format to NetBox ``AA:BB:CC:DD:EE:FF``."""
    if not mac:
        return ""
    cleaned = mac.replace(".", "").replace(":", "").replace("-", "").strip()
    if len(cleaned) != 12:
        return mac
    return ":".join(cleaned[i : i + 2].upper() for i in range(0, 12, 2))


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", text.lower()).strip("-")


def manufacturer_from_vendor(vendor: str) -> NormalizedManufacturer:
    """Resolve a NAPALM vendor string to a NormalizedManufacturer."""
    vendor_lower = vendor.lower()
    for key, (name, slug) in VENDOR_MANUFACTURERS.items():
        if key in vendor_lower:
            return NormalizedManufacturer(name=name, slug=slug)
    return NormalizedManufacturer(name=vendor or "Unknown", slug=slugify(vendor or "unknown"))


# ---------------------------------------------------------------------------
# Connection functions
# ---------------------------------------------------------------------------


def napalm_connect(config: NapalmConfig, host: str) -> Any:
    """Open a NAPALM driver connection and return the device handle."""
    from napalm import get_network_driver

    driver_cls = get_network_driver(config.driver)

    optional_args = dict(config.optional_args)
    if config.enable_secret:
        optional_args.setdefault("secret", config.enable_secret)

    device = driver_cls(
        hostname=host,
        username=config.username,
        password=config.password,
        timeout=config.timeout,
        optional_args=optional_args,
    )
    device.open()
    return device


def napalm_disconnect(device: Any) -> None:
    """Close a NAPALM device connection."""
    device.close()


# ---------------------------------------------------------------------------
# Raw data collection functions (return NAPALM dicts)
# ---------------------------------------------------------------------------


def napalm_get_facts(device: Any) -> dict:
    """Get device facts via NAPALM."""
    return device.get_facts()


def napalm_get_interfaces(device: Any) -> tuple[dict, dict]:
    """Get interfaces and IPs. Returns (raw_ifaces, raw_ips)."""
    raw_ifaces = device.get_interfaces()
    try:
        raw_ips = device.get_interfaces_ip()
    except Exception:
        raw_ips = {}
    return raw_ifaces, raw_ips


def napalm_get_vlans(device: Any) -> dict:
    """Get VLANs via NAPALM. Returns empty dict on failure."""
    try:
        return device.get_vlans()
    except Exception:
        return {}


def napalm_get_lldp(device: Any) -> dict:
    """Get LLDP neighbor detail. Returns empty dict on failure."""
    try:
        return device.get_lldp_neighbors_detail()
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# COM builder functions (NAPALM dicts -> COM objects)
# ---------------------------------------------------------------------------


def build_device_from_napalm(
    facts: dict,
    host: str,
    site: NormalizedSite,
    vendor_hint: str,
    driver: str = "",
) -> NormalizedDevice:
    """Translate NAPALM get_facts() output into a NormalizedDevice."""
    hostname = facts.get("hostname") or host
    vendor = facts.get("vendor") or ""
    model = facts.get("model") or "Unknown"
    serial = facts.get("serial_number") or ""
    os_version = facts.get("os_version") or ""

    mfr = manufacturer_from_vendor(vendor)

    parsed = parse_version(os_version, vendor_hint=vendor_hint)

    platform = NormalizedPlatform(
        name=parsed.platform_name,
        slug=parsed.platform_slug,
        family=parsed.family,
        version_major=parsed.major,
        version_minor=parsed.minor,
        version_full=parsed.full,
        version_raw=os_version,
        manufacturer=mfr,
        description=f"Discovered from {hostname} ({model})",
    )

    device_type = NormalizedDeviceType(
        manufacturer=mfr,
        model=model,
        slug=slugify(model),
    )

    role = NormalizedDeviceRole(name="Network Device", slug="network-device")

    driver_label = f" ({driver})" if driver else ""

    return NormalizedDevice(
        name=hostname,
        device_type=device_type,
        role=role,
        site=site,
        serial=serial,
        status=DeviceStatus.ACTIVE,
        platform=platform,
        comments=f"{parsed.family} {parsed.full}. Discovered via NAPALM{driver_label}.",
    )


def build_interfaces_from_napalm(
    raw_ifaces: dict,
    raw_ips: dict,
    device: NormalizedDevice,
    current_host: str,
) -> list[NormalizedInterface]:
    """Translate NAPALM interface + IP dicts into NormalizedInterface list."""
    iface_map: dict[str, NormalizedInterface] = {}

    for name, data in raw_ifaces.items():
        speed_mbps = data.get("speed", 0) or 0
        mac = normalize_mac(data.get("mac_address", "") or "")

        iface_map[name] = NormalizedInterface(
            name=name,
            enabled=data.get("is_enabled", True),
            description=data.get("description", ""),
            mac_address=mac,
            speed=int(speed_mbps * 1000) if speed_mbps else None,
            mtu=data.get("mtu") or None,
            type=infer_interface_type(name, speed_mbps),
        )

    for iface_name, families in raw_ips.items():
        if iface_name not in iface_map:
            iface_map[iface_name] = NormalizedInterface(
                name=iface_name,
                type=infer_interface_type(iface_name, 0),
            )

        iface = iface_map[iface_name]

        for family in ("ipv4", "ipv6"):
            addrs = families.get(family, {})
            for addr, info in addrs.items():
                prefix_len = info.get("prefix_length", 32 if family == "ipv4" else 128)
                cidr = f"{addr}/{prefix_len}"

                role = None
                if iface_name.lower().startswith(("loopback", "lo")):
                    role = IPAddressRole.LOOPBACK

                ip_obj = NormalizedIPAddress(
                    address=cidr,
                    interface_name=iface_name,
                    device_name=device.name,
                    role=role,
                    description=f"Discovered on {iface_name}",
                )
                iface.ip_addresses.append(ip_obj)

                # Primary IP detection
                if addr == current_host and not device.primary_ip4:
                    device.primary_ip4 = cidr

    return list(iface_map.values())


def build_vlans_from_napalm(
    raw_vlans: dict,
    site: NormalizedSite,
) -> list[NormalizedVLAN]:
    """Translate NAPALM get_vlans() output into NormalizedVLAN list."""
    vlans: list[NormalizedVLAN] = []
    for vid_str, data in raw_vlans.items():
        try:
            vid = int(vid_str)
        except (ValueError, TypeError):
            continue

        vlan = NormalizedVLAN(
            vid=vid,
            name=data.get("name", f"VLAN{vid}"),
            site=site,
            status="active",
        )
        vlans.append(vlan)

    return vlans


def build_lldp_from_napalm(
    raw_lldp: dict,
    device: NormalizedDevice,
) -> list[NormalizedLLDPNeighbor]:
    """Translate NAPALM get_lldp_neighbors_detail() into NormalizedLLDPNeighbor list."""
    neighbors: list[NormalizedLLDPNeighbor] = []
    for local_iface, neighbor_list in raw_lldp.items():
        for entry in neighbor_list:
            chassis_mac = normalize_mac(entry.get("remote_chassis_id", ""))
            neighbor_name = entry.get("remote_system_name", "")
            neighbor_iface = entry.get("remote_port", "") or entry.get(
                "remote_port_description", ""
            )

            if not all([chassis_mac, neighbor_name, neighbor_iface]):
                continue

            neighbors.append(
                NormalizedLLDPNeighbor(
                    local_interface=local_iface,
                    neighbor_device_name=neighbor_name,
                    neighbor_interface=neighbor_iface,
                    neighbor_chassis_mac=chassis_mac,
                    neighbor_mgmt_ip=entry.get("remote_system_capab", ""),
                    neighbor_system_description=entry.get("remote_system_description", ""),
                )
            )

    return neighbors


# ---------------------------------------------------------------------------
# Backwards-compatible aliases (prefixed with underscore)
# ---------------------------------------------------------------------------

_speed_to_type = speed_to_type
_infer_interface_type = infer_interface_type
_normalize_mac = normalize_mac
_slugify = slugify
_manufacturer_from_vendor = manufacturer_from_vendor
_DRIVER_VENDOR_HINTS = DRIVER_VENDOR_HINTS
_VENDOR_MANUFACTURERS = VENDOR_MANUFACTURERS
_IFACE_NAME_PATTERNS = IFACE_NAME_PATTERNS
