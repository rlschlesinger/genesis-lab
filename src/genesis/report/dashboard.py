"""`genesis dashboard EXPERIMENT`: one self-contained HTML page for a whole experiment.

Built only from the lake, deterministic (fixed chart IDs and bootstrap seed), and offline.
Shares the run report's stylesheet and design tokens.
"""

from __future__ import annotations

import html
from importlib.resources import files
from pathlib import Path
from string import Template

from genesis.lake.ingest import DEFAULT_LAKE
from genesis.report import dashboard_figures as figures
from genesis.report import theme
from genesis.report.dashboard_data import ExperimentData, load_experiment
from genesis.report.html import chart_html, plotly_js

DEFAULT_DIR = Path("data") / "dashboards"


def write_dashboard(
    experiment_id: str,
    lake: str | Path = DEFAULT_LAKE,
    out_path: str | Path | None = None,
    window: tuple[int, int] | None = None,
    pairs: list[tuple[str, str]] | None = None,
) -> Path:
    data = load_experiment(experiment_id, lake, window)
    for treatment, control in pairs or []:
        missing = {treatment, control} - set(data.conditions)
        if missing:
            raise ValueError(f"unknown condition(s) {sorted(missing)}; have {data.conditions}")
    out = Path(out_path) if out_path else DEFAULT_DIR / f"{experiment_id}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data, Path(lake), pairs or []), encoding="utf-8")
    return out


def render(data: ExperimentData, lake: Path, pairs: list[tuple[str, str]]) -> str:
    package = files("genesis.report")
    sections = [
        _section(
            "01",
            "Population",
            "Each faint line is one run; the bold line is the median "
            "across runs of that condition, with the middle 50% of runs shaded.",
            figures.population_figure(data),
            "population",
        ),
        _section(
            "02",
            "Gene trends",
            "The population mean of each evolving gene, per run "
            "(faint) and summarized per condition (bold median, middle 50% shaded).",
            figures.gene_trends_figure(data),
            "gene-trends",
        ),
        _section(
            "03",
            "Settled values",
            f"Each dot is one run's mean over ticks "
            f"{data.window[0]:,}–{data.window[1]:,}. Diamonds: the median across runs "
            "with its 95% bootstrap confidence interval.",
            figures.settled_figure(data),
            "settled",
        ),
        _section(
            "04",
            "Paired differences",
            "Each dot is one seed: the same founders and food "
            "under two conditions, subtracted. Diamonds: mean difference with 95% "
            "bootstrap CI; the dotted line is no difference.",
            figures.paired_figure(data, pairs),
            "paired",
        ),
    ]
    return Template(
        package.joinpath("dashboard_template.html").read_text(encoding="utf-8")
    ).substitute(
        experiment_id=html.escape(data.experiment_id),
        title=html.escape(data.title),
        lede=html.escape(_lede(data)),
        facts=_facts(data),
        caveat=html.escape(_caveat(data)),
        sections="\n".join(s for s in sections if s),
        css_variables=theme.css_variables(),
        stylesheet=package.joinpath("report.css").read_text(encoding="utf-8"),
        plotly_js=f"<script>{plotly_js()}</script>",
        lake=html.escape(lake.as_posix()),
        stride=f"{data.stride:,}",
        definition=html.escape(f"docs/experiments/{data.experiment_id}-*.md"),
    )


def _section(number: str, title: str, text: str, fig, div_id: str) -> str:
    if fig is None:
        return ""
    return (
        f'  <section>\n    <div class="rail"><span class="num">{number}</span>'
        f'<h2>{html.escape(title)}</h2></div>\n    <div class="body">\n'
        f"      <p>{html.escape(text)}</p>\n      {chart_html(fig, div_id)}\n"
        "    </div>\n  </section>"
    )


def _lede(data: ExperimentData) -> str:
    done = data.completed
    seeds = sorted(done["seed"].unique())
    return (
        f"{len(data.conditions)} conditions × {len(seeds)} seeds "
        f"({seeds[0]}–{seeds[-1]}): {len(done)} completed runs."
    )


def _facts(data: ExperimentData) -> str:
    runs, done = data.runs, data.completed
    extinct = int((done["stop_reason"] == "extinction").sum())
    items = [
        ("conditions", ", ".join(data.conditions)),
        ("completed runs", str(len(done))),
        ("failed or unfinished", str(len(runs) - len(done))),
        ("went extinct", str(extinct)),
        ("ticks per run", f"{int(done['max_ticks'].min()):,}"),
        ("settled window", f"{data.window[0]:,}–{data.window[1]:,}"),
    ]
    rows = []
    for label, value in items:
        warn = (
            ' class="warn"'
            if label in ("failed or unfinished", "went extinct") and value != "0"
            else ""
        )
        rows.append(
            f"    <div><dt>{html.escape(label)}</dt><dd{warn}>{html.escape(value)}</dd></div>"
        )
    return "\n".join(rows)


def _caveat(data: ExperimentData) -> str:
    done = data.completed
    extinct = done[done["stop_reason"] == "extinction"]
    text = (
        "Each run is one replicate: compare conditions by their spread of runs, never by "
        "counting organisms."
    )
    if not extinct.empty:
        text += (
            f" {len(extinct)} run(s) went extinct, so late-tick medians describe surviving "
            "runs only (survivorship bias): hover a median line to see how many runs it "
            "is based on."
        )
    return text
