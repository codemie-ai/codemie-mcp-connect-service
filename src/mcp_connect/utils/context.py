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

"""Request context management using contextvars for async-safe propagation.

This module provides request-scoped context storage using Python's contextvars
for automatic propagation through async call trees. Context includes request_id
(auto-generated UUID) and optional fields from the request body.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

from ..models.request import BridgeRequestBody
from .logger import get_logger

logger = get_logger(__name__)

# Global context variable for request-scoped data
# Automatically propagates through async tasks, isolated per request
request_context: ContextVar[dict[str, Any]] = ContextVar("request_context", default={})


def extract_request_context(request_body: BridgeRequestBody) -> dict[str, Any]:
    """Extract context fields from request body and generate request_id.

    Args:
        request_body: Incoming bridge request with optional context fields

    Returns:
        Dictionary with:
        - request_id: Auto-generated UUID (always present)
        - user_id, assistant_id, project_name, workflow_execution_id: Optional from request

    Example:
        >>> request = BridgeRequestBody(serverPath="test", method="ping", params={})
        >>> context = extract_request_context(request)
        >>> assert 'request_id' in context
        >>> assert len(context['request_id']) == 36  # UUID format
    """
    # Generate unique request_id for tracing
    context: dict[str, Any] = {
        "request_id": str(uuid.uuid4()),
    }

    # Extract optional context fields from request body
    if request_body.user_id:
        context["user_id"] = request_body.user_id
    if request_body.assistant_id:
        context["assistant_id"] = request_body.assistant_id
    if request_body.project_name:
        context["project_name"] = request_body.project_name
    if request_body.workflow_execution_id:
        context["workflow_execution_id"] = request_body.workflow_execution_id

    logger.debug(f"Extracted request context with request_id={context['request_id']}, fields={list(context.keys())}")

    return context


def set_request_context(context: dict[str, Any]) -> None:
    """Store request context in ContextVar for current async task tree.

    Args:
        context: Context dictionary with request_id and optional fields

    Note:
        Context automatically propagates to all child async tasks.
        Each request has isolated context (no cross-contamination).
    """
    request_context.set(context)
    logger.debug(f"Set request context with {len(context)} fields")


def get_request_context() -> dict[str, Any]:
    """Retrieve current request context from ContextVar.

    Returns:
        Context dictionary with request_id and optional fields.
        Returns empty dict if context not set (outside request scope).

    Example:
        >>> context = get_request_context()
        >>> request_id = context.get('request_id', '')
    """
    return request_context.get()


def get_request_id() -> str | None:
    """Helper to get just request_id from context.

    Returns:
        Request ID string if context is set, None otherwise.
        Useful for adding X-Request-ID headers and error responses.

    Example:
        >>> request_id = get_request_id()
        >>> if request_id:
        >>>     response.headers['X-Request-ID'] = request_id
    """
    context = request_context.get()
    return context.get("request_id") if context else None
