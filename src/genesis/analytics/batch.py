"""Running an experiment spec: plan, resume, run in parallel, load into the lake.

    plan      one task per (condition, seed), each with its own output folder
    status    per task: missing / completed (same config hash) / stale (different hash) /
              incomplete (failed or never finished)
    run       skip completed tasks; refuse stale ones unless asked; run the rest in parallel
              worker processes; then ingest everything into the lake

Each run is fully independent (its own seed and random streams), so running tasks in any
order, on any number of workers, gives the same results. A test checks this byte for byte.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from genesis.analytics.experiments import run_dir_for
from genesis.analytics.runs import execute_run
from genesis.analytics.spec import PROJECT_ROOT, ExperimentSpec
from genesis.core.config import SimulationConfig, config_hash, hash_config_dict
from genesis.lake.ingest import DEFAULT_LAKE, ingest_paths

MISSING, COMPLETED, STALE, INCOMPLETE = "missing", "completed", "stale", "incomplete"


@dataclass(frozen=True)
class Task:
    condition: str
    seed: int
    config: SimulationConfig
    out_dir: Path

    @property
    def config_hash(self) -> str:
        return config_hash(self.config)


@dataclass(frozen=True)
class TaskOutcome:
    task: Task
    ok: bool
    message: str


def default_workers() -> int:
    """All cores but one, so the machine stays usable while an experiment runs."""
    return max(1, (os.cpu_count() or 2) - 1)


def plan(spec: ExperimentSpec, root: Path = PROJECT_ROOT) -> list[Task]:
    out = spec.output_dir(root)
    return [
        Task(label, seed, config, run_dir_for(out, spec.condition(label), seed))
        for (label, seed), config in spec.configs(root).items()
    ]


def task_status(task: Task) -> str:
    run_json = task.out_dir / "run.json"
    if not run_json.exists():
        return MISSING
    meta = json.loads(run_json.read_text())
    if meta.get("status") != "completed":
        return INCOMPLETE
    recorded = meta.get("config_hash") or hash_config_dict(meta["config"])
    return COMPLETED if recorded == task.config_hash else STALE


def run_experiment(
    spec: ExperimentSpec,
    workers: int | None = None,
    rerun_stale: bool = False,
    ingest: bool = True,
    lake: Path = DEFAULT_LAKE,
    root: Path = PROJECT_ROOT,
    on_outcome: Callable[[TaskOutcome, int, int], None] | None = None,
) -> list[TaskOutcome]:
    """Run every task that isn't already completed. Returns the outcome of each task run.

    Raises ``StaleRunsError`` (before running anything) if some folders hold completed runs
    made with a different config and ``rerun_stale`` is False: mixing them would silently
    combine results from two different experiments.
    """
    tasks = plan(spec, root)
    # A list of pairs, not a dict keyed by Task: a Task holds its config, and a config with
    # list values (brain.founder_weights, E007) can't be hashed.
    statuses = [(t, task_status(t)) for t in tasks]
    stale = [t for t, s in statuses if s == STALE]
    if stale and not rerun_stale:
        raise StaleRunsError(stale)
    todo = [t for t, s in statuses if s != COMPLETED]

    outcomes: list[TaskOutcome] = []
    if todo:
        with ProcessPoolExecutor(max_workers=workers or default_workers()) as pool:
            futures = {pool.submit(_run_task, *_payload(t, spec.experiment_id)): t for t in todo}
            for future in as_completed(futures):
                ok, message = future.result()
                outcome = TaskOutcome(futures[future], ok, message)
                outcomes.append(outcome)
                if on_outcome is not None:
                    on_outcome(outcome, len(outcomes), len(todo))
    if ingest:
        ingest_paths([t.out_dir for t in tasks if (t.out_dir / "run.json").exists()], lake)
    return sorted(outcomes, key=lambda o: (o.task.condition, o.task.seed))


class StaleRunsError(RuntimeError):
    def __init__(self, tasks: list[Task]):
        names = ", ".join(t.out_dir.name for t in tasks[:5]) + (" ..." if len(tasks) > 5 else "")
        super().__init__(
            f"{len(tasks)} completed run(s) used a different config than the spec now gives "
            f"({names}). Re-run them with --rerun-stale, or use a new experiment ID."
        )
        self.tasks = tasks


def _payload(task: Task, experiment_id: str) -> tuple:
    """What a worker process needs, as plain data (it must be sent between processes)."""
    return (task.config.model_dump(mode="json"), str(task.out_dir), experiment_id, task.condition)


def _run_task(config_data: dict, out_dir: str, experiment_id: str, condition: str):
    """Runs in a worker process. Returns (ok, message) instead of raising, so one failed run
    is reported without stopping the others; execute_run has already marked it failed."""
    config = SimulationConfig.model_validate(config_data)
    try:
        result = execute_run(
            config,
            Path(out_dir),
            experiment_id=experiment_id,
            condition=condition,
            overwrite=True,
        )
    except Exception as exc:  # noqa: BLE001 - reported per run, recorded in its run.json
        return False, f"{type(exc).__name__}: {exc}"
    return True, f"{result.ticks_run} ticks, {result.stop_reason}"
