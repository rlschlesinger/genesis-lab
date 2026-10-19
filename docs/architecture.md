# Architecture

Status: **Milestone 1 complete** (2026-10-18). Milestone 2 (genetics and evolution) not started; it needs the user's approval.

## Component map

```text
configs/default.yaml ──► core/config.py (Pydantic) ──► SimulationConfig
                                                            │
cli.py ──► core/simulation.py ──owns──► World       (core/world.py: bounds, food positions)
                │                 ├──► Organisms   (core/organism.py: state + Traits)
                │                 └──► RNG streams {setup, food, controller, reproduction, tiebreak}
                │
           tick():
             1 world.regrow_food(rng.food)
             2 observations = sense(snapshot)          every organism sees the same frozen world
             3 actions = controller.decide(obs, rng.controller)
             4 apply movement, clamp to walls
             5 eat (closest pairs first, rng.tiebreak), then pay energy costs; ledger records flows
             6 process deaths
             7 reproduction: eligible survivors clone once; newborns join, first act next tick
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
| `intelligence/controllers.py` | `Observations` → `Actions` (pure) | Mutate world state |
| `core/movement.py` | Apply `Actions` within trait limits; walls; distance moved | Decide anything |
| `core/geometry.py` | `wrap_angle` | |
| `core/feeding.py` | Who eats what: closest-pair matching, random tie-break | Change energy itself |
| `core/energy.py` | `EnergyLedger`: flows and the per-tick conservation check | |
| `evolution/reproduction.py` | Who reproduces (random at the cap) and where offspring appear | Touch organisms |
| `core/simulation.py` | Tick order, RNG streams, founders, deaths, `TickSummary`, `state_digest` | Do I/O |
| `analytics/metrics.py` | Flat rows: `tick_row`, `organism_rows`; column lists | Mutate state |
| `analytics/storage.py` | Byte-stable CSV/JSON writers, atomic replace | Know about simulations |
| `analytics/provenance.py` | Git commit/dirty flag, versions, platform | |
| `analytics/runs.py` | `execute_run`: simulate + write run.json/ticks.csv/organisms.csv with status | |
| `cli.py` | `genesis run` arguments → `execute_run`; exit codes 0/1/2 | Contain logic |

The API (Milestone 5) will drive the same `Simulation` object as the CLI.

## Configuration

`load_config(path)` → `SimulationConfig` with sections `run`, `world`, `food`, `organisms` (including `organisms.traits`). Models forbid unknown keys and are frozen. Cross-field rules:

- `food.initial_count <= food.max_count`
- `organisms.initial_count <= organisms.max_population`
- `traits.reproduction_threshold > offspring_energy + reproduction_overhead`

Reproduction energy model: the parent pays `offspring_energy + reproduction_overhead`; the child starts with `offspring_energy`; the overhead leaves the system (recorded as outflow in the energy ledger).

## World and food

- Coordinates: origin bottom-left; valid positions `[0, width] x [0, height]`; `World.clamp` enforces hard walls and returns a new array.
- Food is one `(n, 2)` float64 array, not objects. Row index is the only identity and is valid until the supply next changes.
- `FoodSupply.positions` is a read-only view; only `spawn` / `remove` mutate food.
- Each tick, `regrow` draws a Poisson count (mean `regrowth_per_tick`), then spawns up to the cap. The draw happens even at the cap, so random draws per tick don't depend on world state.
- `remove` rejects duplicate or out-of-range indices: one item can never feed two organisms.

## Organisms

- `Traits`: frozen dataclass; fixed for a lifetime (heritable from Milestone 2).
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
- **Sensing** computes all organism-to-food distances at once, an `(n, m)` table via broadcasting. Food beyond an organism's own `sense_range` is invisible. Equidistant food: lowest index wins.
- **Actions are requests:** `turn` is clipped to `+/- max_turn`, `throttle` to `[0, 1]`. Non-finite actions raise.
- **Move order:** turn, step along the new heading, clamp to walls. `distances` is measured after clamping, and movement cost (1.6) is charged on it.
- **Baselines:** `RandomWalk` (normal turns, sd 0.3 rad, full speed) and `NearestFoodSeeker` (turn toward nearest sensed food, otherwise identical to `RandomWalk`, with the same random draws). The only difference between them is the response to sensed food.
- **Turning circle:** minimum radius = `speed / max_turn` (3 units by default). A full-speed organism cannot stop on a target; it overshoots and loops. On a head-on approach, steps of `speed` always land within `speed / 2` of the food, so `eat_radius >= speed / 2` guarantees a head-on approach can eat (default 2.0 vs 0.75).

## Simulation loop

- `Simulation(config)` builds streams, world, controller and founders (ids `0..n-1`, generation 0).
- `step()` runs one tick and returns a `TickSummary` (tick, population, deaths, food_count, food_spawned, mean_energy). Population and energy are end-of-tick values; `mean_energy` is NaN for an empty population.
- `run()` steps until `max_ticks`, or extinction if `stop_on_extinction`.
- Living organisms stay in ascending id order; dead organisms move to `sim.dead` and keep their records.
- Snapshot: all per-organism arrays are built once at the start of the tick, before anyone moves.
- Survivors' `age` increments at step 9, so a death check in step 6 sees the age *before* this tick's increment.
- `state_digest()`: SHA-256 over tick, food positions, and every organism's id/x/y/heading/energy/age/alive. Equal digests mean bit-identical state.

## Eating and energy accounting

- **Reach:** food within `eat_radius` of an organism's *post-move* position.
- **One meal per organism per tick; each item eaten once.**
- **Closest pairs first:** all in-reach pairs sorted by distance (ties: random key from the tiebreak stream); a pair eats if neither side is taken. Each item goes to the closest organism still competing for it.
- **Eat, then pay costs** (metabolism, movement), so a nearly-empty organism that reaches food survives.
- **Ledger:** stock = energy in living organisms + `food.count * energy_value`.
  - In: food spawned after the start.
  - Out: metabolism, movement, energy held at death.
  - Transfers: eating.
  - `step()` raises `EnergyLedgerError` if `initial + in - out` differs from the actual stock (tolerance: relative 1e-9, absolute 1e-6 EU).
- **Feedback:** spawning is blocked at `max_count`, so inflow depends on how much the population eats.

## Reproduction

- **Eligible:** survivors of this tick's deaths with `energy >= traits.reproduction_threshold`. At most one child per parent per tick.
- **Cap:** room = `max_population - survivors`. If more are eligible than there is room for, parents are chosen uniformly at random from the reproduction stream (never by ID).
- **Cost:** the parent pays `offspring_energy + reproduction_overhead`; the child starts with `offspring_energy`; the overhead is a ledger outflow. Recorded on the parent as `energy_invested` (separate from `energy_spent`, which is living costs only).
- **Child:** exact copy of the parent's `Traits` (shared frozen object), `generation = parent + 1`, `birth_tick = current tick`, placed uniformly in a disc of radius `parent.traits.speed` around the parent (clamped), random heading.
- **Timing:** newborns are appended after survivors (IDs stay ascending), are not aged at step 9, and first act on tick `birth_tick + 1`. Founders act from tick 0. With `max_age = A`, everyone gets exactly `A` active ticks.

## Run output

```text
<out>/run.json       run_id, experiment_id, status (running→completed|failed), seed, full config,
                     git {commit, dirty}, environment, ticks_run, stop_reason, final_state_digest
<out>/ticks.csv      one row per TickSummary (tick, population, births, deaths, food_count,
                     food_spawned, food_eaten, mean_energy, lineages)
<out>/organisms.csv  one row per organism ever: lineage, birth/death, lifetime totals, trait_* columns
```

- Default `<out>` is `data/runs/<run_id>`; run IDs look like `20261018T235501Z-s42-a1b2c3`.
- `run.json` is written before simulating and rewritten at the end; a failed run records `failed_at_tick` and `error` and writes no CSVs.
- CSVs use fixed columns, `\n` line endings, shortest exact float form, so identical runs give byte-identical files. Only `VOLATILE_FIELDS` (run_id, timestamps, duration) differ in run.json.
- Existing non-empty output directories are refused unless `--overwrite`.
- **Retention:** every tick and every organism (~200 KB + ~130 KB at defaults). No per-event logs in Milestone 1.
- **Lineage:** `founder_id` is inherited; `lineages` counts distinct founder IDs alive.

## Randomness

One integer seed per run → `numpy.random.SeedSequence` → `.spawn(5)` → one independent `Generator` per subsystem, in this fixed order: `setup` (founders), `food`, `controller`, `reproduction`, `tiebreak`. New streams are appended at the end only (D-012). Adding a random draw in one subsystem does not shift the sequence in another, so paired-seed comparisons stay valid as the code grows.

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
| 2.1 | Genome: gene definitions, bounds, expression to traits | Bounds validated; Milestone 1 unchanged | |
| 2.2 | Mutation: per-gene rate and size, reflection, own RNG stream, off switch | In bounds; no pile-up; off = exact copy | |
| 2.3 | Inheritance wired in; `mutations.csv`; gene columns | Child = parent + recorded changes | |
| 2.4 | Trade-off costs; positive control and neutral marker | Ledger balances; defaults = Milestone 1 | |
| 2.5 | Trait statistics per tick; genome snapshots | Matches a recount from raw data | |
| 2.6 | `genesis report`: Plotly HTML trait charts | Built from recorded files | |
| 2.7 | Permutation and sign tests | Known cases | |
| 2.8 | E002 (machinery and controls), E003 (food scarcity), pre-registered | Reported against the drift baseline | |
| 2.9 | Docs, curriculum, push, stop for review | | |
