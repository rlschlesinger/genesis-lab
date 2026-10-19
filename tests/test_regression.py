"""Golden-value regression tests: lock in the exact behaviour of recorded results.

These don't check that behaviour is *right* (other tests do that); they check it hasn't
*changed*. If one of these fails:

* If you meant to change simulation behaviour, the change invalidates earlier results.
  Record that in docs/decision-log.md, then update the digests here deliberately.
* If you didn't mean to (a refactor, a new feature that should be off by default),
  you've found a bug: something leaked into the default behaviour.

There are two kinds of golden value, because floating-point bits are not portable (D-027):

* **State digests** (``GOLDEN_STATE``) hash every position, heading and energy bit for bit.
  NumPy's ``hypot`` and ``arctan2`` can differ in the last bit between CPUs and operating
  systems, so these values hold only on the platform they were recorded on. The test runs
  on recorded platforms and is skipped elsewhere.
* **Event digests** (``GOLDEN_EVENTS``) hash only the integer counts in every tick summary:
  population, births, deaths, food counts, meals, lineages, mutations. In the runs checked
  so far (this test's 1,000 ticks; E001's 5,000-tick metrics on arm64 macOS and x86_64
  Linux), last-bit differences didn't change who ate or who died, so these values hold on
  both platforms. That is observed, not guaranteed: the simulation is sensitive to small
  differences, so over long runs a last-bit difference could eventually flip a close call
  (an organism right at the eat radius), and long runs such as E002/E003's 20,000 ticks may
  not reproduce event for event on another platform. This test always runs.

If the state test fails but the event test passes, only the low bits of some floats changed:
a platform or library difference, not a change in what happened. If the event test fails,
something that happened in the run changed, on any platform.

History of the golden values (the chain that ties them to experiment E001):

1. Recorded at commit 5c37894, the code that produced E001 (increment 2.0).
2. Increment 2.3 wired mutation into reproduction; with mutation disabled the *old* values
   still matched, so behaviour was unchanged.
3. Only then was state_digest() extended to include genes (otherwise a neutral-marker
   difference would be invisible), which changes every digest value. The values below were
   recorded with the new definition on that same, verified behaviour.
4. Linux x86_64 state digests and the event digests were recorded at commit b6c7629 on code
   whose behaviour the arm64 values had verified (D-027).
"""

import hashlib
import platform
from pathlib import Path

import numpy as np
import pytest
import yaml

from genesis.core.config import SimulationConfig
from genesis.core.simulation import Simulation, TickSummary

DEFAULT_CONFIG = Path(__file__).parents[1] / "configs" / "default.yaml"
TICKS = 1000
CONTROLLERS = ["nearest_food_seeker", "random_walk"]

# (platform.system(), platform.machine()) -> controller -> state digest after TICKS ticks of
# the default config, seed 42. Add a platform by recording its values on code whose event
# digests match GOLDEN_EVENTS; never by copying values from another platform.
GOLDEN_STATE = {
    ("Darwin", "arm64"): {
        "nearest_food_seeker": "42b8e2b6b98b94420838e4d11518f2ef76452c40c479013ea78cc90b2212e0ea",
        "random_walk": "7fb0f1d30caf07cbf86f67bc479a931180d95315b7e4508468bef30461327883",
    },
    ("Linux", "x86_64"): {
        "nearest_food_seeker": "d40c008032234dae87c76112379db2adfcc975f33a391e73cf3d49e091f1ea48",
        "random_walk": "5625e05ee0f2b0fdcdacb6edd2badaf19782877d5e1416555eaf53ee4e6c2dd4",
    },
}

# controller -> event digest after TICKS ticks of the default config, seed 42 (any platform).
GOLDEN_EVENTS = {
    "nearest_food_seeker": "1a4b558fca0a4300f367dbdc4c701640b573b7703307327a0ac6c25971b800ed",
    "random_walk": "4448525bfca318f4efba8b99a675d9e58069f2dd40ab3778de688d28c9e120d4",
}

# Every TickSummary field that is a count. mean_energy is left out: it is a float.
EVENT_FIELDS = (
    "tick",
    "population",
    "births",
    "deaths",
    "food_count",
    "food_spawned",
    "food_eaten",
    "lineages",
    "mutations",
)


def event_digest(summaries: list[TickSummary]) -> str:
    """SHA-256 over the integer counts of every tick, in order."""
    h = hashlib.sha256()
    for summary in summaries:
        counts = [getattr(summary, field) for field in EVENT_FIELDS]
        h.update(np.array(counts, dtype=np.int64).tobytes())
    return h.hexdigest()


def run_default(controller: str) -> tuple[Simulation, list[TickSummary]]:
    raw = yaml.safe_load(DEFAULT_CONFIG.read_text())
    raw["organisms"]["controller"] = controller
    raw["run"]["max_ticks"] = TICKS
    sim = Simulation(SimulationConfig.model_validate(raw))
    return sim, sim.run()


@pytest.mark.parametrize("controller", CONTROLLERS)
def test_milestone_1_events_are_unchanged(controller):
    _, summaries = run_default(controller)
    assert event_digest(summaries) == GOLDEN_EVENTS[controller], (
        "the sequence of births, deaths and meals changed: simulation behaviour changed"
    )


@pytest.mark.parametrize("controller", CONTROLLERS)
def test_milestone_1_state_is_unchanged(controller):
    this_platform = (platform.system(), platform.machine())
    if this_platform not in GOLDEN_STATE:
        pytest.skip(
            f"no state digests recorded for {this_platform}; floating-point bits differ "
            "between platforms (D-027), so only the event digests can be checked here"
        )
    sim, _ = run_default(controller)
    assert sim.state_digest() == GOLDEN_STATE[this_platform][controller], (
        "the final state differs bit for bit. If test_milestone_1_events_are_unchanged "
        "passes, only float rounding changed (a NumPy or CPU difference, D-027); "
        "if it fails too, simulation behaviour changed"
    )
