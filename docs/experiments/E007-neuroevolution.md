# E007 · Do evolved brains forage as well as the hand-written rule?

**Status:** defined 2026-10-19, before any E007 run (Milestone 4, chunk 04B). Results will be appended below the line without editing the definition.

## Why this experiment

Milestone 4 gave organisms a small neural network whose 62 weights are inherited and mutated (D-039 to D-042). One run (neural.yaml, seed 1) suggested that selection turned random brains into food-seekers. One run is an anecdote. This experiment asks, with replication and a fair comparison:

1. Does selection reliably produce brains that forage better than random brains?
2. How do evolved brains compare with the hand-written `nearest_food_seeker` rule?
3. Do evolved brains work as well in a world they never lived in?

It measures **foraging** (meals found per organism per tick), not "intelligence".

## Why not settled population size

When food supply limits a population, its settled size is set by the food supply and the organisms' costs, not by how cleverly they find food (E004, H1). In neural.yaml seed 1 the neural, seeker and random-walk populations all settled at similar sizes and meal rates (D-042). So E007 measures foraging where food is **not** limiting: a fixed population of 30 in a fresh world, where 2 new food items per tick far exceed the ~0.65 meals per tick 30 organisms need.

## Design

### Phase 1: training (evolution)

| | |
|---|---|
| **Spec** | `experiments/specs/E007-train.yaml` (condition `train`) |
| **Config** | `configs/neural.yaml`: neural controller, every expressed gene frozen, brains mutating (rate 0.1, size 0.2 per weight) |
| **Seeds** | 7000–7023 (24 runs). Never used before. |
| **Duration** | 20,000 ticks |
| **Recording** | ticks and behaviour every 10 ticks, genome snapshots every 1,000 (smaller files; nothing analysed depends on finer sampling) |
| **Success** | A training run *succeeds* if it completes with **at least 30 living organisms**. Failures (extinction, or fewer than 30) are counted and reported as a result: they show how often evolution from random brains fails. Seeds are never replaced or re-run. |

### Phase 2: evaluation (fresh worlds)

Built from the training results by a fixed rule (`experiments/e007_neuroevolution.py`, `evaluation_spec`), committed with this definition:

- Training run with seed `7000 + i` that succeeded → **evaluation world seed `7100 + i`**. Evaluation seeds were never used for training, so no brain has lived in its evaluation world.
- **Brains:** 30 drawn without replacement from that training run's organisms alive at the end, ordered by organism ID, using `numpy.random.default_rng(7100 + i).choice(n, 30, replace=False)`.
- **Evaluation setting** (all conditions): `neural.yaml` with 30 founders, `organisms.max_population: 30` (no births), `mutation.enabled: false`, `run.stop_on_extinction: false`, 1,000 ticks, every tick recorded.
- **Conditions**, each in the same evaluation world (paired by world):

| Condition | Controller | Founders' brains | Seeds |
|---|---|---|---|
| `random_walk` | random walk | — | 7100 + i |
| `seeker` | nearest food seeker | — | 7100 + i |
| `random_brains` | neural | unevolved random brains (drawn from the world's brain stream) | 7100 + i |
| `evolved` | neural | the 30 evolved brains | 7100 + i |
| `home` | neural | the same 30 evolved brains | 7000 + i (the training run's own seed) |

`home` puts the brains in a world started from their training run's own seed (same founder positions and initial food); it tests generalisation in reverse: if brains had specialised to their home world, they would do better there than in a new one.

### Metrics (per evaluation run)

- **Primary: meals per organism-tick** = total meals ÷ total organism-ticks (the sum over ticks of organisms deciding, `behaviour.n`), over ticks 0–999.
- **Secondary: energy spent per meal** = total living costs paid by all founders (`organisms.energy_spent`) ÷ total meals.
- **Descriptive:** survivors at tick 1,000, mean throttle, `toward_food`.

**Unit of analysis:** the evaluation world (one per successful training run). Organisms within a run are not independent.

## Hypotheses

Differences are paired: *condition A minus condition B in the same world*.

- **H11 (positive control): selection improved foraging.** `evolved − random_brains` meals per organism-tick > 0. One-sided paired sign-flip permutation test (exact up to 20 pairs, otherwise 20,000 samples from `default_rng(7011)`), α = 0.05. **If H11 fails, E007 is inconclusive** about H12 and H13: the evolution machinery would not have done its job.
- **H12 (primary): evolved brains vs the seeker.** Mean of `evolved − seeker` meals per organism-tick, with a 95% bootstrap CI (10,000 resamples, `default_rng(7012)`). **SESOI = 5% of the seeker's mean meal rate** across the evaluation worlds. Verdict, decided by the CI alone:
  - **better**: whole CI above +SESOI
  - **worse**: whole CI below −SESOI
  - **equivalent**: whole CI inside ±SESOI
  - **inconclusive**: otherwise
- **H13 (generalisation): new worlds vs home worlds.** Mean of `evolved − home` (paired by training run), 95% bootstrap CI (`default_rng(7013)`), SESOI = 5% of the mean `home` meal rate; same four verdicts. **Prediction: equivalent.** Brains have no position input, so they cannot memorise a world.
- **H14 (secondary): energy spent per meal, evolved vs seeker.** Mean of `evolved − seeker`, 95% bootstrap CI (`default_rng(7014)`), two-sided paired sign-flip permutation p-value (`default_rng(7015)` if sampled). No SESOI; reported as an estimate. The pilot's evolved brains moved at ~80% throttle, so they may spend less per meal.
- **Reported, not tested:** training failures (count of 24); `random_walk` as the floor; survivors; mean throttle and `toward_food` per condition.

No multiple-comparison correction is applied across H11–H14: H11 is a gate, H12 and H13 are decided by intervals against a SESOI rather than p-values, and H14 is labelled secondary.

## Pilot (disclosed)

Before this definition, a calibration pilot used throwaway seeds 99001–99006 (training) and 99101–99110 (evaluation), never to be reused. Settings matched the design above except the brain sample was drawn with one shared generator. Meals per organism-tick, mean (sd across 10 worlds): random walk 0.0274 (0.0010), seeker 0.0671 (0.0012), random brains 0.0328 (0.0122), evolved 0.0677 (0.0012). Evolved − seeker: +0.0007 on average (8 of 10 worlds ahead, 1 tied). One of 6 training runs went extinct. The pilot chose the endpoint (it separates the controllers; settled population does not), the no-births evaluation, the success rule, and 24 training seeds (to expect about 20 successes). It is not evidence for any hypothesis.

## Limitations stated in advance

- **Not a like-for-like contest.** The seeker was designed by a person and uses its bearing to food directly; the brains got 20,000 ticks of selection and have noise and a wall sensor the seeker lacks.
- **No cost for thinking.** A brain costs no energy (D-042); real nervous systems are expensive.
- **Genes frozen.** Speed and sense range were held at the founders' values, so brains evolved for one body.
- **Short evaluation.** 1,000 ticks with no births measures foraging, not long-term fitness, competition or reproduction.
- **One environment family.** All worlds share neural.yaml's size, food rate and costs; "generalisation" here means new random layouts of the same kind of world.
- **Meals are not intelligence.** A higher meal rate means better foraging in this toy model, nothing more.

**Code check (disclosed):** the analysis script was exercised by smoke runs (throwaway seeds 9100–9101, short runs, separate folder and lake) to check the code works. Their outputs are not evidence and do not change this definition.

---

## Results

*(Appended after the runs.)*
