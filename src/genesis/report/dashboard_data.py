"""Loading one experiment from the lake for its dashboard. Reads the lake only.

Only completed runs are charted (failed ones are counted and reported). Time series are
thinned to about ``POINTS_PER_RUN`` points per run with a stride that is a multiple of every
run's ``ticks_every``, so every run contributes the same ticks.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from genesis.analytics.analysis import query_df, settled_gene_means_df
from genesis.analytics.spec import PROJECT_ROOT
from genesis.evolution.genome import gene_names
from genesis.lake.ingest import DEFAULT_LAKE

POINTS_PER_RUN = 400


@dataclass(frozen=True)
class ExperimentData:
    experiment_id: str
    title: str
    conditions: list[str]  # in the spec's order when a spec file exists
    runs: pd.DataFrame  # one row per run, completed or not
    population: pd.DataFrame  # run_id, condition, seed, tick, population
    genes: pd.DataFrame  # run_id, condition, seed, tick, gene, mean
    settled: pd.DataFrame  # one row per run: condition, seed, one column per gene
    evolving_genes: list[str]  # genes that can change (not frozen in every run)
    window: tuple[int, int]
    stride: int

    @property
    def completed(self) -> pd.DataFrame:
        return self.runs[self.runs["status"] == "completed"]


def load_experiment(
    experiment_id: str,
    lake: str | Path = DEFAULT_LAKE,
    window: tuple[int, int] | None = None,
) -> ExperimentData:
    runs = query_df(
        """SELECT run_id, condition, seed, status, ticks_run, ticks_every, stop_reason,
                  (config ->> '$.run.max_ticks')::INTEGER AS max_ticks, config::VARCHAR AS config
           FROM runs WHERE experiment_id = $e ORDER BY condition, seed""",
        lake,
        {"e": experiment_id},
    )
    if runs.empty:
        raise ValueError(f"no runs of {experiment_id} in the lake; run `genesis lake ingest`")
    completed = runs[runs["status"] == "completed"]
    if completed.empty:
        raise ValueError(f"{experiment_id} has no completed runs")

    longest = int(completed["ticks_run"].max())
    step = math.lcm(*(int(e) for e in completed["ticks_every"]))
    stride = max(step, math.ceil(longest / POINTS_PER_RUN / step) * step)
    max_ticks = int(completed["max_ticks"].min())
    window = window or (max(0, max_ticks - 1000), max_ticks - 1)

    params = {"e": experiment_id, "stride": stride}
    population = query_df(
        """SELECT t.run_id, r.condition, r.seed, t.tick, t.population
           FROM ticks t JOIN completed_runs r USING (run_id)
           WHERE r.experiment_id = $e AND t.tick % $stride = 0
           ORDER BY r.condition, r.seed, t.tick""",
        lake,
        params,
    )
    genes = query_df(
        """SELECT g.run_id, r.condition, r.seed, g.tick, g.gene, g.mean
           FROM gene_stats g JOIN completed_runs r USING (run_id)
           WHERE r.experiment_id = $e AND g.tick % $stride = 0
           ORDER BY r.condition, r.seed, g.gene, g.tick""",
        lake,
        params,
    )
    settled = settled_gene_means_df(experiment_id, *window, lake) if not genes.empty else genes

    return ExperimentData(
        experiment_id=experiment_id,
        title=_title(experiment_id, lake),
        conditions=_condition_order(
            experiment_id, sorted(completed["condition"].dropna().unique())
        ),
        runs=runs,
        population=population,
        genes=genes,
        settled=settled,
        evolving_genes=_evolving_genes(completed["config"]) if not genes.empty else [],
        window=window,
        stride=stride,
    )


def _title(experiment_id: str, lake: str | Path) -> str:
    rows = query_df(
        "SELECT title FROM experiments WHERE experiment_id = $e", lake, {"e": experiment_id}
    )
    return rows["title"].iloc[0] if not rows.empty else experiment_id


def _condition_order(experiment_id: str, found: list[str]) -> list[str]:
    """The spec file's order (it's the order the experiment was designed in), else sorted."""
    spec = PROJECT_ROOT / "experiments" / "specs" / f"{experiment_id}.yaml"
    if not spec.exists():
        return found
    listed = [c["label"] for c in yaml.safe_load(spec.read_text())["conditions"]]
    return [c for c in listed if c in found] + [c for c in found if c not in listed]


def _evolving_genes(configs: pd.Series) -> list[str]:
    """Genes that are mutable in at least one run (frozen-everywhere genes can't change)."""
    parsed = [json.loads(c) for c in configs]
    return [
        g
        for g in gene_names()
        if any(
            c.get("mutation", {}).get("enabled") and c["genome"][g].get("mutable", True)
            for c in parsed
            if "genome" in c
        )
    ]
