"""Normalization helpers for LLDP cable resolution."""

from __future__ import annotations

from functools import lru_cache

DEFAULT_INTERFACE_MAPPINGS: dict[str, dict[str, str]] = {
    "cisco": {
        "Fa": "FastEthernet",
        "Gi": "GigabitEthernet",
        "Te": "TenGigabitEthernet",
        "Eth": "Ethernet",
        "Et": "Ethernet",
        "Po": "Port-channel",
    },
    "aruba": {},
}


def normalize_hostname(hostname: str) -> str:
    """
    Normalize a hostname for cable endpoint matching.

    Args:
        hostname: Raw hostname from LLDP or inventory.

    Returns:
        Lowercase short hostname with any domain suffix removed.

    Raises:
        This function does not raise errors for invalid input.

    """
    normalized = (hostname or "").strip().lower()
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]
    return normalized


def normalize_chassis_mac(mac: str) -> str:
    """
    Normalize a chassis MAC for stable comparisons.

    Args:
        mac: Raw chassis MAC string in any common notation.

    Returns:
        Lowercase hexadecimal string with separators removed.

    Raises:
        This function does not raise errors for invalid input.

    """
    return (
        (mac or "").strip().lower().replace(":", "").replace("-", "").replace(".", "")
    )


def _freeze_mappings(
    mappings: dict[str, dict[str, str]],
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    return tuple(
        (vendor.lower(), tuple(sorted(vendor_mappings.items())))
        for vendor, vendor_mappings in sorted(mappings.items())
    )


def _canonical_prefixes(vendor_rules: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(canonical for _, canonical in vendor_rules)


@lru_cache(maxsize=512)
def _normalize_interface_name_cached(
    interface: str,
    vendor: str,
    frozen_mappings: tuple[tuple[str, tuple[tuple[str, str], ...]], ...],
) -> tuple[str | None, bool]:
    vendor_rules = dict(frozen_mappings).get(vendor, ())
    if not interface:
        return None, False

    normalized = interface.strip()
    if not vendor_rules and vendor == "aruba":
        return normalized, True
    if not vendor_rules:
        return None, False

    if any(
        normalized.startswith(prefix) for prefix in _canonical_prefixes(vendor_rules)
    ):
        return normalized, True

    sorted_rules = sorted(vendor_rules, key=lambda item: len(item[0]), reverse=True)
    for abbreviation, canonical in sorted_rules:
        if normalized.startswith(abbreviation):
            return f"{canonical}{normalized[len(abbreviation):]}", False

    return None, False


def normalize_interface_name(
    interface: str,
    vendor: str,
    mappings: dict[str, dict[str, str]] | None = None,
) -> tuple[str | None, bool]:
    """
    Normalize an interface name to a vendor-canonical form.

    Args:
        interface: Raw interface name, for example "Gi0/1".
        vendor: Vendor key such as "cisco" or "aruba".
        mappings: Optional vendor mapping override. When omitted, defaults
            to ``DEFAULT_INTERFACE_MAPPINGS``.

    Returns:
        A tuple of ``(normalized_name, is_canonical)`` where:
        - ``normalized_name`` is the canonical name, or ``None`` if unknown.
        - ``is_canonical`` is ``True`` when the input was already canonical.

    Raises:
        This function does not raise errors for invalid input.

    Example:
        >>> normalize_interface_name("Gi0/1", "cisco")
        ('GigabitEthernet0/1', False)

    """
    effective_mappings = mappings or DEFAULT_INTERFACE_MAPPINGS
    frozen_mappings = _freeze_mappings(effective_mappings)
    return _normalize_interface_name_cached(
        interface, (vendor or "").strip().lower(), frozen_mappings
    )


normalize_interface_name.cache_info = _normalize_interface_name_cached.cache_info  # type: ignore[attr-defined]
normalize_interface_name.cache_clear = _normalize_interface_name_cached.cache_clear  # type: ignore[attr-defined]
