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

"""Unit and integration tests for enhanced error response handling (Story 4.5).

Tests error detail extraction, error response formatting, debug mode behavior,
request_id integration, and security (no sensitive data in responses).
"""

import asyncio
import os
from unittest.mock import patch

from pydantic import BaseModel, Field, ValidationError

from src.mcp_connect.server.routes import format_error_response
from src.mcp_connect.utils.errors import extract_error_details, extract_root_cause_message, get_stacktrace_string


class TestExtractErrorDetails:
    """Test error detail extraction from various exception types (AC #2)."""

    def test_extract_error_details_oserror_with_errno_syscall(self):
        """Extract errno and syscall from OSError."""
        err = OSError(111, "Connection refused")
        err.syscall = "connect"

        details = extract_error_details(err)

        assert details["errno"] == 111
        assert details["strerror"] == "Connection refused"
        assert details["syscall"] == "connect"

    def test_extract_error_details_oserror_with_filename(self):
        """Extract filename from file-related OSError."""
        err = OSError(2, "No such file or directory")
        err.filename = "/path/to/missing/file"
        err.syscall = "open"

        details = extract_error_details(err)

        assert details["errno"] == 2
        assert details["filename"] == "/path/to/missing/file"
        assert details["syscall"] == "open"

    def test_extract_error_details_oserror_with_address_port(self):
        """Extract address and port from socket OSError."""
        # Socket errors often store (host, port) in args[1]
        err = OSError(111, "Connection refused")
        err.args = (111, ("localhost", 3000))
        err.syscall = "connect"

        details = extract_error_details(err)

        assert details["address"] == "localhost"
        assert details["port"] == 3000
        assert details["syscall"] == "connect"

    def test_extract_error_details_connection_error(self):
        """ConnectionError is a subclass of OSError, should extract same details."""
        err = ConnectionError(111, "Connection refused")
        err.errno = 111
        err.syscall = "connect"

        details = extract_error_details(err)

        assert details["errno"] == 111
        assert details["syscall"] == "connect"

    def test_extract_error_details_timeout_error(self):
        """asyncio.TimeoutError has no built-in context, return empty dict."""
        err = asyncio.TimeoutError()

        details = extract_error_details(err)

        assert details == {}

    def test_extract_error_details_pydantic_validation_error(self):
        """Extract field location and message from Pydantic ValidationError."""

        class TestModel(BaseModel):
            age: int = Field(gt=0)

        # Create validation error by passing invalid data
        try:
            TestModel(age=-5)
        except ValidationError as exc:
            details = extract_error_details(exc)

            assert "field" in details
            assert "age" in details["field"]
            assert "message" in details
            assert "type" in details
            assert details["type"] == "greater_than"

    def test_extract_error_details_pydantic_nested_field_error(self):
        """Extract nested field location from Pydantic ValidationError."""

        class Address(BaseModel):
            street: str
            city: str

        class User(BaseModel):
            name: str
            address: Address

        try:
            User(name="John", address={"street": "Main St"})  # Missing city
        except ValidationError as exc:
            details = extract_error_details(exc)

            assert "field" in details
            assert "address.city" in details["field"]
            assert "message" in details

    def test_extract_error_details_generic_exception(self):
        """Generic exceptions return empty dict (no extractable details)."""
        err = ValueError("Some error")

        details = extract_error_details(err)

        assert details == {}

    def test_extract_error_details_runtime_error(self):
        """RuntimeError returns empty dict (no special attributes)."""
        err = RuntimeError("Something went wrong")

        details = extract_error_details(err)

        assert details == {}


class TestGetStacktraceString:
    """Test stack trace capture for debug mode (AC #5)."""

    def test_get_stacktrace_string_with_exception(self):
        """Capture stack trace when called within exception handler."""
        try:
            raise ValueError("test error message")
        except ValueError:
            trace = get_stacktrace_string()

            assert "Traceback (most recent call last)" in trace
            assert "ValueError: test error message" in trace
            assert "test_error_responses.py" in trace

    def test_get_stacktrace_string_nested_exception(self):
        """Capture stack trace for nested exceptions."""

        def inner_function():
            raise RuntimeError("inner error")

        def outer_function():
            inner_function()

        try:
            outer_function()
        except RuntimeError:
            trace = get_stacktrace_string()

            assert "RuntimeError: inner error" in trace
            assert "inner_function" in trace
            assert "outer_function" in trace

    def test_get_stacktrace_string_no_exception(self):
        """Return placeholder when called outside exception handler."""
        trace = get_stacktrace_string()

        assert "No traceback available" in trace


class TestExtractRootCauseMessage:
    """Test root cause extraction from exceptions, including nested ExceptionGroups."""

    def test_extract_root_cause_message_regular_exception(self):
        """Extract message from regular exception."""
        err = ValueError("test error")
        message = extract_root_cause_message(err)
        assert message == "ValueError: test error"

    def test_extract_root_cause_message_connection_error(self):
        """Extract message from ConnectionError."""
        err = ConnectionError("Connection refused")
        message = extract_root_cause_message(err)
        assert message == "ConnectionError: Connection refused"

    def test_extract_root_cause_message_exception_without_message(self):
        """Extract type name when exception has no message."""
        err = RuntimeError()
        message = extract_root_cause_message(err)
        assert message == "RuntimeError"

    def test_extract_root_cause_message_exception_group_single_exception(self):
        """Extract root cause from ExceptionGroup with single nested exception."""
        inner_error = ConnectionError("All connection attempts failed")
        group = BaseExceptionGroup("task errors", [inner_error])

        message = extract_root_cause_message(group)

        assert message == "ConnectionError: All connection attempts failed"

    def test_extract_root_cause_message_nested_exception_groups(self):
        """Extract root cause from deeply nested ExceptionGroups."""
        # Create nested structure: ExceptionGroup -> ExceptionGroup -> actual error
        actual_error = OSError("Connection refused")
        inner_group = BaseExceptionGroup("inner group", [actual_error])
        outer_group = BaseExceptionGroup("outer group", [inner_group])

        message = extract_root_cause_message(outer_group)

        assert message == "OSError: Connection refused"

    def test_extract_root_cause_message_exception_group_multiple_exceptions(self):
        """Extract first exception when ExceptionGroup contains multiple exceptions."""
        error1 = ValueError("first error")
        error2 = RuntimeError("second error")
        group = BaseExceptionGroup("multiple errors", [error1, error2])

        message = extract_root_cause_message(group)

        # Should extract the first exception
        assert message == "ValueError: first error"

    def test_extract_root_cause_message_httpx_connect_error_in_group(self):
        """Extract httpx.ConnectError from ExceptionGroup (real-world scenario)."""
        # Simulate the actual error structure from the logs
        try:
            import httpx

            inner_error = httpx.ConnectError("All connection attempts failed")
            group = BaseExceptionGroup("unhandled errors in a TaskGroup (1 sub-exception)", [inner_error])

            message = extract_root_cause_message(group)

            assert "ConnectError" in message
            assert "All connection attempts failed" in message
        except ImportError:
            # Skip if httpx not available in test environment
            pass


class TestFormatErrorResponse:
    """Test error response formatting with context integration (AC #1, #4, #5)."""

    def test_format_error_response_with_details(self):
        """Include details object when error has extractable details."""
        err = OSError(111, "Connection refused")
        err.errno = 111
        err.syscall = "connect"

        response = format_error_response(err, "Connection failed")

        assert response["error"] == "Connection failed"
        assert "details" in response
        assert response["details"]["errno"] == 111
        assert response["details"]["syscall"] == "connect"

    def test_format_error_response_without_details(self):
        """Omit details object when error has no extractable details."""
        err = ValueError("generic error")

        response = format_error_response(err, "Operation failed")

        assert response["error"] == "Operation failed"
        assert "details" not in response

    @patch("src.mcp_connect.server.routes.get_request_context")
    def test_format_error_response_with_request_id(self, mock_get_context):
        """Include request_id when context is available (AC #4)."""
        mock_get_context.return_value = {"request_id": "test-uuid-1234"}

        err = RuntimeError("test error")
        response = format_error_response(err, "Test error")

        assert response["request_id"] == "test-uuid-1234"

    @patch("src.mcp_connect.server.routes.get_request_context")
    def test_format_error_response_without_request_id(self, mock_get_context):
        """Gracefully handle missing context (no request_id field)."""
        mock_get_context.return_value = {}

        err = RuntimeError("test error")
        response = format_error_response(err, "Test error")

        assert "request_id" not in response

    @patch("src.mcp_connect.server.routes.get_request_context")
    def test_format_error_response_context_none(self, mock_get_context):
        """Gracefully handle None context."""
        mock_get_context.return_value = None

        err = RuntimeError("test error")
        response = format_error_response(err, "Test error")

        assert "request_id" not in response

    def test_format_error_response_debug_mode_includes_stacktrace(self):
        """Include stacktrace field when LOG_LEVEL=debug (AC #5)."""
        with patch.dict(os.environ, {"LOG_LEVEL": "debug"}):
            try:
                raise ValueError("debug test error")
            except ValueError as err:
                response = format_error_response(err, "Debug error")

                assert "stacktrace" in response
                assert "ValueError: debug test error" in response["stacktrace"]
                assert "Traceback" in response["stacktrace"]

    def test_format_error_response_production_mode_omits_stacktrace(self):
        """Omit stacktrace field when LOG_LEVEL != debug (AC #5)."""
        for level in ["info", "warning", "error"]:
            with patch.dict(os.environ, {"LOG_LEVEL": level}):
                try:
                    raise ValueError("production test error")
                except ValueError as err:
                    response = format_error_response(err, "Production error")

                    assert "stacktrace" not in response

    def test_format_error_response_complete_structure(self):
        """Test complete error response with all fields (AC #1)."""
        with patch.dict(os.environ, {"LOG_LEVEL": "debug"}):
            with patch("src.mcp_connect.server.routes.get_request_context") as mock_context:
                mock_context.return_value = {"request_id": "complete-test-uuid"}

                try:
                    err = OSError(111, "Connection refused")
                    err.errno = 111
                    err.syscall = "connect"
                    err.args = (111, ("localhost", 5000))
                    raise err
                except OSError as exc:
                    response = format_error_response(exc, "Connection error")

                    # Verify all fields present
                    assert "Connection error" in response["error"]
                    assert "details" in response
                    assert response["details"]["errno"] == 111
                    assert response["details"]["address"] == "localhost"
                    assert response["details"]["port"] == 5000
                    assert response["request_id"] == "complete-test-uuid"
                    assert "stacktrace" in response

    def test_format_error_response_with_exception_group(self):
        """Test that format_error_response extracts root cause from ExceptionGroup."""
        with patch("src.mcp_connect.server.routes.get_request_context") as mock_context:
            mock_context.return_value = {"request_id": "exception-group-test"}

            inner_error = ConnectionError("All connection attempts failed")
            group = BaseExceptionGroup("unhandled errors in a TaskGroup (1 sub-exception)", [inner_error])

            response = format_error_response(group, "Failed to execute MCP request")

            # Should include the root cause in the error message
            assert "Failed to execute MCP request" in response["error"]
            assert "ConnectionError: All connection attempts failed" in response["error"]
            assert response["request_id"] == "exception-group-test"


class TestErrorResponseSecurity:
    """Test that sensitive data is NOT included in error responses (AC #6)."""

    @patch("src.mcp_connect.server.routes.get_request_context")
    def test_no_environment_variables_in_error_response(self, mock_get_context):
        """Verify env variables not exposed in error response."""
        mock_get_context.return_value = {
            "request_id": "security-test",
            "env": {"SECRET_KEY": "sensitive-value", "DB_PASSWORD": "password123"},
        }

        err = RuntimeError("Error with env context")
        response = format_error_response(err, "Operation failed")

        # Response should not contain env data
        response_str = str(response)
        assert "SECRET_KEY" not in response_str
        assert "sensitive-value" not in response_str
        assert "DB_PASSWORD" not in response_str
        assert "password123" not in response_str

    @patch("src.mcp_connect.server.routes.get_request_context")
    def test_no_headers_in_error_response(self, mock_get_context):
        """Verify headers not exposed in error response."""
        mock_get_context.return_value = {
            "request_id": "security-test",
            "headers": {"Authorization": "Bearer secret-token"},
        }

        err = RuntimeError("Error with headers context")
        response = format_error_response(err, "Operation failed")

        # Response should not contain header data
        response_str = str(response)
        assert "Authorization" not in response_str
        assert "Bearer" not in response_str
        assert "secret-token" not in response_str

    def test_error_message_safe_for_external_consumption(self):
        """Verify error messages don't contain internal paths in production."""
        with patch.dict(os.environ, {"LOG_LEVEL": "info"}):  # Production mode
            err = FileNotFoundError("/internal/system/path/secret.txt")

            response = format_error_response(err, "File operation failed")

            # In production mode, stacktrace (which might contain paths) is omitted
            assert "stacktrace" not in response
            # Base message is safe (provided by caller)
            assert response["error"] == "File operation failed"


class TestErrorResponseExamples:
    """Test example error response formats from story (AC #7)."""

    @patch("src.mcp_connect.server.routes.get_request_context")
    def test_connection_refused_error_format(self, mock_get_context):
        """Verify connection refused error format matches example."""
        mock_get_context.return_value = {"request_id": "conn-test-uuid"}

        err = OSError(111, "Connection refused")
        err.errno = 111
        err.syscall = "connect"
        err.args = (111, ("localhost", 3000))

        response = format_error_response(err, "Connection refused to localhost:3000")

        assert response["error"] == "Connection refused to localhost:3000"
        assert response["details"]["errno"] == 111
        assert response["details"]["syscall"] == "connect"
        assert response["details"]["address"] == "localhost"
        assert response["details"]["port"] == 3000
        assert response["request_id"] == "conn-test-uuid"

    @patch("src.mcp_connect.server.routes.get_request_context")
    def test_validation_error_format(self, mock_get_context):
        """Verify validation error format matches example."""
        mock_get_context.return_value = {"request_id": "validation-test-uuid"}

        class TransportModel(BaseModel):
            transport: str = Field(pattern="^(stdio|http|https)$")

        try:
            TransportModel(transport="invalid")
        except ValidationError as exc:
            response = format_error_response(exc, "Validation error")

            assert response["error"] == "Validation error"
            assert "details" in response
            assert "field" in response["details"]
            assert "transport" in response["details"]["field"]
            assert response["request_id"] == "validation-test-uuid"


class TestGetLogLevel:
    """Test LOG_LEVEL environment variable reading."""

    def test_get_log_level_default(self):
        """Default log level is 'info' when LOG_LEVEL not set."""
        from src.mcp_connect.utils.logger import get_log_level

        with patch.dict(os.environ, {}, clear=True):
            # Remove LOG_LEVEL if set
            os.environ.pop("LOG_LEVEL", None)
            level = get_log_level()

            assert level == "info"

    def test_get_log_level_debug(self):
        """Return 'debug' when LOG_LEVEL=debug."""
        from src.mcp_connect.utils.logger import get_log_level

        with patch.dict(os.environ, {"LOG_LEVEL": "debug"}):
            level = get_log_level()

            assert level == "debug"

    def test_get_log_level_uppercase(self):
        """Handle uppercase LOG_LEVEL values (normalize to lowercase)."""
        from src.mcp_connect.utils.logger import get_log_level

        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            level = get_log_level()

            assert level == "debug"

    def test_get_log_level_mixed_case(self):
        """Handle mixed case LOG_LEVEL values."""
        from src.mcp_connect.utils.logger import get_log_level

        with patch.dict(os.environ, {"LOG_LEVEL": "Error"}):
            level = get_log_level()

            assert level == "error"
