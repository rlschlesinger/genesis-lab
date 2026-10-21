"""E009 exploratory analyses: post hoc, NOT pre-registered.

    uv run python experiments/e009_exploratory.py

Written after E009's pre-registered analysis (experiments/e009_specialisation.py) gave its
verdicts; recorded in docs/experiments/E009-specialisation.md under "Exploratory". Nothing
here tests a hypothesis.

1. Each tradeoff world's ending: split, or which food the one-sided ones specialised on.
2. Are the splits stable? For each split world, the share of recorded ticks over the last
   5,000 in which both ends held at least 10% of the organisms alive.
3. How fast? The first recorded tick at which more than half the organisms alive were
   specialists (diet below 0.2 or above 0.8), per tradeoff world.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

from genesis.analytics.analysis import query_df
from genesis.analytics.spec import load_spec
from genesis.lake.ingest import DEFAULT_LAKE

sys.path.insert(0, str(Path(__file__).parent))
import e009_specialisation as e  # noqa: E402 (the pre-registered script, for its definitions)

LAKE = e.PROJECT_ROOT / DEFAULT_LAKE


def main() -> int:
    spec = load_spec(e.SPEC)
    print("EXPLORATORY (post hoc, not pre-registered)\n")
    metrics = e.run_metrics(spec, LAKE)
    trade = metrics[metrics["condition"] == "tradeoff"].set_index("seed")

    print("1. How each tradeoff world ended")
    endings = {}
    for seed, row in trade.iterrows():
        if row["split"]:
            endings[seed] = f"split ({row['share_a']:.0%} eat A, {row['share_b']:.0%} eat B)"
        elif row["share_a"] > 0.5:
            endings[seed] = f"A ({row['share_a']:.0%} eat A)"
        elif row["share_b"] > 0.5:
            endings[seed] = f"B ({row['share_b']:.0%} eat B)"
        else:
            endings[seed] = f"other (A {row['share_a']:.0%}, B {row['share_b']:.0%})"
    for seed, text in endings.items():
        print(f"  {seed}: {text}")
    kinds = [t.split(" ")[0] for t in endings.values()]
    print(f"  split {kinds.count('split')}, all A {kinds.count('A')}, all B {kinds.count('B')}, "
          f"other {kinds.count('other')}")  # fmt: skip

    ticks = query_df(
        """SELECT r.seed, d.tick, d.n, d.diet_low, d.diet_high
           FROM diet_ticks AS d JOIN runs AS r USING (run_id)
           WHERE r.experiment_id = 'E009' AND r.condition = 'tradeoff' ORDER BY r.seed, d.tick""",
        LAKE,
    )

    print("\n2. Split worlds: both ends >= 10% in the last 5,000 ticks (share of recorded ticks)")
    for seed in [s for s, t in endings.items() if t.startswith("split")]:
        late = ticks[(ticks["seed"] == seed) & (ticks["tick"] >= 15000)]
        both = ((late["diet_low"] >= 0.1) & (late["diet_high"] >= 0.1)).mean()
        print(f"  {seed}: {both:.0%}")

    print("\n3. First tick with more than half the organisms specialists (tradeoff)")
    firsts = []
    for seed in trade.index:
        rows = ticks[ticks["seed"] == seed]
        hit = rows[(rows["diet_low"] + rows["diet_high"]) > 0.5]
        first = int(hit["tick"].iloc[0]) if len(hit) else None
        firsts.append(first)
        print(f"  {seed}: {first}")
    found = [f for f in firsts if f is not None]
    if found:
        print(f"  median {statistics.median(found):.0f}, range {min(found)}-{max(found)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
