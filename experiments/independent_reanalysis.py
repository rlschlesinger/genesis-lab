"""Re-analyse E003's H7a from an export, using only pandas, NumPy and SciPy (no Genesis Lab).

This is what a collaborator with only the exported files could do. It proves the export is
self-sufficient: if it reproduces the published result, nothing essential lives only inside
Genesis Lab's code.

    uv run genesis lake export --experiment E003 --out data/exports/E003
    uv run python experiments/independent_reanalysis.py data/exports/E003

Published (docs/experiments/E003-food-scarcity.md): median interaction +5.12, 14 positive
of 20, permutation p = 0.0077 (sampled; a different sampler gives a slightly different p).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

FIRST, LAST = 19_000, 19_999  # E003's pre-registered settled window


def settled_means(export: Path, gene: str) -> pd.DataFrame:
    runs = pd.read_parquet(
        export / "runs.parquet", columns=["run_id", "condition", "seed", "status"]
    )
    runs = runs[runs["status"] == "completed"]
    stats_ = pd.read_parquet(
        export / "gene_stats.parquet",
        columns=["run_id", "tick", "gene", "mean"],
        filters=[("gene", "==", gene), ("tick", ">=", FIRST), ("tick", "<=", LAST)],
    )
    per_run = stats_.groupby("run_id", as_index=False)["mean"].mean()
    return per_run.merge(runs, on="run_id")  # join on run_id: one row per run


def main(export: Path) -> None:
    df = settled_means(export, "sense_range")
    wide = df.pivot(index="seed", columns="condition", values="mean")
    interaction = (wide["S_scarce"] - wide["N_scarce"]) - (wide["S_plenty"] - wide["N_plenty"])
    test = stats.permutation_test(
        (interaction.to_numpy(), np.zeros(len(interaction))),
        lambda a, b, axis: np.mean(a - b, axis=axis),
        permutation_type="samples",
        n_resamples=20_000,
        rng=np.random.default_rng(2003),
    )
    print(f"seeds: {len(interaction)}")
    print(f"median interaction: {interaction.median():+.2f}")
    print(f"positive / negative: {(interaction > 0).sum()} / {(interaction < 0).sum()}")
    print(
        f"sign test p: {stats.binomtest(int((interaction > 0).sum()), len(interaction)).pvalue:.4f}"
    )
    print(f"permutation p (SciPy, sampled): {test.pvalue:.4f}")
    assert "genesis" not in sys.modules, "this analysis must not use Genesis Lab"
    print("used only pandas, NumPy and SciPy: no Genesis Lab code imported")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
