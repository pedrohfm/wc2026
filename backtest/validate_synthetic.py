"""
Synthetic validation of the backtest harness.

We generate matches from a KNOWN data-generating process (engine's own
expected_goals at a known GOAL_SCALE, with a known Dixon-Coles draw inflation),
then assert the harness behaves correctly. Run:  python validate_synthetic.py

Two layers:

  ORACLE (isolates the knob-fitter from Elo estimation): feed the TRUE team
  strengths and a pure-Poisson DGP; the fitted GOAL_SCALE must land near the
  true scale. This proves the fitter is unbiased GIVEN correct ratings.

  END-TO-END (realistic): rebuild Elo online from scratch and check the
  properties that mirror the three critiques:
    1. fitted GOAL_SCALE improves OOS log-loss vs the engine default (600);
    2. Dixon-Coles rho comes out negative and is not worse OOS;
    3. independent Poisson under-predicts the draw rate;
    4. the calibrated engine beats a no-skill base rate.

NOTE: in the end-to-end run the fitted scale need NOT equal the true scale,
because online Elo is a noisy estimate on a different effective spread than the
hidden true strengths -- the scale absorbs that mismatch. GOAL_SCALE is only
meaningful relative to the rating spread it is applied to. That is a real
modelling lesson, not a harness bug, which is why scale-recovery is asserted
ONLY in the oracle layer.
"""
import numpy as np
import backtest as B


def oracle_scale_recovery(true_scale=520.0, seed=3, tol=120.0):
    df, true_elo, true = B.make_synthetic(n_matches=12000, true_scale=true_scale,
                                           true_rho=0.0, seed=seed)  # pure Poisson
    eh = np.array([true_elo[h] for h in df["home"]])
    ea = np.array([true_elo[a] for a in df["away"]])
    y = B.outcomes(df); neutral = df["neutral"].values
    scales = np.arange(360, 821, 10.0)
    sw = B.sweep_goal_scale(eh, ea, neutral, y, scales, true["home"])
    rec = float(sw.loc[sw["logloss"].idxmin(), "GOAL_SCALE"])
    ok = abs(rec - true_scale) <= tol
    print(f"\n[ORACLE] true GOAL_SCALE={true_scale:.0f}  recovered={rec:.0f}  "
          f"(tol +-{tol:.0f})  -> {'PASS' if ok else 'FAIL'}")
    return ok


def end_to_end():
    df, true_elo, true = B.make_synthetic(n_teams=80, n_matches=8000,
                                          true_scale=520.0, true_rho=-0.11, seed=1)
    table, info = B.run(df, "Synthetic validation", make_plot=True, true=true)
    ll = table["logloss"].to_dict()
    base = ll["Base rate (no skill)"]
    eng_def = ll["Engine: default GOAL_SCALE=600"]
    eng_cal = [v for k, v in ll.items() if k.startswith("Engine: fitted")][0]
    eng_dc = [v for k, v in ll.items() if "Dixon-Coles" in k][0]
    return [
        ("beats no-skill base rate", eng_cal < base),
        ("fitted GOAL_SCALE improves OOS vs default", eng_cal < eng_def),
        ("Dixon-Coles rho is negative", info["rho"] < 0),
        ("Dixon-Coles not worse than indep. Poisson OOS", eng_dc <= eng_cal + 1e-3),
        ("independent Poisson under-predicts draws", info["pred_draw"] < info["obs_draw"]),
    ]


def main():
    checks = [("oracle: fitter recovers true GOAL_SCALE", oracle_scale_recovery())]
    checks += end_to_end()
    print("\n" + "-" * 62)
    print("VALIDATION ASSERTIONS")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}]  {name}")
        ok = ok and bool(passed)
    print("-" * 62)
    print("ALL PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
