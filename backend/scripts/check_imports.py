"""Verify all orbweaver-specific module imports work correctly."""

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

for path in (str(REPO_ROOT), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

checks = [
    ("orbweaver.models.common", ["NormalizedDevice", "NormalizedInterface", "DiscoveryResult"]),
    ("orbweaver.models.version_parser", ["parse_version"]),
    ("orbweaver.collectors.base", ["CollectorConfig", "BaseCollector"]),
    ("orbweaver.collectors.napalm_helpers", ["NapalmConfig"]),
    ("orbweaver.collectors.napalm_collector", ["NapalmCollector"]),
    ("orbweaver.collectors.cisco_ios", ["CiscoCollector", "CiscoConfig"]),
    ("orbweaver.collectors.aruba_aoscx", ["ArubaCollector", "ArubaConfig"]),
    ("orbweaver.collectors.registry", ["list_collectors", "get_collector"]),
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

from orbweaver.collectors.registry import list_collectors
print(f"\nRegistered collectors: {list_collectors()}")

if errors:
    print(f"\n{len(errors)} import(s) failed.")
    sys.exit(1)
else:
    print("\nAll imports OK.")
