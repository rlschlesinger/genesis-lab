"""Tests for NeuralController: outputs become actions, random draws are fixed per tick, and a
hand-built brain behaves the way its weights say it should."""

import math

import numpy as np
import pytest

from genesis.intelligence.brain_inputs import INPUT_NAMES, wall_distance_ahead
from genesis.intelligence.controllers import NeuralController, make_controller
from genesis.intelligence.neural import N_HIDDEN, N_INPUTS, N_OUTPUTS, Brain, BrainStack
from genesis.intelligence.sensors import BodySenses, Observations, sense_food

W = H = 200.0


def food_turner() -> Brain:
    """A hand-made brain: hidden unit 0 copies food_left; the turn output follows it strongly;
    throttle is a constant sigmoid(1) ~ 0.73. Every other weight is 0."""
    w_hidden = np.zeros((N_HIDDEN, N_INPUTS))
    w_hidden[0, INPUT_NAMES.index("food_left")] = 3.0
    w_output = np.zeros((N_OUTPUTS, N_HIDDEN))
    w_output[0, 0] = 3.0
    return Brain(w_hidden, np.zeros(N_HIDDEN), w_output, np.array([0.0, 1.0]))


def observe(positions, headings, food, max_turn=0.5) -> Observations:
    positions = np.array(positions, float).reshape(-1, 2)
    headings = np.array(headings, float)
    n = len(positions)
    ranges = np.full(n, 20.0)
    obs = sense_food(
        positions, headings, ranges, np.full(n, 40.0), np.array(food, float).reshape(-1, 2)
    )
    body = BodySenses(
        wall_distance=wall_distance_ahead(positions, headings, W, H),
        sense_range=ranges,
        max_turn=np.full(n, max_turn),
        reproduction_threshold=np.full(n, 80.0),
    )
    return Observations(obs.food_found, obs.food_distance, obs.food_bearing, obs.energy, body)


def test_neural_is_a_configurable_controller():
    assert isinstance(make_controller("neural"), NeuralController)


def test_hand_built_brain_turns_toward_food_on_either_side():
    obs = observe([[100, 100], [100, 100], [100, 100]], [0.0, 0.0, 0.0], food=[])
    obs_left = observe([[100, 100]], [0.0], food=[[105, 110]])
    obs_right = observe([[100, 100]], [0.0], food=[[105, 90]])
    brain = BrainStack.of([food_turner()])
    rng = np.random.default_rng(0)
    left = NeuralController().decide(obs_left, rng, brain)
    right = NeuralController().decide(obs_right, rng, brain)
    assert left.turn[0] > 0.3 and right.turn[0] < -0.3  # positive = counter-clockwise = left
    assert left.turn[0] == pytest.approx(-right.turn[0])  # mirror image, mirror action
    none = NeuralController().decide(obs, rng, BrainStack.of([food_turner()] * 3))
    np.testing.assert_array_equal(none.turn, 0.0)  # no food seen: no reason to turn
    assert none.throttle[0] == pytest.approx(1 / (1 + math.exp(-1)))


def test_turn_is_a_fraction_of_each_organisms_own_max_turn():
    brain = BrainStack.of([food_turner()])
    narrow = observe([[100, 100]], [0.0], food=[[105, 110]], max_turn=0.25)
    wide = observe([[100, 100]], [0.0], food=[[105, 110]], max_turn=1.0)
    a = NeuralController().decide(narrow, np.random.default_rng(1), brain).turn[0]
    b = NeuralController().decide(wide, np.random.default_rng(1), brain).turn[0]
    assert b == pytest.approx(4 * a)
    assert abs(b) < 1.0  # tanh never reaches 1, so the body limit is never exceeded


def test_one_noise_draw_per_organism_per_tick():
    n = 5
    obs = observe(np.full((n, 2), 100.0), np.zeros(n), food=[])
    rng = np.random.default_rng(2)
    thought = NeuralController().think(obs, rng, BrainStack.of([food_turner()] * n))
    reference = np.random.default_rng(2)
    np.testing.assert_array_equal(
        thought.inputs[:, INPUT_NAMES.index("noise")], reference.uniform(-1, 1, n)
    )
    assert rng.random() == reference.random()  # and nothing else was drawn


def test_think_exposes_every_step_and_matches_decide():
    rng_a, rng_b = np.random.default_rng(3), np.random.default_rng(3)
    obs = observe([[10, 10], [150, 20]], [1.0, -2.0], food=[[15, 12]])
    brains = BrainStack.of([food_turner(), Brain.from_vector(np.linspace(-1, 1, 62))])
    thought = NeuralController().think(obs, rng_a, brains)
    actions = NeuralController().decide(obs, rng_b, brains)
    assert thought.actions.turn.tobytes() == actions.turn.tobytes()
    assert thought.activations.hidden.shape == (2, N_HIDDEN)
    assert thought.inputs.shape == (2, N_INPUTS)


def test_empty_population_decides_nothing_and_draws_nothing():
    obs = observe(np.empty((0, 2)), np.empty(0), food=[[1, 1]])
    rng = np.random.default_rng(4)
    actions = NeuralController().decide(obs, rng, None)
    assert len(actions.turn) == 0 and len(actions.throttle) == 0
    assert rng.random() == np.random.default_rng(4).random()


def test_missing_brains_or_body_is_an_error():
    obs = observe([[100, 100]], [0.0], food=[])
    with pytest.raises(ValueError, match="one brain per organism"):
        NeuralController().decide(obs, np.random.default_rng(5), None)
    with pytest.raises(ValueError, match="2 brains for 1"):
        NeuralController().decide(obs, np.random.default_rng(5), BrainStack.of([food_turner()] * 2))
    bodiless = Observations(obs.food_found, obs.food_distance, obs.food_bearing, obs.energy)
    with pytest.raises(ValueError, match="BodySenses"):
        NeuralController().decide(
            bodiless, np.random.default_rng(5), BrainStack.of([food_turner()])
        )
