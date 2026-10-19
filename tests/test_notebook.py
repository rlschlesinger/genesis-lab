"""The analysis notebook: committed without outputs, and runs top to bottom in a fresh kernel."""

from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient

NOTEBOOK = Path(__file__).parents[1] / "notebooks" / "analysis-workflow.ipynb"


def test_committed_notebook_has_no_outputs():
    # Saved outputs change on every run (noisy diffs) and can go stale against the code.
    # In VS Code: "Clear All Outputs" before committing.
    nb = nbformat.read(NOTEBOOK, as_version=4)
    nbformat.validate(nb)
    dirty = [
        i
        for i, c in enumerate(nb.cells)
        if c.cell_type == "code" and (c.outputs or c.execution_count)
    ]
    assert not dirty, f"clear the outputs of cells {dirty} before committing"


@pytest.fixture(scope="module")
def executed(tmp_path_factory):
    demo = tmp_path_factory.mktemp("notebook-demo")
    mp = pytest.MonkeyPatch()
    mp.setenv("GENESIS_NOTEBOOK_DIR", str(demo))  # the kernel inherits this environment
    nb = nbformat.read(NOTEBOOK, as_version=4)
    try:
        NotebookClient(
            nb,
            timeout=600,
            kernel_name="python3",
            resources={"metadata": {"path": str(NOTEBOOK.parent)}},
        ).execute()
    finally:
        mp.undo()
    return nb, demo


def printed(nb) -> str:
    return "\n".join(
        o.text
        for c in nb.cells
        if c.cell_type == "code"
        for o in c.outputs
        if o.output_type == "stream"
    )


def test_notebook_runs_without_errors(executed):
    nb, _ = executed
    errors = [
        o for c in nb.cells if c.cell_type == "code" for o in c.outputs if o.output_type == "error"
    ]
    assert not errors, [f"{e.ename}: {e.evalue}" for e in errors]


def test_notebook_results_are_consistent(executed):
    nb, demo = executed
    text = printed(nb)
    assert "12 runs planned" in text
    assert "permutation p: ours 0.0312 (exact: True), SciPy 0.0312" in text  # 2 / 2**6
    assert "reanalysis from the export matches section 3: True" in text
    assert "verify: intact" in text
    assert (demo / "lake" / "runs").is_dir() and (demo / "export" / "manifest.json").exists()


def test_notebook_shows_a_chart(executed):
    nb, _ = executed
    mimes = {
        m
        for c in nb.cells
        if c.cell_type == "code"
        for o in c.outputs
        if o.output_type in ("display_data", "execute_result")
        for m in o.get("data", {})
    }
    assert "application/vnd.plotly.v1+json" in mimes
