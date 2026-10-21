"""Two-food worlds recorded and in the lake (Milestone 6, increment 6.9, D-064).

diets.csv and diet_ticks.csv load value for value; damaged ones are refused; their numbers
agree with the organisms and ticks tables; one-food worlds write neither.
"""

import csv
import shutil
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from genesis.analytics.experiments import apply_changes
from genesis.analytics.runs import execute_run
from genesis.core.config import load_config
from genesis.lake.db import connect
from genesis.lake.ingest import ingest_run
from genesis.lake.tables import ALL_TABLES

CONFIGS = Path(__file__).parents[2] / "configs"


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("diets") / "fed-s2"
    config = apply_changes(
        load_config(CONFIGS / "diets.yaml"),
        {"run.seed": 2, "run.max_ticks": 400, "recording.ticks_every": 4},
    )
    execute_run(config, out, run_id="fed")
    return out


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def test_diet_tables_reproduce_their_csvs(run_dir, tmp_path):
    result = ingest_run(run_dir, tmp_path)
    assert result.ingested, result.reason
    for spec in [t for t in ALL_TABLES if t.resources_only]:
        source = read_csv(run_dir / spec.csv_file)
        loaded = pq.read_table(tmp_path / spec.name / "fed.parquet").to_pylist()
        assert len(loaded) == len(source) > 0, spec.name
        renames = dict(spec.renames)
        for src, row in zip(source, loaded, strict=True):
            for column, text in src.items():
                value = row[renames.get(column, column)]
                if text in ("", "nan"):
                    assert value is None
                elif isinstance(value, float):
                    assert value == float(text), (spec.name, column)
                else:
                    assert str(value) == text, (spec.name, column)


def test_meals_by_kind_agree_everywhere(run_dir, tmp_path):
    ingest_run(run_dir, tmp_path)
    con = connect(tmp_path)
    by_organism, by_tick, total = con.sql(
        "SELECT (SELECT sum(meals_a + meals_b) FROM diets),"
        " (SELECT sum(meals_a + meals_b) FROM diet_ticks),"
        " (SELECT sum(food_eaten) FROM ticks)"
    ).fetchone()
    assert by_organism == by_tick == total > 0
    assert con.sql("SELECT has_two_foods, diet_exponent FROM run_params").fetchone() == (True, 2.0)


@pytest.mark.parametrize(
    ("name", "change", "message"),
    [
        ("diets.csv", lambda rows: rows[1:], "diets has"),
        ("diets.csv", lambda rows: [{**rows[0], "diet": "1.5"}, *rows[1:]], "leaves"),
        ("diets.csv", lambda rows: [{**rows[0], "meals_b": "999"}, *rows[1:]], "add up"),
        ("diet_ticks.csv", lambda rows: rows[1:], "one row per ticks row"),
        ("diet_ticks.csv", lambda rows: [{**rows[0], "bin_5": "0"}, *rows[1:]], "histogram"),
    ],
)
def test_damaged_diet_files_are_refused(run_dir, tmp_path, name, change, message):
    copy = tmp_path / "damaged"
    shutil.copytree(run_dir, copy)
    rows = read_csv(copy / name)
    header = list(rows[0])
    with (copy / name).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(change(rows))
    result = ingest_run(copy, tmp_path / "lake")
    assert not result.ingested and message in result.reason, result.reason


def test_one_food_worlds_write_no_diet_files(tmp_path):
    config = apply_changes(load_config(CONFIGS / "evolution.yaml"), {"run.max_ticks": 20})
    execute_run(config, tmp_path / "plain", run_id="plain")
    assert not (tmp_path / "plain" / "diets.csv").exists()
    assert not (tmp_path / "plain" / "diet_ticks.csv").exists()
