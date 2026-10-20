"""Write real API responses as JSON fixtures for the browser lab's tests (web/src/api/__fixtures__).

    uv run python scripts/build_api_fixtures.py

The browser lab's TypeScript types (web/src/api/types.ts) describe what the Python server
sends. These fixtures are what it actually sends, captured from the real app: the
TypeScript type-checker checks each against its type, and Vitest runs them through the
runtime checks (parse.ts). tests/api/test_fixtures.py regenerates them and fails if the
committed files are out of date, so a change on one side can't go unnoticed on the other.

Run IDs contain a timestamp and a random suffix; they are replaced with fixed placeholders so
the files only change when the API does.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from genesis.analytics.runs import execute_run
from genesis.api.app import create_app
from genesis.api.runs import RunManager
from genesis.core.config import load_config, with_overrides
from genesis.lake.ingest import ingest_run

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "src" / "api" / "__fixtures__"


def capture() -> dict[str, object]:
    """Every response shape the lab reads, from one scripted session (seed 1, neural)."""
    with TestClient(create_app(RunManager())) as client:
        run = client.post("/api/runs", json={"config": "neural", "seed": 1, "max_ticks": 500})
        rid = run.json()["run_id"]
        client.post(f"/api/runs/{rid}/step", json={"ticks": 50})
        fixtures: dict[str, object] = {
            "health": client.get("/api/health").json(),
            "configs": client.get("/api/configs").json(),
            "run_info": client.get(f"/api/runs/{rid}").json(),
            "organism_detail": client.get(f"/api/runs/{rid}/organisms/0").json(),
            "history": client.get(f"/api/runs/{rid}/history", params={"every": 10}).json(),
        }
        with client.websocket_connect(f"/api/runs/{rid}/stream?fps=30") as ws:
            fixtures["hello"] = ws.receive_json()
            fixtures["snapshot"] = ws.receive_json()
            new_id = client.post(f"/api/runs/{rid}/reset").json()["run_id"]
            fixtures["gone"] = ws.receive_json()
        client.delete(f"/api/runs/{new_id}")

        # Lineage: a run old enough to have grandchildren; the deepest organism, lowest ID.
        grown = client.post("/api/runs", json={"config": "neural", "seed": 1, "max_ticks": 2000})
        gid = grown.json()["run_id"]
        client.post(f"/api/runs/{gid}/step", json={"ticks": 400})
        sim = client.app.state.manager.get(gid).sim
        deep = min((*sim.organisms, *sim.dead), key=lambda o: (-o.generation, o.id))
        mid = next(a for a in (*sim.organisms, *sim.dead) if a.offspring_count >= 2)
        fixtures["lineage"] = client.get(
            f"/api/runs/{gid}/lineage/{mid.id}", params={"depth": 2, "breadth": 2}
        ).json()
        fixtures["lineage_deep"] = client.get(f"/api/runs/{gid}/lineage/{deep.id}").json()
        client.delete(f"/api/runs/{gid}")

    # The lake views: from a private lake of one small run, so the fixtures don't depend on
    # (or change with) the real data/lake.
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        config = with_overrides(
            load_config(ROOT / "configs" / "neural.yaml"), seed=1, max_ticks=300
        )
        execute_run(config, root / "run", run_id="fixture-lake-run", condition="live")
        ingest_run(root / "run", root / "lake")
        app = create_app(RunManager())
        app.state.lake = root / "lake"
        with TestClient(app) as lake_client:
            fixtures["lake_experiments"] = lake_client.get("/api/lake/experiments").json()
            fixtures["lake_runs"] = lake_client.get("/api/lake/runs").json()
            fixtures["lake_run_detail"] = lake_client.get("/api/lake/runs/fixture-lake-run").json()
            fixtures["lake_series"] = lake_client.get(
                "/api/lake/runs/fixture-lake-run/series"
            ).json()

    text = json.dumps(fixtures)
    text = text.replace(rid, "fixture-run").replace(new_id, "fixture-run-reset")
    return json.loads(text)


def rendered() -> dict[str, str]:
    """File name -> exact file text."""
    return {
        f"{name}.json": json.dumps(value, indent=2, sort_keys=True) + "\n"
        for name, value in capture().items()
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in rendered().items():
        (OUT / name).write_text(text)
        print(f"wrote {OUT / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
