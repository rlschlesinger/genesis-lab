"""A live run's history: one row per tick, for charts (D-054).

Snapshots carry only the current moment; a chart needs the past. Each live run keeps one row
per tick in typed arrays (8 bytes a number: a 20,000-tick run holds about 2 MB): the tick
summary (population, food, births, deaths, meals, mean energy, lineages) and the cheap
behaviour measures from that tick's decision record (analytics.behaviour.decision_measures).
Recording only reads what the tick already produced; it can't change the simulation.

``query(since, every)`` returns columns for plotting. With ``every`` = k > 1 each point covers
k ticks, the same rule as recorded runs (D-028): **flows** (births, deaths, meals) are summed
over the k ticks, **stocks** (population, food, lineages, mean energy) are read at the
interval's last tick, and behaviour shares are averaged over the ticks that had a value.
Only complete intervals are returned, so a point never changes once a client has drawn it;
the newest partial interval appears once it completes.
"""

from __future__ import annotations

import math
from array import array

import numpy as np

from genesis.analytics.behaviour import decision_measures
from genesis.core.simulation import Decision, TickSummary

STOCKS = ("population", "food_count", "lineages", "mean_energy")
FLOWS = ("births", "deaths", "food_eaten")
SHARES = ("toward_food", "mean_turn", "mean_throttle")
COLUMNS = ("tick", *STOCKS, *FLOWS, *SHARES)


class RunHistory:
    def __init__(self) -> None:
        self._data = {name: array("d") for name in COLUMNS}

    def __len__(self) -> int:
        return len(self._data["tick"])

    def append(self, summary: TickSummary, decision: Decision | None) -> None:
        measures = decision_measures(decision)
        row = {
            "tick": summary.tick,
            "population": summary.population,
            "food_count": summary.food_count,
            "lineages": summary.lineages,
            "mean_energy": summary.mean_energy,
            "births": summary.births,
            "deaths": summary.deaths,
            "food_eaten": summary.food_eaten,
            **{name: measures[name] for name in SHARES},
        }
        for name in COLUMNS:
            self._data[name].append(float(row[name]))

    def query(self, since: int = 0, every: int = 1) -> dict[str, list]:
        """Complete intervals of ``every`` ticks ending at or after tick ``since``, as columns.
        NaN (nothing to measure) becomes None, JSON's null."""
        if every < 1:
            raise ValueError("every must be 1 or more")
        n = len(self)
        complete = n // every  # intervals [k*every, (k+1)*every - 1], all ticks present
        # Row i holds tick i, so the first interval that can end at or after ``since`` is the
        # one containing it. Starting there (instead of reducing the whole history and then
        # filtering) keeps a client's once-a-second "what's new" poll cheap however long the
        # run gets: each row's sum and mean are the same whichever rows come before it.
        first = min(since // every, complete)
        rows = complete - first
        if rows == 0:
            return {name: [] for name in COLUMNS}
        start, stop = first * every, complete * every
        cols = {name: np.frombuffer(self._data[name], dtype=np.float64)[start:stop]
                for name in COLUMNS}  # fmt: skip
        shaped = {name: values.reshape(rows, every) for name, values in cols.items()}
        out: dict[str, np.ndarray] = {"tick": shaped["tick"][:, -1]}
        for name in STOCKS:
            out[name] = shaped[name][:, -1]
        for name in FLOWS:
            out[name] = shaped[name].sum(axis=1)
        for name in SHARES:
            with np.errstate(invalid="ignore"), _quiet_empty_mean():
                out[name] = np.nanmean(shaped[name], axis=1)
        keep = out["tick"] >= since
        return {name: _json(values[keep], integer=name in ("tick", *FLOWS, "population",
                                                           "food_count", "lineages"))
                for name, values in out.items()}  # fmt: skip


def _json(values: np.ndarray, integer: bool) -> list:
    if integer:
        return [int(v) for v in values.tolist()]
    return [None if math.isnan(v) else v for v in values.tolist()]


class _quiet_empty_mean:
    """np.nanmean warns on an all-NaN interval (nobody saw food); None is the right answer."""

    def __enter__(self):
        import warnings

        self._catch = warnings.catch_warnings()
        self._catch.__enter__()
        warnings.simplefilter("ignore", RuntimeWarning)

    def __exit__(self, *exc):
        return self._catch.__exit__(*exc)
