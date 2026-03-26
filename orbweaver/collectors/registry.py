"""
Collector Registry — pluggable vendor discovery.

Register vendor collectors by name so the orchestrator (or CLI) can
instantiate them by string key. This avoids hard-coding vendor imports
and makes it trivial to add new vendors.

Usage:
    from orbweaver.collectors.registry import get_collector

    collector_class, config_class = get_collector("aruba_aoscx")
    config = config_class(hosts=["10.0.0.1"], username="admin", password="secret")
    collector = collector_class(config)
    result = collector.discover()
"""

from __future__ import annotations

from typing import Type

from orbweaver.collectors.base import BaseCollector, CollectorConfig

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, tuple[Type[BaseCollector], Type[CollectorConfig]]] = {}


def register_collector(
    name: str,
    collector_class: Type[BaseCollector],
    config_class: Type[CollectorConfig] = CollectorConfig,
) -> None:
    """Register a vendor collector."""
    _REGISTRY[name] = (collector_class, config_class)


def get_collector(name: str) -> tuple[Type[BaseCollector], Type[CollectorConfig]]:
    """Get a registered collector by name."""
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise KeyError(f"Unknown collector: '{name}'. Available: {available}")
    return _REGISTRY[name]


def list_collectors() -> list[str]:
    """List all registered collector names."""
    return sorted(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Auto-register built-in collectors
# ---------------------------------------------------------------------------


def _register_builtins() -> None:
    """Import and register all built-in collectors."""
    from orbweaver.collectors.aruba_aoscx import ArubaCollector, ArubaConfig
    from orbweaver.collectors.cisco_ios import CiscoCollector, CiscoConfig
    from orbweaver.collectors.napalm_helpers import NapalmConfig
    from orbweaver.collectors.napalm_collector import NapalmCollector

    register_collector("aruba_aoscx", ArubaCollector, ArubaConfig)
    register_collector("cisco_ios", CiscoCollector, CiscoConfig)
    register_collector("napalm", NapalmCollector, NapalmConfig)


_register_builtins()
