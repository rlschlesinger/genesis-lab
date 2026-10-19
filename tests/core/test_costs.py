"""Tests for the living-cost formulas (core/costs.py)."""

from pathlib import Path

import pytest

from genesis.core.config import OrganismConfig, load_config
from genesis.core.costs import metabolic_cost, movement_cost, sensing_cost
from genesis.core.organism import Traits

DEFAULT_CONFIG = Path(__file__).parents[2] / "configs" / "default.yaml"
REFERENCE_SPEED = 1.5


def traits(speed=1.5, sense_range=20.0, metabolic_rate=0.2) -> Traits:
    return Traits(speed=speed, sense_range=sense_range, max_turn=0.5,
                  metabolic_rate=metabolic_rate, reproduction_threshold=80.0)  # fmt: skip


def organisms(**changes) -> OrganismConfig:
    raw = load_config(DEFAULT_CONFIG).organisms.model_dump() | changes
    return OrganismConfig.model_validate(raw)


def test_metabolic_cost_is_the_rate():
    assert metabolic_cost(traits(metabolic_rate=0.13)) == 0.13


def test_sensing_cost_scales_with_range():
    cfg = organisms(sense_cost_per_unit=0.004)
    assert sensing_cost(traits(sense_range=20.0), cfg) == pytest.approx(0.08)
    assert sensing_cost(traits(sense_range=40.0), cfg) == pytest.approx(0.16)


def test_defaults_add_no_new_costs_and_match_milestone_1_exactly():
    cfg = organisms()
    assert sensing_cost(traits(sense_range=60.0), cfg) == 0.0
    for speed in (0.5, 1.5, 3.7):
        # Exact equality: exponent 0 must reproduce the Milestone 1 formula bit for bit.
        assert movement_cost(traits(speed=speed), 1.5, cfg, REFERENCE_SPEED) == 0.1 * 1.5


def test_founders_pay_the_milestone_1_price_with_drag_on():
    cfg = organisms(speed_cost_exponent=1.0)
    assert movement_cost(traits(speed=REFERENCE_SPEED), 1.5, cfg, REFERENCE_SPEED) == 0.1 * 1.5


def test_drag_makes_faster_organisms_pay_more_per_unit_distance():
    cfg = organisms(speed_cost_exponent=1.0)
    per_unit_fast = movement_cost(traits(speed=3.0), 1.0, cfg, REFERENCE_SPEED)
    per_unit_slow = movement_cost(traits(speed=0.75), 1.0, cfg, REFERENCE_SPEED)
    assert per_unit_fast == pytest.approx(0.1 * 2.0)  # twice the founder speed: twice the price
    assert per_unit_slow == pytest.approx(0.1 * 0.5)


def test_with_drag_full_speed_cost_per_tick_grows_with_speed_squared():
    cfg = organisms(speed_cost_exponent=1.0)
    # At full speed, distance per tick = speed, so cost per tick ~ speed x speed.
    cost_1x = movement_cost(traits(speed=1.5), 1.5, cfg, REFERENCE_SPEED)
    cost_2x = movement_cost(traits(speed=3.0), 3.0, cfg, REFERENCE_SPEED)
    assert cost_2x / cost_1x == pytest.approx(4.0)


def test_no_movement_costs_nothing():
    cfg = organisms(speed_cost_exponent=2.0)
    assert movement_cost(traits(speed=4.0), 0.0, cfg, REFERENCE_SPEED) == 0.0


# --- living_costs: the same formulas for a whole population, bit for bit (D-038) --------------


@pytest.mark.parametrize("exponent", [0.0, 1.0, 0.5, 1.7, 2.0])
def test_living_costs_match_the_scalar_formulas_exactly(exponent):
    import numpy as np

    from genesis.core.costs import living_costs

    cfg = organisms(speed_cost_exponent=exponent, sense_cost_per_unit=0.004)
    rng = np.random.default_rng(int(exponent * 10))
    n = 400
    speeds = rng.uniform(0.25, 4.0, n)
    sense_ranges = rng.uniform(1.0, 60.0, n)
    rates = rng.uniform(0.02, 0.5, n)
    distances = rng.uniform(0.0, 4.0, n)
    distances[::5] = 0.0
    metabolism, sensing, movement = living_costs(
        rates, sense_ranges, speeds, distances, cfg, REFERENCE_SPEED
    )
    for i in range(n):
        t = traits(speed=speeds[i], sense_range=sense_ranges[i], metabolic_rate=rates[i])
        assert metabolism[i] == metabolic_cost(t)
        assert sensing[i] == sensing_cost(t, cfg)
        assert movement[i] == movement_cost(t, float(distances[i]), cfg, REFERENCE_SPEED)
