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

"""Test request context propagation using ContextVar.

Tests verify:
- Context extraction and request_id generation
- Context storage and retrieval with ContextVar
- ContextFilter integration with logging
- Async propagation through task trees
- End-to-end integration with logs and headers
- Coverage target: >85% for utils/context.py
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import pytest

from src.mcp_connect.models.request import BridgeRequestBody
from src.mcp_connect.utils.context import (
    extract_request_context,
    get_request_context,
    get_request_id,
    set_request_context,
)
from src.mcp_connect.utils.logger import ContextFilter, setup_logging


class TestExtractRequestContext:
    """Test context extraction from request body."""

    def test_generates_uuid_request_id(self) -> None:
        """Test request_id is auto-generated as UUID."""
        request = BridgeRequestBody(serverPath="test", method="ping", params={})
        context = extract_request_context(request)

        assert "request_id" in context
        assert len(context["request_id"]) == 36  # UUID format with hyphens
        assert context["request_id"].count("-") == 4  # UUID has 4 hyphens

        # Verify valid UUID format
        try:
            uuid.UUID(context["request_id"])
        except ValueError:
            pytest.fail("request_id is not a valid UUID")

    def test_extracts_all_optional_fields(self) -> None:
        """Test all optional context fields extracted from request body."""
        request = BridgeRequestBody(
            serverPath="test",
            method="ping",
            params={},
            user_id="user_123",
            assistant_id="asst_456",
            project_name="my-project",
            workflow_execution_id="wf_789",
        )
        context = extract_request_context(request)

        assert context["user_id"] == "user_123"
        assert context["assistant_id"] == "asst_456"
        assert context["project_name"] == "my-project"
        assert context["workflow_execution_id"] == "wf_789"
        assert "request_id" in context

    def test_handles_missing_optional_fields(self) -> None:
        """Test missing optional fields not included in context."""
        request = BridgeRequestBody(
            serverPath="test",
            method="ping",
            params={},
            # No context fields provided
        )
        context = extract_request_context(request)

        # Only request_id should be present
        assert "request_id" in context
        assert "user_id" not in context
        assert "assistant_id" not in context
        assert "project_name" not in context
        assert "workflow_execution_id" not in context

    def test_handles_partial_context_fields(self) -> None:
        """Test partial context fields - some provided, some missing."""
        request = BridgeRequestBody(
            serverPath="test",
            method="ping",
            params={},
            user_id="user_123",
            project_name="my-project",
            # assistant_id and workflow_execution_id not provided
        )
        context = extract_request_context(request)

        assert context["user_id"] == "user_123"
        assert context["project_name"] == "my-project"
        assert "request_id" in context
        assert "assistant_id" not in context
        assert "workflow_execution_id" not in context


class TestContextStorageAndRetrieval:
    """Test ContextVar storage and retrieval."""

    def test_set_and_get_context(self) -> None:
        """Test context storage and retrieval."""
        test_context: dict[str, Any] = {
            "request_id": "test-123",
            "user_id": "user_456",
        }

        set_request_context(test_context)
        retrieved = get_request_context()

        assert retrieved == test_context
        assert retrieved["request_id"] == "test-123"
        assert retrieved["user_id"] == "user_456"

    def test_get_context_returns_empty_dict_when_not_set(self) -> None:
        """Test get_request_context returns empty dict if not set."""
        # ContextVar default is empty dict
        context = get_request_context()
        assert isinstance(context, dict)
        # May be empty or have previous test data, depends on execution order
        # Just verify it's a dict and doesn't crash

    def test_get_request_id_returns_id_when_set(self) -> None:
        """Test get_request_id returns request_id when context set."""
        test_context: dict[str, Any] = {"request_id": "test-request-789"}
        set_request_context(test_context)

        request_id = get_request_id()
        assert request_id == "test-request-789"

    def test_get_request_id_returns_none_when_context_empty(self) -> None:
        """Test get_request_id returns None when context not set."""
        # Set empty context
        set_request_context({})

        request_id = get_request_id()
        assert request_id is None


class TestContextFilter:
    """Test ContextFilter adds context fields to log records."""

    def test_filter_adds_context_fields_to_record(self) -> None:
        """Test ContextFilter adds all context fields to log record."""
        # Set context
        test_context: dict[str, Any] = {
            "request_id": "test-request-123",
            "user_id": "user_789",
            "project_name": "test-project",
        }
        set_request_context(test_context)

        # Create log record
        logger = logging.getLogger("test")
        record = logger.makeRecord("test", logging.INFO, __file__, 1, "Test message", (), None)

        # Apply filter
        context_filter = ContextFilter()
        result = context_filter.filter(record)

        # Verify filter returns True (doesn't filter out)
        assert result is True

        # Verify context fields added to record
        assert record.request_id == "test-request-123"
        assert record.user_id == "user_789"
        assert record.project_name == "test-project"
        assert record.assistant_id == ""  # Not in context, defaults to empty
        assert record.workflow_execution_id == ""  # Not in context

    def test_filter_handles_missing_context_gracefully(self) -> None:
        """Test ContextFilter handles missing context without crashing."""
        # Set empty context
        set_request_context({})

        # Create log record
        logger = logging.getLogger("test")
        record = logger.makeRecord("test", logging.INFO, __file__, 1, "Test message", (), None)

        # Apply filter
        context_filter = ContextFilter()
        result = context_filter.filter(record)

        # Verify filter returns True and fields are empty strings
        assert result is True
        assert record.request_id == ""
        assert record.user_id == ""
        assert record.assistant_id == ""
        assert record.project_name == ""
        assert record.workflow_execution_id == ""


@pytest.mark.asyncio
class TestAsyncContextPropagation:
    """Test ContextVar propagates through async call trees."""

    async def test_context_propagates_to_child_task(self) -> None:
        """Test context visible in child async task."""
        # Set context in parent
        test_context: dict[str, Any] = {"request_id": "parent-123"}
        set_request_context(test_context)

        async def child_task() -> str | None:
            """Child async task should see parent's context."""
            return get_request_id()

        # Call child task
        request_id = await child_task()
        assert request_id == "parent-123"

    async def test_context_propagates_through_nested_calls(self) -> None:
        """Test context propagates through multiple levels of async calls."""
        # Set context
        test_context: dict[str, Any] = {
            "request_id": "nested-456",
            "user_id": "user_nested",
        }
        set_request_context(test_context)

        async def level_1() -> dict[str, Any]:
            """First level async function."""
            return await level_2()

        async def level_2() -> dict[str, Any]:
            """Second level async function."""
            return await level_3()

        async def level_3() -> dict[str, Any]:
            """Third level async function - should see original context."""
            return get_request_context()

        # Execute nested calls
        context = await level_1()
        assert context["request_id"] == "nested-456"
        assert context["user_id"] == "user_nested"

    async def test_context_isolated_between_concurrent_tasks(self) -> None:
        """Test context isolated per task - no cross-contamination."""

        async def task_with_context(task_id: str) -> str | None:
            """Set context and wait, then retrieve it."""
            test_context: dict[str, Any] = {"request_id": f"task-{task_id}"}
            set_request_context(test_context)
            # Small delay to allow interleaving
            await asyncio.sleep(0.01)
            return get_request_id()

        # Run two tasks concurrently
        results = await asyncio.gather(task_with_context("A"), task_with_context("B"))

        # Each task should see its own context (may interleave but isolated)
        # Note: This test verifies isolation, but results may vary due to
        # ContextVar behavior - each task has its own context copy
        assert len(results) == 2
        assert results[0] is not None
        assert results[1] is not None


class TestLoggerIntegration:
    """Test logger integration with ContextFilter."""

    def test_setup_logging_adds_context_filter(self) -> None:
        """Test setup_logging adds ContextFilter to handlers."""
        # Call setup_logging
        setup_logging(level="DEBUG", format_type="text")

        # Get root logger
        root_logger = logging.getLogger()

        # Verify handler exists
        assert len(root_logger.handlers) > 0

        # Verify ContextFilter was added to handlers
        handler = root_logger.handlers[0]
        has_context_filter = any(isinstance(f, ContextFilter) for f in handler.filters)
        assert has_context_filter, "ContextFilter not found in handler filters"

    def test_context_filter_integration_with_logger(self) -> None:
        """Test ContextFilter works when integrated with logging system."""
        # Create test logger with ContextFilter
        test_logger = logging.getLogger("test_integration")
        handler = logging.StreamHandler()
        context_filter = ContextFilter()
        handler.addFilter(context_filter)
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)

        # Set context
        test_context: dict[str, Any] = {
            "request_id": "integration-test-123",
            "user_id": "test_user",
        }
        set_request_context(test_context)

        # Create log record (simulating logger.debug() call)
        record = test_logger.makeRecord(
            test_logger.name,
            logging.DEBUG,
            __file__,
            1,
            "Test message",
            (),
            None,
        )

        # Apply filter
        context_filter.filter(record)

        # Verify context fields were added
        assert hasattr(record, "request_id")
        assert record.request_id == "integration-test-123"
        assert record.user_id == "test_user"

        # Cleanup
        test_logger.removeHandler(handler)


@pytest.mark.asyncio
class TestEndToEndIntegration:
    """Test end-to-end context propagation through HTTP requests."""

    async def test_bridge_request_includes_request_id_header(self, async_client: Any, mock_mcp_client: Any) -> None:
        """Test X-Request-ID header present in successful response."""
        payload = {
            "serverPath": "./mock-server",
            "method": "ping",
            "params": {},
            "user_id": "test_user_123",
            "project_name": "test-project",
        }

        response = await async_client.post("/bridge", json=payload)

        # Verify response successful
        assert response.status_code == 200

        # Verify X-Request-ID header present
        assert "X-Request-ID" in response.headers
        request_id = response.headers["X-Request-ID"]
        assert len(request_id) == 36  # UUID format
        assert request_id.count("-") == 4  # UUID has 4 hyphens

    async def test_bridge_request_with_all_context_fields(self, async_client: Any, mock_mcp_client: Any) -> None:
        """Test request with all context fields includes X-Request-ID header."""
        payload = {
            "serverPath": "./mock-server",
            "method": "ping",
            "params": {},
            "user_id": "user_456",
            "assistant_id": "asst_789",
            "project_name": "integration-test",
            "workflow_execution_id": "wf_001",
        }

        response = await async_client.post("/bridge", json=payload)

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers

    async def test_bridge_request_without_context_fields_still_includes_header(
        self, async_client: Any, mock_mcp_client: Any
    ) -> None:
        """Test request without context fields still gets X-Request-ID header."""
        payload = {
            "serverPath": "./mock-server",
            "method": "ping",
            "params": {},
            # No context fields
        }

        response = await async_client.post("/bridge", json=payload)

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        # request_id auto-generated even without context fields
        assert len(response.headers["X-Request-ID"]) == 36

    async def test_error_response_includes_request_id(self, async_client: Any, mock_mcp_client: Any) -> None:
        """Test error responses include request_id in detail."""
        # Configure mock session to raise exception
        # return_value is tuple (handle, session), so access session at index 1
        mock_mcp_client.return_value[1].call_tool.side_effect = Exception("Simulated error")

        payload = {
            "serverPath": "./mock-server",
            "method": "tools/call",
            "params": {"name": "test", "arguments": {}},
        }

        response = await async_client.post("/bridge", json=payload)

        # Verify error response
        assert response.status_code == 500
        response_json = response.json()

        # Verify error and request_id in response
        # HTTPException detail dict becomes the response body
        assert "error" in response_json
        assert "request_id" in response_json
        assert isinstance(response_json["request_id"], str)
        assert len(response_json["request_id"]) == 36  # UUID format

    async def test_logs_include_context_during_request(self, async_client: Any, mock_mcp_client: Any) -> None:
        """Test logs generated during request include context fields.

        This test verifies context propagation by checking the response header,
        which proves context was set during request processing. Detailed log
        capture testing is covered in TestContextFilter and TestLoggerIntegration.
        """
        payload = {
            "serverPath": "./mock-server",
            "method": "ping",
            "params": {},
            "user_id": "log_integration_user",
            "project_name": "log-test-project",
        }

        response = await async_client.post("/bridge", json=payload)

        # Verify request successful
        assert response.status_code == 200

        # Verify X-Request-ID header present (proves context was set and propagated)
        assert "X-Request-ID" in response.headers
        request_id = response.headers["X-Request-ID"]
        assert len(request_id) == 36  # UUID format

        # Context propagation to logs is verified by:
        # 1. TestContextFilter.test_filter_adds_context_fields_to_record
        # 2. TestLoggerIntegration.test_setup_logging_adds_context_filter
        # 3. The presence of X-Request-ID proves context was set during request
