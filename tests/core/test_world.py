"""Tests for World: construction from config, wall clamping, bounds checks."""

from pathlib import Path

import numpy as np
import pytest

from genesis.core.config import load_config
from genesis.core.resources import FoodSupply
from genesis.core.world import World

DEFAULT_CONFIG = Path(__file__).parents[2] / "configs" / "default.yaml"


@pytest.fixture
def world() -> World:
    return World(100.0, 50.0, FoodSupply(100.0, 50.0, max_count=10, regrowth_per_tick=0.0))


def test_from_config_spawns_initial_food():
    config = load_config(DEFAULT_CONFIG)
    world = World.from_config(config, np.random.default_rng(0))
    assert world.width == config.world.width
    assert world.food.count == config.food.initial_count
    assert world.contains(world.food.positions).all()


def test_from_config_is_deterministic():
    config = load_config(DEFAULT_CONFIG)
    a = World.from_config(config, np.random.default_rng(42))
    b = World.from_config(config, np.random.default_rng(42))
    np.testing.assert_array_equal(a.food.positions, b.food.positions)


def test_clamp_pushes_outside_points_onto_the_walls(world):
    outside = np.array([[-5.0, 10.0], [120.0, 60.0], [50.0, -0.1]])
    np.testing.assert_array_equal(
        world.clamp(outside),
        [[0.0, 10.0], [100.0, 50.0], [50.0, 0.0]],
    )


def test_clamp_leaves_inside_points_unchanged(world):
    inside = np.array([[0.0, 0.0], [100.0, 50.0], [33.3, 12.5]])
    np.testing.assert_array_equal(world.clamp(inside), inside)


def test_clamp_does_not_modify_its_input(world):
    points = np.array([[-5.0, 10.0]])
    world.clamp(points)
    assert points[0, 0] == -5.0


def test_clamp_accepts_a_single_point(world):
    np.testing.assert_array_equal(world.clamp([150.0, 25.0]), [100.0, 25.0])


def test_contains_includes_edges_and_excludes_outside(world):
    points = [[0.0, 0.0], [100.0, 50.0], [100.01, 10.0], [10.0, -1.0]]
    np.testing.assert_array_equal(world.contains(points), [True, True, False, False])


def test_invalid_bounds_rejected():
    food = FoodSupply(1.0, 1.0, max_count=1, regrowth_per_tick=0.0)
    with pytest.raises(ValueError):
        World(0.0, 10.0, food)
