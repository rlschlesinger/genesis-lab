"""Visual design tokens for reports: one palette, shared by the CSS and every chart.

A dark, restrained "instrument" look: a green-black ink background, bone-coloured text, and
one distinct, muted colour per gene so each gene can be followed across every chart.
System fonts only (the report must work offline): a book serif for prose and headings, a
monospace for numbers and labels.
"""

from __future__ import annotations

INK = "#0e1211"  # page background
PANEL = "#141917"  # chart surfaces
RULE = "#27302c"  # hairlines and grid
BONE = "#e7e2d4"  # primary text
MUTED = "#8b958e"  # secondary text, axes
ACCENT = "#d9a441"  # amber: highlights, the population line

SERIF = '"Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif'
MONO = 'ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace'

GENE_COLORS = {
    "speed": "#d9a441",  # amber
    "sense_range": "#5fb3a5",  # verdigris
    "max_turn": "#7d8a83",  # stone
    "metabolic_rate": "#e07a5f",  # terracotta
    "reproduction_threshold": "#a9b665",  # lichen
    "neutral_marker": "#9c8fd0",  # heather
}


def css_variables() -> str:
    """The same tokens for the stylesheet, so CSS and charts can't drift apart."""
    tokens = {
        "ink": INK,
        "panel": PANEL,
        "rule": RULE,
        "bone": BONE,
        "muted": MUTED,
        "accent": ACCENT,
        "warn": GENE_COLORS["metabolic_rate"],
        "heather": GENE_COLORS["neutral_marker"],
        "serif": SERIF,
        "mono": MONO,
    }
    return ":root {\n" + "".join(f"  --{k}: {v};\n" for k, v in tokens.items()) + "}\n"


def rgba(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {alpha})"


def base_layout(height: int) -> dict:
    """Plotly layout shared by every chart. Axis styling is applied per subplot in figures.py."""
    return dict(
        height=height,
        paper_bgcolor=PANEL,
        plot_bgcolor=PANEL,
        font=dict(family=MONO, size=11, color=BONE),
        margin=dict(l=56, r=20, t=28, b=40),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=INK, bordercolor=RULE, font=dict(family=MONO, color=BONE)),
        showlegend=False,
    )
