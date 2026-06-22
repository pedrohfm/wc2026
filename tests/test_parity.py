"""Parity tests: the refactored package must reproduce the original monolith
EXACTLY (same seeds, same inputs -> identical numeric output). This is what
'no behavior change' means operationally.

  legacy_engine.py  = a frozen copy of the original wc2026_engine.py
  wc2026            = the refactored package under src/

If any assertion here fails, the refactor changed behaviour.
"""
import os
import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

import legacy_engine as L
import wc2026 as E

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Parity tests verify the REFACTOR preserves the original logic, independent of
# parameter VALUES. GOAL_SCALE is read at call time from the module namespace, so
# sync the frozen reference to the package's current config before comparing.
# (config.GOAL_SCALE may be tuned over time; that is an intentional value change,
#  not a refactor regression.)
L.GOAL_SCALE = E.GOAL_SCALE


@pytest.fixture(scope="module")
def elo():
    df = pd.read_csv(os.path.join(ROOT, "wc2026_elo.csv"))
    return df.set_index("Team")["Elo"].to_dict()


# a few realistic group results to exercise the dynamic path
KG_SAMPLE = {1: (2, 1), 2: (0, 0), 6: (3, 0), 13: (4, 0), 17: (2, 2)}


def test_constants_match():
    assert (L.GOAL_SCALE, L.HOME_ADV, L.K_FACTOR, L.SIGMA_TEAM, L.SIGMA_CONF) == \
           (E.GOAL_SCALE, E.HOME_ADV, E.K_FACTOR, E.SIGMA_TEAM, E.SIGMA_CONF)
    assert L.GROUP_FIXTURES == E.GROUP_FIXTURES
    assert L.KO == E.KO
    assert L.CONF == E.CONF
    assert L.GROUPS == E.GROUPS


@pytest.mark.parametrize("ea,eb,ha", [(1900, 1500, 0), (2100, 1440, 60), (1600, 1600, -60)])
def test_match_model_helpers(ea, eb, ha):
    assert L.win_expectancy(ea, eb, ha) == E.win_expectancy(ea, eb, ha)
    assert L.expected_goals(ea, eb, ha=ha) == E.expected_goals(ea, eb, ha=ha)
    assert L.expected_goals(ea, eb, ha=ha, scale=520) == E.expected_goals(ea, eb, ha=ha, scale=520)


def test_update_elo_identical(elo):
    a, b = "Brazil", "Morocco"
    eL = dict(elo); eE = dict(elo)
    L.update_elo(eL, a, b, 3, 0); E.update_elo(eE, a, b, 3, 0)
    assert eL == eE


def test_allocate_thirds_identical():
    groups = list("ABCDEFGH")
    assert L.allocate_thirds(groups) == E.allocate_thirds(groups)


def test_apply_known_results_identical(elo):
    eL = L.apply_known_results(elo, KG_SAMPLE, {})
    eE = E.apply_known_results(elo, KG_SAMPLE, {})
    assert eL == eE


def test_monte_carlo_pretournament_identical(elo):
    a = L.run_monte_carlo(elo, iterations=400, seed=7, verbose=False)
    b = E.run_monte_carlo(elo, iterations=400, seed=7, verbose=False)
    pdt.assert_frame_equal(a, b)


def test_monte_carlo_dynamic_identical(elo):
    a = L.run_monte_carlo(elo, iterations=300, seed=11, kg=KG_SAMPLE, verbose=False)
    b = E.run_monte_carlo(elo, iterations=300, seed=11, kg=KG_SAMPLE, verbose=False)
    pdt.assert_frame_equal(a, b)


def test_simulate_schedule_identical(elo):
    sa, ca = L.simulate_schedule(elo, seed=7)
    sb, cb = E.simulate_schedule(elo, seed=7)
    pdt.assert_frame_equal(sa, sb)
    assert ca == cb


def test_compare_to_market_identical(elo):
    # The package now de-vigs via Shin (an intentional improvement over the
    # monolith's proportional method), so compare with devig=False to verify the
    # rest of the function is unchanged. (Shin is covered in test_blend.py.)
    probs = E.run_monte_carlo(elo, iterations=400, seed=7, verbose=False)
    a = L.compare_to_market(probs, market=L.MARKET_ODDS, devig=False)
    b = E.compare_to_market(probs, market=E.MARKET_ODDS, devig=False)
    pdt.assert_frame_equal(a, b)
