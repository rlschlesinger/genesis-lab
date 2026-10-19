"""Tests for the HTTP routes: shapes, status codes, and input validation at the boundary."""

import pytest
from fastapi.testclient import TestClient

from genesis.api.app import create_app
from genesis.api.runs import RunManager
from genesis.api.schemas import API_VERSION
from genesis.cli import LOCAL_HOSTS, main


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(RunManager(max_runs=3)))


def test_health_reports_the_api_version(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["api_version"] == API_VERSION


def test_configs_are_listed_and_readable(client):
    names = {c["name"]: c for c in client.get("/api/configs").json()}
    assert set(names) == {"default", "evolution", "neural"}
    assert names["neural"]["has_brains"] and names["neural"]["controller"] == "neural"
    assert not names["default"]["mutation_enabled"]
    full = client.get("/api/configs/evolution").json()
    assert full["run"]["max_ticks"] == 20000 and full["genome"]["speed"]["initial"] == 1.5


def test_create_list_get_and_delete_a_run(client):
    response = client.post("/api/runs", json={"config": "neural", "seed": 4, "max_ticks": 100})
    assert response.status_code == 201
    run = response.json()
    assert run["state"] == "idle" and run["tick"] == 0 and run["seed"] == 4
    assert run["controller"] == "neural" and run["population"] == 30 and run["max_ticks"] == 100
    assert [r["run_id"] for r in client.get("/api/runs").json()] == [run["run_id"]]
    assert client.get(f"/api/runs/{run['run_id']}").json() == run
    assert client.delete(f"/api/runs/{run['run_id']}").status_code == 204
    assert client.get(f"/api/runs/{run['run_id']}").status_code == 404


@pytest.mark.parametrize(
    "body, status, fragment",
    [
        ({"config": "../configs/default"}, 422, "pattern"),  # can't name a path
        ({"config": "nope"}, 422, "unknown config"),
        ({"seed": -1}, 422, "greater than or equal"),
        ({"max_ticks": 0}, 422, "greater than"),
        ({"changes": {"food.regrowth_per_tik": 1.0}}, 422, "unknown config path"),
        ({"surprise": True}, 422, "Extra inputs"),  # unknown fields are refused, not ignored
    ],
)
def test_bad_requests_get_a_status_and_a_reason(client, body, status, fragment):
    response = client.post("/api/runs", json=body)
    assert response.status_code == status
    assert fragment in str(response.json()["detail"])


def test_too_many_runs_is_429_and_missing_runs_are_404(client):
    for _ in range(3):
        assert client.post("/api/runs", json={}).status_code == 201
    response = client.post("/api/runs", json={})
    assert response.status_code == 429 and "limit is 3" in response.json()["detail"]
    assert client.get("/api/runs/nope").status_code == 404
    assert client.delete("/api/runs/nope").status_code == 404


def test_the_api_describes_itself():
    schema = TestClient(create_app()).get("/openapi.json").json()
    assert {"/api/health", "/api/configs", "/api/runs", "/api/runs/{run_id}"} <= set(
        schema["paths"]
    )


def test_serve_refuses_a_network_address_without_allow_remote(capsys):
    assert "127.0.0.1" in LOCAL_HOSTS
    assert main(["serve", "--host", "0.0.0.0"]) == 2
    assert "--allow-remote" in capsys.readouterr().err


def test_every_route_is_documented_in_api_md():
    """docs/API.md is the reference the browser lab is built against: it must list every
    route the server actually has."""
    from pathlib import Path

    doc = (Path(__file__).parents[2] / "docs" / "API.md").read_text()
    app = create_app()
    paths = {route.path for route in app.routes if route.path.startswith("/api/")}
    assert paths  # the check is real: there are routes to look for
    missing = sorted(p for p in paths if p.removeprefix("/api").replace("{run_id}", "{id}")
                     .replace("{organism_id}", "{oid}") not in doc)  # fmt: skip
    assert not missing, f"routes missing from docs/API.md: {missing}"
