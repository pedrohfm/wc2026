"""
Dixon-Coles goals model (fit by MLE) — the principled replacement for the
ad-hoc Elo->goals map in match_model.expected_goals().

WHY THIS EXISTS
---------------
The legacy map sets two goal rates from one Elo gap via
    lambda_home = base * sqrt(w/(1-w)),   w = logistic(d / GOAL_SCALE)
with base=1.35 and GOAL_SCALE=600 chosen by taste, and then samples INDEPENDENT
Poisson goals. That has two flaws the backtest quantified: the constants are
guessed, and independent Poisson under-predicts draws.

This module fixes both. It keeps ONE strength rating per team (Elo) — the right
choice for data-sparse international football — but:

  * the Elo gap maps to goal rates through a log-linear form whose parameters
    are FIT BY MAXIMUM LIKELIHOOD, not guessed:
        log lambda_home = mu + gamma * d_eff / 400
        log lambda_away = mu - gamma * d_eff / 400
        d_eff = (elo_home - elo_away) + home_elo * home_flag
  * the scoreline distribution carries the Dixon-Coles (1997) low-score
    correction tau(rho), which restores the right draw mass and the mild
    negative correlation between the two teams' goals.

Parameters (mu, gamma, home_elo, rho) are estimated on historical matches by
backtest/fit_goals_model.py and saved to params/goals_params.json. Equivalences
to the legacy knobs (so the upgrade is interpretable, not a black box):
    mu    ~ ln(base)         (base=1.35 -> mu~0.300)
    gamma ~ 400*ln(10)/(2*GOAL_SCALE)   (GOAL_SCALE=600 -> gamma~0.767)
    rho   : new; 0 reproduces independent Poisson (legacy had no draw term)
    home_elo : replaces the guessed HOME_ADV=60 with a fitted value

Dependency-light: numpy only (+ scipy for the MLE if available).
"""
from __future__ import annotations
import json
import math
from dataclasses import dataclass, asdict

import numpy as np

# legacy-equivalent defaults (so an unfitted model ~ reproduces old behaviour)
DEFAULT_MU = math.log(1.35)
DEFAULT_GAMMA = 400.0 * math.log(10.0) / (2.0 * 600.0)   # ~0.767
DEFAULT_HOME_ELO = 60.0
DEFAULT_RHO = 0.0


def _pois_pmf(lam, kmax):
    k = np.arange(kmax + 1)
    logp = k * math.log(lam) - lam - np.array([math.lgamma(i + 1) for i in k])
    return np.exp(logp)


def _tau(la, lb, rho, kmax):
    t = np.ones((kmax + 1, kmax + 1))
    t[0, 0] = 1.0 - la * lb * rho
    t[0, 1] = 1.0 + la * rho
    t[1, 0] = 1.0 + lb * rho
    t[1, 1] = 1.0 - rho
    return t


@dataclass
class GoalsModel:
    mu: float = DEFAULT_MU
    gamma: float = DEFAULT_GAMMA
    rho: float = DEFAULT_RHO
    home_elo: float = DEFAULT_HOME_ELO
    kmax: int = 8
    lo: float = 0.15
    hi: float = 4.5

    # --- rates ---------------------------------------------------------------
    def lambdas(self, elo_a, elo_b):
        """Goal rates for (home=a, away=b). Any home advantage must already be
        folded into elo_a/elo_b by the caller (the simulator does this through
        _ha, exactly as the legacy path does)."""
        d = elo_a - elo_b
        la = math.exp(self.mu + self.gamma * d / 400.0)
        lb = math.exp(self.mu - self.gamma * d / 400.0)
        return min(max(la, self.lo), self.hi), min(max(lb, self.lo), self.hi)

    # --- scoreline distribution ---------------------------------------------
    def grid(self, elo_a, elo_b):
        la, lb = self.lambdas(elo_a, elo_b)
        M = np.outer(_pois_pmf(la, self.kmax), _pois_pmf(lb, self.kmax))
        M *= _tau(la, lb, self.rho, self.kmax)
        M = np.clip(M, 1e-15, None)
        return M / M.sum()

    def sample(self, elo_a, elo_b, rng):
        M = self.grid(elo_a, elo_b)
        idx = rng.choice(M.size, p=M.ravel())
        return tuple(int(x) for x in divmod(idx, self.kmax + 1))

    def wdl(self, elo_a, elo_b):
        M = self.grid(elo_a, elo_b)
        pH = np.tril(M, -1).sum(); pD = np.trace(M); pA = np.triu(M, 1).sum()
        s = pH + pD + pA
        return pH / s, pD / s, pA / s

    # --- persistence ---------------------------------------------------------
    def save(self, path):
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path):
        with open(path) as f:
            return cls(**json.load(f))


# ----------------------------------------------------------------------------
# MAXIMUM-LIKELIHOOD FIT  (the Dixon-Coles likelihood, specialised to one Elo
# rating per team + a fitted home effect)
# ----------------------------------------------------------------------------
def negloglik(params, d, home_flag, hg, ag, kmax=8):
    mu, gamma, home_elo, rho = params
    d_eff = d + home_elo * home_flag
    la = np.exp(mu + gamma * d_eff / 400.0)
    lb = np.exp(mu - gamma * d_eff / 400.0)
    la = np.clip(la, 0.05, 6.0); lb = np.clip(lb, 0.05, 6.0)
    ll = (hg * np.log(la) - la - _lgamma_arr(hg)
          + ag * np.log(lb) - lb - _lgamma_arr(ag))
    # Dixon-Coles low-score correction (added in log space, 0 elsewhere)
    tau = np.ones_like(la)
    m00 = (hg == 0) & (ag == 0); tau[m00] = 1.0 - la[m00] * lb[m00] * rho
    m01 = (hg == 0) & (ag == 1); tau[m01] = 1.0 + la[m01] * rho
    m10 = (hg == 1) & (ag == 0); tau[m10] = 1.0 + lb[m10] * rho
    m11 = (hg == 1) & (ag == 1); tau[m11] = 1.0 - rho
    ll = ll + np.log(np.clip(tau, 1e-9, None))
    return -np.sum(ll)


_LGAMMA = np.vectorize(lambda k: math.lgamma(k + 1))
def _lgamma_arr(k):
    return _LGAMMA(k)


def fit(d, home_flag, hg, ag, x0=None):
    """Fit (mu, gamma, home_elo, rho) by MLE. Returns a GoalsModel.
       d: elo_home - elo_away (pre-match);  home_flag: 1 if non-neutral home."""
    d = np.asarray(d, float); home_flag = np.asarray(home_flag, float)
    hg = np.asarray(hg, int); ag = np.asarray(ag, int)
    if x0 is None:
        x0 = np.array([DEFAULT_MU, DEFAULT_GAMMA, DEFAULT_HOME_ELO, 0.0])
    bounds = [(-1.0, 1.5), (0.0, 3.0), (-150.0, 300.0), (-0.30, 0.30)]
    try:
        from scipy.optimize import minimize
        r = minimize(negloglik, x0, args=(d, home_flag, hg, ag),
                     method="L-BFGS-B", bounds=bounds)
        p = r.x
    except Exception:
        from scipy.optimize import minimize  # noqa
        p = x0  # if scipy truly unavailable the caller is warned elsewhere
    return GoalsModel(mu=float(p[0]), gamma=float(p[1]), rho=float(p[3]),
                      home_elo=float(p[2]))
