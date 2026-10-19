"""Tests for `genesis inspect`: the replayed decision is the simulation's own, the replay is
checked against the recording, and impossible requests get clear errors."""

import csv
import math
from pathlib import Path

import numpy as np
import pytest

from genesis.analytics.inspector import (
    InspectError,
    format_inspection,
    inspect_run_folder,
    inspect_tick,
    os_family,
)
from genesis.analytics.runs import execute_run
from genesis.cli import main
from genesis.core.config import SimulationConfig, load_config
from genesis.core.simulation import Simulation

CONFIGS = Path(__file__).parents[2] / "configs"


def config(name="neural.yaml", ticks=300) -> SimulationConfig:
    raw = load_config(CONFIGS / name).model_dump()
    raw["run"]["max_ticks"] = ticks
    return SimulationConfig.model_validate(raw)


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("neural")
    execute_run(config(), out)
    return out


def test_inspected_decision_is_what_the_brain_computes_and_the_body_does():
    i = inspect_tick(config(), 120, 5)
    # The printed numbers are the network's: recomputing from the same inputs agrees exactly.
    again = i.brain.forward(i.inputs)
    assert again.hidden.tobytes() == i.hidden.tobytes()
    assert again.outputs.tobytes() == i.outputs.tobytes()
    assert i.turn == i.outputs[0] * i.max_turn  # tanh * max_turn never needs clipping
    assert i.throttle == i.outputs[1]


def test_inspected_result_matches_an_independent_run():
    i = inspect_tick(config(), 120, 5)
    sim = Simulation(config())
    for _ in range(121):
        sim.step()
    org = next(o for o in [*sim.organisms, *sim.dead] if o.id == 5)
    assert (i.after.x, i.after.y, i.after.heading, i.after.energy) == (
        org.x,
        org.y,
        org.heading,
        org.energy,
    )
    moved = math.hypot(i.after.x - i.before.x, i.after.y - i.before.y)
    assert moved == pytest.approx(i.throttle * i.speed) or i.after.x in (0.0, 200.0)


def test_rule_based_organisms_show_their_decision_without_a_brain():
    i = inspect_tick(config("evolution.yaml"), 50, 3)
    assert i.brain is None and i.inputs is None and i.hidden is None
    assert i.throttle == 1.0
    text = format_inspection(i)
    assert "rule-based" in text and "Hidden layer" not in text


def test_run_folder_replay_is_checked_against_ticks_csv(run_dir, tmp_path):
    i = inspect_run_folder(run_dir, 200, 2)
    assert i.recorded_match is True
    assert i.platform_note is None  # recorded on this machine

    # Alter the recorded population at tick 200: the replay must now be reported as diverged.
    copy = tmp_path / "copy"
    copy.mkdir()
    for f in run_dir.iterdir():
        (copy / f.name).write_bytes(f.read_bytes())
    with (copy / "ticks.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    rows[200]["population"] = str(int(rows[200]["population"]) + 1)
    with (copy / "ticks.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    assert inspect_run_folder(copy, 200, 2).recorded_match is False


@pytest.mark.parametrize(
    "tick, organism, message",
    [
        (-1, 0, "0 or more"),
        (300, 0, "the run has 300 ticks"),
        (10, 9999, "born after tick 9"),
    ],
)
def test_impossible_requests_are_explained(tick, organism, message):
    with pytest.raises(InspectError, match=message):
        inspect_tick(config(), tick, organism)


def test_a_dead_organism_names_its_lifetime():
    sim = Simulation(config())
    for _ in range(300):
        sim.step()
    dead = sim.dead[0]
    with pytest.raises(InspectError, match=f"died at tick {dead.death_tick}"):
        inspect_tick(config(), dead.death_tick + 1, dead.id)


def test_extinction_before_the_tick_is_explained():
    raw = config().model_dump()
    raw["food"] |= {"initial_count": 0, "regrowth_per_tick": 0.0}
    raw["organisms"]["initial_energy"] = 0.5
    with pytest.raises(InspectError, match="went extinct"):
        inspect_tick(SimulationConfig.model_validate(raw), 50, 0)


def test_os_family_ignores_versions():
    assert os_family("macOS-27.0.1-arm64-arm-64bit") == "macOS"
    assert os_family("Linux-6.8.0-x86_64-with-glibc2.39") == "Linux"


def test_text_walks_through_every_step():
    text = format_inspection(inspect_tick(config(), 100, 7), weights=True)
    for heading in ("Sensed", "1. Inputs", "2. Hidden layer", "3. Outputs", "4. Result"):
        assert heading in text
    assert "Weights: hidden layer" in text and "food_seen" in text


# --- CLI ------------------------------------------------------------------------------------


def test_cli_inspects_a_run_folder_and_a_config(run_dir, capsys):
    assert main(["inspect", str(run_dir), "--tick", "50", "--organism", "4"]) == 0
    assert "Organism 4, tick 50" in capsys.readouterr().out
    args = ["inspect", "--config", str(CONFIGS / "neural.yaml"), "--seed", "3"]
    assert main([*args, "--tick", "5", "--organism", "1", "--weights"]) == 0
    assert "Weights: outputs" in capsys.readouterr().out


@pytest.mark.parametrize(
    "extra",
    [
        [],  # neither a run folder nor --config
        ["somewhere", "--config", "configs/neural.yaml"],  # both
        ["no-such-folder"],
    ],
)
def test_cli_rejects_bad_sources(extra, capsys):
    assert main(["inspect", *extra, "--tick", "1", "--organism", "0"]) == 2
    assert "error" in capsys.readouterr().err


def test_cli_reports_impossible_requests_without_a_traceback(run_dir, capsys):
    assert main(["inspect", str(run_dir), "--tick", "10", "--organism", "99999"]) == 2
    assert "born after" in capsys.readouterr().err


def test_inputs_shown_are_the_ones_that_produced_the_action():
    i = inspect_tick(config(), 77, 0)
    assert np.all(np.abs(i.inputs) <= 1.0)
    assert len(i.inputs) == 7 and len(i.hidden) == 6 and len(i.outputs) == 2
