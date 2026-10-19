"""Tests for exports: complete, documented, verifiable, and reloadable without Genesis Lab."""

import json
from pathlib import Path

import pandas as pd
import pytest

from genesis.analytics.analysis import settled_gene_means_df
from genesis.analytics.runs import execute_run
from genesis.cli import main
from genesis.core.config import SimulationConfig, load_config
from genesis.lake.db import connect
from genesis.lake.export import export_experiment, export_query, verify_export
from genesis.lake.ingest import ingest_paths

ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def lake(tmp_path_factory) -> Path:
    raw = load_config(ROOT / "configs" / "evolution.yaml").model_dump()
    raw["run"]["max_ticks"] = 200
    runs = tmp_path_factory.mktemp("runs")
    for condition, regrowth in (("plenty", 2.0), ("scarce", 1.0)):
        for seed in (1, 2):
            raw["run"]["seed"], raw["food"]["regrowth_per_tick"] = seed, regrowth
            execute_run(
                SimulationConfig.model_validate(raw),
                runs / f"{condition}-s{seed}",
                experiment_id="E900",
                condition=condition,
            )
    failed = runs / "failed"
    failed.mkdir()
    (failed / "run.json").write_text(
        json.dumps(
            {
                "run_id": "R-failed",
                "experiment_id": "E900",
                "status": "failed",
                "seed": 9,
                "config": {},
                "started_at": "2026-10-19T00:00:00+00:00",
                "error": "boom",
            }
        )
    )
    execute_run(SimulationConfig.model_validate(raw), runs / "other")  # not in E900
    lake = tmp_path_factory.mktemp("lake")
    assert all(r.ingested for r in ingest_paths([runs], lake))
    return lake


@pytest.fixture(scope="module")
def parquet_export(lake, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("export") / "E900"
    export_experiment("E900", out, "parquet", lake=lake)
    return out


def test_export_has_one_file_per_table_with_rows_plus_readme_and_manifest(parquet_export):
    names = {p.name for p in parquet_export.iterdir()}
    assert {
        "runs.parquet",
        "ticks.parquet",
        "gene_stats.parquet",
        "genomes.parquet",
        "organisms.parquet",
        "mutations.parquet",
        "behaviour.parquet",
        "README.md",
        "manifest.json",
    } == names
    # No events were logged and no run had brains, so there is no (empty) events or brains
    # file.


def test_manifest_row_counts_match_the_database(parquet_export, lake):
    manifest = json.loads((parquet_export / "manifest.json").read_text())
    con = connect(lake)
    for name, info in manifest["files"].items():
        expected = con.execute(
            f"SELECT count(*) FROM {info['table']} WHERE run_id IN "
            "(SELECT run_id FROM runs WHERE experiment_id = 'E900')"
        ).fetchone()[0]
        assert info["rows"] == expected, name
    assert manifest["runs"] == 5  # 4 completed + 1 failed; the run outside E900 is excluded


def test_runs_file_keeps_failed_runs_with_their_status(parquet_export):
    runs = pd.read_parquet(parquet_export / "runs.parquet")
    assert dict(runs["status"].value_counts()) == {"completed": 4, "failed": 1}
    assert json.loads(runs.loc[runs["status"] == "completed", "config"].iloc[0])["run"]


def test_parquet_reloads_identically(parquet_export, lake):
    con = connect(lake)
    for table, key in (("ticks", ["run_id", "tick"]), ("organisms", ["run_id", "organism_id"])):
        exported = pd.read_parquet(parquet_export / f"{table}.parquet")
        original = con.sql(
            f"SELECT * FROM {table} WHERE run_id IN (SELECT run_id FROM runs "
            f"WHERE experiment_id = 'E900') ORDER BY {', '.join(key)}"
        ).df()
        pd.testing.assert_frame_equal(exported, original, check_dtype=False)


def test_csv_reloads_with_the_same_values(lake, tmp_path):
    export_experiment("E900", tmp_path, "csv", tables=["runs", "gene_stats"], lake=lake)
    assert {p.suffix for p in tmp_path.iterdir()} == {".csv", ".md", ".json"}
    from_csv = pd.read_csv(tmp_path / "gene_stats.csv")
    original = (
        connect(lake)
        .sql(
            "SELECT * FROM gene_stats WHERE run_id IN (SELECT run_id FROM runs WHERE "
            "experiment_id = 'E900') ORDER BY run_id, tick, gene"
        )
        .df()
    )
    assert len(from_csv) == len(original)
    assert (from_csv["mean"] - original["mean"]).abs().max() < 1e-12


def test_reanalysis_with_pandas_alone_matches_genesis(parquet_export, lake):
    # What a collaborator with only the export would do: pure pandas, no Genesis Lab helpers.
    runs = pd.read_parquet(parquet_export / "runs.parquet")
    stats = pd.read_parquet(
        parquet_export / "gene_stats.parquet", filters=[("tick", ">=", 100), ("tick", "<=", 199)]
    )
    independent = (
        stats.groupby(["run_id", "gene"])["mean"]
        .mean()
        .unstack()
        .join(runs.set_index("run_id")["condition"])
        .sort_index()
    )
    ours = settled_gene_means_df("E900", 100, 199, lake).set_index("run_id").sort_index()
    for gene in ("speed", "sense_range", "neutral_marker"):
        assert independent[gene].to_numpy() == pytest.approx(ours[gene].to_numpy(), rel=1e-12)


def test_readme_documents_exactly_the_exported_tables(parquet_export):
    text = (parquet_export / "README.md").read_text()
    for table in ("runs", "ticks", "gene_stats", "genomes", "organisms", "mutations"):
        assert f"## `{table}`" in text
    assert "## `events`" not in text and "## `experiments`" not in text
    assert "## Conventions" in text and "independent replicate" in text


def test_verify_detects_changed_and_missing_files(parquet_export, tmp_path):
    import shutil

    copy = tmp_path / "copy"
    shutil.copytree(parquet_export, copy)
    assert verify_export(copy) == []
    with (copy / "ticks.parquet").open("ab") as f:
        f.write(b"x")  # one extra byte
    (copy / "mutations.parquet").unlink()
    problems = verify_export(copy)
    assert any("ticks.parquet does not match" in p for p in problems)
    assert any("mutations.parquet is missing" in p for p in problems)


def test_export_query(lake, tmp_path):
    rows = export_query(
        "SELECT condition, count(*) AS n FROM completed_runs WHERE "
        "experiment_id = 'E900' GROUP BY 1 ORDER BY 1",
        tmp_path / "q.csv",
        lake,
    )
    assert rows == 2
    assert (tmp_path / "q.csv").read_text() == "condition,n\nplenty,2\nscarce,2\n"
    with pytest.raises(ValueError, match=".parquet or .csv"):
        export_query("SELECT 1", tmp_path / "q.xlsx", lake)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"experiment_id": "E777"}, "no runs"),
        ({"tables": ["nope"]}, "unknown table"),
        ({"fmt": "xlsx"}, "format"),
    ],
)
def test_export_errors(lake, tmp_path, kwargs, match):
    args = {"experiment_id": "E900", "out_dir": tmp_path, "lake": lake} | kwargs
    with pytest.raises(ValueError, match=match):
        export_experiment(**args)


def test_export_and_verify_commands(lake, tmp_path, capsys):
    out = tmp_path / "cli"
    assert (
        main(
            [
                "lake",
                "export",
                "--experiment",
                "E900",
                "--out",
                str(out),
                "--lake",
                str(lake),
                "--tables",
                "runs,ticks",
            ]
        )
        == 0
    )
    assert "exported E900" in capsys.readouterr().out
    assert main(["lake", "verify", str(out)]) == 0
    (out / "ticks.parquet").write_bytes(b"corrupted")
    assert main(["lake", "verify", str(out)]) == 1
    assert (
        main(["lake", "export", "--experiment", "E777", "--out", str(out), "--lake", str(lake)])
        == 2
    )
