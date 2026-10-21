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


def predators_figure(run: RunData) -> go.Figure | None:
    """Worlds with predators (6.4): both species' numbers, and the predators' strikes and
    captures per recorded row (summed between rows when ticks are sampled)."""
    if not run.has_predators:
        return None
    pairs = list(zip(run.ticks, run.predator_ticks, strict=True))
    keep = downsample(list(range(len(pairs))))
    ticks = [pairs[i][0]["tick"] for i in keep]
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12,
        subplot_titles=["prey and predators alive", "predator strikes, and those that caught"],
    )  # fmt: skip
    lines = [
        (1, "prey", [pairs[i][0]["population"] for i in keep], theme.PREY, None),
        (1, "predators", [pairs[i][1]["population"] for i in keep], theme.PREDATOR, None),
        (2, "strikes", [pairs[i][1]["attempts"] for i in keep], theme.MUTED, "dot"),
        (2, "captures", [pairs[i][1]["captures"] for i in keep], theme.PREDATOR, None),
    ]
    for row, label, values, color, dash in lines:
        fig.add_trace(
            go.Scatter(x=ticks, y=values, name=label, line=dict(color=color, width=1.4, dash=dash)),
            row=row, col=1,
        )  # fmt: skip
    fig.update_layout(**theme.base_layout(height=420))
    fig.update_xaxes(title_text="tick", row=2, col=1)
    theme.style_axes(fig)
    # Name each line at its last point (charts have no legend).
    for row, label, values, color, _ in lines:
        fig.add_annotation(
            x=ticks[-1], y=values[-1], text=label, showarrow=False, xanchor="right",
            yanchor="bottom", font=dict(color=color, size=11), row=row, col=1,
        )  # fmt: skip
    return fig


def phase_figure(run: RunData) -> go.Figure | None:
    """Prey against predators, one point per recorded tick, joined in time order: the classic
    view of a predator-prey system. A cycle shows as a loop; a collapse as a line to an axis."""
    if not run.has_predators:
        return None
    pairs = list(zip(run.ticks, run.predator_ticks, strict=True))
    keep = downsample(list(range(len(pairs))))
    prey = [pairs[i][0]["population"] for i in keep]
    hunters = [pairs[i][1]["population"] for i in keep]
    ticks = [pairs[i][0]["tick"] for i in keep]
    fig = go.Figure(
        go.Scatter(
            x=prey, y=hunters, mode="lines", customdata=ticks,
            line=dict(color=theme.PREDATOR, width=1.2),
            hovertemplate="tick %{customdata}<br>prey %{x}<br>predators %{y}<extra></extra>",
        )
    )  # fmt: skip
    fig.update_layout(**theme.base_layout(height=380))
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(title_text="prey alive", rangemode="tozero")
    fig.update_yaxes(title_text="predators alive", rangemode="tozero")
    theme.style_axes(fig)  # before the labels: it treats annotations as subplot titles
    # Where the path starts and ends, so its direction can be read.
    for k, text in ((0, "start"), (-1, "end")):
        fig.add_annotation(
            x=prey[k], y=hunters[k], text=text, showarrow=True, arrowcolor=theme.MUTED,
            font=dict(color=theme.BONE, size=11), ax=24, ay=-24,
        )  # fmt: skip
    return fig


def diet_figure(run: RunData) -> go.Figure | None:
    """Two foods (6.9): the diet's distribution over time as a heatmap (share of organisms in
    each 0.1-wide band of the diet), and below it the shares near each end and food on the
    plate by kind. One band splitting into two is specialists emerging."""
    if not run.has_two_foods:
        return None
    rows = downsample(run.diet_ticks)
    ticks = [r["tick"] for r in rows]
    shares = [[r[f"bin_{k}"] / r["n"] if r["n"] else None for r in rows] for k in range(10)]
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.5, 0.25, 0.25],
        subplot_titles=["diet of the organisms alive (share in each band)",
                        "specialists: diet below 0.2 (eats A) and above 0.8 (eats B)",
                        "food on the plate, by kind"],
    )  # fmt: skip
    fig.add_trace(
        go.Heatmap(
            x=ticks, y=[k / 10 + 0.05 for k in range(10)], z=shares, zmin=0, zmax=1,
            colorscale=[[0, theme.PANEL], [1, theme.BONE]], showscale=False,
            hovertemplate="tick %{x}<br>diet %{y:.2f}<br>share %{z:.2f}<extra></extra>",
        ),
        row=1, col=1,
    )  # fmt: skip
    lines = [
        (2, "eats A", [r["diet_low"] for r in rows], theme.FOOD_A),
        (2, "eats B", [r["diet_high"] for r in rows], theme.FOOD_B),
        (3, "A", [r["food_a"] for r in rows], theme.FOOD_A),
        (3, "B", [r["food_b"] for r in rows], theme.FOOD_B),
    ]
    for row, label, values, color in lines:
        fig.add_trace(
            go.Scatter(x=ticks, y=values, name=label, line=dict(color=color, width=1.4)),
            row=row, col=1,
        )  # fmt: skip
    fig.update_layout(**theme.base_layout(height=560))
    fig.update_yaxes(range=[0, 1], row=1, col=1, title_text="diet")
    fig.update_yaxes(range=[0, 1.05], row=2, col=1)
    fig.update_xaxes(title_text="tick", row=3, col=1)
    theme.style_axes(fig)  # before the labels: it treats annotations as subplot titles
    for row, label, values, color in lines:
        last = next((v for v in reversed(values) if v is not None), None)
        if last is not None:
            fig.add_annotation(
                x=ticks[-1], y=last, text=label, showarrow=False, xanchor="right",
                yanchor="bottom", font=dict(color=color, size=11), row=row, col=1,
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
