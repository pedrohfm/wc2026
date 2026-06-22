"""Tests for the model+market blend (#2)."""
import numpy as np
import pandas as pd
import pytest

import wc2026 as E
from wc2026.blend import blend_linear, blend_logpool, optimize_blend_weight


def test_blends_are_valid_distributions():
    Pm = np.array([[0.5, 0.3, 0.2], [0.1, 0.2, 0.7]])
    Pk = np.array([[0.4, 0.4, 0.2], [0.2, 0.3, 0.5]])
    for f in (blend_linear, blend_logpool):
        B = f(Pm, Pk, 0.4)
        assert np.allclose(B.sum(1), 1.0)
        assert (B >= 0).all()


def test_blend_endpoints():
    Pm = np.array([[0.6, 0.3, 0.1]]); Pk = np.array([[0.2, 0.3, 0.5]])
    assert np.allclose(blend_linear(Pm, Pk, 1.0), Pm)
    assert np.allclose(blend_linear(Pm, Pk, 0.0), Pk)


def test_optimizer_beats_both_when_market_sharper():
    rng = np.random.default_rng(0); n = 4000
    true = rng.dirichlet([4, 3, 4], size=n)
    y = np.array([rng.choice(3, p=true[i]) for i in range(n)])
    def perturb(P, s):
        L = np.log(np.clip(P, 1e-9, 1)) + rng.normal(0, s, P.shape)
        e = np.exp(L); return e / e.sum(1, keepdims=True)
    Pm = perturb(true, 0.55); Pk = perturb(true, 0.30)   # market sharper
    w, llb, llm, llk = optimize_blend_weight(Pm, Pk, y)
    assert 0.0 < w < 1.0
    assert llb < min(llm, llk) + 1e-9          # blend beats both components
    assert w < 0.5                              # leans to the sharper market


def test_shin_devig_corrects_favourite_longshot_bias():
    from wc2026.blend import shin_probs
    odds = [1.5, 4.0, 7.0]                       # clear favourite + margin
    ps = shin_probs(odds)
    assert abs(sum(ps) - 1.0) < 1e-9
    assert all(0 < p < 1 for p in ps)
    imp = [1/o for o in odds]; s = sum(imp)
    prop = [p / s for p in imp]                  # proportional (multiplicative) de-vig
    assert ps[0] >= prop[0] - 1e-9              # Shin lifts the favourite
    assert ps[-1] <= prop[-1] + 1e-9           # and shaves the longshot


def test_shin_no_margin_is_proportional():
    from wc2026.blend import shin_probs
    ps = shin_probs([2.0, 2.0])                  # booksum = 1, no margin
    assert abs(ps[0] - 0.5) < 1e-6 and abs(ps[1] - 0.5) < 1e-6


def test_blend_champion_table():
    probs = pd.DataFrame({"Win": [30.0, 20.0, 10.0]}, index=["A", "B", "C"])
    odds = {"A": 3.0, "B": 5.0, "C": 8.0}
    tab, overround = E.blend_champion(probs, odds, w=0.3)
    assert abs(tab["Blend%"].sum() - 100.0) < 0.5      # renormalised over contender set
    assert isinstance(overround, float)                # sign depends on how full the book is
    assert list(tab.index) == sorted(tab.index, key=lambda t: -tab.loc[t, "Blend%"])
