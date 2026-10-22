# Genesis Lab: six milestones

A summary of what was built, what was found, and what was learned, written at the end of Milestone 6 (2026-10-21). Every claim below links to where it is recorded. The project stops here: no new features without the user's authorisation (06B's acceptance).

## What was built

| Milestone | What it added | Where |
|---|---|---|
| **1. The Petri dish** | A deterministic 2D world: organisms that sense, decide, move, eat, pay energy and die; food that regrows; an energy ledger checked every tick; one random stream per subsystem; recorded runs and HTML reports | [architecture.md](architecture.md), D-001 to D-020 |
| **2. Genetics and evolution** | Heritable genes, mutation with reflection, trade-off costs (drag, sensing), a neutral marker as an in-run drift control | D-019 to D-028 |
| **3. The science lab** | A Parquet data lake with DuckDB views, a batch experiment runner, statistics (permutation tests, bootstrap intervals, smallest effects of interest), dashboards, exports, a notebook and SQL exercises | [schema.md](schema.md), [data-dictionary.md](data-dictionary.md), D-029 to D-038 |
| **4. Evolving neural brains** | A NumPy network of 7 inputs, 6 hidden units and 2 outputs whose 62 weights are genes; behaviour metrics; `genesis inspect` to replay any decision | [neural-networks.md](neural-networks.md), D-039 to D-046 |
| **5. An API and a browser lab** | A local FastAPI server with a WebSocket stream; a React lab with a PixiJS plate, specimen panel, charts, comparison and lineage views, in a brightfield-microscopy design | [API.md](API.md), [lab.md](lab.md), [ui-design.md](ui-design.md), D-047 to D-056 |
| **6. Predators, and two foods** | A second species that hunts (06A); two kinds of food and a heritable diet (06B); recording, lake tables, report sections and lab views for both | D-057 to D-064 |

Size at the end: about 10,000 lines of Python in `src/`, 10,500 of tests (983 fast tests, 5 slow), 4,700 of TypeScript in `web/src/`, 64 recorded decisions, 9 pre-registered experiments. Every older world still reproduces its recorded files byte for byte (checked at every increment).

## What was found

Each experiment was defined and committed before it ran; results are appended without editing the definition, and post-hoc findings are labelled exploratory.

| | Question | Result |
|---|---|---|
| [E001](experiments/E001-controller-comparison.md) | Food seeker vs random walk | Seekers reach the population limit faster; both settle at a size set by the food supply |
| [E002](experiments/E002-selection-machinery.md) | Does the evolution machinery work? | Yes: the positive control evolved in 20/20 seeds |
| [E003](experiments/E003-food-scarcity.md) | Does scarcity change selection? | It raised selected sense range (adjusted p = 0.031; worth replicating) |
| [E004](experiments/E004-food-dose-response.md) | Is population proportional to food? | Yes: elasticity 0.992 [0.982, 1.001] |
| [E005](experiments/E005-mutation-diversity.md) | Does more mutation keep more diversity? | Yes: ρ = 0.88, roughly √(rate) |
| [E006](experiments/E006-founders-extinction.md) | Do fewer founders mean more extinction? | No monotonic effect (p = 0.42) |
| [E007](experiments/E007-neuroevolution.md) | Do evolved brains forage as well as a hand-written rule? | Selection worked in 24/24 worlds and generalised; +3.6% meals against the rule, inconclusive against the 5% that mattered; replicated on Linux |
| [E008](experiments/E008-evasion.md) | Do prey evolve to escape predators? | Not detectably on the Mac (−5.2%, CI includes 0), but 14% fewer captures in a Linux replication (p = 0.007); a designed flee rule cut captures by 73% on both |
| [E009](experiments/E009-specialisation.md) | Does a population split into specialists on two foods? | Specialists emerged in 20/20 worlds with a curved trade-off; 9 split into two coexisting groups, 11 went one way; a straight-line trade-off did nothing |

Read together: **selection in this world readily tunes numbers** (genes in E002–E005; foraging brains in E007; the diet in E009) **but found avoidance, a behaviour that must react to a moving threat, much harder** (E008: at most a small effect, detected on one platform and not the other). E006's null is informative because its controls passed; E008 shows why a single sample of 20 worlds can't settle a small effect.

## What was learned (the curriculum)

Concept by concept in [curriculum.md](curriculum.md). The habits that mattered most across all six milestones:

- **Determinism first.** One seed, one result, bit for bit; new randomness gets its own stream, so comparisons stay matched.
- **Controls inside experiments:** a neutral gene, random brains, a designed rule, a world without the factor. Without them, E008's null and E009's positive would both be unreadable.
- **Write the question down before the data exists**, disclose what was seen first, and label anything found afterwards.
- **Check a tool on a known case** before trusting it on an unknown one (the flee rule on the turning measure; the smoke runs that found bugs in E008 and E009).
- **Change an approved plan openly**, with the evidence (neural predators couldn't survive; the user decided).

## Where to go from here

[RESEARCH_ROADMAP.md](RESEARCH_ROADMAP.md) lists two ideas, not plans: brains that evolve a food preference (growing from E009), and evasion with an "ahead" input and longer exposure (growing from E008). [release-checklist.md](release-checklist.md) says how to show the project cleanly from a fresh clone.
