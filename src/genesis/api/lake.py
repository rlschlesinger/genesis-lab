"""Read-only views of the data lake for the browser lab's Compare view (D-055).

Completed runs in the lake (every experiment's, and live runs saved from the lab) can be
listed and their time series fetched in the same column shape as a live run's history
(api/history.py), so the lab draws both with the same charts.

One DuckDB connection is opened on first use and reused (opening one builds every view and
reads the experiment documents: ~0.25 s). A DuckDB connection must not be used by two threads
at once, so a lock serialises queries; routes run them in a worker thread so running
simulations never wait. Views read the Parquet files at query time, so runs ingested after
the connection opened (an export from the lab) appear without reconnecting.

Series use the history rule: flows summed per interval, stocks at its last recorded tick,
shares averaged. Runs recorded with ``ticks_every`` > 1 already sum flows between rows
(D-028), so intervals are whole multiples of ``ticks_every`` and sums stay exact. Unlike a
live run, a finished run's last, possibly partial, interval is included: it will never change.
"""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path

import duckdb

from genesis.lake.db import connect

POINT_SIZES = (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000)
MAX_POINTS = 600  # the lab's charts show about this many points (web/src/analytics/series.ts)


class LakeUnavailable(RuntimeError):
    """No lake at the configured path (nothing ingested yet)."""


class LakeReader:
    def __init__(self, lake: Path):
        self.lake = Path(lake)
        self._con: duckdb.DuckDBPyConnection | None = None
        self._lock = threading.Lock()

    def _query(self, sql: str, params: dict | None = None) -> list[dict]:
        with self._lock:
            if self._con is None:
                if not (self.lake / "runs").is_dir():
                    raise LakeUnavailable(
                        f"no data lake at {self.lake}; ingest runs with `genesis lake ingest`"
                    )
                self._con = connect(self.lake)
            relation = self._con.execute(sql, params or {})
            columns = [d[0] for d in relation.description]
            return [dict(zip(columns, row, strict=True)) for row in relation.fetchall()]

    def experiments(self) -> list[dict]:
        """Experiments with completed runs in the lake, plus runs saved outside any experiment."""
        rows = self._query(
            """
            SELECT r.experiment_id, any_value(e.title) AS title, count(*) AS runs
            FROM completed_runs AS r LEFT JOIN experiments AS e USING (experiment_id)
            GROUP BY r.experiment_id
            ORDER BY r.experiment_id NULLS LAST
            """
        )
        for row in rows:
            if row["experiment_id"] is None:
                row["title"] = "Runs saved from the lab, or run on their own"
        return rows

    def runs(self, experiment_id: str | None, limit: int = 1000) -> list[dict]:
        return self._query(
            """
            SELECT run_id, experiment_id, condition, seed, ticks_run, final_population,
                   ticks_every, config ->> '$.organisms.controller' AS controller
            FROM completed_runs
            WHERE experiment_id IS NOT DISTINCT FROM $e
            ORDER BY condition NULLS FIRST, seed, run_id
            LIMIT $limit
            """,
            {"e": experiment_id, "limit": limit},
        )

    def run(self, run_id: str) -> dict:
        rows = self._query(
            """
            SELECT run_id, experiment_id, condition, seed, ticks_run, final_population,
                   ticks_every, config
            FROM completed_runs WHERE run_id = $r
            """,
            {"r": run_id},
        )
        if not rows:
            raise KeyError(f"no completed run {run_id!r} in the lake")
        row = rows[0]
        row["config"] = (
            json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
        )
        return row

    def series(self, run_id: str) -> tuple[int, dict[str, list]]:
        """(every, columns) for a whole run, at most ~MAX_POINTS points."""
        run = self.run(run_id)
        recorded = max(1, int(run["ticks_every"] or 1))
        wanted = next(
            (s for s in POINT_SIZES if run["ticks_run"] / s <= MAX_POINTS), POINT_SIZES[-1]
        )
        every = recorded * math.ceil(max(wanted, recorded) / recorded)  # whole recorded rows
        # Predators (6.5): from predator_ticks, which has the same rows as ticks; a run without
        # predators has none, so predators is NULL and strikes and captures 0, as live.
        rows = self._query(
            """
            WITH t AS (SELECT * FROM ticks WHERE run_id = $r),
                 b AS (SELECT * FROM behaviour WHERE run_id = $r),
                 p AS (SELECT * FROM predator_ticks WHERE run_id = $r)
            SELECT max(t.tick)                                   AS tick,
                   arg_max(t.population, t.tick)                 AS population,
                   arg_max(t.food_count, t.tick)                 AS food_count,
                   arg_max(t.lineages, t.tick)                   AS lineages,
                   arg_max(t.mean_energy, t.tick)                AS mean_energy,
                   arg_max(p.population, t.tick)                 AS predators,
                   sum(t.births)                                 AS births,
                   sum(t.deaths)                                 AS deaths,
                   sum(t.food_eaten)                             AS food_eaten,
                   coalesce(sum(p.attempts), 0)                  AS attempts,
                   coalesce(sum(p.captures), 0)                  AS captures,
                   avg(b.toward_food)                            AS toward_food,
                   avg(b.mean_turn)                              AS mean_turn,
                   avg(b.mean_throttle)                          AS mean_throttle
            FROM t LEFT JOIN b USING (run_id, tick) LEFT JOIN p USING (run_id, tick)
            GROUP BY t.tick // $every
            ORDER BY tick
            """,
            {"r": run_id, "every": every},
        )
        names = ("tick", "population", "food_count", "lineages", "mean_energy", "predators",
                 "births", "deaths", "food_eaten", "attempts", "captures", "toward_food",
                 "mean_turn", "mean_throttle")  # fmt: skip
        columns = {name: [_clean(row[name]) for row in rows] for name in names}
        return every, columns


def _clean(value):
    """DuckDB gives NaN for an empty mean in some versions and NULL in others; JSON wants null."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value
