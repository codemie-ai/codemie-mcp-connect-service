# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ==============================================================================
# Multi-stage Dockerfile for MCP Connect Service (Python with Multi-Runtime Support)
# ==============================================================================
#
# This Dockerfile provides a comprehensive runtime environment for MCP Connect:
# - Python 3.12+ (primary runtime for MCP Connect service)
# - Node.js LTS (for Node.js-based MCP servers)
# - Java 11/17/21 (for Java-based MCP servers)
# - Go-based GitHub MCP Server
# - All official MCP servers (stdio, HTTP, SSE transports)
# - Optional ngrok tunnel to expose the HTTP server to the outside world
#
# Build: docker build --platform linux/amd64 -t mcp-connect:latest .
# Run (without ngrok):
#   docker run -d -p 3000:3000 --name mcp-connect \
#       -e ACCESS_TOKEN=your-token \
#       mcp-connect:latest
#
# Run (with ngrok):
#   docker run -d -p 3000:3000 --name mcp-connect \
#       -e ACCESS_TOKEN=your-token \
#       -e NGROK_AUTHTOKEN=your-ngrok-token \
#       mcp-connect:latest
#
# ==============================================================================

# ==============================================================================
# Stage 1: Build GitHub MCP Server (Go)
# ==============================================================================
FROM dhi.io/golang:1.25-alpine3.23-dev AS github-mcp-build
ARG VERSION="dev"
ARG TARGETARCH

WORKDIR /build

# Install git for cloning
RUN --mount=type=cache,target=/var/cache/apk \
    apk add --no-cache git~=2.52

# Clone and build GitHub MCP Server from specific tag
RUN git clone --branch latest-release --depth 1 https://github.com/github/github-mcp-server.git .

# TODO: Remove once github-mcp-server ships with modelcontextprotocol/go-sdk >= v1.4.1
# Remediation for CVE-2026-27896 and CVE-2026-33252 (go-sdk vulnerable versions bundled in github-mcp-server, fixed in v1.4.1)
# Note: v1.4.1 fixes CSRF/Origin-header validation (CVE-2026-33252) in Streamable HTTP transport
RUN --mount=type=cache,target=/go/pkg/mod \
    go get github.com/modelcontextprotocol/go-sdk@v1.4.1 && \
    go mod tidy

# Build with architecture support and optimizations
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOARCH=${TARGETARCH} go build \
    -ldflags="-s -w -X main.version=${VERSION} -X main.commit=$(git rev-parse HEAD) -X main.date=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    -o /bin/github-mcp-server cmd/github-mcp-server/main.go

# ==============================================================================
# Stage 2: Base Image - Multi-Runtime Foundation
# ==============================================================================
FROM python:3.12-slim AS base
ARG TARGETARCH

# hadolint ignore=DL3002
USER root

# Install comprehensive system dependencies
# hadolint ignore=DL3008
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
        # Core utilities
        wget \
        curl \
        jq \
        git \
        build-essential \
        nano \
        mc \
        ca-certificates \
        gnupg \
        # GitHub CLI
        gh \
        # Media processing (for MCP servers)
        ffmpeg \
        exiftool \
        # Fonts for internationalization (browser-based MCP servers)
        fonts-ipafont-gothic \
        fonts-wqy-zenhei \
        fonts-thai-tlwg \
        fonts-kacst-one \
        fonts-freefont-ttf \
        # Browser dependencies (Chromium)
        libxss1 \
        libgtk2.0-0 \
        libnss3 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxkbcommon0 \
        libgbm1 \
        libasound2 \
        chromium \
        chromium-common && \
    apt-get install -y --no-install-recommends --only-upgrade chromium chromium-common && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Node.js LTS (for Node.js-based MCP servers)
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# hadolint ignore=DL3008
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Update npm to latest stable version
RUN npm install -g npm@latest

# TODO: Remove once npm ships with tinyglobby that includes picomatch >= 4.0.4
# Remediation for CVE-2026-33671 (picomatch@4.0.3 nested in npm via tinyglobby)
ARG PICOMATCH_VERSION=4.0.4
RUN npm install -g picomatch@${PICOMATCH_VERSION} \
    && PICOMATCH_SRC="$(npm root -g)/picomatch" \
    && find "$(npm root -g)" -mindepth 2 -name "picomatch" -type d | while read -r dir; do \
           grep -q '"version": "4.0.3"' "$dir/package.json" 2>/dev/null \
           && rm -rf "$dir" \
           && cp -r "$PICOMATCH_SRC" "$dir" \
           || true; \
       done \
    && npm uninstall -g picomatch \
    && npm cache clean --force

# Install Maven
ENV MAVEN_VERSION=3.9.14
ENV MAVEN_HOME=/opt/apache-maven-${MAVEN_VERSION}

RUN curl -Lso "/tmp/apache-maven-${MAVEN_VERSION}-bin.tar.gz" \
    "https://dlcdn.apache.org/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz" && \
    tar xzf "/tmp/apache-maven-${MAVEN_VERSION}-bin.tar.gz" -C /opt && \
    rm "/tmp/apache-maven-${MAVEN_VERSION}-bin.tar.gz"

ENV PATH=${MAVEN_HOME}/bin:${PATH}

# Install JDKs (11, 17, 21) with multi-architecture support
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN ARCH=${TARGETARCH:-$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')} && \
    case ${ARCH} in \
        amd64)  JDK_ARCH="x64"     ;; \
        arm64)  JDK_ARCH="aarch64" ;; \
        *)      printf "Unsupported arch %s\n" "${ARCH}" && exit 1 ;; \
    esac && \
    mkdir -p /usr/lib/jvm && \
    \
    # JDK 11
    curl -Ls "https://github.com/adoptium/temurin11-binaries/releases/download/jdk-11.0.28%2B6/OpenJDK11U-jdk_${JDK_ARCH}_linux_hotspot_11.0.28_6.tar.gz" \
        -o /tmp/OpenJDK11U-jdk.tar.gz && \
    tar -xzf /tmp/OpenJDK11U-jdk.tar.gz -C /usr/lib/jvm && \
    mv /usr/lib/jvm/jdk-11.0.28+6 /usr/lib/jvm/jdk-11 && \
    rm /tmp/OpenJDK11U-jdk.tar.gz && \
    \
    # JDK 17
    curl -Ls "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.16%2B8/OpenJDK17U-jdk_${JDK_ARCH}_linux_hotspot_17.0.16_8.tar.gz" \
        -o /tmp/OpenJDK17U-jdk.tar.gz && \
    tar -xzf /tmp/OpenJDK17U-jdk.tar.gz -C /usr/lib/jvm && \
    mv /usr/lib/jvm/jdk-17.0.16+8 /usr/lib/jvm/jdk-17 && \
    rm /tmp/OpenJDK17U-jdk.tar.gz && \
    \
    # JDK 21
    curl -Ls "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.8%2B9/OpenJDK21U-jdk_${JDK_ARCH}_linux_hotspot_21.0.8_9.tar.gz" \
        -o /tmp/OpenJDK21U-jdk.tar.gz && \
    tar -xzf /tmp/OpenJDK21U-jdk.tar.gz -C /usr/lib/jvm && \
    mv /usr/lib/jvm/jdk-21.0.8+9 /usr/lib/jvm/jdk-21 && \
    rm /tmp/OpenJDK21U-jdk.tar.gz

# ==============================================================================
# Stage 3: MCP Servers Installation
# ==============================================================================
FROM base AS mcp-servers

# Install official MCP servers (Node.js-based)
WORKDIR /codemie
RUN git clone --depth 1 --recursive https://github.com/modelcontextprotocol/servers.git
WORKDIR /codemie/servers
RUN rm -rf src/everything

RUN npm pkg set 'overrides.esbuild'='>=0.27.4' && \
    npm pkg set 'overrides.@isaacs/brace-expansion'='>=5.0.1' && \
    npm pkg set 'overrides.tar'='>=7.5.11' && \
    npm pkg set 'overrides.picomatch'='>=4.0.4' && \
    rm -f package-lock.json
RUN --mount=type=cache,target=/root/.npm \
    npm install && npm run build && npm run link-all

# Install EPAM MCP servers (postgres, puppeteer)
WORKDIR /codemie
COPY ai-run-mcp-servers ./ai-run-mcp-servers

# Build postgres-typescript
WORKDIR /codemie/ai-run-mcp-servers/epm-cdme/postgres-typescript
RUN rm -f package-lock.json
RUN --mount=type=cache,target=/root/.npm \
    npm install && npm run build && npm link

# Build puppeteer-typescript
WORKDIR /codemie/ai-run-mcp-servers/epm-cdme/puppeteer-typescript
RUN rm -f package-lock.json
RUN --mount=type=cache,target=/root/.npm \
    npm install && npm run build && npm link

# Install fetch-mcp
RUN mkdir -p /codemie/additional-tools && \
    git clone --depth 1 https://github.com/zcaceres/fetch-mcp.git /codemie/additional-tools/fetch-mcp
WORKDIR /codemie/additional-tools/fetch-mcp
RUN npm pkg set 'overrides.esbuild'='>=0.27.4' && \
    npm pkg set 'overrides.@isaacs/brace-expansion'='>=5.0.1' && \
    npm pkg set 'overrides.tar'='>=7.5.11' && \
    npm pkg set 'overrides.picomatch'='>=4.0.4' && \
    rm -f package-lock.json
RUN --mount=type=cache,target=/root/.npm \
    npm install

# Copy GitHub MCP Server binary from build stage
COPY --from=github-mcp-build /bin/github-mcp-server /codemie/additional-tools/github-mcp-server/github-mcp-server

# ==============================================================================
# Stage 4: Python Application Build
# ==============================================================================
FROM mcp-servers AS app-builder

# Install Poetry for Python dependency management and configure venv in project directory
RUN pip install --no-cache-dir poetry==2.2.0 && \
    poetry config virtualenvs.in-project true

# Copy Python application dependency manifests and package metadata
WORKDIR /codemie/codemie-mcp-connect
COPY pyproject.toml poetry.lock README.md ./
COPY scripts/ ./scripts/

# Install Python dependencies only (without the package itself for better caching)
RUN --mount=type=cache,target=/root/.cache/pypoetry \
    poetry install --without dev --no-root --no-interaction

# Copy application source code
COPY src/ ./src/

# Install the package itself now that source code is available
RUN --mount=type=cache,target=/root/.cache/pypoetry \
    poetry install --only-root --no-interaction

# ==============================================================================
# Stage 5: Runtime - Final Production Image (with optional ngrok)
# ==============================================================================
FROM mcp-servers AS runtime

# Install uv (fast Python package manager) system-wide
# hadolint ignore=DL4006
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    if [ -f "/root/.local/bin/uv" ]; then \
        mv /root/.local/bin/uv /usr/local/bin/uv; \
        mv /root/.local/bin/uvx /usr/local/bin/uvx; \
    else \
        echo "Warning: uv not found at /root/.local/bin/uv after install"; \
    fi && \
    (rmdir --ignore-fail-on-non-empty /root/.local/bin 2>/dev/null || true) && \
    (rm -rf /root/.local/share/uv 2>/dev/null || true)

# Install ngrok agent via APT (Debian/Bookworm repo)
# hadolint ignore=DL3008
RUN curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
      -o /etc/apt/trusted.gpg.d/ngrok.asc && \
    echo "deb https://ngrok-agent.s3.amazonaws.com bookworm main" \
      > /etc/apt/sources.list.d/ngrok.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends ngrok && \
    echo "Removing vulnerable packages: linux-libc-dev" && \
    apt-get purge -y linux-libc-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create codemie user
RUN groupadd --gid 1001 codemie && \
    useradd --uid 1001 --gid 1001 --shell /bin/bash --create-home codemie

# Copy Python application with virtual environment from app-builder stage
WORKDIR /codemie/codemie-mcp-connect
COPY --from=app-builder /codemie/codemie-mcp-connect/.venv ./.venv
COPY --from=app-builder /codemie/codemie-mcp-connect/src ./src
COPY --from=app-builder /codemie/codemie-mcp-connect/scripts ./scripts
COPY --chown=codemie:codemie pyproject.toml poetry.lock README.md ./

# Copy helper scripts and add to PATH (owned by root, executable by all)
# Using --chown=root:root ensures codemie user cannot modify/delete these scripts
COPY --chown=root:root --chmod=755 create_python_venv.sh /usr/local/bin/create_python_venv.sh
COPY --chown=root:root --chmod=755 run_in_python_venv.sh /usr/local/bin/run_in_python_venv.sh

# Copy startup script that runs Uvicorn + optional ngrok (owned by root)
COPY --chown=root:root --chmod=755 start-with-ngrok.sh /usr/local/bin/start-with-ngrok.sh

# Set permissions for codemie user
RUN chmod -R o+rX /codemie /usr/lib/jvm "${MAVEN_HOME}" /codemie/additional-tools && \
    chmod +x /codemie/additional-tools/github-mcp-server/github-mcp-server && \
    chown -R codemie:codemie /codemie/codemie-mcp-connect

# Switch to codemie user
USER codemie

# Set PATH to include:
# - Python venv binaries
# - uv (system-wide)
# - Maven
# - Helper scripts (in /usr/local/bin)
ENV PATH=/codemie/codemie-mcp-connect/.venv/bin:/usr/local/bin:${MAVEN_HOME}/bin:${PATH}

# Default port (can be overridden via PORT environment variable)
ENV PORT=3000

# Optional reserved ngrok domain, e.g. https://my-app.ngrok.app
# Note: NGROK_AUTHTOKEN is intentionally NOT given a default here.
# If you don't provide it at runtime, ngrok is never started.
ENV NGROK_DOMAIN=""

# Expose port (documentation only)
EXPOSE ${PORT}

# Configure health check using PORT variable
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run FastAPI application with Uvicorn + optional ngrok via startup script
CMD ["start-with-ngrok.sh"]
