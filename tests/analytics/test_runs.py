"""Tests for run output: files, reproducibility, status records, metrics rows."""

import csv
import json
from pathlib import Path

import pytest

from genesis.analytics.metrics import ORGANISM_FIELDS, TICK_FIELDS, organism_rows
from genesis.analytics.runs import VOLATILE_FIELDS, execute_run
from genesis.core.config import SimulationConfig, load_config, with_overrides
from genesis.core.energy import EnergyLedgerError
from genesis.core.simulation import Simulation

DEFAULT_CONFIG = Path(__file__).parents[2] / "configs" / "default.yaml"


@pytest.fixture
def config():
    return with_overrides(load_config(DEFAULT_CONFIG), max_ticks=300)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


# --- Output files -------------------------------------------------------------------------


def test_run_writes_three_files_with_expected_columns(config, tmp_path):
    result = execute_run(config, tmp_path)
    ticks = read_csv(tmp_path / "ticks.csv")
    organisms = read_csv(tmp_path / "organisms.csv")
    assert list(ticks[0]) == TICK_FIELDS
    assert list(organisms[0]) == ORGANISM_FIELDS
    assert len(ticks) == result.ticks_run == 300
    meta = json.loads((tmp_path / "run.json").read_text())
    assert len(organisms) == meta["organisms_ever"]


def test_run_json_records_provenance(config, tmp_path):
    execute_run(config, tmp_path, experiment_id="exp-test")
    meta = json.loads((tmp_path / "run.json").read_text())
    assert meta["status"] == "completed"
    assert meta["seed"] == config.run.seed
    assert meta["experiment_id"] == "exp-test"
    assert meta["config"]["run"]["max_ticks"] == 300
    assert set(meta["git"]) == {"commit", "dirty"}
    assert meta["environment"]["packages"]["numpy"]
    assert len(meta["final_state_digest"]) == 64  # SHA-256 in hex


def test_csv_values_round_trip_exactly(config, tmp_path):
    # Floats are written in shortest exact form: reading them back gives the same numbers.
    execute_run(config, tmp_path)
    sim = Simulation(config)
    sim.run()
    expected = organism_rows(sim)
    written = read_csv(tmp_path / "organisms.csv")
    assert [float(r["final_energy"]) for r in written] == [r["final_energy"] for r in expected]


# --- Reproducibility ----------------------------------------------------------------------


def test_identical_runs_give_byte_identical_results(config, tmp_path):
    execute_run(config, tmp_path / "a")
    execute_run(config, tmp_path / "b")
    names = sorted(p.name for p in (tmp_path / "a").glob("*.csv"))
    assert names == ["gene_stats.csv", "genomes.csv", "mutations.csv", "organisms.csv", "ticks.csv"]
    for name in names:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    meta_a = json.loads((tmp_path / "a" / "run.json").read_text())
    meta_b = json.loads((tmp_path / "b" / "run.json").read_text())
    for key in VOLATILE_FIELDS:
        meta_a.pop(key), meta_b.pop(key)
    assert meta_a == meta_b


def test_different_seeds_give_different_results(config, tmp_path):
    execute_run(config, tmp_path / "a")
    execute_run(with_overrides(config, seed=config.run.seed + 1), tmp_path / "b")
    assert (tmp_path / "a" / "ticks.csv").read_bytes() != (
        tmp_path / "b" / "ticks.csv"
    ).read_bytes()


# --- Safety and failure records -----------------------------------------------------------


def test_refuses_to_overwrite_an_earlier_run(config, tmp_path):
    execute_run(config, tmp_path)
    with pytest.raises(FileExistsError):
        execute_run(config, tmp_path)
    execute_run(config, tmp_path, overwrite=True)  # explicit opt-in works


def test_failed_run_leaves_an_honest_record(config, tmp_path, monkeypatch):
    original_step = Simulation.step

    def failing_step(self):
        if self.tick == 50:
            raise EnergyLedgerError("simulated accounting failure")
        return original_step(self)

    monkeypatch.setattr(Simulation, "step", failing_step)
    with pytest.raises(EnergyLedgerError):
        execute_run(config, tmp_path)
    meta = json.loads((tmp_path / "run.json").read_text())
    assert meta["status"] == "failed"
    assert meta["failed_at_tick"] == 50
    assert "simulated accounting failure" in meta["error"]
    assert not (tmp_path / "ticks.csv").exists()  # no partial results pretending to be complete


def test_no_temporary_files_left_behind(config, tmp_path):
    execute_run(config, tmp_path)
    assert not list(tmp_path.glob("*.tmp"))


# --- Metrics rows -------------------------------------------------------------------------


def test_organism_rows_cover_everyone_in_id_order(config):
    sim = Simulation(config)
    sim.run()
    rows = organism_rows(sim)
    assert [r["id"] for r in rows] == sorted(o.id for o in [*sim.organisms, *sim.dead])
    dead_row = next(r for r in rows if not r["alive"])
    assert dead_row["death_cause"] in {"starvation", "old_age"}


def test_mutations_csv_and_gene_columns(tmp_path):
    raw = load_config(DEFAULT_CONFIG).model_dump()
    raw["run"]["max_ticks"] = 600
    raw["mutation"].update(enabled=True, rate=0.3, size=0.1)
    execute_run(SimulationConfig.model_validate(raw), tmp_path)
    mutations = read_csv(tmp_path / "mutations.csv")
    organisms = {int(r["id"]): r for r in read_csv(tmp_path / "organisms.csv")}
    assert list(mutations[0]) == ["tick", "parent_id", "child_id", "gene", "before", "after"]
    # A genome only changes at birth, so each mutation's "after" is the child's gene value.
    for m in mutations:
        assert float(organisms[int(m["child_id"])][f"gene_{m['gene']}"]) == float(m["after"])
    meta = json.loads((tmp_path / "run.json").read_text())
    assert meta["mutations"] == len(mutations)


def test_mutations_csv_is_header_only_when_mutation_is_off(config, tmp_path):
    execute_run(config, tmp_path)
    assert (tmp_path / "mutations.csv").read_text() == "tick,parent_id,child_id,gene,before,after\n"
