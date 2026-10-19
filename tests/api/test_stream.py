"""Tests for the snapshot stream: shape and truth of snapshots, bounded rate, shared state
across viewers, disconnects, and runs that disappear."""

import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from genesis.api import stream
from genesis.api.app import create_app
from genesis.api.runs import RunManager


@pytest.fixture
def client():
    with TestClient(create_app(RunManager())) as c:
        yield c


def create(client, **body) -> str:
    response = client.post("/api/runs", json=body)
    assert response.status_code == 201, response.text
    return response.json()["run_id"]


def connect(client, run_id: str, fps: int = 30):
    return client.websocket_connect(f"/api/runs/{run_id}/stream?fps={fps}")


def wait_until(predicate, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition never became true"
        time.sleep(0.01)


# --- what a snapshot says --------------------------------------------------------------------


def test_hello_then_a_snapshot_that_matches_the_simulation(client):
    rid = create(client, config="neural", seed=2, max_ticks=500)
    client.post(f"/api/runs/{rid}/step", json={"ticks": 40})
    run = client.app.state.manager.get(rid)
    with connect(client, rid) as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["version"] == stream.SNAPSHOT_VERSION
        assert hello["world"] == {"width": 200.0, "height": 200.0}
        assert hello["run"]["run_id"] == rid and hello["run"]["tick"] == 40
        snap = ws.receive_json()
    assert snap["type"] == "snapshot" and snap["tick"] == 40 and snap["state"] == "paused"
    organisms = snap["organisms"]
    assert organisms["id"] == [o.id for o in run.sim.organisms]
    assert snap["population"] == len(run.sim.organisms)
    assert all(len(organisms[c]) == snap["population"] for c in organisms)
    assert organisms["x"] == [round(o.x, 2) for o in run.sim.organisms]
    assert organisms["founder"] == [o.founder_id for o in run.sim.organisms]
    assert len(snap["food"]["x"]) == len(snap["food"]["y"]) == run.sim.world.food.count
    assert snap["last_tick"]["births"] == run.last_summary.births


def test_a_step_produces_the_next_snapshot(client):
    rid = create(client, max_ticks=100)
    with connect(client, rid) as ws:
        ws.receive_json()  # hello
        assert ws.receive_json()["tick"] == 0
        client.post(f"/api/runs/{rid}/step")
        assert ws.receive_json()["tick"] == 1
        client.post(f"/api/runs/{rid}/step", json={"ticks": 5})
        assert ws.receive_json()["tick"] == 6


def test_an_extinct_world_streams_empty_columns(client):
    rid = create(
        client,
        max_ticks=20,
        changes={"food.initial_count": 0, "food.regrowth_per_tick": 0.0,
                 "organisms.initial_energy": 0.5, "run.stop_on_extinction": False},
    )  # fmt: skip
    client.post(f"/api/runs/{rid}/step", json={"ticks": 3})
    with connect(client, rid) as ws:
        ws.receive_json()
        snap = ws.receive_json()
    assert snap["population"] == 0 and snap["organisms"]["id"] == []
    assert snap["last_tick"]["mean_energy"] is None  # no organisms: no mean, not NaN


# --- viewers share one truth; slow or many viewers don't matter ------------------------------


def test_two_viewers_receive_the_identical_snapshot(client):
    rid = create(client, config="neural", max_ticks=300)
    client.post(f"/api/runs/{rid}/step", json={"ticks": 25})
    with connect(client, rid) as a, connect(client, rid) as b:
        a.receive_json(), b.receive_json()
        assert a.receive_text() == b.receive_text()
        assert client.get(f"/api/runs/{rid}").json()["viewers"] == 2


def test_a_snapshot_is_built_once_per_tick_however_many_watch(client, monkeypatch):
    builds = []
    original = stream.build_snapshot
    monkeypatch.setattr(stream, "build_snapshot", lambda run: builds.append(1) or original(run))
    rid = create(client, max_ticks=100)
    with connect(client, rid) as a, connect(client, rid) as b, connect(client, rid) as c:
        for ws in (a, b, c):
            ws.receive_json(), ws.receive_json()
    assert len(builds) == 1


def test_frames_are_capped_and_coalesced_while_the_run_races_ahead(client):
    rid = create(client, max_ticks=1_000_000)
    client.put(f"/api/runs/{rid}/speed", json={"ticks_per_second": None})
    with connect(client, rid, fps=5) as ws:
        ws.receive_json(), ws.receive_json()  # hello, tick 0
        client.post(f"/api/runs/{rid}/resume")
        time.sleep(1.0)
        final_tick = client.post(f"/api/runs/{rid}/pause").json()["tick"]
        frames = []
        while True:
            snap = ws.receive_json()
            frames.append(snap["tick"])
            if snap["state"] == "paused":
                break
    assert final_tick > 300  # the run went flat out...
    assert len(frames) <= 5 * 1.0 + 4  # ...but the viewer got about 5 frames a second
    assert frames == sorted(frames) and frames[-1] == final_tick  # newest state, in order


def test_a_viewer_that_never_reads_does_not_slow_the_run(client):
    rid = create(client, max_ticks=1_000_000)
    client.put(f"/api/runs/{rid}/speed", json={"ticks_per_second": None})
    with connect(client, rid, fps=30):  # connected, never reads
        client.post(f"/api/runs/{rid}/resume")
        time.sleep(0.5)
        tick = client.post(f"/api/runs/{rid}/pause").json()["tick"]
    assert tick > 300


def test_viewers_are_counted_and_forgotten_when_they_leave(client):
    rid = create(client, max_ticks=100)  # idle: nothing is being sent while they're away
    with connect(client, rid) as ws:
        ws.receive_json()
        wait_until(lambda: client.get(f"/api/runs/{rid}").json()["viewers"] == 1)
    wait_until(lambda: client.get(f"/api/runs/{rid}").json()["viewers"] == 0)


# --- runs that disappear, and bad requests ---------------------------------------------------


def test_deleting_a_run_tells_its_viewers_and_closes(client):
    rid = create(client, max_ticks=100)
    with connect(client, rid) as ws:
        ws.receive_json(), ws.receive_json()
        client.delete(f"/api/runs/{rid}")
        assert ws.receive_json() == {"type": "gone", "run_id": rid, "replaced_by": None}
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_resetting_a_run_points_its_viewers_at_the_new_one(client):
    rid = create(client, max_ticks=100)
    with connect(client, rid) as ws:
        ws.receive_json(), ws.receive_json()
        new_id = client.post(f"/api/runs/{rid}/reset").json()["run_id"]
        gone = ws.receive_json()
    assert gone["type"] == "gone" and gone["replaced_by"] == new_id


def test_an_unknown_run_is_refused_with_a_close_code(client):
    with connect(client, "nope") as ws:
        assert ws.receive_json()["type"] == "gone"
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == stream.CLOSE_UNKNOWN_RUN


@pytest.mark.parametrize("fps", ["0", "31", "fast"])
def test_a_bad_frame_rate_is_refused(client, fps):
    rid = create(client)
    with (
        client.websocket_connect(f"/api/runs/{rid}/stream?fps={fps}") as ws,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        ws.receive_json()
    assert closed.value.code == stream.CLOSE_BAD_REQUEST


# --- a real server ---------------------------------------------------------------------------


def test_a_real_server_accepts_websocket_connections():
    """The test client above calls the app directly, which hides one class of bug: the real
    server (uvicorn) needs a WebSocket library installed to accept connections at all. This
    starts uvicorn on a free port and connects with a real WebSocket client."""
    import asyncio
    import json
    import socket
    import threading

    import httpx2
    import uvicorn
    import websockets

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(RunManager()), host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        wait_until(lambda: server.started)
        base = f"127.0.0.1:{port}/api"
        rid = httpx2.post(f"http://{base}/runs", json={"max_ticks": 50}).json()["run_id"]

        async def watch() -> tuple[dict, dict]:
            async with websockets.connect(f"ws://{base}/runs/{rid}/stream") as ws:
                return json.loads(await ws.recv()), json.loads(await ws.recv())

        hello, snapshot = asyncio.run(watch())
        assert hello["type"] == "hello" and snapshot["type"] == "snapshot"
        assert snapshot["population"] == 30
    finally:
        server.should_exit = True
        thread.join(timeout=10)
