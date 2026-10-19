"""The report's charts. Each function takes RunData and returns one Plotly figure.

Gene charts use each gene's full allowed range [min, max] as the y-axis, so you see where in
its range a gene sits, and a change isn't visually exaggerated by zooming in on it.
"""

from __future__ import annotations

import math

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from genesis.report import theme
from genesis.report.data import RunData, downsample

HEATMAP_BINS = 24


def population_figure(run: RunData) -> go.Figure:
    """Population, uneaten food and surviving founder lineages, on one shared time axis."""
    rows = downsample(run.ticks)
    ticks = [r["tick"] for r in rows]
    panels = [
        ("population", "population", theme.ACCENT),
        ("food_count", "uneaten food", theme.GENE_COLORS["sense_range"]),
        ("lineages", "founder lineages alive", theme.GENE_COLORS["neutral_marker"]),
    ]
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=[label for _, label, _ in panels],
    )
    for i, (column, label, color) in enumerate(panels, start=1):
        fig.add_trace(
            go.Scatter(
                x=ticks, y=[r[column] for r in rows], name=label, line=dict(color=color, width=1.4)
            ),
            row=i,
            col=1,
        )
    fig.update_layout(**theme.base_layout(height=480))
    fig.update_xaxes(title_text="tick", row=3, col=1)
    theme.style_axes(fig)
    return fig


def gene_trends_figure(run: RunData) -> go.Figure:
    """Per gene: population mean (line), mean +/- 1 sd (band), founders' value (dotted)."""
    genes = run.genes
    rows_n = math.ceil(len(genes) / 2)
    titles = [f"{g}{'  (frozen)' if not run.bounds[g].mutable else ''}" for g in genes]
    fig = make_subplots(
        rows=rows_n,
        cols=2,
        shared_xaxes=True,
        vertical_spacing=0.09,
        horizontal_spacing=0.08,
        subplot_titles=titles,
    )
    for i, gene in enumerate(genes):
        row, col = i // 2 + 1, i % 2 + 1
        color, bounds = theme.GENE_COLORS.get(gene, theme.BONE), run.bounds[gene]
        rows = [r for r in downsample(run.gene_stats[gene]) if r["n"]]
        ticks = [r["tick"] for r in rows]
        upper = [min(bounds.max, r["mean"] + r["sd"]) for r in rows]
        lower = [max(bounds.min, r["mean"] - r["sd"]) for r in rows]
        # The band is drawn as one closed shape: along the upper edge, then back along the lower.
        fig.add_trace(
            go.Scatter(
                x=ticks + ticks[::-1],
                y=upper + lower[::-1],
                fill="toself",
                fillcolor=theme.rgba(color, 0.18),
                line=dict(width=0),
                hoverinfo="skip",
            ),
            row=row,
            col=col,
        )
        fig.add_trace(
            go.Scatter(
                x=ticks,
                y=[r["mean"] for r in rows],
                name=f"{gene} mean",
                line=dict(color=color, width=1.6),
            ),
            row=row,
            col=col,
        )
        fig.add_hline(
            y=bounds.initial, line=dict(color=theme.MUTED, width=1, dash="dot"), row=row, col=col
        )
        fig.update_yaxes(range=[bounds.min, bounds.max], row=row, col=col)
    fig.update_layout(**theme.base_layout(height=210 * rows_n + 40))
    theme.style_axes(fig)
    return fig


def distributions_figure(run: RunData) -> go.Figure | None:
    """Heatmaps of the full gene distribution over time, from genome snapshots.

    Each column is one snapshot; colour is the fraction of the population in each value bin.
    Shows what a mean can't: a population splitting in two, or variation collapsing.
    Frozen genes are left out (their distribution is a single line).
    """
    genes = [g for g in run.genes if run.bounds[g].mutable]
    if not genes or not run.genomes:
        return None
    snapshot_ticks = sorted({r["tick"] for r in run.genomes})
    by_tick: dict[int, list[dict]] = {t: [] for t in snapshot_ticks}
    for row in run.genomes:
        by_tick[row["tick"]].append(row)

    rows_n = math.ceil(len(genes) / 2)
    fig = make_subplots(
        rows=rows_n,
        cols=2,
        shared_xaxes=True,
        vertical_spacing=0.09,
        horizontal_spacing=0.08,
        subplot_titles=genes,
    )
    for i, gene in enumerate(genes):
        bounds, color = run.bounds[gene], theme.GENE_COLORS.get(gene, theme.BONE)
        edges = np.linspace(bounds.min, bounds.max, HEATMAP_BINS + 1)
        z = np.zeros((HEATMAP_BINS, len(snapshot_ticks)))
        for j, tick in enumerate(snapshot_ticks):
            values = [r[f"gene_{gene}"] for r in by_tick[tick]]
            if values:
                counts, _ = np.histogram(values, bins=edges)
                z[:, j] = counts / len(values)
        centres = (edges[:-1] + edges[1:]) / 2
        fig.add_trace(
            go.Heatmap(
                x=snapshot_ticks,
                y=centres,
                z=z,
                showscale=False,
                colorscale=[[0, theme.PANEL], [1, color]],
                zmin=0,
                zmax=1,
                hovertemplate="tick %{x}<br>value %{y:.3g}<br>"
                "%{z:.0%} of population<extra></extra>",
            ),
            row=i // 2 + 1,
            col=i % 2 + 1,
        )
    fig.update_layout(**theme.base_layout(height=210 * rows_n + 40))
    fig.update_layout(hovermode="closest")
    theme.style_axes(fig)
    return fig


ROLLING_ROWS = 100  # behaviour shares are noisy tick to tick; plot a rolling mean


def rolling_mean(values: list[float | None], window: int = ROLLING_ROWS) -> list[float | None]:
    """Mean of the last ``window`` values at each row, ignoring missing ones (None/NaN).

    Computed with cumulative sums: total and count of valid values up to each row, minus the
    same ``window`` rows earlier. None where the window holds no valid value.
    """
    x = np.array([math.nan if v is None else v for v in values], dtype=np.float64)
    valid = ~np.isnan(x)
    totals = np.concatenate([[0.0], np.cumsum(np.where(valid, x, 0.0))])
    counts = np.concatenate([[0], np.cumsum(valid)])
    end = np.arange(1, len(x) + 1)
    start = np.maximum(end - window, 0)
    n = counts[end] - counts[start]
    with np.errstate(invalid="ignore", divide="ignore"):
        means = (totals[end] - totals[start]) / n
    return [float(m) if k else None for m, k in zip(means, n, strict=True)]


def behaviour_figure(run: RunData) -> go.Figure | None:
    """What organisms did: share turning toward seen food, throttle; with brains, how far
    weights have drifted from the founders and how varied they are."""
    if not run.behaviour:
        return None
    rows = run.behaviour
    smoothed = {c: rolling_mean([r[c] for r in rows]) for c in ("toward_food", "mean_throttle")}
    keep = downsample(list(range(len(rows))))
    ticks = [rows[i]["tick"] for i in keep]
    titles = [
        f"turning toward seen food ({ROLLING_ROWS}-row rolling mean)",
        f"throttle ({ROLLING_ROWS}-row rolling mean)",
    ]
    if run.has_brains:
        titles.append("brain weights: drift from founders, and spread")
    fig = make_subplots(
        rows=len(titles), cols=1, shared_xaxes=True, vertical_spacing=0.1, subplot_titles=titles
    )
    for i, (column, color) in enumerate(
        [("toward_food", theme.ACCENT), ("mean_throttle", theme.GENE_COLORS["speed"])], start=1
    ):
        fig.add_trace(
            go.Scatter(
                x=ticks,
                y=[smoothed[column][k] for k in keep],
                name=column.replace("_", " "),
                line=dict(color=color, width=1.4),
            ),
            row=i,
            col=1,
        )
        fig.update_yaxes(range=[0, 1.05], row=i, col=1)
    if run.has_brains:
        for column, label, color in [
            ("weight_drift", "mean |weight - founder's|", theme.GENE_COLORS["metabolic_rate"]),
            ("weight_sd", "spread (mean sd per weight)", theme.GENE_COLORS["neutral_marker"]),
        ]:
            fig.add_trace(
                go.Scatter(
                    x=ticks,
                    y=[rows[k][column] for k in keep],
                    name=label,
                    line=dict(color=color, width=1.4),
                ),
                row=3,
                col=1,
            )
    fig.update_layout(**theme.base_layout(height=170 * len(titles) + 80))
    fig.update_xaxes(title_text="tick", row=len(titles), col=1)
    theme.style_axes(fig)  # before the reference line: it treats annotations as titles
    # Reference: a controller that turns at random brings food closer half the time.
    fig.add_hline(
        y=0.5, line=dict(color=theme.MUTED, width=1, dash="dot"), row=1, col=1,
        annotation_text="random turning", annotation_font_color=theme.MUTED,
    )  # fmt: skip
    if run.has_brains:
        # Name each brain line at its last point (charts have no legend).
        for column, label, color in [
            ("weight_drift", "drift from founders", theme.GENE_COLORS["metabolic_rate"]),
            ("weight_sd", "spread", theme.GENE_COLORS["neutral_marker"]),
        ]:
            last = next((r for r in reversed(rows) if r[column] is not None), None)
            if last is not None and not math.isnan(last[column]):
                fig.add_annotation(
                    x=last["tick"], y=last[column], text=label, showarrow=False,
                    xanchor="right", yanchor="bottom", font=dict(color=color, size=11),
                    row=3, col=1,
                )  # fmt: skip
    return fig


def mutation_summary(run: RunData) -> list[dict]:
    """Per gene: number of mutations, and mean absolute step as a fraction of the gene's range."""
    summary = []
    for gene in run.genes:
        steps = [abs(m["after"] - m["before"]) for m in run.mutations if m["gene"] == gene]
        span = run.bounds[gene].max - run.bounds[gene].min
        summary.append(
            {
                "gene": gene,
                "mutations": len(steps),
                "mean_step": (sum(steps) / len(steps) / span) if steps else None,
                "mutable": run.bounds[gene].mutable,
            }
        )
    return summary
