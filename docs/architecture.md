# Architecture

Status: Milestone 1 design. Modules marked *(planned)* do not exist yet.

## Component map

```text
configs/default.yaml ──► core/config.py (Pydantic) ──► SimulationConfig
                                                            │
cli.py ──► core/simulation.py ──owns──► World       (core/world.py: bounds, food positions)
                │                 ├──► Organisms   (core/organism.py: state + Traits)
                │                 └──► RNG streams {food, controller, reproduction, tiebreak}
                │
           tick():
             1 world.regrow_food(rng.food)
             2 observations = sense(snapshot)          every organism sees the same frozen world
             3 actions = controller.decide(obs, rng.controller)
             4 apply movement, clamp to walls
             5 resolve eating (closest wins, rng.tiebreak), apply energy costs, update ledger
             6 process deaths
             7 process reproduction; newborns queued, active next tick
             8 metrics.record(state)                   read-only
             9 tick += 1
```

## Responsibilities

| Module | Owns | Must not |
|---|---|---|
| `core/config.py` | Validated, immutable configuration | Contain simulation logic |
| `core/world.py` | Bounds, wall clamping; owns the `FoodSupply` | Know about controllers |
| `core/resources.py` | Food positions `(n, 2)`, Poisson regrowth, removal | Create its own RNG |
| `core/organism.py` *(planned)* | Per-organism state, `Traits` | Draw random numbers itself |
| `intelligence/controllers.py` *(planned)* | Observation → action | Mutate world state |
| `core/simulation.py` *(planned)* | Tick order, RNG streams, conflict rules | Do I/O |
| `analytics/metrics.py` *(planned)* | Per-tick measurements | Mutate state |
| `cli.py` *(planned)* | Arguments, file output | Contain simulation rules |

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

## Randomness

One integer seed per run → `numpy.random.SeedSequence` → `.spawn(4)` → one independent `Generator` per subsystem. Adding a random draw in one subsystem does not shift the sequence in another, so paired-seed comparisons stay valid as the code grows.

## Milestone 1 plan

| # | Increment | Key test | Status |
|---|---|---|---|
| 1.0 | Scaffold: git, uv, ruff, pytest, docs | Smoke test passes | done |
| 1.1 | `config.py` + `default.yaml` | Invalid config rejected | done |
| 1.2 | `world.py`: bounds, food regrowth | Food within cap and bounds | done |
| 1.3 | `organism.py`: state, Traits, energy, death | Zero energy → dead | |
| 1.4 | Controllers, movement, wall clamping | Walls hold; seeker approaches food | |
| 1.5 | `simulation.py`: tick loop, RNG streams | Determinism | |
| 1.6 | Eating, tie rule, energy ledger | Tie rule; ledger balances | |
| 1.7 | Cloning, population cap, newborn delay | Newborns inactive on birth tick | |
| 1.8 | Metrics, CLI, CSV output | Identical files from repeated runs | |
| 1.9 | Benchmark, seeker-vs-random observation, docs | Numbers recorded | |
