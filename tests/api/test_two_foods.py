"""Two-food worlds through the API (Milestone 6, increment 6.9, D-064).

The stream carries each food item's kind and each organism's diet; history follows the
diet's spread; details show an organism's diet; a one-food world says so with nulls.
"""

import pytest
from fastapi.testclient import TestClient

from genesis.analytics.metrics import diet_tick_row
from genesis.api import stream
from genesis.api.app import create_app
from genesis.api.runs import RunManager


@pytest.fixture
def client():
    with TestClient(create_app(RunManager())) as c:
        yield c


def stepped(client, ticks: int = 200) -> str:
    rid = client.post("/api/runs", json={"config": "diets", "seed": 1}).json()["run_id"]
    assert client.post(f"/api/runs/{rid}/step", json={"ticks": ticks}).status_code == 200
    return rid


def test_the_snapshot_carries_food_kinds_and_diets(client):
    rid = stepped(client)
    run = client.app.state.manager.get(rid)
    snap = stream.build_snapshot(run)
    sim = run.sim
    assert snap["food"]["kind"] == sim.world.food.kinds.tolist()
    assert len(snap["food"]["kind"]) == len(snap["food"]["x"])
    assert snap["diets"] == [round(o.diet, 3) for o in sim.organisms]


def test_a_one_food_world_says_so(client):
    rid = client.post("/api/runs", json={"config": "neural", "seed": 1}).json()["run_id"]
    client.post(f"/api/runs/{rid}/step", json={"ticks": 3})
    snap = stream.build_snapshot(client.app.state.manager.get(rid))
    assert snap["food"]["kind"] is None and snap["diets"] is None
    columns = client.get(f"/api/runs/{rid}/history").json()["columns"]
    assert columns["diet_sd"] == [None] * 3 and columns["food_a"] == [None] * 3


def test_history_follows_the_diet_as_diet_ticks_records_it(client):
    rid = stepped(client, ticks=100)
    run = client.app.state.manager.get(rid)
    columns = client.get(f"/api/runs/{rid}/history").json()["columns"]
    now = diet_tick_row(run.sim, run.last_summary)
    for name in ("food_a", "food_b", "diet_sd", "diet_low", "diet_high"):
        assert columns[name][-1] == now[name], name


def test_an_organism_shows_its_diet(client):
    rid = stepped(client)
    org = client.app.state.manager.get(rid).sim.organisms[-1]
    detail = client.get(f"/api/runs/{rid}/organisms/{org.id}").json()
    assert detail["diet"] == org.diet and detail["meals_b"] == org.meals_b
    configs = {c["name"]: c for c in client.get("/api/configs").json()}
    assert configs["diets"]["has_two_foods"] and not configs["neural"]["has_two_foods"]
