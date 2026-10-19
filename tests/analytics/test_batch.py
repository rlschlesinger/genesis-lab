"""Tests for experiment specs and the batch runner."""

import json
import os
from pathlib import Path

import pydantic
import pytest
import yaml

from genesis.analytics.batch import (
    COMPLETED,
    INCOMPLETE,
    MISSING,
    STALE,
    StaleRunsError,
    _run_task,
    plan,
    run_experiment,
    task_status,
)
from genesis.analytics.spec import PROJECT_ROOT, ExperimentSpec, load_spec
from genesis.cli import main
from genesis.lake.db import connect

SPECS = PROJECT_ROOT / "experiments" / "specs"


def spec_dict(tmp_path: Path, **changes) -> dict:
    data = {
        "experiment_id": "E900",
        "title": "test",
        "definition": "docs/experiments/E900.md",
        "base_config": "configs/evolution.yaml",
        "base_changes": {"run.max_ticks": 120},
        "seeds": [11, 12],
        "conditions": [
            {"label": "plenty", "changes": {}},
            {"label": "scarce", "changes": {"food.regrowth_per_tick": 1.0}},
        ],
        "output": str(tmp_path / "out"),
    }
    return data | changes


def write_spec(tmp_path: Path, **changes) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(spec_dict(tmp_path, **changes)))
    return path


# --- Spec files ---------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "runs"), [("E001", 20), ("E002", 60), ("E003", 80)])
def test_published_experiment_specs_load_and_plan(name, runs):
    spec = load_spec(SPECS / f"{name}.yaml")
    assert len(plan(spec)) == runs
    assert spec.experiment_id == name
    assert (PROJECT_ROOT / spec.definition).exists()


def test_yaml_anchor_merge_gives_n_scarce_both_changes():
    configs = load_spec(SPECS / "E003.yaml").configs()
    n_scarce = configs[("N_scarce", 2000)]
    assert n_scarce.food.regrowth_per_tick == 1.0 and n_scarce.genome.speed.neutral


def test_quoted_off_label_stays_a_string():
    assert load_spec(SPECS / "E002.yaml").conditions[0].label == "off"


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"conditions": [{"label": "a"}, {"label": "a"}]}, "distinct"),
        ({"conditions": [{"label": "bad label"}]}, "label"),
        ({"seeds": [1, 1]}, "distinct"),
        ({"experiment_id": "X1"}, "experiment_id"),
        ({"surprise": 1}, "surprise"),
    ],
)
def test_invalid_specs_rejected(tmp_path, changes, match):
    with pytest.raises(pydantic.ValidationError, match=match):
        ExperimentSpec.model_validate(spec_dict(tmp_path, **changes))


def test_a_typo_in_any_condition_is_caught_before_running(tmp_path):
    path = write_spec(
        tmp_path,
        conditions=[
            {"label": "fine", "changes": {}},
            {"label": "typo", "changes": {"food.regrowth_per_tik": 1.0}},
        ],
    )
    with pytest.raises(KeyError, match="regrowth_per_tik"):
        load_spec(path)
    assert not (tmp_path / "out").exists()


def test_invalid_value_in_a_condition_is_caught_before_running(tmp_path):
    path = write_spec(tmp_path, conditions=[{"label": "neg", "changes": {"run.max_ticks": -5}}])
    with pytest.raises(pydantic.ValidationError, match="max_ticks"):
        load_spec(path)


def test_seed_range_form(tmp_path):
    spec = load_spec(write_spec(tmp_path, seeds={"first": 5, "count": 3}))
    assert spec.seed_list() == [5, 6, 7]


# --- Running ------------------------------------------------------------------------------


def test_a_condition_can_have_its_own_seeds_and_per_seed_changes(tmp_path):
    """E007's evaluation: each evolved population runs in its own world, with its own brains."""
    spec = ExperimentSpec.model_validate(
        spec_dict(
            tmp_path,
            conditions=[
                {"label": "plenty", "changes": {}},
                {
                    "label": "special",
                    "seeds": [21, 22, 23],
                    "per_seed": {22: {"food.regrowth_per_tick": 0.5}},
                },
            ],
        )
    )
    assert spec.run_count() == 2 + 3
    configs = spec.configs()
    assert sorted(configs) == [
        ("plenty", 11), ("plenty", 12), ("special", 21), ("special", 22), ("special", 23)
    ]  # fmt: skip
    assert configs[("special", 22)].food.regrowth_per_tick == 0.5
    assert configs[("special", 21)].food.regrowth_per_tick == 2.0  # unchanged elsewhere
    assert configs[("special", 22)].run.seed == 22
    assert {t.out_dir.name for t in plan(spec)} >= {"special-s21", "special-s22", "special-s23"}


def test_per_seed_changes_for_a_seed_the_condition_does_not_run_are_rejected(tmp_path):
    bad = spec_dict(
        tmp_path,
        conditions=[{"label": "x", "seeds": [1, 2], "per_seed": {3: {"run.max_ticks": 5}}}],
    )
    with pytest.raises(pydantic.ValidationError, match="per_seed names seeds it doesn't run"):
        ExperimentSpec.model_validate(bad)


def csv_bytes(out: Path) -> dict[str, bytes]:
    return {
        f"{d.name}/{f.name}": f.read_bytes()
        for d in sorted(out.iterdir())
        for f in sorted(d.glob("*.csv"))
    }


def test_parallel_and_sequential_runs_are_byte_identical(tmp_path):
    one = load_spec(write_spec(tmp_path / "a"))
    two = load_spec(write_spec(tmp_path / "b"))
    run_experiment(one, workers=1, ingest=False)
    run_experiment(two, workers=2, ingest=False)
    a, b = csv_bytes(tmp_path / "a" / "out"), csv_bytes(tmp_path / "b" / "out")
    assert len(a) == 4 * 8  # 2 conditions x 2 seeds x 8 CSV files
    assert a == b


def test_runs_record_experiment_and_condition(tmp_path):
    spec = load_spec(write_spec(tmp_path))
    run_experiment(spec, workers=2, ingest=False)
    meta = json.loads((tmp_path / "out" / "scarce-s12" / "run.json").read_text())
    assert (meta["experiment_id"], meta["condition"], meta["seed"]) == ("E900", "scarce", 12)
    assert meta["config"]["food"]["regrowth_per_tick"] == 1.0


def test_resume_skips_completed_runs(tmp_path):
    spec = load_spec(write_spec(tmp_path))
    first = run_experiment(spec, workers=2, ingest=False)
    stamps = {p: p.stat().st_mtime_ns for p in (tmp_path / "out").rglob("run.json")}
    second = run_experiment(spec, workers=2, ingest=False)
    assert len(first) == 4 and second == []
    assert stamps == {p: p.stat().st_mtime_ns for p in (tmp_path / "out").rglob("run.json")}
    assert {task_status(t) for t in plan(spec)} == {COMPLETED}


def test_partial_resume_runs_only_what_is_missing(tmp_path):
    spec = load_spec(write_spec(tmp_path))
    run_experiment(spec, workers=2, ingest=False)
    (tmp_path / "out" / "plenty-s11" / "run.json").unlink()
    rerun = run_experiment(spec, workers=2, ingest=False)
    assert [(o.task.condition, o.task.seed) for o in rerun] == [("plenty", 11)]


def test_changed_spec_marks_runs_stale_and_refuses_to_mix(tmp_path):
    run_experiment(load_spec(write_spec(tmp_path)), workers=2, ingest=False)
    changed = load_spec(write_spec(tmp_path, base_changes={"run.max_ticks": 130}))
    assert {task_status(t) for t in plan(changed)} == {STALE}
    with pytest.raises(StaleRunsError, match="4 completed run"):
        run_experiment(changed, workers=2, ingest=False)
    rerun = run_experiment(changed, workers=2, ingest=False, rerun_stale=True)
    assert len(rerun) == 4 and {task_status(t) for t in plan(changed)} == {COMPLETED}


def test_status_of_missing_and_incomplete_runs(tmp_path):
    spec = load_spec(write_spec(tmp_path))
    task = plan(spec)[0]
    assert task_status(task) == MISSING
    task.out_dir.mkdir(parents=True)
    (task.out_dir / "run.json").write_text(json.dumps({"status": "failed", "config": {}}))
    assert task_status(task) == INCOMPLETE


def test_a_failing_run_is_reported_not_raised(tmp_path, monkeypatch):
    # Runs in this process so the failure can be injected; workers use the same function.
    from genesis.core.simulation import Simulation

    def boom(self):
        raise RuntimeError("injected")

    monkeypatch.setattr(Simulation, "step", boom)
    spec = load_spec(write_spec(tmp_path))
    task = plan(spec)[0]
    ok, message = _run_task(task.config.model_dump(mode="json"), str(task.out_dir), "E900", "x")
    assert not ok and "injected" in message
    assert json.loads((task.out_dir / "run.json").read_text())["status"] == "failed"


def test_results_are_loaded_into_the_lake(tmp_path):
    spec = load_spec(write_spec(tmp_path))
    run_experiment(spec, workers=2, lake=tmp_path / "lake")
    rows = (
        connect(tmp_path / "lake")
        .sql(
            "SELECT condition, count(*) FROM completed_runs WHERE experiment_id = 'E900' "
            "GROUP BY 1 ORDER BY 1"
        )
        .fetchall()
    )
    assert rows == [("plenty", 2), ("scarce", 2)]


# --- Command line -------------------------------------------------------------------------


def test_experiment_commands(tmp_path, capsys):
    path = write_spec(tmp_path)
    args = ["--workers", "2", "--lake", str(tmp_path / "lake")]
    assert main(["experiment", "run", str(path), *args]) == 0
    assert "ran 4, skipped 0" in capsys.readouterr().out
    assert main(["experiment", "run", str(path), *args]) == 0
    assert "ran 0, skipped 4" in capsys.readouterr().out
    assert main(["experiment", "status", str(path)]) == 0
    assert "completed   4" in capsys.readouterr().out


def test_experiment_command_rejects_bad_specs(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("experiment_id: nope\n")
    assert main(["experiment", "run", str(bad)]) == 2
    assert "invalid experiment spec" in capsys.readouterr().err


def test_default_workers_leaves_a_core_free():
    from genesis.analytics.batch import default_workers

    assert default_workers() == max(1, (os.cpu_count() or 2) - 1)
