"""Cable resolution helpers and algorithm entry points."""

from __future__ import annotations

import hashlib
from typing import Any

from orbweaver.cables.models import (
    CableCandidate,
    CableResolutionSummary,
    CableSkipEntry,
    ResolutionConfidence,
)
from orbweaver.cables.normalize import (
    normalize_chassis_mac,
    normalize_hostname,
    normalize_interface_name,
)
from orbweaver.models.common import DiscoveryResult, NormalizedCable


def dedupe_key(dev_a: str, intf_a: str, dev_b: str, intf_b: str) -> str:
    """Build a deterministic, bidirectional cable key."""
    endpoint_a = f"{normalize_hostname(dev_a)}:{(intf_a or '').strip()}"
    endpoint_b = f"{normalize_hostname(dev_b)}:{(intf_b or '').strip()}"
    key_str = "|".join(sorted([endpoint_a, endpoint_b]))
    return hashlib.md5(key_str.encode()).hexdigest()


def _get_nested_attr(obj: Any, path: list[str]) -> Any:
    current = obj
    for key in path:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(key)
        else:
            current = getattr(current, key, None)
    return current


def _device_chassis_mac(device: Any) -> str:
    custom_fields = getattr(device, "custom_fields", {}) or {}
    raw = (
        custom_fields.get("chassis_mac")
        or custom_fields.get("base_mac")
        or custom_fields.get("mac_address")
        or ""
    )
    if not raw:
        interfaces = getattr(device, "interfaces", []) or []
        for interface in interfaces:
            maybe_mac = getattr(interface, "mac_address", "")
            if maybe_mac:
                raw = maybe_mac
                break
    return normalize_chassis_mac(raw)


def build_discovered_device_indexes(
    discovery_result: DiscoveryResult,
) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    """Build hostname and chassis-MAC indexes for discovered devices."""
    by_hostname: dict[str, Any] = {}
    by_mac: dict[str, list[Any]] = {}

    for device in discovery_result.devices:
        hostname = normalize_hostname(getattr(device, "name", ""))
        if hostname:
            by_hostname[hostname] = device

        chassis_mac = _device_chassis_mac(device)
        if chassis_mac:
            by_mac.setdefault(chassis_mac, []).append(device)

    return by_hostname, by_mac


def lookup_device_in_netbox(netbox_client: Any, hostname: str, mac: str) -> Any | None:
    """Lookup a device in NetBox by normalized hostname, then by MAC."""
    if netbox_client is None:
        return None

    normalized_hostname = normalize_hostname(hostname)
    normalized_mac = normalize_chassis_mac(mac)

    try:
        if normalized_hostname:
            by_name = list(netbox_client.dcim.devices.filter(name=normalized_hostname))
            if by_name:
                return by_name[0]
    except Exception:
        pass

    if not normalized_mac:
        return None

    for candidate in (
        normalized_mac,
        _colonize_mac(normalized_mac),
        _dot_mac(normalized_mac),
    ):
        try:
            interfaces = list(
                netbox_client.dcim.interfaces.filter(mac_address=candidate)
            )
            for interface in interfaces:
                device = getattr(interface, "device", None)
                if device is not None:
                    return device
        except Exception:
            continue

    return None


def _colonize_mac(raw_mac: str) -> str:
    if len(raw_mac) != 12:
        return raw_mac
    return ":".join(raw_mac[i : i + 2] for i in range(0, 12, 2))


def _dot_mac(raw_mac: str) -> str:
    if len(raw_mac) != 12:
        return raw_mac
    return ".".join(raw_mac[i : i + 4] for i in range(0, 12, 4))


def match_interface_on_device(
    device: Any, interface: str, normalization_rules: dict | None
) -> str | None:
    """Match an interface name on a device using exact and normalized comparisons."""
    interfaces = getattr(device, "interfaces", []) or []
    interface_names = [getattr(i, "name", str(i)) for i in interfaces]
    if not interface_names:
        return None

    raw = (interface or "").strip()
    if raw in interface_names:
        return raw

    rules = normalization_rules or {}
    vendor = (rules.get("vendor") or "").strip().lower()
    mappings = rules.get("mappings") or rules

    normalized_candidate, _ = normalize_interface_name(raw, vendor, mappings)
    if normalized_candidate and normalized_candidate in interface_names:
        return normalized_candidate

    normalized_index: dict[str, str] = {}
    for existing in interface_names:
        normalized_existing, _ = normalize_interface_name(existing, vendor, mappings)
        if normalized_existing:
            normalized_index[normalized_existing] = existing

    if normalized_candidate and normalized_candidate in normalized_index:
        return normalized_index[normalized_candidate]

    return None


def is_self_loop(device_name: str, neighbor_name: str) -> bool:
    """True when a device advertises itself as an LLDP neighbor."""
    return normalize_hostname(device_name) == normalize_hostname(neighbor_name)


def is_bidirectional_match(
    dev_a: str, dev_b: str, discovery_result: DiscoveryResult
) -> bool:
    """Check if both devices mutually advertise each other via LLDP."""
    a_key = normalize_hostname(dev_a)
    b_key = normalize_hostname(dev_b)

    by_name, _ = build_discovered_device_indexes(discovery_result)
    device_a = by_name.get(a_key)
    device_b = by_name.get(b_key)
    if device_a is None or device_b is None:
        return False

    a_sees_b = any(
        normalize_hostname(n.neighbor_device_name) == b_key
        for n in device_a.lldp_neighbors
    )
    b_sees_a = any(
        normalize_hostname(n.neighbor_device_name) == a_key
        for n in device_b.lldp_neighbors
    )
    return a_sees_b and b_sees_a


def determine_lldp_direction(
    dev_a: str, dev_b: str, discovery_result: DiscoveryResult
) -> str:
    """Return LLDP visibility direction between two devices."""
    a_key = normalize_hostname(dev_a)
    b_key = normalize_hostname(dev_b)

    by_name, _ = build_discovered_device_indexes(discovery_result)
    device_a = by_name.get(a_key)
    device_b = by_name.get(b_key)

    a_sees_b = bool(device_a) and any(
        normalize_hostname(n.neighbor_device_name) == b_key
        for n in device_a.lldp_neighbors
    )
    b_sees_a = bool(device_b) and any(
        normalize_hostname(n.neighbor_device_name) == a_key
        for n in device_b.lldp_neighbors
    )

    if a_sees_b and b_sees_a:
        return "bidirectional"
    if a_sees_b:
        return "a_to_b"
    if b_sees_a:
        return "b_to_a"
    return "unknown"


def is_ambiguous_mac(
    device_name: str,
    discovery_result: DiscoveryResult,
    netbox_client: Any | None = None,
) -> bool:
    """Detect whether a discovered device MAC maps to multiple endpoints."""
    device_key = normalize_hostname(device_name)
    by_name, by_mac = build_discovered_device_indexes(discovery_result)
    device = by_name.get(device_key)
    if device is None:
        return False

    chassis_mac = _device_chassis_mac(device)
    if not chassis_mac:
        return False

    discovered_count = len(by_mac.get(chassis_mac, []))
    if discovered_count > 1:
        return True

    if netbox_client is None:
        return False

    seen_names: set[str] = set()
    for candidate in (chassis_mac, _colonize_mac(chassis_mac), _dot_mac(chassis_mac)):
        try:
            interfaces = list(
                netbox_client.dcim.interfaces.filter(mac_address=candidate)
            )
        except Exception:
            continue
        for interface in interfaces:
            name = normalize_hostname(
                _get_nested_attr(interface, ["device", "name"]) or ""
            )
            if name:
                seen_names.add(name)
        if len(seen_names) > 1:
            return True

    return False


def cable_exists_in_netbox(netbox_client: Any, cable: NormalizedCable) -> bool:
    """Return True when NetBox already has a cable for the same endpoints."""
    if netbox_client is None:
        return False

    expected = {
        (normalize_hostname(cable.device_a_name), cable.interface_a_name),
        (normalize_hostname(cable.device_b_name), cable.interface_b_name),
    }

    try:
        cables = list(netbox_client.dcim.cables.all())
    except Exception:
        return False

    for existing in cables:
        a_device = _get_nested_attr(
            existing, ["termination_a", "device", "name"]
        ) or _get_nested_attr(existing, ["termination_a_device", "name"])
        a_iface = _get_nested_attr(
            existing, ["termination_a", "name"]
        ) or _get_nested_attr(existing, ["termination_a_interface", "name"])
        b_device = _get_nested_attr(
            existing, ["termination_b", "device", "name"]
        ) or _get_nested_attr(existing, ["termination_b_device", "name"])
        b_iface = _get_nested_attr(
            existing, ["termination_b", "name"]
        ) or _get_nested_attr(existing, ["termination_b_interface", "name"])

        current = {
            (normalize_hostname(a_device or ""), (a_iface or "").strip()),
            (normalize_hostname(b_device or ""), (b_iface or "").strip()),
        }
        if expected == current:
            return True

    return False


def resolve_cables(  # noqa: C901
    discovery_result: DiscoveryResult,
    netbox_client: Any,
    normalization_rules: dict | None,
) -> tuple[list[CableCandidate], CableResolutionSummary]:
    """
    Resolve LLDP neighbors into deduplicated cable candidates.

    Args:
            discovery_result: COM discovery result with devices and LLDP neighbors.
            netbox_client: Pynetbox client instance, or None.
            normalization_rules: Vendor normalization hints passed to interface matching.

    Returns:
            Tuple of ``(candidates, summary)`` where:
            - ``candidates`` are writable cable candidates with confidence metadata.
            - ``summary`` contains counters and detailed skip reasons.

    Raises:
            This function does not raise for match/lookup failures; those are tracked
            in summary skip entries.

    Example:
            >>> candidates, summary = resolve_cables(result, netbox_client, {"vendor": "cisco"})

    """
    summary = CableResolutionSummary()
    candidates: list[CableCandidate] = []
    seen_keys: set[str] = set()

    by_name, by_mac = build_discovered_device_indexes(discovery_result)

    for device_a in discovery_result.devices:
        device_a_name = normalize_hostname(device_a.name)

        for neighbor in device_a.lldp_neighbors:
            summary.discovered += 1
            neighbor_name = normalize_hostname(neighbor.neighbor_device_name)
            neighbor_mac = normalize_chassis_mac(neighbor.neighbor_chassis_mac)

            if is_self_loop(device_a_name, neighbor_name):
                summary.unresolvable += 1
                summary.skip_entries.append(
                    CableSkipEntry(
                        local_device=device_a.name,
                        local_interface=neighbor.local_interface,
                        neighbor_hostname=neighbor.neighbor_device_name,
                        neighbor_interface=neighbor.neighbor_interface,
                        neighbor_chassis_mac=neighbor.neighbor_chassis_mac,
                        reason="self_loop_detected",
                    )
                )
                continue

            device_b = by_name.get(neighbor_name)
            device_b_discovered = device_b is not None

            if device_b is None and neighbor_mac:
                mac_matches = by_mac.get(neighbor_mac, [])
                if len(mac_matches) > 1:
                    summary.unresolvable += 1
                    summary.skip_entries.append(
                        CableSkipEntry(
                            local_device=device_a.name,
                            local_interface=neighbor.local_interface,
                            neighbor_hostname=neighbor.neighbor_device_name,
                            neighbor_interface=neighbor.neighbor_interface,
                            neighbor_chassis_mac=neighbor.neighbor_chassis_mac,
                            reason="ambiguous_chassis_mac",
                        )
                    )
                    continue
                if mac_matches:
                    device_b = mac_matches[0]
                    device_b_discovered = True

            if device_b is None:
                device_b = lookup_device_in_netbox(
                    netbox_client, neighbor_name, neighbor_mac
                )
                device_b_discovered = False

            if device_b is None:
                summary.unresolvable += 1
                summary.skip_entries.append(
                    CableSkipEntry(
                        local_device=device_a.name,
                        local_interface=neighbor.local_interface,
                        neighbor_hostname=neighbor.neighbor_device_name,
                        neighbor_interface=neighbor.neighbor_interface,
                        neighbor_chassis_mac=neighbor.neighbor_chassis_mac,
                        reason="neighbor_device_not_found",
                    )
                )
                continue

            local_interface = match_interface_on_device(
                device_a, neighbor.local_interface, normalization_rules
            )
            if local_interface is None:
                local_interface = (neighbor.local_interface or "").strip()

            remote_interface = match_interface_on_device(
                device_b, neighbor.neighbor_interface, normalization_rules
            )
            if remote_interface is None:
                summary.unresolvable += 1
                summary.skip_entries.append(
                    CableSkipEntry(
                        local_device=device_a.name,
                        local_interface=neighbor.local_interface,
                        neighbor_hostname=neighbor.neighbor_device_name,
                        neighbor_interface=neighbor.neighbor_interface,
                        neighbor_chassis_mac=neighbor.neighbor_chassis_mac,
                        reason="interface_name_mismatch",
                    )
                )
                continue

            device_b_name = normalize_hostname(getattr(device_b, "name", neighbor_name))
            key = dedupe_key(
                device_a_name, local_interface, device_b_name, remote_interface
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)

            cable = NormalizedCable(
                device_a_name=device_a_name,
                interface_a_name=local_interface,
                device_b_name=device_b_name,
                interface_b_name=remote_interface,
                label="LLDP auto-discovered",
            )

            confidence = ResolutionConfidence.PARTIAL
            if device_b_discovered and is_bidirectional_match(
                device_a_name, device_b_name, discovery_result
            ):
                confidence = ResolutionConfidence.CONFIRMED

            candidate = CableCandidate(
                cable=cable,
                confidence=confidence,
                device_a_discovered=True,
                device_b_discovered=device_b_discovered,
                lldp_neighbor=neighbor,
                resolution_notes=f"Resolved {device_a_name}:{local_interface} -> {device_b_name}:{remote_interface}",
                lldp_direction=determine_lldp_direction(
                    device_a_name, device_b_name, discovery_result
                ),
            )

            if netbox_client is not None and cable_exists_in_netbox(
                netbox_client, cable
            ):
                summary.unresolvable += 1
                summary.skip_entries.append(
                    CableSkipEntry(
                        local_device=device_a.name,
                        local_interface=neighbor.local_interface,
                        neighbor_hostname=neighbor.neighbor_device_name,
                        neighbor_interface=neighbor.neighbor_interface,
                        neighbor_chassis_mac=neighbor.neighbor_chassis_mac,
                        reason="already_exists",
                    )
                )
                continue

            candidates.append(candidate)

    summary.candidates = len(candidates)
    summary.created = len([c for c in candidates if c.is_writable])
    return candidates, summary


__all__ = [
    "build_discovered_device_indexes",
    "cable_exists_in_netbox",
    "dedupe_key",
    "determine_lldp_direction",
    "is_ambiguous_mac",
    "is_bidirectional_match",
    "is_self_loop",
    "lookup_device_in_netbox",
    "match_interface_on_device",
    "resolve_cables",
]
