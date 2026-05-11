"""Reconstruct NormalizedDevice dataclass instances from stored JSON dicts.

Uses dacite for clean enum coercion.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import Enum

import dacite

from orbweaver.cables.models import CableCandidate
from orbweaver.models.common import NormalizedDevice


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


_DACITE_CONFIG = dacite.Config(
    cast=[Enum],
    type_hooks={datetime: _parse_datetime},
)


def device_from_dict(data: dict) -> NormalizedDevice:
    """Reconstruct a NormalizedDevice from a serialized dict (stored in ReviewItem.data)."""
    return dacite.from_dict(NormalizedDevice, data, config=_DACITE_CONFIG)


def cable_candidate_to_dict(candidate: CableCandidate) -> dict:
    """Serialize CableCandidate dataclass to a JSON-compatible dict."""
    return dataclasses.asdict(candidate)


def dict_to_cable_candidate(data: dict) -> CableCandidate:
    """Reconstruct CableCandidate from serialized review data."""
    return dacite.from_dict(CableCandidate, data, config=_DACITE_CONFIG)
