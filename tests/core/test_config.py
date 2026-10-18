"""Tests for configuration loading and validation."""

import copy
from pathlib import Path

import pydantic
import pytest
import yaml

from genesis.core.config import ConfigError, SimulationConfig, load_config

DEFAULT_CONFIG = Path(__file__).parents[2] / "configs" / "default.yaml"


@pytest.fixture
def raw() -> dict:
    """The default config as a plain dict, ready to be broken one field at a time."""
    return yaml.safe_load(DEFAULT_CONFIG.read_text())


def validate(raw: dict) -> SimulationConfig:
    return SimulationConfig.model_validate(raw)


def test_default_config_loads():
    config = load_config(DEFAULT_CONFIG)
    assert config.run.seed == 42
    assert config.organisms.controller == "nearest_food_seeker"
    assert config.organisms.max_age is None


def test_config_is_immutable():
    config = load_config(DEFAULT_CONFIG)
    with pytest.raises(pydantic.ValidationError):
        config.run.seed = 7


@pytest.mark.parametrize(
    ("section", "field", "bad_value"),
    [
        ("world", "width", -10.0),
        ("world", "height", 0.0),
        ("food", "energy_value", 0.0),
        ("food", "regrowth_per_tick", -1.0),
        ("organisms", "initial_count", 0),
        ("run", "max_ticks", 0),
        ("run", "seed", -1),
    ],
)
def test_out_of_range_values_rejected(raw, section, field, bad_value):
    raw[section][field] = bad_value
    with pytest.raises(pydantic.ValidationError, match=field):
        validate(raw)


def test_max_turn_above_pi_rejected(raw):
    raw["organisms"]["traits"]["max_turn"] = 4.0
    with pytest.raises(pydantic.ValidationError, match="max_turn"):
        validate(raw)


def test_misspelled_key_rejected(raw):
    raw["food"]["energy_valu"] = raw["food"].pop("energy_value")
    with pytest.raises(pydantic.ValidationError, match="energy_valu"):
        validate(raw)


def test_unknown_controller_rejected(raw):
    raw["organisms"]["controller"] = "telepathic"
    with pytest.raises(pydantic.ValidationError, match="controller"):
        validate(raw)


def test_missing_section_rejected(raw):
    del raw["world"]
    with pytest.raises(pydantic.ValidationError, match="world"):
        validate(raw)


def test_initial_food_above_cap_rejected(raw):
    raw["food"]["initial_count"] = raw["food"]["max_count"] + 1
    with pytest.raises(pydantic.ValidationError, match="exceeds max_count"):
        validate(raw)


def test_initial_population_above_cap_rejected(raw):
    raw["organisms"]["initial_count"] = raw["organisms"]["max_population"] + 1
    with pytest.raises(pydantic.ValidationError, match="exceeds max_population"):
        validate(raw)


def test_reproduction_that_would_kill_parent_rejected(raw):
    org = raw["organisms"]
    org["traits"]["reproduction_threshold"] = org["offspring_energy"] + org["reproduction_overhead"]
    with pytest.raises(pydantic.ValidationError, match="reproduction_threshold"):
        validate(raw)


def test_valid_variation_accepted(raw):
    variant = copy.deepcopy(raw)
    variant["organisms"]["controller"] = "random_walk"
    variant["organisms"]["max_age"] = 1000
    config = validate(variant)
    assert config.organisms.controller == "random_walk"
    assert config.organisms.max_age == 1000


def test_non_mapping_file_rejected(tmp_path):
    path = tmp_path / "list.yaml"
    path.write_text("- just\n- a list\n")
    with pytest.raises(ConfigError, match="expected a mapping"):
        load_config(path)


def test_empty_file_rejected(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("")
    with pytest.raises(ConfigError, match="NoneType"):
        load_config(path)


def test_malformed_yaml_rejected(tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("run: {seed: 1\n")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


# Two tests, one per dimension: together they show the rule uses the *shorter* side,
# not just width. Each breaks exactly one thing, starting from the valid default.
def test_eat_radius_wider_than_world_rejected(raw):
    raw["food"]["eat_radius"] = 500.0  # default world is 200 x 200
    with pytest.raises(pydantic.ValidationError, match="eat_radius"):
        validate(raw)


def test_eat_radius_taller_than_narrow_world_rejected(raw):
    raw["world"]["height"] = 10.0  # narrow world: 200 wide, 10 tall
    raw["food"]["eat_radius"] = 50.0  # fits the width, not the height
    with pytest.raises(pydantic.ValidationError, match="shortest side"):
        validate(raw)
