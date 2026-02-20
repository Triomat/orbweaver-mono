# orbweaver Justfile
# Run: just <recipe>

venv   := justfile_directory() / ".venv"
python := venv / "bin" / "python"
pip    := python + " -m pip"

# Show available recipes
default:
    @just --list

# ─── venv ─────────────────────────────────────────────────────────────────────

# Create the shared virtual environment
venv:
    test -d {{venv}} || python3 -m venv {{venv}}

# ─── device-discovery ────────────────────────────────────────────────────────

# Install device-discovery with test dependencies
install-dd: venv
    cd device-discovery && {{pip}} install -e ".[test]"

# Run all device-discovery tests
test-dd: install-dd
    cd device-discovery && {{python}} -m pytest tests/ -v --tb=short

# Run device-discovery tests with coverage report
test-dd-cov: install-dd
    cd device-discovery && {{python}} -m pytest tests/ -v --tb=short \
        --cov=device_discovery --cov-report=term-missing --cov-report=html:coverage/

# Run only the legacy (upstream) tests — verifies nothing broke
test-dd-legacy: install-dd
    cd device-discovery && {{python}} -m pytest tests/ -v --tb=short \
        --ignore=tests/test_collectors.py \
        --ignore=tests/test_diode_translate.py

# Run a specific test file
test-dd-file file: install-dd
    cd device-discovery && {{python}} -m pytest {{file}} -v --tb=short

# ─── worker ──────────────────────────────────────────────────────────────────

# Install worker with test dependencies
install-worker: venv
    cd worker && {{pip}} install -e ".[test]"

# Run all worker tests
test-worker: install-worker
    cd worker && {{python}} -m pytest tests/ -v --tb=short

# ─── all ─────────────────────────────────────────────────────────────────────

# Install all components
install: install-dd install-worker

# Run all tests across all components
test: test-dd test-worker

# Run all tests with coverage
test-cov: test-dd-cov test-worker

# ─── lint ────────────────────────────────────────────────────────────────────

# Run ruff linter on device-discovery
lint-dd:
    cd device-discovery && {{python}} -m ruff check device_discovery/ tests/

# Run ruff on all components
lint: lint-dd

# ─── dev utilities ───────────────────────────────────────────────────────────

# Verify all new module imports are valid (no Diode SDK required)
check-imports:
    cd device-discovery && {{python}} scripts/check_imports.py

# Syntax-check all Python files
check-syntax:
    cd device-discovery && {{python}} -m py_compile \
        device_discovery/models/common.py \
        device_discovery/models/version_parser.py \
        device_discovery/collectors/base.py \
        device_discovery/collectors/napalm_helpers.py \
        device_discovery/collectors/napalm_collector.py \
        device_discovery/collectors/cisco_ios.py \
        device_discovery/collectors/aruba_aoscx.py \
        device_discovery/collectors/registry.py \
        device_discovery/diode_translate.py \
        device_discovery/policy/runner.py \
        device_discovery/policy/models.py
    @echo "All syntax OK"
