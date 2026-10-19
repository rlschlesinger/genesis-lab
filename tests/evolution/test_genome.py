"""Tests for the genome: the gene list, founders' genome, and expression to traits."""

import dataclasses
from pathlib import Path

import pytest

from genesis.core.config import GenomeConfig, load_config
from genesis.core.organism import Traits
from genesis.evolution.genome import GENES, Genome, express, gene_names

DEFAULT_CONFIG = Path(__file__).parents[2] / "configs" / "default.yaml"


@pytest.fixture
def genome_config() -> GenomeConfig:
    return load_config(DEFAULT_CONFIG).genome


def test_gene_list_genome_and_config_agree():
    # One list of genes, three places that must match exactly, in the same order.
    assert list(GENES) == gene_names() == list(GenomeConfig.model_fields)


def test_every_expressed_gene_becomes_a_trait_and_only_those():
    expressed = [name for name, info in GENES.items() if info.expressed]
    assert expressed == [f.name for f in dataclasses.fields(Traits)]


def test_founder_genome_uses_initial_values(genome_config):
    genome = Genome.from_config(genome_config)
    for name in gene_names():
        assert getattr(genome, name) == getattr(genome_config, name).initial


def test_expression_copies_expressed_genes_exactly(genome_config):
    genome = Genome.from_config(genome_config)
    traits = express(genome)
    for field in dataclasses.fields(Traits):
        # Exact equality, not approx: any rounding would change Milestone 1 results.
        assert getattr(traits, field.name) == getattr(genome, field.name)


def test_neutral_marker_is_inherited_but_not_expressed(genome_config):
    genome = Genome.from_config(genome_config)
    assert genome.neutral_marker == 0.5
    assert not hasattr(express(genome), "neutral_marker")
    assert GENES["neutral_marker"].expressed is False


def test_genome_is_immutable(genome_config):
    genome = Genome.from_config(genome_config)
    with pytest.raises(dataclasses.FrozenInstanceError):
        genome.speed = 9.0


def test_every_gene_has_a_unit_and_description():
    for name, info in GENES.items():
        assert info.unit and info.description, name
