"""Worlds with predators in the lake (Milestone 6, increment 6.4, D-060).

Their four extra files load value for value into their own tables; damaged ones are refused;
prey brains' 18 predator weights sit beside older runs' 62 in one view; and the
species_counts view puts both populations side by side.
"""

import csv
import shutil
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from genesis.analytics.experiments import apply_changes
from genesis.analytics.runs import execute_run
from genesis.core.config import SimulationConfig, load_config
from genesis.lake.db import connect
from genesis.lake.ingest import ingest_run
from genesis.lake.tables import ALL_TABLES, THREAT_BRAIN_COLUMNS

CONFIGS = Path(__file__).parents[2] / "configs"


def predator_world(**changes) -> SimulationConfig:
    """predators.yaml with neural predators (so predator brains are recorded too)."""
    raw = apply_changes(load_config(CONFIGS / "predators.yaml"), changes).model_dump()
    raw["predators"]["controller"] = "neural"
    raw["predators"]["brain"] = {}
    return SimulationConfig.model_validate(raw)


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory) -> Path:
    """Seed 3 has captures from early on; sampled every 3 ticks, every event kind logged."""
    out = tmp_path_factory.mktemp("pred") / "hunted-s3"
    config = predator_world(
        **{
            "run.seed": 3,
            "run.max_ticks": 300,
            "recording.ticks_every": 3,
            "recording.events": ["birth", "death", "meal"],
        }
    )
    execute_run(config, out, run_id="hunted")
    return out


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def rewrite(run_dir: Path, tmp_path: Path, name: str, change) -> Path:
    copy = tmp_path / "damaged" / run_dir.name
    shutil.copytree(run_dir, copy)
    rows = read_csv(copy / name)
    header = list(rows[0])
    rows = change(rows)
    with (copy / name).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return copy


def test_every_predator_table_reproduces_its_csv(run_dir, tmp_path):
    result = ingest_run(run_dir, tmp_path)
    assert result.ingested, result.reason
    for spec in [t for t in ALL_TABLES if t.predators_only]:
        source = read_csv(run_dir / spec.csv_file)
        loaded = pq.read_table(tmp_path / spec.name / "hunted.parquet").to_pylist()
        assert len(loaded) == len(source) > 0, spec.name
        renames = dict(spec.renames)
        for src, row in zip(source, loaded, strict=True):
            for column, text in src.items():
                value = row[renames.get(column, column)]
                if text in ("", "nan"):
                    assert value is None, (spec.name, column)
                elif isinstance(value, bool):
                    assert value == (text == "True")
                elif isinstance(value, float):
                    assert value == float(text), (spec.name, column)
                else:
                    assert str(value) == text, (spec.name, column)
    for spec in [t for t in ALL_TABLES if not t.resources_only]:  # one food: no diet files
        schema = pq.read_schema(tmp_path / spec.name / "hunted.parquet").remove_metadata()
        assert schema == spec.schema, spec.name


def test_strikes_agree_with_the_prey_records(run_dir, tmp_path):
    ingest_run(run_dir, tmp_path)
    con = connect(tmp_path)
    caught, predation = con.sql(
        "SELECT (SELECT count(*) FROM strikes WHERE caught),"
        " (SELECT count(*) FROM organisms WHERE death_cause = 'predation')"
    ).fetchone()
    assert caught == predation > 0


@pytest.mark.parametrize(
    ("name", "change", "message"),
    [
        ("strikes.csv", lambda rows: [{**rows[0], "prey_id": "99999"}, *rows[1:]], "a prey"),
        ("strikes.csv", lambda rows: [{**rows[0], "predator_id": "5"}, *rows[1:]],
         "a predator"),
        ("strikes.csv", lambda rows: rows[1:], "strikes has"),
        # A missing predator is caught as soon as something refers to it.
        ("predators.csv", lambda rows: rows[1:], "is not a predator of this run"),
        ("predator_brains.csv", lambda rows: rows[1:], "predator_brains has"),
        ("brains.csv", lambda rows: [{**rows[0], THREAT_BRAIN_COLUMNS[0]: ""}, *rows[1:]],
         "empty values"),
    ],
)  # fmt: skip
def test_damaged_predator_runs_are_refused(run_dir, tmp_path, name, change, message):
    damaged = rewrite(run_dir, tmp_path, name, change)
    result = ingest_run(damaged, tmp_path / "lake")
    assert not result.ingested and message in result.reason, result.reason


def test_old_and_new_brains_share_one_view(run_dir, tmp_path):
    # A run without predators writes 62 weights; a predator world's prey 80. Both read
    # through one brains view, the older rows with the 18 predator weights empty.
    plain = tmp_path / "plain"
    neural = apply_changes(load_config(CONFIGS / "neural.yaml"), {"run.max_ticks": 30})
    execute_run(neural, plain, run_id="plain")
    for folder in (plain, run_dir):
        assert ingest_run(folder, tmp_path / "lake").ingested
    con = connect(tmp_path / "lake")
    rows = dict(
        con.sql(
            f"SELECT run_id, count({THREAT_BRAIN_COLUMNS[0]}) FROM brains GROUP BY run_id"
        ).fetchall()
    )
    assert rows["plain"] == 0 and rows["hunted"] > 0
    counts = con.sql(
        "SELECT count(*), min(prey), max(predators) FROM species_counts WHERE run_id = 'hunted'"
    ).fetchone()
    # 300 ticks, every 3rd (0..297) plus the final tick (299), which is always kept.
    assert counts[0] == 101 and counts[1] >= 0 and counts[2] > 0
    params = con.sql(
        "SELECT run_id, has_predators, predator_controller FROM run_params ORDER BY run_id"
    ).fetchall()
    assert params == [("hunted", True, "neural"), ("plain", False, None)]


def test_a_lake_of_older_runs_still_offers_every_new_column(tmp_path):
    # Before any predator world is ingested, no Parquet file has the new columns; the views
    # still offer them (as NULL), so a query written for predator worlds runs on any lake.
    plain = tmp_path / "plain"
    neural = apply_changes(load_config(CONFIGS / "neural.yaml"), {"run.max_ticks": 20})
    execute_run(neural, plain, run_id="plain")
    assert ingest_run(plain, tmp_path / "lake").ingested
    con = connect(tmp_path / "lake")
    assert con.sql(f"SELECT count({THREAT_BRAIN_COLUMNS[-1]}) FROM brains").fetchone() == (0,)
    assert con.sql("SELECT final_predators, predators_ever FROM runs").fetchone() == (None, None)
    assert con.sql("SELECT count(*) FROM strikes").fetchone() == (0,)
    names = [row[0] for row in con.sql("DESCRIBE brains").fetchall()]
    assert names[-1] == THREAT_BRAIN_COLUMNS[-1] and len(names) == 2 + 80


def test_a_world_ready_for_predators_with_none_in_it_ingests(tmp_path):
    # E008's "safe" condition: a predators section with initial_count 0. Its predator tables
    # are empty, which every check must accept (an empty-table check once refused it).
    config = apply_changes(
        load_config(CONFIGS / "predators.yaml"),
        {"predators.initial_count": 0, "run.max_ticks": 30},
    )
    execute_run(config, tmp_path / "safe", run_id="safe")
    result = ingest_run(tmp_path / "safe", tmp_path / "lake")
    assert result.ingested, result.reason
    assert result.rows["predators"] == result.rows["strikes"] == 0
