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


# Function to display usage
usage() {
    echo "Usage: $0 <absolute_path_to_venv_folder> [python_script_and_arguments...]"
    echo "Example: $0 /home/user/myproject script.py arg1 arg2"
    echo "Example: $0 /home/user/myproject -c \"print('Hello World')\""
    exit 1
}

# Check if at least one argument is provided
if [ $# -lt 1 ]; then
    echo "Error: At least one argument required"
    usage
fi

VENV_FOLDER="$1"
shift  # Remove the first argument, leaving the rest for python

# Validate that path is absolute
if [[ ! "$VENV_FOLDER" = /* ]]; then
    echo "Error: VENV_FOLDER must be an absolute path (starting with /)"
    exit 1
fi

# Construct path to virtual environment
VENV_PATH="$VENV_FOLDER/.venv"

# Check if virtual environment exists
if [ ! -f "$VENV_PATH/bin/activate" ]; then
    echo "Error: Virtual environment not found at $VENV_PATH"
    echo "Make sure you've created the virtual environment first using create_python_venv.sh"
    exit 1
fi

# Check if the venv folder exists
if [ ! -d "$VENV_FOLDER" ]; then
    echo "Error: Specified folder does not exist: $VENV_FOLDER"
    exit 1
fi

# Activate the virtual environment
source "$VENV_PATH/bin/activate"

# Check if activation was successful
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Error: Failed to activate virtual environment"
    exit 1
fi

# Process arguments to expand environment variables
processed_args=()
for arg in "$@"; do
    # Check if envsubst is available, otherwise use eval
    if command -v envsubst >/dev/null 2>&1; then
        # Use envsubst to safely expand environment variables
        expanded_arg=$(echo "$arg" | envsubst)
    else
        # Fallback to eval with proper quoting
        expanded_arg=$(eval echo "\"$arg\"")
    fi

    processed_args+=("$expanded_arg")
done

# Run python with processed arguments
python "${processed_args[@]}"
