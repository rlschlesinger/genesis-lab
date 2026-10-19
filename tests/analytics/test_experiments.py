"""Tests for the experiment helpers."""

from pathlib import Path

import pytest

from genesis.analytics.experiments import (
    Condition,
    apply_changes,
    genomes_never_changed,
    paired,
    run_condition,
    settled_gene_means,
)
from genesis.core.config import load_config

EVOLUTION = Path(__file__).parents[2] / "configs" / "evolution.yaml"


@pytest.fixture
def base():
    return apply_changes(load_config(EVOLUTION), {"run.max_ticks": 300})


def test_apply_changes_sets_dotted_paths_and_validates(base):
    config = apply_changes(base, {"food.regrowth_per_tick": 1.0, "genome.speed.neutral": True})
    assert config.food.regrowth_per_tick == 1.0
    assert config.genome.speed.neutral is True
    assert base.food.regrowth_per_tick == 2.0  # the original is untouched


def test_apply_changes_rejects_typos(base):
    with pytest.raises(KeyError, match="regrowth_per_tik"):
        apply_changes(base, {"food.regrowth_per_tik": 1.0})


def test_run_condition_and_settled_means(base, tmp_path):
    dirs = run_condition(base, Condition("sel"), [5, 6], tmp_path, "TEST")
    assert [d.name for d in dirs] == ["sel-s5", "sel-s6"]
    means = settled_gene_means(dirs[0], 200, 299)
    assert set(means) >= {"speed", "metabolic_rate", "neutral_marker"}
    assert means["max_turn"] == 0.5  # frozen in evolution.yaml


def test_window_beyond_the_run_is_unmeasurable(base, tmp_path):
    (d,) = run_condition(base, Condition("sel"), [5], tmp_path, "TEST")
    assert settled_gene_means(d, 200, 300) is None  # the run ended at tick 299


def test_extinct_run_is_unmeasurable(base, tmp_path):
    starve = Condition("starve", {"food.initial_count": 0, "food.regrowth_per_tick": 0.0})
    (d,) = run_condition(base, starve, [5], tmp_path, "TEST")
    assert settled_gene_means(d, 200, 299) is None


def test_genomes_never_changed_detects_mutation(base, tmp_path):
    (off,) = run_condition(base, Condition("off", {"mutation.enabled": False}), [5], tmp_path, "T")
    (on,) = run_condition(base, Condition("on"), [5], tmp_path, "T")
    assert genomes_never_changed(off)
    assert not genomes_never_changed(on)


def test_paired_drops_and_reports_missing_seeds():
    diffs, dropped = paired({1: 5.0, 2: None, 3: 2.0}, {1: 4.0, 2: 1.0, 3: 3.0})
    assert diffs == [1.0, -1.0]
    assert dropped == [2]
