"""Tests for movement: direction, physical limits, walls, and a sense-decide-move loop."""

import numpy as np
import pytest

from genesis.core.movement import move
from genesis.core.resources import FoodSupply
from genesis.core.world import World
from genesis.intelligence.controllers import Actions, NearestFoodSeeker
from genesis.intelligence.sensors import sense_food


@pytest.fixture
def world() -> World:
    return World(100.0, 100.0, FoodSupply(100.0, 100.0, max_count=10, regrowth_per_tick=0.0))


def move_one(world, x, y, heading, turn=0.0, throttle=1.0, speed=1.5, max_turn=0.5):
    return move(
        positions=np.array([[x, y]], dtype=float),
        headings=np.array([heading], dtype=float),
        actions=Actions(turn=np.array([turn]), throttle=np.array([throttle])),
        speeds=np.array([speed]),
        max_turns=np.array([max_turn]),
        world=world,
    )


def test_heading_zero_moves_along_x(world):
    r = move_one(world, 50, 50, heading=0.0)
    np.testing.assert_allclose(r.positions[0], [51.5, 50.0])
    assert r.distances[0] == pytest.approx(1.5)


def test_heading_quarter_turn_moves_along_y(world):
    r = move_one(world, 50, 50, heading=np.pi / 2)
    np.testing.assert_allclose(r.positions[0], [50.0, 51.5], atol=1e-12)


def test_turn_happens_before_the_step(world):
    r = move_one(world, 50, 50, heading=0.0, turn=0.5, max_turn=0.5)
    assert r.headings[0] == pytest.approx(0.5)
    np.testing.assert_allclose(r.positions[0], [50 + 1.5 * np.cos(0.5), 50 + 1.5 * np.sin(0.5)])


@pytest.mark.parametrize("requested", [3.0, -3.0])
def test_turn_is_limited_to_max_turn(world, requested):
    r = move_one(world, 50, 50, heading=0.0, turn=requested, max_turn=0.5)
    assert r.headings[0] == pytest.approx(np.sign(requested) * 0.5)


@pytest.mark.parametrize(("requested", "expected"), [(5.0, 1.5), (-1.0, 0.0), (0.5, 0.75)])
def test_throttle_is_limited_to_zero_through_one(world, requested, expected):
    r = move_one(world, 50, 50, heading=0.0, throttle=requested, speed=1.5)
    assert r.distances[0] == pytest.approx(expected)


def test_wall_stops_movement_and_distance_is_what_was_actually_moved(world):
    r = move_one(world, 99.5, 50, heading=0.0, speed=1.5)
    np.testing.assert_allclose(r.positions[0], [100.0, 50.0])
    assert r.distances[0] == pytest.approx(0.5)  # charged for 0.5, not the 1.5 requested


def test_organism_pressed_against_wall_does_not_move(world):
    r = move_one(world, 100.0, 50, heading=0.0)
    assert r.distances[0] == 0.0


def test_heading_stays_wrapped(world):
    r = move_one(world, 50, 50, heading=np.pi - 0.1, turn=0.5, max_turn=0.5)
    assert -np.pi <= r.headings[0] < np.pi


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_non_finite_actions_rejected(world, bad):
    with pytest.raises(ValueError, match="non-finite"):
        move_one(world, 50, 50, heading=0.0, turn=bad)


def test_inputs_are_not_modified(world):
    positions = np.array([[50.0, 50.0]])
    headings = np.array([0.0])
    move(positions, headings, Actions(np.array([0.3]), np.array([1.0])),
         np.array([1.5]), np.array([0.5]), world)  # fmt: skip
    assert positions[0, 0] == 50.0 and headings[0] == 0.0


def test_seeker_reaches_food_behind_it(world):
    # Integration: sense -> decide -> move, repeated. Food is behind the organism, so it
    # must first turn around (limited to 0.5 rad per tick), then approach.
    #
    # We check the *closest* approach, not the final position. Eating doesn't exist yet
    # (increment 1.6), so after arriving the seeker overshoots and circles: at speed 1.5 and
    # max_turn 0.5 its tightest turning circle has radius 3, so it can't stop on the spot.
    # In a full simulation it would have eaten the food on first arrival.
    positions, headings = np.array([[50.0, 50.0]]), np.array([0.0])
    food = np.array([[40.0, 50.0]])
    seeker, rng = NearestFoodSeeker(), np.random.default_rng(0)
    closest = np.inf
    for _ in range(20):
        obs = sense_food(positions, headings, np.array([20.0]), np.array([50.0]), food)
        actions = seeker.decide(obs, rng)
        result = move(positions, headings, actions, np.array([1.5]), np.array([0.5]), world)
        positions, headings = result.positions, result.headings
        closest = min(closest, np.hypot(*(positions[0] - food[0])))
    assert closest < 2.0  # came within the default eat radius
