"""
Calibrate the tournament rating-uncertainty (sigma_team / sigma_conf) so the
model's CHAMPION distribution is as wide as the market's.

WHY THIS, NOT A MATCH-DATA ESTIMATE
-----------------------------------
sigma is a TOURNAMENT-level parameter: it controls how much probability spreads
from favourites to the field once you allow each team's true strength to differ
from its Elo (drawn once per simulated tournament). Match-level data barely
identifies it (the match model is already well-calibrated at sigma=0), and a
random-effects estimate undershoots known truth on synthetic. So we calibrate it
against the best external reference for tournament dispersion we have: the
de-vigged outright MARKET. We pick the sigma that minimises the cross-entropy
between the model's champion probabilities and the market's, over the contender
set the market covers.

This makes the standalone model's SPREAD market-consistent (taming the known Elo
over-concentration) WITHOUT touching the rankings. It is anchored to the market,
not to independent ground truth — so it is an alternative to, not a stack on top
of, the model+market blend. Use one or the other and say which.

Saves params/sigma_params.json (read automatically by the forecast pipeline).
Run:  python calibrate_sigma.py
"""
import os
import sys
import json
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
import wc2026 as E

OUT = os.path.join(ROOT, "params", "sigma_params.json")
ITERS = 1500
GRID = [0, 40, 80, 120]                    # sigma_team; sigma_conf tied at 0.7x


def main():
    elo = E.load_elo(os.path.join(ROOT, "wc2026_elo.csv"))
    gm = None
    p = os.path.join(ROOT, "params", "goals_params.json")
    if os.path.exists(p):
        gm = E.GoalsModel.load(p)
    odds = E.load_champion_odds(os.path.join(ROOT, "data", "odds_champion.csv"))
    if not odds:
        print("  no data/odds_champion.csv -> cannot calibrate sigma to market. "
              "Add outright odds (see DATA_REQUIRED.md)."); return 1
    mk, _ = E.devig_odds(odds)
    teams = list(mk)
    m = np.array([mk[t] for t in teams])

    print(f"  calibrating sigma_team over {GRID} (sigma_conf = 0.7x), {ITERS} sims each...")
    rows = []
    for st in GRID:
        sc = round(0.7 * st, 1)
        probs = E.run_monte_carlo(elo, iterations=ITERS, seed=7, goals_model=gm,
                                  home_adv=60.0, sigma_team=float(st), sigma_conf=sc, verbose=False)
        p_model = np.array([probs.loc[t, "Win"] / 100.0 if t in probs.index else 1e-6 for t in teams])
        p_model = p_model / p_model.sum()                 # renormalise over contender set
        xent = float(-np.sum(m * np.log(np.clip(p_model, 1e-9, 1))))
        rows.append((st, sc, xent))
        print(f"    sigma_team={st:4}  sigma_conf={sc:5}  cross-entropy vs market = {xent:.4f}")

    best = min(rows, key=lambda r: r[2])
    boundary = best[0] == GRID[-1]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    print(f"\n  best: sigma_team={best[0]}  sigma_conf={best[1]}  (xent {best[2]:.4f})")

    if boundary:
        # Degenerate: cross-entropy still falling at the largest sigma -> the model
        # is far more concentrated than the market, and only an extreme (signal-
        # destroying) sigma would match it. Don't ship that. Keep a moderate sigma
        # and tell the user the BLEND is the right market-aware tool.
        st, sc = E.SIGMA_TEAM, round(0.7 * E.SIGMA_TEAM, 1)
        json.dump({"sigma_team": float(st), "sigma_conf": float(sc),
                   "source": "moderate default (market-match was degenerate; use the blend)"},
                  open(OUT, "w"), indent=2)
        print("\n  DIAGNOSIS: the optimum sits at the grid edge -> sigma-widening cannot reach")
        print("  the market's spread without extreme, signal-destroying values. This confirms")
        print("  the model is markedly more concentrated than the market. The right fix is the")
        print(f"  model+market BLEND (STEP 7 of the pipeline), not inflating sigma.")
        print(f"  [kept a MODERATE sigma_team={st:.0f} for the standalone table -> {os.path.relpath(OUT, ROOT)}]")
    else:
        json.dump({"sigma_team": float(best[0]), "sigma_conf": float(best[1]),
                   "source": "market-dispersion calibration", "iters": ITERS}, open(OUT, "w"), indent=2)
        print(f"  [saved -> {os.path.relpath(OUT, ROOT)}]  the forecast pipeline will use these.")
        print("  NOTE: this anchors the model's spread to the market; don't ALSO treat the")
        print("        model-vs-market 'edge' as independent once you've done this.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
