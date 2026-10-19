"""Experiment specification files (experiments/specs/*.yaml).

An experiment is described as data: a base config, a list of conditions (named config
changes) and a list of seeds. Loading a spec builds and validates *every* run's config
before anything runs, so a typo in the last condition can't waste the first ones' time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from genesis.analytics.experiments import Condition, apply_changes
from genesis.core.config import SimulationConfig, load_config

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Labels become folder names (<label>-s<seed>), so keep them to safe characters.
Label = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_]+$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SeedRange(_Strict):
    first: int = Field(ge=0)
    count: int = Field(gt=0)

    def seeds(self) -> list[int]:
        return list(range(self.first, self.first + self.count))


class ConditionSpec(_Strict):
    label: Label
    changes: dict[str, object] = Field(default_factory=dict)  # dotted config paths
    # Optional (E007): this condition's own seeds instead of the experiment's, and extra
    # changes for particular seeds (e.g. the brains evolved for that world).
    seeds: SeedRange | list[Annotated[int, Field(ge=0)]] | None = None
    per_seed: dict[int, dict[str, object]] = Field(default_factory=dict)

    def seed_list(self) -> list[int] | None:
        if self.seeds is None:
            return None
        return self.seeds.seeds() if isinstance(self.seeds, SeedRange) else list(self.seeds)


class ExperimentSpec(_Strict):
    experiment_id: Annotated[str, StringConstraints(pattern=r"^E\d{3}$")]
    title: str
    definition: str  # path of the pre-registered definition document
    base_config: str  # path of a YAML config, relative to the project root
    base_changes: dict[str, object] = Field(default_factory=dict)  # applied to every condition
    seeds: SeedRange | list[Annotated[int, Field(ge=0)]]
    conditions: list[ConditionSpec] = Field(min_length=1)
    output: str | None = None  # default: data/experiments/<experiment_id>

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        labels = [c.label for c in self.conditions]
        if len(set(labels)) != len(labels):
            raise ValueError(f"condition labels must be distinct: {labels}")
        for c in self.conditions:
            seeds = self.seeds_for(c)
            if len(set(seeds)) != len(seeds):
                raise ValueError(f"seeds must be distinct (condition {c.label})")
            unknown = sorted(set(c.per_seed) - set(seeds))
            if unknown:
                raise ValueError(
                    f"condition {c.label}: per_seed names seeds it doesn't run: {unknown}"
                )
        return self

    def seed_list(self) -> list[int]:
        """The experiment's seeds (conditions may override them, see ``seeds_for``)."""
        return self.seeds.seeds() if isinstance(self.seeds, SeedRange) else list(self.seeds)

    def seeds_for(self, condition: ConditionSpec) -> list[int]:
        own = condition.seed_list()
        return own if own is not None else self.seed_list()

    def run_count(self) -> int:
        return sum(len(self.seeds_for(c)) for c in self.conditions)

    def output_dir(self, root: Path = PROJECT_ROOT) -> Path:
        return root / (self.output or f"data/experiments/{self.experiment_id}")

    def base(self, root: Path = PROJECT_ROOT) -> SimulationConfig:
        return apply_changes(load_config(root / self.base_config), self.base_changes)

    def smoke_copy(self, seeds: list[int], max_ticks: int) -> ExperimentSpec:
        """A tiny version for checking an experiment's code: throwaway seeds, short runs, and
        its own output folder, so it can never mix with (or overwrite) the real runs."""
        return self.model_copy(
            update={
                "seeds": list(seeds),
                "base_changes": {**self.base_changes, "run.max_ticks": max_ticks},
                "output": f"data/experiments/{self.experiment_id}-smoke",
            }
        )

    def condition(self, label: str) -> Condition:
        spec = next(c for c in self.conditions if c.label == label)
        return Condition(spec.label, dict(spec.changes))

    def configs(self, root: Path = PROJECT_ROOT) -> dict[tuple[str, int], SimulationConfig]:
        """Every run's validated config, keyed by (condition label, seed)."""
        base = self.base(root)
        return {
            (c.label, seed): apply_changes(
                base, {**c.changes, **c.per_seed.get(seed, {}), "run.seed": seed}
            )
            for c in self.conditions
            for seed in self.seeds_for(c)
        }


def load_spec(path: str | Path, root: Path = PROJECT_ROOT) -> ExperimentSpec:
    """Read a spec and check that every run's config is valid. Raises on any problem."""
    spec = ExperimentSpec.model_validate(yaml.safe_load(Path(path).read_text()))
    spec.configs(root)  # builds and validates every config now, before anything runs
    return spec
