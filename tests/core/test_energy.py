"""Tests for the EnergyLedger arithmetic and its check."""

import pytest

from genesis.core.energy import EnergyLedger, EnergyLedgerError


def test_expected_stock_is_initial_plus_in_minus_out():
    ledger = EnergyLedger(initial_stock=100.0, food_spawned=40.0, metabolism=10.0,
                          movement=5.0, lost_at_death=3.0)  # fmt: skip
    assert ledger.inflow == 40.0
    assert ledger.outflow == 18.0
    assert ledger.expected_stock == 122.0


def test_balanced_books_pass():
    EnergyLedger(initial_stock=100.0, metabolism=0.35).check(99.65, tick=0)


def test_rounding_noise_is_tolerated():
    # 0.1 + 0.2 != 0.3 exactly in binary; the check must not treat that as an error.
    EnergyLedger(initial_stock=0.3).check(0.1 + 0.2, tick=0)


def test_one_missing_food_item_is_caught():
    with pytest.raises(EnergyLedgerError, match="tick 7"):
        EnergyLedger(initial_stock=1000.0).check(1020.0, tick=7)


def test_tiny_real_error_is_caught():
    # Far smaller than a food item, still far larger than rounding noise.
    with pytest.raises(EnergyLedgerError):
        EnergyLedger(initial_stock=1000.0).check(1000.001, tick=0)
