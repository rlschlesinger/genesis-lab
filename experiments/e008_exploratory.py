"""E008 exploratory analyses: post hoc, NOT pre-registered.

    uv run python experiments/e008_exploratory.py

Written after E008's pre-registered analysis (experiments/e008_evasion.py) gave its verdicts,
to look for reasons; recorded in docs/experiments/E008-evasion.md under "Exploratory". Nothing
here tests a hypothesis: it suggests what a future, pre-registered experiment could test.

1. What killed prey in training (predation versus starvation), and how many were born.
2. Whether selection touched the weights on the three predator inputs: in "safe" worlds those
   inputs are always 0, so their weights only drift at random, a built-in control.
3. The primary difference (from_hunted - from_safe) split by whether predators lasted the
   whole training run.
4. Behaviour: when a prey sees a predator, how often the predator is in its rear half (more
   than 90 degrees off its heading) after its turn, replaying every arena run. Facing away
   scores near 1, random headings about 0.5. (A first version counted turns that widened the
   angle; it scored a prey already fleeing straight away, predator dead behind, as a failure,
   since that angle can't widen. Replaced before its numbers were interpreted.)
"""

from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import yaml

from genesis.analytics.analysis import query_df
from genesis.analytics.spec import ExperimentSpec, load_spec
from genesis.core.geometry import wrap_angle
from genesis.core.simulation import Simulation
from genesis.lake.ingest import DEFAULT_LAKE
from genesis.lake.tables import BASE_BRAIN_COLUMNS, THREAT_BRAIN_COLUMNS

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import e008_evasion as e  # noqa: E402 (the pre-registered script, for its definitions)

LAKE = e.PROJECT_ROOT / DEFAULT_LAKE
ARENA_SPEC = e.PROJECT_ROOT / "data" / "experiments" / "E008" / "arena-spec.yaml"


def mean_abs(columns: list[str]) -> str:
    return "(" + " + ".join(f"avg(abs(b.{c}))" for c in columns) + f") / {len(columns)}"


def turning_away(key: tuple[str, int]) -> tuple[tuple[str, int], int, int]:
    """Replay one arena run: (prey-ticks seeing a predator that have it in their rear half
    after turning, prey-ticks seeing a predator). The turn is as movement applies it."""
    spec = ExperimentSpec.model_validate(yaml.safe_load(ARENA_SPEC.read_text()))
    sim = Simulation(spec.configs()[key])
    away = seen = 0
    while not sim.finished:
        sim.step()
        decision = sim.last_decision
        threat = decision.observations.threat
        if threat is None or not threat.found.any():
            continue
        mask = threat.found
        limit = decision.max_turn[mask]
        turn = np.clip(decision.actions.turn[mask], -limit, limit)
        after = np.abs(wrap_angle(threat.bearing[mask] - turn))
        away += int((after > np.pi / 2).sum())
        seen += int(mask.sum())
    return key, away, seen


def main() -> int:
    train = load_spec(e.TRAIN_SPEC)
    print("EXPLORATORY (post hoc, not pre-registered)\n")

    print("1. Prey deaths in training, by cause, and births")
    deaths = query_df(
        """SELECT r.condition, o.death_cause, count(*) AS n
           FROM organisms AS o JOIN runs AS r USING (run_id)
           WHERE r.experiment_id = 'E008' AND r.condition IN ('hunted', 'safe') AND NOT o.alive
           GROUP BY ALL""",
        LAKE,
    )
    table = deaths.pivot(index="condition", columns="death_cause", values="n").fillna(0)
    print(table.astype(int).to_string())
    births = query_df(
        """SELECT r.condition, sum(t.births) AS births FROM ticks AS t JOIN runs AS r USING (run_id)
           WHERE r.experiment_id = 'E008' AND r.condition IN ('hunted', 'safe') GROUP BY ALL""",
        LAKE,
    )
    print(births.set_index("condition").astype(int).to_string())

    print("\n2. Mean |weight| among survivors at the end of training (per world, then averaged)")
    rows = []
    for condition in e.TRAINING:
        df = query_df(
            f"""SELECT r.seed, {mean_abs(THREAT_BRAIN_COLUMNS)} AS predator_inputs,
                       {mean_abs(BASE_BRAIN_COLUMNS[:42])} AS other_inputs
                FROM brains AS b JOIN organisms AS o USING (run_id, organism_id)
                     JOIN runs AS r USING (run_id)
                WHERE r.experiment_id = 'E008' AND r.condition = $c AND o.alive
                GROUP BY r.seed""",
            LAKE,
            {"c": condition},
        )
        df["condition"] = condition
        rows.append(df)
    weights = pd.concat(rows)
    for column in ("predator_inputs", "other_inputs"):
        wide = weights.pivot(index="seed", columns="condition", values=column)
        print(
            f"  {column:<16} hunted {wide['hunted'].mean():.3f}, safe {wide['safe'].mean():.3f}; "
            f"hunted larger in {(wide['hunted'] > wide['safe']).sum()}/{len(wide)} worlds"
        )

    print("\n3. from_hunted - from_safe captures per prey-tick, by predator persistence")
    metrics = e.arena_metrics(train, LAKE)
    wide = metrics.pivot(index="world", columns="condition", values="capture_rate")
    diff = (wide["from_hunted"] - wide["from_safe"]).to_numpy()
    outcomes = e.training_outcomes(train, LAKE)
    gone = outcomes[outcomes["condition"] == "hunted"].sort_values("seed")["predators_gone"]
    lasted = gone.isna().to_numpy()
    safe_mean = wide["from_safe"].to_numpy()
    for label, mask in (("predators lasted", lasted), ("predators died out", ~lasted)):
        print(
            f"  {label:<19} n = {mask.sum():>2}: mean {diff[mask].mean():+.6f} "
            f"({diff[mask].mean() / safe_mean[mask].mean():+.1%} of from_safe), "
            f"{(diff[mask] < 0).sum()}/{mask.sum()} worlds lower"
        )

    print("\n4. Predator in the rear half after turning (share of prey-ticks seeing one)")
    spec = ExperimentSpec.model_validate(yaml.safe_load(ARENA_SPEC.read_text()))
    keys = [k for k in spec.configs() if k[0] in ("flee", "from_safe", "from_hunted")]
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(turning_away, keys))
    share: dict[str, dict[int, float]] = {}
    for (label, seed), away, seen in results:
        share.setdefault(label, {})[seed] = away / seen if seen else float("nan")
    for label in ("flee", "from_safe", "from_hunted"):
        print(f"  {label:<12} {np.nanmean(list(share[label].values())):.3f}")
    seeds = sorted(share["from_hunted"])
    h = np.array([share["from_hunted"][s] for s in seeds])
    s = np.array([share["from_safe"][s] for s in seeds])
    print(f"  from_hunted - from_safe {np.nanmean(h - s):+.3f}, higher in {(h > s).sum()}/{len(h)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
