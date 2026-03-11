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

"""
Process Output Capture for MCP stdio Transports

This module provides utilities for capturing stdout and stderr from MCP server
subprocesses, enabling comprehensive error diagnostics.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Deque

from .logger import get_logger

logger = get_logger(__name__)

# Type alias for process output buffers
ProcessOutputBuffers = dict[str, Deque[str]]


class StreamCaptureWrapper:
    """
    TextIO wrapper that captures lines to a deque buffer.

    Used to capture stderr from MCP subprocess by passing to stdio_client's errlog parameter.
    """

    def __init__(self, buffer: Deque[str], prefix: str) -> None:
        """
        Initialize stream capture wrapper.

        Args:
            buffer: Circular buffer to store captured lines
            prefix: Prefix for log messages (e.g., "[MCP Child Process <client_id>]")
        """
        self.buffer = buffer
        self.prefix = prefix

    def write(self, text: str) -> int:
        """
        Write text to buffer and log it.

        Args:
            text: Text to write (may contain multiple lines)

        Returns:
            Number of characters written
        """
        if not text:
            return 0

        # Split into lines and process each non-empty line
        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if line:
                self.buffer.append(line)
                logger.debug(f"{self.prefix} {line}")

        return len(text)

    def flush(self) -> None:
        """Flush the stream (no-op for our purposes)."""
        pass

    # Additional TextIO protocol methods (minimal implementation)
    def writable(self) -> bool:
        """Return True indicating this stream is writable."""
        return True

    def fileno(self) -> int:
        """
        Return file descriptor number.

        Raises OSError as this is a pseudo-file without an actual file descriptor.
        This is standard behavior for file-like objects without underlying OS file.
        """
        raise OSError("StreamCaptureWrapper does not have a file descriptor")

    def close(self) -> None:
        """Close the stream (no-op for our purposes)."""
        pass

    def __enter__(self) -> StreamCaptureWrapper:
        """Support context manager protocol."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Support context manager protocol."""
        pass


def create_output_buffers() -> ProcessOutputBuffers:
    """
    Create circular buffers for stdout and stderr (max 50 lines each).

    Returns:
        Dict with 'stdout' and 'stderr' deque buffers (maxlen=50)
    """
    return {"stdout": deque(maxlen=50), "stderr": deque(maxlen=50)}


async def capture_stream_output(stream: asyncio.StreamReader, buffer: Deque[str], prefix: str) -> None:
    """
    Capture stream lines into circular buffer with prefix.

    Reads asynchronously until EOF or stream closed.
    Logs each line at DEBUG level.
    Handles decoding errors gracefully.

    Args:
        stream: Async stream reader (stdout or stderr)
        buffer: Circular buffer (deque) for storing lines
        prefix: Log prefix (e.g., "[MCP Child Process <client_id>]")
    """
    try:
        while True:
            line_bytes = await stream.readline()
            if not line_bytes:
                break  # EOF

            # Decode with error handling
            line = line_bytes.decode("utf-8", errors="replace").rstrip("\n")

            # Append to circular buffer (auto-truncates at maxlen)
            buffer.append(line)

            # Log at DEBUG level with prefix
            logger.debug(f"{prefix} {line}")

    except Exception as e:
        logger.error(f"Error capturing stream: {e}", exc_info=True)


def get_error_context_from_buffers(stdout_buffer: Deque[str], stderr_buffer: Deque[str]) -> str:
    """
    Extract first line from stderr (or stdout if stderr empty) for error messages.

    Returns:
        First stderr line if present, else first stdout line, else empty string.
    """
    if stderr_buffer:
        return stderr_buffer[0]
    if stdout_buffer:
        return stdout_buffer[0]
    return ""
