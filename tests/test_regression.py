"""Golden-value regression tests: lock in the exact behaviour of recorded results.

These don't check that behaviour is *right* (other tests do that); they check it hasn't
*changed*. If one of these fails:

* If you meant to change simulation behaviour, the change invalidates earlier results.
  Record that in docs/decision-log.md, then update the digest here deliberately.
* If you didn't mean to (a refactor, a new feature that should be off by default),
  you've found a bug: something leaked into the default behaviour.

History of the golden values (the chain that ties them to experiment E001):

1. Recorded at commit 5c37894, the code that produced E001 (increment 2.0).
2. Increment 2.3 wired mutation into reproduction; with mutation disabled the *old* values
   still matched, so behaviour was unchanged.
3. Only then was state_digest() extended to include genes (otherwise a neutral-marker
   difference would be invisible), which changes every digest value. The values below were
   recorded with the new definition on that same, verified behaviour.
"""

from pathlib import Path

import pytest
import yaml

from genesis.core.config import SimulationConfig
from genesis.core.simulation import Simulation

DEFAULT_CONFIG = Path(__file__).parents[1] / "configs" / "default.yaml"

GOLDEN = {
    # controller -> state digest after 1000 ticks, default config, seed 42
    "nearest_food_seeker": "42b8e2b6b98b94420838e4d11518f2ef76452c40c479013ea78cc90b2212e0ea",
    "random_walk": "7fb0f1d30caf07cbf86f67bc479a931180d95315b7e4508468bef30461327883",
}


@pytest.mark.parametrize("controller", sorted(GOLDEN))
def test_milestone_1_behaviour_is_unchanged(controller):
    raw = yaml.safe_load(DEFAULT_CONFIG.read_text())
    raw["organisms"]["controller"] = controller
    raw["run"]["max_ticks"] = 1000
    sim = Simulation(SimulationConfig.model_validate(raw))
    sim.run()
    assert sim.state_digest() == GOLDEN[controller]
