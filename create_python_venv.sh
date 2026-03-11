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


set -e  # Exit on any error

# Function to display usage
usage() {
    echo "Usage: $0 <absolute_path_to_venv_folder> [absolute_path_to_requirements_file]"
    echo "Example: $0 /home/user/myproject"
    echo "Example: $0 /home/user/myproject /home/user/myproject/requirements.txt"
    exit 1
}

# Check if correct number of arguments provided
if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    echo "Error: Invalid number of arguments"
    usage
fi

VENV_FOLDER="$1"
REQUIREMENTS_FILE="$2"

# Validate that venv path is absolute
if [[ ! "$VENV_FOLDER" = /* ]]; then
    echo "Error: VENV_FOLDER must be an absolute path (starting with /)"
    exit 1
fi

# Validate requirements file path if provided
if [ -n "$REQUIREMENTS_FILE" ]; then
    if [[ ! "$REQUIREMENTS_FILE" = /* ]]; then
        echo "Error: REQUIREMENTS_FILE must be an absolute path (starting with /)"
        exit 1
    fi

    # Check if requirements file exists
    if [ ! -f "$REQUIREMENTS_FILE" ]; then
        echo "Error: Requirements file not found at $REQUIREMENTS_FILE"
        exit 1
    fi
fi

# Create the venv folder if it doesn't exist
if [ ! -d "$VENV_FOLDER" ]; then
    echo "Creating directory: $VENV_FOLDER"
    mkdir -p "$VENV_FOLDER"
fi

# Navigate to the specified folder
cd "$VENV_FOLDER"

echo "Creating virtual environment in: $VENV_FOLDER"

echo "Using uv to create virtual environment..."
uv venv

# Activate the virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Check if activation was successful
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Error: Failed to activate virtual environment"
    exit 1
fi

echo "Virtual environment activated: $VIRTUAL_ENV"

# Install dependencies from requirements file if provided
if [ -n "$REQUIREMENTS_FILE" ]; then
    echo "Installing dependencies from: $REQUIREMENTS_FILE"
    echo "Using uv to install dependencies..."
    uv pip install -r "$REQUIREMENTS_FILE"
    echo "Dependencies installed successfully!"
else
    echo "No requirements file provided - skipping package installation"
fi

echo "Virtual environment setup completed successfully!"
echo "Virtual environment location: $VENV_FOLDER/.venv"
echo "To activate manually: source $VENV_FOLDER/.venv/bin/activate"