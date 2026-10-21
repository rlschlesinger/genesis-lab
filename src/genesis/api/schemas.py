"""The API's contract: the exact shape of every request and response (docs/API.md).

Pydantic models do double duty. Incoming JSON is validated against them (a missing or
mistyped field is refused with a 422 before any code runs), and outgoing data is serialised
through them, so the browser can rely on these shapes. FastAPI also turns them into an
OpenAPI description, browsable at http://127.0.0.1:8765/docs while the server runs.

``API_VERSION`` changes whenever a shape changes incompatibly, so a client can tell it is
talking to a server it doesn't understand.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

API_VERSION = 1

# Config names are file names in configs/ without ".yaml": letters, digits, "_" and "-" only,
# so a name can never smuggle in a path like "../../secret".
ConfigName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown fields are an error, not ignored


class RunState(StrEnum):
    """Where a live run is in its life (see runs.py for the allowed moves between them)."""

    IDLE = "idle"  # created; tick 0 not yet taken
    RUNNING = "running"  # stepping on its own (5.2)
    PAUSED = "paused"  # stopped part-way; can resume or step
    COMPLETED = "completed"  # reached max_ticks, or went extinct with stop_on_extinction
    FAILED = "failed"  # the simulation raised an error (e.g. the energy ledger check)


class Health(BaseModel):
    status: str
    api_version: int
    genesis_version: str


class ConfigSummary(BaseModel):
    name: str
    controller: str
    max_ticks: int
    initial_count: int
    has_brains: bool
    mutation_enabled: bool
    has_predators: bool = False  # a predators: section (6.5)
    predator_controller: str | None = None
    initial_predators: int | None = None
    has_two_foods: bool = False  # a resources: section (6.9)


class RunCreate(_Strict):
    """Start a live run from a config in configs/, optionally changed.

    ``changes`` uses the same dotted paths as experiment specs, e.g.
    ``{"food.regrowth_per_tick": 1.0}``; the result is validated exactly like a config file.
    """

    config: ConfigName = "default"
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)
    max_ticks: int | None = Field(default=None, gt=0, le=1_000_000)
    changes: dict[str, object] = Field(default_factory=dict, max_length=32)


class RunInfo(BaseModel):
    run_id: str
    state: RunState
    config_name: str
    seed: int
    controller: str
    tick: int  # ticks completed so far
    max_ticks: int
    population: int  # prey alive
    predators: int | None = None  # predators alive; None in a world without predators (6.5)
    speed: float | None  # target ticks per second while running; None = as fast as possible
    viewers: int  # open snapshot streams
    error: str | None = None  # why the run failed, when state is "failed"


class Digest(BaseModel):
    """The run's state fingerprint (Simulation.state_digest): equal digests at equal ticks mean
    bit-identical states, so an API-driven run can be checked against a headless one."""

    run_id: str
    tick: int
    digest: str


class StepRequest(_Strict):
    ticks: int = Field(default=1, ge=1, le=10_000)


class SpeedRequest(_Strict):
    """Target ticks per second while running; null runs as fast as the machine allows."""

    ticks_per_second: float | None = Field(gt=0, le=100_000)


class ResetRequest(_Strict):
    """Start the run again from tick 0: same config, and the same seed unless one is given."""

    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)


class BrainThought(BaseModel):
    """A neural organism's decision on the run's latest tick, exactly as computed (D-050)."""

    tick: int  # the tick this decision was made in
    input_names: list[str]
    inputs: list[float]  # as passed to the network (7; 10 for prey that sense predators)
    hidden_sum: list[float]  # weighted sums into the hidden layer (6)
    hidden: list[float]  # tanh of those (6)
    output_sum: list[float]  # weighted sums into the outputs (2)
    outputs: list[float]  # turn in (-1, 1), throttle in (0, 1)
    turn: float  # radians, as applied (output x max_turn)
    throttle: float  # as applied


class OrganismDetail(BaseModel):
    id: int
    species: Literal["prey", "predator"] = "prey"  # 6.5
    alive: bool
    parent_id: int | None
    founder_id: int
    generation: int
    birth_tick: int
    death_tick: int | None
    death_cause: str | None
    age: int
    energy: float
    x: float
    y: float
    heading: float
    food_eaten: int
    prey_eaten: int = 0  # predators: prey caught
    diet: float | None = None  # two foods: the diet gene (0 = eats A, 1 = eats B)
    meals_b: int = 0  # two foods: meals of B (food_eaten counts both)
    offspring_count: int
    children: list[int]  # IDs of its offspring, in birth order
    genome: dict[str, float]
    traits: dict[str, float]
    # Named parameters as in brains.csv: 62, or 80 for prey that sense predators; None without.
    brain_weights: dict[str, float] | None
    thought: BrainThought | None  # None: no brain, or it didn't decide on the latest tick


class SavedRun(BaseModel):
    """A recorded run folder on disk (written by genesis run, experiments, or an export)."""

    path: str  # relative to the project folder
    run_id: str
    status: str
    experiment_id: str | None
    condition: str | None
    seed: int
    controller: str | None
    ticks_run: int | None
    final_population: int | None
    started_at: str | None


class ExportResult(BaseModel):
    """A live run written as a normal run folder by replaying it headlessly (D-050)."""

    run_id: str  # of the recorded run (the live run's ID plus the tick)
    path: str
    ticks: int
    digest: str
    matches_live_run: bool  # the replay's final digest equals the live run's
    ingested: bool


class History(BaseModel):
    """A live run's history as columns (api/history.py). Each point covers ``every`` ticks:
    flows summed, stocks at the interval's last tick, shares averaged; null = nothing to
    measure. Only complete intervals."""

    run_id: str
    every: int
    columns: dict[str, list[float | int | None]]


class LineageNode(BaseModel):
    id: int
    generation: int
    birth_tick: int
    death_tick: int | None
    alive: bool
    offspring_count: int
    children: list[LineageNode] = []
    hidden_children: int = 0  # children beyond the requested depth or breadth


class Lineage(BaseModel):
    """An organism's family in a live run (api/lineage.py)."""

    organism: LineageNode  # with descendants, cut to depth and breadth
    ancestors: list[LineageNode]  # founder first, parent last; empty for a founder
    descendants: int  # everyone below it, however deep
    founder_id: int
    founder_family: int  # the founder and all its descendants, ever
    founder_family_alive: int


class LakeExperiment(BaseModel):
    experiment_id: str | None  # None: runs outside any experiment (saved from the lab)
    title: str | None
    runs: int


class LakeRun(BaseModel):
    run_id: str
    experiment_id: str | None
    condition: str | None
    seed: int
    ticks_run: int
    final_population: int
    ticks_every: int
    controller: str | None = None


class LakeRunDetail(LakeRun):
    config: dict


class ErrorBody(BaseModel):
    detail: str
