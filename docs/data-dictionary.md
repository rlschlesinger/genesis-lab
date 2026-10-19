# Data dictionary

Status: **implemented.** Run-folder fields (3.1) and lake tables (3.2, `src/genesis/lake/tables.py`) follow this dictionary; the ETL enforces it. See [schema.md](schema.md) for how the tables relate.

**Conventions**

- **Types** are DuckDB types: `INTEGER` (whole number), `DOUBLE` (64-bit decimal number), `BOOLEAN`, `VARCHAR` (text), `TIMESTAMP` (microseconds, UTC), `JSON` (stored in Parquet as text; read with DuckDB's JSON functions). The Arrow equivalents are in `src/genesis/lake/tables.py`.
- **Units:** `tick` (simulation time step), `wu` (world unit of distance), `EU` (energy unit), `rad` (radians), `—` (count or no unit).
- **NULL** means "no value / unknown". The *Null when* column says when a NULL is legitimate; anywhere else, the ETL rejects the run.
- **PK** = part of the primary key. **FK** = refers to another table.
- **Since** = the run-folder schema version that first contains the column. Older runs have NULL there.

---

## `experiments`

One row per experiment. Source: the definition documents `docs/experiments/E*.md`, read each time the database connects (`lake/db.py`); `defined_at_commit` comes from git history.

| Column | Type | Unit | Key | Null when | Meaning |
|---|---|---|---|---|---|
| `experiment_id` | VARCHAR | — | PK | never | Short ID, e.g. `E003` |
| `title` | VARCHAR | — | | never | One-line question |
| `definition_path` | VARCHAR | — | | never | Path of the pre-registered definition, e.g. `docs/experiments/E003-food-scarcity.md` |
| `defined_at_commit` | VARCHAR | — | | unknown | Git commit that added the definition (proves it predates the runs) |

## `runs`

One row per simulation run, including failed ones. Source: `run.json`.

| Column | Type | Unit | Key | Since | Null when | Meaning |
|---|---|---|---|---|---|---|
| `run_id` | VARCHAR | — | PK | 1 | never | Unique ID, e.g. `20261019T004230Z-s42-1c98e3` |
| `experiment_id` | VARCHAR | — | FK → experiments | 1 | run not part of an experiment | Experiment this run belongs to |
| `condition` | VARCHAR | — | | 3 (derived for 1–2) | not part of an experiment | Condition label, e.g. `S_scarce`. Versions 1–2: derived from the folder name |
| `condition_derived` | BOOLEAN | — | | — | never | True if `condition` came from the folder name rather than `run.json` |
| `seed` | INTEGER | — | | 1 | never | Run seed (`run.seed`) |
| `status` | VARCHAR | — | | 1 | never | `completed`, `failed` or `running` (a run that never finished) |
| `schema_version` | INTEGER | — | | 3 (inferred for 1–2) | never | Run-folder format; see schema.md |
| `config_hash` | VARCHAR | — | | 3 (computed for 1–2) | never | SHA-256 of the canonical config JSON: identical configs ⇔ identical hash |
| `config` | JSON | — | | 1 | never | The full validated config the run used |
| `git_commit` | VARCHAR | — | | 1 | git unavailable | Code version |
| `git_dirty` | BOOLEAN | — | | 1 | git unavailable | True if the code had uncommitted changes (commit alone doesn't describe it) |
| `python_version` | VARCHAR | — | | 1 | never | e.g. `3.12.13` |
| `numpy_version` | VARCHAR | — | | 1 | never | e.g. `2.5.4` |
| `platform` | VARCHAR | — | | 1 | never | Operating system string |
| `machine` | VARCHAR | — | | 1 | never | CPU architecture, e.g. `arm64` (decides float bits, D-027) |
| `started_at` | TIMESTAMP | — | | 1 | never | UTC |
| `finished_at` | TIMESTAMP | — | | 1 | status = running | UTC |
| `duration_seconds` | DOUBLE | s | | 1 | status = running | Wall-clock time |
| `ticks_run` | INTEGER | tick | | 1 | status ≠ completed | Ticks simulated |
| `stop_reason` | VARCHAR | — | | 1 | status ≠ completed | `max_ticks` or `extinction` |
| `final_population` | INTEGER | — | | 1 | status ≠ completed | Living organisms at the end |
| `organisms_ever` | INTEGER | — | | 1 | status ≠ completed | Organisms that ever lived |
| `mutations` | INTEGER | — | | 2 | version 1; status ≠ completed | Gene changes recorded |
| `final_state_digest` | VARCHAR | — | | 1 | status ≠ completed | SHA-256 of the final state (D-020; platform-specific, D-027) |
| `failed_at_tick` | INTEGER | tick | | 1 | status ≠ failed | Tick at which the run failed |
| `error` | VARCHAR | — | | 1 | status ≠ failed | Exception type and message |
| `ticks_every` | INTEGER | tick | | 3 (1 for older) | never | Sampling interval of `ticks` and `gene_stats` rows |
| `events_recorded` | VARCHAR | — | | 3 | never | Which event kinds were logged, e.g. `birth,death` or empty |

## `ticks`

One row per recorded tick (every `ticks_every` ticks, plus the final tick). Source: `ticks.csv`.

**Stocks vs flows.** *Stock* columns (`population`, `food_count`, `mean_energy`, `lineages`) are a snapshot at the end of the recorded tick. *Flow* columns (`births`, `deaths`, `food_spawned`, `food_eaten`, `mutations`) are **totals since the previous recorded row**, so summing a flow column over a run gives the true total at any `ticks_every` (D-028). With `ticks_every` = 1 (the default) each row describes exactly one tick.

| Column | Type | Unit | Key | Since | Null when | Meaning |
|---|---|---|---|---|---|---|
| `run_id` | VARCHAR | — | PK, FK → runs | 1 | never | |
| `tick` | INTEGER | tick | PK | 1 | never | Time step, from 0 |
| `population` | INTEGER | — | | 1 | never | Living organisms at the end of the tick, including newborns |
| `births` | INTEGER | — | | 1 | never | Newborns since the previous row (flow) |
| `deaths` | INTEGER | — | | 1 | never | Deaths since the previous row (flow) |
| `food_count` | INTEGER | — | | 1 | never | Uneaten food items at the end of the tick |
| `food_spawned` | INTEGER | — | | 1 | never | Items that appeared since the previous row (flow) |
| `food_eaten` | INTEGER | — | | 1 | never | Items eaten since the previous row (flow) |
| `mean_energy` | DOUBLE | EU | | 1 | population = 0 | Mean energy of the living population |
| `lineages` | INTEGER | — | | 1 | never | Distinct founder lineages alive |
| `mutations` | INTEGER | — | | 2 | version 1 | Gene changes among newborns since the previous row (flow) |

## `gene_stats`

One row per (sampled) tick per gene, over the living population. Source: `gene_stats.csv`. Not present for version 1.

| Column | Type | Unit | Key | Null when | Meaning |
|---|---|---|---|---|---|
| `run_id` | VARCHAR | — | PK, FK → runs | never | |
| `tick` | INTEGER | tick | PK | never | |
| `gene` | VARCHAR | — | PK | never | One of `speed`, `sense_range`, `max_turn`, `metabolic_rate`, `reproduction_threshold`, `neutral_marker` |
| `n` | INTEGER | — | | never | Organisms summarized (= population) |
| `mean` | DOUBLE | gene unit | | n = 0 | Mean value |
| `sd` | DOUBLE | gene unit | | n = 0 | Population standard deviation (divides by n) |
| `min` | DOUBLE | gene unit | | n = 0 | Smallest value |
| `max` | DOUBLE | gene unit | | n = 0 | Largest value |

**Gene units:** speed `wu/tick`; sense_range `wu`; max_turn `rad/tick`; metabolic_rate `EU/tick`; reproduction_threshold `EU`; neutral_marker `—`.

## `genomes`

Every living organism's genes at snapshot ticks (every `recording.genome_snapshot_every` ticks, and the final tick). Source: `genomes.csv`. Not present for version 1.

| Column | Type | Unit | Key | Null when | Meaning |
|---|---|---|---|---|---|
| `run_id` | VARCHAR | — | PK, FK → runs | never | |
| `tick` | INTEGER | tick | PK | never | Snapshot tick |
| `organism_id` | INTEGER | — | PK, FK → organisms | never | `id` in the CSV |
| `gene_speed` … `gene_neutral_marker` | DOUBLE | gene unit | | never | One column per gene (6), the genotype |

## `organisms`

One row per organism that ever lived in a run. Source: `organisms.csv`.

| Column | Type | Unit | Key | Since | Null when | Meaning |
|---|---|---|---|---|---|---|
| `run_id` | VARCHAR | — | PK, FK → runs | 1 | never | |
| `organism_id` | INTEGER | — | PK | 1 | never | `id` in the CSV; unique within a run only |
| `parent_id` | INTEGER | — | FK → organisms (same run) | 1 | founders | Parent's `organism_id` |
| `founder_id` | INTEGER | — | FK → organisms (same run) | 1 | never | Founding ancestor (itself, for a founder) |
| `generation` | INTEGER | — | | 1 | never | 0 for founders; parent's + 1 |
| `birth_tick` | INTEGER | tick | | 1 | never | Tick of birth (0 for founders, who act from tick 0; newborns act from birth_tick + 1) |
| `death_tick` | INTEGER | tick | | 1 | still alive | Tick of death |
| `death_cause` | VARCHAR | — | | 1 | still alive | `starvation` or `old_age` |
| `alive` | BOOLEAN | — | | 1 | never | Alive at the end of the run |
| `age` | INTEGER | tick | | 1 | never | Ticks survived |
| `final_energy` | DOUBLE | EU | | 1 | never | Energy at the end of the run, or at death |
| `food_eaten` | INTEGER | — | | 1 | never | Items eaten in its lifetime |
| `energy_gained` | DOUBLE | EU | | 1 | never | From food only |
| `energy_spent` | DOUBLE | EU | | 1 | never | Metabolism, sensing and movement |
| `energy_invested` | DOUBLE | EU | | 1 | never | Given to offspring plus reproduction overhead |
| `offspring_count` | INTEGER | — | | 1 | never | Children produced |
| `gene_*` (6 columns) | DOUBLE | gene unit | | 2 | version 1 | Genotype |
| `trait_*` (5 columns) | DOUBLE | gene unit | | 1 | never | Phenotype: expressed values (a `neutral` gene shows its initial value) |

## `mutations`

One row per gene change at a birth. Source: `mutations.csv`. Not present for version 1; empty when mutation is off.

| Column | Type | Unit | Key | Null when | Meaning |
|---|---|---|---|---|---|
| `run_id` | VARCHAR | — | PK, FK → runs | never | |
| `tick` | INTEGER | tick | | never | Birth tick |
| `parent_id` | INTEGER | — | FK → organisms | never | |
| `child_id` | INTEGER | — | PK, FK → organisms | never | |
| `gene` | VARCHAR | — | PK | never | Gene that changed |
| `before` | DOUBLE | gene unit | | never | Parent's value |
| `after` | DOUBLE | gene unit | | never | Child's value |

## `events` (new in 3.1; optional)

One row per logged event, when `recording.events` lists that kind. Source: `events.csv` (always written; header only when no kinds are logged). Within a tick, events appear in the order they happen: meals (step 5), deaths (step 6), births (step 7).

| Column | Type | Unit | Key | Null when | Meaning |
|---|---|---|---|---|---|
| `run_id` | VARCHAR | — | PK, FK → runs | never | |
| `tick` | INTEGER | tick | PK | never | When it happened |
| `seq` | INTEGER | — | PK | never | Order within the tick (0, 1, 2, …) |
| `kind` | VARCHAR | — | | never | `birth`, `death` or `meal` |
| `organism_id` | INTEGER | — | FK → organisms | never | Who: the newborn, the deceased, or the eater |
| `other_id` | INTEGER | — | FK → organisms | not a birth | The parent, for births |
| `energy` | DOUBLE | EU | | never | Births: energy given to the child. Deaths: energy held at death. Meals: energy gained |
| `x`, `y` | DOUBLE | wu | | never | Where it happened |
| `detail` | VARCHAR | — | | not a death | Cause of death |

## Checks the ETL performs (3.2)

For every run before loading it; a run failing any check is refused with a message naming the check:

1. Every primary key is unique.
2. Every foreign key points at an existing row (`organisms.parent_id`, `mutations.child_id`, `genomes.organism_id` …), within the same run.
3. Row counts are consistent: `ticks` has one row per tick that is a multiple of `ticks_every`, plus the final tick if it isn't one; flow totals in `ticks` equal the event counts when events were logged; `organisms` has `organisms_ever` rows; `mutations` has `mutations` rows.
4. Values are in range: counts ≥ 0, genes within their configured `[min, max]`, `alive` ⇔ `death_tick` is NULL.
5. Every column's type matches this dictionary.
