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

"""Request models for MCP Connect endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BridgeRequestBody(BaseModel):
    """Request body schema for POST /bridge endpoint."""

    model_config = ConfigDict(extra="forbid")

    # Required fields
    serverPath: str = Field(..., description="MCP server command or URL")
    method: str = Field(..., description="MCP protocol method name")
    params: Any = Field(..., description="Parameters for the MCP method")

    # Optional configuration fields
    args: list[str] | None = Field(None, description="CLI arguments for stdio transport")
    env: dict[str, Any] | None = Field(None, description="Environment variables for the MCP process")
    mcp_headers: dict[str, str] | None = Field(None, description="HTTP headers for remote MCP servers")
    request_headers: dict[str, str] | None = Field(None, description="Headers available for $headers substitution")
    http_transport_type: str | None = Field(None, description="Preferred HTTP transport (streamable-http or sse)")
    single_usage: bool = Field(False, description="Bypass client cache when true")

    # Context fields for logging/observability
    user_id: str | None = Field(None, description="Optional user identifier for logging")
    assistant_id: str | None = Field(None, description="Optional assistant identifier for logging")
    project_name: str | None = Field(None, description="Optional project name for context propagation")
    workflow_execution_id: str | None = Field(None, description="Workflow execution identifier for tracing")

    @field_validator("env", mode="before")
    @classmethod
    def convert_env_values_to_strings(cls, v: dict[str, Any] | None) -> dict[str, str] | None:
        """
        Convert all environment variable values to strings.

        Unix/Linux environment variables must be strings. This validator accepts
        any JSON type (bool, int, float, null) and converts them to strings:
        - true -> "true", false -> "false"
        - 123 -> "123", 45.67 -> "45.67"
        - null -> ""

        Args:
            v: Environment variables dictionary with any JSON values

        Returns:
            Dictionary with all values converted to strings, or None if input is None
        """
        if v is None:
            return None

        return {key: str(value) if value is not None else "" for key, value in v.items()}
