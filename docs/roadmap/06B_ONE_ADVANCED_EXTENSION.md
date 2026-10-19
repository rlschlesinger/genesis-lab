# Chunk 06B — One research extension, not four

Choose **exactly one** extension after discussing the user’s priorities. If the user does not express a preference, default to a **two-resource ecological specialization** experiment; this is better for measuring divergent adaptation than adding a lot of unrelated features.

## Choose ONE
A. Two resource types with different handling costs/nutrient returns; test whether specialists emerge.
B. Energy sharing with explicit cost, partner detection and tests of cooperation vs freeloading.
C. Seasonal environmental variation and adaptation to periodic scarcity.
D. NEAT topology evolution using compatible stable `neat-python`, *only* if existing fixed-topology experiments are robust.

## Process
1. Before code, write one-page proposal covering hypothesis, independent variable, control, mechanism, metrics, expected confounders, fixed environmental settings, and comparison run counts.
2. Implement minimal mechanics isolated behind documented interfaces, with tests for new invariants and schema version changes.
3. Run 10–20 independent replicates per condition if practical; record actual counts and reproducibility metadata.
4. Interpret effect size and uncertainty; identify alternative explanations; do not claim emerging 'cooperation', 'species', or 'intelligence' based only on visualization.
5. Create `docs/RESEARCH_ROADMAP.md` with two future extensions as ideas only, and a release checklist for a clean demo.

## Acceptance
One extension is implemented, tested, and used in a reproducible experimental report. A local newcomer can launch the app and follow the research story. Stop and summarize all six milestones; do not start new features without authorization.
