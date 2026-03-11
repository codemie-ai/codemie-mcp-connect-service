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

"""Authentication middleware and dependencies for MCP Connect server."""

from __future__ import annotations

import os
import secrets
from typing import Any

from fastapi import Header, HTTPException, status

from ..models.request import BridgeRequestBody
from ..utils.context import extract_request_context, set_request_context


async def verify_token(authorization: str | None = Header(default=None)) -> None:
    """Validate Authorization header when ACCESS_TOKEN is configured.

    The dependency enforces Bearer token authentication on protected endpoints.
    Authentication is disabled automatically when the ACCESS_TOKEN environment
    variable is not set (development mode).

    Args:
        authorization: Value of the incoming Authorization header, if present.

    Raises:
        HTTPException: Raised with 401 status code whenever authentication fails.
    """

    expected_token = os.getenv("ACCESS_TOKEN")
    if not expected_token:
        # Authentication disabled; allow request to proceed.
        return

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Missing Authorization header"},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid Authorization header format"},
        )

    token = authorization[len("Bearer ") :]

    if not secrets.compare_digest(token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid access token"},
        )


async def setup_request_context(
    request_body: BridgeRequestBody,
) -> dict[str, Any]:
    """Extract and set request context from incoming request.

    This dependency extracts context fields (user_id, assistant_id, project_name,
    workflow_execution_id) from the request body, generates a unique request_id,
    and stores the context in a ContextVar for automatic propagation through
    all async operations in the request lifecycle.

    Args:
        request_body: Incoming bridge request with optional context fields

    Returns:
        Context dictionary with request_id and optional fields.
        Can be used in endpoint if needed.

    Example:
        >>> @app.post("/bridge")
        >>> async def bridge(
        >>>     request: BridgeRequestBody,
        >>>     context: dict = Depends(setup_request_context)
        >>> ):
        >>>     # Context automatically available in all logs
        >>>     logger.info("Processing request")  # Includes request_id, user_id, etc.
    """
    context = extract_request_context(request_body)
    set_request_context(context)
    return context


__all__ = ["verify_token", "setup_request_context"]
