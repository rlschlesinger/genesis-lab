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
from pathlib import Path

from fastapi.testclient import TestClient

from genesis.api.app import create_app
from genesis.api.runs import RunManager

OUT = Path(__file__).resolve().parents[1] / "web" / "src" / "api" / "__fixtures__"


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
