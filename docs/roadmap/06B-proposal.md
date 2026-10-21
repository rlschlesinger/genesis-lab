# 06B proposal: two foods, and whether specialists emerge

**Status:** proposed 2026-10-21 for the user's approval (06B process, step 1). No code yet. Extension A of [06B](06B_ONE_ADVANCED_EXTENSION.md), chosen by the user.

## Question and hypothesis

When a world offers two kinds of food, and an organism can't be good at both, does one population split into two kinds of specialist?

**Hypothesis (to be pre-registered as E009):** with a trade-off that makes a generalist worse at both foods than a specialist is at one, the heritable **diet** gene, starting at 0.5 in every founder, spreads out and splits into two groups, one near each end. Without a trade-off, it only drifts.

## Mechanism (minimal, behind documented interfaces)

- **Two food kinds, A and B,** equally likely, placed uniformly at random (no habitats: any split can't come from geography). Each item's kind is drawn from a new random stream, so food positions are exactly as before.
- **A diet gene `d` in [0, 1]**, inherited and mutated like the other genes (same rate, step size and reflection at the bounds). One meal of A gives `V × (1 − d)^k` energy; one of B gives `V × d^k`. **`k` sets the trade-off:** with k = 2, a generalist (d = 0.5) gets a quarter of V from either food, while a specialist (d = 0 or 1) gets all of V from its own and nothing from the other.
- **Choosing food:** a new rule-based controller, `diet_seeker`, senses the nearest item of *each* kind and turns toward whichever offers more energy per unit of distance, given its own `d`. Otherwise it is the food seeker. It eats whatever it reaches (wrong-kind meals give little or nothing, and the item is gone).
- **Why choice matters:** specialists that leave the other food alone keep it plentiful for the other specialists. That rarity advantage (*negative frequency dependence*) is what can keep two specialist groups coexisting, rather than one winning by chance.
- **Compatibility:** the diet is an optional heritable value, like the brain (D-041), switched on by a new optional `resources:` config section. Every existing config, hash and file stays identical. A new random stream is appended at the end. Run-folder version 6 adds a file of diets per organism and meals per food kind per tick; the lake gets matching tables; the lab draws the two foods differently and shades organisms by diet.

## Independent variable and controls

| Condition | Meal energy | Role |
|---|---|---|
| `tradeoff` | A: `V(1−d)²`, B: `Vd²` (k = 2) | the test |
| `neutral` | every meal gives `V/4`, whatever `d` | **control:** diet has no effect, so it only drifts. Founders gain exactly what they gain in `tradeoff`, so both worlds start alike. |
| `linear` | A: `V(1−d)`, B: `Vd` (k = 1) | secondary: generalists are exactly as good on average as specialists; does the trade-off's *shape* matter, or any trade-off? |

`V` is chosen by labelled tuning pilots so that generalist founders survive in every condition; the pilots don't look at the diet's spread.

## Metrics (to be fixed in E009's definition)

- **Primary:** the standard deviation of `d` among organisms alive at the end (spread). `tradeoff` vs `neutral`, paired by seed.
- **Dimorphism:** a world counts as *split* if at least 10% of survivors have `d` < 0.2 *and* at least 10% have `d` > 0.8. The number of split worlds is compared per condition.
- **Realised diet:** each organism's share of meals of its better kind, which shows whether organisms actually eat as their gene says.
- **Descriptive:** the diet's distribution over time (charts and the lab), population size, meals per kind.

## Expected confounders

- **Drift:** genes wander by chance, more in small populations. The `neutral` control measures exactly that, and population size is reported.
- **Choice is designed, not evolved.** The rule follows the gene; what evolves is the gene, not the preference. That's deliberate (E008 showed small brains evolve behaviour slowly). Evolving the choice with brains is a possible E010.
- **Population size differs by condition** (a trade-off may support fewer organisms), which changes drift strength. Reported, and the dimorphism rule needs both groups present.
- **Wrong-kind meals** waste food. Their count is recorded.
- **Mutation at the bounds** reflects (D-019), so values don't pile up at 0 or 1 by construction.
- **One world family:** results hold for these settings only.

## Fixed settings

`evolution.yaml`'s world (200 × 200, 2 food items per tick, at most 300) and costs, with the food seeker's body. **Only the diet gene evolves; the other expressed genes are frozen,** so any change comes from diet alone. No predators, no brains, 100 founders, 20,000 ticks.

## Runs

3 conditions × **20 seeds** (10000–10019, never used) × 20,000 ticks = 60 runs, plus labelled pilots (seeds 90100+) to choose `V`. Unit of analysis: the world. Based on E008's runs, a few minutes on this Mac.

## Then (06B steps 2–5)

Implement and test the mechanics and schema version; pilots; E009 definition committed before running; run; interpret with effect sizes and alternatives; write `docs/RESEARCH_ROADMAP.md` (two future ideas only) and a release checklist; summarise all six milestones and stop.

## Decisions for the user

1. **Rule-based organisms with a diet gene** (recommended: clear and likely to show something) versus neural organisms that see food kinds (richer, but E008 suggests evolution may be too slow to show anything).
2. **Three conditions** (recommended; `linear` asks whether the trade-off's shape matters) versus only `tradeoff` and `neutral` (simpler, fewer runs).
3. **Lab support** (recommended: two food colours and organisms shaded by diet, so you can watch a split happen) versus headless only.
