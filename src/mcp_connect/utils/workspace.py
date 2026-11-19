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

"""Where stdio MCP servers run and where each user's files live (EPMCDME-14735).

The spawn sites and the export module both read this, so the folder rule has one home
(EPMCDME-16903 moves servers into per-user folders here).
"""

from __future__ import annotations

import hashlib
import os

SERVER_CWD = "/home/codemie"  # the image's WORKDIR; the relative base for export


def server_cwd() -> str | None:
    """The working folder to spawn a stdio server in; ``None`` (inherit) where it does not exist, as in local runs."""
    return SERVER_CWD if os.path.isdir(SERVER_CWD) else None


def _h(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def user_root(user_id: str | None, scope: str | None = None) -> str | None:
    """The caller's folder under ``SERVER_CWD``: ``u-<user>``, or ``u-<user>/c-<scope>`` for a conversation.

    ``user_id`` must be the person who made the call (the backend sends the initiator, not the
    credential owner); ``scope`` is the conversation (or workflow run), so one conversation never
    receives another's same-named file. ``None`` when the call names no user. Plain hashes, not
    secrets: every server runs as one uid and can list ``SERVER_CWD`` anyway.
    """
    uid = (user_id or "").strip()
    if not uid:
        return None
    sid = (scope or "").strip()
    return f"{SERVER_CWD}/u-{_h(uid)}" + (f"/c-{_h(sid)}" if sid else "")
