"""Behaviour and brain summaries: what organisms *did*, measured the same way for every
controller (D-043).

Genes say what an organism is; for a neural organism the 62 brain weights are too many to
read directly. What matters is what they make it do, so each recorded tick gets one row:

    n              organisms that decided this tick
    seeing_food    how many of them had food in sight
    toward_food    of those (excluding food exactly ahead), the share whose turn brought the
                   food closer to dead ahead: |bearing - turn| < |bearing|. A random walker
                   scores about 0.5, the food seeker 1.0. NULL if nobody qualified.
    mean_turn      mean |turn| as a fraction of each organism's own max_turn, 0 to 1
    mean_throttle  mean throttle, 0 to 1
    weight_sd      brain diversity: for each of the 62 parameters, the population standard
                   deviation; then the mean of those. NULL without brains.
    weight_drift   distance travelled from the founders: for each organism, the mean
                   |weight - its founder's weight|; then the mean over organisms. NULL
                   without brains.

Turn and throttle are measured *as applied*: clipped to the body's limits exactly as
movement clips them, so a rule asking for a sharp turn is credited with the turn it got.

Behaviour columns describe the decision made during the tick (by the organisms alive at its
start); brain columns describe the population at the end of the tick (newborns included),
the same convention as gene_stats.
"""

from __future__ import annotations

import math

import numpy as np

from genesis.core.geometry import wrap_angle
from genesis.core.organism import Organism
from genesis.core.simulation import Decision

BEHAVIOUR_FIELDS: list[str] = [
    "tick",
    "n",
    "seeing_food",
    "toward_food",
    "mean_turn",
    "mean_throttle",
    "weight_sd",
    "weight_drift",
]


DECISION_FIELDS = ("n", "seeing_food", "toward_food", "mean_turn", "mean_throttle")


def decision_measures(decision: Decision | None) -> dict:
    """The behaviour columns that come from one tick's decision record alone: cheap enough to
    compute every tick (the live API's history uses them too, api/history.py). NaN where there
    is nothing to measure."""
    row: dict = {"n": 0, "seeing_food": 0, "toward_food": math.nan, "mean_turn": math.nan,
                 "mean_throttle": math.nan}  # fmt: skip
    if decision is None or len(decision.observations) == 0:
        return row
    obs, actions = decision.observations, decision.actions
    turn = np.clip(actions.turn, -decision.max_turn, decision.max_turn)
    throttle = np.clip(actions.throttle, 0.0, 1.0)
    row["n"] = len(obs)
    row["seeing_food"] = int(np.count_nonzero(obs.food_found))
    row["mean_turn"] = float(np.mean(np.abs(turn) / decision.max_turn))
    row["mean_throttle"] = float(np.mean(throttle))
    judged = obs.food_found & (obs.food_bearing != 0.0)
    if judged.any():
        bearing = obs.food_bearing[judged]
        closer = np.abs(wrap_angle(bearing - turn[judged])) < np.abs(bearing)
        row["toward_food"] = float(np.mean(closer))
    return row


def behaviour_row(
    tick: int,
    decision: Decision | None,
    living: list[Organism],
    founder_brains: dict[int, np.ndarray],
) -> dict:
    """One behaviour.csv row. ``founder_brains`` maps founder ID -> that founder's weights."""
    row: dict = dict.fromkeys(BEHAVIOUR_FIELDS, math.nan)
    row["tick"] = tick
    row.update(decision_measures(decision))

    with_brains = [o for o in living if o.brain is not None]
    if with_brains:
        weights = np.array([o.brain.to_vector() for o in with_brains])
        founders = np.array([founder_brains[o.founder_id] for o in with_brains])
        row["weight_sd"] = float(np.mean(weights.std(axis=0)))
        row["weight_drift"] = float(np.mean(np.abs(weights - founders)))
    return row
