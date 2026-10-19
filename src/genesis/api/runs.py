"""Live runs: simulations held in memory by the API server, each with an explicit state.

The server is the one authority over a live run. Browsers ask it to do things (create,
pause, step...) and are shown the result; they never hold simulation state of their own.

A run's state can only change along the moves in ``ALLOWED``. A request that would make any
other move (resume a completed run, step a running one) is refused with ``RunConflict``
instead of doing something surprising. Writing the moves down as data, rather than as
scattered if-statements, makes the whole lifecycle readable in one place and testable.

    idle ──resume──► running ──pause──► paused ──resume──► running
      │                 │                  │
      └──step──► paused └──(end)──► completed / failed ◄──(end)── step
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from genesis.analytics.experiments import apply_changes
from genesis.analytics.runs import new_run_id
from genesis.api.schemas import ConfigSummary, RunCreate, RunInfo, RunState
from genesis.core.config import ConfigError, SimulationConfig, load_config, with_overrides
from genesis.core.simulation import Simulation

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIGS_DIR = PROJECT_ROOT / "configs"
MAX_LIVE_RUNS = 4  # each live run holds its whole history in memory
DEFAULT_SPEED = 30.0  # ticks per second: slow enough to watch; the client can change it

# (from, to) pairs a run may move along. Anything else is a conflict.
ALLOWED: frozenset[tuple[RunState, RunState]] = frozenset(
    {
        (RunState.IDLE, RunState.RUNNING),
        (RunState.IDLE, RunState.PAUSED),  # a single step from idle leaves it paused
        (RunState.RUNNING, RunState.PAUSED),
        (RunState.PAUSED, RunState.RUNNING),
        (RunState.IDLE, RunState.COMPLETED),
        (RunState.RUNNING, RunState.COMPLETED),
        (RunState.PAUSED, RunState.COMPLETED),
        (RunState.IDLE, RunState.FAILED),
        (RunState.RUNNING, RunState.FAILED),
        (RunState.PAUSED, RunState.FAILED),
    }
)


class RunNotFound(KeyError):
    pass


class RunConflict(RuntimeError):
    """The request is valid but impossible in the run's current state (HTTP 409)."""


class TooManyRuns(RuntimeError):
    """The server already holds MAX_LIVE_RUNS runs (HTTP 429)."""


class InvalidRunRequest(ValueError):
    """The config or its changes are invalid (HTTP 422)."""


@dataclass
class LiveRun:
    run_id: str
    config_name: str
    config: SimulationConfig
    sim: Simulation
    state: RunState = RunState.IDLE
    error: str | None = None
    speed: float | None = DEFAULT_SPEED  # ticks per second while running; None = flat out
    task: asyncio.Task | None = None  # the background loop while running (stepping.py)

    def info(self) -> RunInfo:
        return RunInfo(
            run_id=self.run_id,
            state=self.state,
            config_name=self.config_name,
            seed=self.config.run.seed,
            controller=self.config.organisms.controller,
            tick=self.sim.tick,
            max_ticks=self.config.run.max_ticks,
            population=len(self.sim.organisms),
            speed=self.speed,
            error=self.error,
        )

    def move_to(self, new: RunState) -> None:
        if (self.state, new) not in ALLOWED:
            raise RunConflict(f"run {self.run_id} is {self.state}; it can't become {new}")
        self.state = new


@dataclass
class RunManager:
    configs_dir: Path = CONFIGS_DIR
    max_runs: int = MAX_LIVE_RUNS
    runs: dict[str, LiveRun] = field(default_factory=dict)  # insertion order = creation order

    # --- Configs --------------------------------------------------------------------------

    def config_names(self) -> list[str]:
        return sorted(p.stem for p in self.configs_dir.glob("*.yaml"))

    def load_config(self, name: str) -> SimulationConfig:
        # Only names listed from the folder are accepted: a name can't point anywhere else.
        if name not in self.config_names():
            raise InvalidRunRequest(f"unknown config {name!r}; choose from {self.config_names()}")
        try:
            return load_config(self.configs_dir / f"{name}.yaml")
        except (ConfigError, ValueError) as exc:
            raise InvalidRunRequest(f"config {name!r} is invalid: {exc}") from exc

    def config_summaries(self) -> list[ConfigSummary]:
        summaries = []
        for name in self.config_names():
            c = self.load_config(name)
            summaries.append(
                ConfigSummary(
                    name=name,
                    controller=c.organisms.controller,
                    max_ticks=c.run.max_ticks,
                    initial_count=c.organisms.initial_count,
                    has_brains=c.brain is not None,
                    mutation_enabled=c.mutation.enabled,
                )
            )
        return summaries

    # --- Runs -----------------------------------------------------------------------------

    def create(self, request: RunCreate) -> LiveRun:
        if len(self.runs) >= self.max_runs:
            raise TooManyRuns(
                f"{len(self.runs)} live runs already (the limit is {self.max_runs}); "
                "delete one first"
            )
        config = self.load_config(request.config)
        try:
            if request.changes:
                config = apply_changes(config, request.changes)
            config = with_overrides(config, seed=request.seed, max_ticks=request.max_ticks)
        except (KeyError, ValueError) as exc:  # unknown path, or the result doesn't validate
            raise InvalidRunRequest(str(exc).strip('"')) from exc
        run = LiveRun(new_run_id(config.run.seed), request.config, config, Simulation(config))
        self.runs[run.run_id] = run
        return run

    def get(self, run_id: str) -> LiveRun:
        try:
            return self.runs[run_id]
        except KeyError:
            raise RunNotFound(f"no live run {run_id!r}") from None

    def delete(self, run_id: str) -> None:
        run = self.get(run_id)
        if run.task is not None and not run.task.done():
            run.task.cancel()
        del self.runs[run_id]

    def reset(self, run_id: str, seed: int | None = None) -> LiveRun:
        """A fresh run from tick 0 with the same config (and seed, unless one is given). It
        replaces the old run and gets a new ID: a run ID always names one history."""
        old = self.get(run_id)
        config = with_overrides(old.config, seed=seed)
        self.delete(run_id)
        run = LiveRun(new_run_id(config.run.seed), old.config_name, config, Simulation(config))
        run.speed = old.speed
        self.runs[run.run_id] = run
        return run
