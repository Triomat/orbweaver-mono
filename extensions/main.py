"""
orbweaver entry point.

Startup order (order matters):
  1. Apply runtime patches to upstream classes (Napalm model + PolicyRunner)
  2. Import extensions.app — extends the upstream FastAPI app in-place
  3. Delegate to the upstream main() which starts uvicorn with the extended app
"""
import extensions.patches  # noqa: F401 — side-effects: patches upstream classes
import extensions.app      # noqa: F401 — side-effects: extends upstream FastAPI app

from device_discovery.main import main  # noqa: E402


if __name__ == "__main__":
    main()
