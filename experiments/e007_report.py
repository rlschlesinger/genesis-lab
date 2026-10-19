"""E007's results page: per-world outcomes and training behaviour over time (chunk 04B).

    uv run python experiments/e007_neuroevolution.py --analyse-only --report

Built from the lake only, in the same visual system as run reports (genesis.report.theme and
report.css). Writes data/dashboards/E007-results.html.
"""

from __future__ import annotations

import html
from importlib.resources import files
from pathlib import Path
from string import Template

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from genesis.analytics.analysis import query_df
from genesis.report import theme
from genesis.report.figures import rolling_mean
from genesis.report.html import chart_html, plotly_js

LABELS = {
    "random_walk": "random walk",
    "seeker": "food seeker",
    "random_brains": "random brains",
    "evolved": "evolved brains",
    "home": "evolved, home world",
}

PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>E007 results</title>
<style>
$css_variables
$stylesheet
</style>
<script>$plotly_js</script>
</head>
<body>
<header class="masthead">
  <p class="eyebrow">Genesis Lab &middot; experiment E007</p>
  <h1>Evolved brains vs the hand-written rule</h1>
  <p class="lede">$lede</p>
  <p class="caveat">Each dot is one independent world (one training run). Organisms within a
  run are not replicates. Full definition and verdicts: docs/experiments/E007-neuroevolution.md.</p>
</header>
<main>
  <section>
    <div class="rail"><span class="num">01</span><h2>Foraging in every world</h2></div>
    <div class="body">
      <p>Meals per organism-tick in each evaluation world: 30 organisms, no births, 1,000
      ticks. A short bar marks each condition's mean.</p>
      $outcomes
    </div>
  </section>
  <section>
    <div class="rail"><span class="num">02</span><h2>Evolved minus seeker</h2></div>
    <div class="body">
      <p>The paired difference in each world, sorted. The shaded band is the pre-registered
      smallest effect of interest (&plusmn;5% of the seeker's mean); the amber lines are the
      95% bootstrap interval of the mean difference. The verdict depends on where that
      interval sits relative to the band.</p>
      $differences
    </div>
  </section>
  <section>
    <div class="rail"><span class="num">03</span><h2>Training</h2></div>
    <div class="body">
      <p>Behaviour during the 24 training runs (20,000 ticks each): the mean across runs
      (line) and the range from lowest to highest run (band), smoothed over 200 ticks.</p>
      $training
    </div>
  </section>
</main>
</body>
</html>
""")


def outcomes_figure(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for k, condition in enumerate(LABELS):
        part = df[df["condition"] == condition].sort_values("world")
        # Deterministic horizontal spread by world index, so dots don't overlap.
        x = k + (part["world"].to_numpy() - 11.5) / 60
        color = theme.CONDITION_COLORS[k]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=part["meal_rate"],
                mode="markers",
                marker=dict(color=color, size=6, opacity=0.8),
                name=LABELS[condition],
                text=[f"world {w}" for w in part["world"]],
                hovertemplate="%{text}: %{y:.4f}<extra>" + LABELS[condition] + "</extra>",
            )
        )
        mean = part["meal_rate"].mean()
        fig.add_trace(
            go.Scatter(
                x=[k - 0.3, k + 0.3],
                y=[mean, mean],
                mode="lines",
                line=dict(color=theme.BONE, width=2),
                hoverinfo="skip",
            )
        )
    fig.update_layout(**theme.base_layout(height=380))
    fig.update_layout(hovermode="closest")
    # Two short lines per label, never rotated: readable on a phone-width page too.
    short = ["random<br>walk", "food<br>seeker", "random<br>brains", "evolved<br>brains",
             "evolved,<br>home"]  # fmt: skip
    fig.update_xaxes(tickvals=list(range(len(LABELS))), ticktext=short, tickangle=0)
    fig.update_yaxes(title_text="meals per organism-tick", rangemode="tozero")
    theme.style_axes(fig)
    return fig


def differences_figure(diff: pd.Series, ci: tuple[float, float], sesoi: float) -> go.Figure:
    d = diff.sort_values()
    x = list(range(len(d)))
    fig = go.Figure()
    fig.add_hrect(y0=-sesoi, y1=sesoi, fillcolor=theme.rgba(theme.MUTED, 0.15), line_width=0)
    for y in ci:
        fig.add_hline(y=y, line=dict(color=theme.ACCENT, width=1.5))
    fig.add_hline(y=0, line=dict(color=theme.MUTED, width=1, dash="dot"))
    fig.add_trace(
        go.Scatter(
            x=x,
            y=d.to_numpy(),
            mode="markers",
            marker=dict(color=theme.CONDITION_COLORS[3], size=7),
            text=[f"world {w}" for w in d.index],
            hovertemplate="%{text}: %{y:+.4f}<extra></extra>",
        )
    )
    fig.update_layout(**theme.base_layout(height=320))
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(title_text="worlds, sorted by difference", showticklabels=False)
    fig.update_yaxes(title_text="evolved − seeker")
    theme.style_axes(fig)
    return fig


def training_figure(lake: Path) -> go.Figure:
    b = query_df(
        """
        SELECT b.run_id, b.tick, b.toward_food, b.mean_throttle, b.weight_drift
        FROM behaviour AS b JOIN runs AS r USING (run_id)
        WHERE r.experiment_id = 'E007' AND r.condition = 'train'
        ORDER BY b.run_id, b.tick
        """,
        lake,
    )
    panels = [
        ("toward_food", "turning toward seen food"),
        ("mean_throttle", "throttle"),
        ("weight_drift", "brain weights: mean |weight − founder's|"),
    ]
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.1,
        subplot_titles=[title for _, title in panels],
    )  # fmt: skip
    for i, (column, _) in enumerate(panels, start=1):
        # One smoothed series per training run (20 rows = 200 ticks), as columns by tick.
        smoothed = pd.DataFrame(
            {
                run_id: pd.Series(rolling_mean(g[column].tolist(), window=20), index=g["tick"])
                for run_id, g in b.groupby("run_id")
            }
        ).astype(float)
        ticks = smoothed.index.to_numpy()
        low, high = smoothed.min(axis=1).to_numpy(), smoothed.max(axis=1).to_numpy()
        fig.add_trace(
            go.Scatter(
                x=np.concatenate([ticks, ticks[::-1]]),
                y=np.concatenate([high, low[::-1]]),
                fill="toself",
                fillcolor=theme.rgba(theme.CONDITION_COLORS[3], 0.18),
                line=dict(width=0),
                hoverinfo="skip",
            ),
            row=i,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=ticks,
                y=smoothed.mean(axis=1).to_numpy(),
                line=dict(color=theme.CONDITION_COLORS[3], width=1.6),
                name=column,
            ),
            row=i,
            col=1,
        )
    fig.update_layout(**theme.base_layout(height=560))
    fig.update_xaxes(title_text="tick", row=3, col=1)
    theme.style_axes(fig)
    return fig


def write_report(
    df: pd.DataFrame, diff: pd.Series, ci: tuple[float, float], sesoi: float, lake: Path, out: Path
) -> Path:
    package = files("genesis.report")
    n = df["world"].nunique()
    lede = (
        f"{n} evolved populations, each tested in a world it never lived in, against the "
        "hand-written food seeker, a random walker and unevolved random brains in the same worlds."
    )
    page = PAGE.substitute(
        css_variables=theme.css_variables(),
        stylesheet=package.joinpath("report.css").read_text(encoding="utf-8"),
        plotly_js=plotly_js(),
        lede=html.escape(lede),
        outcomes=chart_html(outcomes_figure(df), "outcomes"),
        differences=chart_html(differences_figure(diff, ci, sesoi), "differences"),
        training=chart_html(training_figure(lake), "training"),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
