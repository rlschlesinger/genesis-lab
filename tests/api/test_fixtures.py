"""The browser lab's API fixtures must match what the server sends today.

Shapes, keys, strings and whole numbers must be identical. Floats are compared to within
rounding: the fixtures were captured on one machine, and the last bit of a brain's
activations can differ between CPUs (the same reason the neural golden values are recorded
per platform, D-045). A real API change (a field added, renamed or retyped) still fails.
"""

import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).parents[2]
REL_TOL = 1e-9


def differences(committed, current, path="") -> list[str]:
    """Where two JSON values differ, as paths; floats within REL_TOL count as equal."""
    if isinstance(committed, float) or isinstance(current, float):
        if not (
            isinstance(committed, int | float)
            and isinstance(current, int | float)
            and math.isclose(committed, current, rel_tol=REL_TOL, abs_tol=1e-12)
        ):
            return [f"{path}: {committed!r} != {current!r}"]
        return []
    if isinstance(committed, dict) and isinstance(current, dict):
        found = []
        for key in sorted(set(committed) | set(current)):
            if key not in committed or key not in current:
                found.append(f"{path}.{key}: only on one side")
            else:
                found.extend(differences(committed[key], current[key], f"{path}.{key}"))
        return found
    if isinstance(committed, list) and isinstance(current, list):
        if len(committed) != len(current):
            return [f"{path}: {len(committed)} items != {len(current)} items"]
        return [
            d
            for i, (a, b) in enumerate(zip(committed, current, strict=True))
            for d in differences(a, b, f"{path}[{i}]")
        ]
    return [] if committed == current else [f"{path}: {committed!r} != {current!r}"]


def test_committed_fixtures_are_what_the_api_sends_now():
    spec = importlib.util.spec_from_file_location(
        "fixtures", ROOT / "scripts" / "build_api_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = module.rendered()
    for name, text in expected.items():
        committed = (module.OUT / name).read_text()
        hint = (
            f"web/src/api/__fixtures__/{name} is out of date: the API changed. Run "
            "`uv run python scripts/build_api_fixtures.py`, then check web/src/api/types.ts "
            "and `npm test` in web/."
        )
        # The committed file must be the script's own rendering (indent 2, sorted keys)...
        assert json.dumps(json.loads(committed), indent=2, sort_keys=True) + "\n" == committed, hint
        # ...and say the same as the API does now, floats to within rounding.
        found = differences(json.loads(committed), json.loads(text))
        assert not found, hint + "\n" + "\n".join(found[:20])
    assert {p.name for p in module.OUT.glob("*.json")} == set(expected)


def test_the_comparison_notices_real_changes():
    assert differences({"a": [1, 2.0]}, {"a": [1, 2.0 * (1 + 1e-12)]}) == []
    assert differences({"a": 1.0}, {"a": 1.001}) == [".a: 1.0 != 1.001"]
    assert differences({"a": 1}, {"a": 1.0}) == []  # 1 and 1.0 are the same JSON number
    assert differences({"a": None}, {"a": 0.0}) == [".a: None != 0.0"]
    assert differences({"a": [1]}, {"a": [1, 2]}) == [".a: 1 items != 2 items"]
    assert differences({"a": 1}, {"b": 1}) == [".a: only on one side", ".b: only on one side"]
    assert differences({"a": "x"}, {"a": "y"}) == [".a: 'x' != 'y'"]
