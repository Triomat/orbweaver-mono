"""
Common Object Model (COM) for network device discovery.

These dataclasses define the **contract** between vendor-specific collectors
and the vendor-agnostic NetBox importer. Every collector MUST produce instances
of these classes. The importer consumes ONLY these classes.

Design decisions:
- All fields use simple Python types (str, int, Optional) — no vendor objects.
- Fields map closely to NetBox's data model but are NOT NetBox API payloads.
  The importer handles the translation to pynetbox calls.
- Optional fields are truly optional — a collector should populate what it can.
- `unique_key` properties provide deterministic identifiers for idempotent upserts.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enums — constrained to values NetBox actually accepts
# ---------------------------------------------------------------------------


class DeviceStatus(str, Enum):
    ACTIVE = "active"
    PLANNED = "planned"
    STAGED = "staged"
    FAILED = "failed"
    DECOMMISSIONING = "decommissioning"
    OFFLINE = "offline"


class InterfaceType(str, Enum):
    """Subset of NetBox interface types most commonly discovered."""

    VIRTUAL = "virtual"
    LAG = "lag"
    ONEHUNDREDBASE_TX = "100base-tx"
    ONETHOUSANDBASE_T = "1000base-t"
    TENGBASE_X_SFP_PLUS = "10gbase-x-sfpp"
    TWENTYFIVEGBASE_X_SFP28 = "25gbase-x-sfp28"
    FORTYGBASE_X_QSFP_PLUS = "40gbase-x-qsfpp"
    HUNDREDGBASE_X_QSFP28 = "100gbase-x-qsfp28"
    OTHER = "other"


class InterfaceMode(str, Enum):
    ACCESS = "access"
    TAGGED = "tagged"
    TAGGED_ALL = "tagged-all"


class IPAddressRole(str, Enum):
    LOOPBACK = "loopback"
    SECONDARY = "secondary"
    ANYCAST = "anycast"
    VIP = "vip"
    VRRP = "vrrp"
    HSRP = "hsrp"
    GLBP = "glbp"


# ---------------------------------------------------------------------------
# Core COM dataclasses
# ---------------------------------------------------------------------------


@dataclass
class NormalizedSite:
    """Physical or logical site/location."""

    name: str
    slug: str | None = None
    description: str = ""
    physical_address: str = ""
    latitude: float | None = None
    longitude: float | None = None

    @property
    def unique_key(self) -> str:
        return self.slug or self.name.lower().replace(" ", "-")


@dataclass
class NormalizedManufacturer:
    """Device manufacturer (e.g., Aruba, Cisco, Juniper)."""

    name: str
    slug: str | None = None

    @property
    def unique_key(self) -> str:
        return self.slug or self.name.lower().replace(" ", "-")


@dataclass
class NormalizedDeviceType:
    """Hardware model / SKU."""

    manufacturer: NormalizedManufacturer
    model: str
    slug: str | None = None
    part_number: str = ""
    u_height: int = 1
    is_full_depth: bool = True

    @property
    def unique_key(self) -> str:
        return (
            f"{self.manufacturer.unique_key}__{self.slug or self.model.lower().replace(' ', '-')}"
        )


@dataclass
class NormalizedDeviceRole:
    """Functional role (e.g., access-switch, core-router, firewall)."""

    name: str
    slug: str | None = None
    color: str = "9e9e9e"  # NetBox default grey

    @property
    def unique_key(self) -> str:
        return self.slug or self.name.lower().replace(" ", "-")


@dataclass
class NormalizedPlatform:
    """
    Software platform with structured version tree.

    The version tree maps to a nested platform hierarchy in NetBox (4.4+):

        Cisco IOS                          ← root (family)
          └── Cisco IOS 15                 ← major version
                └── Cisco IOS 15.0         ← minor version
                      └── Cisco IOS 15.0(2)SE4  ← leaf (assigned to device)

    Devices are assigned the leaf platform. Filtering by any ancestor
    returns all descendants. Config contexts on parent platforms
    cascade to all children (NetBox 4.5+).
    """

    name: str  # e.g., "Cisco IOS 15.2(4)E10"
    slug: str = ""  # e.g., "cisco-ios-15-2-4-e10"
    family: str = ""  # e.g., "Cisco IOS"
    version_major: str = ""  # e.g., "15"
    version_minor: str = ""  # e.g., "15.2"
    version_full: str = ""  # e.g., "15.2(4)E10"
    version_raw: str = ""  # original string from device
    manufacturer: NormalizedManufacturer | None = None
    description: str = ""

    @property
    def unique_key(self) -> str:
        return self.slug or self.name.lower().replace(" ", "-")

    @property
    def version_tree(self) -> list[str]:
        """Full hierarchy from broadest to most specific."""
        return [
            self.family,
            f"{self.family} {self.version_major}",
            f"{self.family} {self.version_minor}",
            f"{self.family} {self.version_full}",
        ]


@dataclass
class NormalizedVLAN:
    """Layer 2 VLAN."""

    vid: int
    name: str
    site: NormalizedSite | None = None
    description: str = ""
    status: str = "active"

    @property
    def unique_key(self) -> str:
        site_key = self.site.unique_key if self.site else "global"
        return f"{site_key}__vlan-{self.vid}"


@dataclass
class NormalizedPrefix:
    """IP prefix / subnet."""

    prefix: str  # CIDR notation, e.g. "10.0.1.0/24"
    vlan: NormalizedVLAN | None = None
    site: NormalizedSite | None = None
    description: str = ""
    status: str = "active"

    @property
    def unique_key(self) -> str:
        return self.prefix


@dataclass
class NormalizedIPAddress:
    """IP address assigned to an interface."""

    address: str  # CIDR notation, e.g. "10.0.1.1/24"
    interface_name: str = ""  # resolved during import
    device_name: str = ""  # resolved during import
    role: IPAddressRole | None = None
    dns_name: str = ""
    description: str = ""
    status: str = "active"

    @property
    def unique_key(self) -> str:
        return self.address


@dataclass
class NormalizedInterface:
    """Physical or logical network interface."""

    name: str
    type: InterfaceType = InterfaceType.OTHER
    enabled: bool = True
    description: str = ""
    mac_address: str = ""
    mtu: int | None = None
    speed: int | None = None  # Kbps
    mode: InterfaceMode | None = None
    untagged_vlan: NormalizedVLAN | None = None
    tagged_vlans: list[NormalizedVLAN] = field(default_factory=list)
    ip_addresses: list[NormalizedIPAddress] = field(default_factory=list)
    lag: str | None = None  # parent LAG interface name, if member

    @property
    def unique_key(self) -> str:
        return self.name


@dataclass
class NormalizedLLDPNeighbor:
    """
    LLDP neighbor discovered on an interface.

    Represents a physical connection discovered via Link Layer Discovery Protocol.
    Used to build cable connections between devices in NetBox.
    """

    local_interface: str  # Interface on this device (e.g., "GigabitEthernet0/1")
    neighbor_device_name: str  # Hostname from LLDP (e.g., "switch2.example.com")
    neighbor_interface: str  # Remote interface name
    neighbor_chassis_mac: str  # Remote device chassis MAC (for matching)
    neighbor_mgmt_ip: str = ""  # Optional management IP
    neighbor_system_description: str = ""  # Optional system info

    @property
    def unique_key(self) -> str:
        """Unique fingerprint for this neighbor relationship."""
        # Combine local interface + chassis MAC + remote interface
        # This allows deduplication of bidirectional discoveries
        key_str = f"{self.local_interface}|{self.neighbor_chassis_mac}|{self.neighbor_interface}"
        return hashlib.md5(key_str.encode()).hexdigest()


@dataclass
class NormalizedCable:
    """
    Cable connection between two interfaces.

    Represents a physical cable that will be created in NetBox.
    Supports bidirectional deduplication (A→B and B→A create same cable).
    """

    device_a_name: str  # First endpoint device name
    interface_a_name: str  # First endpoint interface name
    device_b_name: str  # Second endpoint device name
    interface_b_name: str  # Second endpoint interface name
    label: str = ""  # Optional label (e.g., "LLDP auto-discovered")
    description: str = ""  # Optional description
    color: str = ""  # Optional NetBox color (hex)

    @property
    def unique_key(self) -> str:
        """
        Sorted endpoint fingerprint for bidirectional deduplication.

        Ensures that cable A→B and cable B→A produce the same key,
        so only one cable object is created regardless of discovery order.
        """
        # Create sorted tuple of endpoints
        endpoint_a = f"{self.device_a_name}:{self.interface_a_name}"
        endpoint_b = f"{self.device_b_name}:{self.interface_b_name}"
        endpoints = tuple(sorted([endpoint_a, endpoint_b]))

        # Hash the sorted endpoints
        key_str = f"{endpoints[0]}|{endpoints[1]}"
        return hashlib.md5(key_str.encode()).hexdigest()


@dataclass
class NormalizedDevice:
    """
    Top-level discovery result for a single network device.

    This is the primary object a collector produces. It contains all nested
    objects (interfaces, VLANs, IPs) discovered from that device.
    """

    name: str
    device_type: NormalizedDeviceType
    role: NormalizedDeviceRole
    site: NormalizedSite
    serial: str = ""
    status: DeviceStatus = DeviceStatus.ACTIVE
    platform: NormalizedPlatform | None = None  # structured platform with version tree
    primary_ip4: str = ""  # CIDR notation
    primary_ip6: str = ""
    rack: str = ""
    interfaces: list[NormalizedInterface] = field(default_factory=list)
    vlans: list[NormalizedVLAN] = field(default_factory=list)
    lldp_neighbors: list[NormalizedLLDPNeighbor] = field(default_factory=list)
    comments: str = ""
    custom_fields: dict = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def unique_key(self) -> str:
        """Serial is most reliable; fall back to name."""
        if self.serial:
            return self.serial
        return self.name.lower()


# ---------------------------------------------------------------------------
# Discovery result container
# ---------------------------------------------------------------------------


@dataclass
class DiscoveryResult:
    """
    Aggregated output of a single discovery run.

    A collector returns one of these. The importer consumes it.
    This allows batch processing and gives the importer full context
    (e.g., all VLANs across all devices for deduplication).
    """

    devices: list[NormalizedDevice] = field(default_factory=list)
    vlans: list[NormalizedVLAN] = field(default_factory=list)
    prefixes: list[NormalizedPrefix] = field(default_factory=list)
    cables: list[NormalizedCable] = field(default_factory=list)
    sites: list[NormalizedSite] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    vendor: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def device_count(self) -> int:
        return len(self.devices)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def merge(self, other: DiscoveryResult) -> DiscoveryResult:
        """Merge two discovery results (e.g., from parallel collectors)."""
        return DiscoveryResult(
            devices=self.devices + other.devices,
            vlans=self.vlans + other.vlans,
            prefixes=self.prefixes + other.prefixes,
            cables=self.cables + other.cables,
            sites=self.sites + other.sites,
            timestamp=max(self.timestamp, other.timestamp),
            vendor=f"{self.vendor},{other.vendor}" if self.vendor != other.vendor else self.vendor,
            errors=self.errors + other.errors,
        )

    def deduplicate(self) -> None:
        """Deduplicate VLANs and prefixes in-place by unique_key."""
        seen_vlans: dict[str, NormalizedVLAN] = {}
        for vlan in self.vlans:
            key = vlan.unique_key
            if key not in seen_vlans:
                seen_vlans[key] = vlan
        self.vlans = list(seen_vlans.values())

        seen_prefixes: dict[str, NormalizedPrefix] = {}
        for prefix in self.prefixes:
            key = prefix.unique_key
            if key not in seen_prefixes:
                seen_prefixes[key] = prefix
        self.prefixes = list(seen_prefixes.values())
