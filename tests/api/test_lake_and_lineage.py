"""Tests for the lake routes (Compare view) and lineage (Lineage view)."""

import json

import pytest
from fastapi.testclient import TestClient

from genesis.analytics.runs import execute_run
from genesis.api.app import create_app
from genesis.api.lineage import lineage
from genesis.api.runs import RunManager
from genesis.api.schemas import RunCreate
from genesis.core.config import load_config, with_overrides
from genesis.lake.ingest import ingest_run


@pytest.fixture(scope="module")
def lake(tmp_path_factory):
    root = tmp_path_factory.mktemp("lake-api")
    lake = root / "lake"
    neural = with_overrides(load_config("configs/neural.yaml"), seed=3, max_ticks=1200)
    sampled = load_config("configs/evolution.yaml").model_dump()
    sampled["run"] |= {"seed": 5, "max_ticks": 1003}
    sampled["recording"]["ticks_every"] = 10
    from genesis.core.config import SimulationConfig

    for name, config, experiment in [
        ("neural", neural, "E900"),
        ("sampled", SimulationConfig.model_validate(sampled), "E900"),
        ("loose", with_overrides(load_config("configs/default.yaml"), max_ticks=300), None),
    ]:
        execute_run(config, root / name, experiment_id=experiment, condition=name)
        assert ingest_run(root / name, lake).ingested
    return root


@pytest.fixture
def client(lake):
    app = create_app(RunManager())
    app.state.lake = lake / "lake"
    with TestClient(app) as c:
        yield c


def csv_rows(path):
    import csv

    with path.open(newline="") as f:
        return list(csv.DictReader(f))


# --- the lake ---------------------------------------------------------------------------------


def test_experiments_and_their_runs_are_listed(client):
    experiments = client.get("/api/lake/experiments").json()
    assert [(e["experiment_id"], e["runs"]) for e in experiments] == [("E900", 2), (None, 1)]
    runs = client.get("/api/lake/runs", params={"experiment_id": "E900"}).json()
    assert [r["condition"] for r in runs] == ["neural", "sampled"]
    loose = client.get("/api/lake/runs").json()
    assert len(loose) == 1 and loose[0]["experiment_id"] is None


def test_a_run_comes_with_its_whole_config(client, lake):
    run_id = json.loads((lake / "neural" / "run.json").read_text())["run_id"]
    detail = client.get(f"/api/lake/runs/{run_id}").json()
    assert detail["config"]["organisms"]["controller"] == "neural"
    assert client.get("/api/lake/runs/nope").status_code == 404


def test_series_sums_flows_exactly_and_reads_stocks_at_the_end(client, lake):
    run_id = json.loads((lake / "neural" / "run.json").read_text())["run_id"]
    body = client.get(f"/api/lake/runs/{run_id}/series").json()
    ticks = csv_rows(lake / "neural" / "ticks.csv")
    cols = body["columns"]
    assert body["every"] == 2  # 1,200 ticks: the first round size under 600 points
    assert sum(cols["births"]) == sum(int(r["births"]) for r in ticks)
    assert cols["population"][-1] == int(ticks[-1]["population"])
    assert cols["tick"][-1] == 1199 and len(cols["toward_food"]) == len(cols["tick"])


def test_series_of_a_sampled_run_uses_whole_recorded_rows(client, lake):
    run_id = json.loads((lake / "sampled" / "run.json").read_text())["run_id"]
    body = client.get(f"/api/lake/runs/{run_id}/series").json()
    rows = csv_rows(lake / "sampled" / "ticks.csv")  # every 10th tick, flows already summed
    assert body["every"] % 10 == 0
    assert sum(body["columns"]["births"]) == sum(int(r["births"]) for r in rows)
    assert body["columns"]["tick"][-1] == 1002  # the final, partial interval is included


def test_no_lake_yet_is_a_clear_404(tmp_path):
    app = create_app(RunManager())
    app.state.lake = tmp_path / "missing"
    with TestClient(app) as client:
        response = client.get("/api/lake/experiments")
    assert response.status_code == 404 and "genesis lake ingest" in response.json()["detail"]


# --- lineage ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def grown():
    run = RunManager().create(RunCreate(config="neural", seed=2, max_ticks=3000))
    for _ in range(1500):
        run.sim.step()
    return run.sim


def test_ancestors_run_from_the_founder_to_the_parent(grown):
    deep = max([*grown.organisms, *grown.dead], key=lambda o: o.generation)
    family = lineage(grown, deep.id)
    ids = [a["id"] for a in family["ancestors"]]
    assert len(ids) == deep.generation and ids[0] == deep.founder_id
    everyone = {o.id: o for o in (*grown.organisms, *grown.dead)}
    assert everyone[ids[-1]].id == deep.parent_id
    for parent, child in zip(ids, ids[1:], strict=False):
        assert everyone[child].parent_id == parent


def test_descendant_counts_match_a_brute_force_count(grown):
    founder = max((o for o in (*grown.organisms, *grown.dead) if o.parent_id is None),
                  key=lambda o: o.offspring_count)  # fmt: skip
    family = lineage(grown, founder.id, depth=8, breadth=50)
    everyone = [*grown.organisms, *grown.dead]
    brute = sum(1 for o in everyone if o.founder_id == founder.id and o.id != founder.id)
    assert family["descendants"] == brute
    assert family["founder_family"] == brute + 1
    assert family["founder_family_alive"] == sum(
        1 for o in grown.organisms if o.founder_id == founder.id
    )


def test_depth_and_breadth_cut_the_tree_and_say_what_they_hide(grown):
    founder = max((o for o in (*grown.organisms, *grown.dead) if o.parent_id is None),
                  key=lambda o: o.offspring_count)  # fmt: skip
    tree = lineage(grown, founder.id, depth=1, breadth=2)["organism"]
    assert len(tree["children"]) == min(2, founder.offspring_count)
    assert tree["hidden_children"] == founder.offspring_count - len(tree["children"])
    for child in tree["children"]:
        assert child["children"] == [] and child["hidden_children"] == child["offspring_count"]


def test_lineage_route_validates_and_finds(client):
    rid = client.post("/api/runs", json={"config": "neural", "seed": 1}).json()["run_id"]
    client.post(f"/api/runs/{rid}/step", json={"ticks": 600})
    body = client.get(f"/api/runs/{rid}/lineage/3").json()
    assert body["organism"]["id"] == 3 and body["ancestors"] == []  # a founder
    assert client.get(f"/api/runs/{rid}/lineage/99999").status_code == 404
    assert client.get(f"/api/runs/{rid}/lineage/3", params={"depth": 9}).status_code == 422


def test_children_are_listed_in_birth_order(grown):
    """IDs are handed out in birth order; the tree must list siblings oldest first (it once
    listed living children before their older, dead siblings)."""
    parent = max((*grown.organisms, *grown.dead), key=lambda o: o.offspring_count)
    tree = lineage(grown, parent.id, depth=2, breadth=50)["organism"]

    def check(node):
        ids = [c["id"] for c in node["children"]]
        assert ids == sorted(ids)
        births = [c["birth_tick"] for c in node["children"]]
        assert births == sorted(births)
        for child in node["children"]:
            check(child)

    assert len(tree["children"]) >= 2
    check(tree)
