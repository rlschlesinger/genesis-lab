"""The FastAPI application: HTTP routes over a RunManager. Deliberately thin.

Each route translates one HTTP request into one RunManager call and its result into JSON.
Errors become status codes in one place (``_errors``), so every route reports problems the
same way:

    404 Not Found        no such run
    409 Conflict         the run's state doesn't allow this (e.g. resume a completed run)
    422 Unprocessable    the request or the config it asks for is invalid
    429 Too Many         the server already holds the maximum number of live runs
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, status
from fastapi.responses import JSONResponse

from genesis import __version__
from genesis.api import details, saved, stepping, stream
from genesis.api.runs import (
    InvalidRunRequest,
    RunConflict,
    RunManager,
    RunNotFound,
    TooManyRuns,
)
from genesis.api.schemas import (
    API_VERSION,
    ConfigSummary,
    Digest,
    ErrorBody,
    ExportResult,
    Health,
    OrganismDetail,
    ResetRequest,
    RunCreate,
    RunInfo,
    SavedRun,
    SpeedRequest,
    StepRequest,
)

ERRORS = {
    RunNotFound: status.HTTP_404_NOT_FOUND,
    RunConflict: status.HTTP_409_CONFLICT,
    InvalidRunRequest: status.HTTP_422_UNPROCESSABLE_CONTENT,
    TooManyRuns: status.HTTP_429_TOO_MANY_REQUESTS,
}
ERROR_RESPONSES = {code: {"model": ErrorBody} for code in ERRORS.values()}


def create_app(manager: RunManager | None = None) -> FastAPI:
    """A new app with its own RunManager (tests pass their own to stay independent).

    Every route is ``async def``: FastAPI runs plain ``def`` routes on a pool of threads, and
    a thread touching a simulation while the stepping loop does would corrupt it. Async
    routes run on the event loop, one at a time between ticks (stepping.py, D-048).
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        for run in app.state.manager.runs.values():  # shutting down: stop every loop
            stepping.stop(run)

    app = FastAPI(
        title="Genesis Lab API",
        version=str(API_VERSION),
        description="Drive seeded simulations; the server is the only authority (docs/API.md).",
        lifespan=lifespan,
    )
    app.state.manager = manager or RunManager()
    # Where saved runs are listed from and exports go (tests point these at temp folders).
    app.state.saved_roots = saved.SAVED_ROOTS
    app.state.export_root = saved.EXPORT_ROOT
    app.state.lake = saved.PROJECT_ROOT / saved.DEFAULT_LAKE
    _errors(app)

    @app.get("/api/health", response_model=Health)
    async def health() -> Health:
        return Health(status="ok", api_version=API_VERSION, genesis_version=__version__)

    @app.get("/api/configs", response_model=list[ConfigSummary])
    async def list_configs() -> list[ConfigSummary]:
        return app.state.manager.config_summaries()

    @app.get("/api/configs/{name}", responses=ERROR_RESPONSES)
    async def get_config(name: str) -> dict:
        """The full validated config, as stored in run.json."""
        return app.state.manager.load_config(name).model_dump(mode="json")

    @app.post(
        "/api/runs",
        response_model=RunInfo,
        status_code=status.HTTP_201_CREATED,
        responses=ERROR_RESPONSES,
    )
    async def create_run(request: RunCreate) -> RunInfo:
        return app.state.manager.create(request).info()

    @app.get("/api/runs", response_model=list[RunInfo])
    async def list_runs() -> list[RunInfo]:
        return [run.info() for run in app.state.manager.runs.values()]

    @app.get("/api/runs/{run_id}", response_model=RunInfo, responses=ERROR_RESPONSES)
    async def get_run(run_id: str) -> RunInfo:
        return app.state.manager.get(run_id).info()

    @app.delete(
        "/api/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT, responses=ERROR_RESPONSES
    )
    async def delete_run(run_id: str) -> None:
        app.state.manager.delete(run_id)

    @app.get("/api/runs/{run_id}/digest", response_model=Digest, responses=ERROR_RESPONSES)
    async def run_digest(run_id: str) -> Digest:
        """A fingerprint of the full state (hashes every organism ever: not for polling)."""
        run = app.state.manager.get(run_id)
        return Digest(run_id=run.run_id, tick=run.sim.tick, digest=run.sim.state_digest())

    @app.get(
        "/api/runs/{run_id}/organisms/{organism_id}",
        response_model=OrganismDetail,
        responses=ERROR_RESPONSES,
    )
    async def get_organism(run_id: str, organism_id: int) -> OrganismDetail:
        """One organism: family, genome, body and, with a brain, its latest decision."""
        return details.organism_detail(app.state.manager.get(run_id), organism_id)

    @app.post("/api/runs/{run_id}/export", response_model=ExportResult, responses=ERROR_RESPONSES)
    async def export_live_run(run_id: str, ingest: bool = True) -> ExportResult:
        """Save the run so far as a normal run folder (data/runs/live/), replaying it
        headlessly; optionally load it into the lake. The run must be paused or finished."""
        return await saved.export_run(
            app.state.manager.get(run_id),
            app.state.export_root,
            app.state.lake if ingest else None,
        )

    @app.get("/api/saved-runs", response_model=list[SavedRun])
    async def list_saved_runs(experiment_id: str | None = None, limit: int = 200) -> list[SavedRun]:
        """Recorded run folders, newest first (up to ``limit``, at most 1,000)."""
        limit = max(1, min(limit, 1000))
        # Reading hundreds of run.json files takes ~0.25 s: do it off the event loop so
        # running simulations don't stall. Safe in a thread: it touches no simulation.
        return await asyncio.to_thread(
            saved.saved_runs, app.state.saved_roots, experiment_id, limit
        )

    @app.websocket("/api/runs/{run_id}/stream")
    async def run_stream(websocket: WebSocket, run_id: str) -> None:
        """Live snapshots (stream.py): hello, then the newest state at most ``fps`` per second."""
        await stream.stream(websocket, app.state.manager, run_id)

    # --- Controls: each returns the run's state afterwards ---------------------------------

    @app.post("/api/runs/{run_id}/resume", response_model=RunInfo, responses=ERROR_RESPONSES)
    async def resume_run(run_id: str) -> RunInfo:
        """Start (or continue) running in the background at the run's speed."""
        run = app.state.manager.get(run_id)
        stepping.resume(run)
        return run.info()

    @app.post("/api/runs/{run_id}/pause", response_model=RunInfo, responses=ERROR_RESPONSES)
    async def pause_run(run_id: str) -> RunInfo:
        """Stop after the tick in progress."""
        run = app.state.manager.get(run_id)
        stepping.pause(run)
        return run.info()

    @app.post("/api/runs/{run_id}/step", response_model=RunInfo, responses=ERROR_RESPONSES)
    async def step_run(run_id: str, request: StepRequest | None = None) -> RunInfo:
        """Take exactly ``ticks`` ticks now (default 1), then stay paused."""
        run = app.state.manager.get(run_id)
        stepping.step(run, (request or StepRequest()).ticks)
        return run.info()

    @app.put("/api/runs/{run_id}/speed", response_model=RunInfo, responses=ERROR_RESPONSES)
    async def set_speed(run_id: str, request: SpeedRequest) -> RunInfo:
        """Change the target speed; takes effect at once, even while running."""
        run = app.state.manager.get(run_id)
        run.speed = request.ticks_per_second
        return run.info()

    @app.post("/api/runs/{run_id}/reset", response_model=RunInfo, responses=ERROR_RESPONSES)
    async def reset_run(run_id: str, request: ResetRequest | None = None) -> RunInfo:
        """Replace the run with a fresh one from tick 0 (a new run ID)."""
        return app.state.manager.reset(run_id, (request or ResetRequest()).seed).info()

    return app


def _errors(app: FastAPI) -> None:
    for error_type, code in ERRORS.items():

        async def handler(_: Request, exc: Exception, code: int = code) -> JSONResponse:
            message = exc.args[0] if exc.args else str(exc)
            return JSONResponse(status_code=code, content={"detail": message})

        app.add_exception_handler(error_type, handler)
