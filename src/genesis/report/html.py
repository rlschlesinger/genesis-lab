"""HTML pieces shared by run reports and experiment dashboards."""

from __future__ import annotations

import plotly.io as pio

# No toolbar: drag to zoom and double-click to reset still work, without generic Plotly chrome.
CHART_CONFIG = {"displayModeBar": False, "responsive": True}


def chart_html(fig, div_id: str) -> str:
    """One chart as an HTML fragment. A fixed ``div_id`` keeps the output deterministic."""
    inner = pio.to_html(
        fig, full_html=False, include_plotlyjs=False, div_id=div_id, config=CHART_CONFIG
    )
    return f'<div class="chart">{inner}</div>'


def plotly_js() -> str:
    """The plotly.js bundle shipped inside the Python package, so no network is needed."""
    from plotly.offline import get_plotlyjs

    return get_plotlyjs()
