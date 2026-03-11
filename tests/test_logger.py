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

"""Unit tests for structured logging utilities.

Tests verify JSON and text format output, log level filtering, environment variable
configuration, and case-insensitive handling of configuration values.
"""

import json
import logging
from io import StringIO

import pytest

from src.mcp_connect.utils.logger import get_logger, setup_logging


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration before each test to ensure clean state."""
    # Clear all handlers and reset root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.WARNING)  # Reset to default
    yield
    # Cleanup after test
    root_logger.handlers.clear()


def test_default_configuration(monkeypatch):
    """Test default values (LOG_LEVEL=info, LOG_FORMAT=json) when env vars not set."""
    # Clear environment variables
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)

    setup_logging()

    # Verify root logger configured with default level
    root_logger = logging.getLogger()
    assert root_logger.level == logging.INFO

    # Verify handler exists
    assert len(root_logger.handlers) == 1


def test_case_insensitive_configuration():
    """Test case-insensitive level and format values."""
    # Should not raise exceptions with various case combinations
    setup_logging(level="INFO", format_type="JSON")
    logging.getLogger().handlers.clear()

    setup_logging(level="info", format_type="json")
    logging.getLogger().handlers.clear()

    setup_logging(level="Info", format_type="Json")
    logging.getLogger().handlers.clear()

    setup_logging(level="DEBUG", format_type="TEXT")
    logging.getLogger().handlers.clear()


def test_json_format_output():
    """Test JSON format produces correct log structure with expected fields."""
    # Capture output directly to string stream
    stream = StringIO()

    # Setup logging manually to use our stream
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    handler = logging.StreamHandler(stream)
    from pythonjsonlogger.json import JsonFormatter

    formatter = JsonFormatter(
        "%(levelname)s %(name)s %(message)s",
        rename_fields={"levelname": "level", "name": "logger_name"},
        timestamp=True,
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    logger = logging.getLogger("test.module")
    logger.info("Test message")

    # Parse JSON output
    output = stream.getvalue().strip()
    log_json = json.loads(output)

    # Verify JSON structure
    assert log_json["level"] == "INFO"
    assert log_json["logger_name"] == "test.module"
    assert log_json["message"] == "Test message"
    assert "timestamp" in log_json


def test_json_format_output_to_stream():
    """Test JSON formatter produces valid JSON output to stream."""
    # Create string stream to capture output
    stream = StringIO()
    handler = logging.StreamHandler(stream)

    # Setup JSON formatter
    from pythonjsonlogger.json import JsonFormatter

    formatter = JsonFormatter(
        "%(levelname)s %(name)s %(message)s",
        rename_fields={"levelname": "level", "name": "logger_name"},
        timestamp=True,
    )
    handler.setFormatter(formatter)

    # Configure logger with stream handler
    logger = logging.getLogger("test.json.stream")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Emit log message
    logger.info("JSON test message", extra={"request_id": "123"})

    # Get output and parse JSON
    output = stream.getvalue().strip()
    log_json = json.loads(output)

    # Verify JSON structure
    assert log_json["level"] == "INFO"
    assert log_json["logger_name"] == "test.json.stream"
    assert log_json["message"] == "JSON test message"
    assert log_json["request_id"] == "123"
    assert "timestamp" in log_json

    # Cleanup
    logger.removeHandler(handler)


def test_text_format_output():
    """Test text format produces human-readable output."""
    # Capture output directly to string stream
    stream = StringIO()

    # Setup logging manually to use our stream
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    handler = logging.StreamHandler(stream)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    logger = logging.getLogger("test.module")
    logger.info("Test message")

    # Get output
    output = stream.getvalue().strip()

    # Verify text format (should contain timestamp, level, name, message)
    assert "INFO" in output
    assert "test.module" in output
    assert "Test message" in output
    assert "]" in output  # Closing bracket from [timestamp]


def test_text_format_output_to_stream():
    """Test text formatter produces human-readable output to stream."""
    # Create string stream to capture output
    stream = StringIO()
    handler = logging.StreamHandler(stream)

    # Setup text formatter
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)

    # Configure logger with stream handler
    logger = logging.getLogger("test.text.stream")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Emit log message
    logger.info("Text test message")

    # Get output
    output = stream.getvalue().strip()

    # Verify text format (should contain timestamp, level, name, message)
    assert "INFO" in output
    assert "test.text.stream" in output
    assert "Text test message" in output
    assert "]" in output  # Closing bracket from [timestamp]

    # Cleanup
    logger.removeHandler(handler)


def test_log_level_filtering():
    """Test that log level filtering works correctly."""
    # Capture output directly to string stream
    stream = StringIO()

    # Setup logging with INFO level
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    handler = logging.StreamHandler(stream)
    from pythonjsonlogger.json import JsonFormatter

    formatter = JsonFormatter(
        "%(levelname)s %(message)s",
        rename_fields={"levelname": "level"},
        timestamp=True,
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    logger = logging.getLogger("test.module")
    logger.debug("Debug message - should not appear")
    logger.info("Info message - should appear")

    # Parse output - should only have one line (info message)
    output = stream.getvalue().strip()
    lines = output.split("\n")
    assert len(lines) == 1

    log_json = json.loads(lines[0])
    assert log_json["level"] == "INFO"
    assert log_json["message"] == "Info message - should appear"


def test_debug_level_includes_all_messages():
    """Test that debug level includes both debug and info messages."""
    # Capture output directly to string stream
    stream = StringIO()

    # Setup logging with DEBUG level
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()

    handler = logging.StreamHandler(stream)
    from pythonjsonlogger.json import JsonFormatter

    formatter = JsonFormatter(
        "%(levelname)s %(message)s",
        rename_fields={"levelname": "level"},
        timestamp=True,
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    logger = logging.getLogger("test.module")
    logger.debug("Debug message")
    logger.info("Info message")

    # Parse output - should have two lines
    output = stream.getvalue().strip()
    lines = output.split("\n")
    assert len(lines) == 2

    log1 = json.loads(lines[0])
    log2 = json.loads(lines[1])
    assert log1["level"] == "DEBUG"
    assert log2["level"] == "INFO"


def test_get_logger_returns_configured_instance():
    """Test get_logger() returns logger instances that inherit root configuration."""
    setup_logging(level="warning", format_type="json")

    logger = get_logger("test.module")

    # Verify logger has correct name
    assert logger.name == "test.module"

    # Verify logger inherits root configuration (effective level should be WARNING)
    assert logger.getEffectiveLevel() == logging.WARNING


def test_environment_variable_configuration(monkeypatch):
    """Test configuration from LOG_LEVEL and LOG_FORMAT environment variables."""
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("LOG_FORMAT", "text")

    setup_logging()

    root_logger = logging.getLogger()
    assert root_logger.level == logging.DEBUG


def test_parameter_overrides_environment(monkeypatch):
    """Test that function parameters override environment variables."""
    monkeypatch.setenv("LOG_LEVEL", "info")
    monkeypatch.setenv("LOG_FORMAT", "json")

    # Override with function parameters
    setup_logging(level="warning", format_type="text")

    root_logger = logging.getLogger()
    assert root_logger.level == logging.WARNING


def test_multiple_loggers_share_configuration():
    """Test that multiple loggers share the same root configuration."""
    setup_logging(level="error", format_type="json")

    logger1 = get_logger("module1")
    logger2 = get_logger("module2")

    # Both should inherit the same effective level
    assert logger1.getEffectiveLevel() == logging.ERROR
    assert logger2.getEffectiveLevel() == logging.ERROR


def test_logger_with_extra_fields():
    """Test logging with extra fields (context data)."""
    # Capture output directly to string stream
    stream = StringIO()

    # Setup logging manually
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    handler = logging.StreamHandler(stream)
    from pythonjsonlogger.json import JsonFormatter

    formatter = JsonFormatter(
        "%(levelname)s %(message)s",
        rename_fields={"levelname": "level"},
        timestamp=True,
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    logger = logging.getLogger("test.module")
    logger.info("Operation completed", extra={"user_id": "123", "duration_ms": 456})

    # Parse JSON output
    output = stream.getvalue().strip()
    log_json = json.loads(output)

    # Verify extra fields are in JSON output
    assert log_json["user_id"] == "123"
    assert log_json["duration_ms"] == 456
    assert log_json["message"] == "Operation completed"


def test_all_log_levels_supported():
    """Test that all standard log levels are supported."""
    # Test each level can be configured
    for level in ["debug", "info", "warning", "error", "critical"]:
        setup_logging(level=level, format_type="json")
        root_logger = logging.getLogger()
        expected_level = getattr(logging, level.upper())
        assert root_logger.level == expected_level
        root_logger.handlers.clear()


def test_no_duplicate_handlers():
    """Test that calling setup_logging() multiple times doesn't create duplicate handlers."""
    setup_logging(level="info", format_type="json")
    setup_logging(level="debug", format_type="text")

    root_logger = logging.getLogger()

    # Should only have one handler (previous cleared)
    assert len(root_logger.handlers) == 1


def test_json_formatter_timestamp_field():
    """Test that JSON formatter includes timestamp field."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)

    from pythonjsonlogger.json import JsonFormatter

    formatter = JsonFormatter(
        "%(levelname)s %(message)s",
        timestamp=True,
    )
    handler.setFormatter(formatter)

    logger = logging.getLogger("test.timestamp")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    logger.info("Timestamp test")

    output = stream.getvalue().strip()
    log_json = json.loads(output)

    # Verify timestamp field exists
    assert "timestamp" in log_json

    # Cleanup
    logger.removeHandler(handler)
