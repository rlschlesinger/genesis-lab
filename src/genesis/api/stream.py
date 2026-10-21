"""Live snapshots over a WebSocket: what a browser needs to draw a run, at a bounded rate.

    ws://127.0.0.1:8765/api/runs/{run_id}/stream?fps=15

HTTP is request-and-answer: the browser must ask every time. A WebSocket stays open and the
server can push messages whenever it likes, which suits a world that changes many times a
second. Three message types, all JSON with a ``type`` field (D-049):

    hello      once, on connect: protocol version, the run (as GET /runs/{id}), world size
    snapshot   the run's newest state: tick, state, counts, food, organisms (columnar), and in
               a world with predators the predators and the latest captures (version 2, 6.5)
    gone       the run was deleted or reset (``replaced_by`` names the new run); then close

Snapshots are **read-only views**: positions are rounded for display (0.01 world units), and
nothing a viewer does can change the simulation. The exact state stays on the server
(``GET /runs/{id}/digest``).

**Rate and memory.** There is no queue. Each viewer has one sender task that, at most
``fps`` times a second, checks whether the run changed since its last message and, if so,
sends the *newest* snapshot. Ticks in between are never sent (coalesced), so a slow viewer
simply gets fewer frames, the server holds at most one message per viewer, and the
simulation never waits for anyone. A snapshot is built once per tick and shared by every
viewer (``LiveRun.snapshot_cache``).
"""

from __future__ import annotations

import asyncio
import json

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

from genesis.api.runs import LiveRun, RunManager

SNAPSHOT_VERSION = 2  # 2 (6.5): fullness, predators, captures
MAX_FPS = 30
DEFAULT_FPS = 15
POSITION_DECIMALS = 2  # 0.01 world units: far below a pixel at any sensible zoom
CLOSE_UNKNOWN_RUN = 4404  # application close codes live in 4000-4999
CLOSE_BAD_REQUEST = 4422


def snapshot_key(run: LiveRun) -> tuple:
    """Everything a snapshot shows that can change; a new key means a new snapshot."""
    return (run.sim.tick, run.state, run.error, run.speed)


def build_snapshot(run: LiveRun) -> dict:
    sim = run.sim
    living = sim.organisms
    food = sim.world.food.positions
    summary = run.last_summary

    def column(values, decimals: int | None = None) -> list:
        array = np.asarray(values, dtype=np.float64)
        return (np.round(array, decimals) if decimals is not None else array).tolist()

    def bodies(group) -> dict:
        """One species, columnar. fullness: energy as a share of the organism's own
        reproduction threshold (0-1, rounded), which the plate draws as how full a cell is."""
        return {
            "id": [o.id for o in group],
            "x": column([o.x for o in group], POSITION_DECIMALS),
            "y": column([o.y for o in group], POSITION_DECIMALS),
            "heading": column([o.heading for o in group], 3),
            "energy": column([o.energy for o in group], 2),
            "fullness": column(
                [min(1.0, o.energy / o.traits.reproduction_threshold) for o in group], 2
            ),
            "generation": [o.generation for o in group],
            "founder": [o.founder_id for o in group],
        }

    hunted = run.config.predators is not None

    return {
        "type": "snapshot",
        "version": SNAPSHOT_VERSION,
        "run_id": run.run_id,
        "tick": sim.tick,  # ticks completed: this is the state after tick - 1
        "state": str(run.state),
        "speed": run.speed,
        "error": run.error,
        "population": len(living),
        "last_tick": None
        if summary is None
        else {
            "births": summary.births,
            "deaths": summary.deaths,
            "food_eaten": summary.food_eaten,
            "mean_energy": None if summary.population == 0 else summary.mean_energy,
            "lineages": summary.lineages,
        },
        "food": {
            "x": column(food[:, 0], POSITION_DECIMALS),
            "y": column(food[:, 1], POSITION_DECIMALS),
        },
        "organisms": bodies(living),
        # Worlds with predators (6.5): the predators, and where the latest captures happened
        # (newest last; a viewer draws the ones newer than its last picture's).
        "predators": bodies(sim.predators) if hunted else None,
        "captures": [
            {"tick": t, "x": round(x, POSITION_DECIMALS), "y": round(y, POSITION_DECIMALS)}
            for t, x, y in run.recent_captures
        ],
    }


def snapshot_json(run: LiveRun) -> str:
    """The run's current snapshot as JSON text, built at most once per change."""
    key = snapshot_key(run)
    if run.snapshot_cache is None or run.snapshot_cache[0] != key:
        run.snapshot_cache = (key, json.dumps(build_snapshot(run), separators=(",", ":")))
    return run.snapshot_cache[1]


def hello(run: LiveRun) -> dict:
    return {
        "type": "hello",
        "version": SNAPSHOT_VERSION,
        "run": run.info().model_dump(mode="json"),
        "world": {"width": run.config.world.width, "height": run.config.world.height},
    }


async def stream(websocket: WebSocket, manager: RunManager, run_id: str) -> None:
    await websocket.accept()
    try:
        fps = int(websocket.query_params.get("fps", DEFAULT_FPS))
    except ValueError:
        fps = 0
    if not 1 <= fps <= MAX_FPS:
        await websocket.close(code=CLOSE_BAD_REQUEST, reason=f"fps must be 1-{MAX_FPS}")
        return
    run = manager.runs.get(run_id)
    if run is None:
        await websocket.send_json(_gone(manager, run_id))
        await websocket.close(code=CLOSE_UNKNOWN_RUN, reason="no such run")
        return

    run.viewers += 1
    # A second task only listens: it notices a closed tab even while nothing is being sent
    # (a paused run sends nothing, so a failed send can't be relied on to notice).
    listener = asyncio.create_task(_until_disconnect(websocket))
    try:
        await websocket.send_json(hello(run))
        last_key = None
        while not listener.done():
            current = manager.runs.get(run_id)
            if current is not run:  # deleted or reset
                await websocket.send_json(_gone(manager, run_id))
                await websocket.close()
                return
            key = snapshot_key(run)
            if key != last_key:
                await websocket.send_text(snapshot_json(run))
                last_key = key
            # Wait one frame, or less if the viewer leaves meanwhile.
            await asyncio.wait({listener}, timeout=1.0 / fps)
    except WebSocketDisconnect:
        pass  # the viewer left mid-send
    finally:
        run.viewers -= 1
        listener.cancel()


async def _until_disconnect(websocket: WebSocket) -> None:
    """Read (and ignore) whatever the viewer sends, until it disconnects."""
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
    except (WebSocketDisconnect, RuntimeError):
        return


def _gone(manager: RunManager, run_id: str) -> dict:
    return {"type": "gone", "run_id": run_id, "replaced_by": manager.replaced.get(run_id)}
