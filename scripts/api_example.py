"""Drive the Genesis Lab API from Python: create a run, step it, read an organism's brain,
watch it live over the WebSocket, then export it. See docs/API.md.

Start the server in one terminal, run this in another:

    uv run genesis serve
    uv run python scripts/api_example.py [--base http://127.0.0.1:8765] [--no-export]

Uses only the standard library for HTTP (urllib) and the ``websockets`` package (installed
with Genesis Lab) for the stream, so it is easy to adapt outside this project.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import urllib.error
import urllib.request

import websockets


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/") + "/api"

    def call(self, method: str, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.base + path, data=data, method=method, headers={"content-type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request) as response:
                text = response.read()
        except urllib.error.HTTPError as error:  # 4xx/5xx: show the server's reason
            raise SystemExit(f"{method} {path} -> {error.code}: {error.read().decode()}") from None
        except urllib.error.URLError as error:  # nothing listening
            raise SystemExit(
                f"can't reach {self.base} ({error.reason}). Is the server running? "
                "Start it with: uv run genesis serve"
            ) from None
        return json.loads(text) if text else None


async def watch(ws_url: str, frames: int) -> None:
    async with websockets.connect(ws_url) as ws:
        hello = json.loads(await ws.recv())
        print(f"  connected: world {hello['world']['width']} x {hello['world']['height']}")
        for _ in range(frames):
            snap = json.loads(await ws.recv())
            tick, population = snap["tick"], snap["population"]
            print(f"  tick {tick:>5}  population {population:>3}  state {snap['state']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8765")
    parser.add_argument("--no-export", action="store_true", help="skip writing a run folder")
    args = parser.parse_args()
    api = Api(args.base)

    print("health:", api.call("GET", "/health"))
    run = api.call("POST", "/runs", {"config": "neural", "seed": 1, "max_ticks": 5000})
    rid = run["run_id"]
    print(f"created {rid}: {run['state']}, {run['population']} organisms")

    run = api.call("POST", f"/runs/{rid}/step", {"ticks": 50})
    print(f"stepped to tick {run['tick']} ({run['state']})")

    organism = api.call("GET", f"/runs/{rid}/organisms/0")
    thought = organism["thought"]
    if thought:
        print(f"organism 0 on tick {thought['tick']}: turn {thought['turn']:+.3f} rad, "
              f"throttle {thought['throttle']:.2f}")  # fmt: skip
        for name, value in zip(thought["input_names"], thought["inputs"], strict=True):
            print(f"    {name:<15} {value:+.3f}")
    else:
        print(f"organism 0: {'dead' if not organism['alive'] else 'no brain'}")

    api.call("PUT", f"/runs/{rid}/speed", {"ticks_per_second": 200})
    api.call("POST", f"/runs/{rid}/resume")
    ws_url = args.base.replace("http", "ws", 1) + f"/api/runs/{rid}/stream?fps=4"
    print("watching (4 frames a second):")
    asyncio.run(watch(ws_url, frames=8))
    run = api.call("POST", f"/runs/{rid}/pause")
    print(f"paused at tick {run['tick']}")

    if not args.no_export:
        export = api.call("POST", f"/runs/{rid}/export")
        print(f"exported to {export['path']} ({export['ticks']} ticks); "
              f"matches the live run: {export['matches_live_run']}")  # fmt: skip

    api.call("DELETE", f"/runs/{rid}")
    print("deleted the live run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
