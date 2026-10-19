"""Golden-value regression tests: lock in the exact behaviour of recorded results.

These don't check that behaviour is *right* (other tests do that); they check it hasn't
*changed*. The digests were recorded at the end of Milestone 1 (commit 5c37894), the code
that produced experiment E001. If one of these fails:

* If you meant to change simulation behaviour, the change invalidates earlier results.
  Record that in docs/decision-log.md, then update the digest here deliberately.
* If you didn't mean to (a refactor, a new feature that should be off by default),
  you've found a bug: something leaked into the default behaviour.
"""

from pathlib import Path

import pytest
import yaml

from genesis.core.config import SimulationConfig
from genesis.core.simulation import Simulation

DEFAULT_CONFIG = Path(__file__).parents[1] / "configs" / "default.yaml"

GOLDEN = {
    # controller -> state digest after 1000 ticks, default config, seed 42
    "nearest_food_seeker": "742095ba85644ba56ec661242af1dcb3948c8764e14b4697f67d67c221d3d7b5",
    "random_walk": "5e497e4b2c0bd31930a6e1e659d81eab4935258b1310585c79b900ced4e538b0",
}


@pytest.mark.parametrize("controller", sorted(GOLDEN))
def test_milestone_1_behaviour_is_unchanged(controller):
    raw = yaml.safe_load(DEFAULT_CONFIG.read_text())
    raw["organisms"]["controller"] = controller
    raw["run"]["max_ticks"] = 1000
    sim = Simulation(SimulationConfig.model_validate(raw))
    sim.run()
    assert sim.state_digest() == GOLDEN[controller]
