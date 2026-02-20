#!/usr/bin/env just --justfile
# orbweaver development tasks

set dotenv-load := true

VENV       := ".venv/bin"
DD_DIR     := "device-discovery"
UI_DIR     := "../orbweaver-ui"
REVIEW_DIR := "/tmp/orbweaver-reviews"
API_BASE   := "http://192.168.11.90:8073"
UI_PORT    := "3000"
SCRIPTS    := justfile_directory() / "scripts"

# List all recipes
default:
    @just --list

# ── Backend ──────────────────────────────────────────────────────────────────

# Install / sync Python dependencies (including dacite)
install-backend:
    {{VENV}}/pip install -e "{{DD_DIR}}[dev,test]"

# Start orbweaver backend (dry-run, no Diode server needed)
backend-start:
    ORBWEAVER_PORT=8073 \
    ORBWEAVER_REVIEW_DIR={{REVIEW_DIR}} \
    {{SCRIPTS}}/orbweaver-backend start

# Stop orbweaver backend
backend-stop:
    {{SCRIPTS}}/orbweaver-backend stop

# Restart orbweaver backend
backend-restart:
    ORBWEAVER_PORT=8073 \
    ORBWEAVER_REVIEW_DIR={{REVIEW_DIR}} \
    {{SCRIPTS}}/orbweaver-backend restart

# Show backend status
backend-status:
    {{SCRIPTS}}/orbweaver-backend status

# Tail backend logs
backend-logs:
    {{SCRIPTS}}/orbweaver-backend logs

# Start backend against a real Diode target
# Usage: just backend-live grpc://diode-server:8080
backend-live target="grpc://localhost:8080":
    ORBWEAVER_PORT=8073 \
    ORBWEAVER_REVIEW_DIR={{REVIEW_DIR}} \
    ORBWEAVER_DIODE_TARGET={{target}} \
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

# Start backend + UI
start:
    just backend-start
    just ui-start

# Stop backend + UI
stop:
    just ui-stop
    just backend-stop

# Restart backend + UI
restart:
    just stop
    just start

# Show status of both services
ps:
    just backend-status
    just ui-status

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

# Run backend tests
test:
    cd {{DD_DIR}} && {{VENV}}/pytest tests/ -v
