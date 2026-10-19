"""Experiment dashboard charts: individual runs and summaries, always visually distinct.

    individual runs   thin, faint lines or small dots, one per run
    summaries         bold median lines with a "middle 50% of runs" band (spread), or a
                      median with a 95% bootstrap confidence interval (precision)

Summary points over time count how many runs they are based on (shown on hover): if runs go
extinct, later medians describe survivors only (survivorship bias).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from genesis.analytics.analysis import bootstrap_ci
from genesis.report import theme
from genesis.report.dashboard_data import ExperimentData

RUN_LINE = dict(width=0.8)
RUN_OPACITY = 0.22
BOOTSTRAP_SEED = 3006  # fixed, so the dashboard is identical every time it's built


def colors(data: ExperimentData) -> dict[str, str]:
    palette = theme.CONDITION_COLORS
    return {c: palette[i % len(palette)] for i, c in enumerate(data.conditions)}


def _layout(fig: go.Figure, height: int) -> None:
    fig.update_layout(**theme.base_layout(height=height))
    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            font=dict(color=theme.BONE),
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="closest",
        margin=dict(l=56, r=20, t=56, b=40),
    )
    theme.style_axes(fig)


def _add_trend(
    fig, df: pd.DataFrame, value: str, data: ExperimentData, row=None, col=None, legend: bool = True
) -> None:
    """Faint per-run lines, then a bold median and middle-50% band per condition."""
    where = dict(row=row, col=col) if row else {}
    for condition, color in colors(data).items():
        part = df[df["condition"] == condition]
        if part.empty:
            continue
        for _, run in part.groupby("run_id", sort=True):
            fig.add_trace(
                go.Scatter(
                    x=run["tick"],
                    y=run[value],
                    mode="lines",
                    line=dict(color=color, **RUN_LINE),
                    opacity=RUN_OPACITY,
                    hoverinfo="skip",
                    showlegend=False,
                    legendgroup=condition,
                ),
                **where,
            )
        summary = (
            part.groupby("tick")[value]
            .agg(
                q1=lambda v: v.quantile(0.25),
                median="median",
                q3=lambda v: v.quantile(0.75),
                runs="count",
            )
            .reset_index()
        )
        x = list(summary["tick"])
        fig.add_trace(
            go.Scatter(
                x=x + x[::-1],
                y=list(summary["q3"]) + list(summary["q1"])[::-1],
                fill="toself",
                fillcolor=theme.rgba(color, 0.16),
                line=dict(width=0),
                hoverinfo="skip",
                showlegend=False,
                legendgroup=condition,
            ),
            **where,
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=summary["median"],
                mode="lines",
                line=dict(color=color, width=2.4),
                name=condition,
                legendgroup=condition,
                showlegend=legend,
                customdata=summary["runs"],
                hovertemplate=f"{condition}<br>tick %{{x}}<br>median %{{y:.4g}}"
                "<br>over %{customdata} runs<extra></extra>",
            ),
            **where,
        )


def population_figure(data: ExperimentData) -> go.Figure:
    fig = go.Figure()
    _add_trend(fig, data.population, "population", data)
    _layout(fig, 380)
    fig.update_xaxes(title_text="tick")
    fig.update_yaxes(title_text="population")
    return fig


def gene_trends_figure(data: ExperimentData) -> go.Figure | None:
    genes = data.evolving_genes
    if not genes:
        return None
    rows = math.ceil(len(genes) / 2)
    fig = make_subplots(
        rows=rows,
        cols=2,
        subplot_titles=genes,
        shared_xaxes=True,
        vertical_spacing=0.1,
        horizontal_spacing=0.08,
    )
    for i, gene in enumerate(genes):
        part = data.genes[data.genes["gene"] == gene]
        _add_trend(fig, part, "mean", data, row=i // 2 + 1, col=i % 2 + 1, legend=i == 0)
    _layout(fig, 230 * rows + 80)
    return fig


def settled_figure(data: ExperimentData) -> go.Figure | None:
    """Every run's settled value as a dot; per condition, the median and its 95% CI."""
    genes = [g for g in data.evolving_genes if g in data.settled.columns]
    if not genes or data.settled.empty:
        return None
    rows = math.ceil(len(genes) / 2)
    fig = make_subplots(
        rows=rows, cols=2, subplot_titles=genes, vertical_spacing=0.16, horizontal_spacing=0.08
    )
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    for i, gene in enumerate(genes):
        where = dict(row=i // 2 + 1, col=i % 2 + 1)
        for k, (condition, color) in enumerate(colors(data).items()):
            values = data.settled.loc[data.settled["condition"] == condition, gene].dropna()
            if values.empty:
                continue
            # Spread the dots sideways in a fixed pattern (not random) so none hide another.
            offsets = (np.arange(len(values)) - (len(values) - 1) / 2) * (0.5 / max(len(values), 1))
            fig.add_trace(
                go.Scatter(
                    x=k + offsets,
                    y=values,
                    mode="markers",
                    marker=dict(color=color, size=5, opacity=0.55),
                    name=condition,
                    legendgroup=condition,
                    showlegend=i == 0,
                    hovertemplate=f"{condition}: %{{y:.4g}}<extra>one run</extra>",
                ),
                **where,
            )
            if len(values) >= 2:
                ci = bootstrap_ci(values.to_numpy(), np.median, rng=rng)
                fig.add_trace(
                    go.Scatter(
                        x=[k + 0.38],
                        y=[ci.estimate],
                        mode="markers",
                        marker=dict(
                            color=color,
                            size=10,
                            symbol="diamond",
                            line=dict(color=theme.BONE, width=1),
                        ),
                        error_y=dict(
                            type="data",
                            symmetric=False,
                            array=[ci.high - ci.estimate],
                            arrayminus=[ci.estimate - ci.low],
                            color=color,
                            thickness=2,
                        ),
                        showlegend=False,
                        legendgroup=condition,
                        hovertemplate=f"{condition} median %{{y:.4g}}<br>95% CI "
                        f"[{ci.low:.4g}, {ci.high:.4g}], {len(values)} runs<extra></extra>",
                    ),
                    **where,
                )
        fig.update_xaxes(
            tickvals=list(range(len(data.conditions))), ticktext=data.conditions, **where
        )
    _layout(fig, 250 * rows + 80)
    return fig


def paired_figure(data: ExperimentData, pairs: list[tuple[str, str]]) -> go.Figure | None:
    """Per seed: treatment - control for each gene (dots), with the mean difference and CI."""
    genes = [g for g in data.evolving_genes if g in data.settled.columns]
    if not pairs or not genes or data.settled.empty:
        return None
    rows = math.ceil(len(genes) / 2)
    fig = make_subplots(
        rows=rows, cols=2, subplot_titles=genes, vertical_spacing=0.16, horizontal_spacing=0.08
    )
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    palette = theme.CONDITION_COLORS
    for i, gene in enumerate(genes):
        where = dict(row=i // 2 + 1, col=i % 2 + 1)
        fig.add_hline(y=0, line=dict(color=theme.MUTED, width=1, dash="dot"), **where)
        for k, (treatment, control) in enumerate(pairs):
            t = data.settled[data.settled["condition"] == treatment].set_index("seed")[gene]
            c = data.settled[data.settled["condition"] == control].set_index("seed")[gene]
            diffs = (t - c).dropna()  # only seeds present in both conditions
            label, color = f"{treatment} − {control}", palette[k % len(palette)]
            offsets = (np.arange(len(diffs)) - (len(diffs) - 1) / 2) * (0.5 / max(len(diffs), 1))
            fig.add_trace(
                go.Scatter(
                    x=k + offsets,
                    y=diffs,
                    mode="markers",
                    marker=dict(color=color, size=5, opacity=0.55),
                    name=label,
                    legendgroup=label,
                    showlegend=i == 0,
                    customdata=diffs.index,
                    hovertemplate="seed %{customdata}: %{y:.4g}<extra></extra>",
                ),
                **where,
            )
            if len(diffs) >= 2:
                ci = bootstrap_ci(diffs.to_numpy(), np.mean, rng=rng)
                fig.add_trace(
                    go.Scatter(
                        x=[k + 0.38],
                        y=[ci.estimate],
                        mode="markers",
                        marker=dict(
                            color=color,
                            size=10,
                            symbol="diamond",
                            line=dict(color=theme.BONE, width=1),
                        ),
                        error_y=dict(
                            type="data",
                            symmetric=False,
                            array=[ci.high - ci.estimate],
                            arrayminus=[ci.estimate - ci.low],
                            color=color,
                            thickness=2,
                        ),
                        showlegend=False,
                        legendgroup=label,
                        hovertemplate=f"mean difference %{{y:.4g}}<br>95% CI [{ci.low:.4g}, "
                        f"{ci.high:.4g}], {len(diffs)} seeds<extra></extra>",
                    ),
                    **where,
                )
        fig.update_xaxes(
            tickvals=list(range(len(pairs))), ticktext=[f"{t}<br>− {c}" for t, c in pairs], **where
        )
    _layout(fig, 250 * rows + 80)
    return fig
