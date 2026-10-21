"""A small neural network, written from scratch in NumPy: the forward pass.

A neural network here is just a function from numbers to numbers. An organism's sensors give
a short list of numbers (the *input vector*); the network turns it into two numbers that say
what to do (turn and throttle). Two steps, repeated once per layer:

1. **Weighted sum.** Each unit in the next layer multiplies every input by its own *weight*,
   adds them up, and adds a *bias* (a constant that shifts the result). For one unit:
   ``z = w1*x1 + w2*x2 + ... + b``. Doing this for every unit at once is a matrix times a
   vector: ``z = W @ x + b``, where row k of ``W`` holds unit k's weights.
2. **Activation function.** The sum is squashed into a fixed range so that no input, however
   large, can produce an unbounded output. ``tanh`` maps any number into (-1, 1); the
   *sigmoid* maps it into (0, 1).

The layer in the middle is the *hidden layer*: its values are neither sensed nor acted on,
they are intermediate features the network computes (for example "food is ahead and close").
Running all of this once, inputs to outputs, is a *forward pass*.

Where the weights come from is the point of Milestone 4: they are genes. Nothing here learns.
Organisms whose weights happen to produce useful behaviour have more offspring, and mutation
supplies new weights (increment 4.3). That is selection, not training: there is no gradient
and no backpropagation.

One way of adding, everywhere. The weighted sums are written as an elementwise product summed
over the last (short) axis, ``(W * x).sum(-1)``: the most literal form of "multiply, then
add up". It is not the only form: ``W @ x`` and ``np.einsum`` compute the same sums but add
the terms in a different order, and floating-point addition depends on order. Measured on
the development Mac (2026-10-19), ``@`` and ``einsum`` differed from ``.sum`` in the last bit
for about a third of values. So every caller goes through ``forward`` below, and a test
checks that a stack of n brains gives exactly the bits each brain gives alone, which is what
lets the inspector (4.6) show exactly what the simulation computed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import compress

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]

# The organism brain (D-039). Inputs are defined in increment 4.2; outputs are mapped to
# actions in 4.4 (turn = max_turn * output 0, throttle = output 1).
N_INPUTS = 7
N_HIDDEN = 6
N_OUTPUTS = 2
OUTPUT_NAMES = ("turn", "throttle")

# Every input is designed to lie in [-1, 1]. Anything outside is clipped, so a sensor bug can
# distort behaviour but can never overflow the arithmetic.
INPUT_LIMIT = 1.0


def parameter_count(n_inputs: int, n_hidden: int, n_outputs: int) -> int:
    """How many numbers describe one brain: two weight matrices and two bias vectors."""
    return n_hidden * n_inputs + n_hidden + n_outputs * n_hidden + n_outputs


PARAMETER_COUNT = parameter_count(N_INPUTS, N_HIDDEN, N_OUTPUTS)  # 62


def _frozen(values: object, shape: tuple[int, ...], name: str) -> FloatArray:
    """A private, read-only float64 copy of ``values``, checked for shape and finiteness.

    The copy matters: a brain must never share an array with its parent or a caller, or a
    later change to one would silently change the other. Read-only makes accidental in-place
    edits raise instead of corrupting a genome.
    """
    array = np.array(values, dtype=np.float64)  # np.array always copies
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains NaN or infinity")
    array.flags.writeable = False
    return array


@dataclass(frozen=True, slots=True)
class Brain:
    """One organism's network: weights and biases of both layers.

    Shapes (``h`` hidden units, ``i`` inputs, ``o`` outputs):

    - ``w_hidden`` (h, i): row k = hidden unit k's weight for each input
    - ``b_hidden`` (h,)
    - ``w_output`` (o, h): row k = output k's weight for each hidden unit
    - ``b_output`` (o,)

    The sizes are taken from ``w_hidden`` and ``w_output``; everything else must match.
    """

    w_hidden: FloatArray
    b_hidden: FloatArray
    w_output: FloatArray
    b_output: FloatArray

    def __post_init__(self) -> None:
        w_hidden = np.asarray(self.w_hidden)
        w_output = np.asarray(self.w_output)
        if w_hidden.ndim != 2 or w_output.ndim != 2:
            raise ValueError("w_hidden and w_output must be 2-D matrices")
        h, i = w_hidden.shape
        o = w_output.shape[0]
        # A frozen dataclass can't assign normally; object.__setattr__ is the documented way
        # to finish construction inside __post_init__.
        object.__setattr__(self, "w_hidden", _frozen(self.w_hidden, (h, i), "w_hidden"))
        object.__setattr__(self, "b_hidden", _frozen(self.b_hidden, (h,), "b_hidden"))
        object.__setattr__(self, "w_output", _frozen(self.w_output, (o, h), "w_output"))
        object.__setattr__(self, "b_output", _frozen(self.b_output, (o,), "b_output"))

    @property
    def shape(self) -> tuple[int, int, int]:
        """(inputs, hidden units, outputs)."""
        h, i = self.w_hidden.shape
        return i, h, self.w_output.shape[0]

    def to_vector(self) -> FloatArray:
        """All parameters as one flat vector, in a fixed order: ``w_hidden`` row by row,
        ``b_hidden``, ``w_output`` row by row, ``b_output``. This vector is the genome."""
        return np.concatenate(
            [self.w_hidden.ravel(), self.b_hidden, self.w_output.ravel(), self.b_output]
        )

    @classmethod
    def from_vector(
        cls,
        vector: Sequence[float] | FloatArray,
        shape: tuple[int, int, int] = (N_INPUTS, N_HIDDEN, N_OUTPUTS),
    ) -> Brain:
        """The inverse of ``to_vector``: cut a flat vector back into matrices."""
        i, h, o = shape
        vector = np.asarray(vector, dtype=np.float64)
        expected = parameter_count(i, h, o)
        if vector.shape != (expected,):
            raise ValueError(f"a {shape} brain needs {expected} parameters, got {vector.shape}")
        cuts = np.cumsum([h * i, h, o * h])
        w_hidden, b_hidden, w_output, b_output = np.split(vector, cuts)
        return cls(w_hidden.reshape(h, i), b_hidden, w_output.reshape(o, h), b_output)

    def forward(self, inputs: Sequence[float] | FloatArray) -> Activations:
        """One forward pass for this brain alone (same arithmetic as the batched version)."""
        x = np.asarray(inputs, dtype=np.float64)[np.newaxis, :]
        return forward(BrainStack.of([self]), x).row(0)


@dataclass(frozen=True, slots=True)
class BrainStack:
    """Many brains of the same shape stacked along a first axis (one row per organism), so
    a whole population's forward pass is a handful of array operations."""

    w_hidden: FloatArray  # (n, h, i)
    b_hidden: FloatArray  # (n, h)
    w_output: FloatArray  # (n, o, h)
    b_output: FloatArray  # (n, o)

    @classmethod
    def of(cls, brains: Sequence[Brain]) -> BrainStack:
        if not brains:
            raise ValueError("cannot stack zero brains")
        shapes = {brain.shape for brain in brains}
        if len(shapes) != 1:
            raise ValueError(f"brains have different shapes: {sorted(shapes)}")
        return cls(
            np.stack([b.w_hidden for b in brains]),
            np.stack([b.b_hidden for b in brains]),
            np.stack([b.w_output for b in brains]),
            np.stack([b.b_output for b in brains]),
        )

    def __len__(self) -> int:
        return len(self.b_hidden)


@dataclass(frozen=True, slots=True)
class Activations:
    """Every intermediate value of a forward pass, kept so it can be inspected.

    For a batch each array has one row per organism; ``row(k)`` gives organism k's values.
    """

    inputs: FloatArray  # after clipping to [-INPUT_LIMIT, INPUT_LIMIT]
    hidden_sum: FloatArray  # weighted sums into the hidden layer, before tanh
    hidden: FloatArray  # tanh(hidden_sum), each in (-1, 1)
    output_sum: FloatArray  # weighted sums into the output layer
    outputs: FloatArray  # column 0: tanh -> (-1, 1); column 1: sigmoid -> (0, 1)

    def row(self, k: int) -> Activations:
        return Activations(
            self.inputs[k], self.hidden_sum[k], self.hidden[k], self.output_sum[k], self.outputs[k]
        )


def sigmoid(z: FloatArray) -> FloatArray:
    """The logistic function 1 / (1 + e^-z), squashing any number into (0, 1).

    Computed as ``0.5 * (1 + tanh(z / 2))``, which is the same function rewritten. The
    textbook form overflows ``e^-z`` for very negative z (a warning, then exactly 0); this
    form never overflows.
    """
    return 0.5 * (1.0 + np.tanh(0.5 * z))


def forward(stack: BrainStack, inputs: FloatArray) -> Activations:
    """The forward pass for n organisms at once: organism k's inputs through brain k.

    ``inputs`` has shape (n, i). Output column 0 uses tanh (a signed value: turn left or
    right), column 1 the sigmoid (a fraction: how much throttle). With two outputs, that
    mapping is fixed here; a different output layout would need its own activations.
    """
    x = np.asarray(inputs, dtype=np.float64)
    n, h, i = stack.w_hidden.shape
    if x.shape != (n, i):
        raise ValueError(f"inputs must have shape ({n}, {i}), got {x.shape}")
    if np.any(np.isnan(x)):
        raise ValueError("inputs contain NaN: a sensor produced an undefined value")
    if stack.w_output.shape[1] != N_OUTPUTS:
        raise ValueError(f"forward() maps exactly {N_OUTPUTS} outputs (turn, throttle)")
    x = np.clip(x, -INPUT_LIMIT, INPUT_LIMIT)

    # Weighted sums. x[:, np.newaxis, :] has shape (n, 1, i); times (n, h, i) weights it
    # broadcasts to (n, h, i): every hidden unit's weights times the same inputs. Summing
    # over the last axis gives (n, h), one weighted sum per hidden unit, plus its bias.
    hidden_sum = (stack.w_hidden * x[:, np.newaxis, :]).sum(axis=-1) + stack.b_hidden
    hidden = np.tanh(hidden_sum)
    output_sum = (stack.w_output * hidden[:, np.newaxis, :]).sum(axis=-1) + stack.b_output
    outputs = np.column_stack([np.tanh(output_sum[:, 0]), sigmoid(output_sum[:, 1])])
    return Activations(x, hidden_sum, hidden, output_sum, outputs)


class BrainStackCache:
    """The living population's ``BrainStack``, kept from tick to tick and patched for births
    and deaths instead of being stacked from scratch every tick.

    Brains never change during a lifetime and the living list only ever loses members (deaths)
    or gains them at its end (newborns, with larger IDs), so last tick's stack can be cut down
    to the survivors and the newborns' brains appended. The arrays hold exactly the values
    ``BrainStack.of`` would build, in the same C-contiguous layout, so the forward pass adds
    the same numbers in the same order and every output is bit-identical (D-036; checked by
    tests/intelligence/test_neural.py against ``BrainStack.of`` and by the golden digests).

    Why: ``np.stack`` over a thousand brains was a quarter of a neural tick (docs/benchmarks.md).
    """

    def __init__(self) -> None:
        self._ids: NDArray[np.int64] = np.empty(0, dtype=np.int64)
        self._brains: list[Brain] = []
        self._stack: BrainStack | None = None

    def of(self, ids: Sequence[int], brains: Sequence[Brain]) -> BrainStack:
        """The stack for organisms ``ids`` (ascending) whose brains are ``brains``."""
        n = len(ids)
        if n == 0 or len(brains) != n:
            raise ValueError("cannot stack zero brains, or a brain count that differs from ids")
        now = np.asarray(ids, dtype=np.int64)
        stack = self._stack
        fresh = None
        if stack is not None and len(self._ids):
            # Survivors: previous IDs still present. Both lists are sorted, so a binary search
            # finds each previous ID's place in the current list.
            at = np.searchsorted(now, self._ids)
            kept = (at < n) & (now[np.minimum(at, n - 1)] == self._ids)
            survivors = int(kept.sum())
            # The survivors must be the first rows of the current list, still carrying the very
            # brain objects stacked before (a Brain is immutable, so identity is enough). Code
            # that swaps a living organism's brain, or a list in another order, gets a stack
            # built afresh rather than stale rows.
            same = all(
                mine is theirs
                for mine, theirs in zip(compress(self._brains, kept), brains, strict=False)
            )
            if same and len(self._brains) == len(kept):
                if survivors == len(self._ids) and survivors == n:
                    return stack  # nobody died, nobody was born
                parts = [
                    np.ascontiguousarray(a[kept])
                    for a in (stack.w_hidden, stack.b_hidden, stack.w_output, stack.b_output)
                ]
                born = brains[survivors:]
                if born:
                    new = BrainStack.of(born)
                    parts = [
                        np.concatenate([old, add])
                        for old, add in zip(
                            parts,
                            (new.w_hidden, new.b_hidden, new.w_output, new.b_output),
                            strict=True,
                        )
                    ]
                fresh = BrainStack(*parts)
        if fresh is None:
            fresh = BrainStack.of(brains)
        self._ids, self._brains, self._stack = now, list(brains), fresh
        return fresh
