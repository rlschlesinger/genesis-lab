"""Mutation: how a child's genome differs from its parent's.

For each gene, at each birth:

1. A uniform draw decides whether the gene mutates (probability ``rate``).
2. A normal draw gives the step: mean 0, standard deviation ``size * (max - min)``. Mean 0
   means mutation has no built-in direction; any consistent trend in a trait must come from
   selection or chance, never from the mutation rule itself.
3. A step that would leave ``[min, max]`` is *reflected* back inside (``reflect``).

Both draws happen for every gene at every birth, even when the gene doesn't mutate or is
frozen (``mutable: false``). The mutation stream then advances by the same amount per birth
regardless of outcomes, so one change can't shift every later mutation (as in D-009).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from genesis.core.config import GenomeConfig, MutationConfig
from genesis.evolution.genome import Genome, gene_names


@dataclass(frozen=True, slots=True)
class GeneChange:
    """One mutation: which gene, and its value before and after."""

    gene: str
    before: float
    after: float

    @property
    def delta(self) -> float:
        return self.after - self.before


def reflect(value: float, low: float, high: float) -> float:
    """Fold ``value`` back into ``[low, high]`` as if bouncing off walls.

    4.3 with bounds [0, 4] becomes 3.7; -0.5 becomes 0.5. Works for steps of any size (it may
    bounce several times), because reflection repeats with period 2 * (high - low).

    Why not clamp (4.3 -> 4.0)? Clamping parks every overshooting mutation exactly on the
    bound, so values pile up there over generations. That pile-up looks like selection for
    the extreme, but it would be an artefact of the rule. Reflection has no such bias: a gene
    with no selection on it stays evenly spread across its range.
    """
    width = high - low
    t = (value - low) % (2 * width)  # position within one there-and-back cycle
    if t > width:
        t = 2 * width - t  # on the way back
    return low + t


def mutate(
    genome: Genome,
    genome_config: GenomeConfig,
    mutation_config: MutationConfig,
    rng: np.random.Generator,
) -> tuple[Genome, list[GeneChange]]:
    """Return a child genome and the list of genes that changed.

    The parent's genome is never modified (Genome is frozen); a new one is returned. When
    mutation is disabled, the parent's genome itself is returned and no random numbers are
    drawn, so a disabled run's mutation stream is never touched.
    """
    if not mutation_config.enabled:
        return genome, []

    names = gene_names()
    # One vectorized call per draw type: all genes' "does it mutate?" draws, then all steps.
    mutates = rng.random(len(names)) < mutation_config.rate
    unit_steps = rng.normal(0.0, 1.0, size=len(names))

    updates: dict[str, float] = {}
    changes: list[GeneChange] = []
    for name, hit, unit_step in zip(names, mutates, unit_steps, strict=True):
        bounds = getattr(genome_config, name)
        if not (hit and bounds.mutable):
            continue
        before = getattr(genome, name)
        step = float(unit_step) * mutation_config.size * (bounds.max - bounds.min)
        after = reflect(before + step, bounds.min, bounds.max)
        if after != before:
            updates[name] = after
            changes.append(GeneChange(name, before, after))

    # dataclasses.replace builds a new frozen Genome with only the changed fields swapped.
    return (replace(genome, **updates) if updates else genome), changes
