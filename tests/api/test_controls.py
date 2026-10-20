"""Tests for run controls: pause, resume, step, speed, reset; and the key promise that a run
steered through the API passes through exactly the states of a headless run."""

import time

import pytest
from fastapi.testclient import TestClient

from genesis.analytics.experiments import apply_changes
from genesis.api.app import create_app
from genesis.api.runs import RunManager
from genesis.core.config import load_config
from genesis.core.simulation import Simulation


@pytest.fixture
def client(tmp_path):
    # The context manager keeps the app's event loop alive between requests, so a run's
    # background loop really runs while the test waits. Exports go to a temp folder, never
    # into the project's data/.
    app = create_app(RunManager())
    app.state.saved_roots = (tmp_path / "runs",)
    app.state.export_root = tmp_path / "runs" / "live"
    app.state.lake = tmp_path / "lake"
    with TestClient(app) as c:
        yield c


def create(client, **body) -> dict:
    response = client.post("/api/runs", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def post(client, run_id: str, action: str, body: dict | None = None) -> dict:
    response = client.post(f"/api/runs/{run_id}/{action}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def wait_for(client, run_id: str, state: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["state"] == state:
            return run
        time.sleep(0.01)
    raise AssertionError(f"run never became {state}: {run}")


def headless_digest(config_name: str, seed: int, ticks: int) -> str:
    config = apply_changes(
        load_config(f"configs/{config_name}.yaml"), {"run.seed": seed, "run.max_ticks": ticks}
    )
    sim = Simulation(config)
    sim.run()
    return sim.state_digest()


# --- the promise: the API never changes what happens -----------------------------------------


@pytest.mark.parametrize("config", ["evolution", "neural"])
def test_a_run_steered_through_the_api_is_bit_identical_to_a_headless_run(client, config):
    """Steps, pauses, speed changes and running flat out, in any mix: same final state."""
    ticks = 400
    run = create(client, config=config, seed=11, max_ticks=ticks)
    rid = run["run_id"]
    post(client, rid, "step")  # 1 tick from idle
    post(client, rid, "step", {"ticks": 25})
    client.put(f"/api/runs/{rid}/speed", json={"ticks_per_second": 2000})
    post(client, rid, "resume")
    time.sleep(0.03)
    paused = post(client, rid, "pause")
    assert paused["state"] == "paused" and 26 < paused["tick"] < ticks
    post(client, rid, "step", {"ticks": 7})
    client.put(f"/api/runs/{rid}/speed", json={"ticks_per_second": None})  # flat out
    post(client, rid, "resume")
    done = wait_for(client, rid, "completed")
    assert done["tick"] == ticks
    digest = client.get(f"/api/runs/{rid}/digest").json()
    assert digest["tick"] == ticks
    assert digest["digest"] == headless_digest(config, 11, ticks)


# --- each control ---------------------------------------------------------------------------


def test_step_takes_exactly_the_requested_ticks_and_leaves_the_run_paused(client):
    rid = create(client, max_ticks=100)["run_id"]
    assert post(client, rid, "step")["tick"] == 1
    after = post(client, rid, "step", {"ticks": 9})
    assert after["tick"] == 10 and after["state"] == "paused"


def test_stepping_past_the_end_completes_the_run(client):
    rid = create(client, max_ticks=50)["run_id"]
    done = post(client, rid, "step", {"ticks": 10_000})
    assert done["tick"] == 50 and done["state"] == "completed"


def test_pause_holds_the_run_still(client):
    rid = create(client, max_ticks=100_000)["run_id"]
    client.put(f"/api/runs/{rid}/speed", json={"ticks_per_second": None})
    post(client, rid, "resume")
    time.sleep(0.05)
    tick = post(client, rid, "pause")["tick"]
    assert tick > 0
    time.sleep(0.1)
    assert client.get(f"/api/runs/{rid}").json()["tick"] == tick  # nothing moved


def test_speed_spaces_ticks_out_in_time(client):
    rid = create(client, max_ticks=100_000)["run_id"]
    client.put(f"/api/runs/{rid}/speed", json={"ticks_per_second": 100})
    post(client, rid, "resume")
    time.sleep(0.5)
    tick = post(client, rid, "pause")["tick"]
    # About 50 ticks; generous bounds because CI machines and laptops are busy.
    assert 15 <= tick <= 80, tick


def test_impossible_controls_are_409_and_change_nothing(client):
    rid = create(client, max_ticks=20)["run_id"]
    assert client.post(f"/api/runs/{rid}/pause").status_code == 409  # idle can't pause
    post(client, rid, "step", {"ticks": 20})  # completed
    for action in ("resume", "pause", "step"):
        response = client.post(f"/api/runs/{rid}/{action}")
        assert response.status_code == 409, action
        assert "completed" in response.json()["detail"]
    assert client.get(f"/api/runs/{rid}").json()["tick"] == 20


def test_stepping_a_running_run_is_refused(client):
    rid = create(client, max_ticks=100_000)["run_id"]
    post(client, rid, "resume")
    response = client.post(f"/api/runs/{rid}/step")
    assert response.status_code == 409 and "pause it before stepping" in response.json()["detail"]
    post(client, rid, "pause")


def test_a_failing_tick_marks_the_run_failed_with_the_reason(client):
    rid = create(client, max_ticks=100)["run_id"]
    run = client.app.state.manager.get(rid)

    def broken_step():
        raise RuntimeError("energy went missing")

    run.sim.step = broken_step
    failed = post(client, rid, "step")
    assert failed["state"] == "failed"
    assert "RuntimeError at tick 0: energy went missing" in failed["error"]
    assert client.post(f"/api/runs/{rid}/resume").status_code == 409


def test_reset_starts_over_with_a_new_id_keeping_speed(client):
    old = create(client, config="neural", seed=3, max_ticks=500)
    client.put(f"/api/runs/{old['run_id']}/speed", json={"ticks_per_second": 77})
    post(client, old["run_id"], "step", {"ticks": 40})
    fresh = post(client, old["run_id"], "reset")
    assert fresh["run_id"] != old["run_id"] and fresh["tick"] == 0 and fresh["state"] == "idle"
    assert fresh["seed"] == 3 and fresh["speed"] == 77
    assert client.get(f"/api/runs/{old['run_id']}").status_code == 404
    reseeded = post(client, fresh["run_id"], "reset", {"seed": 8})
    assert reseeded["seed"] == 8 and "-s8-" in reseeded["run_id"]


def test_pause_then_resume_at_once_leaves_exactly_one_loop(client):
    """With a target speed the loop sleeps between ticks (up to 50 ms). Pausing and resuming
    inside that sleep used to leave the old loop asleep with the run paused; it then woke to
    find the run running again and carried on beside the new loop: two loops stepping one
    run (double speed, and a loop that outlives the run's deletion)."""
    rid = create(client, max_ticks=1_000_000)["run_id"]
    client.put(f"/api/runs/{rid}/speed", json={"ticks_per_second": 20})
    run = client.app.state.manager.get(rid)
    post(client, rid, "resume")
    first = run.task
    post(client, rid, "pause")
    post(client, rid, "resume")  # well inside the old loop's 50 ms sleep
    second = run.task
    assert second is not first
    deadline = time.monotonic() + 1.0
    while not first.done() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert first.done(), "the loop from before the pause is still stepping the run"
    post(client, rid, "pause")


CROWD = {  # a neural run whose ticks are slow: ~600 organisms (the lab's limit is 2,000)
    "organisms.initial_count": 600,
    "organisms.max_population": 600,
    "organisms.initial_energy": 200.0,
    "food.max_count": 600,
    "food.initial_count": 300,
    "food.regrowth_per_tick": 30.0,
    "run.stop_on_extinction": False,
}


def test_a_long_step_yields_to_other_requests_and_refuses_overlapping_controls(client):
    """A big step used to run to completion inside one request: 1,000 ticks of a 2,000-organism
    neural run stalled every run, request and viewer for 18 s, and viewers were dropped
    (keepalive ping timeout) past 40 s. It now works in slices like the background loop."""
    from concurrent.futures import ThreadPoolExecutor

    rid = create(client, config="neural", seed=4, max_ticks=1_000_000, changes=CROWD)["run_id"]
    run = client.app.state.manager.get(rid)
    ticks = 400  # several seconds of stepping at this size
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(post, client, rid, "step", {"ticks": ticks})
        deadline = time.monotonic() + 10
        while not run.stepping and time.monotonic() < deadline:
            time.sleep(0.001)
        assert run.stepping
        t0 = time.perf_counter()
        assert client.get("/api/health").status_code == 200
        assert time.perf_counter() - t0 < 1.0, "a request waited for the whole step"
        mid = client.get(f"/api/runs/{rid}").json()
        assert mid["state"] == "paused" and 0 < mid["tick"] < ticks  # visible progress
        for action in ("export", "resume", "step"):
            assert run.stepping, "the step finished before the checks: make it longer"
            response = client.post(f"/api/runs/{rid}/{action}")
            assert response.status_code == 409, (action, response.text)
            assert "step" in response.json()["detail"] or "pause" in response.json()["detail"]
        done = future.result()
    assert done["tick"] == ticks and done["state"] == "paused" and not run.stepping
    assert post(client, rid, "step")["tick"] == ticks + 1  # controls work again afterwards


def test_deleting_a_run_mid_step_stops_the_step(client):
    from concurrent.futures import ThreadPoolExecutor

    rid = create(client, config="neural", seed=4, max_ticks=1_000_000, changes=CROWD)["run_id"]
    run = client.app.state.manager.get(rid)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(client.post, f"/api/runs/{rid}/step", json={"ticks": 10_000})
        while not run.stepping:
            time.sleep(0.001)
        assert client.delete(f"/api/runs/{rid}").status_code == 204
        t0 = time.perf_counter()
        response = future.result()
        assert time.perf_counter() - t0 < 2.0, "the step kept going after the run was deleted"
    assert response.status_code == 200 and response.json()["tick"] < 10_000
    assert run.dropped and not run.stepping


def test_deleting_a_running_run_stops_its_loop(client):
    rid = create(client, max_ticks=1_000_000)["run_id"]
    post(client, rid, "resume")
    task = client.app.state.manager.get(rid).task
    assert client.delete(f"/api/runs/{rid}").status_code == 204
    deadline = time.monotonic() + 5
    while not task.done() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert task.cancelled()


def test_shutting_the_server_down_stops_every_loop():
    manager = RunManager()
    with TestClient(create_app(manager)) as client:
        rid = create(client, max_ticks=1_000_000)["run_id"]
        post(client, rid, "resume")
        task = manager.get(rid).task
    assert task.done()


@pytest.mark.parametrize(
    "path, body",
    [
        ("speed", {"ticks_per_second": 0}),
        ("speed", {"ticks_per_second": -5}),
        ("speed", {"ticks_per_second": 1e9}),
        ("step", {"ticks": 0}),
        ("step", {"ticks": 50_000}),
        ("reset", {"seed": -1}),
    ],
)
def test_out_of_range_controls_are_422(client, path, body):
    rid = create(client)["run_id"]
    method = client.put if path == "speed" else client.post
    assert method(f"/api/runs/{rid}/{path}", json=body).status_code == 422
