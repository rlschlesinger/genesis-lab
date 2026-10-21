"""Advancing live runs: single steps on request, and a background loop while running.

Concurrency model (D-048). Everything that touches a simulation runs on the server's one
event loop thread: the routes are ``async def`` and the loop below is an asyncio task. An
asyncio task only gives way to others at an ``await``, and a tick contains none, so a tick
always runs to completion before any request is handled. No locks are needed because no two
pieces of code can ever be inside a simulation at the same time.

Wall-clock time decides *how many* ticks happen, never *which*: each tick is the next tick of
the seed's sequence, so a run steered through the API (paused, stepped, sped up) passes
through exactly the states a headless run does. Playback speed only spaces them out.

While running, the loop works in slices: it steps for at most ``SLICE_SECONDS`` of CPU time,
then awaits, so requests (pause, read state, WebSocket snapshots in 5.3) are answered within
a slice. With a target speed it keeps a *tick budget*: elapsed time x speed ticks are due; a
fractional remainder carries over; after a stall (a slow machine, a sleeping laptop) the
backlog is capped at ``MAX_BACKLOG_SECONDS`` worth of ticks rather than replayed in a burst.
"""

from __future__ import annotations

import asyncio
import math
import time

from genesis.api.runs import LiveRun, RunConflict
from genesis.api.schemas import RunState

SLICE_SECONDS = 0.010  # longest stretch of stepping before requests get a turn
MAX_BACKLOG_SECONDS = 0.25
MAX_IDLE_SLEEP = 0.05  # with a slow target speed, wake at least this often to notice a pause


def step_once(run: LiveRun) -> None:
    """Take one tick, then record completion or failure. Never raises for simulation errors:
    a failing tick (e.g. the energy ledger check) marks the run failed with the reason."""
    if run.sim.finished:
        run.move_to(RunState.COMPLETED)
        return
    try:
        run.last_summary = run.sim.step()
    except Exception as exc:  # noqa: BLE001 - recorded on the run and reported to the client
        run.error = f"{type(exc).__name__} at tick {run.sim.tick}: {exc}"
        run.move_to(RunState.FAILED)
        return
    sim = run.sim
    run.history.append(run.last_summary, sim.last_decision, sim.predator_summary)
    # Where this tick's captures happened (the predator's position as it ate), for the plate.
    tick = run.last_summary.tick
    for event in sim.predator_events_this_tick:
        if event.kind == "meal" and event.tick == tick:
            run.recent_captures.append((tick, event.x, event.y))
    if run.sim.finished:
        run.move_to(RunState.COMPLETED)


async def step(run: LiveRun, ticks: int) -> int:
    """Take up to ``ticks`` ticks now (idle or paused only). Returns how many were taken;
    fewer if the run completed or failed on the way, or was deleted or reset meanwhile.

    Like the background loop, it works in slices of ``SLICE_SECONDS`` and yields between
    them: 1,000 ticks of a 2,000-organism neural run take ~18 s, and taken in one go they
    stalled every other run, request and viewer for that long (measured in the Milestone 5
    review). While a step is in progress the run stays ``paused`` and ``run.stepping`` is set,
    so resume, another step and export are refused (409) rather than interleaved.
    """
    if run.state not in (RunState.IDLE, RunState.PAUSED):
        raise RunConflict(f"run {run.run_id} is {run.state}; pause it before stepping")
    if run.stepping:
        raise RunConflict(f"run {run.run_id} is already taking a step; wait for it to finish")
    if run.state is RunState.IDLE:
        run.move_to(RunState.PAUSED)
    run.stepping = True
    taken = 0
    try:
        while taken < ticks and run.state is RunState.PAUSED and not run.dropped:
            slice_end = time.perf_counter() + SLICE_SECONDS
            while (
                taken < ticks and run.state is RunState.PAUSED and time.perf_counter() < slice_end
            ):
                step_once(run)
                taken += 1
            if taken < ticks and run.state is RunState.PAUSED:
                await asyncio.sleep(0)  # let requests and viewers through, then carry on
    finally:
        run.stepping = False
    return taken


def resume(run: LiveRun) -> None:
    """Start the background loop (idle or paused only)."""
    if run.stepping:
        raise RunConflict(f"run {run.run_id} is taking a step; wait for it to finish")
    run.move_to(RunState.RUNNING)  # raises RunConflict from any other state
    # A loop from before a pause may still be asleep (it only notices the pause when it next
    # wakes). Left alone it would wake to find the run running again and step it beside the
    # new loop. Cancel it: cancellation is delivered at its sleep, never inside a tick.
    stop(run)
    run.task = asyncio.get_running_loop().create_task(run_loop(run), name=run.run_id)


def pause(run: LiveRun) -> None:
    """Stop the loop after the tick in progress (the loop checks the state between ticks).

    Only a running run can be paused. The state table allows idle -> paused (a single step
    from idle leaves the run paused), so that move alone would let "pause" succeed on a run
    that never started, which means nothing.
    """
    if run.state is not RunState.RUNNING:
        raise RunConflict(f"run {run.run_id} is {run.state}; only a running run can be paused")
    run.move_to(RunState.PAUSED)


def stop(run: LiveRun) -> None:
    """Cancel the loop, if any (deleting a run, or shutting the server down)."""
    if run.task is not None and not run.task.done():
        run.task.cancel()
    run.task = None


async def run_loop(run: LiveRun) -> None:
    budget = 0.0
    last = time.perf_counter()
    me = asyncio.current_task()
    # Only the run's current loop may step it; a superseded one stops (see resume()).
    while run.state is RunState.RUNNING and run.task is me:
        now = time.perf_counter()
        if run.speed is not None:
            budget = min(budget + (now - last) * run.speed, run.speed * MAX_BACKLOG_SECONDS)
        last = now
        slice_end = now + SLICE_SECONDS
        while run.state is RunState.RUNNING and run.task is me and time.perf_counter() < slice_end:
            if run.speed is not None:
                if budget < 1.0:
                    break
                budget -= 1.0
            step_once(run)
        if run.state is not RunState.RUNNING or run.task is not me:
            break
        if run.speed is None or budget >= 1.0:
            await asyncio.sleep(0)  # let requests through, then carry on
        else:
            wait = (1.0 - budget) / run.speed
            await asyncio.sleep(min(wait, MAX_IDLE_SLEEP) if math.isfinite(wait) else 0)
