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

# Lightweight Python runtime for executing custom Python scripts
# Optimized for minimal image size
FROM python:3.12-slim

# Version pinning for reproducible builds
#ARG GIT_VERSION=1:2.47.3-0+deb13u1
#ARG CURL_VERSION=8.14.1-2
#ARG GNUPG_VERSION=2.4.7-21
#ARG NODE_VERSION=22.20.0-1nodesource1
#ARG CLAUDE_CODE_VERSION=2.0.22
#ARG NPM_VERSION=10.9.3
#ARG PROCPS_VERSION=2:4.0.4-9

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/tmp/venv/bin:/usr/local/bin:${PATH}"

# Install system dependencies, create user, and set up directories in a single optimized layer
# This minimizes image size by:
# 1. Combining all operations in one RUN command
# 2. Using --no-install-recommends to avoid unnecessary packages
# 3. Cleaning up all package manager caches and temporary files in the same layer
# 4. Pinning versions for reproducible builds
# hadolint ignore=DL3008,DL3016
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        git \
        gnupg \
        procps \
    && apt-get install -y --no-install-recommends --only-upgrade openssl libssl3t64 openssl-provider-legacy && \
    curl -fsSL https://deb.nodesource.com/setup_22.x -o /tmp/setup_node.sh && \
    bash /tmp/setup_node.sh && \
    apt-get install -y --no-install-recommends nodejs && \
    # TODO: workaround for npm self-upgrade bug: NodeSource Node 22 ships with npm@10.9.7
    # whose @npmcli/arborist lacks eager require of 'promise-retry', causing MODULE_NOT_FOUND
    # when upgrading directly to npm@11.12.0. Intermediate step to 10.9.8 (which has a working
    # arborist for self-upgrade) resolves this. Fixed upstream in arborist@8.0.5 (npm@11.12.1+).
    # Remove the @10.9.8 line once npm ships with arborist>=8.0.5 bundled.
    npm install -g npm@10.9.8 && \
    npm install -g npm && \
    npm install -g @anthropic-ai/claude-code && \
    rm /tmp/setup_node.sh && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* \
           /var/cache/apt/archives/* \
           /root/.npm \
           /tmp/* \
           /var/tmp/* && \
    groupadd --gid 1001 codemie && \
    useradd --uid 1001 --gid 1001 --shell /bin/bash --create-home codemie && \
    mkdir -p /tmp/venv && \
    chown -R codemie:codemie /tmp/venv

# Set working directory
WORKDIR /home/codemie

# Switch to codemie user before installing dependencies
USER codemie

# Copy requirements file with proper ownership
COPY --chown=codemie:codemie requirements.txt .

# Create virtual environment and install dependencies in a single layer
# Using --no-cache-dir to prevent caching and reduce image size
RUN python -m venv /tmp/venv && \
    /tmp/venv/bin/pip install --no-cache-dir -r requirements.txt && \
    rm -rf ~/.cache/pip ~/.local/share/pip
