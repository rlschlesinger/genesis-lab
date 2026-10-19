"""E002: machinery checks and the positive control. Definition: docs/experiments/E002-*.md

Run:          uv run python experiments/e002_selection_machinery.py
Re-analyse:   ... --analyse-only     (from recorded files, no simulation)
Code check:   ... --smoke            (2 throwaway seeds, 600 ticks; not the experiment)
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

import numpy as np

from genesis.analytics.batch import run_experiment
from genesis.analytics.experiments import (
    genomes_never_changed,
    paired,
    run_dir_for,
    settled_gene_means,
)
from genesis.analytics.significance import holm, paired_permutation_test, sign_test
from genesis.analytics.spec import load_spec
from genesis.core.config import load_config

EXPERIMENT_ID = "E002"
ROOT = Path(__file__).parents[1]
GENES = ["metabolic_rate", "speed", "sense_range", "reproduction_threshold"]  # H6a-H6d
SPEC = load_spec(ROOT / "experiments" / "specs" / "E002.yaml")
CONDITIONS = [SPEC.condition(c.label) for c in SPEC.conditions]  # off, neutral, selection


def settings(smoke: bool) -> dict:
    """Seeds, conditions and output come from the spec file (the single definition)."""
    spec = SPEC
    window, samples = (19_000, 19_999), 20_000
    if smoke:
        spec = SPEC.model_copy(
            update={
                "seeds": [9100, 9101],
                "base_changes": {**SPEC.base_changes, "run.max_ticks": 600},
                "output": "data/experiments/E002-smoke",
            }
        )
        window, samples = (500, 599), 500
    return dict(
        spec=spec,
        seeds=spec.seed_list(),
        window=window,
        samples=samples,
        out=spec.output_dir(),
        ingest=not smoke,
    )


def run(s: dict, rerun_stale: bool) -> None:
    print(f"running {len(s['seeds'])} seeds x {len(CONDITIONS)} conditions in parallel ...")
    outcomes = run_experiment(s["spec"], rerun_stale=rerun_stale, ingest=s["ingest"])
    failed = [o for o in outcomes if not o.ok]
    print(f"ran {len(outcomes)} runs, {len(failed)} failed")


def analyse(s: dict) -> None:
    seeds, out, (first, last) = list(s["seeds"]), s["out"], s["window"]
    bounds = load_config(ROOT / "configs" / "evolution.yaml").genome

    print("\nC1 machinery: genomes unchanged in every 'off' run?")
    unchanged = [genomes_never_changed(run_dir_for(out, CONDITIONS[0], seed)) for seed in seeds]
    print(f"  {sum(unchanged)}/{len(seeds)} runs: {'PASS' if all(unchanged) else 'FAIL'}")

    means = {
        c.label: {
            seed: settled_gene_means(run_dir_for(out, c, seed), first, last) for seed in seeds
        }
        for c in CONDITIONS[1:]
    }

    def gene(label: str, g: str) -> dict:
        return {seed: (m[g] if m else None) for seed, m in means[label].items()}

    rng = np.random.default_rng(2002)
    results = []
    print(f"\nselection - neutral, settled mean over ticks {first}-{last}")
    print(
        f"  {'gene':<23} {'median diff':>12} {'(of range)':>10} {'range of diffs':>24}"
        f" {'+/-':>6} {'sign p':>8} {'perm p':>8}"
    )
    for g in [*GENES, "neutral_marker"]:
        diffs, dropped = paired(gene("selection", g), gene("neutral", g))
        span = getattr(bounds, g).max - getattr(bounds, g).min
        st, pt = sign_test(diffs), paired_permutation_test(diffs, rng=rng, n_samples=s["samples"])
        med = statistics.median(diffs)
        results.append((g, pt.p_value, med))
        print(
            f"  {g:<23} {med:>12.4f} {med / span:>10.1%} {min(diffs):>11.4f} to {max(diffs):<10.4f}"
            f" {st.positive:>2}/{st.negative:<3} {st.p_value:>8.4f} {pt.p_value:>8.4f}"
            + (f"  dropped seeds {dropped}" if dropped else "")
        )

    hypotheses = results[:4]
    adjusted = holm([p for _, p, _ in hypotheses])
    print("\nHypotheses (Holm-adjusted across H6a-H6d):")
    for (g, p, med), adj, label in zip(
        hypotheses, adjusted, ["H6a", "H6b", "H6c", "H6d"], strict=True
    ):
        verdict = "supported" if adj < 0.05 and (label != "H6a" or med < 0) else "not supported"
        print(f"  {label} {g:<23} p={p:.4f}  adjusted={adj:.4f}  -> {verdict}")
    marker_p = results[4][1]
    print(
        f"\nC2 calibration (neutral_marker): p={marker_p:.4f} -> "
        f"{'PASS' if marker_p > 0.05 else 'FAIL: investigate'}"
    )

    print("\nC3 drift expectation: neutral runs whose gene mean moved toward its range midpoint")
    for g in [*GENES, "neutral_marker"]:
        b = getattr(bounds, g)
        mid = (b.min + b.max) / 2
        vals = [v for v in gene("neutral", g).values() if v is not None]
        toward = sum(abs(v - mid) < abs(b.initial - mid) for v in vals)
        print(f"  {g:<23} start {b.initial:g}, midpoint {mid:g}: {toward}/{len(vals)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--analyse-only", action="store_true")
    parser.add_argument(
        "--rerun-stale",
        action="store_true",
        help="re-run completed runs whose config differs from the spec",
    )
    args = parser.parse_args()
    s = settings(args.smoke)
    if not args.analyse_only:
        run(s, args.rerun_stale)
    analyse(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
