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

FROM dhi.io/python:3.12.14-debian13-dev

ARG LIBCAIRO2_VERSION=1.18.4-1+b1
ARG LIBRAQM0_VERSION=0.10.2-1
ARG PIP_VERSION=26.0
ARG SIMPLE_DECK_VERSION=6.1.1
ARG INSTALL_SIMPLE_DECK=false

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:/usr/local/bin:${PATH}"

# libcairo2 is required by CairoSVG/simple-deck.
# libraqm0 provides complex text layout support for Pillow.
#
# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        "libcairo2=${LIBCAIRO2_VERSION}" \
        "libraqm0=${LIBRAQM0_VERSION}" && \
    apt-get clean && \
    rm -rf \
        /var/lib/apt/lists/* \
        /var/cache/apt/archives/* \
        /tmp/* \
        /var/tmp/* && \
    mkdir -p /home/codemie && \
    chown -R 1001:1001 /home/codemie

COPY requirements.txt /tmp/requirements.txt

# Create venv as root so /opt/venv is read-only for unprivileged user (1001:1001) by default.
# Install dependencies, check environment consistency, and clean up temporary files in a single layer.
RUN /usr/bin/python3.12 -m venv /opt/venv && \
    /opt/venv/bin/python -m pip install \
        --no-cache-dir \
        --upgrade \
        "pip==${PIP_VERSION}" && \
    /opt/venv/bin/python -m pip install \
        --no-cache-dir \
        --requirement /tmp/requirements.txt && \
    if [ "${INSTALL_SIMPLE_DECK}" = "true" ]; then \
        /opt/venv/bin/python -m pip install \
            --no-cache-dir \
            "simple-deck==${SIMPLE_DECK_VERSION}"; \
    fi && \
    /opt/venv/bin/python -m pip check && \
    rm -rf \
        /tmp/* \
        /var/tmp/* \
        /root/.cache

WORKDIR /home/codemie

USER 1001:1001
