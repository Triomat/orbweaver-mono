# orbweaver — Dev Environment Setup

Estimated time: ~15 minutes on a fresh Ubuntu 22.04 or 24.04 machine.

---

## Prerequisites

- Ubuntu 22.04 or 24.04 (amd64 or arm64)
- Internet access for package downloads
- SSH access to your old machine (for secrets transport)
- Git + an SSH key with access to `Triomat/orbweaver` on GitHub

---

## Quick Start

### 1. Clone the repo

```bash
git clone git@github.com:Triomat/orbweaver.git ~/projects/netbox/orbweaver
cd ~/projects/netbox/orbweaver
```

### 2. Run bootstrap

This installs system packages, Go, `just`, and Python deps. Safe to re-run.

```bash
bash scripts/bootstrap.sh
```

Reload your shell if bootstrap warns about PATH (Go or `just` added to PATH):

```bash
source ~/.bashrc   # or ~/.zshrc
```

### 3. Transfer secrets from your old machine

Three files need to be copied manually. The bootstrap script will warn about any that are missing.

```bash
# docker/.env — Diode + NetBox credentials
scp oldmachine:~/projects/netbox/orbweaver/docker/.env \
    ~/projects/netbox/orbweaver/docker/.env

# docker/agent.local.yml — orb-agent config with real credentials
scp oldmachine:~/projects/netbox/orbweaver/docker/agent.local.yml \
    ~/projects/netbox/orbweaver/docker/agent.local.yml

# ssh-napalm.conf — SSH proxy config for NAPALM device access
mkdir -p ~/projects/netbox/orb
scp oldmachine:~/projects/netbox/orb/ssh-napalm.conf ~/projects/netbox/orb/ssh-napalm.conf
```

> If you're setting up from scratch (no old machine), see the template files:
> - `docker/.env.example` → copy to `docker/.env` and fill in values
> - `docker/agent.yml` → copy to `docker/agent.local.yml` and fill in values

```bash
just init-env          # creates docker/.env from template
just init-agent-local  # creates docker/agent.local.yml from template
```

### 4. Verify secrets

```bash
just check-secrets
```

All three items should show `[ OK ]`. Fix any `[MISS]` entries before continuing.

### 5. Run tests

```bash
just test
```

All tests should pass on a properly configured machine.

---

## Day-to-Day Workflows

| Command | What it does |
|---|---|
| `just install` | (Re-)install Python deps into `.venv` |
| `just test` | Run all Python tests |
| `just lint` | Run ruff on all code |
| `just orbweaver-up` | Start device-discovery container (standalone) |
| `just orbweaver-up-agent` | Start orb-agent container (uses `agent.local.yml`) |
| `just orbweaver-down` | Stop all orbweaver containers |
| `just orbweaver-logs` | Stream logs from standalone |
| `just orbweaver-push-policy` | POST `policy-example.yaml` to running orbweaver |
| `just check-secrets` | Verify all required secret files are present |
| `just check-imports` | Verify all new module imports resolve |

---

## VS Code / Neovim

### VS Code (recommended)

Open the multi-root workspace — this sets up the Python interpreter, ruff formatter, and extension recommendations for both repos:

```bash
just setup-editor
# or
code orbweaver.code-workspace
```

### Devcontainer (optional)

A devcontainer is provided for fully isolated development. It includes Python 3.12, Go 1.24.6, `just`, and Neovim.

1. Install the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
2. Open the repo in VS Code
3. Command palette → **Dev Containers: Reopen in Container**
4. Wait for the container to build and `just install` to run

> The devcontainer mounts `../../netbox-discovery` and `../../orb` — ensure those exist on your host before opening the container.

---

## Pre-commit Hooks (optional but recommended)

```bash
just install-hooks
```

This installs gitleaks (secret scanning), ruff (lint + format), and standard file hygiene checks. Hooks run automatically on `git commit`.

---

## Repo Layout

```
orbweaver/
├── device-discovery/        ← Python package: NAPALM collectors + Diode bridge
├── docker/                  ← Docker Compose stack + agent config templates
│   ├── .env.example         ← Credential template (commit this)
│   ├── .env                 ← Real creds (gitignored — never commit)
│   ├── agent.yml            ← Sanitized agent config template (committed)
│   └── agent.local.yml      ← Real agent config (gitignored — never commit)
├── scripts/
│   ├── bootstrap.sh         ← Idempotent setup for fresh Ubuntu machine
│   └── setup-secrets.sh     ← Checks required secret files exist
├── .devcontainer/           ← VS Code devcontainer config
├── Justfile                 ← All common recipes
└── SETUP.md                 ← This file
```

---

## Secret Files Reference

| File | Gitignored | Contains |
|---|---|---|
| `docker/.env` | Yes | `DIODE_CLIENT_SECRET`, `NETBOX_TOKEN`, server IPs |
| `docker/agent.local.yml` | Yes | Diode creds, device IPs, device passwords |
| `../../orb/ssh-napalm.conf` | External | SSH ProxyJump / StrictHostKeyChecking config |

> **Never commit these files.** `.gitignore` blocks them, but be careful with `git add -f`.

---

## Troubleshooting

**`just: command not found`**
Add `~/.local/bin` to your PATH: `export PATH="$HOME/.local/bin:$PATH"`

**`go: command not found`**
Add Go to your PATH: `export PATH="/usr/local/go/bin:$PATH"`

**`docker/.env: No such file`**
Run `just init-env` then fill in the values.

**Container fails to start with `agent.local.yml` missing**
Run `just init-agent-local` then fill in real credentials.

**Tests fail with import errors**
Run `just install` to reinstall deps. If the issue persists, check that `netbox-discovery` is cloned at `../../netbox-discovery`.
