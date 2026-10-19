"""Tests for mutation: reflection, bounds, statistics, freezing, determinism, no bias."""

from pathlib import Path

import numpy as np
import pytest

from genesis.core.config import GenomeConfig, MutationConfig, load_config
from genesis.evolution.genome import Genome, gene_names
from genesis.evolution.mutation import mutate, reflect

DEFAULT_CONFIG = Path(__file__).parents[2] / "configs" / "default.yaml"


@pytest.fixture
def genome_config() -> GenomeConfig:
    return load_config(DEFAULT_CONFIG).genome


def mutation(enabled=True, rate=0.1, size=0.05) -> MutationConfig:
    return MutationConfig(enabled=enabled, rate=rate, size=size)


def founders(genome_config) -> Genome:
    return Genome.from_config(genome_config)


def frozen(genome_config, *names) -> GenomeConfig:
    """The same genome config with the named genes made immutable."""
    raw = genome_config.model_dump()
    for name in names:
        raw[name]["mutable"] = False
    return GenomeConfig.model_validate(raw)


# --- reflect ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2.0, 2.0),  # inside: unchanged
        (0.0, 0.0),  # exactly on a bound: unchanged
        (4.0, 4.0),
        (4.3, 3.7),  # small overshoot above
        (-0.5, 0.5),  # small overshoot below
        (8.5, 0.5),  # overshoot by more than the whole range: bounces twice
        (-4.5, 3.5),
    ],
)
def test_reflect(value, expected):
    assert reflect(value, 0.0, 4.0) == pytest.approx(expected)


def test_reflect_works_with_offset_bounds():
    assert reflect(260.0, 55.0, 250.0) == pytest.approx(240.0)


# --- Switching off ------------------------------------------------------------------------


def test_disabled_mutation_returns_the_parent_genome_and_draws_nothing(genome_config):
    rng = np.random.default_rng(0)
    state_before = rng.bit_generator.state
    parent = founders(genome_config)
    child, changes = mutate(parent, genome_config, mutation(enabled=False), rng)
    assert child is parent  # the very same object: nothing was copied or changed
    assert changes == []
    assert rng.bit_generator.state == state_before  # stream untouched


def test_rate_zero_never_mutates(genome_config):
    rng = np.random.default_rng(0)
    parent = founders(genome_config)
    for _ in range(1000):
        child, changes = mutate(parent, genome_config, mutation(rate=0.0), rng)
        assert child == parent and changes == []


def test_rate_one_mutates_every_mutable_gene(genome_config):
    child, changes = mutate(
        founders(genome_config), genome_config, mutation(rate=1.0), np.random.default_rng(0)
    )
    assert [c.gene for c in changes] == gene_names()


def test_frozen_gene_never_changes(genome_config):
    config = frozen(genome_config, "speed", "neutral_marker")
    rng = np.random.default_rng(0)
    parent = founders(config)
    for _ in range(2000):
        child, changes = mutate(parent, config, mutation(rate=1.0, size=0.3), rng)
        assert child.speed == parent.speed
        assert child.neutral_marker == parent.neutral_marker
        assert {c.gene for c in changes}.isdisjoint({"speed", "neutral_marker"})


# --- Correctness of each mutation ---------------------------------------------------------


def test_parent_genome_is_never_modified(genome_config):
    parent = founders(genome_config)
    snapshot = parent.as_dict()
    mutate(parent, genome_config, mutation(rate=1.0), np.random.default_rng(0))
    assert parent.as_dict() == snapshot


def test_recorded_changes_explain_the_child_exactly(genome_config):
    rng = np.random.default_rng(3)
    parent = founders(genome_config)
    for _ in range(500):
        child, changes = mutate(parent, genome_config, mutation(rate=0.5, size=0.2), rng)
        expected = parent.as_dict() | {c.gene: c.after for c in changes}
        assert child.as_dict() == expected
        assert all(c.before == getattr(parent, c.gene) for c in changes)
        parent = child  # walk down a lineage


def test_mutations_always_stay_in_bounds(genome_config):
    # Huge mutations (size 1.0 = a standard deviation as wide as the whole range), many times.
    rng = np.random.default_rng(1)
    genome = founders(genome_config)
    for _ in range(5000):
        genome, _ = mutate(genome, genome_config, mutation(rate=1.0, size=1.0), rng)
        for name in gene_names():
            bounds = getattr(genome_config, name)
            assert bounds.min <= getattr(genome, name) <= bounds.max


# --- Statistics ---------------------------------------------------------------------------


def test_fraction_of_genes_mutated_matches_rate(genome_config):
    rng = np.random.default_rng(2)
    parent, n = founders(genome_config), 5000
    hits = sum(len(mutate(parent, genome_config, mutation(rate=0.1), rng)[1]) for _ in range(n))
    # 5000 births x 6 genes x 0.1 = 3000 expected; sd ~ 52, so +/- 250 is ~5 sd.
    assert abs(hits - 3000) < 250


def test_step_size_matches_setting_and_has_no_direction(genome_config):
    # Away from the bounds, steps are normal with sd = size * range and mean 0.
    rng = np.random.default_rng(4)
    parent = founders(genome_config)  # speed starts at 1.5 in [0.25, 4.0]
    deltas = []
    for _ in range(20_000):
        _, changes = mutate(parent, genome_config, mutation(rate=1.0, size=0.02), rng)
        deltas += [c.delta for c in changes if c.gene == "speed"]
    expected_sd = 0.02 * (4.0 - 0.25)
    assert np.std(deltas) == pytest.approx(expected_sd, rel=0.03)
    assert abs(np.mean(deltas)) < 0.002  # no built-in direction


def test_reflection_does_not_pile_values_up_at_the_bounds(genome_config):
    # Start 50,000 neutral-marker values spread evenly over [0, 1], mutate each once with large
    # steps. Under reflection they stay evenly spread: the 2% of the range next to each bound
    # holds ~2% of values. Clamping would push ~16% of them exactly onto the bounds.
    rng = np.random.default_rng(5)
    starts = rng.uniform(0.0, 1.0, size=50_000)
    parent = founders(genome_config)
    values = []
    for start in starts:
        genome = Genome(**(parent.as_dict() | {"neutral_marker": float(start)}))
        child, _ = mutate(genome, genome_config, mutation(rate=1.0, size=0.2), rng)
        values.append(child.neutral_marker)
    values = np.array(values)
    assert not np.any((values == 0.0) | (values == 1.0))
    assert np.mean(values < 0.02) == pytest.approx(0.02, abs=0.004)
    assert np.mean(values > 0.98) == pytest.approx(0.02, abs=0.004)


# --- Determinism --------------------------------------------------------------------------


def test_same_seed_same_mutations(genome_config):
    a = mutate(founders(genome_config), genome_config, mutation(), np.random.default_rng(9))
    b = mutate(founders(genome_config), genome_config, mutation(), np.random.default_rng(9))
    assert a == b


def test_number_of_draws_does_not_depend_on_outcomes(genome_config):
    # Different parents, frozen genes or not: the stream advances identically per birth.
    rng_a, rng_b = np.random.default_rng(7), np.random.default_rng(7)
    mutate(founders(genome_config), genome_config, mutation(rate=0.9), rng_a)
    mutate(founders(genome_config), frozen(genome_config, *gene_names()), mutation(rate=0.9), rng_b)
    assert rng_a.bit_generator.state == rng_b.bit_generator.state
