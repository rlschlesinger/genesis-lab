"""E003: does food scarcity change selection? 2x2 design. Definition: docs/experiments/E003-*.md

Run:          uv run python experiments/e003_food_scarcity.py
Re-analyse:   ... --analyse-only     (from recorded files, no simulation)
Code check:   ... --smoke            (2 throwaway seeds, 600 ticks; not the experiment)
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

import numpy as np

from genesis.analytics.experiments import (
    Condition,
    apply_changes,
    run_condition,
    run_dir_for,
    settled_gene_means,
)
from genesis.analytics.significance import holm, paired_permutation_test, sign_test
from genesis.core.config import load_config

EXPERIMENT_ID = "E003"
ROOT = Path(__file__).parents[1]
GENES = ["sense_range", "speed", "reproduction_threshold", "metabolic_rate"]  # H7a-H7d
PREDICTED_SIGN = {"sense_range": +1}  # H7a; the others have no predicted direction
NEUTRALIZE = {f"genome.{g}.neutral": True for g in [*GENES, "max_turn"]}
SCARCE = {"food.regrowth_per_tick": 1.0}
CONDITIONS = {
    "S_plenty": Condition("S_plenty", {}),
    "N_plenty": Condition("N_plenty", NEUTRALIZE),
    "S_scarce": Condition("S_scarce", SCARCE),
    "N_scarce": Condition("N_scarce", {**SCARCE, **NEUTRALIZE}),
}


def settings(smoke: bool) -> dict:
    if smoke:
        return dict(
            seeds=range(9100, 9102),
            ticks=600,
            window=(500, 599),
            samples=500,
            out=ROOT / "data" / "experiments" / "E003-smoke",
        )
    return dict(
        seeds=range(2000, 2020),
        ticks=20_000,
        window=(19_000, 19_999),
        samples=20_000,
        out=ROOT / "data" / "experiments" / EXPERIMENT_ID,
    )


def run(s: dict) -> None:
    base = apply_changes(
        load_config(ROOT / "configs" / "evolution.yaml"), {"run.max_ticks": s["ticks"]}
    )
    for condition in CONDITIONS.values():
        print(f"running {condition.label} x {len(s['seeds'])} seeds ...", flush=True)
        run_condition(base, condition, s["seeds"], s["out"], EXPERIMENT_ID)


def analyse(s: dict) -> None:
    seeds, out, (first, last) = list(s["seeds"]), s["out"], s["window"]
    means = {
        label: {seed: settled_gene_means(run_dir_for(out, c, seed), first, last) for seed in seeds}
        for label, c in CONDITIONS.items()
    }
    usable = [seed for seed in seeds if all(means[label][seed] for label in CONDITIONS)]
    dropped = sorted(set(seeds) - set(usable))
    print(
        f"\nusable seeds: {len(usable)}/{len(seeds)}" + (f"; dropped {dropped}" if dropped else "")
    )
    if len(seeds) - len(usable) > 4 and len(seeds) >= 20:
        print("MORE THAN 4 SEEDS DROPPED: experiment inconclusive by its definition")

    def effect(gene: str, food: str, seed: int) -> float:
        return means[f"S_{food}"][seed][gene] - means[f"N_{food}"][seed][gene]

    rng = np.random.default_rng(2003)
    rows = []
    print(f"\nselection effect (S - N) and interaction (scarce - plenty), ticks {first}-{last}")
    print(
        f"  {'gene':<23} {'plenty eff':>11} {'scarce eff':>11} {'interaction':>12}"
        f" {'range':>24} {'+/-':>6} {'sign p':>8} {'perm p':>8}"
    )
    for g in [*GENES, "neutral_marker"]:
        plenty = [effect(g, "plenty", seed) for seed in usable]
        scarce = [effect(g, "scarce", seed) for seed in usable]
        inter = [b - a for a, b in zip(plenty, scarce, strict=True)]
        st, pt = sign_test(inter), paired_permutation_test(inter, rng=rng, n_samples=s["samples"])
        med = statistics.median(inter)
        rows.append((g, pt.p_value, med))
        print(
            f"  {g:<23} {statistics.median(plenty):>11.4f} {statistics.median(scarce):>11.4f}"
            f" {med:>12.4f} {min(inter):>11.4f} to {max(inter):<10.4f}"
            f" {st.positive:>2}/{st.negative:<3} {st.p_value:>8.4f} {pt.p_value:>8.4f}"
        )

    hypotheses = rows[:4]
    adjusted = holm([p for _, p, _ in hypotheses])
    print("\nHypotheses (Holm-adjusted across H7a-H7d):")
    for (g, p, med), adj, label in zip(
        hypotheses, adjusted, ["H7a", "H7b", "H7c", "H7d"], strict=True
    ):
        direction_ok = g not in PREDICTED_SIGN or np.sign(med) == PREDICTED_SIGN[g]
        verdict = "supported" if adj < 0.05 and direction_ok else "not supported"
        if g == "metabolic_rate":
            verdict = (
                "interaction detected" if adj < 0.05 else "no interaction detected (as predicted)"
            )
        print(f"  {label} {g:<23} p={p:.4f}  adjusted={adj:.4f}  -> {verdict}")
    print(
        f"\ncalibration (neutral_marker interaction): p={rows[4][1]:.4f} -> "
        f"{'PASS' if rows[4][1] > 0.05 else 'FAIL: investigate'}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--analyse-only", action="store_true")
    args = parser.parse_args()
    s = settings(args.smoke)
    if not args.analyse_only:
        run(s)
    analyse(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
