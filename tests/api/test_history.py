"""Tests for live-run history: it agrees with the simulation's own tick summaries, aggregates
like recorded runs, and pages forward with ``since``."""

import math

import pytest
from fastapi.testclient import TestClient

from genesis.analytics.behaviour import decision_measures
from genesis.api.app import create_app
from genesis.api.history import RunHistory
from genesis.api.runs import RunManager
from genesis.core.config import load_config, with_overrides
from genesis.core.simulation import Simulation


@pytest.fixture
def client():
    with TestClient(create_app(RunManager())) as c:
        yield c


def truth(ticks: int):
    """The same run headless: every tick summary and decision measures, independently."""
    sim = Simulation(with_overrides(load_config("configs/neural.yaml"), seed=4, max_ticks=5000))
    rows = []
    for _ in range(ticks):
        s = sim.step()
        rows.append((s, decision_measures(sim.last_decision)))
    return rows


def history(client, ticks: int, **params) -> dict:
    rid = client.post("/api/runs", json={"config": "neural", "seed": 4, "max_ticks": 5000}).json()[
        "run_id"
    ]
    client.post(f"/api/runs/{rid}/step", json={"ticks": ticks})
    return client.get(f"/api/runs/{rid}/history", params=params).json()


def test_every_tick_matches_the_headless_run(client):
    body = history(client, 120)
    cols = body["columns"]
    rows = truth(120)
    assert body["every"] == 1 and cols["tick"] == list(range(120))
    assert cols["population"] == [s.population for s, _ in rows]
    assert cols["births"] == [s.births for s, _ in rows]
    assert cols["food_eaten"] == [s.food_eaten for s, _ in rows]
    assert cols["mean_energy"] == [s.mean_energy for s, _ in rows]
    expected = [None if math.isnan(m["toward_food"]) else m["toward_food"] for _, m in rows]
    assert cols["toward_food"] == expected


def test_coarser_points_sum_flows_and_read_stocks_at_the_end(client):
    cols = history(client, 125, every=10)["columns"]
    rows = truth(125)
    assert cols["tick"] == [9, 19, 29, 39, 49, 59, 69, 79, 89, 99, 109, 119]  # 120-124 incomplete
    for k, tick in enumerate(cols["tick"]):
        window = rows[tick - 9 : tick + 1]
        assert cols["births"][k] == sum(s.births for s, _ in window)
        assert cols["deaths"][k] == sum(s.deaths for s, _ in window)
        assert cols["population"][k] == window[-1][0].population
        throttles = [m["mean_throttle"] for _, m in window if not math.isnan(m["mean_throttle"])]
        assert cols["mean_throttle"][k] == pytest.approx(sum(throttles) / len(throttles))
    # Nothing lost or counted twice: the points' births add up to the ticks they cover.
    assert sum(cols["births"]) == sum(s.births for s, _ in rows[:120])


def test_since_pages_forward_without_repeats(client):
    rid = client.post("/api/runs", json={"config": "neural", "seed": 4}).json()["run_id"]
    client.post(f"/api/runs/{rid}/step", json={"ticks": 50})
    first = client.get(f"/api/runs/{rid}/history", params={"every": 5}).json()["columns"]["tick"]
    client.post(f"/api/runs/{rid}/step", json={"ticks": 30})
    later = client.get(
        f"/api/runs/{rid}/history", params={"every": 5, "since": first[-1] + 1}
    ).json()["columns"]["tick"]
    assert first[-1] == 49 and later[0] == 54 and later[-1] == 79


def test_an_empty_or_young_run_has_no_points_yet():
    assert RunHistory().query(0, 1)["tick"] == []
    h = RunHistory()
    assert h.query(0, 10)["population"] == []


@pytest.mark.parametrize("params", [{"every": 0}, {"every": 100_001}, {"since": -1}])
def test_bad_history_requests_are_422(client, params):
    rid = client.post("/api/runs", json={}).json()["run_id"]
    assert client.get(f"/api/runs/{rid}/history", params=params).status_code == 422


def test_reset_starts_a_fresh_history(client):
    rid = client.post("/api/runs", json={"max_ticks": 500}).json()["run_id"]
    client.post(f"/api/runs/{rid}/step", json={"ticks": 40})
    fresh = client.post(f"/api/runs/{rid}/reset").json()["run_id"]
    assert client.get(f"/api/runs/{fresh}/history").json()["columns"]["tick"] == []
