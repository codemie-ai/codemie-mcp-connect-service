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

"""Structured logging utilities for MCP Connect service.

This module provides structured JSON and text logging with configurable format and level.
Uses python-json-logger for production-ready JSON logging compatible with log aggregation
systems (ELK, Splunk, CloudWatch).

Environment Variables:
    LOG_LEVEL: Log level (debug, info, warning, error, critical). Default: info
    LOG_FORMAT: Format type (json, text). Default: json

Usage:
    # At application startup (e.g., in main.py)
    from .utils.logger import setup_logging
    setup_logging()

    # In any module
    from .utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Operation successful", extra={"user_id": "123"})
"""

import logging
import os

from pythonjsonlogger.json import JsonFormatter


class ContextFilter(logging.Filter):
    """Filter that adds request context fields to log records.

    Reads context from ContextVar and adds as record attributes for formatters.
    Context fields default to empty string if not set (graceful degradation).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Add context fields to log record.

        Args:
            record: Log record to enhance with context fields

        Returns:
            True (never filters out records)
        """
        # Import here to avoid circular dependency during module initialization
        from .context import get_request_context

        context = get_request_context()

        # Add context fields as record attributes (default to empty string)
        record.request_id = context.get("request_id", "")
        record.user_id = context.get("user_id", "")
        record.assistant_id = context.get("assistant_id", "")
        record.project_name = context.get("project_name", "")
        record.workflow_execution_id = context.get("workflow_execution_id", "")

        return True  # Don't filter out


def setup_logging(level: str | None = None, format_type: str | None = None) -> None:
    """Initialize root logger with specified level and format.

    Configures the root logger with either JSON (production) or text (development) format.
    Reads configuration from environment variables if parameters not provided.

    Args:
        level: Log level (debug, info, warning, error, critical).
               Defaults to LOG_LEVEL env var or "info".
        format_type: Format type (json, text).
                     Defaults to LOG_FORMAT env var or "json".

    Example:
        >>> # Use environment defaults
        >>> setup_logging()
        >>> # Override with specific values
        >>> setup_logging(level="debug", format_type="text")
    """
    # Read from environment with defaults
    log_level_str = (level or os.getenv("LOG_LEVEL") or "info").upper()
    log_format = (format_type or os.getenv("LOG_FORMAT") or "text").lower()

    # Map string level to logging constant
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Create console handler outputting to stdout
    handler = logging.StreamHandler()
    handler.setLevel(log_level)

    # Configure formatter based on format type
    if log_format == "json":
        # JSON formatter with ISO 8601 timestamp and context fields
        # Using python-json-logger v4.0+ API
        formatter: logging.Formatter = JsonFormatter(
            "%(levelname)s %(name)s %(message)s %(request_id)s %(user_id)s "
            "%(assistant_id)s %(project_name)s %(workflow_execution_id)s",
            rename_fields={"levelname": "level", "name": "logger_name"},
            timestamp=True,  # Adds ISO 8601 timestamp field
        )
    else:
        # Text formatter for development with context fields
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s "
            "[request_id=%(request_id)s user_id=%(user_id)s "
            "project=%(project_name)s workflow_execution_id=%(workflow_execution_id)s]: %(message)s ",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    handler.setFormatter(formatter)

    # Add context filter to inject context fields into log records
    context_filter = ContextFilter()
    handler.addFilter(context_filter)

    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get logger instance with specified name.

    Returns a logger that inherits the root logger configuration set by setup_logging().
    Use __name__ as the logger name to get module-qualified logging.

    Args:
        name: Logger name (typically __name__ for module-level logger)

    Returns:
        Configured logger instance inheriting root logger settings

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Service started")
        >>> logger.error("Failed to connect", extra={"host": "localhost", "port": 5432})
    """
    return logging.getLogger(name)


def get_log_level() -> str:
    """Get current log level from environment.

    Reads LOG_LEVEL environment variable and returns normalized lowercase level.
    Used to determine if debug features (like stack traces) should be enabled.

    Returns:
        Current log level string (debug, info, warning, error, critical)
        Default: "info" if LOG_LEVEL not set

    Example:
        >>> level = get_log_level()
        >>> if level == "debug":
        ...     # Include debug information in response
        ...     pass
    """
    return os.getenv("LOG_LEVEL", "info").lower()
