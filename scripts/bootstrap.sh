#!/usr/bin/env bash
# bootstrap.sh — idempotent dev environment setup for orbweaver on Ubuntu 22.04/24.04
# Usage: bash scripts/bootstrap.sh
# Safe to run multiple times — skips steps that are already done.

set -euo pipefail

ORBWEAVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NETBOX_DISCOVERY_DIR="$(cd "${ORBWEAVER_DIR}/../../../netbox-discovery" 2>/dev/null || echo "")"
GO_VERSION="1.24.6"
GO_INSTALL_DIR="/usr/local/go"
JUST_BIN="${HOME}/.local/bin/just"

# ── helpers ──────────────────────────────────────────────────────────────────

info()  { echo "  [INFO]  $*"; }
ok()    { echo "  [ OK ]  $*"; }
warn()  { echo "  [WARN]  $*"; }
die()   { echo "  [FAIL]  $*" >&2; exit 1; }

need_sudo() {
    if [[ $EUID -ne 0 ]]; then
        sudo "$@"
    else
        "$@"
    fi
}

# ── 1. System packages ────────────────────────────────────────────────────────

info "Checking system packages..."

PKGS=()
for pkg in python3.12 python3.12-venv python3.12-dev git curl gcc make; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        PKGS+=("$pkg")
    fi
done

if [[ ${#PKGS[@]} -gt 0 ]]; then
    info "Installing missing packages: ${PKGS[*]}"
    need_sudo apt-get update -qq
    need_sudo apt-get install -y "${PKGS[@]}"
    ok "System packages installed."
else
    ok "System packages already present."
fi

# ── 2. just ──────────────────────────────────────────────────────────────────

info "Checking just..."

if command -v just &>/dev/null; then
    ok "just already installed: $(just --version)"
elif [[ -x "${JUST_BIN}" ]]; then
    ok "just already installed at ${JUST_BIN}: $(${JUST_BIN} --version)"
else
    info "Installing just to ~/.local/bin ..."
    mkdir -p "${HOME}/.local/bin"
    curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh \
        | bash -s -- --to "${HOME}/.local/bin"
    ok "just installed: $(${JUST_BIN} --version)"
    if [[ ":${PATH}:" != *":${HOME}/.local/bin:"* ]]; then
        warn "Add ~/.local/bin to your PATH. Add to ~/.bashrc or ~/.zshrc:"
        warn "  export PATH=\"\${HOME}/.local/bin:\${PATH}\""
    fi
fi

# ── 3. Go ────────────────────────────────────────────────────────────────────

info "Checking Go ${GO_VERSION}..."

CURRENT_GO=""
if [[ -x "${GO_INSTALL_DIR}/bin/go" ]]; then
    CURRENT_GO="$("${GO_INSTALL_DIR}/bin/go" version 2>/dev/null | awk '{print $3}' | sed 's/go//')"
fi

if [[ "${CURRENT_GO}" == "${GO_VERSION}" ]]; then
    ok "Go ${GO_VERSION} already installed."
else
    info "Installing Go ${GO_VERSION}..."
    ARCH="$(dpkg --print-architecture)"
    case "${ARCH}" in
        amd64) GO_ARCH="amd64" ;;
        arm64) GO_ARCH="arm64" ;;
        *) die "Unsupported architecture: ${ARCH}" ;;
    esac
    GO_TAR="go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"
    GO_URL="https://go.dev/dl/${GO_TAR}"
    TMP="$(mktemp -d)"
    curl -fsSL "${GO_URL}" -o "${TMP}/${GO_TAR}"
    need_sudo rm -rf "${GO_INSTALL_DIR}"
    need_sudo tar -C /usr/local -xzf "${TMP}/${GO_TAR}"
    rm -rf "${TMP}"
    ok "Go ${GO_VERSION} installed at ${GO_INSTALL_DIR}."
    if [[ ":${PATH}:" != *":/usr/local/go/bin:"* ]]; then
        warn "Add Go to your PATH. Add to ~/.bashrc or ~/.zshrc:"
        warn "  export PATH=\"/usr/local/go/bin:\${PATH}\""
    fi
fi

# ── 4. netbox-discovery clone ─────────────────────────────────────────────────

NETBOX_DISCOVERY_TARGET="$(cd "${ORBWEAVER_DIR}" && cd ../ 2>/dev/null && pwd)/netbox-discovery"

info "Checking netbox-discovery at ${NETBOX_DISCOVERY_TARGET}..."

if [[ -d "${NETBOX_DISCOVERY_TARGET}/.git" ]]; then
    ok "netbox-discovery already cloned."
else
    warn "netbox-discovery not found at ${NETBOX_DISCOVERY_TARGET}."
    warn "Clone it manually:"
    warn "  git clone git@github.com:Triomat/netbox-discovery.git ${NETBOX_DISCOVERY_TARGET}"
fi

# ── 5. Python venv + dependencies ────────────────────────────────────────────

info "Setting up Python venv and installing dependencies..."

cd "${ORBWEAVER_DIR}"

JUST_CMD="just"
if ! command -v just &>/dev/null && [[ -x "${JUST_BIN}" ]]; then
    JUST_CMD="${JUST_BIN}"
fi

if command -v "${JUST_CMD}" &>/dev/null || [[ -x "${JUST_CMD}" ]]; then
    "${JUST_CMD}" install
    ok "Python dependencies installed via 'just install'."
else
    warn "just not found in PATH. Run manually after adding it to PATH:"
    warn "  just install"
fi

# ── 6. docker/.env check ─────────────────────────────────────────────────────

info "Checking docker/.env..."

if [[ -f "${ORBWEAVER_DIR}/docker/.env" ]]; then
    ok "docker/.env exists."
else
    warn "docker/.env is missing."
    warn "Create it from the template:"
    warn "  cp docker/.env.example docker/.env"
    warn "  # then fill in DIODE_HOST, DIODE_CLIENT_SECRET, NETBOX_TOKEN, etc."
fi

# ── 7. docker/agent.local.yml check ──────────────────────────────────────────

info "Checking docker/agent.local.yml..."

if [[ -f "${ORBWEAVER_DIR}/docker/agent.local.yml" ]]; then
    ok "docker/agent.local.yml exists."
else
    warn "docker/agent.local.yml is missing."
    warn "Create it from the template:"
    warn "  cp docker/agent.yml docker/agent.local.yml"
    warn "  # then fill in real Diode credentials and device hostnames/passwords."
fi

# ── 8. ssh-napalm.conf check ─────────────────────────────────────────────────

info "Checking ssh-napalm.conf..."

SSH_CONF_PATH="$(cd "${ORBWEAVER_DIR}" && cd ../ 2>/dev/null && pwd)/orb/ssh-napalm.conf"

if [[ -f "${SSH_CONF_PATH}" ]]; then
    ok "ssh-napalm.conf found at ${SSH_CONF_PATH}."
else
    warn "ssh-napalm.conf not found at ${SSH_CONF_PATH}."
    warn "Copy it from your old machine:"
    warn "  mkdir -p $(dirname "${SSH_CONF_PATH}")"
    warn "  scp oldmachine:~/projects/netbox/orb/ssh-napalm.conf ${SSH_CONF_PATH}"
fi

# ── done ─────────────────────────────────────────────────────────────────────

echo ""
echo "Bootstrap complete."
echo "Run 'just check-secrets' to verify all required secret files are in place."
echo "Run 'just test' to confirm the dev environment is working."
