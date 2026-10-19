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

## D-019 · Mutation rule (2026-10-18)

**Decision:** per gene, per birth: mutate with probability `rate`; step ~ Normal(0, `size × range`); reflect at the bounds. Every birth makes the same number of draws from a dedicated `mutation` stream (appended last). Per-gene `mutable` flag. Disabled by default.
**Why:** a normal step with mean 0 has no built-in direction, so trends must come from selection or drift. Scaling to each gene's range makes one `size` meaningful for all genes. **Reflection, not clamping:** clamping parked 13% of 2000 neutral lineages exactly on a bound after 300 generations (demo, 2.2), a fake "selection for extremes"; reflection stayed flat with none on a bound. Constant draws per birth keep the stream independent of outcomes. `mutable` lets experiments isolate one gene.
**Alternatives:** multiplicative/log-scale steps (suits strictly positive traits; consider if small values matter); resampling out-of-range steps (also unbiased, but a variable number of draws).

## D-018 · Genome representation (2026-10-18)

**Decision:** `Genome` is a frozen dataclass with one float per gene, stored in trait units. `express()` maps it to `Traits`. Gene limits come from the config's `genome` section; units and descriptions live in `GENES`. All founders share one genome.
**Why:** rescaling genes to 0–1 and back can change values by one rounding step, which would have changed Milestone 1 results (the golden test would fail). Named fields are clearer to read and inspect than an array. Identical founders mean any variation is attributable to mutation.
**Alternatives:** 0–1 normalized genes (uniform mutation scale; rounding problem); a NumPy array (faster en masse, less readable); initial standing variation (a possible config option later).
**Consequence:** the config's `organisms.traits` section was replaced by `genome`. Configs from Milestone 1 need migrating; behaviour is unchanged (verified by tests/test_regression.py).

## D-017 · No performance optimization in Milestone 1 (2026-10-18)

**Decision:** keep the all-pairs distance calculations in sensing and feeding.
**Why:** measured, not guessed (docs/benchmarks.md). A default run takes ~1 s; 1000 organisms runs at 140 ticks/s. The profile shows the two n × m distance computations take ~75% of the time at N = 1000, so that's where a future fix would go.
**Revisit when:** an experiment needs populations of 1000+, or batch sizes make run time a bottleneck. Planned fix: a spatial index.

## D-015 · Run output format for Milestone 1 (2026-10-18)

**Decision:** each run writes `run.json` + `ticks.csv` + `organisms.csv`, using only the standard library. run.json carries status (running → completed / failed) and provenance (git commit + dirty flag, versions, platform, full config). Files are written atomically (temp file + rename).
**Why:** human-readable, needs no new dependencies, and enough for Milestone 1's question. Writing status first means crashed runs leave evidence.
**Alternatives:** Parquet + DuckDB (planned for Milestone 3, once there are many runs to query); SQLite.
**Revisit at:** Milestone 3.

## D-016 · Founder lineage tracking (2026-10-18)

**Decision:** every organism carries `founder_id`; the `lineages` metric counts distinct founder lineages alive.
**Why:** spec section 9 asks for lineage diversity indicators. Measured before mutation exists, it gives the size of pure-chance drift, which Milestone 2 must distinguish from selection.

## D-014 · Reproduction details (2026-10-18)

**Decision:** one child per parent per tick; random parent choice when the population cap binds; offspring placed uniformly within one step (`speed`) of the parent.
**Why:** the list is in ID order, so "first come first served" at the cap would always favour the oldest lineages, a hidden selection pressure that would distort Milestone 2. Uniform-in-disc placement (via a square root on the radius) avoids clustering births at the parent's exact position.
**Alternatives at the cap:** highest energy first (a deliberate selection rule; could be an experimental condition later).

## D-013 · Feeding rules (2026-10-18)

**Decision:** one meal per organism per tick; in-reach pairs resolved closest-first with random tie-breaking; eating happens before costs are paid.
**Why:** one meal per tick bounds the rate of energy intake. Closest-pair matching implements "closest wins" while still feeding every organism it can. Eating first means an organism that reaches food doesn't die from a cost paid an instant earlier.
**Alternatives:** split contested food between contenders (no winner, but fractional food complicates the ledger); an optimal assignment to maximize meals eaten (harder to explain, and no biological reason).
**Observed consequence (seed 42, no reproduction yet):** energy accumulates without bound (mean ~5000 EU by tick 5000 for seekers). Expected to be absorbed by reproduction in 1.7. If it isn't, consider a maximum energy trait.
**Update (1.7):** confirmed resolved. With reproduction, mean energy settles around 35 EU (seed 42, both controllers).

## D-012 · A fifth RNG stream for setup; streams are append-only (2026-10-18)

**Decision:** founder placement gets its own `setup` stream. Streams are spawned in a fixed order, and a new one is only ever added at the end.
**Why:** borrowing another stream for founder placement would shift that stream's sequence. `SeedSequence.spawn` hands out child seeds in order, so inserting a stream in the middle would silently change every stream after it, and with it every result from earlier software versions.

## D-011 · Energy left at death leaves the system (2026-10-18)

**Decision:** energy an organism still holds when it dies (e.g. of old age) is removed and recorded in the energy ledger as "lost at death".
**Why:** the simplest choice that keeps accounting exact.
**Alternatives:** convert it into food at the death location (a "carcass": recycles energy, enables scavenging); share it among nearby organisms.
**Revisit:** a carcass option makes a good Milestone 6 ecology experiment.
