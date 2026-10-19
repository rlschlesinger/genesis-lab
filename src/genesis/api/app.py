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

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from genesis import __version__
from genesis.api.runs import (
    InvalidRunRequest,
    RunConflict,
    RunManager,
    RunNotFound,
    TooManyRuns,
)
from genesis.api.schemas import API_VERSION, ConfigSummary, ErrorBody, Health, RunCreate, RunInfo

ERRORS = {
    RunNotFound: status.HTTP_404_NOT_FOUND,
    RunConflict: status.HTTP_409_CONFLICT,
    InvalidRunRequest: status.HTTP_422_UNPROCESSABLE_CONTENT,
    TooManyRuns: status.HTTP_429_TOO_MANY_REQUESTS,
}
ERROR_RESPONSES = {code: {"model": ErrorBody} for code in ERRORS.values()}


def create_app(manager: RunManager | None = None) -> FastAPI:
    """A new app with its own RunManager (tests pass their own to stay independent)."""
    app = FastAPI(
        title="Genesis Lab API",
        version=str(API_VERSION),
        description="Drive seeded simulations; the server is the only authority (docs/API.md).",
    )
    app.state.manager = manager or RunManager()
    _errors(app)

    @app.get("/api/health", response_model=Health)
    def health() -> Health:
        return Health(status="ok", api_version=API_VERSION, genesis_version=__version__)

    @app.get("/api/configs", response_model=list[ConfigSummary])
    def list_configs() -> list[ConfigSummary]:
        return app.state.manager.config_summaries()

    @app.get("/api/configs/{name}", responses=ERROR_RESPONSES)
    def get_config(name: str) -> dict:
        """The full validated config, as stored in run.json."""
        return app.state.manager.load_config(name).model_dump(mode="json")

    @app.post(
        "/api/runs",
        response_model=RunInfo,
        status_code=status.HTTP_201_CREATED,
        responses=ERROR_RESPONSES,
    )
    def create_run(request: RunCreate) -> RunInfo:
        return app.state.manager.create(request).info()

    @app.get("/api/runs", response_model=list[RunInfo])
    def list_runs() -> list[RunInfo]:
        return [run.info() for run in app.state.manager.runs.values()]

    @app.get("/api/runs/{run_id}", response_model=RunInfo, responses=ERROR_RESPONSES)
    def get_run(run_id: str) -> RunInfo:
        return app.state.manager.get(run_id).info()

    @app.delete(
        "/api/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT, responses=ERROR_RESPONSES
    )
    def delete_run(run_id: str) -> None:
        app.state.manager.delete(run_id)

    return app


def _errors(app: FastAPI) -> None:
    for error_type, code in ERRORS.items():

        async def handler(_: Request, exc: Exception, code: int = code) -> JSONResponse:
            message = exc.args[0] if exc.args else str(exc)
            return JSONResponse(status_code=code, content={"detail": message})

        app.add_exception_handler(error_type, handler)
