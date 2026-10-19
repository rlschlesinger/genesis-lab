# SQL exercises

Ten questions about the simulated populations in the lake (E001–E006), from simple filters to window functions and recursion. Answers are at the bottom; each shows the query and the result it gives on the current lake.

**Run a query:**

```bash
uv run genesis sql "SELECT ... ;"
```

or paste it into DuckDB after `uv run genesis lake rebuild-db` (`duckdb data/genesis.duckdb`).

**Two rules that apply to every exercise:**

1. **Join on `run_id`.** Organism and tick numbers repeat in every run; forgetting `run_id` silently mixes runs (example 8 in [sql-examples.md](sql-examples.md)).
2. **The run is the unit of analysis.** When a question is about conditions, summarize each run first, then compare runs.

Tables and columns: [schema.md](schema.md), [data-dictionary.md](data-dictionary.md). Worked examples: [sql-examples.md](sql-examples.md).

---

## 1 · Runs and extinctions

How many completed runs does each experiment have, and how many of them went extinct?

**Hint:** `completed_runs`, `GROUP BY`, and `count(*) FILTER (WHERE ...)` to count only some rows of each group. Leave out runs with no experiment (`experiment_id IS NOT NULL`).

## 2 · The biggest populations

Which three runs, across all experiments, ended with the largest populations? Give experiment, condition, seed and final population.

**Hint:** `ORDER BY ... DESC` and `LIMIT`. The column you need is in `runs`.

## 3 · Organisms per controller

In E001, how many organisms ever lived per run, on average, for each controller?

**Hint:** `organisms_ever` in `completed_runs`; the condition label is the controller's name. `round(x, 1)` keeps the output short.

## 4 · Age at death, per run first

In E003, what is the typical age at death in each condition?

**Hint:** **Unit of analysis.** Organisms in one run aren't independent replicates, so don't average all organisms together. First average age at death **per run** (a `WITH` sub-query over `organisms WHERE NOT alive`), then take the median of those run averages per condition (`JOIN` to `completed_runs` for the condition).

## 5 · Genetic diversity at the end

In E002, how much variation in the neutral marker is left at the final tick, per condition? Use the median across runs of the marker's standard deviation.

**Hint:** `gene_stats` has an `sd` column per tick and gene. Join it to `completed_runs` on `run_id` **and** on the final tick (`g.tick = r.ticks_run - 1`).

## 6 · Fastest growth spurt

In E001, what is each run's largest one-tick population increase? Report the median of that per controller.

**Hint:** A window function: `population - lag(population) OVER (PARTITION BY run_id ORDER BY tick)` is the change since the previous tick. Take the `max` per run, then the `median` per condition.

## 7 · The top seed per condition

In E003, which seed had the highest settled sense range in each condition, and what was it?

**Hint:** `settled_gene_means(19000, 19999)` gives one row per run and gene. `row_number() OVER (PARTITION BY ... ORDER BY ... DESC) = 1` inside `QUALIFY` keeps the top row of each group.

## 8 · Mutations along one family line

In E002's selection run with seed 1000, take the organism with the highest generation (lowest ID if tied). How many organisms are in its line back to its founder (itself included), and how many of them were born with a metabolic_rate mutation?

**Hint:** `WITH RECURSIVE` (see example 7 in sql-examples.md), then a `LEFT JOIN` to `mutations` on `run_id`, `child_id` and `gene`. A `LEFT JOIN` keeps organisms with no matching mutation; `count(m.child_id)` counts only the matches.

## 9 · Surviving founder families

In E002, how many of the 30 founder lineages are still alive at the end of a run? Give the median, fewest and most per condition.

**Hint:** `ticks.lineages` at the final tick. Same final-tick join as exercise 5.

## 10 · Checking the design from the data

Confirm from the recorded configs alone that E003's conditions used the intended food levels, all with mutation on, and 20 runs each.

**Hint:** `run_params` turns config values into columns. `any_value(...)` takes one value per group; `bool_and(...)` is true only if every row is true.


---

*Answers below. Try each exercise first.*



---

# Answers

### Answer 1 · Runs and extinctions

```sql
SELECT experiment_id,
       count(*)                                       AS completed_runs,
       count(*) FILTER (WHERE stop_reason = 'extinction') AS extinct
FROM completed_runs
WHERE experiment_id IS NOT NULL
GROUP BY experiment_id
ORDER BY experiment_id;
```

```text
experiment_id  completed_runs  extinct
-------------  --------------  -------
E001                       20        0
E002                       60        0
E003                       80        0
E004                       40        0
E005                       40        0
E006                      250      162
```

Only E006 has extinctions (162 of 250 runs), by design: its harsh world (no starting food, regrowth 0.1) was chosen by pilots so that extinction happens. Every other experiment kept all its runs.

### Answer 2 · The biggest populations

```sql
SELECT experiment_id, condition, seed, final_population
FROM completed_runs
WHERE experiment_id IS NOT NULL
ORDER BY final_population DESC
LIMIT 3;
```

```text
experiment_id  condition  seed  final_population
-------------  ---------  ----  ----------------
E004           food_4     4008               230
E004           food_4     4009               225
E004           food_4     4000               218
```

All three come from E004's highest food level (4 items per tick), as E004 found: population is proportional to food, so four times the food supports about four times as many organisms. The question says "across all experiments", so the answer changes as experiments are added.

### Answer 3 · Organisms per controller

```sql
SELECT condition AS controller,
       count(*)                      AS runs,
       round(avg(organisms_ever), 1) AS mean_organisms_ever
FROM completed_runs
WHERE experiment_id = 'E001'
GROUP BY condition
ORDER BY condition;
```

```text
controller           runs  mean_organisms_ever
-------------------  ----  -------------------
nearest_food_seeker    10               1244.2
random_walk            10               1392.4
```

Seekers lived through fewer organisms than random walkers, consistent with the slightly lower carrying capacity found in E001.

### Answer 4 · Age at death, per run first

```sql
WITH per_run AS (
    SELECT o.run_id, avg(o.age) AS mean_age_at_death
    FROM organisms AS o
    WHERE NOT o.alive
    GROUP BY o.run_id
)
SELECT r.condition,
       count(*)                                   AS runs,
       round(median(p.mean_age_at_death), 1)      AS median_of_run_means
FROM per_run AS p
JOIN completed_runs AS r ON r.run_id = p.run_id
WHERE r.experiment_id = 'E003'
GROUP BY r.condition
ORDER BY r.condition;
```

```text
condition  runs  median_of_run_means
---------  ----  -------------------
N_plenty     20                364.7
N_scarce     20                358.1
S_plenty     20                399.1
S_scarce     20                376.4
```

Descriptively, organisms under selection live longer (399 and 376 ticks vs 365 and 358 under drift); this is not a pre-registered test. Averaging per run first matters: runs with more deaths would otherwise dominate the result.

### Answer 5 · Genetic diversity at the end

```sql
SELECT r.condition,
       round(median(g.sd), 4) AS median_final_marker_sd
FROM gene_stats AS g
JOIN completed_runs AS r
  ON r.run_id = g.run_id
 AND g.tick = r.ticks_run - 1
WHERE r.experiment_id = 'E002'
  AND g.gene = 'neutral_marker'
GROUP BY r.condition
ORDER BY r.condition;
```

```text
condition  median_final_marker_sd
---------  ----------------------
neutral                    0.0727
off                             0
selection                  0.0585
```

With mutation off there is no variation at all (0). Selection leaves less marker variation than drift alone: sweeps carry neutral genes along with selected ones (hitchhiking).

### Answer 6 · Fastest growth spurt

```sql
WITH growth AS (
    SELECT t.run_id, r.condition,
           t.population - lag(t.population) OVER (PARTITION BY t.run_id ORDER BY t.tick) AS change
    FROM ticks AS t
    JOIN completed_runs AS r ON r.run_id = t.run_id
    WHERE r.experiment_id = 'E001'
)
SELECT condition,
       median(max_jump) AS median_largest_one_tick_jump
FROM (SELECT run_id, condition, max(change) AS max_jump FROM growth GROUP BY run_id, condition)
GROUP BY condition
ORDER BY condition;
```

```text
condition            median_largest_one_tick_jump
-------------------  ----------------------------
nearest_food_seeker                             4
random_walk                                     3
```

The biggest jump in a single tick is small (3–4 organisms) because each parent has at most one child per tick.

### Answer 7 · The top seed per condition

```sql
SELECT r.condition, r.seed, round(s.settled_mean, 2) AS settled_sense_range
FROM settled_gene_means(19000, 19999) AS s
JOIN completed_runs AS r ON r.run_id = s.run_id
WHERE r.experiment_id = 'E003'
  AND s.gene = 'sense_range'
QUALIFY row_number() OVER (PARTITION BY r.condition ORDER BY s.settled_mean DESC) = 1
ORDER BY r.condition;
```

```text
condition  seed  settled_sense_range
---------  ----  -------------------
N_plenty   2016                30.28
N_scarce   2010                36.98
S_plenty   2010                25.64
S_scarce   2011                31.34
```

Careful: the top seed is not the typical seed. The drift-only conditions have the highest single values (36.98 in N_scarce) although their medians (~20) are lower than S_scarce's (26.4): their runs are more spread out, and the maximum of a wider spread is higher. Extremes describe spread, not the centre.

### Answer 8 · Mutations along one family line

```sql
WITH RECURSIVE
target AS (
    SELECT o.run_id, o.organism_id
    FROM organisms AS o
    JOIN completed_runs AS r ON r.run_id = o.run_id
    WHERE r.experiment_id = 'E002' AND r.condition = 'selection' AND r.seed = 1000
    ORDER BY o.generation DESC, o.organism_id
    LIMIT 1
),
ancestry AS (
    SELECT o.run_id, o.organism_id, o.parent_id
    FROM organisms AS o JOIN target USING (run_id, organism_id)
    UNION ALL
    SELECT o.run_id, o.organism_id, o.parent_id
    FROM organisms AS o
    JOIN ancestry AS a ON o.run_id = a.run_id AND o.organism_id = a.parent_id
)
SELECT count(*)                                   AS organisms_in_line,
       count(m.child_id)                          AS metabolic_rate_mutations
FROM ancestry AS a
LEFT JOIN mutations AS m
  ON m.run_id = a.run_id
 AND m.child_id = a.organism_id
 AND m.gene = 'metabolic_rate';
```

```text
organisms_in_line  metabolic_rate_mutations
-----------------  ------------------------
               77                         7
```

7 of the 76 births in this line (the founder has no birth) changed metabolic_rate, close to the 7.6 that a 10% chance per birth predicts. Selection decides which lines survive, not how often mutations happen.

### Answer 9 · Surviving founder families

```sql
SELECT r.condition,
       median(t.lineages) AS median_founder_lineages_at_end,
       min(t.lineages)    AS fewest,
       max(t.lineages)    AS most
FROM ticks AS t
JOIN completed_runs AS r
  ON r.run_id = t.run_id
 AND t.tick = r.ticks_run - 1
WHERE r.experiment_id = 'E002'
GROUP BY r.condition
ORDER BY r.condition;
```

```text
condition  median_founder_lineages_at_end  fewest  most
---------  ------------------------------  ------  ----
neutral                                 2       1     3
off                                     2       1     3
selection                               1       1     2
```

Selection runs usually end with a single founder family, while drift-only and mutation-off runs keep about two. That suggests selection speeds up the loss of lineages (descriptive, 20 runs per condition, not a pre-registered test).

### Answer 10 · Checking the design from the data

```sql
SELECT condition,
       any_value(food_regrowth)         AS food_regrowth,
       bool_and(mutation_enabled)       AS mutation_on,
       count(*)                         AS runs
FROM run_params
WHERE experiment_id = 'E003' AND status = 'completed'
GROUP BY condition
ORDER BY condition;
```

```text
condition  food_regrowth  mutation_on  runs
---------  -------------  -----------  ----
N_plenty               2  True           20
N_scarce               1  True           20
S_plenty               2  True           20
S_scarce               1  True           20
```

The data confirms the design: regrowth 2 for plentiful and 1 for scarce, mutation on everywhere, 20 runs per condition. Checking the design from recorded data catches mistakes in how an experiment was set up.
