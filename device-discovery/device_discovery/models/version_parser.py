"""
Network OS Version Parser.

Parses vendor-specific software version strings into a structured
version tree. Each vendor has its own versioning scheme:

Cisco IOS:    "15.2(4)E10"        → IOS / 15 / 15.2 / 15.2(4)E10
Cisco IOS-XE: "17.09.04a"        → IOS-XE / 17 / 17.09 / 17.09.04a
Cisco NX-OS:  "10.3(4a)"         → NX-OS / 10 / 10.3 / 10.3(4a)
Aruba AOS-CX: "10.13.1010"       → AOS-CX / 10 / 10.13 / 10.13.1010
Juniper Junos: "23.4R1.10"       → Junos / 23 / 23.4 / 23.4R1.10

The version tree is stored in NormalizedPlatform as:
  family   = "Cisco IOS"         (the OS family)
  major    = "15"                 (major release train)
  minor    = "15.2"              (minor release train)
  full     = "15.2(4)E10"       (exact build)

This enables filtering in NetBox at any level of the hierarchy:
  "Show me all IOS 15 devices"
  "Show me all IOS 15.2 devices"
  "Which devices are on 15.2(4)E10 specifically?"
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedVersion:
    """Structured version information extracted from a raw version string."""

    family: str  # OS family: "Cisco IOS", "Cisco IOS-XE", "Aruba AOS-CX", etc.
    major: str  # Major version: "15", "17", "10"
    minor: str  # Minor version: "15.2", "17.09", "10.13"
    full: str  # Full version: "15.2(4)E10", "17.09.04a", "10.13.1010"
    raw: str  # Original unparsed string from the device

    @property
    def tree(self) -> list[str]:
        """Return the full hierarchy as a list, top to bottom."""
        return [
            self.family,
            f"{self.family} {self.major}",
            f"{self.family} {self.minor}",
            f"{self.family} {self.full}",
        ]

    @property
    def platform_name(self) -> str:
        """The most specific platform name for NetBox."""
        return f"{self.family} {self.full}"

    @property
    def platform_slug(self) -> str:
        """URL-safe slug for the most specific platform."""
        return _slugify(self.platform_name)


# ---------------------------------------------------------------------------
# Vendor-specific parsers
# ---------------------------------------------------------------------------


def parse_cisco_ios_version(raw: str) -> ParsedVersion:
    """
    Parse Cisco IOS version strings.

    Examples:
        "15.2(4)E10"           → family=Cisco IOS, major=15, minor=15.2, full=15.2(4)E10
        "15.0(2)SE11"          → family=Cisco IOS, major=15, minor=15.0, full=15.0(2)SE11
        "12.2(55)SE12"         → family=Cisco IOS, major=12, minor=12.2, full=12.2(55)SE12
        "15.2(7)E9"            → family=Cisco IOS, major=15, minor=15.2, full=15.2(7)E9

    IOS version format: MAJOR.MINOR(MAINTENANCE)TRAIN_BUILD
        - MAJOR: 12, 15
        - MINOR: 0-9
        - MAINTENANCE: number in parentheses
        - TRAIN: letter(s) indicating feature set (E=Enhanced, SE=SMI Enhanced, etc.)
        - BUILD: optional build number
    """
    raw = raw.strip()

    # Try to extract from a full "show version" line like:
    # "Cisco IOS Software, ... Version 15.2(4)E10, ..."
    version_match = re.search(r"Version\s+(\d+\.\d+\([^)]+\)[^,\s]*)", raw, re.IGNORECASE)
    if version_match:
        raw = version_match.group(1)

    # Parse the version components: MAJOR.MINOR(MAINT)TRAIN
    match = re.match(r"^(\d+)\.(\d+)(\([^)]*\)\S*)?$", raw)
    if match:
        major_num = match.group(1)
        minor_num = match.group(2)
        remainder = match.group(3) or ""
        return ParsedVersion(
            family="Cisco IOS",
            major=major_num,
            minor=f"{major_num}.{minor_num}",
            full=f"{major_num}.{minor_num}{remainder}",
            raw=raw,
        )

    # Fallback: couldn't parse, use raw as full
    # Try to at least get major.minor
    simple_match = re.match(r"^(\d+)\.(\d+)", raw)
    if simple_match:
        return ParsedVersion(
            family="Cisco IOS",
            major=simple_match.group(1),
            minor=f"{simple_match.group(1)}.{simple_match.group(2)}",
            full=raw,
            raw=raw,
        )

    return ParsedVersion(family="Cisco IOS", major=raw, minor=raw, full=raw, raw=raw)


def parse_cisco_iosxe_version(raw: str) -> ParsedVersion:
    """
    Parse Cisco IOS-XE version strings.

    Examples:
        "17.09.04a"            → family=Cisco IOS-XE, major=17, minor=17.09, full=17.09.04a
        "17.06.06"             → family=Cisco IOS-XE, major=17, minor=17.06, full=17.06.06
        "16.12.04"             → family=Cisco IOS-XE, major=16, minor=16.12, full=16.12.04
        "03.07.05E"            → family=Cisco IOS-XE, major=03, minor=03.07, full=03.07.05E

    IOS-XE version format: MAJOR.MINOR.MAINTENANCE[LETTER]
    """
    raw = raw.strip()

    # Extract from "show version" line if present
    version_match = re.search(r"Version\s+(\d+\.\d+\.\d+[^,\s]*)", raw, re.IGNORECASE)
    if version_match:
        raw = version_match.group(1)

    # Parse: MAJOR.MINOR.MAINT[a-z]
    match = re.match(r"^(\d+)\.(\d+)\.(\d+\S*)$", raw)
    if match:
        major_num = match.group(1)
        minor_num = match.group(2)
        maint = match.group(3)
        return ParsedVersion(
            family="Cisco IOS-XE",
            major=major_num,
            minor=f"{major_num}.{minor_num}",
            full=f"{major_num}.{minor_num}.{maint}",
            raw=raw,
        )

    return ParsedVersion(family="Cisco IOS-XE", major=raw, minor=raw, full=raw, raw=raw)


def parse_cisco_nxos_version(raw: str) -> ParsedVersion:
    """
    Parse Cisco NX-OS version strings.

    Examples:
        "10.3(4a)"             → family=Cisco NX-OS, major=10, minor=10.3, full=10.3(4a)
        "9.3(12)"              → family=Cisco NX-OS, major=9, minor=9.3, full=9.3(12)
        "7.0(3)I7(10)"         → family=Cisco NX-OS, major=7, minor=7.0, full=7.0(3)I7(10)
    """
    raw = raw.strip()

    version_match = re.search(r"version\s+(\d+\.\d+\([^)]+\)[^,\s]*)", raw, re.IGNORECASE)
    if version_match:
        raw = version_match.group(1)

    match = re.match(r"^(\d+)\.(\d+)(\([^)]*\)\S*)?$", raw)
    if match:
        major_num = match.group(1)
        minor_num = match.group(2)
        remainder = match.group(3) or ""
        return ParsedVersion(
            family="Cisco NX-OS",
            major=major_num,
            minor=f"{major_num}.{minor_num}",
            full=f"{major_num}.{minor_num}{remainder}",
            raw=raw,
        )

    return ParsedVersion(family="Cisco NX-OS", major=raw, minor=raw, full=raw, raw=raw)


def parse_aruba_aoscx_version(raw: str) -> ParsedVersion:
    """
    Parse Aruba AOS-CX version strings.

    Examples:
        "10.13.1010"           → family=Aruba AOS-CX, major=10, minor=10.13, full=10.13.1010
        "10.12.0001"           → family=Aruba AOS-CX, major=10, minor=10.12, full=10.12.0001
        "10.09.1040"           → family=Aruba AOS-CX, major=10, minor=10.09, full=10.09.1040
    """
    raw = raw.strip()

    match = re.match(r"^(\d+)\.(\d+)\.(\d+\S*)$", raw)
    if match:
        major_num = match.group(1)
        minor_num = match.group(2)
        patch = match.group(3)
        return ParsedVersion(
            family="Aruba AOS-CX",
            major=major_num,
            minor=f"{major_num}.{minor_num}",
            full=f"{major_num}.{minor_num}.{patch}",
            raw=raw,
        )

    return ParsedVersion(family="Aruba AOS-CX", major=raw, minor=raw, full=raw, raw=raw)


def parse_juniper_junos_version(raw: str) -> ParsedVersion:
    """
    Parse Juniper Junos version strings.

    Examples:
        "23.4R1.10"            → family=Juniper Junos, major=23, minor=23.4, full=23.4R1.10
        "22.2R3-S2.5"          → family=Juniper Junos, major=22, minor=22.2, full=22.2R3-S2.5
        "21.4R3-S5.4"          → family=Juniper Junos, major=21, minor=21.4, full=21.4R3-S5.4
    """
    raw = raw.strip()

    match = re.match(r"^(\d+)\.(\d+)(R\S*)?$", raw)
    if match:
        major_num = match.group(1)
        minor_num = match.group(2)
        remainder = match.group(3) or ""
        return ParsedVersion(
            family="Juniper Junos",
            major=major_num,
            minor=f"{major_num}.{minor_num}",
            full=f"{major_num}.{minor_num}{remainder}",
            raw=raw,
        )

    return ParsedVersion(family="Juniper Junos", major=raw, minor=raw, full=raw, raw=raw)


# ---------------------------------------------------------------------------
# Auto-detect parser based on raw version + optional hint
# ---------------------------------------------------------------------------

# Map of vendor hint → parser function
_VENDOR_PARSERS = {
    "cisco_ios": parse_cisco_ios_version,
    "cisco_iosxe": parse_cisco_iosxe_version,
    "cisco_ios-xe": parse_cisco_iosxe_version,
    "cisco_nxos": parse_cisco_nxos_version,
    "cisco_nx-os": parse_cisco_nxos_version,
    "aruba_aoscx": parse_aruba_aoscx_version,
    "aruba_aos-cx": parse_aruba_aoscx_version,
    "juniper_junos": parse_juniper_junos_version,
}


def parse_version(raw: str, vendor_hint: str = "") -> ParsedVersion:
    """
    Parse a version string, optionally using a vendor hint for disambiguation.

    Args:
        raw: The raw version string from the device (e.g., "15.2(4)E10")
        vendor_hint: Optional vendor identifier (e.g., "cisco_ios", "aruba_aoscx")

    Returns:
        ParsedVersion with the structured version tree.

    If no vendor_hint is given, attempts auto-detection based on patterns.
    """
    raw = raw.strip()
    if not raw:
        return ParsedVersion(family="Unknown", major="", minor="", full="", raw="")

    # Try vendor hint first
    hint_lower = vendor_hint.lower().replace(" ", "_")
    if hint_lower in _VENDOR_PARSERS:
        return _VENDOR_PARSERS[hint_lower](raw)

    # Auto-detect based on version string patterns
    # IOS classic: digits.digits(stuff)
    if re.match(r"^\d+\.\d+\(", raw):
        # Could be IOS or NX-OS. NX-OS typically has major >= 5 and no train letter.
        # IOS has train letters like E, SE, SPA after the parenthesized maintenance.
        if re.search(r"\)[A-Z]", raw):
            return parse_cisco_ios_version(raw)
        else:
            # Ambiguous — default to IOS, NX-OS users should pass vendor_hint
            return parse_cisco_ios_version(raw)

    # IOS-XE: digits.digits.digits
    if re.match(r"^\d+\.\d+\.\d+", raw):
        # Could be IOS-XE or AOS-CX. AOS-CX patch numbers are 4 digits.
        parts = raw.split(".")
        if len(parts) >= 3 and len(parts[2].rstrip("abcdefghijklmnopqrstuvwxyz")) >= 4:
            return parse_aruba_aoscx_version(raw)
        return parse_cisco_iosxe_version(raw)

    # Junos: digits.digitsR
    if re.match(r"^\d+\.\d+R", raw):
        return parse_juniper_junos_version(raw)

    # Unknown — return as-is
    return ParsedVersion(family="Unknown", major=raw, minor=raw, full=raw, raw=raw)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """Convert a version platform name to a NetBox-safe slug."""
    slug = text.lower()
    slug = slug.replace("(", "-").replace(")", "-").replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug)  # collapse multiple dashes
    return slug.strip("-")
