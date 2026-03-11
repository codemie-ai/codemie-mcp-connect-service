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

"""Tests for MCPClientHandle error handling and edge cases."""

import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_connect.client.types import MCPClientHandle


@pytest.mark.asyncio
async def test_cleanup_handles_session_timeout():
    """Test cleanup handles session exit timeout."""
    mock_session = MagicMock()
    # Session exit times out
    mock_session.__aexit__ = AsyncMock(side_effect=asyncio.TimeoutError())

    mock_context = MagicMock()
    mock_context.__aexit__ = AsyncMock()

    handle = MCPClientHandle(session=mock_session, context=mock_context)

    # Should complete without raising
    await handle.cleanup()

    # Session exit should have been attempted
    mock_session.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_handles_session_cancelled():
    """Test cleanup handles session exit cancellation."""
    mock_session = MagicMock()
    # Session exit cancelled
    mock_session.__aexit__ = AsyncMock(side_effect=asyncio.CancelledError())

    mock_context = MagicMock()
    mock_context.__aexit__ = AsyncMock()

    handle = MCPClientHandle(session=mock_session, context=mock_context)

    # Should complete without raising
    await handle.cleanup()

    # Session exit should have been attempted
    mock_session.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_handles_session_runtime_error():
    """Test cleanup handles session RuntimeError."""
    mock_session = MagicMock()
    # Session exit raises RuntimeError
    mock_session.__aexit__ = AsyncMock(side_effect=RuntimeError("Session error"))

    mock_context = MagicMock()
    mock_context.__aexit__ = AsyncMock()

    handle = MCPClientHandle(session=mock_session, context=mock_context)

    # Should complete without raising
    await handle.cleanup()

    # Session exit should have been attempted
    mock_session.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_handles_session_oserror():
    """Test cleanup handles session OSError."""
    mock_session = MagicMock()
    # Session exit raises OSError
    mock_session.__aexit__ = AsyncMock(side_effect=OSError("OS error"))

    mock_context = MagicMock()
    mock_context.__aexit__ = AsyncMock()

    handle = MCPClientHandle(session=mock_session, context=mock_context)

    # Should complete without raising
    await handle.cleanup()

    # Session exit should have been attempted
    mock_session.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_handles_transport_timeout():
    """Test cleanup handles transport exit timeout."""
    mock_session = MagicMock()
    mock_session.__aexit__ = AsyncMock()

    mock_context = MagicMock()
    # Transport exit times out
    mock_context.__aexit__ = AsyncMock(side_effect=asyncio.TimeoutError())

    handle = MCPClientHandle(session=mock_session, context=mock_context)

    # Should complete without raising
    await handle.cleanup()

    # Both exits should have been attempted
    mock_session.__aexit__.assert_called_once()
    mock_context.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_handles_transport_cancelled():
    """Test cleanup handles transport exit cancellation."""
    mock_session = MagicMock()
    mock_session.__aexit__ = AsyncMock()

    mock_context = MagicMock()
    # Transport exit cancelled
    mock_context.__aexit__ = AsyncMock(side_effect=asyncio.CancelledError())

    handle = MCPClientHandle(session=mock_session, context=mock_context)

    # Should complete without raising
    await handle.cleanup()

    # Both exits should have been attempted
    mock_session.__aexit__.assert_called_once()
    mock_context.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_handles_transport_generic_error():
    """Test cleanup handles transport generic exception."""
    mock_session = MagicMock()
    mock_session.__aexit__ = AsyncMock()

    mock_context = MagicMock()
    # Transport exit raises generic error
    mock_context.__aexit__ = AsyncMock(side_effect=ValueError("Transport error"))

    handle = MCPClientHandle(session=mock_session, context=mock_context)

    # Should complete without raising
    await handle.cleanup()

    # Both exits should have been attempted
    mock_session.__aexit__.assert_called_once()
    mock_context.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_task_affinity_violation_forces_cleanup():
    """Test cleanup handles task affinity violation by forcing cleanup."""
    mock_session = MagicMock()
    mock_session.__aexit__ = AsyncMock()

    mock_context = MagicMock()
    # Transport exit raises task affinity violation
    mock_context.__aexit__ = AsyncMock(side_effect=RuntimeError("Attempted to exit cancel scope from different task"))

    # Mock process for force cleanup
    mock_process = MagicMock()
    mock_process.returncode = None
    mock_process.pid = 12345
    mock_process.send_signal = MagicMock()
    mock_process.kill = MagicMock()
    mock_context._process = mock_process

    handle = MCPClientHandle(session=mock_session, context=mock_context)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        # Should complete without raising
        await handle.cleanup()

    # Session exit should have been attempted
    mock_session.__aexit__.assert_called_once()
    # Transport exit should have been attempted
    mock_context.__aexit__.assert_called_once()
    # Process should have been killed (SIGTERM)
    mock_process.send_signal.assert_called_with(signal.SIGTERM)


@pytest.mark.asyncio
async def test_force_cleanup_kills_running_process():
    """Test force cleanup kills running subprocess."""
    mock_session = MagicMock()
    mock_session.__aexit__ = AsyncMock()

    mock_context = MagicMock()
    mock_context.__aexit__ = AsyncMock(side_effect=RuntimeError("different task"))  # Triggers force cleanup

    # Mock running process
    mock_process = MagicMock()
    mock_process.returncode = None  # Process is running
    mock_process.pid = 12345
    mock_process.send_signal = MagicMock()
    mock_context._process = mock_process

    handle = MCPClientHandle(session=mock_session, context=mock_context)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await handle.cleanup()

    # Process should have been terminated
    mock_process.send_signal.assert_called_once_with(signal.SIGTERM)


@pytest.mark.asyncio
async def test_force_cleanup_kills_stubborn_process():
    """Test force cleanup force-kills process that doesn't respond to SIGTERM."""
    mock_session = MagicMock()
    mock_session.__aexit__ = AsyncMock()

    mock_context = MagicMock()
    mock_context.__aexit__ = AsyncMock(side_effect=RuntimeError("different task"))  # Triggers force cleanup

    # Mock stubborn process that ignores SIGTERM
    mock_process = MagicMock()
    mock_process.returncode = None  # Still running after SIGTERM
    mock_process.pid = 12345
    mock_process.send_signal = MagicMock()
    mock_process.kill = MagicMock()
    mock_context._process = mock_process

    handle = MCPClientHandle(session=mock_session, context=mock_context)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await handle.cleanup()

    # Process should have been SIGTERM'd then kill'd
    mock_process.send_signal.assert_called_once_with(signal.SIGTERM)
    mock_process.kill.assert_called_once()


@pytest.mark.asyncio
async def test_force_cleanup_handles_process_lookup_error():
    """Test force cleanup handles process already terminated."""
    mock_session = MagicMock()
    mock_session.__aexit__ = AsyncMock()

    mock_context = MagicMock()
    mock_context.__aexit__ = AsyncMock(side_effect=RuntimeError("different task"))  # Triggers force cleanup

    # Mock process that's already gone
    mock_process = MagicMock()
    mock_process.returncode = None
    mock_process.pid = 12345
    mock_process.send_signal = MagicMock(side_effect=ProcessLookupError())
    mock_context._process = mock_process

    handle = MCPClientHandle(session=mock_session, context=mock_context)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        # Should complete without raising
        await handle.cleanup()

    # SIGTERM should have been attempted
    mock_process.send_signal.assert_called_once()


@pytest.mark.asyncio
async def test_force_cleanup_cancels_task_group():
    """Test force cleanup cancels transport task group."""
    mock_session = MagicMock()
    mock_session.__aexit__ = AsyncMock()

    mock_context = MagicMock()
    mock_context.__aexit__ = AsyncMock(side_effect=RuntimeError("different task"))  # Triggers force cleanup

    # Mock task group with cancel scope
    mock_task_group = MagicMock()
    mock_cancel_scope = MagicMock()
    mock_cancel_scope.cancel = MagicMock()
    mock_task_group.cancel_scope = mock_cancel_scope
    mock_context._task_group = mock_task_group

    handle = MCPClientHandle(session=mock_session, context=mock_context)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await handle.cleanup()

    # Task group should have been cancelled
    mock_cancel_scope.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_stderr_resources_closes_file():
    """Test cleanup stderr resources closes file."""
    mock_stderr_file = MagicMock()
    mock_stderr_file.close = MagicMock()

    mock_session = MagicMock()
    mock_session.__aexit__ = AsyncMock()
    mock_context = MagicMock()
    mock_context.__aexit__ = AsyncMock()

    handle = MCPClientHandle(
        session=mock_session,
        context=mock_context,
        stderr_file=mock_stderr_file,
    )

    await handle.cleanup()

    # Stderr file should have been closed
    mock_stderr_file.close.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_stderr_resources_handles_file_close_error():
    """Test cleanup stderr resources handles file close error."""
    mock_stderr_file = MagicMock()
    mock_stderr_file.close = MagicMock(side_effect=OSError("File error"))

    mock_session = MagicMock()
    mock_session.__aexit__ = AsyncMock()
    mock_context = MagicMock()
    mock_context.__aexit__ = AsyncMock()

    handle = MCPClientHandle(
        session=mock_session,
        context=mock_context,
        stderr_file=mock_stderr_file,
    )

    # Should complete without raising
    await handle.cleanup()

    # Close should have been attempted
    mock_stderr_file.close.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_cancels_output_tasks():
    """Test cleanup cancels and awaits output tasks."""

    async def long_running_task():
        await asyncio.sleep(100)

    task = asyncio.create_task(long_running_task())

    mock_session = MagicMock()
    mock_session.__aexit__ = AsyncMock()
    mock_context = MagicMock()
    mock_context.__aexit__ = AsyncMock()

    handle = MCPClientHandle(
        session=mock_session,
        context=mock_context,
        output_tasks=[task],
    )

    await handle.cleanup()

    # Task should have been cancelled
    assert task.cancelled()


@pytest.mark.asyncio
async def test_cleanup_closes_stderr_fd():
    """Test cleanup closes stderr file descriptor."""
    mock_stderr_fd = 100

    mock_session = MagicMock()
    mock_session.__aexit__ = AsyncMock()
    mock_context = MagicMock()
    mock_context.__aexit__ = AsyncMock()

    handle = MCPClientHandle(
        session=mock_session,
        context=mock_context,
        stderr_read_fd=mock_stderr_fd,
    )

    with patch("os.close") as mock_close:
        await handle.cleanup()

        # FD should have been closed
        mock_close.assert_called_once_with(mock_stderr_fd)


@pytest.mark.asyncio
async def test_cleanup_handles_fd_close_error():
    """Test cleanup handles file descriptor close error."""
    mock_stderr_fd = 100

    mock_session = MagicMock()
    mock_session.__aexit__ = AsyncMock()
    mock_context = MagicMock()
    mock_context.__aexit__ = AsyncMock()

    handle = MCPClientHandle(
        session=mock_session,
        context=mock_context,
        stderr_read_fd=mock_stderr_fd,
    )

    with patch("os.close", side_effect=OSError("FD error")):
        # Should complete without raising
        await handle.cleanup()
