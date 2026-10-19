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
