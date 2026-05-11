"""Cable discovery and ingestion primitives."""

from orbweaver.cables.ingest import (
    create_cable_in_netbox,
    delete_cable_in_netbox,
    get_device_id,
    get_interface_id,
    ingest_cables_direct,
    ingest_cables_from_review,
)
from orbweaver.cables.models import (
    CableCandidate,
    CableResolutionSummary,
    CableSkipEntry,
    ResolutionConfidence,
)
from orbweaver.cables.normalize import (
    DEFAULT_INTERFACE_MAPPINGS,
    normalize_chassis_mac,
    normalize_hostname,
    normalize_interface_name,
)
from orbweaver.cables.resolve import (
    build_discovered_device_indexes,
    cable_exists_in_netbox,
    dedupe_key,
    determine_lldp_direction,
    is_ambiguous_mac,
    is_bidirectional_match,
    is_self_loop,
    lookup_device_in_netbox,
    match_interface_on_device,
    resolve_cables,
)

__all__ = [
    "CableCandidate",
    "CableResolutionSummary",
    "CableSkipEntry",
    "build_discovered_device_indexes",
    "cable_exists_in_netbox",
    "create_cable_in_netbox",
    "DEFAULT_INTERFACE_MAPPINGS",
    "dedupe_key",
    "delete_cable_in_netbox",
    "determine_lldp_direction",
    "get_device_id",
    "get_interface_id",
    "ingest_cables_direct",
    "ingest_cables_from_review",
    "is_ambiguous_mac",
    "is_bidirectional_match",
    "is_self_loop",
    "lookup_device_in_netbox",
    "match_interface_on_device",
    "ResolutionConfidence",
    "normalize_chassis_mac",
    "normalize_hostname",
    "normalize_interface_name",
    "resolve_cables",
]
