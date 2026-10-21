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
# The share of organisms turning toward seen food counts only those whose bearing to it is
# not exactly 0.0 (analytics/behaviour.py). A rule-based organism that has turned to face its
# food heads straight at it on the next tick with a bearing of exactly 0.0 on one platform and
# a few ulps on another (arctan2's last bit, D-027), so it is counted on one and left out on
# the other. The fixtures were captured on a Mac; on Linux x86_64 that moved the diets run's
# toward_food in the fourth decimal while every count stayed identical. The measure itself is
# recorded in behaviour.csv and can't change (CLAUDE.md: CSV output stays byte-identical), so
# this comparison alone is loosened for it. A real change in what toward_food means (0.5 for a
# random walker, 1.0 for the seeker) is far larger than this tolerance.
PLATFORM_SENSITIVE = {"toward_food": 1e-2}


def differences(committed, current, path="") -> list[str]:
    """Where two JSON values differ, as paths; floats within REL_TOL count as equal."""
    if isinstance(committed, float) or isinstance(current, float):
        column = path.rsplit(".", 1)[-1].split("[", 1)[0]
        abs_tol = PLATFORM_SENSITIVE.get(column, 1e-12)
        if not (
            isinstance(committed, int | float)
            and isinstance(current, int | float)
            and math.isclose(committed, current, rel_tol=REL_TOL, abs_tol=abs_tol)
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


def test_only_toward_food_may_differ_by_a_platforms_rounding():
    near = {"columns": {"toward_food": [0.9996969696969696], "population": [158.0]}}
    far = {"columns": {"toward_food": [0.9996923076923077], "population": [158.0]}}
    assert differences(near, far) == []
    # Still a real difference when it is one: the seeker (1.0) against a random walker (0.5).
    assert differences({"columns": {"toward_food": [1.0]}}, {"columns": {"toward_food": [0.5]}})
    # Counts never get the allowance, nor does a float column of another name.
    assert differences(near, {"columns": {**near["columns"], "population": [158.001]}})
    assert differences({"mean_energy": [1.0]}, {"mean_energy": [1.001]})
