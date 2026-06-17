"""
============================================================================
 FEATURE IMPORTANCE — incremental out-of-sample value of candidate variables
============================================================================
Question: do squad market value, rest/travel, and competitive-vs-friendly
weight actually improve a World Cup match forecast, or do they just re-state
what Elo already knows?

The honest answer is *incremental* OOS log-loss measured on top of a model that
ALREADY contains Elo (and, as a ceiling, the market). A variable's raw
predictive power is the wrong number: squad value correlates ~0.8+ with Elo, so
most of its apparent power is redundant. We therefore use a discriminative
model into which features enter as covariates, and judge each feature by what
it ADDS over Elo, under the same walk-forward (expanding-window) CV as the rest
of the harness.

Model: an ORDERED LOGIT for the ordinal outcome away-win < draw < home-win,
fit by maximum likelihood. Ordinal (not multinomial) because W/D/L lie on a
latent home-favourability axis; this is the standard parsimonious choice and it
nests cleanly — adding a feature just extends the linear index.

For each candidate we report:
  * MARGINAL dLL : log-loss improvement of {controls + this feature} over
                   {controls} alone.  (controls = Elo diff + home flag)
  * UNIQUE   dLL : log-loss DROP from removing this feature from the FULL model
                   (its contribution net of every other feature — the strict test).
  * a paired-bootstrap 95% CI on the pooled OOS per-match log-loss delta, so you
    can see whether the gain is distinguishable from noise.
  * the MARKET ceiling: the full model vs de-vigged odds on the odds subset.

Positive dLL = the feature helps (lower log-loss). A CI that straddles 0 means
"no demonstrable power", however nice the point estimate looks.

Run:  python feature_importance.py     (synthetic validation if no real data)
============================================================================
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd

import backtest as B   # reuse rolling_elo, metrics, market handling, OUT_DIR

try:
    from scipy.optimize import minimize
    _HAVE_SCIPY = True
except Exception:
    _HAVE_SCIPY = False

EPS = 1e-12

# ----------------------------------------------------------------------------
# 1. ORDERED LOGIT  (latent home-favourability; two cutpoints for the draw band)
# ----------------------------------------------------------------------------
def _unpack(params, k):
    beta = params[:k]
    c1 = params[k]
    c2 = c1 + np.log1p(np.exp(params[k + 1]))   # softplus gap keeps c2 > c1
    return beta, c1, c2

def _probs(params, X):
    """Return P columns in [home, draw, away] order."""
    k = X.shape[1]
    beta, c1, c2 = _unpack(params, k)
    z = X @ beta
    F1 = 1.0 / (1.0 + np.exp(-(c1 - z)))
    F2 = 1.0 / (1.0 + np.exp(-(c2 - z)))
    pA = F1; pD = F2 - F1; pH = 1.0 - F2
    P = np.vstack([pH, pD, pA]).T
    return np.clip(P, EPS, 1.0)

def _nll(params, X, y_model):
    """y_model: 0=away,1=draw,2=home (the latent order)."""
    P = _probs(params, X)              # [home,draw,away]
    Pm = P[:, ::-1]                    # -> [away,draw,home] to index y_model
    return -np.mean(np.log(Pm[np.arange(len(y_model)), y_model]))

def fit_ologit(X, y_home):
    """y_home: 0=home,1=draw,2=away (harness convention). Returns params."""
    y_model = 2 - y_home               # -> 0=away,1=draw,2=home
    k = X.shape[1]
    x0 = np.r_[np.zeros(k), -1.0, 0.0]
    if _HAVE_SCIPY:
        r = minimize(_nll, x0, args=(X, y_model), method="BFGS",
                     options=dict(maxiter=400))
        return r.x
    # numpy-only fallback: simple gradient descent on finite-diff gradient
    p = x0.copy(); lr = 0.05
    for _ in range(2000):
        g = np.zeros_like(p)
        f0 = _nll(p, X, y_model)
        for j in range(len(p)):
            pp = p.copy(); pp[j] += 1e-5
            g[j] = (_nll(pp, X, y_model) - f0) / 1e-5
        p -= lr * g
    return p

def predict_ologit(params, X):
    return _probs(params, X)           # [home,draw,away]

# ----------------------------------------------------------------------------
# 2. WALK-FORWARD CV with a given feature set -> pooled OOS probabilities
# ----------------------------------------------------------------------------
def cv_predict(F, feat_cols, y, dates, n_folds=6, min_train_frac=0.40):
    """F: feature DataFrame (already leakage-free, pre-match).
       Standardisation is fit on TRAIN only, each fold. Returns (pooled P,
       pooled y, pooled index) where every row was predicted blind."""
    X = F[feat_cols].to_numpy(float)
    n = len(F); start = int(n * min_train_frac)
    edges = np.linspace(start, n, n_folds + 1).astype(int)
    Ps, ys, idxs = [], [], []
    for f in range(n_folds):
        a, b = edges[f], edges[f + 1]
        if b <= a: continue
        tr = slice(0, a); te = slice(a, b)
        mu = X[tr].mean(0); sd = X[tr].std(0); sd[sd < 1e-9] = 1.0
        Xtr = (X[tr] - mu) / sd; Xte = (X[te] - mu) / sd
        params = fit_ologit(Xtr, y[tr])
        Ps.append(predict_ologit(params, Xte)); ys.append(y[te]); idxs.append(np.arange(a, b))
    return np.vstack(Ps), np.concatenate(ys), np.concatenate(idxs)

def pointwise_logloss(P, y):
    return -np.log(np.clip(P[np.arange(len(y)), y], EPS, 1.0))

def paired_bootstrap(delta, B_boot=600, seed=0):
    """delta_i = loss_base_i - loss_aug_i (positive = augmented model better).
       Returns (mean, lo95, hi95, p_gt0)."""
    rng = np.random.default_rng(seed)
    n = len(delta); means = np.empty(B_boot)
    for b in range(B_boot):
        means[b] = delta[rng.integers(0, n, n)].mean()
    return float(delta.mean()), float(np.percentile(means, 2.5)), \
           float(np.percentile(means, 97.5)), float((means > 0).mean())

# ----------------------------------------------------------------------------
# 3. THE STUDY: marginal + unique incremental log-loss per feature
# ----------------------------------------------------------------------------
def importance_study(F, y, dates, controls, candidates,
                     market_P=None, market_mask=None, n_folds=6, label="study",
                     make_plot=True):
    print("\n" + "=" * 80)
    print(f"FEATURE IMPORTANCE: {label}   (n={len(F)}, {n_folds} expanding folds)")
    print(f"  controls (always in): {controls}")
    print(f"  candidates tested   : {candidates}")
    print("=" * 80)

    # baseline = controls only
    P0, y0, idx0 = cv_predict(F, controls, y, dates, n_folds)
    L0 = pointwise_logloss(P0, y0)
    # full = controls + all candidates
    Pf, yf, idxf = cv_predict(F, controls + candidates, y, dates, n_folds)
    Lf = pointwise_logloss(Pf, yf)

    rows = []
    for c in candidates:
        # MARGINAL: controls + c
        Pm, ym, _ = cv_predict(F, controls + [c], y, dates, n_folds)
        Lm = pointwise_logloss(Pm, ym)
        dmarg = L0 - Lm
        mm, mlo, mhi, mp = paired_bootstrap(dmarg)
        # UNIQUE: full minus c (drop-one)
        drop = controls + [x for x in candidates if x != c]
        Pd, yd, _ = cv_predict(F, drop, y, dates, n_folds)
        Ld = pointwise_logloss(Pd, yd)
        duniq = Ld - Lf
        um, ulo, uhi, up = paired_bootstrap(duniq)
        rows.append(dict(feature=c,
                         marginal_dLL=round(mm, 4), marg_CI=f"[{mlo:+.4f},{mhi:+.4f}]", marg_p=round(mp, 2),
                         unique_dLL=round(um, 4), uniq_CI=f"[{ulo:+.4f},{uhi:+.4f}]", uniq_p=round(up, 2),
                         marg_lo=mlo, marg_hi=mhi, uniq_lo=ulo, uniq_hi=uhi))

    tab = pd.DataFrame(rows)
    _show = ["feature", "marginal_dLL", "marg_CI", "marg_p", "unique_dLL", "uniq_CI", "uniq_p"]
    base_ll = L0.mean(); full_ll = Lf.mean()
    print(f"\n  baseline (controls only) OOS log-loss : {base_ll:.4f}")
    print(f"  full model OOS log-loss               : {full_ll:.4f}   "
          f"(total gain {base_ll-full_ll:+.4f})")
    print("\n  PER-FEATURE INCREMENTAL OOS LOG-LOSS  (positive = helps; "
          "p = bootstrap P(improvement>0))")
    print("  MARGINAL = added on top of Elo alone;  UNIQUE = lost if removed from full model")
    print(tab[_show].to_string(index=False))

    # market ceiling
    if market_P is not None and market_mask is not None:
        msub = market_mask[idxf]
        if msub.sum() >= 30:
            ym2 = yf[msub]
            mll = B.log_loss(market_P[idxf][msub], ym2)
            fll = B.log_loss(Pf[msub], ym2)
            print(f"\n  MARKET CEILING (on {int(msub.sum())} odds-available matches):")
            print(f"    market log-loss {mll:.4f}  vs  full feature model {fll:.4f}  "
                  f"-> {'model beats market' if fll<mll else 'market still ahead'}")

    if make_plot:
        try:
            import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(8.4, 4.4))
            yv = np.arange(len(tab))
            marg = tab["marginal_dLL"].to_numpy()
            uniq = tab["unique_dLL"].to_numpy()
            ax.barh(yv + 0.2, marg, height=0.38, color="#2563eb", label="marginal (over Elo)")
            ax.barh(yv - 0.2, uniq, height=0.38, color="#16a34a", label="unique (drop-one)")
            ax.axvline(0, color="k", lw=1)
            ax.set_yticks(yv); ax.set_yticklabels(tab["feature"])
            ax.set_xlabel("incremental OOS log-loss reduction  (higher = more predictive)")
            ax.set_title(f"Feature importance — {label}"); ax.legend()
            fig.tight_layout()
            p = os.path.join(B.OUT_DIR, f"feature_importance_{label.replace(' ','_')}.png")
            fig.savefig(p, dpi=130); plt.close(fig)
            print(f"\n  [saved figure -> {p}]")
        except Exception as e:
            print(f"  [plot skipped: {e}]")
    return tab

# ----------------------------------------------------------------------------
# 4. REAL-DATA FEATURE BUILDERS  (all strictly pre-match / leakage-free)
# ----------------------------------------------------------------------------
FRIENDLY_KEYS = ("friendly",)
MAJOR_KEYS = ("world cup", "uefa euro", "copa am", "african cup", "afc asian",
              "confederations", "nations league")

def build_features(df, k=60.0, home_adv=60.0, mv_table=None):
    """Attach leakage-free features to a results frame (martj42 schema +
       optional market-value table). Returns (F, y, dates)."""
    df = df.sort_values("date").reset_index(drop=True).copy()
    eh, ea = B.rolling_elo(df, k=k, home_adv=home_adv)
    F = pd.DataFrame(index=df.index)
    F["elo_diff"] = eh - ea
    F["home_flag"] = (~df["neutral"].astype(bool)).astype(float)

    # rest differential: days since each team's previous match (pre-match only)
    last = {}
    rest_h = np.full(len(df), 7.0); rest_a = np.full(len(df), 7.0)
    d = pd.to_datetime(df["date"]).values
    for i in range(len(df)):
        h, a = df["home"].iloc[i], df["away"].iloc[i]
        if h in last: rest_h[i] = (d[i] - last[h]) / np.timedelta64(1, "D")
        if a in last: rest_a[i] = (d[i] - last[a]) / np.timedelta64(1, "D")
        last[h] = d[i]; last[a] = d[i]
    F["rest_diff"] = np.clip(rest_h, 0, 30) - np.clip(rest_a, 0, 30)

    # competitive vs friendly weight, and its interaction with the Elo gap
    t = df["tournament"].astype(str).str.lower()
    friendly = t.str.contains("|".join(FRIENDLY_KEYS)).astype(float)
    F["friendly"] = friendly
    F["fr_x_elo"] = friendly * F["elo_diff"]

    # squad market value (as-of date) if a table is provided
    if mv_table is not None:
        F["mv_diff"] = _market_value_diff(df, mv_table)
    y = B.outcomes(df)
    return F, y, pd.to_datetime(df["date"])

def _market_value_diff(df, mv_table):
    """mv_table: long DataFrame [team, date, value]. We join the most recent
       value strictly BEFORE each match (as-of merge) to avoid look-ahead."""
    mv = mv_table.sort_values("date")
    out = np.zeros(len(df))
    for col, sign in (("home", 1.0), ("away", -1.0)):
        m = pd.merge_asof(df[["date", col]].rename(columns={col: "team"}).sort_values("date"),
                          mv, on="date", by="team", direction="backward")
        out += sign * np.log1p(m["value"].fillna(m["value"].median()).to_numpy())
    return out

# ----------------------------------------------------------------------------
# 5. SYNTHETIC DGP with KNOWN feature effects (validation + negative control)
# ----------------------------------------------------------------------------
def make_synthetic_features(n_teams=70, n_matches=9000, seed=2, true_scale=520.0,
                            true_home=65.0, friendly_damp=0.6, rest_coef=5.0,
                            drift=12.0, mv_noise=35.0, with_market=True):
    """Goals are generated from latent team strengths that DRIFT over time.
       - squad market value reads CURRENT strength (cleaner than lagged Elo) ->
         it should add power OVER Elo.
       - rest_diff has a real (modest) effect on the goal gap.
       - friendlies COMPRESS the strength gap (friendly_damp) -> the
         friendly x Elo interaction should help.
       - noise_feat has ZERO effect (the negative control that must score ~0).
       A sharp bookmaker (sees the true probs) sets the market ceiling."""
    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(n_teams)]
    strength = {t: float(rng.normal(0, 1)) for t in teams}     # latent, drifts
    last_date = {}
    base = np.datetime64("2006-01-01")
    rows = []
    for m in range(n_matches):
        a, b = rng.choice(teams, size=2, replace=False)
        # drift strengths a touch on each appearance
        strength[a] += rng.normal(0, drift / 300.0); strength[b] += rng.normal(0, drift / 300.0)
        date = base + np.timedelta64(int(m * 1.2), "D")
        neutral = rng.random() < 0.35
        friendly = rng.random() < 0.45
        Sa = 1500 + 300 * strength[a]; Sb = 1500 + 300 * strength[b]
        # rest
        rh = (date - last_date[a]) / np.timedelta64(1, "D") if a in last_date else 7.0
        ra = (date - last_date[b]) / np.timedelta64(1, "D") if b in last_date else 7.0
        rest_diff = float(np.clip(rh, 0, 30) - np.clip(ra, 0, 30))
        last_date[a] = date; last_date[b] = date
        # effective gap that actually drives goals (the ground truth)
        gap = (Sa - Sb) * (friendly_damp if friendly else 1.0)
        ha = 0.0 if neutral else true_home
        eff = gap + ha + rest_coef * rest_diff
        la, lb = B.expected_goals(1500 + eff, 1500.0, ha=0.0, scale=true_scale)
        gi, gj = int(rng.poisson(la)), int(rng.poisson(lb))
        # observed features
        mv_a = Sa + rng.normal(0, mv_noise); mv_b = Sb + rng.normal(0, mv_noise)  # current-strength proxy
        noise_feat = float(rng.normal(0, 1))
        row = [date, a, b, gi, gj, neutral, "friendly" if friendly else "world cup qualification",
               mv_a - mv_b, rest_diff, noise_feat]
        if with_market:
            M2 = B.score_grid(la, lb, 10)
            pH, pD, pA = B.wdl_from_grid(M2)
            q = np.array([pH, pD, pA]) * np.exp(rng.normal(0, 0.04, 3)); q /= q.sum()
            odds = 1.0 / (q * 1.05)
            row += [round(float(o), 3) for o in odds]
        rows.append(row)
    cols = ["date","home","away","hg","ag","neutral","tournament","mv_diff_raw","rest_diff_raw","noise_raw"]
    if with_market: cols += ["oh","od","oa"]
    df = pd.DataFrame(rows, columns=cols)
    return df


def run_synthetic():
    df = make_synthetic_features()
    # build the standard leakage-free features, then attach the synthetic ones
    F, y, dates = build_features(df[["date","home","away","hg","ag","neutral","tournament"]])
    F["mv_diff"] = df["mv_diff_raw"].to_numpy()        # (would come from as-of join on real data)
    F["noise_feat"] = df["noise_raw"].to_numpy()
    mkt_P, mkt_mask = B.market_probs_from_df(df)
    controls = ["elo_diff", "home_flag"]
    candidates = ["mv_diff", "rest_diff", "fr_x_elo", "noise_feat"]
    tab = importance_study(F, y, dates, controls, candidates,
                           market_P=mkt_P, market_mask=mkt_mask,
                           label="Synthetic (known truth)")
    print("\n  GROUND TRUTH: mv_diff / rest_diff / fr_x_elo SHOULD help; "
          "noise_feat SHOULD be ~0 (CI straddling 0).")
    return tab


if __name__ == "__main__":
    if not _HAVE_SCIPY:
        print("[note] scipy not found; using slower numpy fallback. `pip install scipy` for speed.")
    real = B.load_real(min_year=2002)
    if real is not None and len(real) > 2000:
        F, y, dates = build_features(real)   # mv_diff requires a market-value table (see docs)
        controls = ["elo_diff", "home_flag"]
        candidates = [c for c in ["rest_diff", "fr_x_elo"] if c in F.columns]
        mkt_P, mkt_mask = B.market_probs_from_df(real)
        importance_study(F, y, dates, controls, candidates, market_P=mkt_P,
                         market_mask=mkt_mask, label="Real internationals 2002+")
    else:
        print("\n[no reachable real dataset -> SYNTHETIC validation of feature-importance harness]")
        run_synthetic()
