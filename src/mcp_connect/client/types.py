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
MCP Client Types

Type definitions for MCP client lifecycle management.
"""

import asyncio
import logging
import signal
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession

logger = logging.getLogger(__name__)


@dataclass
class MCPClientHandle:
    """
    Handle for MCP client with lifecycle management.

    Encapsulates an MCP ClientSession along with its underlying transport
    context manager, enabling proper resource cleanup.

    Attributes:
        session: Initialized MCP ClientSession ready for protocol operations
        context: Async context manager for the transport (stdio, HTTP, SSE)
                 Must be cleaned up by calling cleanup() or using async with
        output_tasks: Background tasks capturing stdout/stderr (stdio only)
        output_buffers: Circular buffers with last 50 lines per stream (stdio only)
        stderr_file: File object for stderr pipe write end (stdio only)
        stderr_read_fd: Raw file descriptor for stderr pipe read end (stdio only)

    Usage:
        >>> handle = await create_stdio_client(request)
        >>> try:
        ...     result = await handle.session.send_ping()
        ... finally:
        ...     await handle.cleanup()

    Note:
        The context manager is entered before session initialization and must
        remain active for the session lifetime. Call cleanup() when done to
        properly release resources (subprocess, HTTP connections, etc.).
    """

    session: ClientSession
    context: Any  # Async context manager (e.g., from stdio_client, streamablehttp_client)
    output_tasks: list[asyncio.Task[None]] = field(default_factory=list)
    output_buffers: dict[str, Any] | None = None
    stderr_file: Any = None  # File object for stderr pipe write end (stdio only)
    stderr_read_fd: int | None = None  # Raw FD for stderr pipe read end (stdio only)

    def _close_stderr_pipe(self) -> None:
        """Close stderr pipe write end (signals EOF to reader)."""
        if not self.stderr_file:
            return
        try:
            self.stderr_file.close()
        except OSError as e:
            logger.debug("Error closing stderr pipe (already closed or invalid): %s", e)

    async def _cancel_output_tasks(self) -> None:
        """Cancel output capture tasks (stdio transport only) with timeout protection."""
        for idx, task in enumerate(self.output_tasks):
            if task.done():
                logger.debug("Output task %d already done, skipping", idx)
                continue

            logger.debug("Cancelling output task %d...", idx)
            task.cancel()

            try:
                # Timeout protection: don't wait forever for task cancellation
                # If task can't be cancelled in 1 second, move on
                await asyncio.wait_for(task, timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning("Output task %d cancellation timed out after 1s", idx)
            except asyncio.CancelledError:
                logger.debug("Output task %d cancelled successfully", idx)
            except Exception as e:
                logger.warning("Unexpected error while cancelling output task %d: %s", idx, e, exc_info=True)

    def _close_stderr_fd(self) -> None:
        """Close stderr read FD if still open."""
        if self.stderr_read_fd is None:
            return
        try:
            import os

            os.close(self.stderr_read_fd)
        except OSError as e:
            logger.debug("Error closing stderr FD (already closed or invalid): %s", e)

    async def _exit_session(self) -> None:
        """Exit session context or directly cancel tasks if task affinity violated."""
        if not self.session:
            return

        try:
            logger.debug("Exiting session context...")
            await self.session.__aexit__(None, None, None)
            logger.debug("Session context exited successfully")
        except RuntimeError as e:
            if "different task" in str(e) or "cancel scope" in str(e):
                # Task affinity violation - can't use __aexit__, do direct cleanup
                logger.warning("Task affinity violation - doing direct session cleanup")
                await self._force_cleanup_session()
            else:
                logger.warning("RuntimeError during session exit: %s", e, exc_info=True)
        except asyncio.CancelledError:
            logger.warning("Session exit was cancelled")
        except Exception as e:
            logger.warning("Error during session exit: %s", e, exc_info=True)

    async def _force_cleanup_session(self) -> None:
        """Forcefully cleanup session by directly cancelling its task group."""
        try:
            # Access internal task group and cancel it directly
            if hasattr(self.session, "_task_group"):
                # noinspection PyProtectedMember
                task_group = self.session._task_group
                if hasattr(task_group, "cancel_scope"):
                    logger.debug("Directly cancelling session task group...")
                    task_group.cancel_scope.cancel()
                    # Give it a moment to process cancellation
                    await asyncio.sleep(0.1)
                    logger.debug("Session task group cancelled")
        except Exception as e:
            logger.warning("Error during force session cleanup: %s", e)

    async def _exit_transport(self) -> None:
        """Exit transport context or directly kill subprocess if task affinity violated."""
        if not self.context:
            return

        try:
            logger.debug("Exiting transport context...")
            await self.context.__aexit__(None, None, None)
            logger.debug("Transport context exited successfully")
        except RuntimeError as e:
            if "different task" in str(e) or "cancel scope" in str(e):
                # Task affinity violation - can't use __aexit__, do direct cleanup
                logger.warning("Task affinity violation - doing direct transport cleanup")
                await self._force_cleanup_transport()
            else:
                logger.warning("RuntimeError during transport exit: %s", e, exc_info=True)
        except asyncio.CancelledError:
            logger.warning("Transport exit was cancelled")
        except Exception as e:
            logger.warning("Error during transport exit: %s", e, exc_info=True)

    async def _force_cleanup_transport(self) -> None:
        """Forcefully cleanup transport by directly killing subprocess/closing connections."""
        try:
            # For stdio transport, kill the subprocess directly
            if hasattr(self.context, "_process"):
                # noinspection PyProtectedMember
                process = self.context._process
                if process and process.returncode is None:
                    logger.debug("Directly killing subprocess (PID: %s)...", process.pid)
                    try:
                        process.send_signal(signal.SIGTERM)
                        # Give it 100ms to terminate gracefully
                        await asyncio.sleep(0.1)
                        if process.returncode is None:
                            # Still alive, force kill
                            process.kill()
                            await asyncio.sleep(0.05)
                        logger.debug("Subprocess killed")
                    except ProcessLookupError:
                        logger.debug("Subprocess already terminated")

            # For HTTP/SSE transport, close the connection
            # (No direct access to httpx client in MCP SDK, let it leak)

            # Cancel any task groups in the context
            if hasattr(self.context, "_task_group"):
                # noinspection PyProtectedMember
                task_group = self.context._task_group
                if hasattr(task_group, "cancel_scope"):
                    logger.debug("Directly cancelling transport task group...")
                    task_group.cancel_scope.cancel()
                    await asyncio.sleep(0.1)
                    logger.debug("Transport task group cancelled")

        except Exception as e:
            logger.warning("Error during force transport cleanup: %s", e)

    def _reset_state(self) -> None:
        """Reset all state to prevent double cleanup."""
        self.context = None
        self.session = None  # type: ignore[assignment]
        self.output_tasks = []
        self.output_buffers = None
        self.stderr_file = None
        self.stderr_read_fd = None

    async def cleanup(self) -> None:
        """
        Clean up client resources.

        Exits both the session and transport context managers:
        - Transport: Closes connections/subprocesses FIRST
          - stdio: Closes stdin, waits for subprocess exit, terminates if needed
          - HTTP/SSE: Closes HTTP client connections
        - Session: Stops receive loop (gets EOF from closed transport)
        - Output capture tasks: Cancels stream capture tasks (stdio only)
        - Releases any OS resources (file descriptors, sockets)

        Safe to call multiple times (subsequent calls are no-ops).

        Note:
            Order is critical: transport MUST be closed before session to prevent
            cancellation storm. When transport closes, receive loop gets EOF and
            exits cleanly without forced cancellation.
        """
        import time

        start_time = time.monotonic()
        logger.debug("Starting MCPClientHandle cleanup...")

        # Close stderr pipe to signal EOF to stderr capture task
        logger.debug("Step 1: Closing stderr pipe...")
        self._close_stderr_pipe()

        # Exit transport FIRST - this closes pipes/connections and kills subprocess
        # After this, the session's receive loop will get EOF and exit cleanly
        logger.debug("Step 2: Exiting transport (this should close pipes/subprocess)...")
        transport_start = time.monotonic()
        await self._exit_transport()
        logger.debug("Step 2 completed in %.3fs", time.monotonic() - transport_start)

        # Now exit session - receive loop should already be done due to EOF
        logger.debug("Step 3: Exiting session (receive loop should get EOF)...")
        session_start = time.monotonic()
        await self._exit_session()
        logger.debug("Step 3 completed in %.3fs", time.monotonic() - session_start)

        # Cancel output capture tasks after transport is closed
        logger.debug("Step 4: Cancelling output capture tasks...")
        await self._cancel_output_tasks()

        # Close any remaining file descriptors
        logger.debug("Step 5: Closing remaining file descriptors...")
        self._close_stderr_fd()

        # Reset state to prevent double cleanup
        self._reset_state()

        total_time = time.monotonic() - start_time
        logger.debug("MCPClientHandle cleanup completed in %.3fs", total_time)
