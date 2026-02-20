"""Verify all orbweaver-specific module imports work correctly."""

import sys

checks = [
    ("device_discovery.models.common", ["NormalizedDevice", "NormalizedInterface", "DiscoveryResult"]),
    ("device_discovery.models.version_parser", ["parse_version"]),
    ("device_discovery.collectors.base", ["CollectorConfig", "BaseCollector"]),
    ("device_discovery.collectors.napalm_helpers", ["NapalmConfig"]),
    ("device_discovery.collectors.napalm_collector", ["NapalmCollector"]),
    ("device_discovery.collectors.cisco_ios", ["CiscoCollector", "CiscoConfig"]),
    ("device_discovery.collectors.aruba_aoscx", ["ArubaCollector", "ArubaConfig"]),
    ("device_discovery.collectors.registry", ["list_collectors", "get_collector"]),
    ("device_discovery.policy.models", ["Napalm"]),
]

errors = []
for module, names in checks:
    try:
        mod = __import__(module, fromlist=names)
        for name in names:
            getattr(mod, name)
        print(f"  OK  {module}")
    except Exception as e:
        print(f"  FAIL {module}: {e}")
        errors.append(module)

from device_discovery.collectors.registry import list_collectors
print(f"\nRegistered collectors: {list_collectors()}")

if errors:
    print(f"\n{len(errors)} import(s) failed.")
    sys.exit(1)
else:
    print("\nAll imports OK.")
