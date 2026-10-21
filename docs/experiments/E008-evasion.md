# E008 · Do prey evolve to escape predators?

**Status:** defined 2026-10-21, before any E008 run (Milestone 6, chunk 06A). Results will be appended below the line without editing the definition.

## Why this experiment

Milestone 6 added predators that hunt prey (D-057, D-058) and gave prey with brains three inputs about the nearest predator: is one in sight, on which side, how close (D-059). Nothing tells a prey to flee; its brain weights are inherited and mutated as in E007. This experiment asks, with replication and a fair test:

1. Do prey whose ancestors lived with predators get caught less often than prey whose ancestors never met one?
2. Is that evolved evasion as good as a fleeing rule a person wrote?
3. Does evading cost anything in foraging?

It measures **how often prey are caught** in a standard test, not "fear" or "intelligence". Chunk 06A asks not to build an arms-race outcome in; here only the prey can adapt (the predators follow a fixed rule), so it can't be an arms race at all.

## Design

### Phase 1: training (evolution)

| | |
|---|---|
| **Spec** | `experiments/specs/E008-train.yaml`, conditions `hunted` and `safe` |
| **Config** | `configs/predators.yaml` at commit of this definition: neural prey as `neural.yaml` (every expressed gene frozen, brains mutating at rate 0.1, size 0.2) with **100 founders**; predators `nearest_prey_seeker`, 4 founders, cap 10, speed 1.5, capture radius 3, capture probability 0.18, capture efficiency 0.5, reproduction threshold 240. Settings chosen by the tuning pilots below. |
| **Conditions** | `hunted`: as configured. `safe`: `predators.initial_count: 0`, the same world with no predators. Prey brains in both have the same 10 inputs and are drawn identically on the same seed; in `safe` the predator inputs are always 0. |
| **Seeds** | 8000–8019 (20 worlds, each run in both conditions: 40 runs). Never used before. |
| **Duration** | 20,000 ticks (E007's training length) |
| **Recording** | ticks, behaviour and predator counts every 10 ticks; genome snapshots every 1,000 |
| **Success** | A training run *succeeds* if it completes with **at least 30 prey alive**. A world enters the test only if **both** its training runs succeed. Failures are counted and reported as results; seeds are never replaced or re-run. |

Predators may die out during a `hunted` run (in the pilots they did in 5 of 12 seeds, between ticks 15,780 and 19,926). Such worlds are **not** excluded: their prey still evolved under predation for most of the run. When predators died out in each world is reported.

### Phase 2: the test arena

Built from the training results by a fixed rule (`experiments/e008_evasion.py`, `arena_spec`), committed with this definition:

- World `8000 + i` whose two training runs succeeded → **arena world seed `8100 + i`**. Arena seeds were never used for training.
- **Brains:** from each training run, 30 drawn without replacement from its prey alive at the end, ordered by organism ID, using `numpy.random.default_rng(8100 + i).choice(n, 30, replace=False)` (the same generator seed for both training runs of a world; each draw uses its own generator). Brains are rebuilt in `Brain.to_vector()` order from the lake (`BRAIN_ORDER`).
- **Arena setting** (all groups): `configs/predators.yaml` with 30 prey and **no births** (`organisms.births: false`, D-062), mutation off, `run.stop_on_extinction: false`, 1,000 ticks, every tick recorded; **4 chasers that neither starve nor breed** (no living costs: metabolic rate, movement and sensing costs 0; `predators.births: false`), with the training predators' capture radius, probability and efficiency. So every group meets the same predators under the same constant pressure.
- **Groups**, each in the same arena world (paired by world):

| Group | Prey controller | Prey brains |
|---|---|---|
| `seeker` | nearest food seeker (ignores predators) | — |
| `flee` | the designed flee rule (D-062): turn straight away from the nearest predator in sight, otherwise seek food | — |
| `from_safe` | neural | the 30 brains from the `safe` training run |
| `from_hunted` | neural | the 30 brains from the `hunted` training run |

### Metrics (per arena run)

- **Primary: captures per prey-tick** = total captures (`predator_ticks.captures`) ÷ total prey-ticks (the sum over ticks of prey deciding, `behaviour.n`), ticks 0–999. A hazard rate: how likely a prey is to be caught in a tick it is alive. It stays comparable however fast a group is eaten.
- **Secondary: meals per prey-tick** = total meals ÷ prey-ticks.
- **Descriptive:** survivors at tick 1,000, strike success (captures ÷ strikes), mean throttle.

**Unit of analysis:** the arena world. Prey within a run are not independent.

## Hypotheses

Differences are paired: *group A minus group B in the same world*.

- **H15 (positive control): evasion is possible in this arena.** `flee − seeker` captures per prey-tick < 0. One-sided paired sign-flip permutation test (exact up to 16 pairs, otherwise 20,000 samples from `default_rng(8015)`), α = 0.05. **If H15 fails, E008 is inconclusive** about H16: a designed fleeing rule doing no better than ignoring predators would mean the arena can't show evasion at all.
- **H16 (primary): prey evolved with predators are caught less.** `from_hunted − from_safe` captures per prey-tick < 0. One-sided paired sign-flip permutation test (`default_rng(8116)` if sampled), α = 0.05. Reported with the mean difference, its 95% bootstrap CI (10,000 resamples, `default_rng(8016)`), the relative difference, and the number of worlds where `from_hunted` was caught less.
- **H17 (estimate): evolved versus designed evasion.** Mean of `from_hunted − flee` captures per prey-tick, 95% bootstrap CI (`default_rng(8017)`). **SESOI = 10% of the `flee` group's mean capture rate.** Verdict by the CI alone: **evolved caught less** (whole CI below −SESOI), **designed caught less** (whole CI above +SESOI), **equivalent** (whole CI inside ±SESOI), **inconclusive** otherwise. Not a test; chunk 06A's question of how a designed fleeing rule differs from evolved avoidance.
- **H18 (secondary): the cost of evasion.** Mean of `from_hunted − from_safe` meals per prey-tick, 95% bootstrap CI (`default_rng(8018)`), two-sided paired sign-flip permutation p-value (`default_rng(8019)` if sampled). No SESOI; an estimate. Fleeing spends ticks not feeding; it may cost meals.
- **Reported, not tested:** training failures in each condition; when predators died out in each `hunted` world; survivors, strike success and throttle per group; `seeker` as the reference of no evasion.

No multiple-comparison correction across H15–H18: H15 is a gate, H16 is the single primary test, H17 is an interval against a SESOI, and H18 is labelled secondary.

## Tuning pilots and decisions taken before this definition (disclosed)

- **Tuning pilots** ([pilots/E008-tuning.md](pilots/E008-tuning.md), seeds 90000+, never to be reused): chose the training world's settings so that both species usually persist. With the chosen settings the prey never died out in 12 pilot seeds. The pilots measured only persistence and capture counts, never evasion; they are not evidence for any hypothesis.
- **Predators follow a rule, not brains** (approved by the user 2026-10-21, changing the Milestone 6 plan's "predators have brains and evolve"): neural predators starved within ~800 ticks in every pilot, so they can't be part of the training world.
- **The prey's predator senses have no "ahead" input** (D-059): a predator straight ahead and one straight behind look the same to a prey in a single tick. Kept as approved; a known limit.
- **Code added for this experiment** (D-062): the `flee_seeker` controller, `births: false`, and the arena rule. Tested before this definition was committed.

**Code check (disclosed):** the script was exercised by smoke runs (throwaway seeds 9100–9101, 3,000-tick training, 200-tick arenas, separate folder and lake) to check that it works. They found and fixed three bugs before any real run: an empty-table check that refused worlds with 0 predators, arena groups named like the training conditions (which mixed training runs into the arena's numbers), and births refilling the arena after captures (now `births: false`). Their outputs are not evidence and do not change this definition.

## Limitations stated in advance

- **One-sided adaptation.** Only prey evolve; predators follow a fixed rule. This is selection by a predator, not coevolution.
- **A blind spot.** No input says whether a predator is ahead or behind; evasion has to work around that.
- **The test predators are the training predators' kind.** Prey evolved against chasers are tested against chasers; nothing here says how they would fare against another kind of predator.
- **Training pressure varies.** In some `hunted` worlds predators may die out before tick 20,000, weakening selection late in training; reported, not corrected.
- **No cost for thinking or fear.** Brains cost no energy (D-042); sensing predators costs nothing beyond the sense range prey already pay for.
- **A toy world.** Caught less often here means a lower capture rate in this simulation, not that real prey would evolve the same way.

---

## Results

*(Appended after the runs, in 6.7.)*
