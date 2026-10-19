"""Tests for live runs: the state machine, config loading and the run limit."""

from itertools import product

import pytest

from genesis.api.runs import (
    ALLOWED,
    InvalidRunRequest,
    LiveRun,
    RunConflict,
    RunManager,
    RunNotFound,
    TooManyRuns,
)
from genesis.api.schemas import RunCreate, RunState


def test_every_state_move_is_either_allowed_or_refused():
    """The whole lifecycle in one table: finished runs are final, nothing returns to idle."""
    manager = RunManager()
    for start, end in product(RunState, RunState):
        run = manager.create(RunCreate())
        run.state = start
        if (start, end) in ALLOWED:
            run.move_to(end)
            assert run.state is end
        else:
            with pytest.raises(RunConflict, match=f"is {start}"):
                run.move_to(end)
            assert run.state is start  # a refused move changes nothing
        manager.delete(run.run_id)
    finished = {RunState.COMPLETED, RunState.FAILED}
    assert not any(start in finished for start, _ in ALLOWED)
    assert not any(end is RunState.IDLE for _, end in ALLOWED)


def test_create_applies_seed_ticks_and_changes():
    run = RunManager().create(
        RunCreate(config="evolution", seed=9, max_ticks=50, changes={"food.regrowth_per_tick": 0.5})
    )
    assert isinstance(run, LiveRun) and run.state is RunState.IDLE
    assert (run.config.run.seed, run.config.run.max_ticks) == (9, 50)
    assert run.config.food.regrowth_per_tick == 0.5
    assert run.sim.tick == 0 and len(run.sim.organisms) == 30
    assert "-s9-" in run.run_id


@pytest.mark.parametrize(
    "request_, message",
    [
        (RunCreate(config="nope"), "unknown config"),
        (RunCreate(changes={"food.regrowth_per_tik": 1.0}), "unknown config path"),
        (RunCreate(changes={"food.regrowth_per_tick": -1.0}), "regrowth_per_tick"),
        (RunCreate(changes={"organisms.controller": "neural"}), "needs a brain"),
    ],
)
def test_invalid_requests_are_refused_with_a_reason(request_, message):
    with pytest.raises(InvalidRunRequest, match=message):
        RunManager().create(request_)


def test_config_names_come_only_from_the_folder(tmp_path):
    (tmp_path / "mine.yaml").write_text((RunManager().configs_dir / "default.yaml").read_text())
    manager = RunManager(configs_dir=tmp_path)
    assert manager.config_names() == ["mine"]
    with pytest.raises(InvalidRunRequest, match="unknown config"):
        manager.load_config("default")  # exists elsewhere, but not in this folder


def test_the_number_of_live_runs_is_bounded():
    manager = RunManager(max_runs=2)
    first = manager.create(RunCreate())
    manager.create(RunCreate())
    with pytest.raises(TooManyRuns, match="limit is 2"):
        manager.create(RunCreate())
    manager.delete(first.run_id)
    manager.create(RunCreate())  # room again


def test_unknown_runs_are_not_found():
    with pytest.raises(RunNotFound):
        RunManager().get("missing")
    with pytest.raises(RunNotFound):
        RunManager().delete("missing")
