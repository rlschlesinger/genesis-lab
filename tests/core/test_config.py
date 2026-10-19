"""Tests for configuration loading and validation."""

import copy
from pathlib import Path

import pydantic
import pytest
import yaml

from genesis.core.config import (
    ConfigError,
    SimulationConfig,
    config_hash,
    load_config,
    with_overrides,
)

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


def test_max_turn_range_above_pi_rejected(raw):
    raw["genome"]["max_turn"]["max"] = 4.0
    with pytest.raises(pydantic.ValidationError, match="max_turn"):
        validate(raw)


@pytest.mark.parametrize(
    ("gene", "bounds"),
    [
        ("speed", {"initial": 1.0, "min": 2.0, "max": 3.0}),  # initial below min
        ("speed", {"initial": 1.0, "min": 1.0, "max": 1.0}),  # empty range
        ("sense_range", {"initial": 5.0, "min": 3.0, "max": 1.0}),  # min above max
    ],
)
def test_badly_ordered_gene_rejected(raw, gene, bounds):
    raw["genome"][gene] = bounds
    with pytest.raises(pydantic.ValidationError, match=gene):
        validate(raw)


@pytest.mark.parametrize("gene", ["speed", "sense_range"])
def test_gene_range_that_reaches_zero_rejected(raw, gene):
    raw["genome"][gene]["min"] = 0.0
    with pytest.raises(pydantic.ValidationError, match=f"{gene}.min must be positive"):
        validate(raw)


def test_missing_gene_rejected(raw):
    del raw["genome"]["neutral_marker"]
    with pytest.raises(pydantic.ValidationError, match="neutral_marker"):
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


def test_reproduction_that_could_kill_parent_rejected(raw):
    # The *lowest* threshold mutation could reach must still pay for a child.
    org = raw["organisms"]
    raw["genome"]["reproduction_threshold"]["min"] = (
        org["offspring_energy"] + org["reproduction_overhead"]
    )
    with pytest.raises(pydantic.ValidationError, match="reproduction_threshold.min"):
        validate(raw)


def test_valid_variation_accepted(raw):
    variant = copy.deepcopy(raw)
    variant["organisms"]["controller"] = "random_walk"
    variant["organisms"]["max_age"] = 1000
    config = validate(variant)
    assert config.organisms.controller == "random_walk"
    assert config.organisms.max_age == 1000


def test_with_overrides_replaces_only_what_was_asked():
    config = load_config(DEFAULT_CONFIG)
    changed = with_overrides(config, seed=7, max_ticks=10)
    assert (changed.run.seed, changed.run.max_ticks) == (7, 10)
    assert changed.model_dump() | {"run": config.run.model_dump()} == config.model_dump()
    assert config.run.seed == 42  # the original is untouched (frozen)
    assert with_overrides(config) == config


@pytest.mark.parametrize(("field", "bad"), [("seed", -1), ("max_ticks", 0)])
def test_with_overrides_revalidates(field, bad):
    # model_copy(update=...) would let these through; with_overrides must not.
    with pytest.raises(pydantic.ValidationError, match=field):
        with_overrides(load_config(DEFAULT_CONFIG), **{field: bad})


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


@pytest.mark.parametrize(("field", "bad"), [("rate", 1.5), ("rate", -0.1), ("size", -0.01)])
def test_invalid_mutation_settings_rejected(raw, field, bad):
    raw["mutation"][field] = bad
    with pytest.raises(pydantic.ValidationError, match=field):
        validate(raw)


def test_default_config_has_mutation_off_and_all_genes_mutable():
    config = load_config(DEFAULT_CONFIG)
    assert config.mutation.enabled is False  # keeps Milestone 1 behaviour (regression tests)
    assert all(getattr(config.genome, g).mutable for g in type(config.genome).model_fields)


def flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for key, value in d.items():
        path = f"{prefix}{key}"
        out |= flatten(value, f"{path}.") if isinstance(value, dict) else {path: value}
    return out


def test_evolution_config_differs_only_where_intended():
    # evolution.yaml is a full copy of default.yaml; this keeps the copies from drifting apart.
    default = flatten(load_config(DEFAULT_CONFIG).model_dump())
    evolution = flatten(load_config(DEFAULT_CONFIG.with_name("evolution.yaml")).model_dump())
    differing = {key for key in default if default[key] != evolution[key]}
    assert differing == {
        "run.max_ticks",
        "organisms.speed_cost_exponent",
        "organisms.sense_cost_per_unit",
        "genome.max_turn.mutable",
        "mutation.enabled",
    }


def test_neural_config_differs_only_where_intended():
    # neural.yaml is a full copy of evolution.yaml: only the controller, the brain section and
    # the frozen expressed genes differ, so neural runs are comparable with E002-E006 settings.
    evolution = flatten(load_config(DEFAULT_CONFIG.with_name("evolution.yaml")).model_dump())
    neural = flatten(load_config(DEFAULT_CONFIG.with_name("neural.yaml")).model_dump())
    differing = {key for key in neural if neural[key] != evolution.get(key)}
    assert differing == {
        "organisms.controller",
        "genome.speed.mutable",
        "genome.sense_range.mutable",
        "genome.metabolic_rate.mutable",
        "genome.reproduction_threshold.mutable",
        "brain.weight_limit",
        "brain.initial_sd",
        "brain.mutation_rate",
        "brain.mutation_size",
    }


def test_neural_controller_requires_a_brain_section(raw):
    raw["organisms"]["controller"] = "neural"
    with pytest.raises(pydantic.ValidationError, match="needs a brain"):
        validate(raw)
    raw["brain"] = {}
    assert validate(raw).brain.weight_limit == 4.0


@pytest.mark.parametrize("field", ["speed_cost_exponent", "sense_cost_per_unit"])
def test_negative_costs_rejected(raw, field):
    raw["organisms"][field] = -0.1
    with pytest.raises(pydantic.ValidationError, match=field):
        validate(raw)


def test_snapshot_interval_must_be_positive(raw):
    raw["recording"]["genome_snapshot_every"] = 0
    with pytest.raises(pydantic.ValidationError, match="genome_snapshot_every"):
        validate(raw)


def test_recording_section_is_optional(raw):
    del raw["recording"]
    assert validate(raw).recording.genome_snapshot_every == 50


def test_config_hash_identifies_settings_not_formatting():
    config = load_config(DEFAULT_CONFIG)
    assert config_hash(config) == config_hash(load_config(DEFAULT_CONFIG))
    # Key order in the source doesn't matter...
    reordered = SimulationConfig.model_validate(dict(reversed(config.model_dump().items())))
    assert config_hash(reordered) == config_hash(config)
    # ...but any setting does, including the seed.
    assert config_hash(with_overrides(config, seed=7)) != config_hash(config)


@pytest.mark.parametrize("events", [["birth", "birth"], ["lunch"]])
def test_invalid_event_lists_rejected(raw, events):
    raw["recording"]["events"] = events
    with pytest.raises(pydantic.ValidationError, match="events"):
        validate(raw)


def test_ticks_every_must_be_positive(raw):
    raw["recording"]["ticks_every"] = 0
    with pytest.raises(pydantic.ValidationError, match="ticks_every"):
        validate(raw)
