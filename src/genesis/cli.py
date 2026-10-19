"""Command-line interface: ``genesis run ...`` and ``genesis report ...``.

Deliberately thin: it parses arguments, calls ``execute_run`` or ``write_report``, and
reports. All behaviour lives in the library, so batch experiments and the API can do anything
the CLI can.

Exit codes: 0 success, 1 the run failed while simulating (or a run was refused by
`lake ingest`), 2 bad input (arguments, config, output directory, no runs found).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import duckdb
import pydantic

from genesis.analytics.batch import StaleRunsError, plan, run_experiment, task_status
from genesis.analytics.inspector import (
    InspectError,
    format_inspection,
    inspect_run_folder,
    inspect_tick,
)
from genesis.analytics.runs import execute_run, new_run_id
from genesis.analytics.spec import load_spec
from genesis.core.config import ConfigError, load_config, with_overrides
from genesis.lake.db import DEFAULT_DB, connect, rebuild_db
from genesis.lake.export import export_experiment, export_query, verify_export
from genesis.lake.ingest import DEFAULT_LAKE, ingest_paths
from genesis.report import write_report
from genesis.report.dashboard import write_dashboard

PROGRESS_EVERY = 1000  # ticks between progress lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="genesis", description="Genesis Lab simulations.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run one simulation and write its results")
    run.add_argument(
        "--config",
        type=Path,
        default=Path("configs/default.yaml"),
        help="YAML config file (default: %(default)s)",
    )
    run.add_argument("--seed", type=int, help="override run.seed from the config")
    run.add_argument("--ticks", type=int, help="override run.max_ticks from the config")
    run.add_argument("--out", type=Path, help="output directory (default: data/runs/<run id>)")
    run.add_argument("--experiment-id", help="label this run as part of an experiment")
    run.add_argument(
        "--overwrite", action="store_true", help="allow writing into a non-empty output directory"
    )
    run.add_argument("--quiet", action="store_true", help="no progress output")

    report = commands.add_parser("report", help="write an HTML report of a recorded run")
    report.add_argument("run_dir", type=Path, help="a run folder written by `genesis run`")
    report.add_argument("--out", type=Path, help="output file (default: <run_dir>/report.html)")

    lake = commands.add_parser("lake", help="the Parquet data lake (docs/schema.md)")
    lake_commands = lake.add_subparsers(dest="lake_command", required=True)
    ingest = lake_commands.add_parser(
        "ingest", help="validate run folders and convert them to Parquet tables"
    )
    ingest.add_argument(
        "paths", type=Path, nargs="+", help="run folders, or folders to search for runs"
    )
    ingest.add_argument(
        "--lake", type=Path, default=DEFAULT_LAKE, help="lake directory (default: %(default)s)"
    )
    export = lake_commands.add_parser(
        "export", help="export an experiment's tables, or a query's result, as Parquet or CSV"
    )
    what = export.add_mutually_exclusive_group(required=True)
    what.add_argument("--experiment", help="experiment ID, e.g. E003")
    what.add_argument("--query", help="a SQL query; --out must end in .parquet or .csv")
    export.add_argument("--out", type=Path, required=True, help="folder (experiment) or file")
    export.add_argument("--format", choices=["parquet", "csv"], default="parquet")
    export.add_argument("--tables", help="comma-separated tables (default: all with rows)")
    export.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
    verify = lake_commands.add_parser("verify", help="check an export against its manifest")
    verify.add_argument("export_dir", type=Path)
    rebuild = lake_commands.add_parser(
        "rebuild-db", help="write the SQL views into a DuckDB file for other tools"
    )
    rebuild.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
    rebuild.add_argument(
        "--db", type=Path, default=DEFAULT_DB, help="database file (default: %(default)s)"
    )

    experiment = commands.add_parser("experiment", help="run experiment spec files")
    exp_commands = experiment.add_subparsers(dest="experiment_command", required=True)
    exp_run = exp_commands.add_parser("run", help="run every condition x seed not yet completed")
    exp_run.add_argument("spec", type=Path, help="e.g. experiments/specs/E002.yaml")
    exp_run.add_argument("--workers", type=int, help="parallel runs (default: cores - 1)")
    exp_run.add_argument(
        "--rerun-stale",
        action="store_true",
        help="re-run completed runs whose config differs from the spec",
    )
    exp_run.add_argument("--no-ingest", action="store_true", help="don't load into the lake")
    exp_run.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
    exp_status = exp_commands.add_parser("status", help="which runs exist, are stale, or missing")
    exp_status.add_argument("spec", type=Path)

    dashboard = commands.add_parser("dashboard", help="write an HTML dashboard of an experiment")
    dashboard.add_argument("experiment_id", help="e.g. E003 (its runs must be in the lake)")
    dashboard.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
    dashboard.add_argument("--out", type=Path, help="default: data/dashboards/<id>.html")
    dashboard.add_argument(
        "--window",
        type=int,
        nargs=2,
        metavar=("FIRST", "LAST"),
        help="ticks to average for settled values (default: last 1000)",
    )
    dashboard.add_argument(
        "--compare",
        action="append",
        default=[],
        metavar="TREATMENT:CONTROL",
        help="add a paired-difference panel, e.g. selection:neutral",
    )

    inspect = commands.add_parser(
        "inspect", help="replay a run to one tick and show one organism's decision step by step"
    )
    inspect.add_argument("run_dir", type=Path, nargs="?", help="a run folder (or use --config)")
    inspect.add_argument("--config", type=Path, help="replay this config instead of a run folder")
    inspect.add_argument("--seed", type=int, help="with --config: override run.seed")
    inspect.add_argument("--tick", type=int, required=True, help="the tick to inspect")
    inspect.add_argument("--organism", type=int, required=True, help="the organism's ID")
    inspect.add_argument("--weights", action="store_true", help="also print the brain's weights")

    serve = commands.add_parser("serve", help="start the API server (docs/API.md)")
    serve.add_argument(
        "--host", default="127.0.0.1", help="address to listen on (default: %(default)s)"
    )
    serve.add_argument("--port", type=int, default=8765, help="port (default: %(default)s)")
    serve.add_argument(
        "--allow-remote",
        action="store_true",
        help="allow a non-local --host (the API has no login: anyone who can reach it controls it)",
    )

    sql = commands.add_parser("sql", help="run a SQL query against the lake (docs/sql-examples.md)")
    sql.add_argument("query", help="the SQL query, in quotes")
    sql.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
    sql.add_argument("--max-rows", type=int, default=40, help="rows to print (default: 40)")
    sql.add_argument("--csv", action="store_true", help="print every row as CSV instead")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "run": _run,
        "report": _report,
        "lake": _lake,
        "sql": _sql,
        "experiment": _experiment,
        "dashboard": _dashboard,
        "inspect": _inspect,
        "serve": _serve,
    }
    return handlers[args.command](args)


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _serve(args: argparse.Namespace) -> int:
    if args.host not in LOCAL_HOSTS and not args.allow_remote:
        print(
            f"error: {args.host} is reachable from other machines and the API has no login; "
            "use --allow-remote if you really mean it",
            file=sys.stderr,
        )
        return 2
    import uvicorn  # imported here so other commands don't pay for loading the web stack

    from genesis.api.app import create_app

    print(f"Genesis Lab API on http://{args.host}:{args.port}  (docs: /docs; Ctrl+C to stop)")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")
    return 0


def _inspect(args: argparse.Namespace) -> int:
    if (args.run_dir is None) == (args.config is None):
        print("error: give either a run folder or --config (not both)", file=sys.stderr)
        return 2
    try:
        if args.run_dir is not None:
            if not (args.run_dir / "run.json").exists():
                print(f"error: {args.run_dir} has no run.json", file=sys.stderr)
                return 2
            inspection = inspect_run_folder(args.run_dir, args.tick, args.organism)
        else:
            config = with_overrides(load_config(args.config), seed=args.seed)
            inspection = inspect_tick(config, args.tick, args.organism)
    except (InspectError, ConfigError, pydantic.ValidationError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(format_inspection(inspection, weights=args.weights))
    return 0


def _dashboard(args: argparse.Namespace) -> int:
    pairs = []
    for item in args.compare:
        treatment, sep, control = item.partition(":")
        if not sep or not treatment or not control:
            print(f"error: --compare expects TREATMENT:CONTROL, got {item!r}", file=sys.stderr)
            return 2
        pairs.append((treatment, control))
    window = tuple(args.window) if args.window else None
    try:
        path = write_dashboard(args.experiment_id, args.lake, args.out, window, pairs)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"dashboard written to {path}")
    return 0


def _export(args: argparse.Namespace) -> int:
    try:
        if args.query:
            rows = export_query(args.query, args.out, args.lake)
            print(f"wrote {rows:,} rows to {args.out}")
            return 0
        tables = args.tables.split(",") if args.tables else None
        if args.format == "csv":
            print(
                "note: CSV is much larger than Parquet (E003's gene_stats: ~800 MB vs ~70 MB)",
                file=sys.stderr,
            )
        manifest = export_experiment(args.experiment, args.out, args.format, tables, args.lake)
    except (ValueError, duckdb.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for name, info in manifest["files"].items():
        print(f"  {name:<22} {info['rows']:>12,} rows")
    print(f"exported {args.experiment} to {args.out} (README.md and manifest.json included)")
    return 0


def _experiment(args: argparse.Namespace) -> int:
    try:
        spec = load_spec(args.spec)
    except (OSError, ValueError, KeyError) as exc:  # includes pydantic.ValidationError
        print(f"error: invalid experiment spec {args.spec}\n{exc}", file=sys.stderr)
        return 2
    tasks = plan(spec)
    if args.experiment_command == "status":
        counts: dict[str, int] = {}
        for task in tasks:
            status = task_status(task)
            counts[status] = counts.get(status, 0) + 1
        print(f"{spec.experiment_id}: {len(tasks)} runs planned in {spec.output_dir()}")
        for status, n in sorted(counts.items()):
            print(f"  {status:<11} {n}")
        return 0

    def progress(outcome, done: int, total: int) -> None:
        t = outcome.task
        mark = "ok  " if outcome.ok else "FAIL"
        print(
            f"  [{done:>3}/{total}] {mark} {t.condition}-s{t.seed}: {outcome.message}", flush=True
        )

    print(
        f"{spec.experiment_id}: {len(tasks)} runs planned; running what isn't completed ...",
        flush=True,
    )
    try:
        outcomes = run_experiment(
            spec,
            workers=args.workers,
            rerun_stale=args.rerun_stale,
            ingest=not args.no_ingest,
            lake=args.lake,
            on_outcome=progress,
        )
    except StaleRunsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    failed = [o for o in outcomes if not o.ok]
    print(
        f"ran {len(outcomes)}, skipped {len(tasks) - len(outcomes)} already completed, "
        f"{len(failed)} failed" + ("" if args.no_ingest else f"; lake: {args.lake}")
    )
    return 1 if failed else 0


def _sql(args: argparse.Namespace) -> int:
    try:
        relation = connect(args.lake).sql(args.query)
    except duckdb.Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if relation is None:  # a statement with no result (e.g. CREATE)
        return 0
    if args.csv:
        writer = csv.writer(sys.stdout, lineterminator="\n")
        writer.writerow(relation.columns)
        writer.writerows(relation.fetchall())
        return 0
    rows = relation.fetchmany(args.max_rows + 1)
    print(format_table(relation.columns, rows[: args.max_rows]))
    if len(rows) > args.max_rows:
        print(f"(first {args.max_rows} rows shown; use --max-rows or --csv for more)")
    return 0


def format_table(columns: list[str], rows: list[tuple]) -> str:
    """Rows as aligned text columns, numbers right-aligned, NULL shown as 'NULL'."""

    def text(value) -> str:
        if value is None:
            return "NULL"
        return f"{value:.6g}" if isinstance(value, float) else str(value)

    def is_number(value) -> bool:
        return isinstance(value, int | float) and not isinstance(value, bool)

    cells = [[text(v) for v in row] for row in rows]
    widths = [max([len(name), *(len(r[i]) for r in cells)]) for i, name in enumerate(columns)]
    numeric = [
        bool(rows) and all(is_number(r[i]) or r[i] is None for r in rows)
        for i in range(len(columns))
    ]

    def line(values: list[str]) -> str:
        parts = [
            v.rjust(w) if n else v.ljust(w) for v, w, n in zip(values, widths, numeric, strict=True)
        ]
        return "  ".join(parts).rstrip()

    return "\n".join([line(columns), line(["-" * w for w in widths]), *map(line, cells)])


def _lake(args: argparse.Namespace) -> int:
    if args.lake_command == "export":
        return _export(args)
    if args.lake_command == "verify":
        problems = verify_export(args.export_dir)
        for problem in problems:
            print(f"problem: {problem}", file=sys.stderr)
        print("export intact" if not problems else f"{len(problems)} problem(s) found")
        return 1 if problems else 0
    if args.lake_command == "rebuild-db":
        path = rebuild_db(args.db, args.lake)
        print(f"wrote views to {path} (absolute paths: rebuild if the project folder moves)")
        return 0
    results = ingest_paths(args.paths, args.lake)
    if not results:
        print("error: no run folders (folders containing run.json) found", file=sys.stderr)
        return 2
    totals: dict[str, int] = {}
    for result in results:
        for table, rows in result.rows.items():
            totals[table] = totals.get(table, 0) + rows
    refused = [r for r in results if not r.ingested]
    for r in refused:
        print(f"refused {r.run_dir}: {r.reason}", file=sys.stderr)
    print(f"ingested {len(results) - len(refused)} of {len(results)} runs into {args.lake}")
    for table, rows in totals.items():
        print(f"  {table:<11} {rows:>10,} rows")
    return 1 if refused else 0


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
            config,
            out_dir,
            run_id=run_id,
            experiment_id=args.experiment_id,
            overwrite=args.overwrite,
            on_tick=progress,
        )
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
