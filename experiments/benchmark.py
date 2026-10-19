"""Throughput benchmark: simulation speed at different population sizes.

Run:  uv run python experiments/benchmark.py

Population is held near a target size by setting initial_count = max_population = N and
giving food generously, so the population starts and stays near N. Each size is timed over
several repeats; the best repeat is reported, because slower repeats measure interference
from other programs, not the simulation.
"""

from __future__ import annotations

import platform
import time
from pathlib import Path

import numpy as np

from genesis.core.config import SimulationConfig, load_config
from genesis.core.simulation import Simulation

DEFAULT_CONFIG = Path(__file__).parents[1] / "configs" / "default.yaml"
SIZES = [30, 100, 300, 1000]
TICKS = 200
REPEATS = 3


def config_for(n: int) -> SimulationConfig:
    raw = load_config(DEFAULT_CONFIG).model_dump()
    raw["run"].update(max_ticks=TICKS, stop_on_extinction=False)
    raw["organisms"].update(initial_count=n, max_population=n, initial_energy=200.0)
    raw["food"].update(
        max_count=max(300, n), initial_count=max(150, n // 2), regrowth_per_tick=n * 0.05
    )
    return SimulationConfig.model_validate(raw)


def main() -> None:
    print(f"Python {platform.python_version()}, NumPy {np.__version__}, {platform.machine()}")
    print(f"{TICKS} ticks per repeat, best of {REPEATS}\n")
    header = ["target N", "mean pop", "mean food", "ticks/s", "us per organism-tick"]
    widths = [8, 8, 9, 8, 20]
    print("  ".join(f"{h:>{w}}" for h, w in zip(header, widths, strict=True)))
    for n in SIZES:
        best = np.inf
        for _ in range(REPEATS):
            sim = Simulation(config_for(n))
            start = time.perf_counter()
            summaries = sim.run()
            best = min(best, time.perf_counter() - start)
        pop = np.mean([s.population for s in summaries])
        food = np.mean([s.food_count for s in summaries])
        print(
            f"{n:>8}  {pop:>8.0f}  {food:>9.0f}  {TICKS / best:>8.0f}  "
            f"{best / (TICKS * pop) * 1e6:>20.1f}"
        )


if __name__ == "__main__":
    main()
