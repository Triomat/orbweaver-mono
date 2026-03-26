#!/usr/bin/env python
# Copyright 2024 NetBox Labs Inc
"""
Diode translation bridge: COM (Common Object Model) → Diode SDK entities.

Converts the rich NormalizedDevice/NormalizedInterface/etc. objects produced
by vendor collectors into the flat list of Entity objects required by
Client().ingest().

This is the translation layer between netbox-discovery's collector framework
and orb-discovery's Diode SDK output path.
"""

from __future__ import annotations

import logging

from netboxlabs.diode.sdk.ingester import (
    VLAN,
    Device,
    DeviceType,
    Entity,
    Interface,
    IPAddress,
    Platform,
    Prefix,
)

from orbweaver.models.common import (
    DiscoveryResult,
    NormalizedDevice,
    NormalizedInterface,
    NormalizedIPAddress,
    NormalizedPrefix,
    NormalizedVLAN,
)
from device_discovery.policy.models import Defaults

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def translate_discovery_result(result: DiscoveryResult, defaults: Defaults) -> list[Entity]:
    """
    Translate a full DiscoveryResult into a flat list of Diode Entity objects.

    Args:
        result: DiscoveryResult from a vendor collector.
        defaults: orb-discovery Defaults for site/role/tags/tenant overrides.

    Returns:
        Flat list of Entity objects ready for Client().ingest().
    """
    entities: list[Entity] = []

    for device in result.devices:
        entities.extend(translate_single_device(device, defaults))

    # Result-level prefixes (deduplicated across devices)
    for prefix in result.prefixes:
        entity = _translate_prefix(prefix)
        if entity:
            entities.append(entity)

    return entities


def translate_single_device(device: NormalizedDevice, defaults: Defaults) -> list[Entity]:
    """
    Translate a single NormalizedDevice into Diode Entity objects.

    Produces:
      - One Entity(device=...) for the device itself
      - One Entity(interface=...) per interface
      - One Entity(ip_address=...) per IP on each interface
      - One Entity(vlan=...) per VLAN on the device
      - One Entity(prefix=...) per prefix derived from interface IPs

    Args:
        device: NormalizedDevice from a vendor collector.
        defaults: orb-discovery Defaults for site/role/tags overrides.

    Returns:
        List of Entity objects for this device.
    """
    entities: list[Entity] = []

    # 1. Device entity (without primary IPs — they can't be set until the IPs
    #    are assigned to interfaces, which happens in step 2 below)
    diode_device = _translate_device(device, defaults)
    entities.append(Entity(device=diode_device))

    # 2. Interface entities (with IPs)
    for iface in device.interfaces:
        iface_entities = _translate_interface(diode_device, iface)
        entities.extend(iface_entities)

    # 3. VLAN entities
    for vlan in device.vlans:
        vlan_entity = _translate_vlan(vlan, defaults)
        if vlan_entity:
            entities.append(Entity(vlan=vlan_entity))

    # 4. Set primary IPs last — NetBox requires the IP to already be assigned
    #    to an interface before it can be designated as primary on the device.
    if device.primary_ip4 or device.primary_ip6:
        entities.append(Entity(device=Device(
            name=diode_device.name,
            site=diode_device.site,
            device_type=diode_device.device_type,
            role=diode_device.role,
            primary_ip4=device.primary_ip4 or None,
            primary_ip6=device.primary_ip6 or None,
        )))

    return entities


# ---------------------------------------------------------------------------
# Private translators
# ---------------------------------------------------------------------------


def _translate_device(device: NormalizedDevice, defaults: Defaults) -> Device:
    """Convert NormalizedDevice → Diode Device."""
    # Site: defaults.site wins over COM site name
    site_name = defaults.site if defaults.site and defaults.site != "undefined" else None
    if not site_name and device.site:
        site_name = device.site.name

    # Role: defaults.role wins over COM role name
    role_name = defaults.role if defaults.role and defaults.role != "undefined" else None
    if not role_name and device.role:
        role_name = device.role.name

    # Manufacturer
    manufacturer_name = None
    if device.device_type and device.device_type.manufacturer:
        manufacturer_name = device.device_type.manufacturer.name

    # Model
    model = device.device_type.model if device.device_type else None

    # Platform
    platform = None
    if device.platform:
        platform = Platform(
            name=device.platform.name,
            manufacturer=manufacturer_name,
        )

    # Tags from defaults
    tags = list(defaults.tags) if defaults.tags else []

    return Device(
        name=device.name,
        device_type=DeviceType(
            model=model,
            manufacturer=manufacturer_name,
        ),
        platform=platform,
        role=role_name,
        serial=device.serial or None,
        status=device.status.value if device.status else "active",
        site=site_name,
        tags=tags,
        comments=device.comments or None,
    )


def _translate_interface(
    diode_device: Device,
    iface: NormalizedInterface,
) -> list[Entity]:
    """Convert NormalizedInterface → list of Diode Entity objects."""
    entities: list[Entity] = []

    # Build the interface entity
    # Diode SDK Interface: device, name, type, enabled, description, mac, mtu, speed
    # mode/vlan fields: check what the SDK supports
    untagged_vlan = None
    if iface.untagged_vlan:
        untagged_vlan = _com_vlan_to_diode(iface.untagged_vlan)

    tagged_vlans = [_com_vlan_to_diode(v) for v in iface.tagged_vlans] if iface.tagged_vlans else []

    # Build a device reference for use in interface/IP entities.
    # Must include device_type, role, platform, serial to prevent Diode from
    # clobbering those fields when upserting the device from a nested ref.
    # Must NOT include primary_ip4/primary_ip6: NetBox rejects setting a primary
    # IP before that IP is assigned to an interface, causing the whole changeset
    # (including the interface itself) to fail.
    device_ref = Device(
        name=diode_device.name,
        site=diode_device.site,
        device_type=diode_device.device_type,
        role=diode_device.role,
        platform=diode_device.platform,
        serial=diode_device.serial,
        status=diode_device.status,
        tags=diode_device.tags,
        comments=diode_device.comments,
    )

    iface_kwargs = {
        "device": device_ref,
        "name": iface.name,
        "type": iface.type.value if iface.type else "other",
        "enabled": iface.enabled,
        "description": iface.description or None,
        "primary_mac_address": iface.mac_address or None,
        "mtu": iface.mtu if iface.mtu and iface.mtu > 0 else None,
    }

    # Speed: COM stores Kbps, Diode expects Kbps
    if iface.speed and iface.speed > 0:
        iface_kwargs["speed"] = iface.speed

    # Switchport mode and VLANs — set if present
    if iface.mode:
        iface_kwargs["mode"] = iface.mode.value

    if untagged_vlan:
        iface_kwargs["untagged_vlan"] = untagged_vlan

    if tagged_vlans:
        iface_kwargs["tagged_vlans"] = tagged_vlans

    try:
        diode_iface = Interface(**iface_kwargs)
        entities.append(Entity(interface=diode_iface))
    except Exception as e:
        logger.warning(f"Failed to create Interface entity for {iface.name}: {e}")
        # Create minimal interface as fallback
        try:
            diode_iface = Interface(
                device=device_ref,
                name=iface.name,
                type=iface.type.value if iface.type else "other",
            )
            entities.append(Entity(interface=diode_iface))
        except Exception as e2:
            logger.error(f"Failed to create fallback Interface entity for {iface.name}: {e2}")
            return entities

    # IP address entities
    for ip in iface.ip_addresses:
        ip_entities = _translate_ip_address(ip, diode_iface)
        entities.extend(ip_entities)

    return entities


def _translate_ip_address(
    ip: NormalizedIPAddress,
    diode_iface: Interface,
) -> list[Entity]:
    """Convert NormalizedIPAddress → Diode IPAddress + Prefix entities."""
    import ipaddress as _ipaddress

    entities: list[Entity] = []

    try:
        net = _ipaddress.ip_interface(ip.address).network
        prefix_str = str(net)

        # Prefix entity
        entities.append(
            Entity(
                prefix=Prefix(
                    prefix=prefix_str,
                )
            )
        )

        # IP address entity
        role = ip.role.value if ip.role else None
        entities.append(
            Entity(
                ip_address=IPAddress(
                    address=ip.address,
                    assigned_object_interface=Interface(
                        device=diode_iface.device,
                        name=diode_iface.name,
                        type=diode_iface.type,
                    ),
                    role=role,
                    description=ip.description or None,
                )
            )
        )
    except Exception as e:
        logger.warning(f"Failed to translate IP address {ip.address}: {e}")

    return entities


def _translate_vlan(vlan: NormalizedVLAN, defaults: Defaults) -> VLAN | None:
    """Convert NormalizedVLAN → Diode VLAN."""
    try:
        tags = list(defaults.tags) if defaults.tags else []
        group = None
        tenant = None
        role = None
        description = vlan.description or None
        comments = None

        if defaults.vlan:
            tags.extend(defaults.vlan.tags or [])
            group = defaults.vlan.group
            role = defaults.vlan.role
            description = defaults.vlan.description or description
            comments = defaults.vlan.comments
            if defaults.vlan.tenant:
                from device_discovery.translate import translate_tenant
                tenant = translate_tenant(defaults.vlan.tenant)

        return VLAN(
            vid=vlan.vid,
            name=vlan.name,
            group=group,
            tenant=tenant,
            role=role,
            tags=tags,
            comments=comments,
            description=description,
        )
    except Exception as e:
        logger.warning(f"Failed to translate VLAN {vlan.vid}: {e}")
        return None


def _translate_prefix(prefix: NormalizedPrefix) -> Entity | None:
    """Convert NormalizedPrefix → Diode Prefix Entity."""
    try:
        vlan = None
        if prefix.vlan:
            vlan = _com_vlan_to_diode(prefix.vlan)

        return Entity(
            prefix=Prefix(
                prefix=prefix.prefix,
                vlan=vlan,
                description=prefix.description or None,
            )
        )
    except Exception as e:
        logger.warning(f"Failed to translate prefix {prefix.prefix}: {e}")
        return None


def _com_vlan_to_diode(vlan: NormalizedVLAN) -> VLAN:
    """Convert a NormalizedVLAN to a minimal Diode VLAN reference."""
    return VLAN(
        vid=vlan.vid,
        name=vlan.name,
    )
