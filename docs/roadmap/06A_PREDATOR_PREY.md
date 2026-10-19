# Chunk 06A — Ecological extension: predator and prey

Introduce the first complex ecosystem pressure using the scientific method, not a pile of new features.

## Scope
- Create predator agent type with documented hunger/energy, movement, sensing, prey contact/capture, energy transfer, reproduction and mortality. Explain how it interacts with existing tick sequence, collision rules, and costs; record ADR for any new phases.
- Ensure prey have a meaningful sensory signal or behavioral option for evasion and that costs/tradeoffs are modeled. Do not bake in 'arms race' outcomes.
- Add predator and prey counts, capture attempts/successes, extinction rates, and trait distributions to persistence and charts, with versioned schema changes.
- Write a preregistered experiment: predator-present vs predator-absent worlds, with matched configurations/seeds, predeclared prey sensing or survival metric, 10–20 independent runs per condition when practical.
- Produce graphs and honest explanation of observed differences with effect sizes and uncertainty; discuss that the toy model is not real ecology.

## Tests
- One predator cannot consume one prey twice; energy transferred according to specification; no prey acts after death; deterministic contested captures; no crashes when either species extinct; saved-run schema compatibility; replay reproducible.

## Learning
Explain ecological feedback, selection pressure, coevolution, and how a designed fleeing rule differs from evolved avoidance.

## Acceptance
Predator-prey simulation and replication analysis work with prior headless/UI commands. Stop and point to `06B_ONE_ADVANCED_EXTENSION.md`.
