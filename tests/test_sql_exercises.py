"""docs/sql-exercises.md: every answer is valid SQL and still gives its printed result."""

import re
from pathlib import Path

import pytest

from genesis.cli import format_table
from genesis.lake.db import connect
from genesis.lake.ingest import DEFAULT_LAKE

ROOT = Path(__file__).parents[1]
DOC = ROOT / "docs" / "sql-exercises.md"
REAL_LAKE = ROOT / DEFAULT_LAKE


def answers() -> list[tuple[int, str, str]]:
    """(number, query, printed result) for every '### Answer N' section."""
    text = DOC.read_text().split("# Answers", 1)[1]
    found = []
    for section in re.split(r"\n(?=### Answer )", text)[1:]:
        number = int(re.match(r"### Answer (\d+)", section).group(1))
        query = re.search(r"```sql\n(.*?)```", section, re.S).group(1)
        result = re.search(r"```text\n(.*?)\n```", section, re.S).group(1)
        found.append((number, query, result))
    return found


def test_every_exercise_has_an_answer():
    questions = re.findall(r"^## (\d+) · ", DOC.read_text(), re.M)
    assert [int(q) for q in questions] == [n for n, _, _ in answers()] == list(range(1, 11))


@pytest.mark.parametrize(("number", "query", "_result"), answers())
def test_answer_is_valid_sql_for_the_schema(number, query, _result, tmp_path):
    # An empty lake still has every view (typed, no rows), so this checks names and syntax
    # anywhere, including machines without the experiment data.
    connect(tmp_path).sql(query).fetchall()


@pytest.mark.skipif(
    not (REAL_LAKE / "runs").is_dir(), reason="the real lake (data/lake) isn't on this machine"
)
@pytest.mark.parametrize(("number", "query", "result"), answers())
def test_answer_still_gives_its_printed_result(number, query, result):
    con = connect(REAL_LAKE)
    # A lake holding only some experiments (say, a fresh E007 re-run on another machine)
    # would make every printed result wrong without anything having changed.
    # An answer that names no experiment summarises them all, so it needs every experiment
    # the document mentions.
    named = set(re.findall(r"'(E\d{3})'", query))
    needed = named or set(re.findall(r"\bE\d{3}\b", DOC.read_text()))
    present = {row[0] for row in con.sql("SELECT DISTINCT experiment_id FROM runs").fetchall()}
    if needed - present:
        pytest.skip(f"answer {number} needs {sorted(needed - present)}, not in this lake")
    relation = con.sql(query)
    assert format_table(relation.columns, relation.fetchall()) == result, (
        f"answer {number} no longer matches the document: the lake or the code changed. "
        "Run scripts/build_sql_exercises.py and check the answer notes still hold."
    )
