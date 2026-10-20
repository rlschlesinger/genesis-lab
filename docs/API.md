# Genesis Lab API

A local HTTP and WebSocket API for running seeded simulations live: create a run, step it, change its speed, watch it, inspect any organism's brain, and save it as a normal run folder. The Python server is the **only authority** over a run; clients view and request, they never hold simulation state. Version 1 (`API_VERSION`, reported by `/api/health`).

```bash
uv run genesis serve                       # http://127.0.0.1:8765
open http://127.0.0.1:8765/docs            # interactive documentation (try every route)
uv run python scripts/api_example.py       # a complete Python client, start to finish
```

The server listens on `127.0.0.1` only. A network address needs `--allow-remote`: there is no login, so anyone who can reach the API controls it.

## Guarantees

- **Same seed, same run.** A run driven through the API (any mix of steps, pauses, speeds and viewers) passes through exactly the states of a headless run with the same config and seed. Wall-clock time decides how many ticks happen per second, never which tick comes next. `GET /api/runs/{id}/digest` lets you check: equal digests at equal ticks mean bit-identical states (tested).
- **Viewers can't change anything.** The stream is read-only, rounded for display, and never makes the simulation wait.
- **Exports are exact.** An exported run is replayed headlessly and its digest compared with the live run's.

## Run states

```
idle ──resume──► running ──pause──► paused ──resume──► running
  │                 │                  │
  └──step──► paused └──(end)──► completed / failed ◄──(end)── step
```

`completed`: reached `max_ticks`, or went extinct with `stop_on_extinction`. `failed`: a tick raised an error (for example the energy ledger check); `error` says why. Completed and failed runs are final: reset makes a fresh run. Any request that would make another move gets **409**.

## Endpoints

All paths start with `/api`. Request and response bodies are JSON. Unknown fields in a request are refused (422).

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health` | | `{status, api_version, genesis_version}` |
| GET | `/configs` | | `[ConfigSummary]`: name, controller, max_ticks, initial_count, has_brains, mutation_enabled |
| GET | `/configs/{name}` | | the full validated config (as in run.json) |
| POST | `/runs` | `RunCreate` | `RunInfo` (201) |
| GET | `/runs` | | `[RunInfo]`, in creation order |
| GET | `/runs/{id}` | | `RunInfo` |
| DELETE | `/runs/{id}` | | 204; viewers get `gone` |
| GET | `/runs/{id}/digest` | | `{run_id, tick, digest}` (hashes every organism ever: don't poll) |
| POST | `/runs/{id}/resume` | | `RunInfo`; runs in the background at the run's speed |
| POST | `/runs/{id}/pause` | | `RunInfo`; stops after the tick in progress (running runs only) |
| POST | `/runs/{id}/step` | `{ticks: 1–10000}` (default 1) | `RunInfo`; idle or paused runs only; leaves it paused |
| PUT | `/runs/{id}/speed` | `{ticks_per_second: >0–100000 or null}` | `RunInfo`; null = as fast as possible; default 30 |
| POST | `/runs/{id}/reset` | `{seed}` (optional) | `RunInfo` of a fresh run from tick 0, **new ID**; viewers of the old ID get `gone` with `replaced_by` |
| GET | `/runs/{id}/organisms/{oid}` | | `OrganismDetail` |
| GET | `/runs/{id}/history?since=0&every=1` | | `History`: the run so far as columns, for charts (below) |
| POST | `/runs/{id}/export?ingest=true` | | `ExportResult`; paused or finished runs only |
| GET | `/saved-runs?experiment_id=&limit=200` | | `[SavedRun]`, newest first (limit ≤ 1000) |
| WebSocket | `/runs/{id}/stream?fps=15` | | `hello`, `snapshot`s, `gone` (below) |

### `RunCreate`

```json
{"config": "neural", "seed": 7, "max_ticks": 5000, "changes": {"food.regrowth_per_tick": 1.0}}
```

All fields optional. `config` is a name from `configs/` (`default`, `evolution`, `neural`), never a path. `changes` uses the experiment specs' dotted paths (up to 32); the result is validated exactly like a config file, so `{"organisms.controller": "neural"}` on `default` is refused (no brain section). At most **4** live runs exist at once (429 beyond that).

### `RunInfo`

```json
{"run_id": "20261019T232024Z-s1-e47246", "state": "paused", "config_name": "neural", "seed": 1,
 "controller": "neural", "tick": 50, "max_ticks": 5000, "population": 34, "speed": 30.0,
 "viewers": 1, "error": null}
```

`tick` counts ticks completed: the state shown is the state after tick `tick − 1`.

### `OrganismDetail`

Identity (`id`, `alive`, `parent_id`, `founder_id`, `generation`, `birth_tick`, `death_tick`, `death_cause`), body (`age`, `energy`, `x`, `y`, `heading`, `food_eaten`, `offspring_count`), family (`children`: IDs in birth order), `genome` and `traits` (as in organisms.csv), `brain_weights` (the 62 parameters under their brains.csv names, or null), and `thought`:

```json
{"tick": 49, "input_names": ["food_seen", "food_ahead", "food_left", "food_closeness", "energy", "wall_ahead", "noise"],
 "inputs": [1.0, -0.768, 0.64, 0.671, 0.383, 0.0, 0.427],
 "hidden_sum": [...6], "hidden": [...6], "output_sum": [...2], "outputs": [0.942, 0.58],
 "turn": 0.471, "throttle": 0.58}
```

(Values from `scripts/api_example.py`, seed 1, organism 0 on tick 49; `[...6]` stands for six numbers.) `thought` is the organism's decision on the run's latest tick, read from the simulation's own record (the same numbers `genesis inspect` replays). Null without a brain, or if the organism didn't decide on that tick (born on it, or dead before it).

### `ExportResult`

```json
{"run_id": "20261019T232024Z-s1-e47246-t150", "path": "data/runs/live/20261019T232024Z-s1-e47246-t150",
 "ticks": 150, "digest": "…", "matches_live_run": true, "ingested": true}
```

The live run is **replayed** headlessly for its `tick` ticks with the normal recorder, writing exactly what `genesis run` would for that config (`max_ticks` = the tick reached); with `ingest=true` it is loaded into the lake (condition `live`). Refused (409) for runs that haven't started, are running (pause first), or failed.

### `History`

```json
{"run_id": "…", "every": 10,
 "columns": {"tick": [9, 19, 29], "population": [31, 34, 36], "food_count": [140, 133, 129],
             "lineages": [30, 30, 29], "mean_energy": [44.1, 41.8, 40.2],
             "births": [0, 3, 2], "deaths": [0, 0, 1], "food_eaten": [4, 7, 6],
             "toward_food": [0.52, 0.61, 0.58], "mean_turn": [0.41, 0.39, 0.40],
             "mean_throttle": [0.55, 0.54, 0.56]}}
```

One point per `every` ticks, the same rule as recorded runs: **flows** (births, deaths, food eaten) summed over the interval, **stocks** (population, food, lineages, mean energy) at its last tick, **shares** (turning toward food, mean turn as a fraction of max turn, mean throttle) averaged over its ticks; `null` where there was nothing to measure. Only complete intervals are returned, so a point never changes once drawn; ask again with `since` = the last tick received + 1 for newer points. Values are examples.

## The stream

`ws://127.0.0.1:8765/api/runs/{id}/stream?fps=15` (fps 1–30). Messages are JSON, each with a `type` (values below are examples):

```json
{"type": "hello", "version": 1, "run": {RunInfo}, "world": {"width": 200.0, "height": 200.0}}

{"type": "snapshot", "version": 1, "run_id": "…", "tick": 403, "state": "running", "speed": 200.0,
 "error": null, "population": 86,
 "last_tick": {"births": 2, "deaths": 0, "food_eaten": 3, "mean_energy": 41.2, "lineages": 9},
 "food": {"x": [12.31, …], "y": [180.02, …]},
 "organisms": {"id": [14, …], "x": [103.59, …], "y": [2.22, …], "heading": [-1.427, …],
               "energy": [23.98, …], "generation": [0, …], "founder": [14, …]}}

{"type": "gone", "run_id": "…", "replaced_by": "…new run ID, after a reset, or null"}
```

- **Newest state only.** At most `fps` times a second, the server sends the run's current snapshot if it changed since your last one. Ticks in between are skipped, not queued: a slow viewer gets fewer frames, never stale ones, and never slows the run. A paused run sends nothing until something changes.
- **Columnar.** Each organism field is one list, all the same length (`population`), in organism ID order.
- **Display precision.** Positions to 0.01 world units, headings to 0.001 rad, energy to 0.01 EU. Use `/digest` and exports for exact state.
- **Close codes.** 4404: no such run (after a `gone` message). 4422: bad `fps`.

## Errors

Every error body is `{"detail": "…"}` with a readable reason.

| Status | Meaning | Example |
|---|---|---|
| 404 | No such run or organism | a deleted run's ID |
| 409 | Not possible in the run's current state | resume a completed run; step a running one; export before the first tick |
| 422 | Invalid request or config | `max_ticks: 0`; a misspelled dotted path; an unknown field |
| 429 | Too many live runs | a fifth run while four exist |

## How it works

`src/genesis/api/`: `schemas.py` (this contract as Pydantic models), `runs.py` (live runs and the state table), `stepping.py` (controls and the background loop), `stream.py` (WebSocket), `details.py` (organism details), `saved.py` (saved runs, export), `app.py` (routes). Design decisions: D-047 to D-050 in [decision-log.md](decision-log.md).
