"""Stress tests: the edges of the state space and the edges of scale (increment 3.12), and
the API server under load (the Milestone 5 review).

Each test here is a situation that *could* break something without any single module being
wrong: nobody alive after the first tick, a population cap of one, every gene parked on its
bound, 5,000 organisms, a 2000 x 2000 world with 20,000 food items, 50,000 ticks of ledger
rounding, 120 runs through the batch runner and into the lake; and, against a real uvicorn
server (not the in-process test client): controls raced from eight clients, fifty viewers
with some that never read and some that churn, four runs flat out with 2,000 neural
organisms, a 120,000-tick run's history and export, lake queries while exports ingest. The
fast ones run with the normal suite; the ones marked ``slow`` take a minute or more and run
with ``pytest -m slow``. The API tests print their measurements (``pytest -s``).
"""

import asyncio
import json
import logging
import math
import random
import socket
import statistics
import threading
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx2
import pytest
import uvicorn
import websockets
import yaml

from genesis.analytics.batch import run_experiment
from genesis.analytics.experiments import apply_changes
from genesis.analytics.recorder import RunRecorder
from genesis.analytics.runs import execute_run
from genesis.analytics.spec import load_spec
from genesis.api.app import create_app
from genesis.api.runs import RunManager
from genesis.core import spatial
from genesis.core.config import SimulationConfig, load_config
from genesis.core.organism import DeathCause
from genesis.core.simulation import Simulation
from genesis.evolution.genome import gene_names
from genesis.lake.db import connect
from genesis.lake.ingest import ingest_paths

ROOT = Path(__file__).parents[1]
CONFIGS = ROOT / "configs"


def config(name: str = "default.yaml", **sections) -> SimulationConfig:
    """A config file with whole-section updates, e.g. config(food={"initial_count": 0})."""
    raw = yaml.safe_load((CONFIGS / name).read_text())
    for section, changes in sections.items():
        raw[section].update(changes)
    return SimulationConfig.model_validate(raw)


def crowd(n: int, ticks: int) -> SimulationConfig:
    """The benchmark's recipe: a population held at N with food to match."""
    return config(
        run={"max_ticks": ticks, "stop_on_extinction": False},
        organisms={"initial_count": n, "max_population": n, "initial_energy": 200.0},
        food={"max_count": max(300, n), "initial_count": max(150, n // 2),
              "regrowth_per_tick": n * 0.05},
    )  # fmt: skip


# Zero food and too little energy to pay one tick's metabolism: every founder starves on tick 0
# (organisms eat *before* paying costs, so without the empty larder they would survive).
DEAD_ON_ARRIVAL = dict(
    food={"initial_count": 0, "regrowth_per_tick": 0.0},
    organisms={"initial_energy": 0.1},
    recording={"events": ["birth", "death", "meal"]},
)


# --- Extinction on tick 0, all the way into the lake ----------------------------------------------


def test_extinction_on_tick_0_is_recorded_loaded_and_queryable(tmp_path):
    cfg = config(**DEAD_ON_ARRIVAL)
    sim = Simulation(cfg)
    summaries = sim.run()
    assert sim.tick == 1 and sim.organisms == [] and len(sim.dead) == 30
    (only,) = summaries
    assert (only.population, only.deaths, only.lineages) == (0, 30, 0)
    assert math.isnan(only.mean_energy)
    assert all(o.death_cause is DeathCause.STARVATION and o.death_tick == 0 for o in sim.dead)
    assert sim.ledger.metabolism == pytest.approx(3.0)  # 30 x 0.1: all they had

    result = execute_run(cfg, tmp_path / "run")
    assert (result.ticks_run, result.stop_reason, result.final_population) == (1, "extinction", 0)
    lines = (tmp_path / "run" / "gene_stats.csv").read_text().splitlines()
    assert len(lines) == 1 + len(gene_names()) and lines[1].endswith(",0,nan,nan,nan,nan")
    assert (tmp_path / "run" / "genomes.csv").read_text().count("\n") == 1  # header only

    (ingested,) = ingest_paths([tmp_path / "run"], tmp_path / "lake")
    assert ingested.ingested, ingested.reason
    con = connect(tmp_path / "lake")
    assert con.sql("SELECT ticks_run, final_population, organisms_ever FROM runs").fetchall() == [
        (1, 0, 30)
    ]
    assert con.sql("SELECT count(*), count(mean) FROM gene_stats").fetchall() == [(6, 0)]
    assert con.sql("SELECT count(*) FROM organisms WHERE NOT alive").fetchall() == [(30,)]
    assert con.sql("SELECT count(*) FROM events WHERE kind = 'death'").fetchall() == [(30,)]
    assert con.sql("SELECT count(*) FROM lineage_sizes").fetchall() == [(30,)]


def test_an_empty_world_keeps_ticking_when_asked_not_to_stop():
    cfg = config(
        **{**DEAD_ON_ARRIVAL, "food": {"initial_count": 0, "regrowth_per_tick": 2.0}},
        run={"stop_on_extinction": False, "max_ticks": 300},
    )
    sim = Simulation(cfg)
    summaries = sim.run()
    assert sim.tick == 300 and len(summaries) == 300 and not sim.organisms
    assert all(math.isnan(s.mean_energy) and s.population == 0 for s in summaries)
    # Food keeps arriving (and leaving the ledger's books balanced) with nobody to eat it.
    assert summaries[-1].food_count == min(300, sum(s.food_spawned for s in summaries))
    assert sim.ledger.food_spawned == pytest.approx(summaries[-1].food_count * 20.0)


# --- The population cap ---------------------------------------------------------------------------


@pytest.mark.parametrize("cap", [1, 2])
def test_a_cap_of_one_or_two_is_never_exceeded(cap):
    cfg = config(
        "evolution.yaml",
        run={"max_ticks": 1500, "seed": 3},
        organisms={"max_population": cap, "initial_count": 1},
        food={"regrowth_per_tick": 10.0},
    )
    sim = Simulation(cfg)
    summaries = sim.run()
    assert max(s.population for s in summaries) <= cap
    births = sum(s.births for s in summaries)
    # With a cap of 1 the lone founder can never make room; with a cap of 2 it has one child.
    assert births == (0 if cap == 1 else 1)


def test_a_rich_world_pins_the_population_at_the_cap():
    cfg = config(
        "evolution.yaml",
        run={"max_ticks": 400},
        organisms={"max_population": 200},
        food={"max_count": 2000, "initial_count": 2000, "regrowth_per_tick": 40.0},
    )
    sim = Simulation(cfg)
    summaries = sim.run()
    populations = [s.population for s in summaries]
    assert max(populations) == 200
    at_cap = [s for s in summaries if s.population == 200]
    assert len(at_cap) > 200
    # At the cap, births are rationed to the room deaths make, never more.
    for before, after in zip(summaries, summaries[1:], strict=False):
        assert after.births <= 200 - (before.population - after.deaths)


# --- Genes parked exactly on their bounds ---------------------------------------------------------


@pytest.mark.parametrize("bound", ["min", "max"])
def test_genes_starting_on_a_bound_stay_within_bounds_under_mutation(bound):
    raw = yaml.safe_load((CONFIGS / "evolution.yaml").read_text())
    for gene in raw["genome"].values():
        gene["initial"] = gene[bound]
    raw["run"]["max_ticks"] = 600
    sim = Simulation(SimulationConfig.model_validate(raw))
    sim.run()
    assert sim.tick == 600 and len(sim.mutation_log) > 0
    everyone = [*sim.organisms, *sim.dead]
    for name, gene in raw["genome"].items():
        values = [getattr(o.genome, name) for o in everyone]
        assert gene["min"] <= min(values) and max(values) <= gene["max"], name
    # Reflection keeps mutated genes strictly inside the range, never piled on the bound.
    changed = [e for e in sim.mutation_log if e.gene == "speed"]
    assert any(raw["genome"]["speed"]["min"] < e.after < raw["genome"]["speed"]["max"]
               for e in changed)  # fmt: skip


# --- Tiny and huge worlds -------------------------------------------------------------------------


def test_one_organism_in_a_world_three_by_two_units():
    cfg = config(
        run={"max_ticks": 500},
        world={"width": 3.0, "height": 2.0},
        food={"eat_radius": 2.0, "max_count": 5, "initial_count": 5, "regrowth_per_tick": 1.0},
        organisms={"initial_count": 1, "max_population": 1},
    )
    sim = Simulation(cfg)
    summaries = sim.run()
    assert sim.tick == 500 and len(sim.organisms) == 1
    (org,) = sim.organisms
    assert 0.0 <= org.x <= 3.0 and 0.0 <= org.y <= 2.0
    assert sum(s.food_eaten for s in summaries) > 400  # it can reach anything in this world


def test_a_huge_world_with_twenty_thousand_food_items_matches_all_pairs(monkeypatch):
    cfg = config(
        run={"max_ticks": 8, "stop_on_extinction": False},
        world={"width": 2000.0, "height": 2000.0},
        food={"max_count": 20000, "initial_count": 20000, "regrowth_per_tick": 50.0},
        organisms={"initial_count": 300, "max_population": 300},
    )
    with_grid = Simulation(cfg)
    with_grid.run()
    monkeypatch.setattr(spatial, "DENSE_PAIR_LIMIT", float("inf"))
    all_pairs = Simulation(cfg)
    all_pairs.run()
    assert with_grid.state_digest() == all_pairs.state_digest()


# --- Scale ----------------------------------------------------------------------------------------


def test_five_thousand_organisms_run_record_and_balance():
    cfg = crowd(5000, ticks=5)
    sim = Simulation(cfg)
    recorder = RunRecorder(genome_snapshot_every=5, events=("birth", "death", "meal"))
    while not sim.finished:
        recorder.observe(sim, sim.step())  # the ledger check inside step() must hold
    assert sim.tick == 5 and len(sim.organisms) == 5000
    assert len(recorder.ticks) == 5 and len(recorder.genomes) == 2 * 5000
    assert sum(e["kind"] == "meal" for e in recorder.events) == sum(
        r["food_eaten"] for r in recorder.ticks
    )


def test_three_thousand_organisms_and_food_items_need_little_memory():
    # All-pairs at this size would build several 3000 x 3000 tables (72 MB each); the grid
    # must not. Measured on the Python heap, which excludes NumPy's own small overheads.
    cfg = crowd(3000, ticks=3)
    tracemalloc.start()
    try:
        sim = Simulation(cfg)
        assert sim.world.food.count == 1500  # 3000 x 1500 pairs on the first tick
        baseline = tracemalloc.get_traced_memory()[0]
        sim.run()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert (peak - baseline) < 60e6, f"peak {peak - baseline:.0f} bytes above the start"


# --- Slow: minutes, run with `pytest -m slow` -----------------------------------------------------


@pytest.mark.slow
def test_ledger_rounding_stays_far_below_tolerance_over_fifty_thousand_ticks():
    sim = Simulation(config("evolution.yaml", run={"max_ticks": 50_000}))
    worst = 0.0
    while not sim.finished:
        sim.step()
        if sim.tick % 1000 == 0:
            drift = abs(sim.energy_stock() - sim.ledger.expected_stock)
            worst = max(worst, drift / sim.ledger.tolerance)
    assert sim.tick == 50_000
    # Measured 2026-10-19: worst ratio 0.002. Fifteen times that still leaves a wide margin
    # below 1.0 (the EnergyLedgerError line) and would signal a real change in rounding.
    assert worst < 0.03, f"drift reached {worst:.3f} of the tolerance"


@pytest.mark.slow
def test_a_batch_of_one_hundred_and_twenty_runs_loads_into_the_lake(tmp_path):
    spec = {
        "experiment_id": "E999",
        "title": "stress: 120 short runs",
        "definition": "docs/experiments/E999-does-not-exist.md",
        "base_config": "configs/evolution.yaml",
        "base_changes": {"run.max_ticks": 300},
        "conditions": [{"label": "a"}, {"label": "b", "changes": {"food.regrowth_per_tick": 1.0}}],
        "seeds": {"first": 100, "count": 60},
        "output": str(tmp_path / "out"),
    }
    path = tmp_path / "E999.yaml"
    path.write_text(yaml.safe_dump(spec))
    outcomes = run_experiment(load_spec(path, ROOT), workers=3, lake=tmp_path / "lake", root=ROOT)
    assert len(outcomes) == 120 and all(o.ok for o in outcomes)
    con = connect(tmp_path / "lake")
    assert con.sql("SELECT count(*) FROM completed_runs").fetchall() == [(120,)]
    assert con.sql("SELECT count(*) FROM ticks").fetchall()[0][0] <= 120 * 300
    by_condition = con.sql(
        "SELECT condition, count(*) FROM completed_runs GROUP BY condition ORDER BY condition"
    ).fetchall()
    assert by_condition == [("a", 60), ("b", 60)]
    means = con.sql(
        "SELECT gene, count(*) FROM settled_gene_means(200, 299) GROUP BY gene ORDER BY gene"
    ).fetchall()
    assert [g for g, _ in means] == sorted(gene_names())
    assert all(count <= 120 for _, count in means)


# --- The API server under load (Milestone 5 review) -----------------------------------------------
#
# The in-process test client (tests/api/) calls the app directly, one request at a time. These
# tests start uvicorn on a free port and hit it from threads and real WebSocket clients, which is
# the only way to see request latency under load, dropped viewers, or a race between requests.


class ErrorLog(logging.Handler):
    """Collects everything the server logs at WARNING or above (a 500 shows up here)."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records: list[str] = []

    def emit(self, record):
        self.records.append(self.format(record))


class LiveServer:
    """A real uvicorn server in a thread, with its event loop in hand (to inspect tasks)."""

    def __init__(self, tmp: Path):
        self.manager = RunManager()
        self.app = create_app(self.manager)
        self.app.state.saved_roots = (tmp / "runs",)
        self.app.state.export_root = tmp / "runs" / "live"
        self.app.state.lake = tmp / "lake"
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.base = f"http://127.0.0.1:{self.port}/api"
        self.ws_base = f"ws://127.0.0.1:{self.port}/api"
        self.server = uvicorn.Server(
            uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="warning")
        )
        self.loop = asyncio.new_event_loop()
        self.errors = ErrorLog()
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.server.serve())

    def __enter__(self):
        for name in ("uvicorn.error", "uvicorn", "asyncio"):
            logging.getLogger(name).addHandler(self.errors)
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            assert time.monotonic() < deadline, "the server never started"
            time.sleep(0.01)
        self.http = httpx2.Client(base_url=self.base, timeout=120)
        return self

    def __exit__(self, *exc):
        self.http.close()
        self.server.should_exit = True
        self.thread.join(timeout=30)
        for name in ("uvicorn.error", "uvicorn", "asyncio"):
            logging.getLogger(name).removeHandler(self.errors)

    def create(self, **body) -> dict:
        response = self.http.post("/runs", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    def info(self, run_id: str) -> dict:
        return self.http.get(f"/runs/{run_id}").json()

    def loop_tasks(self) -> list[str]:
        """Names of the live tasks on the server's loop (a stepping loop is named after its run)."""

        async def names():
            return [t.get_name() for t in asyncio.all_tasks() if not t.done()]

        return asyncio.run_coroutine_threadsafe(names(), self.loop).result(timeout=30)

    def run_loops(self) -> list[str]:
        return [n for n in self.loop_tasks() if n in self.manager.runs or "-s" in n]


@pytest.fixture
def live_server(tmp_path):
    with LiveServer(tmp_path) as server:
        yield server
    assert server.errors.records == [], server.errors.records[:5]


def rss_mb() -> float:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return math.nan


def quantiles(seconds: list[float]) -> str:
    s = sorted(seconds)
    at = lambda q: s[min(len(s) - 1, int(q * len(s)))] * 1000  # noqa: E731
    return f"n={len(s)} p50={at(0.5):.1f} ms p95={at(0.95):.1f} ms max={s[-1] * 1000:.1f} ms"


def sample_latency(server: LiveServer, path: str, seconds: float) -> list[float]:
    """GET ``path`` every 20 ms for ``seconds``; the time each answer took."""
    out = []
    with httpx2.Client(base_url=server.base, timeout=60) as client:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            t0 = time.perf_counter()
            assert client.get(path).status_code == 200
            out.append(time.perf_counter() - t0)
            time.sleep(0.02)
    return out


async def watch(
    server: LiveServer, run_id: str, seconds: float, fps: int = 15, until_tick: int | None = None
) -> list[dict]:
    """The snapshots one viewer receives in ``seconds`` (or until it sees ``until_tick``),
    each with the time it arrived."""
    seen = []
    url = f"{server.ws_base}/runs/{run_id}/stream?fps={fps}"
    async with websockets.connect(url, max_size=None) as ws:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.01, end - time.monotonic()))
            except TimeoutError:
                break
            message = json.loads(raw)
            if message["type"] == "snapshot":
                seen.append({"at": time.perf_counter(), "tick": message["tick"], "bytes": len(raw)})
                if until_tick is not None and message["tick"] >= until_tick:
                    break
    return seen


def headless_digest(config_name: str, seed: int, ticks: int) -> str:
    config = apply_changes(
        load_config(CONFIGS / f"{config_name}.yaml"), {"run.seed": seed, "run.max_ticks": ticks}
    )
    sim = Simulation(config)
    sim.run()
    return sim.state_digest()


NEURAL_CROWD = {  # the lab's worst case: 2,000 neural organisms, held there
    "organisms.initial_count": 2000,
    "organisms.max_population": 2000,
    "organisms.initial_energy": 200.0,
    "food.max_count": 2000,
    "food.initial_count": 1000,
    "food.regrowth_per_tick": 100.0,
    "run.stop_on_extinction": False,
}


def test_controls_raced_from_eight_clients_leave_one_loop_and_a_headless_digest(live_server):
    """resume, pause, step and speed fired at one run from eight threads at once: every answer
    is 200 or a clean 409, exactly one loop steps the run, and the final state is still the
    headless run's (a race that stepped twice, or two loops, would change the digest)."""
    ticks = 1500
    rid = live_server.create(config="evolution", seed=21, max_ticks=ticks)["run_id"]
    statuses: dict[int, int] = {}
    lock = threading.Lock()

    def client(seed):
        rng = random.Random(seed)
        with httpx2.Client(base_url=live_server.base, timeout=60) as http:
            for _ in range(60):
                action = rng.choice(["resume", "pause", "step", "speed", "flat_out", "read"])
                if action == "step":
                    r = http.post(f"/runs/{rid}/step", json={"ticks": rng.choice([1, 3, 10])})
                elif action == "speed":
                    r = http.put(
                        f"/runs/{rid}/speed", json={"ticks_per_second": rng.choice([5, 500, 5000])}
                    )
                elif action == "flat_out":
                    r = http.put(f"/runs/{rid}/speed", json={"ticks_per_second": None})
                elif action == "read":
                    r = http.get(f"/runs/{rid}")
                else:
                    r = http.post(f"/runs/{rid}/{action}")
                with lock:
                    statuses[r.status_code] = statuses.get(r.status_code, 0) + 1

    threads = [threading.Thread(target=client, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert set(statuses) <= {200, 409}, statuses
    assert statuses.get(409, 0) > 0  # the race really happened
    if live_server.info(rid)["state"] == "running":
        assert len([n for n in live_server.loop_tasks() if n == rid]) == 1
        live_server.http.post(f"/runs/{rid}/pause")
    live_server.http.put(f"/runs/{rid}/speed", json={"ticks_per_second": None})
    if live_server.info(rid)["state"] != "completed":
        live_server.http.post(f"/runs/{rid}/resume")
    deadline = time.monotonic() + 60
    while live_server.info(rid)["state"] != "completed":
        assert time.monotonic() < deadline
        time.sleep(0.02)
    digest = live_server.http.get(f"/runs/{rid}/digest").json()
    assert digest["tick"] == ticks and digest["digest"] == headless_digest("evolution", 21, ticks)
    print(f"\n  control races: {statuses}")


def test_reset_delete_and_create_spam_leaves_no_orphan_or_duplicate_loops(live_server):
    """Eight clients create, reset, delete, resume, pause and step whatever runs exist. Every
    answer is one of the documented codes, at most four runs exist afterwards, and every
    running run has exactly one loop (none for runs that were deleted or reset)."""
    known = [
        live_server.create(config="default", seed=s, max_ticks=100_000)["run_id"] for s in range(2)
    ]
    for rid in known:
        live_server.http.put(f"/runs/{rid}/speed", json={"ticks_per_second": 50})
        live_server.http.post(f"/runs/{rid}/resume")
    statuses: dict[int, int] = {}
    lock = threading.Lock()

    def client(seed):
        rng = random.Random(seed)
        with httpx2.Client(base_url=live_server.base, timeout=60) as http:
            for _ in range(60):
                with lock:
                    target = rng.choice(known) if known else None
                action = rng.choice(
                    ["reset", "delete", "create", "resume", "pause", "step", "list"]
                )
                if action == "create":
                    r = http.post(
                        "/runs",
                        json={"config": "default", "seed": rng.randint(0, 9), "max_ticks": 100_000},
                    )
                    if r.status_code == 201:
                        with lock:
                            known.append(r.json()["run_id"])
                elif target is None:
                    continue
                elif action == "reset":
                    r = http.post(f"/runs/{target}/reset")
                    if r.status_code == 200:
                        with lock:
                            known.append(r.json()["run_id"])
                elif action == "delete":
                    r = http.delete(f"/runs/{target}")
                elif action == "list":
                    r = http.get("/runs")
                elif action == "step":
                    r = http.post(f"/runs/{target}/step", json={"ticks": 5})
                else:
                    r = http.post(f"/runs/{target}/{action}")
                with lock:
                    statuses[r.status_code] = statuses.get(r.status_code, 0) + 1

    threads = [threading.Thread(target=client, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert set(statuses) <= {200, 201, 204, 404, 409, 429}, statuses
    live = live_server.http.get("/runs").json()
    assert len(live) <= 4
    time.sleep(0.2)  # cancelled loops finish at their next await
    loops = live_server.run_loops()
    running = sorted(r["run_id"] for r in live if r["state"] == "running")
    assert sorted(loops) == running, (loops, running)  # one each, no orphans, no duplicates
    for r in live:
        live_server.http.delete(f"/runs/{r['run_id']}")
    time.sleep(0.2)
    assert live_server.run_loops() == []
    print(f"\n  reset/delete/create spam: {statuses}")


def test_fifty_viewers_some_never_reading_some_churning_leave_no_trace(live_server):
    """40 viewers reading, 10 that never read a byte after connecting, and two clients
    connecting and disconnecting as fast as they can: the run keeps going, memory stays
    bounded, nothing is logged, and the viewer count returns to 0."""
    rid = live_server.create(config="neural", seed=5, max_ticks=1_000_000)["run_id"]
    live_server.http.put(f"/runs/{rid}/speed", json={"ticks_per_second": 200})
    live_server.http.post(f"/runs/{rid}/resume")
    url = f"{live_server.ws_base}/runs/{rid}/stream?fps=30"
    seconds = 3.0

    async def reader():
        frames = 0
        async with websockets.connect(url, max_size=None) as ws:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=0.5)
                    frames += 1
                except TimeoutError:
                    pass
        return frames

    async def never_reads():
        async with websockets.connect(url, max_size=None) as ws:
            ws.transport.pause_reading()  # not even the socket buffer is drained
            await asyncio.sleep(seconds)
            ws.transport.resume_reading()
        return 0

    async def churn(count):
        for i in range(count):
            async with websockets.connect(url, max_size=None) as ws:
                if i % 3 == 0:
                    await ws.recv()  # sometimes read the hello, mostly not
        return count

    async def everyone():
        readers = [reader() for _ in range(40)]
        silent = [never_reads() for _ in range(10)]
        return await asyncio.gather(*readers, *silent, churn(40), churn(40))

    peak = 0

    def count_viewers():
        nonlocal peak
        end = time.monotonic() + seconds - 0.5
        while time.monotonic() < end:
            peak = max(peak, live_server.info(rid)["viewers"])
            time.sleep(0.05)

    rss_before = rss_mb()
    tracemalloc.start()
    heap_before = tracemalloc.get_traced_memory()[0]
    counter = threading.Thread(target=count_viewers)
    counter.start()
    results = asyncio.run(everyone())
    counter.join()
    heap_after = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    deadline = time.monotonic() + 5
    while live_server.info(rid)["viewers"] != 0 and time.monotonic() < deadline:
        time.sleep(0.05)
    info = live_server.info(rid)
    assert info["viewers"] == 0 and info["state"] == "running" and info["tick"] > 100
    assert peak >= 50 and sum(results[:40]) > 40 * 10  # everyone was there; readers got frames
    heap_growth = (heap_after - heap_before) / 1e6  # server and clients share this process
    assert heap_growth < 40, f"python heap grew by {heap_growth:.0f} MB"
    live_server.http.delete(f"/runs/{rid}")
    time.sleep(0.2)
    assert [n for n in live_server.loop_tasks() if n == rid] == []
    print(
        f"\n  viewers: peak {peak}, frames to 40 readers {sum(results[:40])}, "
        f"churn {results[50] + results[51]} connections, "
        f"RSS {rss_before:.0f} -> {rss_mb():.0f} MB, heap +{heap_growth:.1f} MB"
    )


def test_lake_routes_answer_while_runs_step_and_exports_ingest(live_server):
    """Six threads query every lake route without pause while two runs step flat out and a
    seventh thread steps a third run and exports it into the lake again and again. Every
    answer is 200 (the DuckDB connection is shared under a lock), and no export fails."""
    a = live_server.create(
        config="default", seed=31, max_ticks=100_000, changes={"run.stop_on_extinction": False}
    )["run_id"]
    b = live_server.create(config="neural", seed=32, max_ticks=100_000)["run_id"]
    c = live_server.create(config="evolution", seed=33, max_ticks=5000)["run_id"]
    for rid in (a, b, c):
        live_server.http.put(f"/runs/{rid}/speed", json={"ticks_per_second": None})
    live_server.http.post(f"/runs/{c}/step", json={"ticks": 300})
    first = live_server.http.post(f"/runs/{c}/export", params={"ingest": "true"})
    assert first.status_code == 200 and first.json()["ingested"], first.text
    for rid in (a, b):
        live_server.http.post(f"/runs/{rid}/resume")
    statuses: dict[tuple[str, int], int] = {}
    lock = threading.Lock()
    stop = threading.Event()
    latencies: list[float] = []
    paths = (
        "/lake/experiments",
        "/lake/runs",
        f"/lake/runs/{c}-t300",
        f"/lake/runs/{c}-t300/series",
    )

    def querier():
        with httpx2.Client(base_url=live_server.base, timeout=120) as http:
            while not stop.is_set():
                for path in paths:
                    t0 = time.perf_counter()
                    r = http.get(path)
                    with lock:
                        latencies.append(time.perf_counter() - t0)
                        statuses[(path, r.status_code)] = statuses.get((path, r.status_code), 0) + 1

    def exporter():
        with httpx2.Client(base_url=live_server.base, timeout=300) as http:
            while not stop.is_set():
                http.post(f"/runs/{c}/step", json={"ticks": 50})
                r = http.post(f"/runs/{c}/export", params={"ingest": "true"})
                with lock:
                    statuses[("export", r.status_code)] = (
                        statuses.get(("export", r.status_code), 0) + 1
                    )
                assert r.status_code == 200 and r.json()["ingested"], r.text

    threads = [threading.Thread(target=querier) for _ in range(6)] + [
        threading.Thread(target=exporter)
    ]
    for t in threads:
        t.start()
    time.sleep(5.0)
    stop.set()
    for t in threads:
        t.join()
    for rid in (a, b):
        live_server.http.post(f"/runs/{rid}/pause")
    assert {code for _, code in statuses} == {200}, statuses
    assert sum(n for (p, _), n in statuses.items() if p == "export") >= 2
    print(
        f"\n  lake under load: {sum(statuses.values())} requests, GET {quantiles(latencies)}, "
        f"runs reached {live_server.info(a)['tick']} and {live_server.info(b)['tick']} ticks"
    )


@pytest.mark.slow
def test_four_runs_flat_out_including_two_thousand_neural_organisms_stay_responsive(live_server):
    """The limit of four live runs, all flat out, one of them the lab's worst case. Requests
    and a viewer's frames keep coming (a tick of the big run is ~50 ms and can't be cut, so
    a request may wait for one), and nothing is logged."""
    rids = [
        live_server.create(config="evolution", seed=1, max_ticks=1_000_000)["run_id"],
        live_server.create(
            config="default", seed=2, max_ticks=1_000_000, changes={"run.stop_on_extinction": False}
        )["run_id"],
        live_server.create(config="neural", seed=3, max_ticks=1_000_000)["run_id"],
        live_server.create(config="neural", seed=4, max_ticks=1_000_000, changes=NEURAL_CROWD)[
            "run_id"
        ],
    ]
    assert live_server.info(rids[3])["population"] == 2000
    for rid in rids:
        live_server.http.put(f"/runs/{rid}/speed", json={"ticks_per_second": None})
        live_server.http.post(f"/runs/{rid}/resume")
    seconds = 10.0
    with ThreadPoolExecutor(1) as pool:
        viewer = pool.submit(lambda: asyncio.run(watch(live_server, rids[3], seconds)))
        latencies = sample_latency(live_server, "/runs", seconds)
        frames = viewer.result()
    infos = [live_server.info(rid) for rid in rids]
    for rid in rids:
        live_server.http.post(f"/runs/{rid}/pause")
    assert all(i["state"] == "running" and i["tick"] > 50 for i in infos), infos
    assert statistics.median(latencies) < 1.0 and max(latencies) < 5.0, quantiles(latencies)
    gaps = [b["at"] - a["at"] for a, b in zip(frames, frames[1:], strict=False)]
    assert len(frames) >= seconds * 2 and max(gaps) < 2.0, quantiles(gaps)
    assert [f["tick"] for f in frames] == sorted(f["tick"] for f in frames)  # newest only
    size_kb = statistics.mean(f["bytes"] for f in frames) / 1024
    print(
        f"\n  four runs flat out: GET /runs {quantiles(latencies)}; viewer of the 2,000-organism "
        f"run: {len(frames)} frames, gaps {quantiles(gaps)}, {size_kb:.0f} KB each; "
        + "; ".join(f"{i['config_name']} s{i['seed']} tick {i['tick']}" for i in infos)
    )


@pytest.mark.slow
def test_a_long_step_keeps_viewers_connected_and_the_server_answering(live_server):
    """Before the review a 2,500-tick step of the 2,000-organism run blocked the server for
    44 s and every viewer was dropped (keepalive ping timeout, close code 1011). Now a step
    yields between slices: the viewer sees the tick advance, and requests are answered."""
    rid = live_server.create(config="neural", seed=4, max_ticks=1_000_000, changes=NEURAL_CROWD)[
        "run_id"
    ]
    ticks = 300  # 6-15 s of stepping, depending on the machine
    with ThreadPoolExecutor(2) as pool:
        viewer = pool.submit(lambda: asyncio.run(watch(live_server, rid, 120.0, until_tick=ticks)))
        time.sleep(0.5)
        step = pool.submit(
            lambda: httpx2.post(
                f"{live_server.base}/runs/{rid}/step", json={"ticks": ticks}, timeout=300
            )
        )
        time.sleep(0.5)
        latencies = sample_latency(live_server, "/health", 3.0)
        frames = viewer.result()
        response = step.result()
    assert response.status_code == 200 and response.json()["tick"] == ticks
    ticks_seen = sorted({f["tick"] for f in frames})
    # Before the fix the viewer saw tick 0 and then nothing until the step ended (or the drop).
    assert len(ticks_seen) > 10 and ticks_seen[-1] == ticks, ticks_seen[:5]
    assert max(latencies) < 1.0, quantiles(latencies)
    print(
        f"\n  step {ticks} on 2,000 neural organisms: {response.elapsed.total_seconds():.1f} s; "
        f"viewer saw {len(frames)} frames ({len(ticks_seen)} distinct ticks); "
        f"GET /health {quantiles(latencies)}"
    )


@pytest.mark.slow
def test_a_long_run_keeps_history_small_and_exports_exactly_while_another_steps(live_server):
    """120,000 ticks flat out: the per-tick history stays at 88 bytes a tick, a client's
    once-a-second "what's new" poll stays cheap, and the export's replay (in a worker thread)
    matches the live digest while another run keeps stepping."""
    ticks = 120_000
    rid = live_server.create(
        config="default", seed=7, max_ticks=ticks, changes={"run.stop_on_extinction": False}
    )["run_id"]
    other = live_server.create(config="evolution", seed=8, max_ticks=1_000_000)["run_id"]
    for r in (rid, other):
        live_server.http.put(f"/runs/{r}/speed", json={"ticks_per_second": None})
    rss_before = rss_mb()
    t0 = time.monotonic()
    live_server.http.post(f"/runs/{rid}/resume")
    polls: list[float] = []
    since = 0
    while live_server.info(rid)["state"] != "completed":
        assert time.monotonic() - t0 < 600, "the run should finish in a few minutes"
        t1 = time.perf_counter()
        page = live_server.http.get(
            f"/runs/{rid}/history", params={"every": 200, "since": since}
        ).json()
        polls.append(time.perf_counter() - t1)
        if page["columns"]["tick"]:
            since = page["columns"]["tick"][-1] + 1
        time.sleep(1.0)
    run_seconds = time.monotonic() - t0
    history = live_server.manager.get(rid).history
    history_mb = sum(len(a) * a.itemsize for a in history._data.values()) / 1e6
    assert len(history) == ticks and history_mb < 12
    assert statistics.median(polls) < 0.25, quantiles(polls)
    whole = live_server.http.get(f"/runs/{rid}/history", params={"every": 200}).json()["columns"]
    assert whole["tick"][-1] == ticks - 1 and len(whole["tick"]) == ticks // 200

    live_server.http.post(f"/runs/{other}/resume")
    time.sleep(1.0)
    before = live_server.info(other)["tick"]
    t2 = time.perf_counter()
    with ThreadPoolExecutor(1) as pool:
        export = pool.submit(
            lambda: httpx2.post(
                f"{live_server.base}/runs/{rid}/export", params={"ingest": "true"}, timeout=900
            )
        )
        latencies = sample_latency(live_server, "/runs", 5.0)
        result = export.result()
    export_seconds = time.perf_counter() - t2
    after = live_server.info(other)["tick"]
    live_server.http.post(f"/runs/{other}/pause")
    body = result.json()
    assert result.status_code == 200 and body["matches_live_run"] and body["ingested"], body
    assert body["ticks"] == ticks
    assert after - before > 100, "the other run stalled during the export"
    assert statistics.median(latencies) < 0.5, quantiles(latencies)
    print(
        f"\n  long run: {ticks} ticks in {run_seconds:.0f} s, history {history_mb:.1f} MB, "
        f"RSS {rss_before:.0f} -> {rss_mb():.0f} MB, since-poll {quantiles(polls)}; "
        f"export {export_seconds:.0f} s, the other run did "
        f"{(after - before) / export_seconds:.0f} ticks/s meanwhile, "
        f"GET /runs {quantiles(latencies)}"
    )
