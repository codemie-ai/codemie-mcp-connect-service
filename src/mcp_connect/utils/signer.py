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

import re
from typing import Any

from botocore.credentials import Credentials


class SigV4Manager:
    """
    Central manager for SigV4 signing.
    Decides if signing is needed based on URL and applies signing if required.
    """

    @staticmethod
    def needs_signing(url: str) -> bool:
        """Return True if the URL requires AWS SigV4 signing."""
        return "bedrock-agentcore" in url.lower()

    @staticmethod
    def extract_service(url: str, env: dict[str, Any]) -> str:
        """Extract AWS service name from the URL."""
        if env.get("AWS_SERVICE"):
            return str(env["AWS_SERVICE"])
        m = re.search(r"https?://([a-z0-9-]+)\.[a-z0-9-]+\.amazonaws\.com", url)
        if m:
            return m.group(1)
        raise ValueError("Cannot extract AWS service from request")

    @staticmethod
    def extract_region(url: str, env: dict[str, Any]) -> str:
        """Extract AWS region from the URL."""
        if env.get("AWS_REGION"):
            return str(env["AWS_REGION"])

        m = re.search(r"https?://[a-z0-9-]+\.([a-z0-9-]+)\.amazonaws\.com", url)
        if m:
            return m.group(1)

        raise ValueError("Cannot extract AWS region from request")

    @staticmethod
    def extract_credentials(env: dict[str, Any]) -> Credentials:
        """Extract AWS credentials from the environment dictionary."""
        access_key = env.get("AWS_ACCESS_KEY_ID")
        secret_key = env.get("AWS_SECRET_ACCESS_KEY")
        token = env.get("AWS_SESSION_TOKEN")

        if not (access_key and secret_key):
            raise ValueError("AWS credentials not found in environment")

        return Credentials(access_key=access_key, secret_key=secret_key, token=token)
