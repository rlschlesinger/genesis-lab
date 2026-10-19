"""Tests for the ETL: faithful conversion, old formats, and refusal of damaged runs."""

import csv
import hashlib
import json
import math
import shutil
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from genesis.analytics.runs import execute_run
from genesis.core.config import SimulationConfig, config_hash, hash_config_dict, load_config
from genesis.lake.ingest import find_run_dirs, ingest_paths, ingest_run
from genesis.lake.tables import ALL_TABLES, ORGANISMS, TICKS

CONFIGS = Path(__file__).parents[2] / "configs"


def make_config(**changes) -> SimulationConfig:
    raw = load_config(CONFIGS / "evolution.yaml").model_dump()
    raw["run"]["max_ticks"] = 400
    for path, value in changes.items():
        *parents, leaf = path.split(".")
        section = raw
        for key in parents:
            section = section[key]
        section[leaf] = value
    return SimulationConfig.model_validate(raw)


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory) -> Path:
    """A version-3 run with sampling and every event kind, inside an experiment folder."""
    out = tmp_path_factory.mktemp("exp") / "S_plenty-s5"
    config = make_config(
        **{
            "run.seed": 5,
            "recording.ticks_every": 3,
            "recording.events": ["birth", "death", "meal"],
        }
    )
    execute_run(config, out, experiment_id="E900", condition="S_plenty")
    return out


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def lake_rows(lake: Path, table: str, run_id: str) -> list[dict]:
    return pq.read_table(lake / table / f"{run_id}.parquet").to_pylist()


def fingerprint(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


def damaged_copy(run_dir: Path, tmp_path: Path, csv_name: str, change) -> Path:
    """Copy a run folder and apply ``change(rows) -> rows`` to one of its CSV files."""
    copy = tmp_path / "damaged" / run_dir.name
    shutil.copytree(run_dir, copy)
    rows = read_csv(copy / csv_name)
    header = list(rows[0]) if rows else next(csv.reader((copy / csv_name).open()))
    rows = change(rows)
    header = list(rows[0]) if rows else header
    with (copy / csv_name).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return copy


# --- Faithful conversion ------------------------------------------------------------------


def test_every_table_reproduces_its_csv_value_for_value(run_dir, tmp_path):
    result = ingest_run(run_dir, tmp_path)
    assert result.ingested, result.reason
    for spec in ALL_TABLES[1:]:
        source = read_csv(run_dir / spec.csv_file)
        loaded = lake_rows(tmp_path, spec.name, result.run_id)
        assert len(loaded) == len(source) == result.rows[spec.name], spec.name
        renames = dict(spec.renames)
        for src, row in zip(source, loaded, strict=True):
            assert row["run_id"] == result.run_id
            for column, text in src.items():
                value = row[renames.get(column, column)]
                if text in ("", "nan"):
                    assert value is None, (spec.name, column)  # empty and NaN become NULL
                elif isinstance(value, bool):
                    assert value == (text == "True")
                elif isinstance(value, float):
                    assert value == float(text), (spec.name, column)  # exact, not approximate
                else:
                    assert str(value) == text, (spec.name, column)


def test_parquet_files_have_exactly_the_dictionary_schema(run_dir, tmp_path):
    result = ingest_run(run_dir, tmp_path)
    for spec in ALL_TABLES:
        schema = pq.read_schema(tmp_path / spec.name / f"{result.run_id}.parquet")
        assert schema.remove_metadata() == spec.schema, spec.name


def test_runs_row_carries_metadata(run_dir, tmp_path):
    result = ingest_run(run_dir, tmp_path)
    (row,) = lake_rows(tmp_path, "runs", result.run_id)
    meta = json.loads((run_dir / "run.json").read_text())
    assert row["experiment_id"] == "E900" and row["condition"] == "S_plenty"
    assert row["condition_derived"] is False and row["schema_version"] == 4
    assert (
        row["config_hash"]
        == meta["config_hash"]
        == config_hash(
            make_config(
                **{
                    "run.seed": 5,
                    "recording.ticks_every": 3,
                    "recording.events": ["birth", "death", "meal"],
                }
            )
        )
    )
    assert json.loads(row["config"]) == meta["config"]
    assert row["ticks_every"] == 3 and row["events_recorded"] == "birth,death,meal"


def test_run_folders_are_never_modified(run_dir, tmp_path):
    before = fingerprint(run_dir)
    ingest_run(run_dir, tmp_path)
    assert fingerprint(run_dir) == before


def test_reingesting_replaces_rather_than_duplicates(run_dir, tmp_path):
    first = ingest_run(run_dir, tmp_path)
    second = ingest_run(run_dir, tmp_path)
    assert first.rows == second.rows
    assert len(list((tmp_path / "ticks").glob("*.parquet"))) == 1
    assert not list(tmp_path.rglob("*.tmp"))


def test_empty_population_statistics_become_null(tmp_path):
    out = tmp_path / "run"
    execute_run(make_config(**{"food.initial_count": 0, "food.regrowth_per_tick": 0.0}), out)
    result = ingest_run(out, tmp_path / "lake")
    last = lake_rows(tmp_path / "lake", "ticks", result.run_id)[-1]
    assert last["population"] == 0 and last["mean_energy"] is None  # not NaN


# --- Older run-folder formats -------------------------------------------------------------


def downgrade(run_dir: Path, tmp_path: Path, version: int) -> Path:
    """Rewrite a copy of a run folder in an older format (as earlier code wrote it)."""
    copy = tmp_path / f"v{version}" / run_dir.name
    shutil.copytree(run_dir, copy)
    meta = json.loads((copy / "run.json").read_text())
    for key in ("schema_version", "condition", "config_hash", "ticks_every", "events_recorded"):
        meta.pop(key)
    (copy / "run.json").write_text(json.dumps(meta))
    (copy / "events.csv").unlink()
    if version == 1:
        for name in ("gene_stats.csv", "genomes.csv", "mutations.csv"):
            (copy / name).unlink()
    return copy


@pytest.fixture(scope="module")
def plain_run(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("exp") / "S_plenty-s5"
    execute_run(make_config(**{"run.seed": 5}), out, experiment_id="E900")
    return out


def test_version_2_folder_derives_condition_from_its_name(plain_run, tmp_path):
    result = ingest_run(downgrade(plain_run, tmp_path, 2), tmp_path / "lake")
    assert result.ingested, result.reason
    (row,) = lake_rows(tmp_path / "lake", "runs", result.run_id)
    assert (row["schema_version"], row["condition"], row["condition_derived"]) == (
        2,
        "S_plenty",
        True,
    )
    meta = json.loads((plain_run / "run.json").read_text())
    assert row["config_hash"] == hash_config_dict(meta["config"])  # computed when missing
    assert "events" not in result.rows


def test_version_1_folder_loads_without_gene_tables_and_with_null_genes(plain_run, tmp_path):
    copy = downgrade(plain_run, tmp_path, 1)
    gene_cols = [c for c in read_csv(copy / "organisms.csv")[0] if c.startswith("gene_")]
    damaged = damaged_copy(
        copy,
        tmp_path,
        "organisms.csv",
        lambda rows: [{k: v for k, v in r.items() if k not in gene_cols} for r in rows],
    )
    result = ingest_run(damaged, tmp_path / "lake")
    assert result.ingested, result.reason
    assert set(result.rows) == {"runs", "ticks", "organisms"}
    organism = lake_rows(tmp_path / "lake", "organisms", result.run_id)[0]
    assert organism["gene_speed"] is None and organism["trait_speed"] == 1.5


def test_failed_run_gets_a_runs_row_and_no_data(tmp_path):
    folder = tmp_path / "failed"
    folder.mkdir()
    meta = {
        "run_id": "R-failed",
        "experiment_id": None,
        "status": "failed",
        "seed": 1,
        "config": {"run": {"seed": 1}},
        "started_at": "2026-10-19T00:00:00+00:00",
        "error": "EnergyLedgerError: boom",
        "failed_at_tick": 7,
    }
    (folder / "run.json").write_text(json.dumps(meta))
    result = ingest_run(folder, tmp_path / "lake")
    assert result.ingested and result.rows == {"runs": 1}
    (row,) = lake_rows(tmp_path / "lake", "runs", "R-failed")
    assert row["status"] == "failed" and row["failed_at_tick"] == 7


# --- Refusing damaged runs: one test per check --------------------------------------------


def set_field(index: int, column: str, value: str):
    def change(rows):
        rows[index][column] = value
        return rows

    return change


@pytest.mark.parametrize(
    ("csv_name", "change", "check"),
    [
        ("ticks.csv", lambda rows: rows + [rows[-1]], "primary key"),
        ("organisms.csv", set_field(-1, "parent_id", "999999"), "foreign key"),
        ("mutations.csv", set_field(0, "child_id", "999999"), "foreign key"),
        ("ticks.csv", lambda rows: rows[:-1], "row counts"),
        ("organisms.csv", lambda rows: rows[:-1], "row counts"),
        (
            "events.csv",
            lambda rows: (
                [r for r in rows if r["kind"] != "meal"][:-1]
                + [r for r in rows if r["kind"] == "meal"]
            ),
            "row counts",
        ),
        ("ticks.csv", set_field(3, "food_count", "-1"), "ranges"),
        ("organisms.csv", set_field(0, "gene_speed", "99.0"), "ranges"),
        ("organisms.csv", set_field(0, "alive", "True"), "ranges"),
    ],
    ids=[
        "duplicate-tick",
        "unknown-parent",
        "unknown-child",
        "missing-tick",
        "missing-organism",
        "missing-event",
        "negative-count",
        "gene-out-of-range",
        "alive-but-dead",
    ],
)
def test_damaged_runs_are_refused_with_the_check_named(run_dir, tmp_path, csv_name, change, check):
    damaged = damaged_copy(run_dir, tmp_path, csv_name, change)
    result = ingest_run(damaged, tmp_path / "lake")
    assert not result.ingested
    # Some damage breaks two rules (a missing organism also leaves dangling references to
    # it); the earliest check to see it reports it. Either name is a correct refusal.
    accepted = (
        {check, "foreign key"} if csv_name == "organisms.csv" and check == "row counts" else {check}
    )
    assert any(f"[{name}]" in result.reason for name in accepted), result.reason
    assert not (tmp_path / "lake").exists()  # nothing at all written for a refused run


def test_wrong_type_is_refused(run_dir, tmp_path):
    damaged = damaged_copy(run_dir, tmp_path, "ticks.csv", set_field(2, "population", "many"))
    result = ingest_run(damaged, tmp_path / "lake")
    assert not result.ingested
    assert "[types]" in result.reason and "ticks.csv" in result.reason
    assert "'population'" in result.reason and "many" in result.reason


def test_unexpected_column_is_refused(run_dir, tmp_path):
    def add_column(rows):
        return [r | {"surprise": "1"} for r in rows]

    result = ingest_run(damaged_copy(run_dir, tmp_path, "ticks.csv", add_column), tmp_path / "l")
    assert not result.ingested and "[types]" in result.reason and "surprise" in result.reason


# --- Finding runs -------------------------------------------------------------------------


def test_find_run_dirs_searches_below_each_path(run_dir, plain_run):
    found = find_run_dirs([run_dir.parent, plain_run])
    assert run_dir in found and plain_run in found


def test_ingest_paths_reports_each_run(run_dir, tmp_path):
    (result,) = ingest_paths([run_dir], tmp_path)
    assert result.ingested and result.rows["ticks"] == len(read_csv(run_dir / "ticks.csv"))


def test_table_definitions_match_the_writers():
    # The lake's columns must match what the run writers produce (plus run_id, renames).
    from genesis.analytics.metrics import ORGANISM_FIELDS, TICK_FIELDS

    assert [c for c in TICKS.schema.names if c != "run_id"] == TICK_FIELDS
    renamed = ["organism_id" if c == "id" else c for c in ORGANISM_FIELDS]
    assert [c for c in ORGANISMS.schema.names if c != "run_id"] == renamed
    assert not math.isnan(0.0)
