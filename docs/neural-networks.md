# Neural networks, by hand

Milestone 4 gives organisms a small neural network as a brain. This page explains what that network computes, with an example small enough to check with a calculator. The code is [`src/genesis/intelligence/neural.py`](../src/genesis/intelligence/neural.py); every number below is asserted by `test_hand_computed_forward_pass` in [`tests/intelligence/test_neural.py`](../tests/intelligence/test_neural.py).

## The pieces

- **Vector:** an ordered list of numbers. An organism's senses become one vector, such as `[food seen, direction to food, ...]`.
- **Matrix:** a table of numbers. Row *k* holds the weights of unit *k*.
- **Weight:** how strongly one input pushes one unit, and in which direction. A positive weight means "more of this input, more output"; a negative one means the opposite; zero means the input is ignored.
- **Bias:** a constant added to a unit's sum, so a unit can be "on" even when every input is 0.
- **Weighted sum:** multiply each input by its weight, add everything up, and add the bias. For a whole layer this is written `z = W·x + b`.
- **Activation function:** squashes a sum into a fixed range, so no input can produce a runaway output.
  - **tanh** maps any number into (−1, 1). tanh(0) = 0, tanh(1) ≈ 0.7616, and tanh of anything large is almost exactly ±1.
  - **sigmoid** maps any number into (0, 1): sigmoid(z) = 1 / (1 + e^−z). sigmoid(0) = 0.5.
- **Hidden layer:** the units between the inputs and the outputs. Their values are intermediate features the network invents, such as "food is close and ahead".
- **Forward pass:** one trip from inputs to outputs.

## The worked example

A tiny network with 2 inputs, 2 hidden units and 2 outputs. The organisms' real brain has the same structure, only bigger (7 inputs, 6 hidden units, 2 outputs).

```
inputs x          = [1.0, 0.5]

hidden weights    = [[0.5, -1.0],     # hidden unit 1
                     [1.0,  1.0]]     # hidden unit 2
hidden biases     = [0.0, -0.5]

output weights    = [[2.0,  1.0],     # output 1: turn
                     [0.0, -2.0]]     # output 2: throttle
output biases     = [0.0, 1.0]
```

**Step 1: hidden weighted sums.**

- Unit 1: 0.5 × 1.0 + (−1.0) × 0.5 + 0.0 = 0.5 − 0.5 = **0**
- Unit 2: 1.0 × 1.0 + 1.0 × 0.5 + (−0.5) = 1.0 + 0.5 − 0.5 = **1**

**Step 2: hidden activations (tanh).**

- tanh(0) = **0**
- tanh(1) ≈ **0.7616**

**Step 3: output weighted sums.**

- Turn: 2.0 × 0 + 1.0 × 0.7616 + 0.0 ≈ **0.7616**
- Throttle: 0.0 × 0 + (−2.0) × 0.7616 + 1.0 ≈ **−0.5232**

**Step 4: output activations.**

- Turn uses tanh, because it needs a sign (left or right): tanh(0.7616) ≈ **0.6420**
- Throttle uses the sigmoid, because it is a fraction of full speed: sigmoid(−0.5232) = 1 / (1 + e^0.5232) ≈ **0.3721**

So this brain turns 64% of its maximum turn to the left (positive is counter-clockwise, as for food bearings) and moves at 37% of its top speed. Mapping these two numbers to an actual turn and speed happens in increment 4.4.

Notice hidden unit 1: its two inputs cancelled out exactly, so it contributed nothing. With other inputs it would. That is what a hidden unit is: a feature that switches on for some combinations of inputs and not others.

## What the brain is told

The organism brain has 7 inputs, each scaled so it lies between −1 and 1 and is 0 when there is nothing to report ([`brain_inputs.py`](../src/genesis/intelligence/brain_inputs.py), D-040):

| # | Input | Meaning |
|---|---|---|
| 0 | food_seen | 1 if any food is within sense range, else 0 |
| 1 | food_ahead | cos(bearing to food): 1 straight ahead, −1 straight behind |
| 2 | food_left | sin(bearing to food): 1 to the left, −1 to the right |
| 3 | food_closeness | 1 touching the food, 0 at the edge of sight |
| 4 | energy | energy as a fraction of the reproduction threshold (capped at 1) |
| 5 | wall_ahead | 1 touching the wall straight ahead, 0 when it is out of sight |
| 6 | noise | a fresh random number each tick |

So "food slightly to the left, quite close, half full, no wall in sight" is roughly `[1, 0.97, 0.26, 0.7, 0.5, 0, noise]`.

## Counting parameters

Every weight and bias is one number in the brain. For the organism brain:

| Part | Shape | Count |
|---|---|---|
| hidden weights | 6 units × 7 inputs | 42 |
| hidden biases | 6 | 6 |
| output weights | 2 outputs × 6 hidden units | 12 |
| output biases | 2 | 2 |
| **total** | | **62** |

`Brain.to_vector()` lays these 62 numbers out in exactly that order (hidden weights row by row, hidden biases, output weights row by row, output biases). That flat vector is what organisms inherit and mutate (increment 4.3).

## Watching a real brain decide

`genesis inspect` replays a run to any tick and prints one organism's whole computation:

```bash
uv run genesis inspect data/runs/neural-1 --tick 15000 --organism 3217 --weights
```

It shows what the organism sensed, its 7 inputs, each hidden unit's weighted sum and tanh, the two outputs and how they became a turn and a throttle, and what happened (new heading, position, energy). `--weights` adds the weight tables: row *h* of the hidden table is what hidden unit *h* listens to; the output table is how much each hidden unit pushes turn and throttle.

## Where the weights come from: selection, not training

In most machine learning, a network is **trained**: it is shown examples and the right answers, its error is measured, and **backpropagation** works out how to nudge every weight to reduce that error (the nudges point along the *gradient*, the direction in which the error falls fastest). Repeated millions of times, the network gets better.

Nothing like that happens here. No organism is ever told what the right action was, and no weight is ever adjusted during a lifetime. Instead:

1. Founders start with random weights, so some brains behave better than others by chance.
2. Organisms that find more food reproduce more, and their offspring inherit their weights.
3. Mutation changes a few weights slightly at each birth, producing new variants.

Over many generations this is **neuroevolution**: selection on random variation, exactly the mechanism E002 showed working for speed and reproduction threshold, now applied to 62 numbers that together describe a behaviour. It is much less efficient than backpropagation, but it needs no right answers, only survival and reproduction. A real possible outcome of Milestone 4 is that evolved brains do worse than the simple hand-written rule. That would be a result too.

## Why the arithmetic is written the way it is

The same weighted sums can be computed several ways in NumPy (`W @ x`, `np.einsum`, or multiply-then-`sum`). They are equal on paper but add the terms in a different order, and floating-point addition depends on order. Measured on the development Mac, about a third of values differed in the last bit between methods. Genesis Lab promises bit-identical results, so there is exactly one implementation, `forward()`, and a test checks that running 1,000 brains together gives the same bits as running each one alone.
