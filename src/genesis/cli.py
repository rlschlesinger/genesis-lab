"""Command-line interface: ``genesis run ...``.

Deliberately thin: it parses arguments, calls ``execute_run``, and reports. All behaviour
lives in the library, so batch experiments and the API can do anything the CLI can.

Exit codes: 0 success, 1 the run failed while simulating, 2 bad input (arguments, config,
output directory).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pydantic

from genesis.analytics.runs import execute_run, new_run_id
from genesis.core.config import ConfigError, load_config, with_overrides
from genesis.report import write_report

PROGRESS_EVERY = 1000  # ticks between progress lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="genesis", description="Genesis Lab simulations.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run one simulation and write its results")
    run.add_argument("--config", type=Path, default=Path("configs/default.yaml"),
                     help="YAML config file (default: %(default)s)")  # fmt: skip
    run.add_argument("--seed", type=int, help="override run.seed from the config")
    run.add_argument("--ticks", type=int, help="override run.max_ticks from the config")
    run.add_argument("--out", type=Path,
                     help="output directory (default: data/runs/<run id>)")  # fmt: skip
    run.add_argument("--experiment-id", help="label this run as part of an experiment")
    run.add_argument("--overwrite", action="store_true",
                     help="allow writing into a non-empty output directory")  # fmt: skip
    run.add_argument("--quiet", action="store_true", help="no progress output")

    report = commands.add_parser("report", help="write an HTML report of a recorded run")
    report.add_argument("run_dir", type=Path, help="a run folder written by `genesis run`")
    report.add_argument("--out", type=Path, help="output file (default: <run_dir>/report.html)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return _run(args) if args.command == "run" else _report(args)


def _report(args: argparse.Namespace) -> int:
    try:
        path = write_report(args.run_dir, args.out)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"report written to {path}")
    return 0


def _run(args: argparse.Namespace) -> int:
    try:
        config = with_overrides(load_config(args.config), seed=args.seed, max_ticks=args.ticks)
    except (FileNotFoundError, ConfigError, pydantic.ValidationError) as exc:
        print(f"error: invalid configuration\n{exc}", file=sys.stderr)
        return 2

    run_id = new_run_id(config.run.seed)
    out_dir = args.out or Path("data") / "runs" / run_id

    def progress(summary) -> None:
        if not args.quiet and (summary.tick + 1) % PROGRESS_EVERY == 0:
            print(f"  tick {summary.tick + 1:>6}: population {summary.population}", file=sys.stderr)

    try:
        result = execute_run(
            config, out_dir, run_id=run_id, experiment_id=args.experiment_id,
            overwrite=args.overwrite, on_tick=progress,
        )  # fmt: skip
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: run failed: {exc}\nsee {out_dir / 'run.json'}", file=sys.stderr)
        return 1

    print(
        f"run {result.run_id} completed: {result.ticks_run} ticks, stopped by "
        f"{result.stop_reason}, final population {result.final_population}\n"
        f"results in {result.out_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
