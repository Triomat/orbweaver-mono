#!/usr/bin/env bash
# setup-secrets.sh — verify all required secret/config files are present
# Usage: bash scripts/setup-secrets.sh  OR  just check-secrets
# Exits 0 if all required files are present; exits 1 if any are missing.

set -euo pipefail

ORBWEAVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PASS=0
FAIL=0

check() {
    local label="$1"
    local path="$2"
    local hint="$3"
    if [[ -f "${path}" ]]; then
        echo "  [ OK ]  ${label}"
    else
        echo "  [MISS]  ${label}"
        echo "          Path: ${path}"
        echo "          Fix:  ${hint}"
        FAIL=$((FAIL + 1))
    fi
}

check_no_changeme() {
    local label="$1"
    local path="$2"
    if [[ ! -f "${path}" ]]; then
        return  # already reported as missing above
    fi
    if grep -q 'CHANGEME' "${path}" 2>/dev/null; then
        echo "  [WARN]  ${label} still contains CHANGEME placeholder(s)"
        echo "          Path: ${path}"
    fi
}

echo ""
echo "Checking required secret files..."
echo ""

# ── Required files ────────────────────────────────────────────────────────────

ENV_FILE="${ORBWEAVER_DIR}/docker/.env"
check "docker/.env" \
    "${ENV_FILE}" \
    "cp docker/.env.example docker/.env  # then fill in credentials"
check_no_changeme "docker/.env" "${ENV_FILE}"

AGENT_LOCAL="${ORBWEAVER_DIR}/docker/agent.local.yml"
check "docker/agent.local.yml" \
    "${AGENT_LOCAL}" \
    "cp docker/agent.yml docker/agent.local.yml  # then fill in real creds"
check_no_changeme "docker/agent.local.yml" "${AGENT_LOCAL}"

SSH_CONF="$(cd "${ORBWEAVER_DIR}" && cd ../ 2>/dev/null && pwd)/orb/ssh-napalm.conf"
check "orb/ssh-napalm.conf" \
    "${SSH_CONF}" \
    "scp oldmachine:~/projects/netbox/orb/ssh-napalm.conf ${SSH_CONF}"

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
if [[ ${FAIL} -eq 0 ]]; then
    echo "All required secret files are present."
    exit 0
else
    echo "${FAIL} required file(s) missing. See hints above."
    exit 1
fi
