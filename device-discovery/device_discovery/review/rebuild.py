"""Reconstruct NormalizedDevice dataclass instances from stored JSON dicts.

Uses dacite for clean enum coercion.
"""

from __future__ import annotations

from enum import Enum

import dacite

from device_discovery.models.common import NormalizedDevice


_DACITE_CONFIG = dacite.Config(cast=[Enum])


def device_from_dict(data: dict) -> NormalizedDevice:
    """Reconstruct a NormalizedDevice from a serialized dict (stored in ReviewItem.data)."""
    return dacite.from_dict(NormalizedDevice, data, config=_DACITE_CONFIG)
