"""Validated simulation configuration.

A YAML file is parsed once into an immutable ``SimulationConfig``. Everything downstream
can trust its values: types, ranges and cross-field rules are checked here, at the boundary.

Units used throughout Genesis Lab:
    distance  world units (the world is ``width`` x ``height`` units)
    time      ticks
    energy    energy units (EU); an abstract currency, not calories
    angle     radians
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

PositiveFloat = Annotated[float, Field(gt=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]

ControllerName = Literal["random_walk", "nearest_food_seeker"]


class ConfigError(ValueError):
    """Raised when a configuration file cannot be read as a configuration at all."""


class _Strict(BaseModel):
    # extra="forbid": a misspelled key is an error, not a silently ignored value.
    # frozen=True: configs cannot be modified after validation.
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunConfig(_Strict):
    seed: NonNegativeInt
    max_ticks: PositiveInt
    stop_on_extinction: bool = True


class WorldConfig(_Strict):
    width: PositiveFloat
    height: PositiveFloat


class FoodConfig(_Strict):
    initial_count: NonNegativeInt
    max_count: PositiveInt
    regrowth_per_tick: NonNegativeFloat = Field(
        description="Expected number of new food items per tick, while below max_count."
    )
    energy_value: PositiveFloat = Field(description="EU gained by eating one item.")
    eat_radius: PositiveFloat = Field(description="Max distance at which food can be eaten.")

    @model_validator(mode="after")
    def _initial_within_cap(self) -> Self:
        if self.initial_count > self.max_count:
            raise ValueError(
                f"initial_count ({self.initial_count}) exceeds max_count ({self.max_count})"
            )
        return self


class TraitsConfig(_Strict):
    """Initial per-organism traits. Fixed in Milestone 1; heritable from Milestone 2."""

    speed: PositiveFloat = Field(description="Max distance moved per tick.")
    sense_range: PositiveFloat = Field(description="Max distance at which food is detected.")
    max_turn: float = Field(gt=0, le=math.pi, description="Max heading change per tick.")
    metabolic_rate: NonNegativeFloat = Field(description="EU spent per tick just staying alive.")
    reproduction_threshold: PositiveFloat = Field(
        description="Energy at or above which an organism reproduces."
    )


class OrganismConfig(_Strict):
    initial_count: PositiveInt
    max_population: PositiveInt
    initial_energy: PositiveFloat
    max_age: PositiveInt | None = Field(default=None, description="Ticks; None means no limit.")
    move_cost_per_distance: NonNegativeFloat = Field(description="EU spent per unit moved.")
    offspring_energy: PositiveFloat = Field(description="EU transferred from parent to child.")
    reproduction_overhead: NonNegativeFloat = Field(
        description="EU lost by the parent when reproducing, beyond the transfer."
    )
    controller: ControllerName
    traits: TraitsConfig

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if self.initial_count > self.max_population:
            raise ValueError(
                f"initial_count ({self.initial_count}) exceeds "
                f"max_population ({self.max_population})"
            )
        cost = self.offspring_energy + self.reproduction_overhead
        if self.traits.reproduction_threshold <= cost:
            raise ValueError(
                f"traits.reproduction_threshold ({self.traits.reproduction_threshold}) must exceed "
                f"offspring_energy + reproduction_overhead ({cost}), "
                "or parents would reach zero energy by reproducing"
            )
        return self


class SimulationConfig(_Strict):
    run: RunConfig
    world: WorldConfig
    food: FoodConfig
    organisms: OrganismConfig

    # This rule compares two sections (food and world), so it must live here: SimulationConfig
    # is the only model that can see both. A validator inside FoodConfig only sees food fields.
    #
    # mode="after" runs it once every field has passed its own checks, so width, height and
    # eat_radius are already guaranteed to be positive floats when we compare them.
    @model_validator(mode="after")
    def _eat_radius_fits_world(self) -> Self:
        # The binding limit is the world's shorter side. Checking only width would accept a
        # radius that is wider than a narrow world is tall.
        shortest_side = min(self.world.width, self.world.height)
        if self.food.eat_radius > shortest_side:
            # Pydantic catches this ValueError and reports it as a ValidationError,
            # alongside any other problems in the file.
            raise ValueError(
                f"food.eat_radius ({self.food.eat_radius}) exceeds the world's shortest side "
                f"({shortest_side}); an organism anywhere could reach most of the world's food"
            )
        # Validators must return the model; returning nothing would discard the config.
        return self


def with_overrides(
    config: SimulationConfig, *, seed: int | None = None, max_ticks: int | None = None
) -> SimulationConfig:
    """Return a copy of ``config`` with selected run settings replaced, fully re-validated.

    Pydantic's ``model_copy(update=...)`` skips validation, so a bad override (a negative
    seed from the command line, say) would slip through. Dumping to a dict and validating
    again runs every rule.
    """
    raw = config.model_dump()
    if seed is not None:
        raw["run"]["seed"] = seed
    if max_ticks is not None:
        raw["run"]["max_ticks"] = max_ticks
    return SimulationConfig.model_validate(raw)


def load_config(path: str | Path) -> SimulationConfig:
    """Read and validate a YAML configuration file.

    Raises:
        FileNotFoundError: the file does not exist.
        ConfigError: the file is not valid YAML or its top level is not a mapping.
        pydantic.ValidationError: the values break a type, range or consistency rule.
    """
    text = Path(path).read_text(encoding="utf-8")
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: expected a mapping of sections, got {type(raw).__name__}")
    return SimulationConfig.model_validate(raw)
