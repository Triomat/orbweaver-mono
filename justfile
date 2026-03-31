#!/usr/bin/env just --justfile
# orbweaver development tasks

set dotenv-load := true

VENV       := ".venv/bin"
DD_DIR     := "backend"
UI_DIR     := "frontend"
REVIEW_DIR    := "/tmp/orbweaver-reviews"
API_BASE   := "http://192.168.11.90:8073"
UI_PORT    := "3000"
SCRIPTS    := justfile_directory() / "scripts"

# List all recipes
default:
    @just --list

# ── Backend ──────────────────────────────────────────────────────────────────

# Install / sync Python dependencies (upstream backend + orbweaver package)
install-backend:
    {{VENV}}/pip install -e "{{DD_DIR}}[dev,test]"
    {{VENV}}/pip install -e "orbweaver[dev,test]"

# Start orbweaver backend (dry-run, no Diode server needed)
backend-start:
    ORBWEAVER_PORT=8073 \
    ORBWEAVER_REVIEW_DIR={{REVIEW_DIR}} \
    {{SCRIPTS}}/orbweaver-backend start

# Stop orbweaver backend
backend-stop:
    {{SCRIPTS}}/orbweaver-backend stop

# Restart orbweaver backend (sources docker/.env for Diode credentials if present)
backend-restart target="":
    #!/usr/bin/env bash
    set -euo pipefail
    env_file="{{justfile_directory()}}/docker/.env"
    if [[ -f "$env_file" ]]; then
        set -a; source "$env_file"; set +a
    fi
    export ORBWEAVER_PORT=8073
    export ORBWEAVER_REVIEW_DIR={{REVIEW_DIR}}
    if [[ -n "{{target}}" ]]; then
        export ORBWEAVER_DIODE_TARGET={{target}}
        export ORBWEAVER_DIODE_CLIENT_ID="${DIODE_CLIENT_ID:-}"
        export ORBWEAVER_DIODE_CLIENT_SECRET="${DIODE_CLIENT_SECRET:-}"
    fi
    {{SCRIPTS}}/orbweaver-backend restart

# Show backend status
backend-status:
    {{SCRIPTS}}/orbweaver-backend status

# Tail backend logs
backend-logs:
    {{SCRIPTS}}/orbweaver-backend logs

# Start backend against a real Diode target (reads credentials from docker/.env)
# Usage: just backend-live [grpc://diode-server:8080/diode]
backend-live target="grpc://192.168.11.90:8080/diode":
    #!/usr/bin/env bash
    set -euo pipefail
    env_file="{{justfile_directory()}}/docker/.env"
    if [[ -f "$env_file" ]]; then
        set -a; source "$env_file"; set +a
    fi
    ORBWEAVER_PORT=8073 \
    ORBWEAVER_REVIEW_DIR={{REVIEW_DIR}} \
    ORBWEAVER_DIODE_TARGET={{target}} \
    ORBWEAVER_DIODE_CLIENT_ID="${DIODE_CLIENT_ID:-}" \
    ORBWEAVER_DIODE_CLIENT_SECRET="${DIODE_CLIENT_SECRET:-}" \
    {{SCRIPTS}}/orbweaver-backend start

# ── Frontend ─────────────────────────────────────────────────────────────────

# Install Node dependencies for the UI
install-ui:
    pnpm --dir {{UI_DIR}} install

# Start the Nuxt dev server
ui-start:
    NUXT_PUBLIC_API_BASE={{API_BASE}} \
    ORBWEAVER_UI_PORT={{UI_PORT}} \
    {{SCRIPTS}}/orbweaver-ui start

# Stop the Nuxt dev server
ui-stop:
    {{SCRIPTS}}/orbweaver-ui stop

# Restart the Nuxt dev server
ui-restart:
    NUXT_PUBLIC_API_BASE={{API_BASE}} \
    ORBWEAVER_UI_PORT={{UI_PORT}} \
    {{SCRIPTS}}/orbweaver-ui restart

# Show UI status
ui-status:
    {{SCRIPTS}}/orbweaver-ui status

# Tail UI logs
ui-logs:
    {{SCRIPTS}}/orbweaver-ui logs

# Build the UI for production
ui-build:
    NUXT_PUBLIC_API_BASE={{API_BASE}} pnpm --dir {{UI_DIR}} build

# ── Seed data ────────────────────────────────────────────────────────────────

# Seed a fake review session for UI testing
seed:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p {{REVIEW_DIR}}
    ID=$({{VENV}}/python {{DD_DIR}}/seed_review.py {{REVIEW_DIR}})
    echo "Seeded review: $ID"
    echo "Open: http://localhost:{{UI_PORT}}/review/$ID"

# ── Combined ─────────────────────────────────────────────────────────────────

# Start backend + UI (dry-run). Use: just start [grpc://host:8080] to point at a real Diode target.
start target="":
    #!/usr/bin/env bash
    set -euo pipefail
    # Load docker/.env for Diode credentials if present
    env_file="{{justfile_directory()}}/docker/.env"
    if [[ -f "$env_file" ]]; then
        set -a; source "$env_file"; set +a
    fi
    if [[ -n "{{target}}" ]]; then
        ORBWEAVER_PORT=8073 ORBWEAVER_REVIEW_DIR={{REVIEW_DIR}} \
        ORBWEAVER_DIODE_TARGET={{target}} \
        ORBWEAVER_DIODE_CLIENT_ID="${DIODE_CLIENT_ID:-}" \
        ORBWEAVER_DIODE_CLIENT_SECRET="${DIODE_CLIENT_SECRET:-}" \
        {{SCRIPTS}}/orbweaver-backend start
    else
        ORBWEAVER_PORT=8073 ORBWEAVER_REVIEW_DIR={{REVIEW_DIR}} \
        {{SCRIPTS}}/orbweaver-backend start
    fi
    NUXT_PUBLIC_API_BASE={{API_BASE}} ORBWEAVER_UI_PORT={{UI_PORT}} {{SCRIPTS}}/orbweaver-ui start

# Stop backend + UI
stop:
    just ui-stop
    just backend-stop

# Restart backend + UI. Use: just restart [grpc://host:8080]
restart target="":
    just stop
    just start {{target}}

# Show status of both services
ps:
    just backend-status
    just ui-status

# ── Docker (integration stack) ───────────────────────────────────────────────

# Build and start the full stack via Docker
docker-up:
    docker compose -f docker/docker-compose.yml --env-file docker/.env up -d --build

# Stop and remove all Docker containers
docker-down:
    docker compose -f docker/docker-compose.yml down

# Stream logs from Docker backend container
docker-logs:
    docker compose -f docker/docker-compose.yml logs -f orbweaver

# POST the example policy to the Docker stack
docker-push-policy:
    curl -s -o /dev/null -w "%{http_code}" \
        -X POST -H "Content-Type: application/x-yaml" \
        --data-binary @docker/policy-example.yaml \
        http://localhost:8072/api/v1/policies

# Preview what cleanup would delete (no changes made)
docker-cleanup-dry:
    @export $(grep -v '^#' docker/.env | xargs) && \
        {{VENV}}/python docker/netbox-cleanup.py --dry-run

# Delete all orbweaver-ingested objects from NetBox (tagged 'discovered')
docker-cleanup:
    @export $(grep -v '^#' docker/.env | xargs) && \
        {{VENV}}/python docker/netbox-cleanup.py

# ── Utilities ────────────────────────────────────────────────────────────────

# Check backend health
status:
    curl -s {{API_BASE}}/api/v1/status | python3 -m json.tool

# List registered collectors
collectors:
    curl -s {{API_BASE}}/api/v1/collectors | python3 -m json.tool

# List review sessions
reviews:
    curl -s {{API_BASE}}/api/v1/reviews | python3 -m json.tool

# ── Tests & lint ─────────────────────────────────────────────────────────────

# Run backend tests
test:
    cd {{DD_DIR}} && {{VENV}}/pytest tests/ -v

# Run tests with coverage report
test-cov:
    cd {{DD_DIR}} && {{VENV}}/pytest tests/ -v --tb=short \
        --cov=device_discovery --cov-report=term-missing --cov-report=html:coverage/

# Run only the legacy (upstream) tests — verifies nothing broke
test-legacy:
    cd {{DD_DIR}} && {{VENV}}/pytest tests/ -v --tb=short \
        --ignore=tests/test_collectors.py \
        --ignore=tests/test_diode_translate.py

# Run a specific test file
test-file file:
    cd {{DD_DIR}} && {{VENV}}/pytest {{file}} -v --tb=short

# Run ruff linter
lint:
    cd {{DD_DIR}} && {{VENV}}/python -m ruff check device_discovery/ tests/

# Verify all orbweaver module imports are valid (no Diode SDK required)
check-imports:
    {{VENV}}/python {{DD_DIR}}/scripts/check_imports.py

# Syntax-check all Python files
check-syntax:
    {{VENV}}/python -m py_compile \
        orbweaver/models/common.py \
        orbweaver/models/version_parser.py \
        orbweaver/collectors/base.py \
        orbweaver/collectors/napalm_helpers.py \
        orbweaver/collectors/napalm_collector.py \
        orbweaver/collectors/cisco_ios.py \
        orbweaver/collectors/aruba_aoscx.py \
        orbweaver/collectors/registry.py \
        orbweaver/diode_translate.py \
        orbweaver/patches.py \
        orbweaver/app.py \
        orbweaver/main.py
    @echo "All syntax OK"

# ── Git workflows ────────────────────────────────────────────────────────────

# Run tests, push current branch to origin, then merge into develop
promote-to-dev: test
    #!/usr/bin/env bash
    set -euo pipefail
    branch=$(git rev-parse --abbrev-ref HEAD)
    echo "Pushing branch '${branch}' to origin..."
    git push origin "${branch}"
    echo "Merging '${branch}' into develop..."
    git checkout develop
    git merge --no-ff "${branch}" -m "Merge branch '${branch}' into develop"
    git push origin develop
    git checkout "${branch}"
    echo "Done. '${branch}' merged into develop and pushed."

# ── Env setup ────────────────────────────────────────────────────────────────

# Run full bootstrap on a fresh Ubuntu machine
bootstrap:
    bash scripts/bootstrap.sh

# Verify all required secret files are present and filled in
check-secrets:
    bash scripts/setup-secrets.sh

# Create docker/.env from template if it doesn't exist
init-env:
    @test -f docker/.env || (cp docker/.env.example docker/.env && echo "Created docker/.env — fill in credentials before running containers.")

# Install pre-commit hooks
install-hooks:
    {{VENV}}/python -m pre_commit install
