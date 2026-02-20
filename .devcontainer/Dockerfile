FROM debian:bookworm-slim

ARG GO_VERSION=1.24.6
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000

# System packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-venv \
        python3.11-dev \
        python3-pip \
        git \
        curl \
        wget \
        gcc \
        make \
        openssh-client \
        ca-certificates \
        gnupg \
        sudo \
    && rm -rf /var/lib/apt/lists/*

# Python 3.12 from deadsnakes PPA equivalent for Debian bookworm
# bookworm ships Python 3.11; add 3.12 via backports or build
# Use python3.11 as python3 fallback; override with 3.12 if needed
RUN curl -fsSL https://www.python.org/ftp/python/3.12.9/Python-3.12.9.tar.xz -o /tmp/python.tar.xz \
    && apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libssl-dev \
        libffi-dev \
        zlib1g-dev \
        libbz2-dev \
        libreadline-dev \
        libsqlite3-dev \
        libncurses5-dev \
        libgdbm-dev \
        liblzma-dev \
    && tar -xf /tmp/python.tar.xz -C /tmp \
    && cd /tmp/Python-3.12.9 \
    && ./configure --enable-optimizations --prefix=/usr/local \
    && make -j"$(nproc)" \
    && make altinstall \
    && rm -rf /tmp/python.tar.xz /tmp/Python-3.12.9 \
    && rm -rf /var/lib/apt/lists/*

# Make python3.12 the default python3
RUN update-alternatives --install /usr/bin/python3 python3 /usr/local/bin/python3.12 10 \
    && update-alternatives --install /usr/bin/python python /usr/local/bin/python3.12 10

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
RUN groupadd --gid ${USER_GID} ${USERNAME} \
    && useradd --uid ${USER_UID} --gid ${USER_GID} -m ${USERNAME} \
    && echo "${USERNAME} ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME}

USER ${USERNAME}
ENV PATH="/home/${USERNAME}/.local/bin:/usr/local/go/bin:${PATH}"
WORKDIR /workspace/orbweaver
