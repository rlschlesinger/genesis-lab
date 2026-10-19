# Chunk 04B — Neuroevolution and honest model comparison

Determine whether evolved neural policies outperform transparent alternatives for defined tasks.

## Scope
- Configure inherited fixed-topology neural networks and generational mutation within ecological reproduction. Do not add a second unrelated population genetic algorithm unless justified.
- Compare random, hand-written food-seeking, and neural policies under matched environmental settings; predefine endpoint metrics and independent seeds. Run enough seeds to estimate variability, e.g., 10–20 per group when practical.
- Important: equivalent genotype complexity, computation cost and starting conditions should be discussed as limitations. Report survival/offspring/energy rather than anthropomorphic 'intelligence'.
- Add plots of per-run outcomes and evolution of weights/behavior summaries over time. Train and evaluate on different seed groups (or environmental conditions) to discuss generalization.
- Optional learning task: reimplement one forward pass in PyTorch, show it matches NumPy within numerical tolerance; **do not** introduce GPU or large model training.

## Tests
- Same seeded neural controller has reproducible action outputs; no shape/NaN errors in batch runs; baseline comparisons preserve condition labels and seeds; train/evaluation grouping correctly separated.

## Learning
Explain fitness vs reproductive success, overfitting to environment seeds, selection vs reinforcement learning, and why a neural model may lose to a simple heuristic.

## Acceptance
Comparison report exists with uncertainty and an unembellished conclusion; backward-compatible rule-based runs still work. Stop and point to `05A_API_STREAMING.md`.
