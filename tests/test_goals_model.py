"""Tests for the Dixon-Coles goals model and its integration into the Monte
Carlo. (The legacy/None path is covered by test_parity.py; here we test the new
opt-in path.)"""
import os
import numpy as np
import pandas as pd
import pytest

import wc2026 as E
from wc2026.goals_model import GoalsModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def elo():
    df = pd.read_csv(os.path.join(ROOT, "wc2026_elo.csv"))
    return df.set_index("Team")["Elo"].to_dict()


def test_wdl_sums_to_one():
    gm = GoalsModel(mu=0.30, gamma=0.8, rho=-0.1, home_elo=60)
    for ea, eb in [(2000, 1500), (1500, 1500), (1440, 2171)]:
        p = gm.wdl(ea, eb)
        assert abs(sum(p) - 1.0) < 1e-9
        assert all(0 <= x <= 1 for x in p)


def test_stronger_team_more_likely_to_win():
    gm = GoalsModel()
    pH_strong, _, _ = gm.wdl(2000, 1500)
    pH_even, _, _ = gm.wdl(1500, 1500)
    assert pH_strong > pH_even


def test_negative_rho_increases_draws():
    even = (1500, 1500)
    pD_indep = GoalsModel(rho=0.0).wdl(*even)[1]
    pD_dc = GoalsModel(rho=-0.12).wdl(*even)[1]
    assert pD_dc > pD_indep


def test_monte_carlo_with_goals_model_runs(elo):
    gm = GoalsModel(mu=0.32, gamma=0.6, rho=-0.10, home_elo=98)
    df = E.run_monte_carlo(elo, iterations=300, seed=7, goals_model=gm, verbose=False)
    assert abs(df["Win"].sum() - 100.0) < 1.0          # probabilities, summing to ~100%
    assert len(df) == 48 and df["Win"].notna().all()
    assert df["Win"].iloc[0] > 0


def test_goals_model_path_is_reproducible(elo):
    gm = GoalsModel(mu=0.32, gamma=0.6, rho=-0.10, home_elo=98)
    a = E.run_monte_carlo(elo, iterations=300, seed=7, goals_model=gm, verbose=False)
    b = E.run_monte_carlo(elo, iterations=300, seed=7, goals_model=gm, verbose=False)
    pd.testing.assert_frame_equal(a, b)


def test_save_load_roundtrip(tmp_path):
    gm = GoalsModel(mu=0.31, gamma=0.77, rho=-0.08, home_elo=64)
    p = tmp_path / "g.json"; gm.save(p)
    gm2 = GoalsModel.load(p)
    assert (gm2.mu, gm2.gamma, gm2.rho, gm2.home_elo) == (gm.mu, gm.gamma, gm.rho, gm.home_elo)
