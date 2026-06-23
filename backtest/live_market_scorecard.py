"""
LIVE MARKET SCORECARD — the real, current out-of-sample test
============================================================================
We have no *historical* international odds, so the market path in backtest.py
cannot be validated across history. What we DO have is this tournament: every
played 2026 fixture for which we logged a model probability AND a market price,
scored against the actual result. This is a genuine out-of-sample market test —
small now, sharper every matchday.

It consumes the latest outputs/group_matches_<date>.csv (built by
scripts/build_group_matches.py), which already joins, per fixture:
  model W/D/L (m_*), Shin-de-vigged market W/D/L (mkt_*), actual outcome, played.

It then scores, on the played-with-odds subset:
  * MODEL only
  * MARKET only (de-vigged)
  * BLEND at a grid of weights  (1-w)*model + w*market
and reports log-loss, Brier, RPS, accuracy, plus a paired bootstrap on the
model-vs-market log-loss difference so we don't over-read a few matches.

Data hygiene: rows where the market's implied favourite is the DRAW are treated
as corrupted odds (this never reflects a real book) and dropped, with a count.

    python backtest/live_market_scorecard.py
    python backtest/live_market_scorecard.py outputs/group_matches_2026-06-23.csv
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
YMAP = {"H": 0, "D": 1, "A": 2}


def _ll(P, y):
    P = np.clip(P, 1e-9, 1.0)
    return float(-np.log(P[np.arange(len(y)), y]).mean())


def _brier(P, y):
    Y = np.eye(3)[y]
    return float(((P - Y) ** 2).sum(1).mean())


def _rps(P, y):
    Y = np.eye(3)[y]
    cp, cy = np.cumsum(P, 1), np.cumsum(Y, 1)
    return float(((cp - cy) ** 2).sum(1).mean() / 2.0)


def _norm(A):
    A = np.clip(A.astype(float), 1e-9, None)
    return A / A.sum(1, keepdims=True)


def latest_group_matches():
    files = sorted(glob.glob(os.path.join(ROOT, "outputs", "group_matches_*.csv")))
    return files[-1] if files else None


def load_scored(path):
    df = pd.read_csv(path)
    have = df["mkt_home"].notna() & (df["played"] == 1) & df["actual"].isin(YMAP)
    d = df[have].copy()
    M = _norm(np.c_[d.m_home, d.m_draw, d.m_away])
    K = _norm(np.c_[d.mkt_home, d.mkt_draw, d.mkt_away])
    y = d["actual"].map(YMAP).values
    # corrupted-odds guard: a real book never makes the draw the outright favourite
    bad = (K[:, 1] > K[:, 0]) & (K[:, 1] > K[:, 2])
    return M[~bad], K[~bad], y[~bad], int(bad.sum()), d


def paired_bootstrap(M, K, y, n=10000, seed=7):
    """P(market log-loss < model log-loss) by resampling matches with replacement.
       Returns (mean delta = model_ll - market_ll, share of resamples market wins)."""
    rng = np.random.default_rng(seed)
    Pm = np.clip(M[np.arange(len(y)), y], 1e-9, 1)
    Pk = np.clip(K[np.arange(len(y)), y], 1e-9, 1)
    dm = -np.log(Pm)  # per-match model loss
    dk = -np.log(Pk)  # per-match market loss
    diff = dm - dk    # >0 => market better on that match
    idx = rng.integers(0, len(y), size=(n, len(y)))
    boot = diff[idx].mean(1)
    return float(diff.mean()), float((boot > 0).mean())


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else latest_group_matches()
    if not path:
        print("No group_matches_*.csv found. Run scripts/build_group_matches.py first.")
        return
    M, K, y, n_bad, _ = load_scored(path)
    n = len(y)
    print(f"\nLIVE MARKET SCORECARD  —  {os.path.basename(path)}")
    print(f"played fixtures with model+market: {n}"
          + (f"   (dropped {n_bad} corrupted-odds row(s): draw as favourite)" if n_bad else ""))
    if n < 1:
        print("Not enough scored fixtures yet.")
        return

    def card(name, P):
        print(f"  {name:<22} LL={_ll(P,y):.4f}  Brier={_brier(P,y):.4f}  "
              f"RPS={_rps(P,y):.4f}  Acc={ (P.argmax(1)==y).mean():.3f}")

    print("-" * 64)
    card("MODEL", M)
    card("MARKET (de-vigged)", K)
    best_w, best_ll = 0.0, _ll(M, y)
    for w in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        B = _norm((1 - w) * M + w * K)
        ll = _ll(B, y)
        card(f"BLEND w={w:.1f}", B)
        if ll < best_ll:
            best_w, best_ll = w, ll
    print("-" * 64)
    mean_delta, p_market = paired_bootstrap(M, K, y)
    better = "MARKET" if mean_delta > 0 else "MODEL"
    print(f"Best blend weight (this sample): w={best_w:.1f}  (LL={best_ll:.4f} "
          f"vs model {_ll(M,y):.4f})")
    print(f"Paired bootstrap: mean per-match LL gap (model-market) = {mean_delta:+.4f}  "
          f"-> {better} ahead; market beats model in {p_market*100:.0f}% of resamples.")
    if n < 50:
        print(f"CAUTION: n={n} is far too small for significance. Treat as directional "
              f"only; the read sharpens each matchday as daily.sh refreshes this file.")


if __name__ == "__main__":
    main()
