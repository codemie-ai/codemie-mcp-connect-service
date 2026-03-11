#!/bin/bash
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
# Build Script for CodeMie MCP Connect Service Docker Image
# ==============================================================================
#
# This script clones required dependencies and builds the Docker image.
#
# Usage:
#   ./build.sh                    # Build with default tag (mcp-connect:latest)
#   ./build.sh my-image:v1.0      # Build with custom tag
#   ./build.sh --no-cache         # Build without Docker cache
#   ./build.sh my-image:v1.0 --no-cache  # Custom tag + no cache
#
# ==============================================================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_SERVERS_DIR="${SCRIPT_DIR}/ai-run-mcp-servers"
MCP_SERVERS_REPO="git@gitbud.epam.com:epm-cdme/ai-run-mcp-servers.git"
MCP_SERVERS_REPO_HTTPS="https://gitbud.epam.com/epm-cdme/ai-run-mcp-servers.git"
DEFAULT_IMAGE_TAG="mcp-connect:latest"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
IMAGE_TAG="${DEFAULT_IMAGE_TAG}"
DOCKER_ARGS=""

for arg in "$@"; do
    case $arg in
        --no-cache)
            DOCKER_ARGS="${DOCKER_ARGS} --no-cache"
            ;;
        --help|-h)
            echo "Usage: $0 [IMAGE_TAG] [--no-cache]"
            echo ""
            echo "Arguments:"
            echo "  IMAGE_TAG    Docker image tag (default: ${DEFAULT_IMAGE_TAG})"
            echo "  --no-cache   Build without Docker cache"
            echo ""
            echo "Examples:"
            echo "  $0                           # Build mcp-connect:latest"
            echo "  $0 my-image:v1.0             # Build with custom tag"
            echo "  $0 --no-cache                # Build without cache"
            echo "  $0 my-image:v1.0 --no-cache  # Custom tag + no cache"
            exit 0
            ;;
        *)
            # If argument doesn't start with --, treat it as image tag
            if [[ ! "$arg" =~ ^-- ]]; then
                IMAGE_TAG="$arg"
            fi
            ;;
    esac
done

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}CodeMie MCP Connect Service - Build${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Step 1: Clone or update ai-run-mcp-servers repository
echo -e "${YELLOW}Step 1: Checking ai-run-mcp-servers dependency...${NC}"

if [ -d "${MCP_SERVERS_DIR}" ]; then
    echo -e "${GREEN}  Found existing ai-run-mcp-servers directory${NC}"

    # Check if it's a git repository
    if [ -d "${MCP_SERVERS_DIR}/.git" ]; then
        echo "  Updating repository..."
        cd "${MCP_SERVERS_DIR}"
        git pull --ff-only || echo -e "${YELLOW}  Warning: Could not update repository (may have local changes)${NC}"
        cd "${SCRIPT_DIR}"
    else
        echo -e "${YELLOW}  Warning: Directory exists but is not a git repository${NC}"
    fi
else
    echo "  Cloning ai-run-mcp-servers repository..."

    # Try SSH first, fall back to HTTPS
    if git clone --depth 1 "${MCP_SERVERS_REPO}" "${MCP_SERVERS_DIR}" 2>/dev/null; then
        echo -e "${GREEN}  Successfully cloned via SSH${NC}"
    elif git clone --depth 1 "${MCP_SERVERS_REPO_HTTPS}" "${MCP_SERVERS_DIR}" 2>/dev/null; then
        echo -e "${GREEN}  Successfully cloned via HTTPS${NC}"
    else
        echo -e "${RED}  Error: Failed to clone ai-run-mcp-servers repository${NC}"
        echo ""
        echo "  Please clone manually:"
        echo "    git clone ${MCP_SERVERS_REPO} ${MCP_SERVERS_DIR}"
        echo "  Or via HTTPS:"
        echo "    git clone ${MCP_SERVERS_REPO_HTTPS} ${MCP_SERVERS_DIR}"
        exit 1
    fi
fi

echo ""

# Step 2: Verify required files exist
echo -e "${YELLOW}Step 2: Verifying build prerequisites...${NC}"

MISSING_FILES=()

if [ ! -f "${SCRIPT_DIR}/Dockerfile" ]; then
    MISSING_FILES+=("Dockerfile")
fi

if [ ! -d "${MCP_SERVERS_DIR}/epm-cdme" ]; then
    MISSING_FILES+=("ai-run-mcp-servers/epm-cdme")
fi

if [ ${#MISSING_FILES[@]} -ne 0 ]; then
    echo -e "${RED}  Error: Missing required files/directories:${NC}"
    for file in "${MISSING_FILES[@]}"; do
        echo -e "${RED}    - ${file}${NC}"
    done
    exit 1
fi

echo -e "${GREEN}  All prerequisites verified${NC}"
echo ""

# Step 3: Build Docker image
echo -e "${YELLOW}Step 3: Building Docker image...${NC}"
echo "  Image tag: ${IMAGE_TAG}"
echo "  Platform: linux/amd64"
if [ -n "${DOCKER_ARGS}" ]; then
    echo "  Additional args:${DOCKER_ARGS}"
fi
echo ""

cd "${SCRIPT_DIR}"
docker build --platform linux/amd64 -t "${IMAGE_TAG}" ${DOCKER_ARGS} .

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Build completed successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Image: ${IMAGE_TAG}"
echo ""
echo "Run the container:"
echo "  docker run -d -p 3000:3000 --name mcp-connect \\"
echo "    -e ACCESS_TOKEN=your-token \\"
echo "    ${IMAGE_TAG}"
