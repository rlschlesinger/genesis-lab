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

import hashlib
import json
import math
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

PositiveFloat = Annotated[float, Field(gt=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]

# Parameters in one brain: 7 inputs x 6 hidden + 6 + 6 x 2 outputs + 2 (D-039). Kept here as a
# number so config validation doesn't import the network code; a test checks it matches.
BRAIN_PARAMETERS = 62

ControllerName = Literal["random_walk", "nearest_food_seeker", "neural"]
# Predators can't use the food seeker (they don't eat food). 6.3 adds prey-seeking and neural.
PredatorControllerName = Literal["random_walk"]
EventKind = Literal["birth", "death", "meal"]


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


class GeneConfig(_Strict):
    """One gene: every founder's starting value, and the range mutation must stay within."""

    initial: float
    min: float
    max: float
    mutable: bool = Field(
        default=True, description="False freezes this gene: offspring always copy it exactly."
    )
    neutral: bool = Field(
        default=False,
        description=(
            "True makes this gene a drift-only control: it is still inherited and still "
            "mutates, but has no effect, since every organism behaves as if it had the "
            "initial value. Used for neutral-twin control runs (D-025)."
        ),
    )

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not self.min < self.max:
            raise ValueError(f"min ({self.min}) must be less than max ({self.max})")
        if not self.min <= self.initial <= self.max:
            raise ValueError(f"initial ({self.initial}) must lie in [{self.min}, {self.max}]")
        return self


class GenomeConfig(_Strict):
    """The heritable genes. Units as in genesis.evolution.genome.GENES.

    Each gene's whole range must be physically valid, not just its starting value: from
    Milestone 2, mutation can carry a gene anywhere between its min and max.
    """

    speed: GeneConfig
    sense_range: GeneConfig
    max_turn: GeneConfig
    metabolic_rate: GeneConfig
    reproduction_threshold: GeneConfig
    neutral_marker: GeneConfig

    @model_validator(mode="after")
    def _physical_ranges(self) -> Self:
        if self.speed.min <= 0:
            raise ValueError("speed.min must be positive")
        if self.sense_range.min <= 0:
            raise ValueError("sense_range.min must be positive")
        if self.max_turn.min <= 0 or self.max_turn.max > math.pi:
            raise ValueError("max_turn must stay within (0, pi]")
        if self.metabolic_rate.min < 0:
            raise ValueError("metabolic_rate.min must be >= 0")
        return self


class OrganismConfig(_Strict):
    initial_count: PositiveInt
    max_population: PositiveInt
    initial_energy: PositiveFloat
    max_age: PositiveInt | None = Field(default=None, description="Ticks; None means no limit.")
    move_cost_per_distance: NonNegativeFloat = Field(description="EU spent per unit moved.")
    speed_cost_exponent: NonNegativeFloat = Field(
        default=0.0,
        description="Drag: movement cost is scaled by (speed / founder speed) ** this. 0 = off.",
    )
    sense_cost_per_unit: NonNegativeFloat = Field(
        default=0.0, description="EU per tick per unit of sense range (sensory upkeep). 0 = off."
    )
    offspring_energy: PositiveFloat = Field(description="EU transferred from parent to child.")
    reproduction_overhead: NonNegativeFloat = Field(
        description="EU lost by the parent when reproducing, beyond the transfer."
    )
    controller: ControllerName

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if self.initial_count > self.max_population:
            raise ValueError(
                f"initial_count ({self.initial_count}) exceeds "
                f"max_population ({self.max_population})"
            )
        return self


class PredatorConfig(OrganismConfig):
    """A second species that hunts prey (Milestone 6, roadmap 06A; D-057). Optional: a config
    without this section has no predators and runs exactly as before.

    Predators have the same kind of body as prey (the inherited fields: population, energy,
    costs, reproduction) with their own values, and their own genome ranges, so they can be
    faster, see further or burn more. They never eat food; from 6.2 they eat prey. Mutation
    uses the shared ``mutation`` section, applied to these ranges.
    """

    controller: PredatorControllerName = "random_walk"  # type: ignore[assignment]
    genome: GenomeConfig

    @model_validator(mode="after")
    def _reproduction_affordable(self) -> Self:
        # The same rule as for prey (SimulationConfig._reproduction_affordable), here because
        # a predator's body and genome live in one section.
        cost = self.offspring_energy + self.reproduction_overhead
        lowest = self.genome.reproduction_threshold.min
        if lowest <= cost:
            raise ValueError(
                f"predators: genome.reproduction_threshold.min ({lowest}) must exceed "
                f"offspring_energy + reproduction_overhead ({cost})"
            )
        return self


class MutationConfig(_Strict):
    """How offspring genomes differ from their parent's (genesis.evolution.mutation)."""

    enabled: bool = Field(description="False: offspring are exact copies (Milestone 1 behaviour).")
    rate: float = Field(ge=0, le=1, description="Probability that each gene mutates at a birth.")
    size: NonNegativeFloat = Field(
        description="Standard deviation of a mutation, as a fraction of the gene's range."
    )


class BrainConfig(_Strict):
    """Neural brains (Milestone 4, genesis.intelligence.neural): how founders' weights are drawn
    and how they mutate. The network's shape is fixed (7 inputs, 6 hidden, 2 outputs; D-039).

    Weights are in their own units (a weight of 1 passes an input through unscaled), so the
    mutation size is an absolute standard deviation, not a fraction of a range as for genes.
    """

    weight_limit: PositiveFloat = Field(
        default=4.0,
        description="Every weight and bias stays within [-limit, limit] (reflected, as genes).",
    )
    initial_sd: PositiveFloat = Field(
        default=0.5, description="Founders' weights: Normal(0, initial_sd), one brain each."
    )
    mutation_rate: float = Field(
        default=0.1, ge=0, le=1, description="Probability that each weight mutates at a birth."
    )
    mutation_size: NonNegativeFloat = Field(
        default=0.2, description="Standard deviation of one weight's mutation step."
    )
    founder_weights: list[list[float]] | None = Field(
        default=None,
        description=(
            "Explicit brains for the founders, one 62-number vector per founder (in "
            "Brain.to_vector() order), e.g. brains evolved in another run (E007). None: draw "
            "random brains. Stored in the config so its hash identifies the exact brains."
        ),
    )

    @model_validator(mode="after")
    def _founder_weights_valid(self) -> Self:
        if self.founder_weights is None:
            return self
        for k, vector in enumerate(self.founder_weights):
            if len(vector) != BRAIN_PARAMETERS:
                raise ValueError(
                    f"founder_weights[{k}] has {len(vector)} numbers; "
                    f"a brain has {BRAIN_PARAMETERS}"
                )
            if not all(math.isfinite(w) and abs(w) <= self.weight_limit for w in vector):
                raise ValueError(
                    f"founder_weights[{k}] has a value that is not finite or exceeds "
                    f"weight_limit ({self.weight_limit})"
                )
        return self


class RecordingConfig(_Strict):
    """What a recorded run saves beyond the per-tick summaries (genesis.analytics.recorder).

    Not part of the simulation itself: changing it never changes results, only what is kept.
    """

    genome_snapshot_every: PositiveInt = Field(
        default=50, description="Ticks between snapshots of every living genome (genomes.csv)."
    )
    ticks_every: PositiveInt = Field(
        default=1,
        description=(
            "Ticks between rows of ticks.csv and gene_stats.csv (the final tick is always "
            "kept). Flow columns (births, deaths, meals...) hold totals since the previous row."
        ),
    )
    events: tuple[EventKind, ...] = Field(
        default=(), description="Event kinds to log in events.csv: birth, death, meal."
    )

    @model_validator(mode="after")
    def _distinct_events(self) -> Self:
        if len(set(self.events)) != len(self.events):
            raise ValueError(f"events lists a kind twice: {list(self.events)}")
        return self


class SimulationConfig(_Strict):
    run: RunConfig
    world: WorldConfig
    food: FoodConfig
    organisms: OrganismConfig
    genome: GenomeConfig
    mutation: MutationConfig
    recording: RecordingConfig = RecordingConfig()
    # None: no brains (rule-based controllers). Present: every organism carries a brain.
    brain: BrainConfig | None = None
    # None: no predators (every config before Milestone 6). Present: a second species (D-057).
    predators: PredatorConfig | None = None

    @model_serializer(mode="wrap")
    def _omit_absent_sections(self, handler):  # noqa: ANN001, ANN202 (pydantic's own signature)
        """Leave optional sections (``brain``, ``predators``) out of the dump when they are None.

        A config's dump is hashed (``config_hash``) and saved in run.json. Without this, every
        older config would gain ``"brain": null`` or ``"predators": null``, change its hash,
        and make every completed run of E001-E007 look stale to the batch runner, though
        nothing about those runs changed. Omitting empty sections keeps old configs
        byte-identical.
        """
        data = handler(self)
        for name in ("brain", "predators"):
            if getattr(self, name) is None:
                data.pop(name, None)
        return data

    @model_validator(mode="after")
    def _neural_needs_brains(self) -> Self:
        # The reverse is allowed: brains carried by a rule-based controller are inherited and
        # mutated but never used, a no-selection control for brain weights.
        if self.organisms.controller == "neural" and self.brain is None:
            raise ValueError("controller 'neural' needs a brain: section (it may be empty: {})")
        return self

    @model_validator(mode="after")
    def _one_brain_per_founder(self) -> Self:
        if self.brain is not None and self.brain.founder_weights is not None:
            given, needed = len(self.brain.founder_weights), self.organisms.initial_count
            if given != needed:
                raise ValueError(
                    f"brain.founder_weights has {given} brains for {needed} founders "
                    "(organisms.initial_count)"
                )
        return self

    @model_validator(mode="after")
    def _reproduction_affordable(self) -> Self:
        # Checked against the *lowest* threshold mutation could reach, not just the starting
        # value: an organism anywhere in the range must be able to afford a child.
        cost = self.organisms.offspring_energy + self.organisms.reproduction_overhead
        lowest = self.genome.reproduction_threshold.min
        if lowest <= cost:
            raise ValueError(
                f"genome.reproduction_threshold.min ({lowest}) must exceed "
                f"offspring_energy + reproduction_overhead ({cost}), "
                "or parents could reach zero energy by reproducing"
            )
        return self

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


def config_hash(config: SimulationConfig) -> str:
    """SHA-256 of the config in a canonical form: identical configs give identical hashes.

    Canonical means keys sorted and no optional whitespace, so the same settings always
    produce the same text, whatever order a YAML file listed them in. The seed is included:
    two runs with the same hash should produce the same results (on the same platform).
    """
    return hash_config_dict(config.model_dump(mode="json"))


def hash_config_dict(raw: dict) -> str:
    """``config_hash`` for a config already in JSON form (e.g. read back from run.json).

    Works for configs from older code that no longer validate against today's schema, so
    every recorded run can be fingerprinted the same way.
    """
    text = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
