"""Provenance: recording exactly what produced a run (code version and environment).

Spec section 9 requires every run to record its software version and relevant dependency
versions. Without these, "same seed, same result" can't be checked later.
"""

from __future__ import annotations

import platform
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

# Directory of this source file; git commands run here so they find this project's repo
# regardless of where the user launched the command from.
_SOURCE_DIR = Path(__file__).resolve().parent

PACKAGES = ["genesis-lab", "numpy", "pydantic", "pyyaml"]


def git_info() -> dict:
    """The current commit, and whether the working tree has uncommitted changes.

    ``dirty: true`` means the commit hash alone does NOT describe the code that ran: some
    files differed from that commit. Results from dirty runs are fine for exploring, but
    formal experiments should run from a clean commit.
    Returns ``None`` values if git or the repository is unavailable.
    """
    try:
        commit = _git("rev-parse", "HEAD")
        dirty = _git("status", "--porcelain") != ""
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}
    return {"commit": commit, "dirty": dirty}


def environment() -> dict:
    packages = {}
    for name in PACKAGES:
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": packages,
    }


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=_SOURCE_DIR, capture_output=True, text=True, check=True, timeout=10
    )
    return result.stdout.strip()
