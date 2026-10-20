"""Tests for organism details, saved runs and export-by-replay."""

import json

import pytest
from fastapi.testclient import TestClient

from genesis.analytics.inspector import inspect_tick
from genesis.analytics.runs import execute_run
from genesis.api import details
from genesis.api.app import create_app
from genesis.api.runs import RunManager
from genesis.api.schemas import RunCreate
from genesis.core.config import load_config, with_overrides
from genesis.intelligence.brain_inputs import parameter_names


@pytest.fixture
def client(tmp_path):
    app = create_app(RunManager())
    app.state.saved_roots = (tmp_path / "runs",)
    app.state.export_root = tmp_path / "runs" / "live"
    app.state.lake = tmp_path / "lake"
    with TestClient(app) as c:
        yield c


def create(client, **body) -> str:
    response = client.post("/api/runs", json=body)
    assert response.status_code == 201, response.text
    return response.json()["run_id"]


# --- who decided on the latest tick ----------------------------------------------------------


def test_deciders_rule_matches_the_truth_every_tick_through_births_and_deaths():
    run = RunManager().create(RunCreate(config="neural", seed=5, max_ticks=600))
    births = deaths = 0
    while not run.sim.finished:
        before = [o.id for o in run.sim.organisms]  # who is about to decide
        summary = run.sim.step()
        births, deaths = births + summary.births, deaths + summary.deaths
        assert details.deciders(run.sim) == before
    assert births > 50 and deaths > 20  # the rule was exercised, not just tick 0


def test_thought_is_exactly_what_genesis_inspect_replays():
    config = with_overrides(load_config("configs/neural.yaml"), seed=3, max_ticks=500)
    run = RunManager().create(RunCreate(config="neural", seed=3, max_ticks=500))
    for _ in range(201):
        run.sim.step()
    organism_id = run.sim.organisms[4].id
    live = details.thought(run.sim, organism_id)
    replay = inspect_tick(config, 200, organism_id)
    assert live.tick == 200
    assert live.inputs == replay.inputs.tolist()
    assert live.hidden == replay.hidden.tolist()
    assert live.outputs == replay.outputs.tolist()
    assert (live.turn, live.throttle) == (replay.turn, replay.throttle)


# --- organism details ------------------------------------------------------------------------


def test_organism_detail_has_family_genome_brain_and_thought(client):
    rid = create(client, config="neural", seed=2, max_ticks=1000)
    client.post(f"/api/runs/{rid}/step", json={"ticks": 400})
    sim = client.app.state.manager.get(rid).sim
    parent = next(o for o in sim.organisms if o.offspring_count > 0 and o.alive)
    body = client.get(f"/api/runs/{rid}/organisms/{parent.id}").json()
    kids = sorted(o.id for o in (*sim.organisms, *sim.dead) if o.parent_id == parent.id)
    assert body["children"] == kids and len(kids) == parent.offspring_count
    assert body["genome"]["speed"] == parent.genome.speed
    assert list(body["brain_weights"]) == parameter_names()
    assert body["thought"]["tick"] == 399 and len(body["thought"]["hidden"]) == 6
    assert body["thought"]["input_names"][0] == "food_seen"


def test_rule_based_organisms_have_no_brain_and_the_dead_stay_visible(client):
    rid = create(client, config="evolution", seed=4, max_ticks=1000)
    client.post(f"/api/runs/{rid}/step", json={"ticks": 600})
    sim = client.app.state.manager.get(rid).sim
    dead = sim.dead[0]
    body = client.get(f"/api/runs/{rid}/organisms/{dead.id}").json()
    assert body["alive"] is False and body["death_tick"] == dead.death_tick
    assert body["brain_weights"] is None and body["thought"] is None


def test_a_newborn_has_no_thought_until_it_has_decided(client):
    rid = create(client, config="neural", seed=6, max_ticks=5000)
    sim = client.app.state.manager.get(rid).sim
    for _ in range(2000):  # step until the latest tick produced a newborn
        client.post(f"/api/runs/{rid}/step")
        newborns = [o for o in sim.organisms if o.parent_id is not None
                    and o.birth_tick == sim.tick - 1]  # fmt: skip
        if newborns:
            break
    else:
        pytest.fail("no birth in 2,000 ticks")
    newborn = newborns[0]
    assert client.get(f"/api/runs/{rid}/organisms/{newborn.id}").json()["thought"] is None
    client.post(f"/api/runs/{rid}/step")  # now it has decided once
    assert client.get(f"/api/runs/{rid}/organisms/{newborn.id}").json()["thought"] is not None


def test_unknown_organisms_are_404(client):
    rid = create(client)
    assert client.get(f"/api/runs/{rid}/organisms/99999").status_code == 404


# --- export by replay ------------------------------------------------------------------------


def test_export_replays_the_live_run_exactly_and_loads_it_into_the_lake(client, tmp_path):
    rid = create(client, config="neural", seed=8, max_ticks=5000)
    client.put(f"/api/runs/{rid}/speed", json={"ticks_per_second": None})
    client.post(f"/api/runs/{rid}/step", json={"ticks": 37})
    client.post(f"/api/runs/{rid}/step", json={"ticks": 113})
    result = client.post(f"/api/runs/{rid}/export").json()
    assert result["matches_live_run"] is True and result["ticks"] == 150
    assert result["ingested"] is True and result["run_id"] == f"{rid}-t150"
    folder = tmp_path / "runs" / "live" / result["run_id"]
    meta = json.loads((folder / "run.json").read_text())
    assert meta["status"] == "completed" and meta["condition"] == "live"
    assert meta["config"]["run"]["max_ticks"] == 150
    assert (tmp_path / "lake" / "runs" / f"{result['run_id']}.parquet").exists()
    # The export is what `genesis run` writes for the same config and ticks, byte for byte.
    headless = tmp_path / "headless"
    config = with_overrides(load_config("configs/neural.yaml"), seed=8, max_ticks=150)
    execute_run(config, headless)
    for name in ("ticks.csv", "organisms.csv", "brains.csv", "behaviour.csv"):
        assert (folder / name).read_bytes() == (headless / name).read_bytes(), name


@pytest.mark.parametrize("situation", ["unstarted", "running", "failed"])
def test_export_is_refused_when_it_cannot_match_a_fixed_moment(client, situation):
    rid = create(client, max_ticks=100_000)
    run = client.app.state.manager.get(rid)
    if situation == "running":
        client.post(f"/api/runs/{rid}/resume")
    if situation == "failed":
        run.sim.step = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        client.post(f"/api/runs/{rid}/step")
    response = client.post(f"/api/runs/{rid}/export")
    assert response.status_code == 409
    if situation == "running":
        client.post(f"/api/runs/{rid}/pause")


# --- saved runs ------------------------------------------------------------------------------


def test_saved_runs_lists_folders_newest_first_and_filters(client, tmp_path):
    config = with_overrides(load_config("configs/default.yaml"), max_ticks=20)
    execute_run(config, tmp_path / "runs" / "a", experiment_id="E900")
    execute_run(with_overrides(config, seed=7), tmp_path / "runs" / "b")
    listed = client.get("/api/saved-runs").json()
    assert [r["path"] for r in listed] == ["b", "a"]  # newest first; names, not full paths
    assert listed[1]["experiment_id"] == "E900" and listed[0]["seed"] == 7
    assert [r["path"] for r in client.get("/api/saved-runs?experiment_id=E900").json()] == ["a"]
    rid = create(client, max_ticks=50)
    client.post(f"/api/runs/{rid}/step", json={"ticks": 10})
    client.post(f"/api/runs/{rid}/export?ingest=false")
    assert client.get("/api/saved-runs").json()[0]["condition"] == "live"


def test_viewing_and_selecting_never_change_the_simulation(client):
    """Everything the browser lab does while you look (stream, select, inspect) is a read.
    A run that was looked at hard must stay bit-identical to an identical run nobody saw."""
    watched = create(client, config="neural", seed=12, max_ticks=2000)
    untouched = create(client, config="neural", seed=12, max_ticks=2000)
    for rid in (watched, untouched):
        client.post(f"/api/runs/{rid}/step", json={"ticks": 120})
    sim = client.app.state.manager.get(watched).sim
    with client.websocket_connect(f"/api/runs/{watched}/stream") as ws:
        ws.receive_json(), ws.receive_json()
        for org in [*sim.organisms, *sim.dead][:60]:  # "select" sixty organisms
            assert client.get(f"/api/runs/{watched}/organisms/{org.id}").status_code == 200
        client.get(f"/api/runs/{watched}/digest")
    for rid in (watched, untouched):
        client.post(f"/api/runs/{rid}/step", json={"ticks": 80})
    digests = {client.get(f"/api/runs/{r}/digest").json()["digest"] for r in (watched, untouched)}
    assert len(digests) == 1
