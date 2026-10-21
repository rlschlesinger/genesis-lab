"""E008 tuning pilots: settings where predators and prey usually both survive (6.6).

    uv run python experiments/pilots/e008_tuning.py --round 1|2|3 [--seeds 6]

**Tuning, not results.** These runs choose E008's fixed settings before E008 is defined; they
answer "which settings keep both species alive?", never E008's question (do prey evolve to
escape?). They use seeds 90000 and up, which no experiment uses, and nothing here is analysed
as evidence. The table they print is recorded in docs/experiments/pilots/E008-tuning.md.

Each pilot is predators.yaml (neural prey) with a few predator settings changed, run for
``--ticks`` ticks or until both species are gone. Reported per setting: how many seeds kept
both species to the end, when prey or predators died out (median over seeds where they did),
and the mean numbers of each over the last fifth of the runs that kept both.
"""

from __future__ import annotations

import argparse
import itertools
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from genesis.analytics.experiments import apply_changes
from genesis.core.config import SimulationConfig, load_config
from genesis.core.simulation import Simulation

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "configs" / "predators.yaml"
FIRST_SEED = 90000

# Each round: settings changed for every pilot (base), the grid tried, and the run length.
# Rounds were run in order, each designed after reading the one before
# (docs/experiments/pilots/E008-tuning.md says what each one showed).
ROUNDS: dict[int, dict] = {
    # 1: span "clearly too strong" (the placeholders, which overkill) to "clearly too weak".
    1: {
        "base": {},
        "grid": {
            "predators.initial_count": [3, 6],
            "predators.capture_probability": [0.1, 0.25],
            "predators.genome.speed.initial": [1.5, 1.8],
            "predators.capture_efficiency": [0.5, 0.8],
            "predators.genome.reproduction_threshold.initial": [160.0, 240.0],
        },
        "ticks": 10000,
    },
    # 2: round 1's prey often died out after few captures: 30 founders with random brains dip
    # to ~20 before brains that feed take over. Does starting with 100 prey avoid that?
    2: {
        "base": {"organisms.initial_count": 100, "predators.genome.speed.initial": 1.5,
                 "predators.capture_efficiency": 0.5},
        "grid": {
            "predators.initial_count": [3, 6],
            "predators.capture_probability": [0.1, 0.25],
            "predators.genome.reproduction_threshold.initial": [160.0, 240.0],
        },
        "ticks": 10000,
    },
    # 3: with 100 prey, weak chasers never ended the prey; small predator populations died out
    # instead. A cap on predators limits booms (overkill) without starving them; 20,000 ticks
    # is E007's training length.
    3: {
        "base": {"organisms.initial_count": 100, "predators.genome.speed.initial": 1.5,
                 "predators.capture_efficiency": 0.5,
                 "predators.genome.reproduction_threshold.initial": 240.0},
        "grid": {
            "predators.initial_count": [4, 8],
            "predators.capture_probability": [0.08, 0.12, 0.18],
            "predators.max_population": [10, 20],
        },
        "ticks": 20000,
    },
    # 4: round 3's two best settings again, on twice as many seeds (chasers only: neural
    # predators starved within ~800 ticks in every round-3 pilot).
    4: {
        "base": {"organisms.initial_count": 100, "predators.genome.speed.initial": 1.5,
                 "predators.capture_efficiency": 0.5,
                 "predators.genome.reproduction_threshold.initial": 240.0,
                 "predators.max_population": 10},
        "grid": {
            "predators.initial_count": [4, 8],
            "predators.capture_probability": [0.12, 0.18],
        },
        "ticks": 20000,
        "controllers": ["nearest_prey_seeker"],
        "seeds": 12,
    },
}  # fmt: skip
CONTROLLERS = ["nearest_prey_seeker", "neural"]


def config_for(controller: str, setting: dict, seed: int, ticks: int) -> SimulationConfig:
    raw = apply_changes(
        load_config(BASE), {**setting, "run.seed": seed, "run.max_ticks": ticks}
    ).model_dump()
    raw["predators"]["controller"] = controller
    if controller == "neural":
        raw["predators"]["brain"] = {}
    # A threshold above the genome's max would be invalid; widen the max to fit.
    gene = raw["predators"]["genome"]["reproduction_threshold"]
    gene["max"] = max(gene["max"], gene["initial"])
    return SimulationConfig.model_validate(raw)


def pilot(args: tuple[str, dict, int, int]) -> dict:
    controller, setting, seed, ticks = args
    sim = Simulation(config_for(controller, setting, seed, ticks))
    prey_gone = predators_gone = None
    tail_prey, tail_predators, captures = [], [], 0
    while not sim.finished:
        sim.step()
        captures += sim.predator_summary.captures
        if prey_gone is None and not sim.organisms:
            prey_gone = sim.tick
        if predators_gone is None and not sim.predators:
            predators_gone = sim.tick
        if sim.tick > 0.8 * ticks:
            tail_prey.append(len(sim.organisms))
            tail_predators.append(len(sim.predators))
    return {
        "controller": controller,
        "setting": tuple(setting.items()),
        "seed": seed,
        "both": prey_gone is None and predators_gone is None,
        "prey_gone": prey_gone,
        "predators_gone": predators_gone,
        "captures": captures,
        "tail_prey": statistics.fmean(tail_prey) if tail_prey else 0.0,
        "tail_predators": statistics.fmean(tail_predators) if tail_predators else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--round", type=int, choices=sorted(ROUNDS), required=True)
    parser.add_argument("--seeds", type=int, default=6, help="unless the round sets its own")
    args = parser.parse_args()
    spec = ROUNDS[args.round]
    grid, ticks = spec["grid"], spec["ticks"]
    names = list(grid)
    settings = [
        {**spec["base"], **dict(zip(names, values, strict=True))}
        for values in itertools.product(*grid.values())
    ]
    seeds = spec.get("seeds", args.seeds)
    jobs = [
        (controller, setting, FIRST_SEED + k, ticks)
        for controller in spec.get("controllers", CONTROLLERS)
        for setting in settings
        for k in range(seeds)
    ]
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(pilot, jobs, chunksize=4))

    short = {"predators.initial_count": "n", "predators.capture_probability": "p",
             "predators.genome.speed.initial": "speed", "predators.capture_efficiency": "eff",
             "predators.genome.reproduction_threshold.initial": "thresh",
             "predators.max_population": "cap"}  # fmt: skip
    fixed = ", ".join(f"{k} {v:g}" for k, v in spec["base"].items()) or "none"
    print(f"round {args.round}: {ticks} ticks, seeds {FIRST_SEED}-{FIRST_SEED + seeds - 1}")
    print(f"fixed for this round: {fixed}\n")
    print(f"{'predators':<20}{'setting':<44}{'both':>6}{'prey out':>10}{'pred out':>10}"
          f"{'prey':>7}{'pred':>6}{'caught':>8}")  # fmt: skip
    groups: dict[tuple, list[dict]] = {}
    for r in results:
        groups.setdefault((r["controller"], r["setting"]), []).append(r)
    rows = sorted(groups.items(), key=lambda kv: (-sum(r["both"] for r in kv[1]), kv[0]))
    for (controller, setting), runs in rows:
        both = [r for r in runs if r["both"]]
        label = " ".join(f"{short[k]}={v:g}" for k, v in setting if k in grid)

        def median(key: str, runs: list[dict] = runs) -> str:
            values = [r[key] for r in runs if r[key] is not None]
            return f"{statistics.median(values):.0f}" if values else "-"

        prey = f"{statistics.fmean(r['tail_prey'] for r in both):.0f}" if both else "-"
        pred = f"{statistics.fmean(r['tail_predators'] for r in both):.0f}" if both else "-"
        caught = f"{statistics.fmean(r['captures'] for r in runs):.0f}"
        print(f"{controller:<20}{label:<44}{len(both):>3}/{len(runs):<2}{median('prey_gone'):>10}"
              f"{median('predators_gone'):>10}{prey:>7}{pred:>6}{caught:>8}")  # fmt: skip
        ends = [
            "both"
            if r["both"]
            else f"prey {r['prey_gone']}"
            if r["prey_gone"] is not None
            else f"pred {r['predators_gone']}"
            for r in sorted(runs, key=lambda r: r["seed"])
        ]
        print(f"{'':<20}  per seed: {', '.join(ends)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
