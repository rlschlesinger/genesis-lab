# Roadmap: the remaining milestones

The chunk files in this folder are the user's scope documents for Milestones 4–6, kept **word for word**. They were written for a generic artificial-life repository, so a few details don't match Genesis Lab. This page says how each chunk maps onto the project and which details are adapted. Where a chunk and this page disagree, this page wins, and the reason is recorded in [decision-log.md](../decision-log.md) when the work happens.

Approval still works the same way: **no milestone starts without the user's explicit go-ahead** (see [CLAUDE.md](../../CLAUDE.md)).

## Which chunk belongs to which milestone

| Chunk | Genesis Lab milestone | Status |
|---|---|---|
| 00A–03B (discovery, scaffold, world, food, genomes, evolution, storage, statistics) | Milestones 1–3 | Done (not copied here; the work is in the code and docs) |
| [04A Neural brains](04A_NEURAL_BRAINS.md) | Milestone 4, first half | Done (scope check in [architecture.md](../architecture.md)) |
| [04B Neuroevolution comparison](04B_NEUROEVOLUTION_COMPARISON.md) | Milestone 4, second half (experiment E007) | Done ([E007](../experiments/E007-neuroevolution.md)); PyTorch check deferred (D-046) |
| [05A API and streaming](05A_API_STREAMING.md) | Milestone 5, backend | Done ([API.md](../API.md); scope check in [architecture.md](../architecture.md)) |
| [05B Browser lab](05B_BROWSER_LAB.md) | Milestone 5, frontend | Done ([lab.md](../lab.md); scope check in [architecture.md](../architecture.md)) |
| [06A Predator and prey](06A_PREDATOR_PREY.md) | Milestone 6, first half (experiment E008) | Done ([E008](../experiments/E008-evasion.md); scope check in [architecture.md](../architecture.md)); predators follow a rule in E008, since neural predators couldn't survive (D-062) |
| [06B One advanced extension](06B_ONE_ADVANCED_EXTENSION.md) | Milestone 6, second half (experiment E009) | Done: extension A (two foods), [proposal](06B-proposal.md), [E009](../experiments/E009-specialisation.md), scope check in [architecture.md](../architecture.md), [summary](../summary.md) |

## Translations that apply to every chunk

The chunks assume a different starting repository. In Genesis Lab:

| The chunks say | Genesis Lab uses | Why |
|---|---|---|
| package `alife`, CLI `alife` | package `genesis`, CLI `genesis` | Existing name. |
| `docs/DECISIONS.md` (ADRs) | [decision-log.md](../decision-log.md) (D-001 onwards) | Same purpose; an ADR is one decision entry. |
| `docs/MILESTONE_STATUS.md` | the status line in [architecture.md](../architecture.md) and the README | Same purpose. |
| `docs/LEARNING_LOG.md` | [curriculum.md](../curriculum.md) | Same purpose. |
| `docs/SQL_EXAMPLES.md` | [sql-examples.md](../sql-examples.md) | Already exists. |
| `PROJECT_PROPOSAL.md` | [architecture.md](../architecture.md) and [CLAUDE.md](../../CLAUDE.md) | The original master spec lives there in adapted form. |
| Mesa agents | plain NumPy and dataclasses | Chosen in Milestone 1: every line is visible and nothing hides the tick order. |
| toroidal (wrap-around) world, "wrapped" distances | hard walls | Chosen in Milestone 1. Switching now would change every golden value and invalidate E001–E006. Wherever a chunk says "wrapped direction" or "wrapped distance", read plain direction or distance. |
| contested food broken by distance, then organism ID | closest pair first, exact ties broken by the tiebreak random stream | Breaking ties by ID would favour older lineages (CLAUDE.md, food contention). |
| matplotlib PNGs | Plotly HTML reports and dashboards | Chosen in Milestone 2 (D-023). |

The simulation invariants in CLAUDE.md hold for every chunk: determinism (new random streams are appended at the end only), snapshot sensing, the energy ledger, bit-identical optimisations, and byte-identical CSVs for rule-based runs.

## Chunk-specific notes

**04A.** Eating already happens automatically whenever food is within reach, so a third "forage" output would add a decision with nothing to decide. The chunk allows a simpler 2-output network (turn and throttle) if it is recorded as a decision; that is the plan. "Heading" as an input means little in a world without a sense of position, so the sensor list is proposed in the Milestone 4 plan and fixed by a decision-log entry.

**04B.** Experiment E007, pre-registered in `docs/experiments/` before it runs, like E001–E006. The optional PyTorch cross-check is a separate yes/no question, because PyTorch is a large dependency.

**05A/05B.** The browser lab follows the user's global design rules (no default Tailwind/shadcn look, no glassmorphism, no toasts, small components, data outside component files). The API drives the same `Simulation` object as the CLI; the browser never runs simulation rules.

**06B.** The default extension is A, two resource types, unless the user picks another.
