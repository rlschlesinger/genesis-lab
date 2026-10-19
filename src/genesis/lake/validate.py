"""Checks a run must pass before it is loaded into the lake (docs/data-dictionary.md).

Parquet files and DuckDB views can't enforce keys or ranges, so the ETL does: every check
here raises ``ValidationError`` naming the check, and a run that fails any check is refused
whole. Nothing of it is written.
"""

from __future__ import annotations

import pyarrow as pa
import pyarrow.compute as pc

from genesis.lake.tables import ALL_TABLES, BRAIN_COLUMNS, GENE_COLUMNS

STATUSES = {"completed", "failed", "running"}
COUNT_COLUMNS = {
    "ticks": [
        "population",
        "births",
        "deaths",
        "food_count",
        "food_spawned",
        "food_eaten",
        "lineages",
        "mutations",
    ],
    "organisms": ["generation", "birth_tick", "age", "food_eaten", "offspring_count"],
    "behaviour": ["n", "seeing_food"],
}
# behaviour columns that are shares or fractions, so must lie in [0, 1] (NULL allowed).
FRACTION_COLUMNS = ["toward_food", "mean_turn", "mean_throttle"]
FLOW_FOR_EVENT = {"birth": "births", "death": "deaths", "meal": "food_eaten"}


class ValidationError(ValueError):
    def __init__(self, check: str, message: str):
        super().__init__(f"[{check}] {message}")
        self.check = check


def validate_run(meta: dict, tables: dict[str, pa.Table]) -> None:
    """Run every check. ``tables`` maps table name -> Arrow table (runs included)."""
    run = tables["runs"].to_pylist()[0]
    if run["status"] not in STATUSES:
        raise ValidationError("values", f"unknown status {run['status']!r}")
    check_primary_keys(tables)
    if run["status"] != "completed":
        return  # failed or unfinished runs have no data tables to check
    check_foreign_keys(tables)
    check_row_counts(run, tables)
    check_ranges(meta, tables)


def check_primary_keys(tables: dict[str, pa.Table]) -> None:
    """1. No two rows of a table share a primary key."""
    for spec in ALL_TABLES:
        table = tables.get(spec.name)
        if table is None or table.num_rows == 0:
            continue
        for column in spec.primary_key:
            if table[column].null_count:
                raise ValidationError("primary key", f"{spec.name}.{column} has empty values")
        distinct = table.group_by(list(spec.primary_key)).aggregate([]).num_rows
        if distinct != table.num_rows:
            duplicates = table.num_rows - distinct
            raise ValidationError(
                "primary key", f"{spec.name}: {duplicates} rows repeat a {spec.primary_key} key"
            )


def check_foreign_keys(tables: dict[str, pa.Table]) -> None:
    """2. Every reference to an organism points at an organism of the same run."""
    ids = tables["organisms"]["organism_id"]
    references = [
        ("organisms", "parent_id"),
        ("organisms", "founder_id"),
        ("genomes", "organism_id"),
        ("mutations", "parent_id"),
        ("mutations", "child_id"),
        ("events", "organism_id"),
        ("events", "other_id"),
        ("brains", "organism_id"),
    ]
    for table_name, column in references:
        table = tables.get(table_name)
        if table is None or table.num_rows == 0:
            continue
        values = pc.drop_null(table[column])
        missing = pc.invert(pc.is_in(values, value_set=ids))
        if pc.any(missing).as_py():
            example = pc.filter(values, missing)[0].as_py()
            raise ValidationError(
                "foreign key", f"{table_name}.{column} = {example} is not an organism of this run"
            )


def check_row_counts(run: dict, tables: dict[str, pa.Table]) -> None:
    """3. Row counts agree with run.json, and logged events agree with the flow totals."""
    every, ticks_run = run["ticks_every"], run["ticks_run"]
    expected = sorted({t for t in range(ticks_run) if t % every == 0} | {ticks_run - 1})
    ticks = tables["ticks"]
    if ticks["tick"].to_pylist() != expected:
        raise ValidationError(
            "row counts",
            f"ticks has {ticks.num_rows} rows; expected {len(expected)} "
            f"(ticks_run {ticks_run}, ticks_every {every}, in order)",
        )
    _expect_rows(tables["organisms"], run["organisms_ever"], "organisms", "organisms_ever")
    if tables.get("mutations") is not None:
        _expect_rows(tables["mutations"], run["mutations"], "mutations", "mutations")
    behaviour = tables.get("behaviour")
    if behaviour is not None and behaviour["tick"].to_pylist() != expected:
        raise ValidationError(
            "row counts", f"behaviour has {behaviour.num_rows} rows; expected one per ticks row"
        )
    events = tables.get("events")
    if events is not None and run["events_recorded"]:
        for kind in run["events_recorded"].split(","):
            logged = pc.sum(pc.equal(events["kind"], kind)).as_py() or 0
            total = pc.sum(ticks[FLOW_FOR_EVENT[kind]]).as_py() or 0
            if logged != total:
                raise ValidationError(
                    "row counts", f"{logged} {kind} events but ticks.csv totals {total}"
                )


def _expect_rows(table: pa.Table, expected: int | None, name: str, field: str) -> None:
    if expected is not None and table.num_rows != expected:
        raise ValidationError(
            "row counts", f"{name} has {table.num_rows} rows; run.json {field} = {expected}"
        )


def check_ranges(meta: dict, tables: dict[str, pa.Table]) -> None:
    """4. Counts are never negative; genes stay in bounds; alive <=> no death tick."""
    for table_name, columns in COUNT_COLUMNS.items():
        if table_name not in tables:
            continue  # behaviour exists from run-folder version 4 on
        for column in columns:
            values = tables[table_name][column]
            if values.null_count < len(values) and pc.min(values).as_py() < 0:
                raise ValidationError("ranges", f"{table_name}.{column} has a negative value")

    organisms = tables["organisms"]
    alive, no_death = organisms["alive"], pc.is_null(organisms["death_tick"])
    if not pc.all(pc.equal(alive, no_death)).as_py():
        raise ValidationError("ranges", "organisms: alive disagrees with death_tick")

    behaviour = tables.get("behaviour")
    if behaviour is not None and behaviour.num_rows:
        for column in FRACTION_COLUMNS:
            values = pc.drop_null(behaviour[column])
            if len(values) and (pc.min(values).as_py() < 0 or pc.max(values).as_py() > 1):
                raise ValidationError("ranges", f"behaviour.{column} leaves [0, 1]")
    check_brains(meta, tables)

    genome = meta["config"].get("genome")  # absent in version-1 runs (no genes)
    if not genome:
        return
    for name, bounds in genome.items():
        low, high = bounds["min"], bounds["max"]
        for table_name in ("organisms", "genomes"):
            table = tables.get(table_name)
            if table is None or table.num_rows == 0 or f"gene_{name}" not in GENE_COLUMNS:
                continue
            values = table[f"gene_{name}"]
            if values.null_count == len(values):
                continue  # no gene values recorded (a version-1 run)
            if pc.min(values).as_py() < low or pc.max(values).as_py() > high:
                raise ValidationError(
                    "ranges", f"{table_name}.gene_{name} leaves its range [{low}, {high}]"
                )


def check_brains(meta: dict, tables: dict[str, pa.Table]) -> None:
    """Brains: one row per organism when the run had brains, none otherwise; every weight
    within the configured limit (part of checks 3 and 4)."""
    brains = tables.get("brains")
    if brains is None:
        return  # run-folder version < 4
    brain_config = meta["config"].get("brain")
    if brain_config is None:
        if brains.num_rows:
            raise ValidationError("row counts", "brains has rows but the run had no brains")
        return
    _expect_rows(brains, meta.get("organisms_ever"), "brains", "organisms_ever")
    limit = brain_config["weight_limit"]
    for column in BRAIN_COLUMNS:
        values = brains[column]
        if values.null_count:
            raise ValidationError("ranges", f"brains.{column} has empty values")
        if brains.num_rows and pc.max(pc.abs(values)).as_py() > limit:
            raise ValidationError("ranges", f"brains.{column} leaves [-{limit}, {limit}]")
