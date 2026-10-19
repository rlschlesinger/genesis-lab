"""Tests for the from-scratch forward pass: shapes, a hand-computed example, extremes,
bit-identical batching, and that brains never share or change their arrays."""

import math

import numpy as np
import pytest

from genesis.intelligence.neural import (
    N_HIDDEN,
    N_INPUTS,
    N_OUTPUTS,
    PARAMETER_COUNT,
    Brain,
    BrainStack,
    forward,
    parameter_count,
    sigmoid,
)


def tiny_brain() -> Brain:
    """The worked example in docs/neural-networks.md: 2 inputs, 2 hidden units, 2 outputs."""
    return Brain(
        w_hidden=[[0.5, -1.0], [1.0, 1.0]],
        b_hidden=[0.0, -0.5],
        w_output=[[2.0, 1.0], [0.0, -2.0]],
        b_output=[0.0, 1.0],
    )


def random_brain(rng: np.random.Generator, scale: float = 1.0) -> Brain:
    return Brain.from_vector(rng.normal(0.0, scale, PARAMETER_COUNT))


# --- shapes and parameter count -------------------------------------------------------------


def test_parameter_count_of_the_organism_brain():
    # 6 x 7 hidden weights + 6 hidden biases + 2 x 6 output weights + 2 output biases.
    assert (N_INPUTS, N_HIDDEN, N_OUTPUTS) == (7, 6, 2)
    assert PARAMETER_COUNT == 42 + 6 + 12 + 2 == 62
    assert parameter_count(2, 2, 2) == 12


def test_vector_round_trip_keeps_every_parameter_in_place():
    vector = np.arange(PARAMETER_COUNT, dtype=float)
    brain = Brain.from_vector(vector)
    assert brain.shape == (N_INPUTS, N_HIDDEN, N_OUTPUTS)
    # Layout: w_hidden row by row first, so w_hidden[1, 0] is parameter 7.
    assert brain.w_hidden[1, 0] == 7
    assert brain.b_hidden[0] == 42
    assert brain.w_output[0, 0] == 48
    assert brain.b_output[-1] == 61
    np.testing.assert_array_equal(brain.to_vector(), vector)


def test_tiny_brain_vector_order():
    assert tiny_brain().to_vector().tolist() == [
        0.5, -1.0, 1.0, 1.0,  # w_hidden, row by row
        0.0, -0.5,  # b_hidden
        2.0, 1.0, 0.0, -2.0,  # w_output, row by row
        0.0, 1.0,  # b_output
    ]  # fmt: skip


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"b_hidden": [0.0]}, "b_hidden must have shape"),
        ({"w_output": [[1.0, 2.0, 3.0]]}, "w_output must have shape"),
        ({"b_output": [0.0, 1.0, 2.0]}, "b_output must have shape"),
        ({"w_hidden": [1.0, 2.0]}, "2-D"),
        ({"b_hidden": [0.0, math.nan]}, "NaN or infinity"),
        ({"w_output": [[math.inf, 1.0], [0.0, 1.0]]}, "NaN or infinity"),
    ],
)
def test_malformed_brains_are_rejected(kwargs, message):
    parts = {
        "w_hidden": [[0.5, -1.0], [1.0, 1.0]],
        "b_hidden": [0.0, -0.5],
        "w_output": [[2.0, 1.0], [0.0, -2.0]],
        "b_output": [0.0, 1.0],
    }
    with pytest.raises(ValueError, match=message):
        Brain(**{**parts, **kwargs})


def test_wrong_vector_length_is_rejected():
    with pytest.raises(ValueError, match="needs 62 parameters"):
        Brain.from_vector(np.zeros(61))


def test_inputs_of_the_wrong_shape_are_rejected():
    with pytest.raises(ValueError, match="inputs must have shape"):
        tiny_brain().forward([1.0, 2.0, 3.0])


# --- the worked example, by hand ------------------------------------------------------------


def test_hand_computed_forward_pass():
    """Every number here is worked out step by step in docs/neural-networks.md."""
    a = tiny_brain().forward([1.0, 0.5])
    # Hidden sums: 0.5*1 + (-1)*0.5 + 0 = 0  and  1*1 + 1*0.5 + (-0.5) = 1.
    assert a.hidden_sum.tolist() == [0.0, 1.0]
    assert a.hidden[0] == 0.0  # tanh(0)
    assert a.hidden[1] == pytest.approx(0.761594, abs=1e-6)  # tanh(1)
    # Output sums: 2*0 + 1*0.7616 + 0  and  0*0 + (-2)*0.7616 + 1.
    assert a.output_sum[0] == pytest.approx(0.761594, abs=1e-6)
    assert a.output_sum[1] == pytest.approx(-0.523188, abs=1e-6)
    assert a.outputs[0] == pytest.approx(0.642015, abs=1e-6)  # tanh(0.7616): turn
    assert a.outputs[1] == pytest.approx(0.372107, abs=1e-6)  # sigmoid(-0.5232): throttle


def test_forward_pass_matches_textbook_formulas():
    """The same computation written as plain Python loops, the way you'd do it on paper."""
    brain = random_brain(np.random.default_rng(1))
    x = np.random.default_rng(2).uniform(-1, 1, N_INPUTS)
    hidden = [
        math.tanh(sum(w * xi for w, xi in zip(row, x, strict=True)) + b)
        for row, b in zip(brain.w_hidden, brain.b_hidden, strict=True)
    ]
    z = [
        sum(w * hj for w, hj in zip(row, hidden, strict=True)) + b
        for row, b in zip(brain.w_output, brain.b_output, strict=True)
    ]
    a = brain.forward(x)
    np.testing.assert_allclose(a.hidden, hidden, rtol=0, atol=1e-12)
    assert a.outputs[0] == pytest.approx(math.tanh(z[0]), abs=1e-12)
    assert a.outputs[1] == pytest.approx(1 / (1 + math.exp(-z[1])), abs=1e-12)


def test_sigmoid_is_the_logistic_function_and_never_overflows():
    z = np.array([-5.0, -1.0, 0.0, 0.5, 3.0])
    np.testing.assert_allclose(sigmoid(z), 1 / (1 + np.exp(-z)), rtol=0, atol=1e-15)
    with np.errstate(all="raise"):  # any overflow warning would become an error here
        extreme = sigmoid(np.array([-1e308, 1e308]))
    assert extreme.tolist() == [0.0, 1.0]


# --- extremes -------------------------------------------------------------------------------


def test_outputs_stay_in_range_for_extreme_weights_and_inputs():
    rng = np.random.default_rng(3)
    brains = [random_brain(rng, scale=1e6) for _ in range(50)]
    inputs = rng.choice([-1e300, -1.0, 0.0, 1.0, 1e300, -np.inf, np.inf], size=(50, N_INPUTS))
    with np.errstate(all="raise"):
        a = forward(BrainStack.of(brains), inputs)
    assert np.all(np.isfinite(a.outputs))
    assert np.all((a.outputs[:, 0] >= -1) & (a.outputs[:, 0] <= 1))
    assert np.all((a.outputs[:, 1] >= 0) & (a.outputs[:, 1] <= 1))
    # Inputs outside [-1, 1] are clipped before use (and recorded clipped).
    assert np.all(np.abs(a.inputs) <= 1.0)


def test_nan_input_is_an_error_not_a_silent_action():
    with pytest.raises(ValueError, match="NaN"):
        tiny_brain().forward([1.0, math.nan])


# --- batching, determinism, no shared state -------------------------------------------------


@pytest.mark.parametrize("n", [1, 2, 7, 64, 1000])
def test_stacked_forward_is_bit_identical_to_one_brain_at_a_time(n):
    """The simulation runs all organisms at once; the inspector runs one. Same bits."""
    rng = np.random.default_rng(n)
    brains = [random_brain(rng) for _ in range(n)]
    inputs = rng.uniform(-1, 1, size=(n, N_INPUTS))
    together = forward(BrainStack.of(brains), inputs)
    for k in (0, n // 2, n - 1):
        alone = brains[k].forward(inputs[k])
        assert alone.hidden_sum.tobytes() == together.hidden_sum[k].tobytes()
        assert alone.outputs.tobytes() == together.outputs[k].tobytes()


def test_same_brain_and_inputs_give_identical_outputs_every_time():
    brain = random_brain(np.random.default_rng(4))
    x = np.random.default_rng(5).uniform(-1, 1, N_INPUTS)
    first = brain.forward(x).outputs.tobytes()
    assert all(brain.forward(x).outputs.tobytes() == first for _ in range(5))


def test_brain_copies_its_inputs_and_is_read_only():
    weights = np.ones((2, 2))
    brain = Brain(weights, np.zeros(2), np.ones((2, 2)), np.zeros(2))
    weights[0, 0] = 99.0  # changing the caller's array...
    assert brain.w_hidden[0, 0] == 1.0  # ...doesn't reach the brain
    with pytest.raises(ValueError, match="read-only"):
        brain.w_hidden[0, 0] = 5.0


def test_brains_built_from_one_vector_do_not_share_memory():
    vector = np.random.default_rng(6).normal(size=PARAMETER_COUNT)
    a, b = Brain.from_vector(vector), Brain.from_vector(vector)
    assert not np.shares_memory(a.w_hidden, b.w_hidden)
    assert not np.shares_memory(a.w_hidden, vector)


def test_stacking_mixed_shapes_or_nothing_is_rejected():
    with pytest.raises(ValueError, match="different shapes"):
        BrainStack.of([tiny_brain(), random_brain(np.random.default_rng(7))])
    with pytest.raises(ValueError, match="zero brains"):
        BrainStack.of([])
