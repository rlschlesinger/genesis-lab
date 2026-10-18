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

## D-007 · YAML files validated by Pydantic (2026-10-18)

**Decision:** configs are YAML, read with `yaml.safe_load`, validated into frozen Pydantic models that forbid unknown keys.
**Why:** a typo or impossible value should stop a run before it starts, with an error naming the field. Frozen configs can't drift mid-run.
**Alternatives:** TOML via the standard library's `tomllib` (no dependency, but the spec names YAML); dataclasses with hand-written checks; `msgspec`.

## D-008 · Reproduction energy split (2026-10-18)

**Decision:** reproducing costs the parent `offspring_energy + reproduction_overhead`; the child receives `offspring_energy`; the overhead is lost.
**Why:** makes reproduction costly (as the spec requires) while keeping the energy ledger explicit. A config is rejected if reproducing could drive the parent to zero.

## D-009 · Poisson food regrowth (2026-10-18)

**Decision:** new food per tick ~ Poisson(`regrowth_per_tick`), capped at `max_count`, at uniformly random positions.
**Why:** the standard model for independent events at a constant average rate; supports fractional rates (0.3/tick) naturally.
**Alternatives:** a deterministic accumulator (adds exactly 0.3 per tick, spawns when it passes 1). It's less noisy, but its regular timing could become an artefact organisms exploit. We could revisit it as a config option.
**Note:** the Poisson draw happens even when food is at the cap, so the food stream's sequence doesn't depend on how much was eaten.

## D-010 · Food stored as a NumPy array, not objects (2026-10-18)

**Decision:** `FoodSupply` holds an `(n, 2)` float64 array.
**Why:** food has no state beyond its position, and sensing needs distances to all food every tick, which is a single vectorized operation on an array.
**Revisit if:** food gains per-item state (e.g. varying energy, decay). Then add parallel arrays first, and objects only if needed.

## D-011 · Energy left at death leaves the system (2026-10-18)

**Decision:** energy an organism still holds when it dies (e.g. of old age) is removed and recorded in the energy ledger as "lost at death".
**Why:** the simplest choice that keeps accounting exact.
**Alternatives:** convert it into food at the death location (a "carcass": recycles energy, enables scavenging); share it among nearby organisms.
**Revisit:** a carcass option makes a good Milestone 6 ecology experiment.
