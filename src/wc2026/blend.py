"""
Model + market blending.

The backtest shows the market out-predicts the Elo model out-of-sample (it
prices information the model can't see). The optimal use of two imperfect
forecasters is not to pick one but to COMBINE them: a weighted blend of the
model and the de-vigged market typically beats BOTH, because their errors are
partly independent. This module provides the blend and an out-of-sample
optimiser for the weight.

Two pooling rules:
  * linear  : w*model + (1-w)*market         (arithmetic; robust default)
  * logpool : model^w * market^(1-w)         (log-opinion pool; sharper, the
              standard choice when combining well-calibrated probabilities)

The weight w in [0,1] is the WEIGHT ON THE MODEL. w=0 trusts the market fully,
w=1 ignores it. It should be fit by out-of-sample log-loss on historical
matches where you have odds (see optimize_blend_weight); until you have those,
treat any default as a prior, not a calibrated value.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

EPS = 1e-12


def _norm(P):
    P = np.clip(np.asarray(P, float), EPS, None)
    return P / P.sum(axis=1, keepdims=True)


def blend_linear(P_model, P_market, w):
    return _norm(w * np.asarray(P_model, float) + (1.0 - w) * np.asarray(P_market, float))


def blend_logpool(P_model, P_market, w):
    Pm = np.clip(np.asarray(P_model, float), EPS, None)
    Pk = np.clip(np.asarray(P_market, float), EPS, None)
    return _norm(np.exp(w * np.log(Pm) + (1.0 - w) * np.log(Pk)))


def _logloss(P, y):
    P = np.clip(P, EPS, 1.0)
    return float(-np.mean(np.log(P[np.arange(len(y)), y])))


def optimize_blend_weight(P_model, P_market, y, kind="linear", grid=None):
    """Out-of-sample optimal weight on the MODEL. Returns
       (w_star, blended_logloss, model_logloss, market_logloss)."""
    grid = np.linspace(0.0, 1.0, 101) if grid is None else np.asarray(grid)
    f = blend_linear if kind == "linear" else blend_logpool
    lls = [_logloss(f(P_model, P_market, w), y) for w in grid]
    i = int(np.argmin(lls))
    return float(grid[i]), float(lls[i]), _logloss(_norm(P_model), y), _logloss(_norm(P_market), y)


def shin_probs(odds):
    """Shin (1992) margin removal for a single book. Given decimal odds, return
       probabilities summing to 1 that account for a proportion z of
       insider/informed money — which shaves the favourite-longshot bias that the
       naive proportional method leaves in. Solved for z by bisection.
       odds: list of decimal odds. Returns list of probabilities."""
    import math
    pi = [1.0 / o for o in odds]
    B = sum(pi)
    if B <= 1.0:
        return [p / B for p in pi] if B else pi          # no margin -> proportional
    def P(z):
        return [(math.sqrt(z * z + 4 * (1 - z) * p * p / B) - z) / (2 * (1 - z)) for p in pi]
    lo, hi = 0.0, 0.999
    for _ in range(80):                                   # sum(P) decreases in z; solve sum=1
        mid = (lo + hi) / 2
        if sum(P(mid)) > 1.0: lo = mid
        else: hi = mid
    p = P((lo + hi) / 2); s = sum(p)
    return [x / s for x in p]


def shin_devig(odds):
    """Shin margin removal for {team: decimal_odds} -> {team: probability}."""
    teams = [t for t, o in odds.items() if o and o > 1]
    if not teams:
        return {}
    ps = shin_probs([odds[t] for t in teams])
    return {t: ps[i] for i, t in enumerate(teams)}


def devig(odds, method="shin"):
    """Decimal champion odds {team: o} -> (de-vigged probabilities, overround%).
       method='shin' (default, rigorous) or 'proportional' (multiplicative)."""
    imp = {t: 1.0 / o for t, o in odds.items() if o and o > 1}
    s = sum(imp.values()); over = (s - 1.0) * 100.0
    if method == "shin":
        return shin_devig(odds), over
    return {t: p / s for t, p in imp.items()}, over


def blend_champion(model_df, market_odds, w=0.35, col="Win", kind="linear"):
    """Blend the model's outright champion probabilities with the de-vigged
       market over the contender set the market covers. Renormalises over that
       set so model and market are compared like-for-like. Returns a table."""
    mk, overround = devig(market_odds)
    teams = list(mk)
    pm = np.array([model_df.loc[t, col] / 100.0 if t in model_df.index else 0.0 for t in teams])
    pm = pm / pm.sum() if pm.sum() > 0 else pm          # renormalise model over contender set
    pk = np.array([mk[t] for t in teams])
    if kind == "linear":
        pb = w * pm + (1 - w) * pk
    else:
        pb = np.power(np.clip(pm, EPS, None), w) * np.power(np.clip(pk, EPS, None), 1 - w)
    pb = pb / pb.sum()
    out = pd.DataFrame({"Model%": (pm * 100).round(1), "Market%": (pk * 100).round(1),
                        "Blend%": (pb * 100).round(1)}, index=teams)
    out.index.name = "Team"
    return out.sort_values("Blend%", ascending=False), overround
