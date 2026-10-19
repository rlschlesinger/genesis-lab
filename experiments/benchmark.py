"""Throughput benchmark: simulation speed at different population sizes.

Run:  uv run python experiments/benchmark.py
      uv run python experiments/benchmark.py --sizes 30,100,300,1000,3000 --ticks 100
      uv run python experiments/benchmark.py --evolution    # configs/evolution.yaml, with and
                                                            # without the RunRecorder

Population is held near a target size by setting initial_count = max_population = N and
giving food generously, so the population starts and stays near N. Each size is timed over
several repeats; the best repeat is reported, because slower repeats measure interference
from other programs, not the simulation.
"""

from __future__ import annotations

import argparse
import platform
import time
from pathlib import Path

import numpy as np

from genesis.analytics.recorder import RunRecorder
from genesis.core.config import SimulationConfig, load_config
from genesis.core.simulation import Simulation

CONFIGS = Path(__file__).parents[1] / "configs"
DEFAULT_CONFIG = CONFIGS / "default.yaml"
EVOLUTION_CONFIG = CONFIGS / "evolution.yaml"
SIZES = [30, 100, 300, 1000]
TICKS = 200
REPEATS = 3
EVOLUTION_SEED, EVOLUTION_TICKS, EVOLUTION_REPEATS = 9100, 5000, 2


def config_for(n: int, ticks: int = TICKS) -> SimulationConfig:
    raw = load_config(DEFAULT_CONFIG).model_dump()
    raw["run"].update(max_ticks=ticks, stop_on_extinction=False)
    raw["organisms"].update(initial_count=n, max_population=n, initial_energy=200.0)
    raw["food"].update(
        max_count=max(300, n), initial_count=max(150, n // 2), regrowth_per_tick=n * 0.05
    )
    return SimulationConfig.model_validate(raw)


def population_sweep(sizes: list[int], ticks: int) -> None:
    print(f"{ticks} ticks per repeat, best of {REPEATS}\n")
    header = ["target N", "mean pop", "mean food", "ticks/s", "us per organism-tick"]
    widths = [8, 8, 9, 8, 20]
    print("  ".join(f"{h:>{w}}" for h, w in zip(header, widths, strict=True)))
    for n in sizes:
        best = np.inf
        for _ in range(REPEATS):
            sim = Simulation(config_for(n, ticks))
            start = time.perf_counter()
            summaries = sim.run()
            best = min(best, time.perf_counter() - start)
        pop = np.mean([s.population for s in summaries])
        food = np.mean([s.food_count for s in summaries])
        print(
            f"{n:>8}  {pop:>8.0f}  {food:>9.0f}  {ticks / best:>8.0f}  "
            f"{best / (ticks * pop) * 1e6:>20.1f}"
        )


def evolution_run(record: bool) -> SimulationConfig:
    raw = load_config(EVOLUTION_CONFIG).model_dump()
    raw["run"].update(seed=EVOLUTION_SEED, max_ticks=EVOLUTION_TICKS)
    return SimulationConfig.model_validate(raw)


def evolution_timing() -> None:
    """configs/evolution.yaml as the experiments run it, alone and with the recorder."""
    print(
        f"\nconfigs/evolution.yaml, seed {EVOLUTION_SEED}, {EVOLUTION_TICKS} ticks, "
        f"best of {EVOLUTION_REPEATS}"
    )
    for record in (False, True):
        best, pop = np.inf, 0.0
        for _ in range(EVOLUTION_REPEATS):
            sim = Simulation(evolution_run(record))
            recorder = RunRecorder(genome_snapshot_every=50) if record else None
            start = time.perf_counter()
            summaries = []
            while not sim.finished:
                summary = sim.step()
                summaries.append(summary)
                if recorder is not None:
                    recorder.observe(sim, summary)
            best = min(best, time.perf_counter() - start)
            pop = np.mean([s.population for s in summaries])
        label = "with RunRecorder" if record else "simulation alone"
        print(f"  {label:17s} {sim.tick / best:>6.0f} ticks/s  (mean population {pop:.0f})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sizes", default=",".join(map(str, SIZES)), help="e.g. 30,100,3000")
    parser.add_argument("--ticks", type=int, default=TICKS, help="ticks per repeat")
    parser.add_argument("--evolution", action="store_true", help="also time evolution.yaml")
    args = parser.parse_args()
    print(f"Python {platform.python_version()}, NumPy {np.__version__}, {platform.machine()}")
    population_sweep([int(s) for s in args.sizes.split(",")], args.ticks)
    if args.evolution:
        evolution_timing()


if __name__ == "__main__":
    main()
