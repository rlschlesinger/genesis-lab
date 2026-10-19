"""Shared command line for experiment analysis scripts (experiments/e00N_*.py).

    uv run python experiments/e004_food_dose_response.py                # run, then analyse
    uv run python experiments/e004_food_dose_response.py --analyse-only # analyse saved runs
    uv run python experiments/e004_food_dose_response.py --smoke        # tiny code check

A smoke run uses throwaway seeds, short runs, and its own output folder and lake, so it can't
touch the real experiment.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from genesis.analytics.batch import run_experiment
from genesis.analytics.spec import PROJECT_ROOT, ExperimentSpec, load_spec
from genesis.lake.ingest import DEFAULT_LAKE

SMOKE_SEEDS = [9100, 9101]


def experiment_main(
    spec_file: str,
    analyse: Callable[[ExperimentSpec, Path, bool], None],
    smoke_ticks: int,
) -> int:
    """Parse the standard options, run what's needed, then call ``analyse(spec, lake, smoke)``."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="tiny code check (throwaway seeds)")
    parser.add_argument("--analyse-only", action="store_true", help="don't run; analyse saved runs")
    parser.add_argument(
        "--rerun-stale",
        action="store_true",
        help="re-run completed runs whose config differs from the spec",
    )
    args = parser.parse_args()

    spec = load_spec(PROJECT_ROOT / "experiments" / "specs" / spec_file)
    lake = PROJECT_ROOT / DEFAULT_LAKE
    if args.smoke:
        spec = spec.smoke_copy(SMOKE_SEEDS, smoke_ticks)
        lake = spec.output_dir() / "lake"
    if not args.analyse_only:
        planned = len(spec.seed_list()) * len(spec.conditions)
        print(f"{spec.experiment_id}: {planned} runs planned; running what isn't complete ...")
        outcomes = run_experiment(spec, rerun_stale=args.rerun_stale, lake=lake)
        print(f"ran {len(outcomes)}, failed {sum(not o.ok for o in outcomes)}\n")
    analyse(spec, lake, args.smoke)
    return 0
