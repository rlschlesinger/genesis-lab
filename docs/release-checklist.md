# Release checklist: a clean demo

Before showing Genesis Lab to someone, or tagging a version, work through this list from a **fresh clone** on the demo machine. Each line says what to run and what must happen. Stop at the first failure.

## 1. Set up from nothing

- [ ] `git clone https://github.com/rlschlesinger/genesis-lab && cd genesis-lab`
- [ ] `uv sync` completes; `uv run genesis --help` lists `run`, `report`, `lake`, `sql`, `experiment`, `dashboard`, `inspect`, `serve`, `lab`.
- [ ] `cd web && npm ci && npm run build && cd ..` completes (Node 22).

## 2. Checks

- [ ] `uv run ruff check . && uv run ruff format --check .`: clean.
- [ ] `uv run pytest`: every test passes (exit status 0, checked on its own, never through a pipe). The SQL exercises skip without a lake; that's expected on a fresh clone.
- [ ] `uv run pytest -m slow`: passes.
- [ ] `cd web && npm run typecheck && npm test && cd ..`: both pass.
- [ ] `uv run pytest tests/test_regression.py`: golden values pass on this platform (Darwin arm64 and Linux x86_64 are recorded; another platform needs its own, D-027).

## 3. Reproduce the science

On a fresh clone the lake is empty; the experiments re-create it (E002–E006 take longest; E007–E009 a few minutes each on a recent laptop):

- [ ] Each experiment's script, in order: `uv run python experiments/e001_controller_comparison.py` through `e006_founders_extinction.py`, then `e007_neuroevolution.py`, `e008_evasion.py`, `e009_specialisation.py` (each runs what its spec in `experiments/specs/` lists, then analyses).
- [ ] Each script's `--analyse-only` output matches the numbers in its definition's Results section (on the platform that produced them; see the replication note in E007 for Linux).
- [ ] `uv run genesis lake ingest data/runs data/experiments` reports no refusals.
- [ ] `uv run python scripts/build_sql_exercises.py` leaves `docs/sql-exercises.md` unchanged apart from counts of runs added since.

## 4. The lab, by hand

- [ ] `uv run genesis lab --open`, then [e2e-checklist.md](e2e-checklist.md) in Chrome, every item, including the six marked "not yet checked by hand" (real mouse, reduced motion).
- [ ] The three worlds worth showing, each for a minute at speed: `neural` (brains evolving to forage), `predators` (chasers, captures, the phase plot in Analytics), `diets` (two foods; organisms turning the colour of their food).

## 5. The story

- [ ] [README.md](../README.md) reads correctly top to bottom for a newcomer: what it is, setup, the first run, the lab, the experiments table.
- [ ] The experiments table links each of E001–E009 and states its result in one line, nulls included.
- [ ] `git status` is clean; every run used for a result recorded `git_dirty: false`.
- [ ] Optionally tag the release, for example `git tag v0.6.0 && git push --tags` (no tags exist yet; one per completed milestone would be a simple scheme).
