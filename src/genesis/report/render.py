"""Assembling the report page: template + stylesheet + charts -> one self-contained HTML file.

The output is deterministic: the same run folder always produces a byte-identical file.
Plotly normally gives each chart a random element ID; fixed IDs (``div_id``) prevent that.
Plotly's JavaScript is embedded once, so the page works offline.
"""

from __future__ import annotations

import html
import math
from importlib.resources import files
from pathlib import Path
from string import Template

from genesis.report import figures, theme
from genesis.report.data import MAX_POINTS, REQUIRED_FILES, RunData, load_run
from genesis.report.html import chart_html, plotly_js


def write_report(run_dir: str | Path, out_path: str | Path | None = None) -> Path:
    """Build ``report.html`` for a recorded run. Returns the path written."""
    run = load_run(run_dir)
    out = Path(out_path) if out_path else run.run_dir / "report.html"
    out.write_text(render(run), encoding="utf-8")
    return out


def render(run: RunData) -> str:
    package = files("genesis.report")
    template = Template(package.joinpath("template.html").read_text(encoding="utf-8"))
    distributions = figures.distributions_figure(run)
    return template.substitute(
        run_id=html.escape(run.meta["run_id"]),
        lede=html.escape(_lede(run)),
        facts=_facts(run),
        css_variables=theme.css_variables(),
        stylesheet=package.joinpath("report.css").read_text(encoding="utf-8"),
        plotly_js=f"<script>{plotly_js()}</script>",
        population_figure=chart_html(figures.population_figure(run), "population"),
        gene_trends_figure=chart_html(figures.gene_trends_figure(run), "gene-trends"),
        distributions_figure=(
            chart_html(distributions, "distributions")
            if distributions is not None
            else "<p class='caveat'>No mutable genes or no snapshots in this run.</p>"
        ),
        mutation_table=_mutation_table(run),
        run_dir=html.escape(run.run_dir.name),
        files=", ".join(f"<code>{name}</code>" for name in REQUIRED_FILES),
        max_points=MAX_POINTS,
        stride_note=_stride_note(run),
    )


def _lede(run: RunData) -> str:
    cfg = run.meta["config"]
    mutation = cfg["mutation"]
    evolving = "with mutation" if mutation["enabled"] else "without mutation (exact copies)"
    return (
        f"{cfg['organisms']['controller'].replace('_', ' ')} organisms, {evolving}, "
        f"over {run.meta['ticks_run']:,} ticks from seed {run.meta['seed']}."
    )


def _facts(run: RunData) -> str:
    meta, cfg = run.meta, run.meta["config"]
    mutation, org = cfg["mutation"], cfg["organisms"]
    git = meta.get("git") or {}
    commit = (git.get("commit") or "unknown")[:7]
    items = [
        ("seed", str(meta["seed"])),
        ("ticks run", f"{meta['ticks_run']:,}"),
        ("stopped by", meta["stop_reason"]),
        ("final population", str(meta["final_population"])),
        ("organisms ever", f"{meta['organisms_ever']:,}"),
        ("mutations", f"{meta.get('mutations', 0):,}"),
        (
            "mutation",
            f"rate {mutation['rate']}, size {mutation['size']}" if mutation["enabled"] else "off",
        ),
        ("drag exponent", str(org.get("speed_cost_exponent", 0.0))),
        ("sense cost / unit", str(org.get("sense_cost_per_unit", 0.0))),
        ("code", f"{commit}{' (dirty)' if git.get('dirty') else ''}"),
    ]
    rows = []
    for label, value in items:
        warn = ' class="warn"' if label == "code" and git.get("dirty") else ""
        rows.append(
            f"    <div><dt>{html.escape(label)}</dt><dd{warn}>{html.escape(value)}</dd></div>"
        )
    return "\n".join(rows)


def _mutation_table(run: RunData) -> str:
    head = (
        "<tr><th>gene</th><th class='num'>mutations</th>"
        "<th class='num'>mean step (fraction of range)</th></tr>"
    )
    body = []
    for row in figures.mutation_summary(run):
        color = theme.GENE_COLORS.get(row["gene"], theme.BONE)
        step = (
            "frozen"
            if not row["mutable"]
            else ("&mdash;" if row["mean_step"] is None else f"{row['mean_step']:.4f}")
        )
        css = " class='frozen'" if not row["mutable"] else ""
        body.append(
            f"<tr{css}><td><span class='swatch' style='background:{color}'></span>"
            f"{html.escape(row['gene'])}</td><td class='num'>{row['mutations']:,}</td>"
            f"<td class='num'>{step}</td></tr>"
        )
    return f"<table>{head}{''.join(body)}</table>"


def _stride_note(run: RunData) -> str:
    n = len(run.ticks)
    stride = math.ceil(n / MAX_POINTS) if n > MAX_POINTS else 1
    return "every tick" if stride == 1 else f"one tick in every {stride}"
