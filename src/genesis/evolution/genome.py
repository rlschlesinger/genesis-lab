"""The genome (genotype) and its expression into traits (phenotype).

Genotype: the heritable information an organism carries and passes to its offspring.
Phenotype: what the organism actually is and does: how fast it moves, how far it sees.
Expression: the mapping from one to the other, ``express(genome, config) -> Traits``.

In Milestone 2 expression is nearly a copy, with one deliberate exception: the neutral marker
is inherited but not expressed, so it never affects survival or reproduction. Any change in
it over time is drift (chance), which makes it the in-run control for detecting selection.

Genes are stored in their trait units (speed in world units/tick, and so on), not rescaled to
0-1. Rescaling and back can change a value by one rounding step (1.5 -> 1.5000000000000002),
which would silently alter Milestone 1 results (tests/test_regression.py guards this).
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from genesis.core.config import GenomeConfig
from genesis.core.organism import Traits


@dataclass(frozen=True, slots=True)
class GeneInfo:
    unit: str
    description: str
    expressed: bool  # False: inherited but has no effect on the organism


# The single list of genes. Genome's fields, GenomeConfig's fields and this dict must name the
# same genes in the same order (tests/evolution/test_genome.py checks this).
GENES: dict[str, GeneInfo] = {
    "speed": GeneInfo("world units/tick", "maximum distance moved per tick", True),
    "sense_range": GeneInfo("world units", "maximum distance at which food is detected", True),
    "max_turn": GeneInfo("radians/tick", "maximum heading change per tick", True),
    "metabolic_rate": GeneInfo(
        "EU/tick", "energy burned per tick just staying alive; lower is more efficient", True
    ),
    "reproduction_threshold": GeneInfo(
        "EU", "energy at or above which the organism reproduces", True
    ),
    "neutral_marker": GeneInfo(
        "none", "no effect on the organism; shows how much a gene drifts by chance", False
    ),
}


@dataclass(frozen=True, slots=True, kw_only=True)
class Genome:
    """One organism's genes. Frozen: a genome never changes during a lifetime.

    Offspring receive a (possibly mutated) *new* Genome; the parent's is never modified.
    """

    speed: float
    sense_range: float
    max_turn: float
    metabolic_rate: float
    reproduction_threshold: float
    neutral_marker: float

    @classmethod
    def from_config(cls, config: GenomeConfig) -> Genome:
        """The founders' genome: every gene at its configured ``initial`` value."""
        return cls(**{name: getattr(config, name).initial for name in gene_names()})

    def as_dict(self) -> dict[str, float]:
        # Same as dataclasses.asdict(self), minus its deep copy of each value (floats need
        # none); called at every birth and in every genome snapshot.
        return {name: getattr(self, name) for name in _GENE_NAMES}


def gene_names() -> list[str]:
    return [f.name for f in fields(Genome)]


_GENE_NAMES: tuple[str, ...] = tuple(gene_names())


def express(genome: Genome, config: GenomeConfig | None = None) -> Traits:
    """Genotype -> phenotype. Unexpressed genes (the neutral marker) are left out.

    If ``config`` marks a gene ``neutral``, the phenotype uses that gene's *initial* value
    instead of the organism's own: the gene keeps being inherited and mutated, but can't
    affect survival or reproduction. A run with neutral genes shows exactly what drift alone
    does to each gene, from its real starting point (the neutral-twin control, D-025).
    """
    values = genome.as_dict()
    if config is not None:
        for name in values:
            gene = getattr(config, name)
            if gene.neutral:
                values[name] = gene.initial
    return Traits(
        speed=values["speed"],
        sense_range=values["sense_range"],
        max_turn=values["max_turn"],
        metabolic_rate=values["metabolic_rate"],
        reproduction_threshold=values["reproduction_threshold"],
    )
