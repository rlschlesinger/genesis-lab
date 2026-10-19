"""Tests for the brain's sensor vector: each input's meaning, the wall sensor's geometry, and
that every input stays in [-1, 1] whatever state an organism is in."""

import math

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from genesis.intelligence.brain_inputs import INPUT_NAMES, brain_inputs, wall_distance_ahead
from genesis.intelligence.neural import N_INPUTS, PARAMETER_COUNT, Brain, BrainStack, forward
from genesis.intelligence.sensors import sense_food

W, H = 200.0, 100.0


def inputs_for(
    position, heading, food, *, sense_range=20.0, energy=25.0, threshold=50.0, noise=0.0
):
    """One organism's input vector, built the way the simulation will build it."""
    positions = np.array([position], dtype=float)
    headings = np.array([heading])
    ranges = np.array([sense_range])
    obs = sense_food(
        positions, headings, ranges, np.array([energy]), np.array(food, float).reshape(-1, 2)
    )
    walls = wall_distance_ahead(positions, headings, W, H)
    return dict(
        zip(
            INPUT_NAMES,
            brain_inputs(obs, ranges, np.array([threshold]), walls, np.array([noise]))[0],
            strict=True,
        )
    )


def test_seven_named_inputs_match_the_brain():
    assert len(INPUT_NAMES) == N_INPUTS == 7
    assert len(set(INPUT_NAMES)) == 7


# --- food inputs ----------------------------------------------------------------------------


def test_no_food_in_sight_reports_zero_for_every_food_input():
    x = inputs_for((100, 50), 0.0, food=[[190, 90]])  # far beyond 20 units
    assert (x["food_seen"], x["food_ahead"], x["food_left"], x["food_closeness"]) == (0, 0, 0, 0)


def test_food_straight_ahead():
    x = inputs_for((100, 50), 0.0, food=[[110, 50]])  # 10 units ahead, range 20
    assert x["food_seen"] == 1.0
    assert x["food_ahead"] == pytest.approx(1.0)
    assert x["food_left"] == pytest.approx(0.0)
    assert x["food_closeness"] == pytest.approx(0.5)


def test_food_to_the_left_and_behind():
    left = inputs_for((100, 50), 0.0, food=[[100, 60]])
    assert left["food_ahead"] == pytest.approx(0.0, abs=1e-12)
    assert left["food_left"] == pytest.approx(1.0)
    behind = inputs_for((100, 50), 0.0, food=[[95, 50]])
    assert behind["food_ahead"] == pytest.approx(-1.0)


def test_food_just_behind_on_either_side_gives_nearly_equal_inputs():
    """The reason for cos/sin: the angle jumps from +pi to -pi, these don't."""
    a = inputs_for((100, 50), 0.0, food=[[90, 50.001]])
    b = inputs_for((100, 50), 0.0, food=[[90, 49.999]])
    assert a["food_ahead"] == pytest.approx(b["food_ahead"], abs=1e-6)
    assert a["food_left"] == pytest.approx(b["food_left"], abs=1e-3)


def test_food_closeness_runs_from_one_at_contact_to_zero_at_the_edge_of_range():
    assert inputs_for((100, 50), 0.0, food=[[100, 50]])["food_closeness"] == 1.0
    assert inputs_for((100, 50), 0.0, food=[[120, 50]])["food_closeness"] == pytest.approx(0.0)


# --- energy and noise -----------------------------------------------------------------------


@pytest.mark.parametrize("energy, expected", [(0.0, 0.0), (25.0, 0.5), (50.0, 1.0), (500.0, 1.0)])
def test_energy_is_a_fraction_of_the_reproduction_threshold_capped_at_one(energy, expected):
    assert inputs_for((100, 50), 0.0, food=[], energy=energy)["energy"] == expected


def test_noise_passes_through_and_out_of_range_noise_is_rejected():
    assert inputs_for((100, 50), 0.0, food=[], noise=-0.75)["noise"] == -0.75
    with pytest.raises(ValueError, match="noise"):
        inputs_for((100, 50), 0.0, food=[], noise=1.5)
    with pytest.raises(ValueError, match="noise"):
        inputs_for((100, 50), 0.0, food=[], noise=math.nan)


# --- the wall sensor ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "position, heading, expected",
    [
        ((50, 50), 0.0, 150.0),  # facing right: 200 - 50
        ((50, 50), math.pi, 50.0),  # facing left
        ((50, 30), math.pi / 2, 70.0),  # facing up: 100 - 30
        ((50, 30), -math.pi / 2, 30.0),  # facing down
        ((0, 0), math.pi / 4, 100 * math.sqrt(2)),  # diagonal: the top wall comes first
        ((200, 50), 0.0, 0.0),  # pressed against the right wall, facing it
        ((200, 50), math.pi, 200.0),  # same spot, facing away
    ],
)
def test_wall_distance_ahead(position, heading, expected):
    got = wall_distance_ahead(np.array([position], float), np.array([heading]), W, H)[0]
    assert got == pytest.approx(expected)


def test_wall_ahead_input_is_zero_when_the_wall_is_out_of_sight_and_one_when_touching():
    assert inputs_for((100, 50), 0.0, food=[])["wall_ahead"] == 0.0  # 100 units away
    assert inputs_for((190, 50), 0.0, food=[])["wall_ahead"] == pytest.approx(0.5)  # 10 of 20
    assert inputs_for((200, 50), 0.0, food=[])["wall_ahead"] == 1.0


def test_wall_distance_of_nobody_is_empty():
    assert wall_distance_ahead(np.empty((0, 2)), np.empty(0), W, H).shape == (0,)


# --- every input in [-1, 1], for any state --------------------------------------------------


@given(
    x=st.floats(0, W),
    y=st.floats(0, H),
    heading=st.floats(-math.pi, math.pi),
    sense_range=st.floats(0.01, 1000),
    energy=st.floats(0, 1e9),
    threshold=st.floats(0.01, 1e6),
    noise=st.floats(-1, 1),
    food=st.lists(st.tuples(st.floats(0, W), st.floats(0, H)), max_size=5),
)
def test_every_input_stays_in_range_and_the_brain_output_is_finite(
    x, y, heading, sense_range, energy, threshold, noise, food
):
    v = inputs_for(
        (x, y), heading, food=food, sense_range=sense_range, energy=energy, threshold=threshold,
        noise=noise,
    )  # fmt: skip
    values = np.array(list(v.values()))
    assert np.all(np.isfinite(values))
    assert np.all((values >= -1.0) & (values <= 1.0))
    assert all(
        v[name] >= 0 for name in INPUT_NAMES if name not in ("food_ahead", "food_left", "noise")
    )
    brain = Brain.from_vector(np.full(PARAMETER_COUNT, 4.0))  # the largest weights allowed (4.3)
    out = forward(BrainStack.of([brain]), values[np.newaxis, :]).outputs
    assert np.all(np.isfinite(out))


def test_many_organisms_at_once_match_one_at_a_time():
    rng = np.random.default_rng(1)
    n = 200
    positions = rng.uniform([0, 0], [W, H], size=(n, 2))
    headings = rng.uniform(-math.pi, math.pi, n)
    ranges = rng.uniform(5, 40, n)
    energies = rng.uniform(0, 80, n)
    food = rng.uniform([0, 0], [W, H], size=(60, 2))
    obs = sense_food(positions, headings, ranges, energies, food)
    walls = wall_distance_ahead(positions, headings, W, H)
    noise = rng.uniform(-1, 1, n)
    together = brain_inputs(obs, ranges, np.full(n, 50.0), walls, noise)
    for k in (0, 57, 199):
        alone = inputs_for(
            positions[k], headings[k], food, sense_range=ranges[k], energy=energies[k],
            noise=noise[k],
        )  # fmt: skip
        assert together[k].tolist() == list(alone.values())


def test_mismatched_lengths_are_rejected():
    obs = sense_food(np.zeros((2, 2)), np.zeros(2), np.ones(2), np.ones(2), np.empty((0, 2)))
    with pytest.raises(ValueError, match="noise must have shape"):
        brain_inputs(obs, np.ones(2), np.ones(2), np.ones(2), np.zeros(3))
    with pytest.raises(ValueError, match="positive"):
        brain_inputs(obs, np.zeros(2), np.ones(2), np.ones(2), np.zeros(2))
