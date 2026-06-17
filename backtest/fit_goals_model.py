"""
Fit the Dixon-Coles goals model by MLE, save the parameters, and validate that
the calibrated model (a) recovers known truth on synthetic data, (b) beats the
ad-hoc Elo->goals map out-of-sample, and (c) drops into the tournament Monte
Carlo. This is the bridge from 'evaluation layer' to 'actual match engine'.

Run:  python fit_goals_model.py
Outputs: ../params/goals_params.json  (load with wc2026.GoalsModel.load)
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import backtest as B
import wc2026 as E
from wc2026.goals_model import fit as fit_goals, negloglik  # noqa

PARAMS = os.path.join(os.path.dirname(__file__), "..", "params", "goals_params.json")


def _wdl_dc(model, eh, ea, neutral):
    P = np.empty((len(eh), 3))
    for i in range(len(eh)):
        ha = model.home_elo if not neutral[i] else 0.0
        P[i] = model.wdl(eh[i] + ha, ea[i])
    return P


def fit_and_validate():
    real = B.load_real(min_year=2002)
    if real is not None and len(real) > 2000:
        df, true = real, None
        label = "real internationals 2002+"
    else:
        print("[no reachable real dataset -> SYNTHETIC fit/validation]")
        df, true_elo, true = B.make_synthetic(n_matches=9000, true_scale=520.0,
                                              true_rho=-0.11, true_home=65.0, with_market=False)
        label = "synthetic (known truth)"

    eh, ea = B.rolling_elo(df, k=60.0, home_adv=60.0)
    d = eh - ea
    neutral = df["neutral"].values
    home_flag = (~neutral).astype(float)
    hg, ag = df["hg"].values, df["ag"].values
    y = B.outcomes(df)

    cut = int(len(df) * 0.6)
    tr, te = slice(0, cut), slice(cut, len(df))

    model = fit_goals(d[tr], home_flag[tr], hg[tr], ag[tr])
    implied_scale = 400.0 * np.log(10.0) / (2.0 * model.gamma)
    print(f"\nFITTED Dixon-Coles goals model  [{label}]")
    print(f"  mu        = {model.mu:+.4f}   (legacy ~0.300 = ln 1.35)")
    print(f"  gamma     = {model.gamma:+.4f}  -> implied GOAL_SCALE ~ {implied_scale:.0f} (legacy 600)")
    print(f"  home_elo  = {model.home_elo:+.1f}   (legacy guessed 60)")
    print(f"  rho       = {model.rho:+.4f}   (0 = independent Poisson; <0 inflates draws)")

    # OOS comparison: DC-MLE vs ad-hoc map (default knobs)
    P_dc = _wdl_dc(model, eh[te], ea[te], neutral[te])
    P_legacy, _ = B.engine_probs(eh[te], ea[te], neutral[te], 600.0, 60.0)
    ll_dc, ll_lg = B.log_loss(P_dc, y[te]), B.log_loss(P_legacy, y[te])
    draw_dc = P_dc[:, 1].mean(); draw_lg = P_legacy[:, 1].mean(); draw_obs = (y[te] == 1).mean()
    print(f"\n  OOS log-loss   DC-MLE {ll_dc:.4f}  vs  ad-hoc map {ll_lg:.4f}  "
          f"({'better' if ll_dc < ll_lg else 'worse'})")
    print(f"  OOS draw rate  DC-MLE {draw_dc*100:.1f}%  ad-hoc {draw_lg*100:.1f}%  actual {draw_obs*100:.1f}%")

    os.makedirs(os.path.dirname(PARAMS), exist_ok=True)
    model.save(PARAMS)
    print(f"  [saved -> {os.path.relpath(PARAMS)}]")

    # ---- integration: the fitted model runs inside the tournament Monte Carlo ----
    elo = E.load_elo(os.path.join(os.path.dirname(__file__), "..", "wc2026_elo.csv"))
    probs = E.run_monte_carlo(elo, iterations=400, seed=7, goals_model=model, verbose=False)
    top = probs.head(3)
    integ_ok = (abs(probs["Win"].sum() - 100.0) < 1.0) and (probs["Win"].iloc[0] > 0)
    print(f"\n  INTEGRATION — Monte Carlo with the fitted model ran; top-3 champions:")
    print("   ", ", ".join(f"{t} {probs.loc[t,'Win']:.1f}%" for t in top.index))

    checks = [("DC-MLE beats ad-hoc map OOS", ll_dc < ll_lg + 1e-4),
              ("MC integration produces a valid forecast", integ_ok)]
    if true is not None:
        true_gamma = 400.0 * np.log(10.0) / (2.0 * true["scale"])
        # ORACLE: fit on TRUE strengths -> gamma must recover the DGP value.
        # (On ONLINE Elo, gamma is scale-entangled with the rating spread and is
        #  NOT expected to equal true_gamma -- the same lesson as GOAL_SCALE.)
        d_oracle = np.array([true_elo[h] for h in df["home"]]) - np.array([true_elo[a] for a in df["away"]])
        m_oracle = fit_goals(d_oracle, home_flag, hg, ag)
        print(f"\n  [ground truth: gamma~{true_gamma:.3f}, rho={true['rho']:+.3f}, home={true['home']:.0f}]")
        print(f"  [oracle fit on TRUE strengths: gamma={m_oracle.gamma:.3f}, rho={m_oracle.rho:+.3f}, "
              f"home={m_oracle.home_elo:.0f}]")
        checks += [
            ("ORACLE recovers gamma near truth", abs(m_oracle.gamma - true_gamma) < 0.12),
            ("recovered rho negative (draw inflation)", model.rho < 0),
            ("recovered rho near truth", abs(model.rho - true["rho"]) < 0.04),
            ("DC draw rate closer to actual than ad-hoc",
             abs(draw_dc - draw_obs) <= abs(draw_lg - draw_obs) + 1e-6),
        ]

    print("\n" + "-" * 60)
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}]  {name}")
        ok = ok and bool(passed)
    print("-" * 60)
    print("ALL PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(fit_and_validate())
