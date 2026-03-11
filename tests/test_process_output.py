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
Tests for process output capture (Story 4.2).

Tests verify stdout/stderr capture, circular buffer limits, error context extraction,
and integration with MCP client manager.
"""

import asyncio
from collections import deque
from unittest.mock import AsyncMock

import pytest

from src.mcp_connect.utils.process import (
    StreamCaptureWrapper,
    capture_stream_output,
    create_output_buffers,
    get_error_context_from_buffers,
)


def test_create_output_buffers():
    """Test buffer creation with correct maxlen."""
    buffers = create_output_buffers()

    assert "stdout" in buffers
    assert "stderr" in buffers
    assert buffers["stdout"].maxlen == 50
    assert buffers["stderr"].maxlen == 50
    assert len(buffers["stdout"]) == 0
    assert len(buffers["stderr"]) == 0


def test_get_error_context_stderr_priority():
    """Test stderr takes priority over stdout."""
    stdout_buffer = deque(["stdout line 1", "stdout line 2"], maxlen=50)
    stderr_buffer = deque(["stderr line 1", "stderr line 2"], maxlen=50)

    context = get_error_context_from_buffers(stdout_buffer, stderr_buffer)
    assert context == "stderr line 1"


def test_get_error_context_stdout_fallback():
    """Test stdout used if stderr empty."""
    stdout_buffer = deque(["stdout line 1"], maxlen=50)
    stderr_buffer = deque(maxlen=50)  # Empty

    context = get_error_context_from_buffers(stdout_buffer, stderr_buffer)
    assert context == "stdout line 1"


def test_get_error_context_empty():
    """Test empty string returned when both buffers empty."""
    stdout_buffer = deque(maxlen=50)
    stderr_buffer = deque(maxlen=50)

    context = get_error_context_from_buffers(stdout_buffer, stderr_buffer)
    assert context == ""


class TestStreamCaptureWrapper:
    """Tests for StreamCaptureWrapper TextIO wrapper."""

    def test_write_single_line(self):
        """Test writing a single line to buffer."""
        buffer = deque(maxlen=50)
        wrapper = StreamCaptureWrapper(buffer, "[Test]")

        result = wrapper.write("test line\n")

        assert result == 10  # Length of written string
        assert len(buffer) == 1
        assert buffer[0] == "test line"

    def test_write_multiple_lines(self):
        """Test writing multiple lines in one call."""
        buffer = deque(maxlen=50)
        wrapper = StreamCaptureWrapper(buffer, "[Test]")

        result = wrapper.write("line1\nline2\nline3\n")

        assert result == 18  # Length of written string
        assert len(buffer) == 3
        assert list(buffer) == ["line1", "line2", "line3"]

    def test_write_empty_string(self):
        """Test writing empty string is a no-op."""
        buffer = deque(maxlen=50)
        wrapper = StreamCaptureWrapper(buffer, "[Test]")

        result = wrapper.write("")

        assert result == 0
        assert len(buffer) == 0

    def test_write_strips_whitespace(self):
        """Test that lines are stripped of surrounding whitespace."""
        buffer = deque(maxlen=50)
        wrapper = StreamCaptureWrapper(buffer, "[Test]")

        wrapper.write("  line with spaces  \n")

        assert len(buffer) == 1
        assert buffer[0] == "line with spaces"

    def test_flush_is_noop(self):
        """Test that flush() doesn't raise exceptions."""
        buffer = deque(maxlen=50)
        wrapper = StreamCaptureWrapper(buffer, "[Test]")

        # Should not raise
        wrapper.flush()


@pytest.mark.asyncio
async def test_capture_stream_output():
    """Test async stream capture into circular buffer."""
    buffer = deque(maxlen=50)

    # Mock StreamReader
    class MockStreamReader:
        def __init__(self, lines):
            self.lines = [line.encode("utf-8") for line in lines]
            self.index = 0

        async def readline(self):
            if self.index >= len(self.lines):
                return b""  # EOF
            line = self.lines[self.index]
            self.index += 1
            return line

    stream = MockStreamReader(["line1\n", "line2\n", "line3\n"])

    await capture_stream_output(stream, buffer, "[Test]")

    assert len(buffer) == 3
    assert list(buffer) == ["line1", "line2", "line3"]


@pytest.mark.asyncio
async def test_capture_stream_output_eof():
    """Test stream capture stops at EOF."""
    buffer = deque(maxlen=50)

    class MockStreamReader:
        async def readline(self):
            return b""  # Immediate EOF

    stream = MockStreamReader()

    await capture_stream_output(stream, buffer, "[Test]")

    assert len(buffer) == 0


@pytest.mark.asyncio
async def test_capture_stream_output_utf8_errors():
    """Test UTF-8 decoding with errors='replace'."""
    buffer = deque(maxlen=50)

    class MockStreamReader:
        def __init__(self):
            self.lines = [
                b"valid line\n",
                b"invalid \xff\xfe bytes\n",  # Invalid UTF-8
            ]
            self.index = 0

        async def readline(self):
            if self.index >= len(self.lines):
                return b""
            line = self.lines[self.index]
            self.index += 1
            return line

    stream = MockStreamReader()

    # Should not raise, uses errors='replace'
    await capture_stream_output(stream, buffer, "[Test]")

    assert len(buffer) == 2
    assert buffer[0] == "valid line"
    # Second line will have replacement characters
    assert "invalid" in buffer[1]


@pytest.mark.asyncio
async def test_buffer_maxlen_enforced():
    """Test circular buffer truncates at maxlen."""
    buffer = deque(maxlen=50)

    # Create 51 lines
    lines = [f"line{i}\n" for i in range(51)]

    class MockStreamReader:
        def __init__(self, lines):
            self.lines = [line.encode("utf-8") for line in lines]
            self.index = 0

        async def readline(self):
            if self.index >= len(self.lines):
                return b""
            line = self.lines[self.index]
            self.index += 1
            return line

    stream = MockStreamReader(lines)
    await capture_stream_output(stream, buffer, "[Test]")

    # Buffer should have last 50 lines (line0 evicted)
    assert len(buffer) == 50
    assert buffer[0] == "line1"  # First line after eviction
    assert buffer[-1] == "line50"


@pytest.mark.asyncio
async def test_capture_stream_output_exception_handling():
    """Test that exceptions during capture are logged but don't crash."""
    buffer = deque(maxlen=50)

    class FailingStreamReader:
        async def readline(self):
            raise RuntimeError("Stream read error")

    stream = FailingStreamReader()

    # Should not raise, catches and logs exception
    await capture_stream_output(stream, buffer, "[Test]")

    # Buffer should be empty since read failed
    assert len(buffer) == 0


@pytest.mark.asyncio
async def test_cleanup_cancels_output_tasks():
    """Test that cleanup() cancels output capture tasks."""
    from src.mcp_connect.client.types import MCPClientHandle

    # Create real async tasks that will be cancelled
    async def long_running_task():
        await asyncio.sleep(100)

    task1 = asyncio.create_task(long_running_task())
    task2 = asyncio.create_task(long_running_task())

    # Give tasks a moment to start
    await asyncio.sleep(0.01)

    # Create handle with tasks
    session_mock = AsyncMock()
    session_mock.__aexit__ = AsyncMock()
    context_mock = AsyncMock()
    context_mock.__aexit__ = AsyncMock()

    handle = MCPClientHandle(
        session=session_mock,
        context=context_mock,
        output_tasks=[task1, task2],
        output_buffers=create_output_buffers(),
    )

    # Verify tasks are not done yet
    assert not task1.done()
    assert not task2.done()

    # Cleanup
    await handle.cleanup()

    # Verify tasks are now done (completed via cancellation)
    assert task1.done()
    assert task2.done()

    # Verify output_tasks list was cleared
    assert handle.output_tasks == []
    assert handle.output_buffers is None
