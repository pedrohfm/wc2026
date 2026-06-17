"""
============================================================================
 BUILD & FORECAST  —  the one-command pipeline
============================================================================
Does the whole job end-to-end:

  1. locate the historical match dataset (auto-download, or local file);
  2. fit the Dixon-Coles goals model by MLE and save it;
  3. show a GOAL_SCALE / draw-rate sanity read vs the legacy defaults;
  4. run the tournament Monte Carlo with the CALIBRATED model;
  5. attach Monte Carlo standard errors to every probability;
  6. show how sensitive the champion picks are to the rating-uncertainty sigmas;
  7. compare to the outright market if you've supplied odds;
  8. save a dated forecast CSV.

Everything degrades gracefully: if a piece of optional data is missing the
pipeline says so and carries on, so you always get a forecast.

Run from the project root:
    python scripts/build_and_forecast.py                 # full (10k sims)
    python scripts/build_and_forecast.py --quick         # fast (2k sims)
============================================================================
"""
import argparse
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "backtest"))
import wc2026 as E
from wc2026.goals_model import GoalsModel, fit as fit_goals

ELO_CSV   = os.path.join(ROOT, "wc2026_elo.csv")
PARAMS    = os.path.join(ROOT, "params", "goals_params.json")
ODDS_CHAMP = os.path.join(ROOT, "data", "odds_champion.csv")
OUT_DIR   = os.path.join(ROOT, "outputs")


def banner(title):
    print("\n" + "=" * 74 + f"\n{title}\n" + "=" * 74)


SKILL_CACHE = os.path.join(ROOT, "params", "skill_cache.json")
SIGMA_PARAMS = os.path.join(ROOT, "params", "sigma_params.json")


def load_sigma():
    """Return (sigma_team, sigma_conf, source) from a calibration file if present,
       else the package defaults."""
    import json
    if os.path.exists(SIGMA_PARAMS):
        try:
            j = json.load(open(SIGMA_PARAMS))
            return float(j["sigma_team"]), float(j["sigma_conf"]), j.get("source", "file")
        except Exception:
            pass
    return E.SIGMA_TEAM, E.SIGMA_CONF, "package default (uncalibrated)"

def skill_panel():
    """Out-of-sample skill of the modelling approach. Cached on the dataset so it
       only recomputes when backtest/data/results.csv changes (not every run)."""
    import json
    try:
        import backtest as B
    except Exception as e:
        print(f"  skill panel unavailable ({e})."); return
    real = B.load_real(min_year=2002)
    if real is None or len(real) < 3000:
        print("  no historical dataset -> skill panel unavailable.")
        print("  Add backtest/data/results.csv (see DATA_REQUIRED.md) to enable it."); return
    key = f"{len(real)}|{real['date'].max().date()}|2022-01-01"
    data = None
    if os.path.exists(SKILL_CACHE):
        try:
            j = json.load(open(SKILL_CACHE))
            if j.get("key") == key:
                data = j["data"]; print("  (cached — delete params/skill_cache.json to force recompute)")
        except Exception:
            pass
    if data is None:
        print("  computing out-of-sample skill (one-time for this dataset; then cached)...")
        data = B.compute_skill(real)
        if data:
            os.makedirs(os.path.dirname(SKILL_CACHE), exist_ok=True)
            json.dump({"key": key, "data": data}, open(SKILL_CACHE, "w"), indent=2)
    if not data:
        print("  not enough data to score."); return
    print(f"  hold-out test: {data['n_test']} matches from {data['split']} onward "
          f"(model refit on {data['n_train']} earlier matches; W/D/L, lower=better)")
    print(f"    {'model':22}{'logloss':>9}{'brier':>8}{'rps':>8}{'acc':>7}")
    for nm, (ll, br, rp, ac) in data["rows"].items():
        star = "  <-" if nm.startswith("Model") else ""
        print(f"    {nm:22}{ll:9.4f}{br:8.4f}{rp:8.4f}{ac:7.3f}{star}")
    print(f"  skill vs coin : log-loss {data['skill_coin_ll']:+.3f}   Brier {data['skill_coin_brier']:+.3f}")
    print(f"  skill vs base : log-loss {data['skill_base_ll']:+.3f}   Brier {data['skill_base_brier']:+.3f}"
          f"   (pseudo-R^2 {data['pseudo_r2']:.3f})")
    print(f"  calibration   : ECE {data['ece']:.3f}  (when it says X%, it happens ~X%; <0.03 is good)")


def step_fit_goals_model():
    """Returns (GoalsModel or None, provenance string)."""
    try:
        import backtest as B
    except Exception as e:
        print(f"  [!] could not import backtest harness ({e}); using legacy defaults.")
        return None, "legacy defaults (harness unavailable)"

    real = B.load_real(min_year=2002)
    if real is not None and len(real) > 2000:
        eh, ea = B.rolling_elo(real, k=60.0, home_adv=60.0)
        d = eh - ea
        hf = (~real["neutral"].values).astype(float)
        model = fit_goals(d, hf, real["hg"].values, real["ag"].values)
        os.makedirs(os.path.dirname(PARAMS), exist_ok=True)
        model.save(PARAMS)
        implied = 400.0 * np.log(10.0) / (2.0 * model.gamma)
        print(f"  fitted on {len(real)} real matches; saved -> {os.path.relpath(PARAMS, ROOT)}")
        print(f"    mu={model.mu:+.3f}  gamma={model.gamma:.3f} (GOAL_SCALE~{implied:.0f})  "
              f"home_elo={model.home_elo:.0f}  rho={model.rho:+.3f}")
        return model, f"MLE fit on real internationals ({dt.date.today()})"

    if os.path.exists(PARAMS):
        model = GoalsModel.load(PARAMS)
        print(f"  [!] no historical dataset reachable -> using existing {os.path.relpath(PARAMS, ROOT)}")
        print("      (provenance unknown; add the dataset and re-run to fit on real matches)")
        return model, "loaded params/goals_params.json (provenance unverified)"

    print("  [!] no historical dataset and no saved params -> using LEGACY ad-hoc map.")
    print("      Add the dataset (see DATA_REQUIRED.md) to calibrate the goals model.")
    return None, "legacy ad-hoc map (uncalibrated)"


def with_standard_errors(probs, iterations):
    """Binomial Monte Carlo standard error (in percentage points) for each
       probability column: SE = 100*sqrt(p(1-p)/N)."""
    out = probs.copy()
    for col in ["R32", "R16", "QF", "SF", "Final", "Win"]:
        if col in out.columns:
            p = out[col] / 100.0
            out[col + "_SE"] = (100.0 * np.sqrt(p * (1 - p) / iterations)).round(2)
    return out


def sigma_sensitivity(elo, model, iters, host_adv):
    grid = [(0, 0), (40, 35), (80, 70)]
    print("  champion % for the top sides across rating-uncertainty settings")
    print("  (sigma_team, sigma_conf) -- bigger = more upsets/wider distribution:")
    cols = {}
    for st, sc in grid:
        p = E.run_monte_carlo(elo, iterations=max(1500, iters // 4), seed=7,
                              sigma_team=st, sigma_conf=sc, goals_model=model,
                              home_adv=host_adv, verbose=False)
        cols[f"st{st}/sc{sc}"] = p["Win"]
    tab = pd.DataFrame(cols)
    tab = tab.loc[tab.mean(axis=1).sort_values(ascending=False).index].head(8)
    print(tab.round(1).to_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="2k sims instead of 10k")
    ap.add_argument("--iterations", type=int, default=None)
    ap.add_argument("--host-adv", type=float, default=60.0,
                    help="Elo bump for host nations on home soil (default 60; "
                         "the model's fitted home value overstates a neutral-venue host).")
    ap.add_argument("--blend-weight", type=float, default=0.30,
                    help="weight on the MODEL when blending the outright with the market "
                         "(0=all market, 1=all model). Lean low: the market out-predicts the model OOS.")
    args = ap.parse_args()
    iters = args.iterations or (2000 if args.quick else 10000)
    os.makedirs(OUT_DIR, exist_ok=True)

    banner("STEP 0  Model skill (out-of-sample, cached) — is this better than a coin?")
    skill_panel()

    banner("STEP 1-2  Calibrate the goals model")
    model, provenance = step_fit_goals_model()

    banner("STEP 3-5  Tournament forecast (calibrated model + MC standard errors)")
    elo = E.load_elo(ELO_CSV)
    kg, kk = E.load_results(os.path.join(ROOT, "wc2026_results.xlsx"))
    state = "PRE-TOURNAMENT" if not (kg or kk) else f"DYNAMIC ({len(kg)} group + {len(kk)} KO results)"
    fitted_home = f"{model.home_elo:.0f}" if model is not None else "n/a"
    st, sc, sigma_src = load_sigma()
    print(f"  state: {state}   |   goals model: {provenance}   |   sims: {iters}")
    print(f"  host advantage: {args.host_adv:.0f} Elo applied to US/Mexico/Canada "
          f"(model's fitted home value = {fitted_home}; capped here for a neutral-venue WC)")
    print(f"  rating uncertainty: sigma_team={st:.0f}, sigma_conf={sc:.0f}  [{sigma_src}]")
    probs = E.run_monte_carlo(elo, iterations=iters, seed=7, kg=kg, kk=kk,
                              goals_model=model, home_adv=args.host_adv,
                              sigma_team=st, sigma_conf=sc, verbose=False)
    probs = with_standard_errors(probs, iters)
    show = ["Elo", "Conf", "Grp", "SF", "Final", "Win", "Win_SE"]
    print(probs[show].head(16).to_string())
    stamp = dt.date.today().isoformat()
    out_csv = os.path.join(OUT_DIR, f"forecast_{stamp}.csv")
    probs.to_csv(out_csv)
    print(f"\n  [saved forecast -> {os.path.relpath(out_csv, ROOT)}]")

    banner("STEP 6  Sigma sensitivity (how load-bearing is rating uncertainty?)")
    sigma_sensitivity(elo, model, iters, args.host_adv)

    banner("STEP 7  Model vs market, and the blended forecast (outright champion)")
    champ_odds = E.load_champion_odds(ODDS_CHAMP)
    if champ_odds:
        print(E.compare_to_market(probs, market=champ_odds).to_string())
        bt, _ = E.blend_champion(probs, champ_odds, w=args.blend_weight)
        print(f"\n  BLENDED outright forecast (model weight = {args.blend_weight:.0%}; "
              f"the market out-predicts the model OOS, so we lean to it):")
        print(bt.head(12).to_string())
        print("  [blend weight is a prior, not OOS-tuned at champion level; supply historical")
        print("   match odds + optimize_blend_weight() to calibrate it. Renormalised over the")
        print("   contender set the market covers.]")
    else:
        print(f"  no {os.path.relpath(ODDS_CHAMP, ROOT)} found -> skipping.")
        print("  Add outright decimal odds (see data/odds_champion.example.csv) to enable.")

    banner("DONE")
    print(f"  Forecast written to {os.path.relpath(out_csv, ROOT)}.")
    if "uncalibrated" in provenance or "unverified" in provenance:
        print("  NOTE: goals model is not yet fit on real data. See DATA_REQUIRED.md.")


if __name__ == "__main__":
    main()
