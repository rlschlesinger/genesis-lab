# Decision log

Each entry records a decision, why it was made, and what would make us revisit it.

## D-001 · Use uv for Python and dependency management (2026-10-18)

**Decision:** uv manages the Python version, virtual environment and lockfile (`uv.lock`).
**Why:** one tool, fast, produces a cross-platform lockfile for reproducibility.
**Alternatives:** pip + venv + pip-tools (more pieces), Poetry (slower, separate Python management), conda (heavier).
**Revisit if:** a required package is only distributed via conda.

## D-002 · Defer Mesa; write our own simulation loop (2026-10-18)

**Decision:** Milestone 1 does not use Mesa.
**Why:** Mesa's model is agents that act one at a time in a shuffled order. Our spec requires snapshot observation and simultaneous resolution, which would work against that. Mesa's main extras (Solara visualization, batch runner) overlap with our planned React UI and experiment tooling. Writing the loop is also more instructive.
**Revisit at:** Milestone 3, when building batch experiments.

## D-003 · Exact-copy reproduction in Milestone 1 (2026-10-18)

**Decision:** organisms reproduce by cloning their `Traits` exactly; mutation arrives in Milestone 2.
**Why:** without reproduction the population can only decline, which leaves the ecosystem untested. Cloning lets us check ecological dynamics (for example, does population settle near what the food supply can sustain?) before evolution adds variation.

## D-004 · Hard-wall boundaries (2026-10-18)

**Decision:** the world is bounded; positions are clamped to the edges.
**Why:** matches the spec ("bounded"). Wrap-around (torus) can be added later as a config option if edge effects become a confound.

## D-005 · Food contention rule (2026-10-18)

**Decision:** if several organisms can eat the same food in one tick, the closest wins; exact ties are broken by a dedicated seeded RNG stream.
**Why:** breaking ties by organism ID would systematically favour older lineages and bias evolution.

## D-006 · Independent RNG streams per subsystem (2026-10-18)

**Decision:** one run seed → `SeedSequence.spawn` → separate generators for food, controllers, reproduction and tie-breaking.
**Why:** keeps subsystems from shifting each other's random sequences, so paired-seed experiments stay comparable as code changes.
**Limit:** bit-identical results are guaranteed only within the same machine, OS and package versions.
