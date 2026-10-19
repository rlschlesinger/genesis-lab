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
from typing import Annotated

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
    population: int
    error: str | None = None  # why the run failed, when state is "failed"


class ErrorBody(BaseModel):
    detail: str
