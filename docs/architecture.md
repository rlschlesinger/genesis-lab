# Architecture

Status: **Milestones 1–5 complete** (2026-10-20). **Milestone 6 approved 2026-10-20** for chunk 06A (predator and prey; plan below); chunk 06B (one research extension) needs its own go-ahead. Scope in [roadmap/](roadmap/README.md). Schema in [schema.md](schema.md), columns in [data-dictionary.md](data-dictionary.md).

## Component map

```text
configs/default.yaml ──► core/config.py (Pydantic) ──► SimulationConfig
                                                            │
cli.py ──► core/simulation.py ──owns──► World       (core/world.py: bounds, food positions)
                │                 ├──► Organisms   (core/organism.py: state, Genome, Traits)
                │                 └──► RNG streams {setup, food, controller, reproduction, tiebreak, mutation, brain}
                │
           tick():
             1 world.regrow_food(rng.food)
             2 observations = sense(snapshot)          every organism sees the same frozen world
             3 actions = controller.decide(obs, rng.controller)
               (neural: obs + body senses + the living organisms' brains → think(), D-042)
             4 apply movement, clamp to walls
             5 eat (closest pairs first, rng.tiebreak), then pay energy costs; ledger records flows
             6 process deaths
             7 reproduction: eligible survivors have one child (mutated genome); newborns act next tick
             8 ledger.check(stock); metrics.record(state)  read-only
             9 tick += 1
```

## Responsibilities

| Module | Owns | Must not |
|---|---|---|
| `core/config.py` | Validated, immutable configuration | Contain simulation logic |
| `core/world.py` | Bounds, wall clamping; owns the `FoodSupply` | Know about controllers |
| `core/resources.py` | Food positions `(n, 2)`, Poisson regrowth, removal | Create its own RNG |
| `core/organism.py` | Per-organism state, `Traits`, energy bookkeeping, death rules | Draw random numbers, sense, or move itself |
| `intelligence/sensors.py` | World snapshot → `Observations` (nearest food in range) | Mutate anything |
| `intelligence/neural.py` | `Brain` (weights and biases, flat-vector layout), `BrainStack`, `forward()` → `Activations` (D-039) | Know about organisms or the world; use any other summation method |
| `intelligence/brain_inputs.py` | `INPUT_NAMES`, `wall_distance_ahead`, `brain_inputs` → the (n, 7) input matrix (D-040) | Draw random numbers (noise is passed in) |
| `intelligence/controllers.py` | `Observations` → `Actions` (pure); `NeuralController.think` also returns inputs and activations (D-042) | Mutate world state |
| `core/movement.py` | Apply `Actions` within trait limits; walls; distance moved | Decide anything |
| `core/geometry.py` | `wrap_angle` | |
| `core/spatial.py` | Which food is within reach of which organism: all-pairs for small populations, a grid of cells for large ones, identical results (D-036) | Decide anything; change a single bit of a distance |
| `core/costs.py` | Per-tick living costs: metabolism, sensing, movement with drag | Touch organisms |
| `core/feeding.py` | Who eats what: closest-pair matching, random tie-break | Change energy itself |
| `core/energy.py` | `EnergyLedger`: flows and the per-tick conservation check | |
| `evolution/genome.py` | `GENES` (units, descriptions), `Genome` (genotype), `express()` → `Traits` (phenotype) | Import config at runtime from organism.py |
| `evolution/mutation.py` | `mutate()` → child genome + `GeneChange` list; `reflect()` at bounds | Modify the parent genome |
| `evolution/brain.py` | `founder_brains` (one random brain per founder), `mutate_brain`, `reflect_array` (D-041) | Modify a parent's brain; use any stream but `brain` |
| `evolution/reproduction.py` | Who reproduces (random at the cap) and where offspring appear | Touch organisms |
| `core/simulation.py` | Tick order, RNG streams, founders, deaths, `TickSummary`, `state_digest`; predators beside the prey (`sim.predators`, `PredatorStreams`, `PredatorSummary`, D-057) | Do I/O |
| `core/predation.py` | `resolve_strikes`: which predator strikes which prey, and whether it catches it (D-058) | Change organisms |
| `analytics/metrics.py` | Flat rows: `tick_row`, `organism_rows`; column lists | Mutate state |
| `analytics/storage.py` | Byte-stable CSV/JSON writers, atomic replace | Know about simulations |
| `analytics/provenance.py` | Git commit/dirty flag, versions, platform | |
| `analytics/behaviour.py` | `behaviour_row`: turning toward food, turn, throttle, brain spread and drift per recorded tick (D-043) | Change the simulation |
| `analytics/inspector.py` | `genesis inspect`: `replay_to`, `inspect_tick`, `inspect_run_folder`, `format_inspection` (D-044) | Change a recorded run |
| `analytics/recorder.py` | `RunRecorder.observe(sim, summary)` after each tick: tick rows, gene stats, genome snapshots | Change the simulation |
| `analytics/significance.py` | Sign test, paired and two-group permutation tests (exact or seeded sampling), Holm correction | Use per-organism data as replicates |
| `analytics/experiments.py` | Conditions (dotted config changes), `run_condition`, `settled_gene_means`, `paired`, `genomes_never_changed` | Decide hypotheses |
| `analytics/spec.py` | `ExperimentSpec` (experiments/specs/*.yaml): base config, conditions, seeds; validates every run's config on load | Run anything |
| `analytics/batch.py` | `plan`, `task_status` (missing/completed/stale/incomplete), `run_experiment` (process pool, resume, ingest) | |
| `analytics/analysis.py` | `query_df`, `settled_gene_means_df`, `describe(_by)`, `bootstrap_ci`, `wilson_interval`, `paired_effect`, `practical_significance` | Treat organisms as replicates |
| `analytics/runs.py` | `execute_run`: simulate + write run.json/ticks.csv/organisms.csv with status | |
| `report/dashboard*.py` | `genesis dashboard EXP`: `dashboard_data.py` (SQL loaders), `dashboard_figures.py` (runs vs summaries), `dashboard.py` + template | Read run folders |
| `report/` | `genesis report`: `data.py` (load run folder, downsample), `theme.py` (design tokens), `figures.py` (charts), `render.py` + `template.html` + `report.css` | Run simulations; read anything outside the run folder |
| `lake/` | ETL: `tables.py` (data dictionary as Arrow schemas), `ingest.py` (extract, transform, load), `validate.py` (the five checks) | Modify run folders |
| `lake/export.py` | `export_experiment` (tables + README + manifest), `export_query`, `verify_export` | |
| `lake/db.py` | `connect()`: in-memory DuckDB with a view per lake table, derived views, `settled_gene_means` macro, `experiments` from docs; `rebuild_db()` | Store data |
| `api/schemas.py` | The API contract: request/response models, `RunState`, `API_VERSION` (D-047) | Contain logic |
| `api/runs.py` | `RunManager`, `LiveRun`, the allowed state transitions (`ALLOWED`), config loading by name | Know about HTTP |
| `api/history.py` | `RunHistory`: one row per tick, `query(since, every)` with flows summed, stocks at the end, shares averaged (D-054) | Change the simulation |
| `api/lake.py` | `LakeReader`: experiments, runs, a run's config and series from the lake (one locked connection) (D-055) | Write to the lake |
| `api/lineage.py` | `lineage()`: ancestors, descendants cut to depth and breadth, family counts (D-055) | Change the simulation |
| `api/stepping.py` | `step` (also in slices, yielding between them), `resume` (cancels a superseded loop), `pause`, `stop`, the background `run_loop` (slices, tick budget) (D-048 and its amendment) | Choose which tick comes next (only how many) |
| `api/stream.py` | WebSocket snapshots: `hello`/`snapshot`/`gone`, `build_snapshot` (columnar, rounded), per-viewer sender and listener (D-049) | Queue messages; send exact state |
| `api/details.py` | `organism_detail`, `thought` from the latest decision record, `deciders` (D-050) | Recompute a decision |
| `api/saved.py` | `saved_runs` (folders on disk), `export_run` (replay to a run folder, digest check, ingest) (D-050) | Accept paths from clients |
| `api/app.py` | FastAPI routes over a `RunManager`; errors → status codes | Contain simulation logic |
| `cli.py` | `genesis run` arguments → `execute_run`; exit codes 0/1/2 | Contain logic |

The API (Milestone 5) will drive the same `Simulation` object as the CLI.

## Browser lab (`web/`, Milestone 5)

A separate TypeScript project that only views and requests; the Python API is the authority (D-047, D-051). Design system: [ui-design.md](ui-design.md).

| Folder | Owns | Must not |
|---|---|---|
| `src/api/` | `types.ts` (docs/API.md as types), `client.ts` (one function per route, `ApiError`), `parse.ts` (runtime checks on stream messages), `__fixtures__/` (real server output, generated) | Hold state |
| `src/stream/` | `connection.ts` (`StreamConnection`: one subscription, reconnection rules; no React), `useRunStream.ts` (starts/stops it) | Touch the DOM |
| `src/world/` | `camera.ts` (world↔screen, zoom about a point, clamping), `interpolate.ts` (gliding), `hitTest.ts` (click and keyboard selection), `trails.ts`, `renderer.ts` (PixiJS: the only GPU code), `usePlateInput.ts` (pointer, wheel, keys) (D-052) | Reach the server |
| `src/store/` | `labStore.ts`: the one Zustand store (view, watched run, latest snapshot, status, selection) | Send anything to the server |
| `src/data/` | Labels, copy and small pure rules: `views.ts`, `status.ts`, `controls.ts` (which controls each state allows; the speed scale), `brain.ts` (the brain view's encodings) | Touch state or the network |
| `src/hooks/` | `useRunActions` (controls with pending/error/result), `useOrganismDetail` (throttled, stale-safe), `useServerLists` (configs, live runs), `useRunHistory` (polls `/history`) | Render anything |
| `src/compare/` | `diff.ts` (config differences by dotted path), `align.ts` (two runs on one tick axis) (D-055) | Fetch or render |
| `src/analytics/` | `series.ts`: point sizes, merging new points, the next request (D-054) | Fetch or render |
| `src/components/` | Small components, one CSS module each | Fetch or open sockets directly |
| `src/styles/` | `tokens.css` (every colour, size, radius), `base.css` | |

```bash
cd web && npm ci          # install exactly what package-lock.json says
npm run dev               # http://127.0.0.1:5173 (needs `uv run genesis serve` for /api)
npm test                  # Vitest
npm run typecheck         # TypeScript, including the contract tests' compile-time checks
npm run build             # production build in web/dist
```

## Configuration

`load_config(path)` → `SimulationConfig` with sections `run`, `world`, `food`, `organisms`, `genome`, `mutation`, `recording` (optional, defaults) and `brain` (optional; required by `controller: neural`, omitted from the dump when absent so older config hashes are unchanged). Models forbid unknown keys and are frozen. Cross-field rules:

- `food.initial_count <= food.max_count`
- `organisms.initial_count <= organisms.max_population`
- `genome.reproduction_threshold.min > offspring_energy + reproduction_overhead` (the whole range, since mutation can reach its minimum)
- each gene: `min < max`, `min <= initial <= max`; speed and sense_range min > 0; max_turn within (0, pi]

Reproduction energy model: the parent pays `offspring_energy + reproduction_overhead`; the child starts with `offspring_energy`; the overhead leaves the system (recorded as outflow in the energy ledger).

## World and food

- Coordinates: origin bottom-left; valid positions `[0, width] x [0, height]`; `World.clamp` enforces hard walls and returns a new array.
- Food is one `(n, 2)` float64 array, not objects. Row index is the only identity and is valid until the supply next changes.
- `FoodSupply.positions` is a read-only view; only `spawn` / `remove` mutate food.
- Each tick, `regrow` draws a Poisson count (mean `regrowth_per_tick`), then spawns up to the cap. The draw happens even at the cap, so random draws per tick don't depend on world state.
- `remove` rejects duplicate or out-of-range indices: one item can never feed two organisms.

## Organisms

- `Genome` (genotype): frozen dataclass of six genes in trait units, inherited. `Traits` (phenotype) = `express(genome)`, computed once at birth. The `neutral_marker` gene is inherited but not expressed.
- Founders all share the configured initial genome; variation can only come from mutation.
- `Organism`: mutable dataclass with `slots=True, kw_only=True`. Identity/lineage fields are set at birth; physical state (`x`, `y`, `heading`, `energy`) is changed by the simulation.
- **Time:** a *tick* is one step of simulated time, during which the 9-step sequence runs once for every organism. `age` counts ticks survived.
- `spend(amount)` never takes energy below zero and returns the amount actually deducted (the ledger records that, not the amount requested).
- **Zero energy does not kill on the spot.** `cause_of_death(max_age)` is a side-effect-free query; `die(tick, cause)` is applied in tick step 6 for all organisms together. Starvation takes precedence over old age.
- Dead organisms raise `RuntimeError` on any action, so a tick-loop bug that keeps processing them fails loudly.
- Energy still held by an organism when it dies (e.g. old age) is removed from the living system by the simulation and logged in the ledger (1.6).

## Sensing, deciding, moving

```text
sense_food(positions, headings, sense_ranges, energies, food)  -> Observations
controller.decide(observations, rng)                           -> Actions (requests)
move(positions, headings, actions, speeds, max_turns, world)   -> new positions, headings, distances
```

- **Angles:** radians; heading 0 = +x, counter-clockwise positive; always wrapped to `[-pi, pi)`. **Bearing** = turn needed to face the food (positive = left).
- **Sensing** asks `core/spatial.py` for each organism's nearest food within its own `sense_range`. Below ~4,000 organism × food pairs that is one `(n, m)` distance table via broadcasting; above it, a grid of cells (side = the longest sense range) so each organism only measures food in its own cell and the ring around it. The grid only proposes candidates; the distances and the `<=` test are the same operations, so the answer is identical bit for bit (D-036). Food beyond an organism's own `sense_range` is invisible. Equidistant food: lowest index wins.
- **Actions are requests:** `turn` is clipped to `+/- max_turn`, `throttle` to `[0, 1]`. Non-finite actions raise.
- **Move order:** turn, step along the new heading, clamp to walls. `distances` is measured after clamping, and movement cost (1.6) is charged on it.
- **Baselines:** `RandomWalk` (normal turns, sd 0.3 rad, full speed) and `NearestFoodSeeker` (turn toward nearest sensed food, otherwise identical to `RandomWalk`, with the same random draws). The only difference between them is the response to sensed food.
- **Turning circle:** minimum radius = `speed / max_turn` (3 units by default). A full-speed organism cannot stop on a target; it overshoots and loops. On a head-on approach, steps of `speed` always land within `speed / 2` of the food, so `eat_radius >= speed / 2` guarantees a head-on approach can eat (default 2.0 vs 0.75).

## Simulation loop

- `Simulation(config)` builds streams, world, controller and founders (ids `0..n-1`, generation 0).
- `step()` runs one tick and returns a `TickSummary` (tick, population, births, deaths, food_count, food_spawned, food_eaten, mean_energy, lineages, mutations). Population and energy are end-of-tick values; `mean_energy` is NaN for an empty population.
- `run()` steps until `max_ticks`, or extinction if `stop_on_extinction` (with predators: only when both species are gone).
- Predators (6.1, D-057): a second list, `sim.predators` (dead ones in `sim.dead_predators`), founders numbered after the prey founders. Each tick they take their snapshot with the prey's, then decide, move, pay their own costs, die and reproduce beside the prey (their newborns after the prey's, so IDs stay ascending). Their numbers are in `sim.predator_summary`, not `TickSummary`. They never eat food: they catch prey (below, "Capture").
- Living organisms stay in ascending id order; dead organisms move to `sim.dead` and keep their records.
- Snapshot: all per-organism arrays are built once at the start of the tick, before anyone moves. From then on the tick works on arrays (costs via `costs.living_costs`, payments via `organism.spend_all`, deaths and reproduction eligibility as array comparisons) and writes results back to the organisms; the `Organism` objects remain the only lasting state, so code and tests may still set `org.x` or `org.energy` directly (D-038).
- Survivors' `age` increments at step 9, so a death check in step 6 sees the age *before* this tick's increment.
- `state_digest()`: SHA-256 over tick, food positions, and every organism's id/x/y/heading/energy/age/alive and genes, plus its 62 brain weights when it has a brain. Equal digests mean bit-identical state. Digests are comparable only within one platform (CPU, OS, NumPy build): the last bits of `hypot`/`arctan2` results differ between platforms (D-027).

## Eating and energy accounting

- **Reach:** food within `eat_radius` of an organism's *post-move* position.
- **One meal per organism per tick; each item eaten once.**
- **Closest pairs first:** all in-reach pairs (from `core/spatial.py`, ordered by organism then food index, as `np.nonzero` orders them) sorted by distance (ties: random key from the tiebreak stream); a pair eats if neither side is taken. Each item goes to the closest organism still competing for it.
- **Eat, then pay costs** (metabolism, movement), so a nearly-empty organism that reaches food survives.
- **Ledger:** stock = energy in living organisms + `food.count * energy_value`.
  - In: food spawned after the start.
  - Out: metabolism, sensing, movement, energy held at death, reproduction overhead.
  - Transfers: eating.
  - `step()` raises `EnergyLedgerError` if `initial + in - out` differs from the actual stock (tolerance: relative 1e-9, absolute 1e-6 EU).
- **Feedback:** spawning is blocked at `max_count`, so inflow depends on how much the population eats.

## Senses with predators (6.3, D-059)

- **Predators** sense the nearest prey within their sense range exactly as prey sense food (`sense_food` with prey positions from the start-of-tick snapshot). So `nearest_prey_seeker` is the food seeker's rule unchanged, and a neural predator's seven inputs are the prey's seven with "food" meaning prey. Predator controllers: `random_walk`, `nearest_prey_seeker`, `neural` (with `predators.brain`, brains from the predators' `brain` stream).
- **Prey with brains** in a world with predators get three more inputs about the nearest predator (`sense_threats`): seen, side (sin of the bearing), closeness. 10 inputs, 80 parameters. Rule-based prey are told nothing about predators.
- **The brain size follows the config, not the population:** a `predators:` section with `initial_count: 0` gives prey the same 10-input brains, drawn identically on the same seed, with the predator inputs always 0. That world is E008's matched control.
- `sim.last_predator_decision` holds the predators' observations, actions and (neural) thought, as `sim.last_decision` does for prey.

## Capture (predators, 6.2, D-058)

- **When:** right after the prey eat (step 5), before anyone pays costs, using everyone's post-move positions.
- **Reach and matching:** exactly the meal rule with predators as eaters and prey as food (`core/predation.py` calls `resolve_feeding`): each predator strikes at most one prey, each prey is struck at most once, closest pairs first, exact ties by a random key from the predators' `capture` stream.
- **Success:** each strike catches with probability `capture_probability` (one draw per strike, same stream); an escaped prey isn't struck again that tick.
- **Energy:** the predator gains `capture_efficiency` × the prey's energy (this tick's meal included) before paying its own costs; the rest leaves through the ledger's `predation` flow. Stock now counts predators too.
- **A caught prey is finished:** it dies at once (`predation`), pays no costs, can't reproduce, doesn't age, and counts in the tick's `deaths`.

## Reproduction

- **Eligible:** survivors of this tick's deaths with `energy >= traits.reproduction_threshold`. At most one child per parent per tick.
- **Cap:** room = `max_population - survivors`. If more are eligible than there is room for, parents are chosen uniformly at random from the reproduction stream (never by ID).
- **Cost:** the parent pays `offspring_energy + reproduction_overhead`; the child starts with `offspring_energy`; the overhead is a ledger outflow. Recorded on the parent as `energy_invested` (separate from `energy_spent`, which is living costs only).
- **Child:** genome = `mutate(parent.genome)` (an exact copy when mutation is off; see Mutation), traits = `express(genome, config)`, `generation = parent + 1`, `birth_tick = current tick`, placed uniformly in a disc of radius `parent.traits.speed` around the parent (clamped), random heading.
- **Timing:** newborns are appended after survivors (IDs stay ascending), are not aged at step 9, and first act on tick `birth_tick + 1`. Founders act from tick 0. With `max_age = A`, everyone gets exactly `A` active ticks.

## Run output

```text
<out>/run.json       run_id, experiment_id, status (running→completed|failed), seed, full config,
                     git {commit, dirty}, environment, ticks_run, stop_reason, final_state_digest
<out>/ticks.csv      one row per TickSummary (tick, population, births, deaths, food_count,
                     food_spawned, food_eaten, mean_energy, lineages, mutations)
<out>/organisms.csv  one row per organism ever: lineage, birth/death, lifetime totals, gene_* and trait_* columns
<out>/mutations.csv  one row per gene change at a birth (header only when mutation is off)
<out>/gene_stats.csv one row per (tick, gene): n, mean, sd (population), min, max; tidy format
<out>/genomes.csv    every living genome every recording.genome_snapshot_every ticks (default 50) + final tick
<out>/events.csv     optional births/deaths/meals (recording.events); header only by default
<out>/behaviour.csv  one row per recorded tick: n, seeing_food, toward_food, mean_turn, mean_throttle,
                     weight_sd, weight_drift (brain columns empty without brains; D-043)
<out>/brains.csv     one row per organism with a brain: its 62 weights by name (header only without brains)
```

- Default `<out>` is `data/runs/<run_id>`; run IDs look like `20261018T235501Z-s42-a1b2c3`.
- `run.json` is written before simulating and rewritten at the end; a failed run records `failed_at_tick` and `error` and writes no CSVs.
- CSVs use fixed columns, `\n` line endings, shortest exact float form, so identical runs give byte-identical files. Only `VOLATILE_FIELDS` (run_id, timestamps, duration) differ in run.json.
- Existing non-empty output directories are refused unless `--overwrite`.
- **Retention:** every tick, organism and mutation; per-tick gene statistics; full genomes sampled every 50 ticks. A 20,000-tick evolution run is ~16 MB (gene_stats.csv 10 MB). No meal/death event logs.
- Recording policy lives in `RunRecorder` (analytics), not the simulation; tests confirm recording never changes results.
- `recording.ticks_every` samples ticks.csv and gene_stats.csv; flow columns are summed between rows (D-028). The simulation always fills `events_this_tick`; the recorder keeps the kinds listed in `recording.events`.
- run.json (schema version 4 since Milestone 4; 3 added these fields) also records `condition`, `schema_version`, `config_hash` (SHA-256 of the canonical config, seed included), `ticks_every`, `events_recorded`; `ticks_run` counts ticks simulated, not rows written.
- **Lineage:** `founder_id` is inherited; `lineages` counts distinct founder IDs alive.

## Mutation

- Config: `mutation: {enabled, rate, size}`; each gene also has `mutable` (default true). Off by default.
- Per birth, per gene: mutate if `uniform < rate` and the gene is mutable; step ~ Normal(0, `size × (max − min)`); result reflected into `[min, max]`.
- Two vectorized draws per birth (6 uniforms, 6 normals) whatever the outcome; none at all when disabled.
- Returns the child genome and a `GeneChange(gene, before, after)` for each changed gene. The parent's genome is never modified.
- **Inheritance (step 7):** child genome = `mutate(parent.genome)`, traits = `express(genome)` (the parent's traits are reused when nothing changed). Each change is appended to `sim.mutation_log` as a `MutationEvent(tick, parent_id, child_id, gene, before, after)`.
- **Lineage integrity** (tested over every organism in a run): genome = parent's genome + exactly the logged changes.

## Trade-offs (core/costs.py)

| Gene | Cost per tick | Config |
|---|---|---|
| metabolic_rate | `metabolic_rate` (no trade-off: positive control) | — |
| sense_range | `sense_cost_per_unit × sense_range` | `organisms.sense_cost_per_unit` (default 0) |
| speed | `move_cost_per_distance × distance × (speed / founder speed) ^ speed_cost_exponent` | `organisms.speed_cost_exponent` (default 0) |
| max_turn | none, so frozen in `evolution.yaml` | `genome.max_turn.mutable` |

Any gene can be made `neutral: true`: still inherited and mutating, but expressed at its initial value. That's the drift-only "neutral twin" used as the control in E002/E003.
| neutral_marker | none, and not expressed | — |

Founders pay exactly the Milestone 1 movement price at any exponent. Defaults reproduce Milestone 1 bit for bit. `configs/evolution.yaml` = `default.yaml` + mutation on, drag exponent 1, sense cost 0.004, max_turn frozen, 20000 ticks (a test enforces that nothing else differs).

## Reports (`genesis report <run_dir>`)

- Reads only the run folder's files; bounds and settings come from the recorded `run.json`, not `configs/`.
- Sections: population/food/lineages; per-gene mean ± sd over each gene's full range with the founder value; distribution heatmaps from `genomes.csv` (mutable genes only); a mutation table.
- At most 2000 points per line (a fixed stride, always keeping the last tick); the CSVs keep everything.
- Self-contained and offline: Plotly embedded once, system fonts, no external links. Deterministic: fixed chart `div_id`s give byte-identical output.
- Refuses runs whose status isn't `completed`.

## Data lake (`genesis lake ingest PATH...`)

- Reads run folders (any schema version), converts each CSV to its table's exact Arrow schema, validates, and writes `data/lake/<table>/<run_id>.parquet` (zstd). Run folders are never modified.
- Checks (refuse the whole run, naming the check): primary keys, foreign keys, row counts (incl. events vs flow totals), ranges, types.
- Failed runs: a `runs` row only. Version 1–2 runs: `condition` derived from the folder name, `config_hash` computed from the stored config; missing columns are NULL.
- Re-ingesting replaces a run's files (all written to `.tmp` first, then renamed).
- Back-fill 2026-10-19: 165 runs, 25.2 M rows, 206 MB (from ~1.94 GB of CSV), 8.7 s.
- **SQL** (`genesis sql "..."`, or `genesis.lake.db.connect()` in Python): views read `data/lake/<table>/*.parquet` directly and are created on every connect (instant, always current). A table with no files yet gets a typed empty view. `genesis lake rebuild-db` writes the same views to `data/genesis.duckdb` (absolute paths) for other tools. Examples: [sql-examples.md](sql-examples.md), each executed by the tests. Exercises: [sql-exercises.md](sql-exercises.md), generated by `scripts/build_sql_exercises.py`; tests check every answer is valid SQL and, where the real lake exists, still gives its printed result.

## Experiments as files (`genesis experiment run|status SPEC`)

- `experiments/specs/E00N.yaml`: `experiment_id`, `title`, `definition` (the pre-registered document), `base_config`, optional `base_changes`, `seeds` (list or `{first, count}`), `conditions` (label + dotted config changes), optional `output` (default `data/experiments/<id>`).
- Loading builds and validates every run's config first; a typo anywhere fails before any run starts.
- Each (condition, seed) writes `<output>/<label>-s<seed>/`. Status: **completed** (same config hash) is skipped; **stale** (completed with a different config) stops the batch unless `--rerun-stale`; **missing/incomplete** runs.
- Runs execute in worker processes (default: cores − 1); tasks are sent as plain config data. Order and worker count don't affect results (byte-identical test; 12 runs: 17.5 s on 1 worker, 2.6 s on 13).
- Results are ingested into the lake afterwards (`--no-ingest` to skip).
- E001–E003 have spec files; their existing runs show as **stale** because configs gained fields since (recording settings; for E001 the whole genome section). Their configs otherwise match the specs exactly (checked).

## Analysis notebook (`notebooks/analysis-workflow.ipynb`)

- The whole pipeline on a demo experiment (E990: 2 conditions × 6 seeds × 1500 ticks): spec → batch run → lake → SQL (join, window function) → pandas → descriptive statistics → bootstrap and Wilson intervals → paired effect and practical significance → permutation and sign tests (with SciPy cross-checks) → dashboard chart → export, verify, reload with pandas only.
- Writes to `data/notebook-demo/` (or `$GENESIS_NOTEBOOK_DIR`); runs in ~6 s.
- `tests/test_notebook.py` executes it in a fresh kernel (nbclient) and checks it is committed without outputs.

## Exports (`genesis lake export`, `genesis lake verify`)

- `--experiment E003 --out DIR [--format parquet|csv] [--tables a,b]`: one file per table with rows (sorted by primary key; `runs` includes failed runs; config as JSON text), `README.md` (conventions and table sections cut from the data dictionary) and `manifest.json` (source commit, row counts, SHA-256 per file).
- `--query "SELECT ..." --out file.csv|.parquet` saves any query result.
- `genesis lake verify DIR` recomputes checksums against the manifest.
- E003: 13.7 M rows exported in 1.7 s (91 MB Parquet). `experiments/independent_reanalysis.py` (pandas, NumPy, SciPy only; asserts no Genesis Lab import) reproduced H7a from the export.

## Experiment dashboards (`genesis dashboard EXP [--compare T:C] [--window A B]`)

- Built from the lake (completed runs only; failed and extinct runs are counted in the header). Output `data/dashboards/<EXP>.html`: self-contained, offline, deterministic (fixed chart IDs and bootstrap seed).
- Individual runs vs summaries are always visually distinct: faint per-run lines and small per-run dots; bold per-condition medians with a middle-50%-of-runs band (spread); diamonds with 95% bootstrap CIs (precision).
- Sections: population; gene trends (evolving genes); settled values (window default: last 1,000 ticks); paired differences per seed (`--compare`). Sections without data are left out (e.g. no genes in E001).
- Median-over-time hovers show how many runs each point is based on; the header warns about survivorship when runs went extinct.
- Shares `report.css`, `theme.py` and `report/html.py` with run reports.

## Randomness

One integer seed per run → `numpy.random.SeedSequence` → `.spawn(8)` → one independent `Generator` per subsystem, in this fixed order: `setup` (founders), `food`, `controller`, `reproduction`, `tiebreak`, `mutation` (added in 2.2), `brain` (added in 4.3: founders' weights and brain mutation; unused when there are no brains), `predators` (added in 6.1, D-057: unused without predators; split with `Generator.spawn` into the predators' own setup, controller, reproduction, mutation, capture (6.2) and brain (6.3) streams, so predator draws never shift the prey's, and a world with predators starts with the same prey and food as one without). Tests check that each addition left the earlier streams unchanged. New streams are appended at the end only (D-012). Adding a random draw in one subsystem does not shift the sequence in another, so paired-seed comparisons stay valid as the code grows.

## Milestone 1 plan

| # | Increment | Key test | Status |
|---|---|---|---|
| 1.0 | Scaffold: git, uv, ruff, pytest, docs | Smoke test passes | done |
| 1.1 | `config.py` + `default.yaml` | Invalid config rejected | done |
| 1.2 | `world.py`: bounds, food regrowth | Food within cap and bounds | done |
| 1.3 | `organism.py`: state, Traits, energy, death | Zero energy → dead | done |
| 1.4 | Controllers, movement, wall clamping | Walls hold; seeker approaches food | done |
| 1.5 | `simulation.py`: tick loop, RNG streams | Determinism | done |
| 1.6 | Eating, tie rule, energy ledger | Tie rule; ledger balances | done |
| 1.7 | Cloning, population cap, newborn delay | Newborns inactive on birth tick | done |
| 1.8 | Metrics, CLI, CSV output | Identical files from repeated runs | done |
| 1.9 | Benchmark, seeker-vs-random comparison (E001), docs | Numbers recorded | done |

## Milestone 2 plan (approved 2026-10-18)

Decisions: trade-off costs for sense range and speed; metabolic rate as a cost-free positive control; a neutral marker gene as the in-run drift control; Plotly HTML reports; hand-written permutation and sign tests (SciPy stays in Milestone 3).

| # | Increment | Key test | Status |
|---|---|---|---|
| 2.0 | Golden digests lock in Milestone 1 behaviour | Default run unchanged | done |
| 2.1 | Genome: gene definitions, bounds, expression to traits | Bounds validated; Milestone 1 unchanged | done |
| 2.2 | Mutation: per-gene rate and size, reflection, own RNG stream, off switch | In bounds; no pile-up; off = exact copy | done |
| 2.3 | Inheritance wired in; `mutations.csv`; gene columns | Child = parent + recorded changes | done |
| 2.4 | Trade-off costs; positive control and neutral marker | Ledger balances; defaults = Milestone 1 | done |
| 2.5 | Trait statistics per tick; genome snapshots | Matches a recount from raw data | done |
| 2.6 | `genesis report`: Plotly HTML trait charts | Built from recorded files | done |
| 2.7 | Permutation and sign tests | Known cases | done |
| 2.8a | Neutral-twin control; E002 + E003 pre-registered; experiment helpers | Smoke runs on throwaway seeds | done |
| 2.8b | Run E002 + E003 and report (after review) | Results appended to definitions | done |
| 2.9 | Docs, curriculum, benchmarks, push, stop for review | | done |

### Milestone 2 scope check (2026-10-18)

| Scope item / acceptance criterion | Evidence |
|---|---|
| Genome with explicit gene definitions and bounds | `evolution/genome.py` (`GENES`), `GenomeConfig` validation; tests/evolution/test_genome.py |
| Heritable speed, sense range, metabolic efficiency, reproduction threshold | Genes + `express()`; lineage-integrity test; E002 |
| Asexual reproduction; offspring energy and parental cost | 1.7 (D-008, D-014) |
| Configurable mutation probability and magnitude; off switch | `mutation: {enabled, rate, size}`, per-gene `mutable`; tests/evolution/test_mutation.py |
| Mutations stay within bounds | Reflection (D-019); 5000 huge mutations stay in bounds; no pile-up test |
| Reproduction obeys energy requirements | Config rejects unaffordable threshold ranges; `pay_for_offspring` raises; energy ledger every tick |
| Lineage information consistent | `founder_id`, `parent_id`, mutation log; genome = parent + logged changes for every organism |
| Births, deaths, offspring counts, trait distributions recorded | ticks.csv, organisms.csv, gene_stats.csv, genomes.csv, mutations.csv; recount test |
| Population limits, safeguards against runaway consumption | Population cap, one meal per tick, ledger with gross-flow tolerance (D-026) |
| Simple visualization of trait distributions | `genesis report` (D-023) |
| Evolutionary change measurable across generations | gene_stats time series; E002/E003 |
| Extinction handled without crashing | Tests for extinct runs in simulation, recorder, report, experiments |
| No-mutation runs preserve genomes | E002 check C1 (20/20); tests |
| Scenario A (neutral baseline) and B (resource scarcity) | E002 (off + neutral twins + positive control), E003 (scarcity, 2 × 2) |
| No adaptation claims without controls and statistics | Pre-registration, neutral twins, permutation/sign tests, Holm correction, recorded corrections |
| No neural networks | None added |

## Milestone 3 plan (approved 2026-10-19)

Decisions: Parquet files are the source of truth with DuckDB views over them; run folders keep writing CSV and an ETL produces Parquet; Experiment A is a four-level food dose-response testing H1; notebooks are Jupyter in VS Code (ipykernel), executed in tests.

| # | Increment | Key test | Status |
|---|---|---|---|
| 3.0 | Schema document and data dictionary; stop for review | — | done |
| 3.1 | Tick sampling, optional event log, schema version, condition, config hash in run.json | Defaults give identical results | done |
| 3.2 | ETL: run folder → Parquet with validation; back-fill E001–E003 | Rows and values match the CSVs | done |
| 3.3 | DuckDB views; `genesis sql`; join and lineage examples | SQL = independent Python from the CSVs (pandas arrives in 3.5) | done |
| 3.4 | Batch runner: experiment file → parallel, resumable runs | Parallel = sequential, byte for byte | done |
| 3.5 | pandas + SciPy analysis: descriptive stats, bootstrap/Wilson CIs, effect sizes; cross-check hand-written tests | Known answers; SciPy agreement | done |
| 3.6 | Experiment dashboards: individual runs vs aggregates | Built from the database | done |
| 3.7 | Export to CSV/Parquet; reload and re-analyse | Round trip; independent re-analysis | done |
| 3.8 | Analysis notebook, executed in tests | Runs clean | done |
| 3.9 | SQL exercises (hints, hidden answers) | Answers verified | done |
| 3.10a | Experiments A, B, C: pilots, pre-registration, specs, analysis scripts | Analyses recover known answers | done |
| 3.10b | Run E004–E006 and report (after review) | Results appended to definitions | done |
| 3.11 | Wrap-up; stop before neural networks | | done |

### Milestone 3 scope check (2026-10-19)

| Scope item / acceptance criterion / deliverable | Evidence |
|---|---|
| Schemas for experiments, runs, organisms, lineages, time series | [schema.md](schema.md) (explained before implementation, 3.0), [data-dictionary.md](data-dictionary.md), `lake/tables.py` |
| Parquet persistence and DuckDB queries | `lake/ingest.py` (D-029), `lake/db.py` (D-030); 495 runs, 293 MB |
| Run IDs, config snapshots, seeds, versions, completion status | `run.json` (schema v3: condition, config_hash), `runs` table; failed runs recorded |
| Configurable metric sampling and event logging | `recording.ticks_every` (flows summed, D-028), `recording.events` |
| Batch execution; repeated simulations with different seeds | spec files + `genesis experiment run` (parallel, resumable, D-031); parallel = sequential byte for byte |
| Comparison using pandas and SciPy | `analytics/analysis.py` (D-032); SciPy cross-checks to 1e-12 |
| Interactive Plotly charts | `genesis dashboard` (D-033), run reports |
| CSV and Parquet export | `genesis lake export` with README + manifest (D-034) |
| Notebook demonstrating the workflow | `notebooks/analysis-workflow.ipynb`, executed in tests (D-035) |
| Experiments A, B, C, each pre-specified | E004 (food dose-response), E005 (mutation vs diversity), E006 (founders vs extinction): hypothesis, control, metrics, replicates, analysis and SESOI committed before running |
| Every run has reproducible metadata | run.json provenance + `config_hash`; golden and determinism tests |
| Multiple experiments run headlessly | `genesis experiment run`, scripts with `--analyse-only` / `--smoke` |
| Data queryable with SQL | `genesis sql`, [sql-examples.md](sql-examples.md) (executed by tests) |
| Time series and lineage can be joined | SQL examples 3 and 7, exercises 4–5, 8; tests compare with independent Python |
| Failed runs marked and excluded from completed-run analyses | `status` column, `completed_runs` view; tests |
| Charts distinguish individual runs from aggregates | dashboards: faint per-run lines/dots vs bold medians and CIs; tests count traces |
| Results report variation across replicates | describe_by, bootstrap and Wilson intervals, dashboards, experiment result tables |
| Organisms never used as replicates | per-run summaries everywhere; exercise 4; analysis docstrings |
| Exported data reloadable and independently analysable | `experiments/independent_reanalysis.py` (pandas/SciPy only) reproduced E003 H7a |
| SQL exercises with questions about the populations | [sql-exercises.md](sql-exercises.md), 10 exercises, answers checked against the lake |
| Data dictionary; updated documentation | data-dictionary.md; README, CLAUDE.md, curriculum, decision log D-026–D-035 |
| Stop before neural-network controllers | none added |

## Milestone 4 plan (approved 2026-10-19)

Scope: [roadmap/04A](roadmap/04A_NEURAL_BRAINS.md) and [roadmap/04B](roadmap/04B_NEUROEVOLUTION_COMPARISON.md). Decisions: 7 inputs, 6 tanh hidden units, 2 outputs (turn, throttle; no "forage" output since eating is automatic); every founder gets its own seeded random weights; a noise input gives brains the same randomness the baselines use; no energy cost for having a brain (a stated limitation); PyTorch cross-check decided at 4.8.

| # | Increment | Key test | Status |
|---|---|---|---|
| 4.1 | Forward pass in NumPy: `Brain`, parameter layout, worked example ([neural-networks.md](neural-networks.md)) | Hand-computed example; batch = one at a time, bit for bit | done |
| 4.2 | Sensor vector: 7 normalised inputs including a wall sensor and noise | Every input in [−1, 1] for extreme states | done |
| 4.3 | Brains as inherited genes: `brain` RNG stream (appended), founder initialisation, bounded mutation, inheritance, digest | Golden values unchanged; child = parent + mutation | done |
| 4.4 | `controller: neural` in the tick; `configs/neural.yaml` | Rule-based runs byte-identical; ledger balances | done |
| 4.5 | Recording: brains at birth, behaviour summaries; schema v4; lake tables; report charts | Lake checks; recount | done |
| 4.6 | `genesis inspect`: inputs → hidden → outputs → action → state for one organism and tick | Replay = original run | done |
| 4.7 | Pre-register E007: random vs seeker vs evolved brains, train/evaluation seed groups; neural golden values (Darwin arm64; Linux x86_64 added in the post-milestone review) | Smoke runs on throwaway seeds | done |
| 4.8 | Run E007 and report | Results appended to the definition | done |
| 4.9 | Wrap-up: docs, scope check; stop before Milestone 5 | | done |

### Chunk 04A scope check (2026-10-19)

| 04A requirement | Evidence |
|---|---|
| Fixed-topology feedforward policy in NumPy; documented sensors and outputs | `intelligence/neural.py` (D-039), `brain_inputs.py` (D-040), [neural-networks.md](neural-networks.md) |
| Normalised inputs; stable activations; bounded turn and throttle | Inputs in [−1, 1] (property-tested); tanh/sigmoid; turn = tanh × max_turn |
| Forage output, or a documented 2-output alternative | 2 outputs; eating is automatic (D-039, roadmap note) |
| Weights as inheritable genome parameters: validated shapes, finite, seeded initialisation, bounded Gaussian mutation; no gradient descent | `evolution/brain.py` (D-041): own stream, ±4 reflected, read-only arrays |
| CLI inspector: inputs, hidden activations, outputs, action, resulting state | `genesis inspect` (D-044) |
| Tests: shapes and parameter count; hand-computed example; extreme inputs; reproducible initialisation and inference; mutation; no shared mutable parameters; newborns inherit | tests/intelligence/test_neural.py, test_brain_inputs.py, test_neural_controller.py; tests/evolution/test_brain.py |
| A neural organism lives in the deterministic engine | `controller: neural`, `configs/neural.yaml` (D-042); deterministic, ledger-checked, extinction-safe |
| Worked example verifiable by hand | [neural-networks.md](neural-networks.md), asserted by tests |
| Learning: vectors/matrices, weighted sums, activations, genotype→controller, selection vs backpropagation | [neural-networks.md](neural-networks.md); [curriculum.md](curriculum.md) 4.1–4.6 |
| Rule-based results unchanged | Golden values; byte-identical CSVs against `main` after every increment |



### Milestone 4 scope check (chunk 04B, 2026-10-19)

Chunk 04A's checklist is above. Chunk 04B:

| 04B requirement | Evidence |
|---|---|
| Inherited fixed-topology networks with mutation inside ecological reproduction; no separate genetic algorithm | Brains inherited and mutated at birth like genes (D-041); selection is survival and reproduction in the world |
| Random, hand-written and neural policies under matched settings; endpoints and seeds predefined; 10–20+ seeds | E007: same evaluation worlds for all conditions; endpoint and four hypotheses pre-registered (`826a705`); 24 worlds |
| Genotype complexity, computation cost and starting conditions discussed as limitations; survival/energy, not "intelligence" | E007 "Limitations stated in advance" and "What this does not show"; endpoint is meals and energy per meal |
| Plots of per-run outcomes and of weights/behaviour over time | E007 results page (`--report`): per-world dots, paired differences vs SESOI, training behaviour and weight drift across 24 runs; run reports' Behaviour section (D-043) |
| Train and evaluate on different seed groups; discuss generalisation | Training seeds 7000–7023, evaluation worlds 7100+; H13 home vs away: equivalent |
| Optional PyTorch forward-pass check | Deferred, with reasons (D-046) |
| Tests: reproducible neural actions; no shape/NaN errors in batches; condition labels and seeds preserved; train/evaluation separated | tests/core/test_simulation_neural.py, tests/intelligence/test_neural_controller.py, neural golden values (D-045); evaluation-rule test re-derives the brain sample; seed-overlap test |
| Comparison report with uncertainty and an unembellished conclusion | [E007 results](experiments/E007-neuroevolution.md): H12 reported as inconclusive although the difference is "significant" |
| Rule-based runs still work, unchanged | Golden values; byte-identical CSVs against `main` after every increment |

Linux x86_64 neural golden values were recorded in the post-milestone review (D-045): the event digest matched the Mac's, the state digest is platform-specific as for rule-based runs (D-027). The same review re-ran E007 on Linux: every verdict agreed (H11 supported, H12 inconclusive, H13 equivalent, H14 lower cost per meal) although the numbers differ beyond the last bits, as expected when 20,000-tick runs diverge from last-bit differences.

## Milestone 5 plan (approved 2026-10-19)

Scope: [roadmap/05A](roadmap/05A_API_STREAMING.md) and [roadmap/05B](roadmap/05B_BROWSER_LAB.md). Decisions: the Python server is the only authority; the simulation steps in slices inside the event loop (no threads); snapshots are versioned, columnar JSON, sent at most ~15 per second with only the newest kept per client; local only; uPlot for charts; bundled fonts; Vitest plus a manual end-to-end checklist; live runs can be exported as normal run folders. The interface follows the user's design rules (no default Tailwind/shadcn look, no glassmorphism, no toasts, small components, Zustand for shared state, data outside components).

| # | Increment | Key test | Status |
|---|---|---|---|
| 5.1 | FastAPI app, `genesis serve`, run manager with explicit states, create/list/get/delete runs, configs | Invalid configs rejected; state table | done |
| 5.2 | Pause, resume, single step, reset by seed; playback speed | Run steered through the API = headless run (digest) | done |
| 5.3 | WebSocket snapshot stream: versioned payload, newest-only, bounded queues, many clients | Two clients see the same state; no unbounded growth | done |
| 5.4 | Organism details (genome, family, brain thought); saved runs; export to a run folder; `docs/API.md` and an example script | Export = a `genesis run` folder | done |
| 5.5 | Vite + React + TypeScript; design tokens, fonts, layout shell; API client, reconnecting WebSocket hook; Zustand store | Store and payload unit tests | done |
| 5.6 | Live World: PixiJS canvas, food, organisms, pan/zoom, selection, trails; 1,000+ organisms | Selection never changes the simulation | done |
| 5.7 | Controls and the organism inspector with a brain view | Out-of-range input rejected in place | done |
| 5.8 | Run Analytics: live charts with units, sample sizes, run IDs | Chart values = backend values | done |
| 5.9 | Experiment Comparison and Lineage Explorer from the lake | Two runs compared; tree correct | done |
| 5.10 | Hardening and wrap-up: reconnect, extinction, refresh, keyboard and accessibility, phone width; `genesis lab`; quickstart, manual E2E checklist, docs | Checklist passes | done |

### Chunk 05A scope check (2026-10-19)

| 05A requirement | Evidence |
|---|---|
| Validated endpoints: create, read config, pause, resume, single step, reset by seed, summary, organism details, list saved runs, export | [API.md](API.md) endpoint table; `tests/api/` |
| WebSocket stream of read-only snapshots at a rate independent of the tick rate; typed, versioned payload; coalescing for slow consumers; simulation never blocked by the UI | `api/stream.py` (D-049): `hello`/`snapshot`/`gone`, version 1, newest-only at ≤ fps; tests: frames capped while running flat out, a non-reading viewer doesn't slow the run |
| Explicit run state; safe control coordination; bounded inputs, paths and memory | `RunState` and `ALLOWED` (D-047); one-thread model (D-048); names not paths; ≤ 4 live runs; no queues |
| Deterministic stepping through the API; sequence independent of the number of clients | Digest test: API-steered runs (steps, pauses, speeds, flat out) = headless runs, rule-based and neural |
| `docs/API.md` and a usage script | [API.md](API.md) (coverage tested); `scripts/api_example.py` |
| Tests: create/step/pause/resume/reset; invalid config; snapshot shape; two clients same state; disconnects; no unbounded queue growth; digest equal to headless after N ticks | `tests/api/test_app.py`, `test_runs.py`, `test_controls.py`, `test_stream.py` (including a real-uvicorn WebSocket test), `test_details.py`; under load against a real server (controls raced from eight clients, fifty viewers, four runs flat out, a 120,000-tick run, lake queries during exports): `tests/test_stress.py` |
| Learning: client/server, JSON schemas, async I/O, WebSocket vs HTTP, concurrency hazards, one authority | [curriculum.md](curriculum.md) 5.1–5.4 |

### Chunk 05B scope check (2026-10-20)

| 05B requirement | Evidence |
|---|---|
| React + TypeScript + Vite, stable PixiJS; canvas world with food, organisms with heading, pan/zoom, optional trails, selection, responsive layout | `web/` (D-051, D-052); 120 fps at 2,100 organisms; phone width checked |
| Sections: Live World, Run Analytics, Experiment Comparison, Lineage Explorer | The four views (D-053–D-055) |
| Controls: run, pause, one step, seed/config, reset, playback speed, export | Run picker and stage controls (D-053); export = "Save run" |
| Organism inspector: phenotype, genome, parent, children, neural sensors and actions | Specimen panel with the brain diagram (D-053) |
| Charts from real data, with units, sample sizes, conditions, run IDs; no invented metrics | Analytics and Compare captions, run IDs, "each point covers" (D-054, D-055); every value from the server |
| API disconnected/reconnecting, invalid input, extinction, >1000 agents with frame coalescing, refresh without changing the run | Reconnection with backoff; refusals in place; extinction and missing-run messages (D-056); newest-only stream (D-049); `?run=` |
| Quickstart, screenshot/demo instructions, manual E2E checklist; simple UI tests if feasible | [lab.md](lab.md), [e2e-checklist.md](e2e-checklist.md); Vitest for the lab's logic and contract |
| Tests/review: pause and single-step; reconnect reads true state; selecting doesn't modify the simulation; controls validate ranges; compare two runs; outputs match backend; responsive and keyboard usable | API tests (steering = headless by digest; viewing leaves a run bit-identical); fixture contract tests; checklist |
| Learning: frontend vs backend, API contracts, state synchronisation, Canvas/WebGL, evidence vs decoration | [curriculum.md](curriculum.md) 5.1–5.10 |
| Local UI doesn't affect seeded numerical results | Golden values unchanged throughout; viewing test |

## Milestone 6 plan, chunk 06A (approved 2026-10-20)

Scope: [roadmap/06A](roadmap/06A_PREDATOR_PREY.md). After trying the lab, the user found it worked but was "very simplistic", above all the world itself and how it looks; this plan answers both. Decisions (the recommendations, approved as proposed):

- **Predators have brains and evolve**, like prey: coevolution is possible but not designed in (06A: "do not bake in arms race outcomes").
- **Prey brains get three predator inputs** (seen, side, closeness): 7 → 10 inputs, 62 → 80 parameters. Configs without predators keep the 7-input brain, so E007 and every saved run reproduce exactly.
- **New data goes in new files** (`species.csv`, `captures.csv`): existing CSVs stay byte-identical for every old config; species is joined in the lake rather than added to `organisms.csv`.
- **Tune before pre-registering:** labelled pilot runs find settings where both species usually persist for a whole run; then E008 is fixed and run, and extinctions are reported, not hidden.
- **The plate is redrawn** (6.5): oriented cells instead of dots, predators a different shape and colour, energy as how full a cell looks, a fading mark at each capture (the one motion not caused by the user, because it marks a real event), predator and prey counts plus a phase plot.
- E008 is this experiment; the crowding experiment suggested after E007 becomes E009.

| # | Increment | Key test | Status |
|---|---|---|---|
| 6.0 | Chart sizes from the design tokens (Milestone 5 review recommendation) | Lengths in rem/px converted exactly; charts unchanged in the lab | done |
| 6.1 | Species and predator bodies: optional `predators:` config section (own body, costs and genes; brains come with senses in 6.3), no capture yet | Old configs: hashes, golden values and CSVs unchanged; matched seeds give the same prey and food | done |
| 6.2 | Capture phase after eating: one capture per predator per tick, contested prey closest-first with seeded tie-breaks, energy transfer through the ledger, captured prey never act again | One prey can't be eaten twice; energy as specified; no crash when either species dies out; replay reproducible | done |
| 6.3 | Senses: predators sense the nearest prey; prey sense the nearest predator (3 inputs) | Sensor values against hand-worked cases; old brains unchanged | done |
| 6.4 | Recording: counts per species, capture attempts and successes, extinctions, traits per species; schema version; lake tables; report sections | Saved-run schema compatibility; lake validation | done |
| 6.5 | The lab redrawn: cell bodies, species, energy, capture marks; predator/prey charts and phase plot; species in the specimen panel | Snapshot contract (fixtures) and drawing rules unit-tested; checked in Chrome | |
| 6.6 | E008 pre-registered (after labelled tuning pilots): prey evolved with vs without predators, plus a designed fleeing rule, tested against the same frozen predators | Spec and definition committed before running | |
| 6.7 | Run E008; effect sizes and uncertainty; honest limits of a toy model; 06A scope check; docs | Verdicts from the pre-registered analysis | |
