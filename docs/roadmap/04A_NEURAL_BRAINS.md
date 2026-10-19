# Chunk 04A — Small neural brains from first principles

Introduce machine learning without replacing transparent scientific modeling with an opaque library call.

## Scope
- Implement a fixed-topology feedforward neural policy in NumPy (recommended 8 inputs, 1 hidden layer, 3 outputs), with explicitly documented sensor vector and output semantics. Include food-relative wrapped direction, distance, energy level, heading and a fixed bias as applicable.
- Normalize inputs; use stable activations (e.g., tanh, sigmoid); map outputs to bounded turn, throttle, and forage. Specify exactly what the forage output means, its energy cost, and contention rules; if a third action complicates ecosystem semantics, document a simpler 2-output alternative via ADR.
- Encode all weights/biases as inheritable genome parameters with validated shapes, finite values, deterministic seeded initialization, and bounded Gaussian mutation. Use no gradient descent at this stage.
- Add an organism inspector in CLI showing input vector, hidden activations, output vector, chosen action, and resulting state for one tick.

## Tests
- Correct matrix shapes and parameter count; hand-computed tiny forward-pass example; finite/clamped outputs for extreme input; reproducible initialization and inference; mutation behavior and no shared mutable parameters; newborns inherit neural policy.

## Learning
Explain vectors/matrices, weighted sums, activation functions, genotype-to-controller mapping, and why evolutionary selection differs from backpropagation.

## Acceptance
A neural organism can live in the existing deterministic engine; small worked numerical example is verifiable by hand. Stop and point to `04B_NEUROEVOLUTION_COMPARISON.md`.
