"""Tests for the EnergyLedger arithmetic and its check."""

import pytest

from genesis.core.energy import EnergyLedger, EnergyLedgerError


def test_expected_stock_is_initial_plus_in_minus_out():
    # Every outflow has a distinct value, so leaving any one of them out of `outflow` would
    # change the total and fail this test.
    ledger = EnergyLedger(initial_stock=100.0, food_spawned=40.0, metabolism=10.0, sensing=1.0,
                          movement=5.0, lost_at_death=3.0, reproduction_overhead=7.0)  # fmt: skip
    assert ledger.inflow == 40.0
    assert ledger.outflow == 26.0
    assert ledger.expected_stock == 114.0
    assert ledger.gross_flow == 166.0


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


def test_tolerance_scales_with_energy_flowed_not_with_stock():
    # The situation that stopped E002/E003: stock ~3500, but ~1.1 million EU had flowed through.
    quiet = EnergyLedger(initial_stock=3500.0)
    busy = EnergyLedger(initial_stock=4500.0, food_spawned=551_360.0, metabolism=552_325.0)
    assert busy.gross_flow == pytest.approx(1_108_185.0)
    assert busy.tolerance > quiet.tolerance
    # The worst drift measured after the per-tick fsum fix (~6e-9 EU) is accepted...
    busy.check(busy.expected_stock + 6e-9, tick=13_820)
    # ...but the old code's drift (3.5e-6) still isn't: the fix is exact per-tick summing,
    # not a looser tolerance.
    with pytest.raises(EnergyLedgerError):
        busy.check(busy.expected_stock + 3.5e-6, tick=13_820)


def test_smallest_real_error_is_still_caught_after_huge_flows():
    # One missed sensing payment at the minimum sense range: 1 x 0.004 EU.
    busy = EnergyLedger(initial_stock=4500.0, food_spawned=1_000_000.0, metabolism=1_000_000.0)
    with pytest.raises(EnergyLedgerError):
        busy.check(busy.expected_stock + 0.004, tick=20_000)


def test_tolerance_has_a_floor_for_tiny_runs():
    assert EnergyLedger(initial_stock=0.0).tolerance == pytest.approx(1e-6)
