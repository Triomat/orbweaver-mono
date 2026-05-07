FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

ARG GO_VERSION=1.24.6
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000

# System packages (Python 3.12 already installed in base image)
RUN rm -f /etc/apt/sources.list.d/yarn.list /etc/apt/sources.list.d/yarn-source.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    openssh-client \
    ca-certificates \
    gnupg \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Go
RUN ARCH="$(dpkg --print-architecture)" \
    && GO_ARCH="${ARCH}" \
    && curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz" \
    | tar -C /usr/local -xz
ENV PATH="/usr/local/go/bin:${PATH}"

# just
RUN curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh \
    | bash -s -- --to /usr/local/bin

# Neovim (AppImage approach for bookworm)
RUN curl -fsSL https://github.com/neovim/neovim/releases/download/stable/nvim-linux-x86_64.tar.gz \
    -o /tmp/nvim.tar.gz \
    && tar -xzf /tmp/nvim.tar.gz -C /opt \
    && ln -s /opt/nvim-linux-x86_64/bin/nvim /usr/local/bin/nvim \
    && rm /tmp/nvim.tar.gz

# Non-root user
RUN if ! id -u ${USERNAME} >/dev/null 2>&1; then \
        if ! getent group ${USER_GID} >/dev/null 2>&1; then \
            groupadd --gid ${USER_GID} ${USERNAME}; \
        fi; \
        useradd --uid ${USER_UID} --gid ${USER_GID} -m ${USERNAME}; \
    fi \
    && echo "${USERNAME} ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME}

USER ${USERNAME}
ENV PATH="/home/${USERNAME}/.local/bin:/usr/local/go/bin:${PATH}"
WORKDIR /workspace/orbweaver
