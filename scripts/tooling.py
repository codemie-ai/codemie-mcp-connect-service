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

"""Utility entry points for Poetry script aliases."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable, List


def _existing_paths(paths: Iterable[str]) -> List[str]:
    """Return provided paths that exist, defaulting to originals if none do."""
    materialized = [path for path in paths if Path(path).exists()]
    return materialized or list(paths)


def _run(command: list[str]) -> None:
    """Run a subprocess command, exiting with the same code on failure."""
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def run_format() -> None:
    """Format Python sources using Black."""
    _run(["black", *_existing_paths(("src", "tests"))])


def run_lint() -> None:
    """Run Ruff lint checks against project sources."""
    _run(["ruff", "check", *_existing_paths(("src", "tests"))])


def run_typecheck() -> None:
    """Run mypy in strict mode over src/."""
    _run(["mypy", "src"])


def run_test() -> None:
    """Execute the pytest suite."""
    _run(["pytest"])
