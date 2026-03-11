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
MCP Client Cache with TTL

Provides an in-memory async cache for MCP ClientHandle instances with
time-based expiration to minimize connection setup overhead.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any

from ..models.request import BridgeRequestBody
from .managed import ManagedClient

logger = logging.getLogger(__name__)


async def _validate_client(managed_client: ManagedClient) -> bool:
    """
    Validate cached managed client by sending ping.

    Attempts to ping the MCP server to verify the client connection is still
    active. Timeout is set to 2 seconds to fail fast on stale connections.

    Args:
        managed_client: ManagedClient to validate

    Returns:
        True if client responds to ping within timeout, False otherwise
        (timeout, connection error, or any other exception)

    Note:
        All exceptions are caught and logged as warnings. The method never
        raises exceptions - failures are treated as validation failures.
    """
    try:
        await asyncio.wait_for(managed_client.session.send_ping(), timeout=2.0)
        return True
    except asyncio.TimeoutError:
        logger.warning("Cached client validation failed: ping timeout, removing from cache")
        return False
    except Exception as e:
        logger.warning("Cached client validation failed: %s, removing from cache", str(e))
        return False


class MCPClientCache:
    """
    Async cache for managed MCP clients with TTL-based expiration.

    Stores ManagedClient instances (each running in dedicated task) with
    timestamps for connection reuse, reducing overhead on repeated requests.

    Thread-safe with asyncio.Lock for concurrent access protection.

    Attributes:
        _cache: Internal storage mapping cache keys to (managed_client, timestamp) tuples
        _lock: Asyncio lock for thread-safe operations
        _ttl: Time-to-live in seconds before cached clients expire
    """

    def __init__(
        self,
        ttl_seconds: int | None = None,
    ) -> None:
        """
        Initialize cache with configurable TTL.

        Args:
            ttl_seconds: Time-to-live in seconds. If None, reads from
                        MCP_CONNECT_CLIENT_CACHE_TTL env var (milliseconds).
                        Defaults to 300 seconds (5 minutes) if not provided.

        Note:
            Cleanup interval is controlled by the cleanup scheduler in main.py.
            See MCP_CONNECT_CACHE_CLEANUP_INTERVAL env var.
        """
        # Read TTL from env var if not provided
        if ttl_seconds is None:
            ttl_ms = int(os.getenv("MCP_CONNECT_CLIENT_CACHE_TTL", "300000"))
            ttl_seconds = int(ttl_ms / 1000)

        self._cache: dict[str, tuple[ManagedClient, float]] = {}  # managed_client, last_used_at
        self._lock = asyncio.Lock()
        self._ttl = ttl_seconds

    async def get(self, key: str) -> ManagedClient | None:
        """
        Retrieve cached managed client if within TTL and passes validation.

        Performs TTL expiration check followed by ping validation to ensure
        the cached client is still connected and responsive. On successful
        retrieval, updates last_used_at to current time (sliding window TTL).

        Args:
            key: Cache key identifying the client configuration

        Returns:
            ManagedClient if found, not expired, and ping succeeds;
            None otherwise (cache miss triggers new client creation)
        """
        async with self._lock:
            if key not in self._cache:
                return None

            managed_client, last_used_at = self._cache[key]
            age = time.monotonic() - last_used_at

            if age >= self._ttl:
                # Expired - remove and return None
                await self._remove_unsafe(key)
                return None

            # Validate client with ping before returning
            if not await _validate_client(managed_client):
                # Validation failed - remove stale client and return None
                await self._remove_unsafe(key)
                return None

            # Update last_used_at to current time (sliding window TTL)
            self._cache[key] = (managed_client, time.monotonic())

            return managed_client

    async def set(self, key: str, managed_client: ManagedClient) -> None:
        """
        Store managed client in cache with current timestamp.

        Args:
            key: Cache key identifying the client configuration
            managed_client: ManagedClient to cache (running in dedicated task)
        """
        async with self._lock:
            self._cache[key] = (managed_client, time.monotonic())

    async def remove(self, key: str) -> None:
        """
        Remove specific client from cache.

        Args:
            key: Cache key to remove
        """
        async with self._lock:
            await self._remove_unsafe(key)

    async def clear(self) -> None:
        """
        Remove all clients from cache (for graceful shutdown).
        """
        async with self._lock:
            # Iterate over copy of keys to avoid mutation during iteration
            keys = list(self._cache.keys())
            for key in keys:
                await self._remove_unsafe(key)

    async def _remove_unsafe(self, key: str) -> None:
        """
        Remove managed client from cache (assumes lock already held).

        Signals the managed client's dedicated task to exit contexts and cleanup.
        Exceptions during cleanup are logged but not raised.

        Args:
            key: Cache key to remove

        Note:
            This method assumes the caller already holds self._lock.
            Do NOT call this method without holding the lock.
        """
        if key in self._cache:
            managed_client, _ = self._cache.pop(key)
            try:
                logger.debug("Cleaning up cached client: %s", key[:16])
                # Signal dedicated task to exit contexts
                await managed_client.cleanup()
                logger.debug("Cached client cleaned up successfully: %s", key[:16])
            except asyncio.CancelledError:
                logger.error("Cleanup was cancelled for key %s (cancellation storm!)", key[:16])
                raise  # Re-raise to preserve cancellation semantics
            except Exception as e:
                logger.error("Error during client cleanup for key %s: %s", key[:16], e, exc_info=True)


# DEPRECATED: cleanup_expired_clients() function removed
# Cleanup now handled by periodic scheduler in main.py that signals
# ManagedClient dedicated tasks to exit contexts, preserving anyio task affinity.
# See: src/mcp_connect/client/managed.py


def generate_cache_key(request: BridgeRequestBody) -> str:
    """
    Generate deterministic cache key from request parameters.

    Creates a SHA-256 hash of all parameters that affect client configuration,
    ensuring identical requests produce identical cache keys.

    Args:
        request: Bridge request containing MCP server configuration

    Returns:
        Hex digest string (64 characters) uniquely identifying the configuration
    """
    key_data: dict[str, Any] = {
        "server_path": request.serverPath,
        "args": sorted(request.args or []),
        "env": sorted((request.env or {}).items()),
        "mcp_headers": sorted((request.mcp_headers or {}).items()),
        "http_transport_type": request.http_transport_type or "default",
    }

    # Serialize with sorted keys for determinism
    key_json = json.dumps(key_data, sort_keys=True)

    # Hash to create fixed-length key
    return hashlib.sha256(key_json.encode()).hexdigest()
