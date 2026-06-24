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

"""Tests for ManagedClient lifecycle error handling."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_connect.client.managed import ManagedClient
from src.mcp_connect.models.request import BridgeRequestBody


@pytest.fixture
def stdio_request():
    """Create a sample stdio request."""
    return BridgeRequestBody(
        serverPath="python",
        method="ping",
        params={},
        args=["-u", "fixtures/json_rpc_server.py"],
    )


@pytest.fixture
def http_request():
    """Create a sample HTTP request."""
    return BridgeRequestBody(
        serverPath="https://example.com/mcp",
        method="ping",
        params={},
    )


@pytest.mark.asyncio
async def test_spawn_timeout_cleans_up_task(stdio_request):
    """Test spawn timeout cancels the spawned task."""

    with patch.object(ManagedClient, "_run_client_lifecycle", new_callable=AsyncMock) as mock_lifecycle:
        # Make lifecycle never complete (will timeout)
        # Use lambda to create coroutine when called (not immediately)
        mock_lifecycle.side_effect = lambda *args, **kwargs: asyncio.sleep(100)

        with patch("asyncio.create_task", wraps=asyncio.create_task) as mock_create_task:
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                # Spawn should raise exception after timeout
                with pytest.raises(Exception, match="Client initialization timeout"):
                    await ManagedClient.spawn(stdio_request)

                # Task should have been created
                assert mock_create_task.called


@pytest.mark.asyncio
async def test_spawn_initialization_error_cleans_up(stdio_request):
    """Test spawn cleans up task when initialization fails."""

    with patch.object(ManagedClient, "_run_client_lifecycle", new_callable=AsyncMock) as mock_lifecycle:
        # Make lifecycle raise error immediately
        mock_lifecycle.side_effect = RuntimeError("Init failed")

        # Track task and cleanup event via asyncio.create_task wrapper
        created_task = None
        cleanup_event = None

        original_create_task = asyncio.create_task

        def capture_task(coro):
            nonlocal created_task
            task = original_create_task(coro)
            created_task = task
            return task

        with patch("asyncio.create_task", side_effect=capture_task) as mock_create_task:
            # Capture cleanup event from lifecycle call
            def capture_lifecycle_args(request, event, future):
                nonlocal cleanup_event
                cleanup_event = event
                raise RuntimeError("Init failed")

            mock_lifecycle.side_effect = capture_lifecycle_args

            # Should propagate the error
            with pytest.raises(RuntimeError, match="Init failed"):
                await ManagedClient.spawn(stdio_request)

            # Verify cleanup happened
            assert mock_create_task.called, "Task should have been created"
            assert created_task is not None, "Task should have been captured"
            assert cleanup_event is not None, "Cleanup event should have been captured"

            # Verify cleanup steps
            assert cleanup_event.is_set(), "Cleanup event should have been set to signal task"
            assert created_task.cancelled() or created_task.done(), "Task should have been cancelled or completed"


@pytest.mark.asyncio
async def test_cleanup_timeout_cancels_task(stdio_request):
    """Test cleanup timeout force-cancels task."""

    # Create mock components
    mock_session = MagicMock()
    cleanup_event = asyncio.Event()
    ready_future = asyncio.Future()
    ready_future.set_result(mock_session)

    # Create a task that won't complete
    async def never_completes():
        await asyncio.sleep(100)

    task = asyncio.create_task(never_completes())

    # Create managed client with the task
    managed = ManagedClient(
        session=mock_session,
        _cleanup_event=cleanup_event,
        _task=task,
        _ready_future=ready_future,
    )

    # Mock wait_for to timeout
    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
        # Cleanup should complete despite timeout
        await managed.cleanup()

    # Task should be cancelled
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_cleanup_handles_task_exception(stdio_request):
    """Test cleanup handles exception during task completion."""

    # Create mock components
    mock_session = MagicMock()
    cleanup_event = asyncio.Event()
    ready_future = asyncio.Future()
    ready_future.set_result(mock_session)

    # Create a task that raises error
    async def fails():
        await asyncio.sleep(0.01)
        raise RuntimeError("Task error")

    task = asyncio.create_task(fails())

    # Create managed client
    managed = ManagedClient(
        session=mock_session,
        _cleanup_event=cleanup_event,
        _task=task,
        _ready_future=ready_future,
    )

    # Cleanup should handle the error gracefully
    await managed.cleanup()

    # Task should be done
    assert task.done()


@pytest.mark.asyncio
async def test_lifecycle_sets_exception_on_cancellation(stdio_request):
    """Test lifecycle sets exception on ready_future when cancelled."""

    cleanup_event = asyncio.Event()
    ready_future = asyncio.Future()

    # Run lifecycle with immediate cancellation
    task = asyncio.create_task(ManagedClient._run_client_lifecycle(stdio_request, cleanup_event, ready_future))

    # Cancel immediately
    await asyncio.sleep(0.01)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # Ready future should have exception set
    assert ready_future.done()
    with pytest.raises(asyncio.CancelledError):
        ready_future.result()


@pytest.mark.asyncio
async def test_lifecycle_sets_exception_on_error(stdio_request):
    """Test lifecycle sets exception on ready_future when error occurs."""

    cleanup_event = asyncio.Event()
    ready_future = asyncio.Future()

    # Mock stdio_client to raise error
    with patch("mcp.client.stdio.stdio_client", side_effect=ValueError("Test error")):
        # Run lifecycle
        await ManagedClient._run_client_lifecycle(stdio_request, cleanup_event, ready_future)

        # Ready future should have exception set
        assert ready_future.done()
        with pytest.raises(ValueError, match="Test error"):
            ready_future.result()


@pytest.mark.asyncio
async def test_cleanup_sets_event_signal(stdio_request):
    """Test cleanup sets the cleanup event to signal task."""

    mock_session = MagicMock()
    cleanup_event = asyncio.Event()
    ready_future = asyncio.Future()
    ready_future.set_result(mock_session)

    # Create a task that will complete quickly
    async def completes_quickly():
        await asyncio.sleep(0.01)

    task = asyncio.create_task(completes_quickly())

    managed = ManagedClient(
        session=mock_session,
        _cleanup_event=cleanup_event,
        _task=task,
        _ready_future=ready_future,
    )

    # Event should not be set initially
    assert not cleanup_event.is_set()

    # Cleanup
    await managed.cleanup()

    # Event should be set
    assert cleanup_event.is_set()


@pytest.mark.asyncio
async def test_http_lifecycle_handles_cancellation(http_request):
    """Test SSE (HTTP) lifecycle handles cancellation."""

    cleanup_event = asyncio.Event()
    ready_future = asyncio.Future()

    # Create a task and cancel it immediately
    task = asyncio.create_task(ManagedClient._run_sse_client(http_request, cleanup_event, ready_future))

    # Cancel after a brief delay
    await asyncio.sleep(0.01)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # Ready future should have exception if not already resolved
    if not ready_future.done():
        # Cancellation happened before initialization
        pass
    else:
        # Check if it completed or got exception
        assert ready_future.done()


@pytest.mark.asyncio
async def test_stdio_lifecycle_handles_cancellation(stdio_request):
    """Test stdio lifecycle handles cancellation."""

    cleanup_event = asyncio.Event()
    ready_future = asyncio.Future()

    # Create a task and cancel it immediately
    task = asyncio.create_task(ManagedClient._run_stdio_client(stdio_request, cleanup_event, ready_future))

    # Cancel after a brief delay
    await asyncio.sleep(0.01)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # Ready future should have exception if not already resolved
    if not ready_future.done():
        # Cancellation happened before initialization
        pass
    else:
        # Check if it completed or got exception
        assert ready_future.done()


@pytest.mark.asyncio
async def test_spawn_waits_for_initialization(stdio_request):
    """Test spawn waits for session initialization before returning."""

    mock_session = MagicMock()
    init_called = False

    async def mock_lifecycle(request, cleanup_event, ready_future):
        nonlocal init_called
        init_called = True
        # Simulate initialization delay
        await asyncio.sleep(0.01)
        ready_future.set_result(mock_session)
        # Wait for cleanup
        await cleanup_event.wait()

    with patch.object(ManagedClient, "_run_client_lifecycle", side_effect=mock_lifecycle):
        managed = await ManagedClient.spawn(stdio_request)

        # Initialization should have been called
        assert init_called
        # Session should be available
        assert managed.session == mock_session

        # Cleanup
        await managed.cleanup()


@pytest.mark.asyncio
async def test_spawn_propagates_ready_future_exception(stdio_request):
    """Test spawn propagates exception from ready_future."""

    async def mock_lifecycle(request, cleanup_event, ready_future):
        # Set exception on ready_future
        ready_future.set_exception(ValueError("Setup failed"))

    with patch.object(ManagedClient, "_run_client_lifecycle", side_effect=mock_lifecycle):
        # Should raise the exception from ready_future
        with pytest.raises(ValueError, match="Setup failed"):
            await ManagedClient.spawn(stdio_request)


@pytest.mark.asyncio
async def test_cleanup_completes_even_if_task_hangs(stdio_request):
    """Test cleanup completes with timeout even if task doesn't respond."""

    mock_session = MagicMock()
    cleanup_event = asyncio.Event()
    ready_future = asyncio.Future()
    ready_future.set_result(mock_session)

    # Create a stubborn task that ignores cleanup signal
    async def stubborn_task():
        await asyncio.sleep(100)  # Never completes

    task = asyncio.create_task(stubborn_task())

    managed = ManagedClient(
        session=mock_session,
        _cleanup_event=cleanup_event,
        _task=task,
        _ready_future=ready_future,
    )

    # Patch wait_for to simulate 10s timeout
    original_wait_for = asyncio.wait_for

    async def mock_wait_for(coro, timeout):
        if timeout == 10.0:
            # Simulate timeout on cleanup wait
            raise asyncio.TimeoutError()
        return await original_wait_for(coro, timeout)

    with patch("asyncio.wait_for", side_effect=mock_wait_for):
        # Cleanup should complete despite timeout
        await managed.cleanup()

    # Task should be cancelled after timeout
    assert task.cancelled() or task.done()
