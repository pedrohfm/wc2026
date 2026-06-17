"""
Feeding orthogonal features into the engine.

The backtest's verdict (see docs/METHODOLOGY.md §8): tweaking the goals mapping
with match-importance does NOT improve out-of-sample accuracy. The one feature
that can add genuinely new signal is SQUAD MARKET VALUE, because it carries
information Elo doesn't (a rising squad whose results haven't caught up yet).

The engine already accepts an arbitrary Elo dict, so the clean way to inject a
feature is to convert it into an Elo nudge and add it before forecasting. The
nudge below is deliberately the ORTHOGONAL part of squad value — the component
left after removing whatever value already correlates with Elo — so you don't
double-count strength.

    import wc2026 as E
    elo = E.load_elo()
    elo2 = E.elo_nudge_from_values(elo, squad_value_map, beta=20)
    probs = E.run_monte_carlo(elo2, goals_model=gm)

beta = Elo points per 1 SD of orthogonal squad value. It is UNVALIDATED until you
fit it: build the mv_diff feature (backtest/feature_importance.py), find the Elo-
equivalent of its fitted coefficient, and use that. Treat the default as a
placeholder, not a calibrated value.
"""
from __future__ import annotations
import numpy as np


def elo_nudge_from_values(elo, value_map, beta=20.0, min_teams=5):
    """Return a NEW elo dict with a zero-meaned, Elo-orthogonal squad-value nudge
       added. Teams missing from value_map are left unchanged."""
    teams = [t for t in elo if t in value_map and value_map[t] and value_map[t] > 0]
    if len(teams) < min_teams:
        return dict(elo)
    e = np.array([float(elo[t]) for t in teams])
    v = np.log(np.array([float(value_map[t]) for t in teams]))
    # residual of log(value) after removing its linear dependence on Elo
    A = np.vstack([np.ones_like(e), e]).T
    coef, *_ = np.linalg.lstsq(A, v, rcond=None)
    resid = v - A @ coef
    sd = resid.std()
    if sd < 1e-9:
        return dict(elo)
    z = (resid - resid.mean()) / sd
    out = dict(elo)
    for t, zz in zip(teams, z):
        out[t] = elo[t] + beta * float(zz)
    return out
