"""The browser lab's API fixtures must match what the server sends today."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_committed_fixtures_are_what_the_api_sends_now():
    spec = importlib.util.spec_from_file_location(
        "fixtures", ROOT / "scripts" / "build_api_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = module.rendered()
    for name, text in expected.items():
        committed = (module.OUT / name).read_text()
        assert committed == text, (
            f"web/src/api/__fixtures__/{name} is out of date: the API changed. Run "
            "`uv run python scripts/build_api_fixtures.py`, then check web/src/api/types.ts "
            "and `npm test` in web/."
        )
    assert {p.name for p in module.OUT.glob("*.json")} == set(expected)
