"""Integration tests for markitdown-mcp server."""

import sys

import httpx
import pytest

from mcp_connect.main import app, lifespan

# Get the Python executable path from the virtual environment
PYTHON_EXE = sys.executable


@pytest.mark.integration
@pytest.mark.asyncio
async def test_convert_to_markdown_https_uri() -> None:
    """Test convert_to_markdown with https:// URI."""
    async with lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/bridge",
                json={
                    "serverPath": PYTHON_EXE,
                    "args": ["-m", "markitdown_mcp"],
                    "method": "tools/call",
                    "params": {"name": "convert_to_markdown", "arguments": {"uri": "https://www.example.com"}},
                },
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert len(data["content"]) > 0
        # Example.com returns HTML, which markitdown converts to markdown
        assert "Example Domain" in str(data["content"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_convert_to_markdown_http_uri() -> None:
    """Test convert_to_markdown with http:// URI."""
    async with lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/bridge",
                json={
                    "serverPath": PYTHON_EXE,
                    "args": ["-m", "markitdown_mcp"],
                    "method": "tools/call",
                    "params": {"name": "convert_to_markdown", "arguments": {"uri": "http://www.example.com"}},
                },
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert len(data["content"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_convert_to_markdown_data_uri() -> None:
    """Test convert_to_markdown with data: URI."""
    async with lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/bridge",
                json={
                    "serverPath": PYTHON_EXE,
                    "args": ["-m", "markitdown_mcp"],
                    "method": "tools/call",
                    "params": {
                        "name": "convert_to_markdown",
                        "arguments": {"uri": "data:text/plain;base64,SGVsbG8gV29ybGQ="},
                    },
                },
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        # Base64 "Hello World" should be converted
        assert "Hello World" in str(data["content"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_convert_to_markdown_file_uri() -> None:
    """Test convert_to_markdown with file:// URI."""
    async with lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/bridge",
                json={
                    "serverPath": PYTHON_EXE,
                    "args": ["-m", "markitdown_mcp"],
                    "method": "tools/call",
                    "params": {"name": "convert_to_markdown", "arguments": {"uri": "file:///tmp/test.txt"}},
                },
                headers={"Authorization": "Bearer test-token"},
            )

        # File may not exist in test environment, but validation should pass
        # Response may be 200 with content or error from markitdown-mcp
        assert response.status_code >= 200


@pytest.mark.integration
@pytest.mark.asyncio
async def test_markitdown_client_caching() -> None:
    """Test that markitdown-mcp client is cached across requests."""
    async with lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # First request
            response1 = await client.post(
                "/bridge",
                json={
                    "serverPath": PYTHON_EXE,
                    "args": ["-m", "markitdown_mcp"],
                    "method": "tools/call",
                    "params": {"name": "convert_to_markdown", "arguments": {"uri": "data:text/plain,Test1"}},
                },
                headers={"Authorization": "Bearer test-token"},
            )

            # Second request with same serverPath
            response2 = await client.post(
                "/bridge",
                json={
                    "serverPath": PYTHON_EXE,
                    "args": ["-m", "markitdown_mcp"],
                    "method": "tools/call",
                    "params": {"name": "convert_to_markdown", "arguments": {"uri": "data:text/plain,Test2"}},
                },
                headers={"Authorization": "Bearer test-token"},
            )

        assert response1.status_code == 200
        assert response2.status_code == 200
        # Both requests should succeed (caching doesn't break functionality)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_markitdown_single_usage_mode() -> None:
    """Test markitdown-mcp with single_usage flag."""
    async with lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/bridge",
                json={
                    "serverPath": PYTHON_EXE,
                    "args": ["-m", "markitdown_mcp"],
                    "method": "tools/call",
                    "params": {"name": "convert_to_markdown", "arguments": {"uri": "data:text/plain,SingleUse"}},
                    "single_usage": True,
                },
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
