"""Verify all orbweaver-specific module imports work correctly."""

import sys

checks = [
    ("extensions.models.common", ["NormalizedDevice", "NormalizedInterface", "DiscoveryResult"]),
    ("extensions.models.version_parser", ["parse_version"]),
    ("extensions.collectors.base", ["CollectorConfig", "BaseCollector"]),
    ("extensions.collectors.napalm_helpers", ["NapalmConfig"]),
    ("extensions.collectors.napalm_collector", ["NapalmCollector"]),
    ("extensions.collectors.cisco_ios", ["CiscoCollector", "CiscoConfig"]),
    ("extensions.collectors.aruba_aoscx", ["ArubaCollector", "ArubaConfig"]),
    ("extensions.collectors.registry", ["list_collectors", "get_collector"]),
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

from extensions.collectors.registry import list_collectors
print(f"\nRegistered collectors: {list_collectors()}")

if errors:
    print(f"\n{len(errors)} import(s) failed.")
    sys.exit(1)
else:
    print("\nAll imports OK.")
