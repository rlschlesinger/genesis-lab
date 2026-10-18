# Genesis Lab: instructions for Claude Code sessions

## What this project is

An artificial life research platform built incrementally as a teaching project. The user is a technically curious beginner in Python, SQL and ML. Understanding matters as much as working code.

## Working rules

- **Milestone gating:** never start a new milestone without explicit user approval. Current: Milestone 1 (The Petri Dish). Stop after each numbered increment (see docs/architecture.md, "Milestone 1 plan").
- **Teaching loop for every substantial change:** problem → concept → proposed implementation → smallest useful increment → demonstrate → how to inspect/test → one small exercise → ask to proceed.
- **New dependencies:** explain why, name alternatives, add it in the increment that first needs it. Record significant ones in docs/decision-log.md.
- **Do not commit or push** unless the user asks.
- **Never fabricate results.** Report what runs actually produced; separate observation from interpretation.
- After each milestone, update README.md, this file, and all of docs/.

## Commands

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Simulation invariants (do not break)

- **Determinism:** same config + seed + environment → identical output. All randomness comes from `numpy.random.Generator` streams spawned from one `SeedSequence` per run, one stream per subsystem, in fixed order (setup, food, controller, reproduction, tiebreak); new streams are appended only at the end. Never use `random`, `np.random.<function>` global state, or iterate over sets/unordered collections in simulation code. Organisms are processed in ascending ID order.
- **Snapshot observation:** all organisms observe the same frozen world state before any action is applied.
- **Newborns** are inactive until the tick after their birth.
- **Food contention:** the closest organism wins; exact ties are broken with the tiebreak stream (never by ID, which would bias toward older lineages).
- **Energy ledger:** initial + inflow − outflow == current total, checked in tests.
- **Separation of concerns:** controllers are pure (observation → action) and never mutate the world; metrics are read-only.
- **Boundaries:** hard walls (positions clamped), not wrap-around.

## Code conventions

- src layout; package name `genesis`, distribution `genesis-lab`.
- Python 3.12, ruff (line length 100), type hints on public functions.
- Tests live in `tests/`, mirroring the module they cover.
- Generated data goes in `data/` (Git-ignored).
- UI work (Milestone 5) follows the user's global anti-vibe-code design rules.
