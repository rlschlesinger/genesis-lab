"""Writing run output files: CSV tables and JSON metadata.

Both writers produce byte-identical files for identical inputs, on any operating system:
fixed column order, "\\n" line endings, UTF-8. That is what lets us check reproducibility
by comparing files directly.
"""

from __future__ import annotations

import csv
import json
import os
from collections.abc import Iterable
from pathlib import Path


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict]) -> None:
    """Write rows to CSV. ``None`` becomes an empty cell; floats use Python's shortest exact
    representation, so reading a value back gives exactly the same float.
    """
    with _atomic(path) as tmp, tmp.open("w", newline="", encoding="utf-8") as f:
        # lineterminator="\n": the csv module defaults to "\r\n" (Windows style), which would
        # make files differ by platform.
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: dict) -> None:
    with _atomic(path) as tmp:
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class _atomic:
    """Write to a temporary file, then rename it into place.

    A rename is all-or-nothing, so a crash mid-write can never leave a half-written file
    under the real name. This matters most for run.json, which is rewritten as a run's
    status changes.
    """

    def __init__(self, path: Path):
        self.path = path
        self.tmp = path.with_name(path.name + ".tmp")

    def __enter__(self) -> Path:
        return self.tmp

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            os.replace(self.tmp, self.path)
        else:
            self.tmp.unlink(missing_ok=True)
