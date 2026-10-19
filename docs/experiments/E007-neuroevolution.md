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

### Run

Commit `826a705` (clean; all 144 runs `git_dirty: false`). 24 training runs and 120 evaluation runs, all completed (34 s on 9 worker processes). Analysis: `uv run python experiments/e007_neuroevolution.py --analyse-only`; results page: add `--report` (writes `data/dashboards/E007-results.html`).

### Training

**24 of 24 training runs succeeded** (final populations 83–102; the pilot had lost 1 of 6). All 24 evaluation worlds were therefore used.

### Evaluation (24 worlds)

Mean (sd across worlds) per condition:

| Condition | Meals per organism-tick | Energy per meal (EU) | Survivors of 30 | Mean throttle | Turning toward seen food |
|---|---|---|---|---|---|
| random walk | 0.0264 (0.0013) | 15.30 (0.71) | 30.0 | 1.00 | 0.51 |
| food seeker | 0.0665 (0.0031) | 6.42 (0.34) | 30.0 | 1.00 | 1.00 |
| random brains | 0.0322 (0.0113) | 12.57 (4.80) | 28.7 | 0.53 | 0.62 |
| evolved brains | **0.0688 (0.0012)** | **6.02 (0.16)** | 30.0 | 0.90 | 0.75 |
| evolved, home world | 0.0686 (0.0018) | 6.05 (0.24) | 30.0 | 0.90 | 0.75 |

- **H11 (positive control): SUPPORTED.** Evolved − random brains = **+0.0366** meals per organism-tick; higher in **24 of 24** worlds; one-sided p = 0.00002. Selection reliably turned random brains into foragers, so H12 and H13 can be interpreted.
- **H12 (primary): INCONCLUSIVE.** Evolved − seeker = **+0.00237**, 95% CI [+0.00136, +0.00371] (**+3.6%** of the seeker's rate); SESOI ±0.00332. The interval excludes zero (evolved brains found more food, in 23 of 24 worlds), but its upper end crosses +SESOI, so by the pre-registered rule the data can't say whether the advantage reaches the 5% that was declared to matter. Neither "better" nor "equivalent" is supported.
- **H13 (generalisation): EQUIVALENT,** as predicted. Evolved (new world) − home = **+0.00021**, 95% CI [−0.00063, +0.00106] (+0.3%), entirely inside ±0.00343. Brains did as well in worlds they had never lived in.
- **H14 (secondary): evolved brains spend less per meal.** Evolved − seeker = **−0.40 EU per meal**, 95% CI [−0.55, −0.27] (**−6.2%**), two-sided p = 0.00005.

### Interpretation

Neuroevolution worked: in every world, brains shaped by 20,000 ticks of selection foraged far better than the random brains they started from (2.1× the meal rate), and they did not depend on the world they evolved in. Against the hand-written rule, evolved brains found slightly more food (+3.6%) at a lower cost per meal (−6.2%), and were more consistent across worlds (sd 0.0012 vs 0.0031). Whether the meal-rate advantage is large enough to matter by the pre-registered standard is undecided: more worlds would narrow the interval.

What this does **not** show: that the brains are "smarter". They turn toward food less consistently than the seeker (0.75 vs 1.00), had a wall sensor and a noise input the seeker lacks, and pay nothing for their brains. The comparison is between two foraging strategies in one toy world.

### Exploratory (post hoc, not tested; to be tested in a new experiment)

- **Where the cost advantage comes from.** Living cost per organism-tick (energy per meal × meal rate): seeker 0.426, evolved 0.414 EU (−2.6%, slower throttle: 0.90 vs 1.00). Combined with +3.6% meals per tick, that gives the −6.2% per meal: both contribute, the extra meals slightly more.
- **The advantage is concentrated where the seeker does badly.** Across worlds, the seeker's own meal rate and the evolved − seeker difference correlate at r = −0.92: in the seeker's best worlds the two tie; in its worst (world 15: 0.0554 vs 0.0691) the brains are far ahead.
- **A candidate mechanism: crowding.** Replaying the evaluation runs, seekers stood closer to their nearest neighbour than evolved brains in **24 of 24** worlds (mean 12.4 vs 16.6 units), and across worlds the seekers' spacing correlated with their meal rate (Spearman ρ = +0.48, p = 0.019). In the worst seeker worlds, seekers saw food more often than evolved brains (85% vs 80% of organism-ticks) but converted sightings into meals less (0.060 vs 0.084 meals per sighting-tick). A plausible reading: seekers all head for the nearest food, so several chase the same item and only one wins; evolved brains, turning toward food less reliably and with noise, stay spread out. Wall contact was ruled out as the main cause (seekers touched walls 4–6% of the time in both good and bad worlds). Testing this needs a pre-registered experiment that manipulates crowding (for example, food clustering or population density).
- **Training dynamics.** Turning toward food plateaued at ~0.75 within about 2,000 ticks in nearly every run; throttle kept rising for the whole run and ended anywhere from ~0.6 to ~1.0 across runs (results page, section 3).
