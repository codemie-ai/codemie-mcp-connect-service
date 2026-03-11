#!/usr/bin/env bash
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

set -euo pipefail

PORT="${PORT:-3000}"

echo "Starting FastAPI (Uvicorn) on port ${PORT}..."

# Start Uvicorn in the background
uvicorn mcp_connect.main:app --host 0.0.0.0 --port "${PORT}" &
UVICORN_PID=$!

# If NGROK_AUTHTOKEN is not provided or empty, skip ngrok completely
if [[ -z "${NGROK_AUTHTOKEN:-}" ]]; then
  echo "NGROK_AUTHTOKEN is not set, running without ngrok tunnel."
  wait "${UVICORN_PID}"
  exit $?
fi

echo "NGROK_AUTHTOKEN detected, starting ngrok tunnel..."

NGROK_TARGET="http://127.0.0.1:${PORT}"

# Optional reserved domain (e.g. https://my-app.ngrok.app)
NGROK_ARGS=()
if [[ -n "${NGROK_DOMAIN:-}" ]]; then
  # New ngrok CLI uses --url for reserved domains
  NGROK_ARGS+=(--url "${NGROK_DOMAIN}")
fi

# Minimal ngrok config to disable the console UI and use structured logs
NGROK_CONFIG_FILE=/tmp/ngrok.yml
cat > "${NGROK_CONFIG_FILE}" <<'EOF'
version: 3
agent:
  # Disable the full-screen console UI and just emit log lines
  console_ui: false
  # Stream logs to stdout in a simple key=value format
  log: stdout
  log_level: info
  log_format: logfmt
EOF

# ngrok will pick up the authtoken from NGROK_AUTHTOKEN env var
ngrok http "${NGROK_ARGS[@]}" "${NGROK_TARGET}" --config="${NGROK_CONFIG_FILE}" &
NGROK_PID=$!

echo "Uvicorn PID: ${UVICORN_PID}, ngrok PID: ${NGROK_PID}"

terminate() {
  echo "Shutting down Uvicorn and ngrok..."
  kill "${UVICORN_PID}" "${NGROK_PID}" 2>/dev/null || true
}
trap terminate SIGINT SIGTERM

# Wait for either Uvicorn or ngrok to exit
wait -n "${UVICORN_PID}" "${NGROK_PID}"
STATUS=$?
terminate
exit "${STATUS}"
