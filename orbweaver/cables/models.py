"""Data models for LLDP cable resolution and ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from orbweaver.models.common import NormalizedCable, NormalizedLLDPNeighbor


class ResolutionConfidence(str, Enum):
    """Confidence tier for cable resolution."""

    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    UNRESOLVABLE = "unresolvable"


@dataclass
class CableSkipEntry:
    """Detailed skip information for an unresolved cable candidate."""

    local_device: str
    local_interface: str
    neighbor_hostname: str
    reason: str
    neighbor_interface: str = ""
    neighbor_chassis_mac: str = ""
    neighbor_mgmt_ip: str = ""


@dataclass
class CableCandidate:
    """Resolved cable candidate with provenance and confidence metadata."""

    cable: NormalizedCable
    confidence: ResolutionConfidence
    device_a_discovered: bool
    device_b_discovered: bool
    skip_reason: str | None = None
    lldp_neighbor: NormalizedLLDPNeighbor | None = None
    resolution_notes: str = ""
    lldp_direction: str = ""

    @property
    def is_writable(self) -> bool:
        """Return True when the candidate is eligible for NetBox write."""
        return self.confidence in (
            ResolutionConfidence.CONFIRMED,
            ResolutionConfidence.PARTIAL,
        )


@dataclass
class CableResolutionSummary:
    """Aggregated outcome of cable resolution and optional ingestion."""

    discovered: int = 0
    candidates: int = 0
    created: int = 0
    skipped: int = 0
    unresolvable: int = 0
    skip_entries: list[CableSkipEntry] = field(default_factory=list)
    ingestion_disabled: bool = False
    ingestion_error: str | None = None
    resolution_duration_ms: float = 0.0
    ingestion_duration_ms: float = 0.0
