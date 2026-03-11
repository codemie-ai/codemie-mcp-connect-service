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
MCP Client Manager Module

This module handles creation and lifecycle management of MCP (Model Context Protocol)
clients. It provides transport detection (stdio, HTTP, SSE) and manages client
initialization with proper capabilities and cleanup.
"""

from .manager import detect_transport_type, get_or_create_client

__all__ = ["detect_transport_type", "get_or_create_client"]
