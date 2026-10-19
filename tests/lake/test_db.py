"""Tests for the DuckDB views: SQL answers must match independent computations from the CSVs."""

import csv
import json
import re
import statistics
from pathlib import Path

import duckdb
import pytest

from genesis.analytics.runs import execute_run
from genesis.cli import format_table, main
from genesis.core.config import SimulationConfig, load_config
from genesis.lake.db import connect, rebuild_db
from genesis.lake.ingest import ingest_paths, ingest_run
from genesis.lake.tables import ALL_TABLES

ROOT = Path(__file__).parents[2]


def config(seed: int, **changes) -> SimulationConfig:
    raw = load_config(ROOT / "configs" / "evolution.yaml").model_dump()
    raw["run"].update(max_ticks=300, seed=seed)
    for path, value in changes.items():
        *parents, leaf = path.split(".")
        section = raw
        for key in parents:
            section = section[key]
        section[leaf] = value
    return SimulationConfig.model_validate(raw)


@pytest.fixture(scope="module")
def lake(tmp_path_factory) -> Path:
    """Two conditions x two seeds in experiment E900, one failed run, one run with events."""
    root = tmp_path_factory.mktemp("runs")
    for label, changes in (("plenty", {}), ("scarce", {"food.regrowth_per_tick": 1.0})):
        for seed in (1, 2):
            execute_run(
                config(seed, **changes),
                root / f"{label}-s{seed}",
                experiment_id="E900",
                condition=label,
            )
    execute_run(config(3, **{"recording.events": ["birth", "death", "meal"]}), root / "events")
    failed = root / "failed"
    failed.mkdir()
    (failed / "run.json").write_text(
        json.dumps(
            {
                "run_id": "R-failed",
                "experiment_id": "E900",
                "condition": "plenty",
                "status": "failed",
                "seed": 9,
                "config": {},
                "started_at": "2026-10-19T00:00:00+00:00",
                "error": "boom",
            }
        )
    )
    lake = tmp_path_factory.mktemp("lake")
    results = ingest_paths([root], lake)
    (lake / "runs_root.txt").write_text(str(root))
    assert all(r.ingested for r in results), [r.reason for r in results]
    return lake


@pytest.fixture(scope="module")
def con(lake):
    return connect(lake)


def run_dirs(lake: Path) -> dict[str, Path]:
    """run_id -> run folder, for the completed runs of *this* fixture only.

    The run folders were recorded beside the lake (runs_root.txt). Searching a shared parent
    folder would also find other tests' runs, which aren't in this lake.
    """
    found = {}
    for path in Path((lake / "runs_root.txt").read_text()).rglob("run.json"):
        meta = json.loads(path.read_text())
        if meta["status"] == "completed":
            found[meta["run_id"]] = path.parent
    return found


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


# --- Views mirror the lake ----------------------------------------------------------------


def test_every_table_view_has_the_dictionary_columns(con):
    for spec in ALL_TABLES:
        columns = [d[0] for d in con.sql(f"SELECT * FROM {spec.name} LIMIT 0").description]
        assert columns == spec.schema.names, spec.name


def test_completed_runs_excludes_the_failed_run(con):
    statuses = dict(con.sql("SELECT status, count(*) FROM runs GROUP BY status").fetchall())
    assert statuses == {"completed": 5, "failed": 1}
    assert con.sql("SELECT count(*) FROM completed_runs").fetchone()[0] == 5
    assert (
        con.sql("SELECT count(*) FROM completed_runs WHERE run_id = 'R-failed'").fetchone()[0] == 0
    )


def test_run_params_exposes_config_values(con):
    rows = con.sql(
        "SELECT condition, food_regrowth, mutation_enabled, mutation_rate "
        "FROM run_params WHERE experiment_id = 'E900' AND status = 'completed' "
        "ORDER BY condition"
    ).fetchall()
    assert {(r[0], r[1]) for r in rows} == {("plenty", 2.0), ("scarce", 1.0)}
    assert all(r[2] is True and r[3] == 0.1 for r in rows)


def test_config_is_queryable_json(con):
    seed = con.sql(
        "SELECT config ->> '$.run.seed' FROM completed_runs WHERE condition = "
        "'plenty' ORDER BY seed LIMIT 1"
    ).fetchone()[0]
    assert seed == "1"


# --- SQL answers match independent Python ------------------------------------------------


def test_join_population_at_birth_matches_python(con, lake):
    for run_id, folder in run_dirs(lake).items():
        population = {int(r["tick"]): int(r["population"]) for r in read_csv(folder / "ticks.csv")}
        expected = sorted(
            (int(o["id"]), population[int(o["birth_tick"])])
            for o in read_csv(folder / "organisms.csv")
            if o["parent_id"]
        )
        got = con.execute(
            "SELECT o.organism_id, t.population FROM organisms o JOIN ticks t "
            "ON t.run_id = o.run_id AND t.tick = o.birth_tick "
            "WHERE o.run_id = ? AND o.parent_id IS NOT NULL ORDER BY 1",
            [run_id],
        ).fetchall()
        assert got == expected


def test_settled_gene_means_macro_matches_python(con, lake):
    for run_id, folder in run_dirs(lake).items():
        rows = [r for r in read_csv(folder / "gene_stats.csv") if 200 <= int(r["tick"]) <= 299]
        for gene in ("speed", "neutral_marker"):
            values = [float(r["mean"]) for r in rows if r["gene"] == gene]
            got = con.execute(
                "SELECT settled_mean, rows_in_window FROM settled_gene_means(200, "
                "299) WHERE run_id = ? AND gene = ?",
                [run_id, gene],
            ).fetchone()
            assert got[0] == pytest.approx(statistics.fmean(values), rel=1e-12)
            assert got[1] == 100


def test_lineage_sizes_match_python(con, lake):
    for run_id, folder in run_dirs(lake).items():
        counts: dict[int, list[int]] = {}
        for o in read_csv(folder / "organisms.csv"):
            entry = counts.setdefault(int(o["founder_id"]), [0, 0])
            entry[0] += 1
            entry[1] += o["alive"] == "True"
        got = con.execute(
            "SELECT founder_id, born, alive_at_end FROM lineage_sizes WHERE run_id = ? ORDER BY 1",
            [run_id],
        ).fetchall()
        assert got == sorted((f, born, alive) for f, (born, alive) in counts.items())


def test_recursive_ancestry_matches_walking_parent_pointers(con, lake):
    run_id, folder = next(iter(run_dirs(lake).items()))
    organisms = {int(o["id"]): o for o in read_csv(folder / "organisms.csv")}
    youngest = max(organisms.values(), key=lambda o: (int(o["generation"]), -int(o["id"])))
    expected, current = [], youngest
    while current is not None:
        expected.append(int(current["id"]))
        current = organisms.get(int(current["parent_id"])) if current["parent_id"] else None
    got = con.execute(
        """
        WITH RECURSIVE ancestry AS (
            SELECT run_id, organism_id, parent_id, 0 AS steps FROM organisms
            WHERE run_id = $run AND organism_id = $start
            UNION ALL
            SELECT o.run_id, o.organism_id, o.parent_id, a.steps + 1
            FROM organisms o JOIN ancestry a ON o.run_id = a.run_id AND o.organism_id = a.parent_id
        ) SELECT organism_id FROM ancestry ORDER BY steps""",
        {"run": run_id, "start": int(youngest["id"])},
    ).fetchall()
    assert [r[0] for r in got] == expected


def test_forgetting_run_id_in_a_join_fans_out(con):
    correct, fan_out = con.sql("""
        SELECT (SELECT count(*) FROM organisms o JOIN ticks t
                  ON t.run_id = o.run_id AND t.tick = o.birth_tick),
               (SELECT count(*) FROM organisms o JOIN ticks t ON t.tick = o.birth_tick)
    """).fetchone()
    assert fan_out > correct  # valid SQL, silently wrong


def test_events_view_matches_tick_totals(con):
    events = con.sql("SELECT count(*) FROM events WHERE kind = 'death'").fetchone()[0]
    deaths = con.sql(
        "SELECT sum(t.deaths) FROM ticks t JOIN runs r USING (run_id) WHERE r.events_recorded <> ''"
    ).fetchone()[0]
    assert events == deaths > 0


# --- Docs, empty tables, database file ----------------------------------------------------


def test_every_documented_example_runs(con):
    text = (ROOT / "docs" / "sql-examples.md").read_text()
    blocks = re.findall(r"```sql\n(.*?)```", text, re.S)
    assert len(blocks) >= 9
    for block in blocks:
        con.sql(block).fetchall()  # raises on any error


def test_views_work_on_a_lake_with_missing_tables(tmp_path):
    run = tmp_path / "run"
    execute_run(config(4), run)  # no events logged
    assert ingest_run(run, tmp_path / "lake").ingested
    for table in ("events",):
        (tmp_path / "lake" / table).mkdir(exist_ok=True)
        for f in (tmp_path / "lake" / table).glob("*.parquet"):
            f.unlink()
    con = connect(tmp_path / "lake")
    assert con.sql("SELECT count(*) FROM events").fetchone()[0] == 0
    assert con.sql("SELECT count(*) FROM completed_runs").fetchone()[0] == 1


def test_experiments_table_lists_the_definition_documents(con):
    rows = dict(con.sql("SELECT experiment_id, defined_at_commit FROM experiments").fetchall())
    assert {"E001", "E002", "E003"} <= set(rows)


def test_rebuild_db_writes_a_reopenable_file(lake, tmp_path):
    path = rebuild_db(tmp_path / "g.duckdb", lake)
    with duckdb.connect(str(path), read_only=True) as db:
        assert db.sql("SELECT count(*) FROM completed_runs").fetchone()[0] == 5


# --- Command line -------------------------------------------------------------------------


def test_sql_command_prints_a_table(lake, capsys):
    assert (
        main(
            [
                "sql",
                "SELECT condition, count(*) AS n FROM completed_runs WHERE condition "
                "IS NOT NULL GROUP BY 1 ORDER BY 1",
                "--lake",
                str(lake),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out.splitlines()
    assert out[0].split() == ["condition", "n"] and out[2].split() == ["plenty", "2"]


def test_sql_command_csv_and_errors(lake, capsys):
    assert main(["sql", "SELECT 1 AS a, NULL AS b", "--lake", str(lake), "--csv"]) == 0
    assert capsys.readouterr().out == "a,b\n1,\n"
    assert main(["sql", "SELECT * FROM nope", "--lake", str(lake)]) == 2
    assert "nope" in capsys.readouterr().err


def test_sql_command_says_when_rows_are_cut(lake, capsys):
    assert main(["sql", "SELECT * FROM range(100)", "--lake", str(lake), "--max-rows", "5"]) == 0
    assert "first 5 rows shown" in capsys.readouterr().out


def test_format_table_aligns_numbers_and_shows_null():
    text = format_table(["name", "value"], [("a", 1.5), ("bb", None), ("c", 10)])
    assert text.splitlines() == [
        "name  value",
        "----  -----",
        "a       1.5",
        "bb     NULL",
        "c        10",
    ]
