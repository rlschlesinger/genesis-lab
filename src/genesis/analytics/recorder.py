"""RunRecorder: decides what to keep from each tick of a run.

The simulation knows nothing about files or sampling intervals; the recorder watches it after
every tick and collects rows. That keeps recording policy (what, how often) out of the
simulation core.

Collected per run:

    ticks        one TickSummary row per tick
    gene_stats   one row per (tick, gene): n, mean, sd, min, max over the living population
    genomes      every living organism's genes, every ``genome_snapshot_every`` ticks and on
                 the final tick
    events       optional log of births, deaths and meals (``recording.events``)
    behaviour    one row per recorded tick: what organisms did, and brain diversity and drift
                 (analytics/behaviour.py; every controller, brain columns only with brains)
    predator_ticks  worlds with predators only (D-060): one PredatorSummary row per
                 recorded tick, sampled like ticks
    strikes      worlds with predators only: every strike, caught or not

With ``ticks_every`` > 1, ticks, gene_stats and behaviour keep every n-th tick (plus the final
one).

gene_stats uses "tidy" (long) format: one observation per row, with the gene name as a column
value rather than baked into column names. Analysis tools (pandas, DuckDB, Plotly) can then
filter, group and plot any gene the same way.
"""

from __future__ import annotations

import math
import operator
from dataclasses import fields

import numpy as np

from genesis.analytics.behaviour import behaviour_row
from genesis.analytics.metrics import (
    GENE_FIELDS,
    PREDATOR_FLOW_FIELDS,
    STRIKE_FIELDS,
    predator_tick_row,
    tick_row,
)
from genesis.core.simulation import Event, Simulation, TickSummary
from genesis.evolution.genome import gene_names

GENE_STAT_FIELDS: list[str] = ["tick", "gene", "n", "mean", "sd", "min", "max"]
EVENT_FIELDS: list[str] = ["tick", "seq", "kind", "organism_id", "other_id", "energy", "x", "y",
                           "detail"]  # fmt: skip
# Event's own field names, in order: used instead of dataclasses.asdict, which deep-copies
# every value and costs ~20x more for the same plain dict.
_EVENT_FIELD_NAMES: tuple[str, ...] = tuple(f.name for f in fields(Event))
# All six genes of a genome in one call: genome -> (speed, sense_range, ...).
_GENES_OF = operator.attrgetter(*gene_names())
# TickSummary columns that count things happening *during* a tick (flows, not stocks).
FLOW_FIELDS: tuple[str, ...] = ("births", "deaths", "food_spawned", "food_eaten", "mutations")
# The same gene_* column names as organisms.csv, so the two files can be joined on them.
GENOME_SNAPSHOT_FIELDS: list[str] = ["tick", "id", *GENE_FIELDS]


def gene_stat_rows(tick: int, genome_values: dict[str, list[float]]) -> list[dict]:
    """Summary statistics per gene for one set of organisms.

    ``sd`` is the *population* standard deviation (dividing by n, NumPy's default ddof=0):
    these numbers describe exactly the organisms alive, not an estimate of some larger group.
    An empty population gets n = 0 and NaN statistics ("no value", not zero).
    """
    names = list(genome_values)
    counts = {len(values) for values in genome_values.values()}
    if len(counts) > 1:
        raise ValueError(f"every gene needs one value per organism, got counts {sorted(counts)}")
    matrix = np.array([genome_values[g] for g in names], dtype=np.float64).reshape(len(names), -1)
    return _stat_rows(tick, names, matrix)


def _stat_rows(tick: int, names: list[str], matrix: np.ndarray) -> list[dict]:
    """``gene_stat_rows`` on a C-contiguous (genes, organisms) array: one row per gene.

    All genes are reduced in one NumPy call per statistic (``axis=1``) instead of one call per
    gene. Each row of the matrix is one gene's values laid out contiguously in memory, so
    NumPy sums each row with exactly the same pairwise algorithm it uses for a 1-D array, and
    the results are bit for bit what the per-gene version produced (D-038; checked in
    tests/analytics/test_recorder.py). A (organisms, genes) layout reduced along axis 0 would
    *not* be: there NumPy accumulates in a different order.
    """
    n = matrix.shape[1]
    if n == 0:
        stats = [(math.nan,) * 4] * len(names)
    else:
        if not matrix.flags.c_contiguous:
            raise ValueError("gene matrix must be C-contiguous (genes as rows)")
        stats = zip(
            matrix.mean(axis=1).tolist(),
            matrix.std(axis=1).tolist(),
            matrix.min(axis=1).tolist(),
            matrix.max(axis=1).tolist(),
            strict=True,
        )
    return [
        dict(zip(GENE_STAT_FIELDS, (tick, gene, n, *gene_stats), strict=True))
        for gene, gene_stats in zip(names, stats, strict=True)
    ]


class RunRecorder:
    def __init__(
        self,
        genome_snapshot_every: int,
        ticks_every: int = 1,
        events: tuple[str, ...] = (),
    ):
        if genome_snapshot_every < 1 or ticks_every < 1:
            raise ValueError("recording intervals must be at least 1")
        self.genome_snapshot_every = genome_snapshot_every
        self.ticks_every = ticks_every
        self.event_kinds = frozenset(events)
        self.ticks: list[dict] = []
        self.gene_stats: list[dict] = []
        self.genomes: list[dict] = []
        self.events: list[dict] = []
        self.behaviour: list[dict] = []
        # Founder ID -> founder's brain weights, captured once: weight drift is measured from
        # them. Founders who died on tick 0 are in sim.dead, so both lists are searched.
        self._founder_brains: dict[int, np.ndarray] | None = None
        # Flow columns accumulated since the last recorded tick row.
        self._pending = dict.fromkeys(FLOW_FIELDS, 0)
        self.predator_ticks: list[dict] = []
        self.strikes: list[dict] = []
        self._predator_pending = dict.fromkeys(PREDATOR_FLOW_FIELDS, 0)

    def observe(self, sim: Simulation, summary: TickSummary) -> None:
        """Call once after every ``sim.step()``. Reads the simulation; never changes it."""
        tick = summary.tick
        self._record_events(sim)
        hunted = sim.predator_summary is not None
        if hunted:
            self._record_predators(sim)

        # Flows (things that happened during a tick) are summed between recorded rows, so a
        # sampled ticks.csv still gives true totals. Stocks (population, food count, mean
        # energy, lineages) are a snapshot of the recorded tick itself.
        row = tick_row(summary)
        for field in FLOW_FIELDS:
            self._pending[field] += row[field]
        if tick % self.ticks_every != 0 and not sim.finished:
            return
        self.ticks.append(row | self._pending)
        self._pending = dict.fromkeys(FLOW_FIELDS, 0)
        if hunted:
            # The same rows as ticks.csv, flows summed the same way.
            self.predator_ticks.append(
                predator_tick_row(sim.predator_summary) | self._predator_pending
            )
            self._predator_pending = dict.fromkeys(PREDATOR_FLOW_FIELDS, 0)

        living = sim.organisms
        if self._founder_brains is None:
            self._founder_brains = {
                o.id: o.brain.to_vector()
                for o in [*living, *sim.dead]
                if o.parent_id is None and o.brain is not None
            }
        self.behaviour.append(behaviour_row(tick, sim.last_decision, living, self._founder_brains))
        # One (organisms, genes) table from a single attribute lookup per organism, then
        # transposed into a contiguous (genes, organisms) matrix for _stat_rows.
        names = gene_names()
        by_organism = np.array([_GENES_OF(o.genome) for o in living], dtype=np.float64)
        matrix = np.ascontiguousarray(by_organism.reshape(len(living), len(names)).T)
        self.gene_stats.extend(_stat_rows(tick, names, matrix))

        # Snapshot on the interval, and always on the final tick so the end state is kept.
        if tick % self.genome_snapshot_every == 0 or sim.finished:
            for org in living:
                genes = {f"gene_{g}": v for g, v in org.genome.as_dict().items()}
                self.genomes.append({"tick": tick, "id": org.id, **genes})

    def _record_predators(self, sim: Simulation) -> None:
        """Every tick, recorded row or not: flows into the pending totals, and every strike."""
        row = predator_tick_row(sim.predator_summary)
        for field in PREDATOR_FLOW_FIELDS:
            self._predator_pending[field] += row[field]
        for strike in sim.strikes_this_tick:
            self.strikes.append({name: getattr(strike, name) for name in STRIKE_FIELDS})

    def _record_events(self, sim: Simulation) -> None:
        if not self.event_kinds:
            return
        kept = [e for e in sim.events_this_tick if e.kind in self.event_kinds]
        for seq, event in enumerate(kept):
            row = {name: getattr(event, name) for name in _EVENT_FIELD_NAMES}
            self.events.append({"seq": seq, **row})
