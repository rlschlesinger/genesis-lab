"""Predator worlds through the API (Milestone 6, increment 6.5).

The stream carries predators and the latest captures; history, organism details and lineage
know which species an organism is; a run without predators says so with nulls.
"""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from genesis.api import stream
from genesis.api.app import create_app
from genesis.api.runs import RECENT_CAPTURES, RunManager

CONFIGS = Path(__file__).parents[2] / "configs"
# Seed 3's chasers catch prey within the first hundred ticks (6.3).
WORLD = {"config": "predators", "seed": 3, "max_ticks": 400}


@pytest.fixture
def client():
    with TestClient(create_app(RunManager())) as c:
        yield c


def stepped(client, ticks: int = 120, **body) -> str:
    rid = client.post("/api/runs", json={**WORLD, **body}).json()["run_id"]
    assert client.post(f"/api/runs/{rid}/step", json={"ticks": ticks}).status_code == 200
    return rid


def test_the_snapshot_carries_both_species_and_where_captures_happened(client):
    rid = stepped(client)
    run = client.app.state.manager.get(rid)
    snap = stream.build_snapshot(run)
    assert snap["version"] == stream.SNAPSHOT_VERSION >= 2  # predators arrived in version 2
    sim = run.sim
    hunters = snap["predators"]
    assert hunters["id"] == [o.id for o in sim.predators]
    for column in ("x", "y", "heading", "energy", "fullness", "generation", "founder"):
        assert len(hunters[column]) == len(sim.predators)
    for o, full in zip(sim.predators, hunters["fullness"], strict=True):
        assert full == round(min(1.0, o.energy / o.traits.reproduction_threshold), 2)
    assert all(0 <= f <= 1 for f in snap["organisms"]["fullness"])
    caught = sum(r for r in run.history.query()["captures"])
    assert 0 < len(snap["captures"]) == min(caught, RECENT_CAPTURES)
    ticks = [c["tick"] for c in snap["captures"]]
    assert ticks == sorted(ticks) and ticks[-1] < sim.tick


def test_a_world_without_predators_says_so(client):
    rid = client.post("/api/runs", json={"config": "neural", "seed": 1}).json()["run_id"]
    client.post(f"/api/runs/{rid}/step", json={"ticks": 5})
    snap = stream.build_snapshot(client.app.state.manager.get(rid))
    assert snap["predators"] is None and snap["captures"] == []
    assert client.get(f"/api/runs/{rid}").json()["predators"] is None
    history = client.get(f"/api/runs/{rid}/history").json()["columns"]
    assert history["predators"] == [None] * 5 and history["captures"] == [0] * 5


def test_history_counts_predators_and_their_captures(client):
    rid = stepped(client, ticks=100)
    run = client.app.state.manager.get(rid)
    columns = client.get(f"/api/runs/{rid}/history", params={"every": 10}).json()["columns"]
    assert len(columns["predators"]) == 10
    assert columns["predators"][-1] == run.sim.predator_summary.population
    captures = sum(o.prey_eaten for o in (*run.sim.predators, *run.sim.dead_predators))
    assert sum(columns["captures"]) == captures > 0
    assert sum(columns["attempts"]) >= captures
    assert client.get(f"/api/runs/{rid}").json()["predators"] == len(run.sim.predators)


def test_a_predator_in_detail_and_its_family(client):
    rid = stepped(client)
    sim = client.app.state.manager.get(rid).sim
    hunter = max((*sim.predators, *sim.dead_predators), key=lambda o: o.prey_eaten)
    detail = client.get(f"/api/runs/{rid}/organisms/{hunter.id}").json()
    assert detail["species"] == "predator" and detail["prey_eaten"] == hunter.prey_eaten > 0
    assert detail["food_eaten"] == 0
    family = client.get(f"/api/runs/{rid}/lineage/{hunter.id}").json()
    assert family["founder_id"] == hunter.founder_id
    prey = sim.organisms[0]
    assert client.get(f"/api/runs/{rid}/organisms/{prey.id}").json()["species"] == "prey"


def test_a_neural_predators_latest_decision_is_shown(tmp_path):
    # A config folder of its own, with neural predators (a section can't be added by a dotted
    # path, so this needs a file).
    raw = yaml.safe_load(CONFIGS.joinpath("predators.yaml").read_text())
    raw["predators"]["controller"], raw["predators"]["brain"] = "neural", {}
    (tmp_path / "hunters.yaml").write_text(yaml.safe_dump(raw))
    with TestClient(create_app(RunManager(configs_dir=tmp_path))) as client:
        rid = client.post("/api/runs", json={"config": "hunters", "seed": 3}).json()["run_id"]
        client.post(f"/api/runs/{rid}/step", json={"ticks": 2})
        sim = client.app.state.manager.get(rid).sim
        hunter = client.get(f"/api/runs/{rid}/organisms/{sim.predators[0].id}").json()
        assert hunter["species"] == "predator" and len(hunter["brain_weights"]) == 62
        assert len(hunter["thought"]["inputs"]) == 7
        assert hunter["thought"]["input_names"][0] == "food_seen"  # "food" is prey (D-059)
        prey = client.get(f"/api/runs/{rid}/organisms/{sim.organisms[0].id}").json()
        assert len(prey["thought"]["inputs"]) == 10 and len(prey["brain_weights"]) == 80
