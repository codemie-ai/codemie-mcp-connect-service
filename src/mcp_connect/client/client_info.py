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

"""MCP client identity configuration.

The client name sent to MCP servers during handshake is controlled by the
MCP_CLIENT_NAME environment variable (default: "mcp-bridge").
"""

from __future__ import annotations

import os

from mcp.types import Implementation


def get_client_info() -> Implementation:
    """Return the Implementation identity sent to MCP servers during session init."""
    name = os.getenv("MCP_CLIENT_NAME", "mcp-bridge")
    return Implementation(name=name, version="1.0.0")


def apply_user_agent_header(headers: dict[str, str] | None) -> dict[str, str]:
    """Return a new headers dict with User-Agent set from MCP_CLIENT_NAME.

    Any existing header matching "user-agent" case-insensitively is removed
    first so the env-var-derived value always wins with no duplicate key.
    """
    merged = {key: value for key, value in (headers or {}).items() if key.lower() != "user-agent"}
    merged["User-Agent"] = get_client_info().name
    return merged
