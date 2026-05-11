# Contract: Cable Resolution Algorithm

**Module**: `orbweaver/cables/resolve.py`  
**Inputs**: `DiscoveryResult`, optional NetBox client  
**Outputs**: `list[CableCandidate]`, `CableResolutionSummary`

---

## Overview

The cable resolution algorithm takes LLDP neighbor advertisements from a discovery run and produces cable candidates with confidence tiers. The algorithm:

1. Normalizes all device identifiers (hostnames, chassis MACs, interface names)
2. Resolves neighbors against both newly discovered devices and existing NetBox inventory
3. Deduplicates bidirectionally (A→B and B→A produce one cable)
4. Checks for existing cables in NetBox (idempotent skip)
5. Applies validation rules (self-loops, ambiguous MACs, one-sided neighbors)
6. Assigns confidence tiers based on discovery scope
7. Generates skip reasons for unresolvable candidates

---

## Algorithm Pseudocode

```
Input:
  discovery_result: DiscoveryResult        (contains discovered devices + LLDP neighbors)
  netbox_client: optional pynetbox.api     (for looking up existing cables + devices)
  normalization_rules: dict                (vendor-specific interface name mappings)
  ignore_feature_flag: bool = False        (if True, always resolve; else check config)

Output:
  cable_candidates: list[CableCandidate]
  summary: CableResolutionSummary

Algorithm:
  
  # Phase 1: Normalize device identifiers
  discovered_devices = {}
  for device in discovery_result.devices:
    normalized_name = normalize_hostname(device.name)      # lowercase, strip domain
    discovered_devices[normalized_name] = device
    discovered_devices[device.chassis_mac] = device        # Also index by MAC
  
  # Phase 2: Build a map of neighbor cables (to detect bidirectional pairs)
  neighbor_map = {}                        # keyed by sorted device pair
  cable_candidates = []
  cables_seen_from_lldp = {}               # to deduplicate bidirectional discoveries
  
  for device in discovery_result.devices:
    device_a_name = normalize_hostname(device.name)
    
    for lldp_neighbor in device.lldp_neighbors:
      summary.discovered += 1
      
      # Phase 3a: Self-loop detection
      if normalize_hostname(lldp_neighbor.neighbor_device_name) == device_a_name:
        skip_entry = CableSkipEntry(
          local_device=device.name,
          local_interface=lldp_neighbor.local_interface,
          neighbor_hostname=lldp_neighbor.neighbor_device_name,
          reason="self_loop_detected"
        )
        summary.skip_entries.append(skip_entry)
        summary.unresolvable += 1
        continue
      
      # Phase 3b: Normalize neighbor identifiers
      neighbor_hostname_normalized = normalize_hostname(lldp_neighbor.neighbor_device_name)
      neighbor_mac = normalize_chassis_mac(lldp_neighbor.neighbor_chassis_mac)
      neighbor_interface_normalized = normalize_interface_name(
        lldp_neighbor.neighbor_interface,
        normalization_rules
      )
      
      # Phase 3c: Device matching (hostname → device, then MAC → device)
      device_b = None
      device_b_discovered = False  # Assume existing NetBox; will flip if found in discovered
      
      # Try to match against newly discovered devices first (preferred for Confirmed tier)
      if neighbor_hostname_normalized in discovered_devices:
        device_b = discovered_devices[neighbor_hostname_normalized]
        device_b_discovered = True
      
      # Fallback: Try MAC match against discovered devices
      if device_b is None and neighbor_mac in discovered_devices:
        device_b = discovered_devices[neighbor_mac]
        device_b_discovered = True
      
      # Last resort: Query NetBox for existing device (by hostname or MAC)
      if device_b is None and netbox_client:
        try:
          device_b = lookup_device_in_netbox(
            netbox_client,
            hostname=neighbor_hostname_normalized,
            mac=neighbor_mac
          )
          device_b_discovered = False  # Existing device, not discovered
        except:
          device_b = None
      
      device_b_name = normalize_hostname(device_b.name) if device_b else None
      
      # Phase 3d: Resolve interface name
      interface_b_name = None
      interface_a_name = normalize_interface_name(
        lldp_neighbor.local_interface,
        normalization_rules
      )
      
      if device_b:
        # Try to find matching interface on device_b
        interface_b_name = match_interface_on_device(
          device_b,
          neighbor_interface_normalized,
          normalization_rules
        )
      
      # Phase 4: Validation and confidence tier assignment
      
      # If neighbor device not found → unresolvable
      if device_b is None or device_b_name is None:
        skip_entry = CableSkipEntry(
          local_device=device.name,
          local_interface=lldp_neighbor.local_interface,
          neighbor_hostname=lldp_neighbor.neighbor_device_name,
          neighbor_interface=lldp_neighbor.neighbor_interface,
          neighbor_chassis_mac=lldp_neighbor.neighbor_chassis_mac,
          reason="neighbor_device_not_found"
        )
        summary.skip_entries.append(skip_entry)
        summary.unresolvable += 1
        continue
      
      # If interface on device_b not found → unresolvable
      if interface_b_name is None:
        skip_entry = CableSkipEntry(
          local_device=device.name,
          local_interface=lldp_neighbor.local_interface,
          neighbor_hostname=lldp_neighbor.neighbor_device_name,
          neighbor_interface=lldp_neighbor.neighbor_interface,
          neighbor_chassis_mac=lldp_neighbor.neighbor_chassis_mac,
          reason="interface_name_mismatch"
        )
        summary.skip_entries.append(skip_entry)
        summary.unresolvable += 1
        continue
      
      # Phase 5: Deduplicate bidirectionally
      cable_key = dedupe_key(device_a_name, interface_a_name, device_b_name, interface_b_name)
      
      if cable_key in cables_seen_from_lldp:
        # Already seen from the other direction; skip this one (count as candidate but not new)
        continue
      
      cables_seen_from_lldp[cable_key] = True
      summary.candidates += 1
      
      # Phase 6: Create cable candidate
      cable = NormalizedCable(
        device_a_name=device_a_name,
        interface_a_name=interface_a_name,
        device_b_name=device_b_name,
        interface_b_name=interface_b_name,
        label="LLDP auto-discovered",
        description=""
      )
      
      # Determine LLDP direction (for UI context)
      lldp_direction = determine_lldp_direction(
        device_a_name, device_b_name,
        discovery_result.devices
      )
      
      # Assign confidence tier
      confidence = ResolutionConfidence.CONFIRMED if (
        device_a_discovered and device_b_discovered and
        is_bidirectional_match(device_a_name, device_b_name, discovery_result)
      ) else ResolutionConfidence.PARTIAL
      
      candidate = CableCandidate(
        cable=cable,
        confidence=confidence,
        device_a_discovered=True,  # device_a is always from this discovery
        device_b_discovered=device_b_discovered,
        skip_reason=None,
        lldp_neighbor=lldp_neighbor,
        resolution_notes=f"Hostname match: {neighbor_hostname_normalized}; "
                        f"interfaces: {interface_a_name} ↔ {interface_b_name}",
        lldp_direction=lldp_direction
      )
      
      cable_candidates.append(candidate)
  
  # Phase 7: Check for ambiguous chassis MAC matches
  for candidate in cable_candidates:
    if is_ambiguous_mac(candidate.cable.device_b_name, discovery_result, netbox_client):
      candidate.confidence = ResolutionConfidence.UNRESOLVABLE
      candidate.skip_reason = "ambiguous_chassis_mac"
      skip_entry = CableSkipEntry(
        local_device=candidate.cable.device_a_name,
        local_interface=candidate.cable.interface_a_name,
        neighbor_hostname=candidate.cable.device_b_name,
        reason="ambiguous_chassis_mac"
      )
      summary.skip_entries.append(skip_entry)
      summary.unresolvable += 1
      summary.candidates -= 1
  
  # Phase 8: Detect one-sided neighbors
  for candidate in cable_candidates:
    if not is_bidirectional_match(candidate.cable.device_a_name, candidate.cable.device_b_name,
                                   discovery_result):
      if candidate.confidence != ResolutionConfidence.UNRESOLVABLE:
        candidate.confidence = ResolutionConfidence.PARTIAL
        candidate.lldp_direction = "one-sided"
  
  # Phase 9: Check NetBox for existing cables
  writable_candidates = [c for c in cable_candidates if c.confidence != ResolutionConfidence.UNRESOLVABLE]
  for candidate in writable_candidates:
    if netbox_client and cable_exists_in_netbox(netbox_client, candidate.cable):
      candidate.confidence = ResolutionConfidence.UNRESOLVABLE
      candidate.skip_reason = "already_exists"
      skip_entry = CableSkipEntry(
        local_device=candidate.cable.device_a_name,
        local_interface=candidate.cable.interface_a_name,
        neighbor_hostname=candidate.cable.device_b_name,
        reason="already_exists"
      )
      summary.skip_entries.append(skip_entry)
      summary.unresolvable += 1
  
  # Phase 10: Finalize summary
  summary.created = sum(1 for c in cable_candidates if c.is_writable)
  
  return cable_candidates, summary
```

---

## Helper Functions

### normalize_hostname(hostname: str) → str

Strip domain suffix and lowercase.

```python
def normalize_hostname(hostname: str) -> str:
    """
    Normalize hostname for matching.
    
    - Strip domain suffix (e.g., "switch1.example.com" → "switch1")
    - Lowercase
    - Trim whitespace
    
    Args:
        hostname: LLDP-advertised hostname or NetBox device name
    
    Returns:
        Normalized hostname (lowercase, no domain)
    """
    if not hostname:
        return ""
    
    # Lowercase
    normalized = hostname.lower().strip()
    
    # Strip domain suffix (first dot onward)
    if "." in normalized:
        normalized = normalized.split(".")[0]
    
    return normalized
```

### normalize_chassis_mac(mac: str) → str

Normalize MAC address for comparison.

```python
def normalize_chassis_mac(mac: str) -> str:
    """
    Normalize chassis MAC for matching.
    
    - Lowercase
    - Remove separators (colons, hyphens)
    - Return canonical form
    
    Args:
        mac: Chassis MAC from LLDP (e.g., "aa:bb:cc:dd:ee:ff")
    
    Returns:
        Normalized MAC (lowercase, no separators)
    """
    if not mac:
        return ""
    
    mac_normalized = mac.lower().replace(":", "").replace("-", "")
    return mac_normalized
```

### normalize_interface_name(interface: str, rules: dict) → str | None

Vendor-specific interface name normalization.

```python
def normalize_interface_name(interface: str, rules: dict) -> str | None:
    """
    Normalize interface name using vendor-specific canonical mappings.
    
    Attempts to expand abbreviated names (e.g., Cisco "Gi0/1" → "GigabitEthernet0/1").
    Returns None if no canonical form is found.
    
    Args:
        interface: Interface name from LLDP or NetBox (e.g., "Gi0/1")
        rules: dict mapping vendor to abbreviation→canonical dict
               E.g., {
                   "cisco": {"Gi": "GigabitEthernet", "Fa": "FastEthernet"},
                   "aruba": {}  # Aruba uses canonical names
               }
    
    Returns:
        Canonical interface name (e.g., "GigabitEthernet0/1"), or
        None if expansion failed
    """
    if not interface:
        return None
    
    # Try exact match first (already canonical)
    if interface in _canonical_cache:
        return _canonical_cache[interface]
    
    # Try each vendor's rules
    for vendor, abbrev_map in rules.items():
        for abbrev, canonical_prefix in abbrev_map.items():
            if interface.startswith(abbrev):
                # Replace abbreviation with canonical
                expanded = canonical_prefix + interface[len(abbrev):]
                _canonical_cache[interface] = expanded
                return expanded
    
    # No expansion found; return None to signal mismatch
    return None
```

### match_interface_on_device(device, interface_name, rules) → str | None

Find matching interface on a device by name.

```python
def match_interface_on_device(device, interface_name: str, rules: dict) -> str | None:
    """
    Find matching interface on device by name.
    
    Tries direct name match first, then vendor-specific normalization.
    
    Args:
        device: NormalizedDevice or pynetbox.dcim.Device
        interface_name: Interface name to match (e.g., "Gi0/1")
        rules: Vendor-specific normalization rules
    
    Returns:
        Matching interface name from device, or None if not found
    """
    device_interfaces = [iface.name for iface in device.interfaces] if hasattr(device, 'interfaces') else []
    
    # Direct match
    if interface_name in device_interfaces:
        return interface_name
    
    # Normalized match
    interface_normalized = normalize_interface_name(interface_name, rules)
    if interface_normalized and interface_normalized in device_interfaces:
        return interface_normalized
    
    # Try matching any device interface against the provided name (reverse lookup)
    for device_iface_name in device_interfaces:
        device_iface_normalized = normalize_interface_name(device_iface_name, rules)
        if device_iface_normalized and device_iface_normalized == interface_normalized:
            return device_iface_name
    
    return None
```

### dedupe_key(dev_a, iface_a, dev_b, iface_b) → str

Generate deterministic deduplication key for bidirectional matching.

```python
def dedupe_key(device_a: str, interface_a: str, device_b: str, interface_b: str) -> str:
    """
    Generate sorted deduplication key for bidirectional cables.
    
    Ensures A→B and B→A produce the same key.
    
    Args:
        device_a, interface_a, device_b, interface_b: Endpoint identifiers
    
    Returns:
        Sorted canonical key (md5 hash)
    """
    endpoint_a = f"{device_a}:{interface_a}"
    endpoint_b = f"{device_b}:{interface_b}"
    
    # Sort endpoints so A→B and B→A produce same key
    endpoints = tuple(sorted([endpoint_a, endpoint_b]))
    key_str = f"{endpoints[0]}|{endpoints[1]}"
    
    return hashlib.md5(key_str.encode()).hexdigest()
```

### is_bidirectional_match(dev_a, dev_b, discovery_result) → bool

Check if two devices see each other via LLDP (both ways).

```python
def is_bidirectional_match(device_a: str, device_b: str, discovery_result: DiscoveryResult) -> bool:
    """
    Check if device_a and device_b mutually advertise each other.
    
    Args:
        device_a, device_b: Normalized device names
        discovery_result: Discovery result containing LLDP neighbors
    
    Returns:
        True if A sees B and B sees A
    """
    dev_a_obj = next((d for d in discovery_result.devices if normalize_hostname(d.name) == device_a), None)
    dev_b_obj = next((d for d in discovery_result.devices if normalize_hostname(d.name) == device_b), None)
    
    if not dev_a_obj or not dev_b_obj:
        return False
    
    # Check if A sees B
    a_sees_b = any(normalize_hostname(n.neighbor_device_name) == device_b for n in dev_a_obj.lldp_neighbors)
    
    # Check if B sees A
    b_sees_a = any(normalize_hostname(n.neighbor_device_name) == device_a for n in dev_b_obj.lldp_neighbors)
    
    return a_sees_b and b_sees_a
```

### is_ambiguous_mac(device_name, discovery_result, netbox_client) → bool

Check if a chassis MAC is ambiguous (appears on multiple devices).

```python
def is_ambiguous_mac(device_name: str, discovery_result: DiscoveryResult, netbox_client) -> bool:
    """
    Check if a device is resolved via ambiguous chassis MAC.
    
    Counts how many devices have the same MAC and returns True if > 1.
    
    Args:
        device_name: Device to check
        discovery_result: Discovery result
        netbox_client: Optional NetBox client for checking existing inventory
    
    Returns:
        True if MAC is ambiguous (multiple devices have it)
    """
    # Implementation: Count devices with this MAC in discovery + NetBox
    # Return True if count > 1
    pass
```

### lookup_device_in_netbox(netbox_client, hostname, mac) → Device | None

Query NetBox for a device by hostname or MAC.

```python
def lookup_device_in_netbox(netbox_client, hostname: str, mac: str) -> Device | None:
    """
    Query NetBox for a device by hostname or chassis MAC.
    
    Args:
        netbox_client: pynetbox.api instance
        hostname: Device hostname to search for
        mac: Chassis MAC to search for
    
    Returns:
        First matching NetBox device, or None if not found
    """
    if not netbox_client:
        return None
    
    try:
        # Try hostname match
        devices = list(netbox_client.dcim.devices.filter(name=hostname))
        if devices:
            return devices[0]
        
        # Try MAC match
        if mac:
            # NetBox doesn't have a direct MAC filter; search via interface
            devices = list(netbox_client.dcim.interfaces.filter(mac_address=mac))
            if devices:
                return devices[0].device
    except Exception:
        pass
    
    return None
```

### cable_exists_in_netbox(netbox_client, cable) → bool

Check if a cable already exists in NetBox by endpoint matching.

```python
def cable_exists_in_netbox(netbox_client, cable: NormalizedCable) -> bool:
    """
    Check if a cable exists in NetBox by endpoint matching.
    
    Matches on device name + interface name for both endpoints.
    
    Args:
        netbox_client: pynetbox.api instance
        cable: NormalizedCable to check
    
    Returns:
        True if cable already exists in NetBox
    """
    try:
        # Query NetBox cables
        # This is pseudo-code; actual pynetbox API may vary
        cables = list(netbox_client.dcim.cables.all())
        
        for existing_cable in cables:
            # Extract endpoint device/interface
            a_dev = existing_cable.termination_a_device
            a_iface = existing_cable.termination_a_interface
            
            b_dev = existing_cable.termination_b_device
            b_iface = existing_cable.termination_b_interface
            
            # Check both directions
            if ((a_dev.name == cable.device_a_name and a_iface.name == cable.interface_a_name and
                 b_dev.name == cable.device_b_name and b_iface.name == cable.interface_b_name) or
                (a_dev.name == cable.device_b_name and a_iface.name == cable.interface_b_name and
                 b_dev.name == cable.device_a_name and b_iface.name == cable.interface_a_name)):
                return True
        
        return False
    except Exception:
        return False
```

---

## Usage Example

```python
from orbweaver.models.common import DiscoveryResult, NormalizedDevice
from orbweaver.cables.resolve import resolve_cables
import pynetbox

# Collect discovery result from collectors
discovery_result = DiscoveryResult(
    devices=[
        NormalizedDevice(
            name="switch1",
            lldp_neighbors=[
                NormalizedLLDPNeighbor(
                    local_interface="Gi0/1",
                    neighbor_device_name="switch2.example.com",
                    neighbor_interface="Gi0/1",
                    neighbor_chassis_mac="aa:bb:cc:dd:ee:ff"
                )
            ]
        ),
        NormalizedDevice(
            name="switch2",
            lldp_neighbors=[
                NormalizedLLDPNeighbor(
                    local_interface="Gi0/1",
                    neighbor_device_name="switch1",
                    neighbor_interface="Gi0/1",
                    neighbor_chassis_mac="aa:bb:cc:dd:ee:00"
                )
            ]
        )
    ]
)

# Resolve cables
netbox_client = pynetbox.api("http://netbox:8000", token="...")
candidates, summary = resolve_cables(discovery_result, netbox_client)

print(f"Found {summary.discovered} LLDP neighbors")
print(f"Created {len(candidates)} cable candidates")
print(f"Summary: {summary}")

for candidate in candidates:
    if candidate.is_writable:
        print(f"  {candidate.cable.device_a_name}:{candidate.cable.interface_a_name} "
              f"↔ {candidate.cable.device_b_name}:{candidate.cable.interface_b_name} "
              f"({candidate.confidence})")
```

---

**Status**: ✅ Contract Complete  
**Ready for**: Implementation
