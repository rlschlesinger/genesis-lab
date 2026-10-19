# SQL examples

Every query here runs against the lake (`tests/lake/test_db.py` executes each one, so they can't go out of date). Run one from the terminal:

```bash
uv run genesis sql "SELECT experiment_id, count(*) FROM runs GROUP BY experiment_id"
```

Tables and columns are described in [schema.md](schema.md) and the [data dictionary](data-dictionary.md). Exercises to try yourself are in 3.9.

---

## 1 · SELECT and GROUP BY: how many runs, of what kind?

`GROUP BY` collapses rows that share the listed values into one row each; `count(*)` counts the rows in each group.

```sql
SELECT experiment_id, schema_version, status, count(*) AS runs
FROM runs
GROUP BY experiment_id, schema_version, status
ORDER BY experiment_id NULLS LAST;
```

## 2 · WHERE: filter rows before anything else

`WHERE` keeps only rows matching a condition. `completed_runs` is a view that already applies `WHERE status = 'completed'`, so analyses start there.

```sql
SELECT run_id, condition, seed, food_regrowth, mutation_rate
FROM run_params
WHERE experiment_id = 'E003'
  AND mutation_enabled
  AND food_regrowth < 2
ORDER BY condition, seed
LIMIT 10;
```

## 3 · JOIN: time series meets lineage

How big was the population when each organism was born? The join condition matches **both** the run and the tick. Leave out the run and every organism matches that tick in every run (example 8).

```sql
SELECT o.run_id, o.organism_id, o.generation, o.birth_tick,
       t.population AS population_at_birth
FROM organisms AS o
JOIN ticks AS t
  ON t.run_id = o.run_id
 AND t.tick   = o.birth_tick
WHERE o.parent_id IS NOT NULL
ORDER BY o.run_id, o.organism_id
LIMIT 10;
```

## 4 · GROUP BY over a macro: E003's measurement in SQL

`settled_gene_means(19000, 19999)` is a table macro (a view with parameters). This reproduces E003's per-condition medians.

```sql
SELECT p.condition,
       count(*)                     AS runs,
       median(s.settled_mean)       AS median_settled_sense_range
FROM settled_gene_means(19000, 19999) AS s
JOIN run_params AS p USING (run_id)
WHERE p.experiment_id = 'E003'
  AND s.gene = 'sense_range'
GROUP BY p.condition
ORDER BY p.condition;
```

## 5 · Window functions: compare each row with its neighbours

A **window function** computes a value from *other rows related to this one* without collapsing them (unlike `GROUP BY`). `PARTITION BY run_id` restarts the calculation for each run; `ORDER BY tick` defines "previous" and "next".

```sql
SELECT run_id, tick, population,
       population - lag(population) OVER w                      AS change_since_last_row,
       avg(population) OVER (w ROWS BETWEEN 99 PRECEDING AND CURRENT ROW) AS rolling_mean_100
FROM ticks
WHERE run_id = (SELECT min(run_id) FROM completed_runs)
WINDOW w AS (PARTITION BY run_id ORDER BY tick)
ORDER BY tick
LIMIT 10;
```

## 6 · Window functions: the top row per group

The largest founder family in each run. `row_number()` numbers rows within each run, biggest first; `QUALIFY` filters on a window function's result (like `WHERE`, but evaluated after windows).

```sql
SELECT run_id, founder_id, born, alive_at_end
FROM lineage_sizes
QUALIFY row_number() OVER (PARTITION BY run_id ORDER BY born DESC, founder_id) = 1
ORDER BY born DESC
LIMIT 10;
```

## 7 · WITH RECURSIVE: a family history

Start from the organism with the highest generation in one run, then repeatedly join to its parent until reaching a founder. Each pass of the recursive part adds one generation further back.

```sql
WITH RECURSIVE
start AS (
    SELECT run_id, organism_id
    FROM organisms
    WHERE run_id = (SELECT min(run_id) FROM completed_runs)
    ORDER BY generation DESC, organism_id
    LIMIT 1
),
ancestry AS (
    SELECT o.run_id, o.organism_id, o.parent_id, o.generation, 0 AS steps_back
    FROM organisms AS o JOIN start USING (run_id, organism_id)
    UNION ALL
    SELECT o.run_id, o.organism_id, o.parent_id, o.generation, a.steps_back + 1
    FROM organisms AS o
    JOIN ancestry AS a
      ON o.run_id = a.run_id
     AND o.organism_id = a.parent_id
)
SELECT * FROM ancestry ORDER BY steps_back;
```

## 8 · The fan-out mistake (on purpose)

The same join as example 3, without `t.run_id = o.run_id`. Each organism now matches its birth tick in *every* run that reached it. Compare the two counts: the wrong join is valid SQL and silently returns many times more rows.

```sql
SELECT
    (SELECT count(*) FROM organisms AS o
       JOIN ticks AS t ON t.run_id = o.run_id AND t.tick = o.birth_tick
      WHERE o.run_id = (SELECT min(run_id) FROM completed_runs))   AS correct_rows,
    (SELECT count(*) FROM organisms AS o
       JOIN ticks AS t ON t.tick = o.birth_tick
      WHERE o.run_id = (SELECT min(run_id) FROM completed_runs))   AS fan_out_rows;
```

## 9 · Events: where do organisms die?

Only runs that logged events have rows here. Grouping death positions into a 4 × 4 grid of 50-unit cells shows whether deaths cluster (for example, against walls).

```sql
SELECT floor(x / 50)::INTEGER AS cell_x,
       floor(y / 50)::INTEGER AS cell_y,
       count(*)               AS deaths
FROM events
WHERE kind = 'death'
GROUP BY cell_x, cell_y
ORDER BY deaths DESC
LIMIT 8;
```
