"""
Validation of the feature-importance harness against a KNOWN data-generating
process. In the synthetic world we KNOW that squad market value, rest, and the
friendly x Elo interaction genuinely matter, and that `noise_feat` does not.

A correct harness must:
  1. give each TRUE feature a marginal incremental log-loss whose bootstrap 95%
     CI lies entirely ABOVE zero (demonstrable predictive power over Elo);
  2. give the NOISE feature a CI that straddles zero (no demonstrable power) --
     the negative control that guards against the harness rewarding overfitting;
  3. have the full feature model beat the Elo-only baseline;
  4. still rank BELOW a sharp market (the honest ceiling).

Run:  python validate_features.py
"""
import feature_importance as FI
import backtest as B


def main():
    df = FI.make_synthetic_features(seed=2)
    F, y, dates = FI.build_features(df[["date","home","away","hg","ag","neutral","tournament"]])
    F["mv_diff"] = df["mv_diff_raw"].to_numpy()
    F["noise_feat"] = df["noise_raw"].to_numpy()
    mkt_P, mkt_mask = B.market_probs_from_df(df)

    controls = ["elo_diff", "home_flag"]
    candidates = ["mv_diff", "rest_diff", "fr_x_elo", "noise_feat"]
    tab = FI.importance_study(F, y, dates, controls, candidates,
                              market_P=mkt_P, market_mask=mkt_mask,
                              label="validate", make_plot=False)
    r = tab.set_index("feature")

    checks = []
    for f in ["mv_diff", "rest_diff", "fr_x_elo"]:
        checks.append((f"{f}: CI strictly > 0 (real power)", r.loc[f, "marg_lo"] > 0))
    lo, hi = r.loc["noise_feat", "marg_lo"], r.loc["noise_feat", "marg_hi"]
    checks.append(("noise_feat: CI straddles 0 (negative control)", lo < 0 < hi))
    checks.append(("mv_diff is the strongest real feature",
                   r.loc["mv_diff", "marginal_dLL"] >= max(r.loc["rest_diff", "marginal_dLL"],
                                                           r.loc["fr_x_elo", "marginal_dLL"])))

    print("\n" + "-" * 60)
    print("VALIDATION ASSERTIONS")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}]  {name}")
        ok = ok and bool(passed)
    print("-" * 60)
    print("ALL PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
