"""Recorded runs on disk, and exporting a live run as one (D-050).

**Saved runs** are run folders (a folder holding run.json) under ``data/runs`` and
``data/experiments``. The client only ever sees paths relative to the project folder and can
never name one: the server decides where to look and where to write.

**Export by replay.** A live run isn't recorded tick by tick (that would cost memory and
~20% speed for every run, wanted or not). It doesn't need to be: a run is fully determined
by its config and seed, so re-running the same config headlessly for the same number of
ticks, with the normal recorder, reproduces its history exactly and writes the same files
``genesis run`` would. The replay's final state digest is compared with the live run's, so
the export proves itself. It runs in a worker thread (``asyncio.to_thread``): it builds its
own simulation and shares nothing with the live run, so the server stays responsive.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from genesis.analytics.runs import execute_run
from genesis.api.runs import PROJECT_ROOT, LiveRun, RunConflict
from genesis.api.schemas import ExportResult, RunState, SavedRun
from genesis.core.config import with_overrides
from genesis.lake.ingest import DEFAULT_LAKE, ingest_run

SAVED_ROOTS = (PROJECT_ROOT / "data" / "runs", PROJECT_ROOT / "data" / "experiments")
EXPORT_ROOT = PROJECT_ROOT / "data" / "runs" / "live"


def saved_runs(
    roots: tuple[Path, ...] = SAVED_ROOTS,
    experiment_id: str | None = None,
    limit: int = 200,
) -> list[SavedRun]:
    """Run folders, newest first. Unreadable folders are skipped, not fatal."""
    found = []
    for root in roots:
        for run_json in root.rglob("run.json") if root.exists() else ():
            try:
                meta = json.loads(run_json.read_text())
            except (OSError, ValueError):
                continue
            if not isinstance(meta, dict) or not {"run_id", "seed"} <= meta.keys():
                continue  # not a run record (a stray or half-written run.json): skip, not 500
            if experiment_id is not None and meta.get("experiment_id") != experiment_id:
                continue
            found.append((meta, run_json))
    # started_at is recorded to the second; the file's modification time breaks ties.
    found.sort(
        key=lambda item: (item[0].get("started_at") or "", item[1].stat().st_mtime_ns),
        reverse=True,
    )
    return [_saved(meta, run_json.parent) for meta, run_json in found[:limit]]


def _saved(meta: dict, folder: Path) -> SavedRun:
    try:
        path = folder.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        path = folder.name  # outside the project (tests): don't reveal the absolute path
    return SavedRun(
        path=path,
        run_id=meta["run_id"],
        status=meta.get("status", "unknown"),
        experiment_id=meta.get("experiment_id"),
        condition=meta.get("condition"),
        seed=meta["seed"],
        controller=(meta.get("config") or {}).get("organisms", {}).get("controller"),
        ticks_run=meta.get("ticks_run"),
        final_population=meta.get("final_population"),
        started_at=meta.get("started_at"),
    )


async def export_run(
    run: LiveRun,
    out_root: Path = EXPORT_ROOT,
    lake: Path | None = PROJECT_ROOT / DEFAULT_LAKE,
) -> ExportResult:
    """Replay ``run`` headlessly to its current tick into ``out_root/<run_id>-t<tick>``."""
    ticks = run.sim.tick
    if ticks == 0:
        raise RunConflict("the run hasn't taken a tick yet: nothing to export")
    if run.state is RunState.FAILED:
        raise RunConflict("a failed run can't be exported: its replay would fail the same way")
    if run.state is RunState.RUNNING or run.stepping:
        raise RunConflict("pause the run first, so the export matches a fixed moment")
    if run.exporting:
        # Two replays at once would write the same folder's files over each other.
        raise RunConflict("an export of this run is already in progress; wait for it")
    live_digest = run.sim.state_digest()
    config = with_overrides(run.config, max_ticks=ticks)
    recorded_id = f"{run.run_id}-t{ticks}"
    out_dir = out_root / recorded_id
    run.exporting = True
    try:
        result = await asyncio.to_thread(
            execute_run, config, out_dir, run_id=recorded_id, condition="live", overwrite=True
        )
        ingested = False
        if lake is not None:
            ingested = (await asyncio.to_thread(ingest_run, out_dir, lake)).ingested
    finally:
        run.exporting = False
    try:
        path = out_dir.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        path = out_dir.name
    return ExportResult(
        run_id=recorded_id,
        path=path,
        ticks=result.ticks_run,
        digest=result.final_state_digest,
        matches_live_run=result.final_state_digest == live_digest,
        ingested=ingested,
    )
