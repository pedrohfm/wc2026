"""
============================================================================
 WORLD CUP 2026 ENGINE — OUT-OF-SAMPLE BACKTEST HARNESS
============================================================================
Purpose
-------
The engine (wc2026_engine.py) maps Elo -> goals via a handful of hand-set
constants (GOAL_SCALE, HOME_ADV, K, base, sigmas). NONE of them have ever
been scored on real matches. This harness is the missing instrument: it
measures, out-of-sample, how good the engine's *match model* actually is,
and whether the guessed constants are anywhere near optimal.

It is deliberately dependency-light (numpy + pandas; matplotlib only for the
optional reliability chart) and self-contained.

What it does
------------
1. DATA. Loads a continuous history of international matches (the martj42
   dataset: date, home, away, scores, tournament, neutral). On your machine
   it auto-downloads and caches; in a firewalled environment it falls back to
   a documented SYNTHETIC data-generating process so the pipeline can still be
   validated end-to-end (see make_synthetic()).

2. LEAKAGE-FREE ELO. Replays every match in date order, assigning each match a
   *pre-match* Elo for both teams using the engine's OWN update rule
   (update_elo: K, margin-of-victory multiplier, home advantage). No future
   information ever enters a prediction.

3. SCORE THE ENGINE. For every match it turns the engine's expected_goals()
   into analytic P(Home win / Draw / Away win) and a full scoreline grid, then
   scores those probabilities against what actually happened with proper
   metrics: log-loss, Ranked Probability Score (RPS), multiclass Brier,
   accuracy, plus a reliability (calibration) curve.

4. TEST THE THREE CRITIQUES.
   (a) Draw bias:  predicted vs actual draw rate under independent Poisson.
   (b) Dixon-Coles: does the low-score correction beat independent Poisson OOS?
   (c) Calibration of the knobs: sweep GOAL_SCALE (and HOME_ADV) and find the
       value that minimises OOS log-loss; compare to the engine default (600).

5. BENCHMARKS. Everything is scored against (i) an Elo-logistic W/D/L model
   (Davidson, with a fitted draw parameter), (ii) the unconditional base rate,
   and (iii) "stronger team wins". A model only has predictive power if it
   beats these out-of-sample. (Market odds slot in as a fourth benchmark when
   you supply them — that is the real bar.)

Run:  python backtest.py
============================================================================
"""
from __future__ import annotations
import os, sys, math, json, ssl, urllib.request
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
OUT_DIR  = os.path.join(HERE, "outputs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

# martj42/international_results — the standard open dataset, ~48k matches 1872->now
DATA_URL   = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
DATA_LOCAL = os.path.join(DATA_DIR, "results.csv")

# ----------------------------------------------------------------------------
# 0. ENGINE MATCH MODEL  (replicated verbatim from wc2026_engine.py so we are
#    scoring the ACTUAL model, not a paraphrase of it)
# ----------------------------------------------------------------------------
DEFAULTS = dict(GOAL_SCALE=600.0, HOME_ADV=60.0, K_FACTOR=60.0, BASE=1.35)

def win_expectancy(elo_a, elo_b, ha=0.0):
    return 1.0 / (10 ** (-((elo_a + ha) - elo_b) / 400.0) + 1.0)

def expected_goals(elo_a, elo_b, ha=0.0, base=1.35, lo=0.15, hi=4.5, scale=600.0):
    w = 1.0 / (10 ** (-((elo_a + ha) - elo_b) / scale) + 1.0)
    w = min(max(w, 1e-6), 1 - 1e-6)
    la = base * ((w / (1 - w)) ** 0.5)
    lb = base * (((1 - w) / w) ** 0.5)
    return min(max(la, lo), hi), min(max(lb, lo), hi)

def update_elo(elo, a, b, ga, gb, k=60.0, ha=0.0):
    """Engine's Elo update with margin-of-victory multiplier (in place)."""
    we = win_expectancy(elo[a], elo[b], ha)
    w = 1.0 if ga > gb else (0.5 if ga == gb else 0.0)
    gd = abs(ga - gb)
    g = 1.0 if gd <= 1 else (1.5 if gd == 2 else (11 + gd) / 8.0)
    d = k * g * (w - we)
    elo[a] += d; elo[b] -= d

# ----------------------------------------------------------------------------
# 1. OUTCOME PROBABILITY MODELS  (analytic, no simulation needed)
# ----------------------------------------------------------------------------
def _pois_pmf(lam, kmax):
    k = np.arange(kmax + 1)
    return np.exp(-lam) * lam ** k / np.array([math.factorial(i) for i in k], dtype=float)

def score_grid(la, lb, kmax=12):
    """Independent-Poisson joint scoreline matrix P(i,j)."""
    pa = _pois_pmf(la, kmax); pb = _pois_pmf(lb, kmax)
    return np.outer(pa, pb)

def dixon_coles_grid(la, lb, rho, kmax=12):
    """Dixon-Coles low-score correction. rho<0 inflates draws (0-0,1-1)."""
    M = score_grid(la, lb, kmax)
    tau = np.ones_like(M)
    tau[0, 0] = 1 - la * lb * rho
    tau[0, 1] = 1 + la * rho
    tau[1, 0] = 1 + lb * rho
    tau[1, 1] = 1 - rho
    M = M * tau
    M = np.clip(M, 1e-15, None)
    return M / M.sum()

def wdl_from_grid(M):
    """(P_home_win, P_draw, P_away_win) from a scoreline matrix."""
    pH = np.tril(M, -1).sum()   # i>j  (home scores more)
    pD = np.trace(M)            # i==j
    pA = np.triu(M, 1).sum()    # i<j
    s = pH + pD + pA
    return pH / s, pD / s, pA / s

# ----------------------------------------------------------------------------
# 2. METRICS  (all "lower is better" except accuracy)
# ----------------------------------------------------------------------------
EPS = 1e-15
def log_loss(P, y):
    P = np.clip(P, EPS, 1)
    return float(-np.mean([np.log(P[i, y[i]]) for i in range(len(y))]))

def brier(P, y):
    Y = np.zeros_like(P); Y[np.arange(len(y)), y] = 1
    return float(np.mean(np.sum((P - Y) ** 2, axis=1)))

def rps(P, y):
    """Ranked Probability Score for ORDERED outcomes H(0) > D(1) > A(2).
       The standard scoring rule for football because it rewards being
       'close' (predicting a draw when the away side wins beats predicting
       a home win)."""
    Y = np.zeros_like(P); Y[np.arange(len(y)), y] = 1
    cp = np.cumsum(P, axis=1); cy = np.cumsum(Y, axis=1)
    return float(np.mean(np.sum((cp[:, :-1] - cy[:, :-1]) ** 2, axis=1)))

def accuracy(P, y):
    return float(np.mean(np.argmax(P, axis=1) == y))

# ----------------------------------------------------------------------------
# 3. DATA LOADING  (real -> cached -> synthetic fallback)
# ----------------------------------------------------------------------------
def load_real(min_year=2002):
    """martj42 schema: date,home_team,away_team,home_score,away_score,
       tournament,city,country,neutral."""
    if not os.path.exists(DATA_LOCAL):
        try:
            print(f"  downloading dataset -> {DATA_LOCAL}")
            ctx = ssl.create_default_context()
            req = urllib.request.Request(DATA_URL, headers={"User-Agent": "wc2026-backtest"})
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r, open(DATA_LOCAL, "wb") as f:
                f.write(r.read())
        except Exception as e:
            print(f"  [!] download failed ({e!s}). Drop results.csv into {DATA_DIR} manually.")
            return None
    df = pd.read_csv(DATA_LOCAL)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"].dt.year >= min_year].copy()
    df = df.dropna(subset=["home_score", "away_score"])
    df = df.rename(columns={"home_team": "home", "away_team": "away",
                            "home_score": "hg", "away_score": "ag"})
    df["hg"] = df["hg"].astype(int); df["ag"] = df["ag"].astype(int)
    df["neutral"] = df.get("neutral", False).astype(bool)
    return df.sort_values("date").reset_index(drop=True)[["date","home","away","hg","ag","neutral","tournament"]]

def make_synthetic(n_teams=80, n_matches=8000, true_scale=520.0, true_rho=-0.11,
                   true_home=65.0, seed=1, with_market=False, market_noise=0.05,
                   market_margin=1.05):
    """Documented data-generating process used to VALIDATE the harness when no
       real data is reachable. Teams have hidden true strengths; scores are
       drawn from the engine's own expected_goals() at TRUE_SCALE, then a
       Dixon-Coles tau (TRUE_RHO<0) inflates draws. A correct harness should
       (a) recover a GOAL_SCALE near true_scale, (b) find Dixon-Coles beats
       independent Poisson OOS, and (c) flag that independent Poisson
       under-predicts the draw rate.

       with_market=True also fabricates a 'bookmaker': it sees the TRUE W/D/L
       probabilities, perturbs them slightly (market_noise) and adds an
       overround (market_margin), then stores decimal odds (oh/od/oa). This is
       deliberately sharper than the engine -- the engine should LOSE to it
       out-of-sample, which is exactly the point of the benchmark."""
    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(n_teams)]
    true_elo = {t: float(rng.normal(1500, 150)) for t in teams}
    rows = []
    base_date = np.datetime64("2008-01-01")
    for m in range(n_matches):
        a, b = rng.choice(teams, size=2, replace=False)
        neutral = rng.random() < 0.4
        ha = 0.0 if neutral else true_home
        la, lb = expected_goals(true_elo[a], true_elo[b], ha=ha, scale=true_scale)
        M2 = dixon_coles_grid(la, lb, true_rho, kmax=10)   # 2D joint
        pH, pD, pA = wdl_from_grid(M2)
        idx = rng.choice(M2.size, p=M2.ravel())
        gi, gj = divmod(idx, M2.shape[1])
        row = [base_date + np.timedelta64(m * 2, "D"), a, b, int(gi), int(gj), neutral, "synthetic"]
        if with_market:
            q = np.array([pH, pD, pA]) * np.exp(rng.normal(0, market_noise, 3))
            q = q / q.sum()
            odds = 1.0 / (q * market_margin)             # decimal odds w/ overround
            row += [round(float(o), 3) for o in odds]
        rows.append(row)
    cols = ["date","home","away","hg","ag","neutral","tournament"]
    if with_market: cols += ["oh","od","oa"]
    df = pd.DataFrame(rows, columns=cols)
    return df.sort_values("date").reset_index(drop=True), true_elo, dict(scale=true_scale, rho=true_rho, home=true_home)

# ----------------------------------------------------------------------------
# 3b. MARKET ODDS  (the only benchmark that separates EDGE from FIT)
# ----------------------------------------------------------------------------
ODDS_COL_SETS = [("oh","od","oa"), ("odds_h","odds_d","odds_a"),
                 ("psh","psd","psa"), ("b365h","b365d","b365a"),
                 ("avgh","avgd","avga")]

def devig(odds, method="proportional"):
    """Decimal odds [N,3] -> de-vigged probabilities that sum to 1 per row.
       'proportional' (a.k.a. multiplicative) matches the engine's
       compare_to_market; 'shin' applies the Shin (1992) insider-trade model,
       which shaves the favourite-longshot bias a touch more realistically."""
    odds = np.asarray(odds, float)
    imp = 1.0 / odds
    s = imp.sum(axis=1, keepdims=True)
    if method == "proportional":
        return imp / s
    if method == "shin":
        out = np.empty_like(imp)
        for i in range(len(imp)):
            pi = imp[i]; B = pi.sum()
            if B <= 1.0:
                out[i] = pi / B; continue
            lo, hi = 0.0, 0.999                          # sum(P) decreases in z; bisect to sum=1
            for _ in range(80):
                z = (lo + hi) / 2
                P = (np.sqrt(z * z + 4 * (1 - z) * pi * pi / B) - z) / (2 * (1 - z))
                if P.sum() > 1.0: lo = z
                else: hi = z
            z = (lo + hi) / 2
            P = (np.sqrt(z * z + 4 * (1 - z) * pi * pi / B) - z) / (2 * (1 - z))
            out[i] = P / P.sum()
        return out
    raise ValueError(method)

def attach_match_odds(df, odds_path):
    """Left-join a separate match-odds file onto the results frame so the market
       benchmark activates. Odds file columns (case-insensitive):
           date, home, away, oh, od, oa   (decimal odds for home/draw/away)
       Matching is on (date, home, away). Rows without odds stay NaN (skipped
       in scoring). Returns the df with oh/od/oa columns added."""
    o = pd.read_csv(odds_path)
    o.columns = [c.lower().strip() for c in o.columns]
    o["date"] = pd.to_datetime(o["date"])
    keep = ["date", "home", "away", "oh", "od", "oa"]
    o = o[[c for c in keep if c in o.columns]]
    df = df.copy(); df["date"] = pd.to_datetime(df["date"])
    return df.merge(o, on=["date", "home", "away"], how="left")


def market_probs_from_df(df, method="shin"):
    """Return (P[N,3] with NaN rows where no odds, mask) using the first odds
       column-set found. Returns (None, all-False) if the dataset has no odds."""
    cols = next((c for c in ODDS_COL_SETS if all(x in df.columns for x in c)), None)
    if cols is None:
        return None, np.zeros(len(df), bool)
    O = df[list(cols)].to_numpy(float)
    mask = np.isfinite(O).all(axis=1) & (O > 1).all(axis=1)
    P = np.full((len(df), 3), np.nan)
    if mask.any():
        P[mask] = devig(O[mask], method)
    return P, mask

# ----------------------------------------------------------------------------
# 4. ROLLING PRE-MATCH ELO  (online, leakage-free)
# ----------------------------------------------------------------------------
def rolling_elo(df, k=60.0, home_adv=60.0, init=1500.0, regress=0.0, season_gap_days=None):
    """Return arrays of pre-match Elo (home, away) aligned to df rows, then
       update from the realised score. `regress` optionally shrinks toward the
       mean a touch each match (mean-reversion); 0 = pure Elo."""
    elo = {}
    eh = np.empty(len(df)); ea = np.empty(len(df))
    H, A, HG, AG, NEU = df["home"].values, df["away"].values, df["hg"].values, df["ag"].values, df["neutral"].values
    for i in range(len(df)):
        a, b = H[i], A[i]
        elo.setdefault(a, init); elo.setdefault(b, init)
        eh[i], ea[i] = elo[a], elo[b]
        ha = 0.0 if NEU[i] else home_adv
        update_elo(elo, a, b, HG[i], AG[i], k=k, ha=ha)
    return eh, ea

# ----------------------------------------------------------------------------
# 5. BENCHMARK: Elo-logistic W/D/L  (Davidson model with fitted draw nu)
# ----------------------------------------------------------------------------
def davidson_probs(d, nu):
    """d = elo_home(+ha) - elo_away. Returns (pH,pD,pA).
       Ra/Rb on a 400-base logistic; nu>0 controls draw mass."""
    ra = 10 ** (d / 800.0); rb = 10 ** (-d / 800.0)
    den = ra + rb + nu * np.sqrt(ra * rb)
    return ra / den, nu * np.sqrt(ra * rb) / den, rb / den

def fit_davidson_nu(d, y, grid=None):
    grid = grid if grid is not None else np.linspace(0.2, 3.0, 57)
    best, bnu = 1e9, 1.0
    for nu in grid:
        pH, pD, pA = davidson_probs(d, nu)
        P = np.vstack([pH, pD, pA]).T
        ll = log_loss(P, y)
        if ll < best: best, bnu = ll, nu
    return bnu

# ----------------------------------------------------------------------------
# 6. ENGINE PROBABILITIES for a set of matches given pre-match Elo
# ----------------------------------------------------------------------------
def engine_probs(eh, ea, neutral, scale, home_adv, base=1.35, rho=None, kmax=12):
    P = np.empty((len(eh), 3))
    pdraw = np.empty(len(eh))
    for i in range(len(eh)):
        ha = 0.0 if neutral[i] else home_adv
        la, lb = expected_goals(eh[i], ea[i], ha=ha, base=base, scale=scale)
        M = score_grid(la, lb, kmax) if rho is None else dixon_coles_grid(la, lb, rho, kmax)
        pH, pD, pA = wdl_from_grid(M)
        P[i] = (pH, pD, pA); pdraw[i] = pD
    return P, pdraw

def outcomes(df):
    hg, ag = df["hg"].values, df["ag"].values
    return np.where(hg > ag, 0, np.where(hg == ag, 1, 2))

# ----------------------------------------------------------------------------
# 7. CALIBRATION OF THE KNOBS  (OOS GOAL_SCALE / HOME_ADV sweep)
# ----------------------------------------------------------------------------
def sweep_goal_scale(eh, ea, neutral, y, scales, home_adv, base=1.35):
    out = []
    for s in scales:
        P, _ = engine_probs(eh, ea, neutral, s, home_adv, base)
        out.append((s, log_loss(P, y), rps(P, y)))
    return pd.DataFrame(out, columns=["GOAL_SCALE", "logloss", "rps"])

def fit_rho(eh, ea, neutral, y, scale, home_adv, base=1.35, grid=None):
    grid = grid if grid is not None else np.linspace(-0.20, 0.05, 26)
    best, brho = 1e9, 0.0
    for rho in grid:
        P, _ = engine_probs(eh, ea, neutral, scale, home_adv, base, rho=rho)
        ll = log_loss(P, y)
        if ll < best: best, brho = ll, rho
    return brho, best

# ----------------------------------------------------------------------------
# 8. RELIABILITY CURVE  (optional plot)
# ----------------------------------------------------------------------------
def reliability(P_home, y_home, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(P_home, edges) - 1, 0, bins - 1)
    rows = []
    for b in range(bins):
        m = idx == b
        if m.sum() == 0: continue
        rows.append((P_home[m].mean(), y_home[m].mean(), int(m.sum())))
    return pd.DataFrame(rows, columns=["pred", "obs", "n"])

# ----------------------------------------------------------------------------
# 9. MAIN BACKTEST
# ----------------------------------------------------------------------------
def run(df, label, k=60.0, home_adv=DEFAULTS["HOME_ADV"], base=DEFAULTS["BASE"],
        scale=DEFAULTS["GOAL_SCALE"], train_frac=0.6, make_plot=True, true=None):
    print("\n" + "=" * 76)
    print(f"BACKTEST: {label}   (n={len(df)} matches, {df['date'].min().date()} -> {df['date'].max().date()})")
    print("=" * 76)

    # leakage-free pre-match Elo
    eh, ea = rolling_elo(df, k=k, home_adv=home_adv)
    y = outcomes(df)
    neutral = df["neutral"].values

    # time-ordered split: fit knobs on the past, evaluate on the future
    cut = int(len(df) * train_frac)
    tr = slice(0, cut); te = slice(cut, len(df))
    print(f"  train (knob-fit): {df['date'].iloc[0].date()} .. {df['date'].iloc[cut-1].date()}  (n={cut})")
    print(f"  test  (OOS):      {df['date'].iloc[cut].date()} .. {df['date'].iloc[-1].date()}  (n={len(df)-cut})")

    # ---- (1) the engine AS SHIPPED (default knobs) on OOS ----
    P_def, pdraw_def = engine_probs(eh[te], ea[te], neutral[te], DEFAULTS["GOAL_SCALE"], DEFAULTS["HOME_ADV"], base)
    yte = y[te]
    base_rate = np.c_[np.full(len(yte), (y[tr] == 0).mean()),
                      np.full(len(yte), (y[tr] == 1).mean()),
                      np.full(len(yte), (y[tr] == 2).mean())]

    # ---- (2) Elo-logistic benchmark (fit nu on train) ----
    d_all = (eh + np.where(neutral, 0.0, home_adv)) - ea
    nu = fit_davidson_nu(d_all[tr], y[tr])
    pHb, pDb, pAb = davidson_probs(d_all[te], nu)
    P_bench = np.vstack([pHb, pDb, pAb]).T

    # ---- (3) calibrate GOAL_SCALE on train, apply to test ----
    scales = np.arange(380, 901, 20.0)
    sw_tr = sweep_goal_scale(eh[tr], ea[tr], neutral[tr], y[tr], scales, DEFAULTS["HOME_ADV"], base)
    best_scale = float(sw_tr.loc[sw_tr["logloss"].idxmin(), "GOAL_SCALE"])
    P_cal, _ = engine_probs(eh[te], ea[te], neutral[te], best_scale, DEFAULTS["HOME_ADV"], base)

    # ---- (4) Dixon-Coles: fit rho on train at the calibrated scale ----
    rho, _ = fit_rho(eh[tr], ea[tr], neutral[tr], y[tr], best_scale, DEFAULTS["HOME_ADV"], base)
    P_dc, pdraw_dc = engine_probs(eh[te], ea[te], neutral[te], best_scale, DEFAULTS["HOME_ADV"], base, rho=rho)

    def card(name, P):
        return dict(model=name, logloss=round(log_loss(P, yte), 4), rps=round(rps(P, yte), 4),
                    brier=round(brier(P, yte), 4), acc=round(accuracy(P, yte), 3))

    table = pd.DataFrame([
        card("Base rate (no skill)", base_rate),
        card("Elo-logistic (Davidson)", P_bench),
        card("Engine: default GOAL_SCALE=600", P_def),
        card(f"Engine: fitted GOAL_SCALE={best_scale:.0f}", P_cal),
        card(f"Engine: +Dixon-Coles rho={rho:+.3f}", P_dc),
    ]).set_index("model")
    print("\n  OUT-OF-SAMPLE SCORES (lower logloss/rps/brier = better):")
    print(table.to_string())

    # ---- (5) the three critiques, quantified ----
    obs_draw = float((yte == 1).mean())
    print("\n  CRITIQUE TESTS")
    print(f"   (a) DRAW BIAS  — independent Poisson predicts {pdraw_def.mean()*100:4.1f}% draws; "
          f"actual {obs_draw*100:4.1f}%  (gap {(pdraw_def.mean()-obs_draw)*100:+.1f}pp)")
    print(f"   (b) DIXON-COLES — fitted rho={rho:+.3f}; OOS logloss "
          f"{log_loss(P_dc,yte):.4f} vs independent-Poisson {log_loss(P_cal,yte):.4f} "
          f"({'better' if log_loss(P_dc,yte)<log_loss(P_cal,yte) else 'not better'})")
    print(f"   (c) KNOB CALIBRATION — OOS-optimal GOAL_SCALE≈{best_scale:.0f} vs engine default 600; "
          f"logloss {log_loss(P_cal,yte):.4f} vs {log_loss(P_def,yte):.4f}")
    if true:
        print(f"   [synthetic ground truth: true GOAL_SCALE={true['scale']:.0f}, true rho={true['rho']:+.3f}]")

    # ---- (6) reliability plot ----
    if make_plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            rel = reliability(P_cal[:, 0], (yte == 0).astype(float), bins=10)
            fig, ax = plt.subplots(1, 2, figsize=(11, 4.4))
            ax[0].plot([0, 1], [0, 1], "k--", lw=1, label="perfect")
            ax[0].plot(rel["pred"], rel["obs"], "o-", color="#2563eb")
            ax[0].set_xlabel("Predicted P(home win)"); ax[0].set_ylabel("Observed frequency")
            ax[0].set_title(f"Reliability — home win ({label})"); ax[0].legend()
            ax[1].plot(sw_tr["GOAL_SCALE"], sw_tr["logloss"], "o-", color="#16a34a")
            ax[1].axvline(600, color="gray", ls=":", label="engine default 600")
            ax[1].axvline(best_scale, color="#dc2626", ls="-", label=f"OOS-optimal {best_scale:.0f}")
            ax[1].set_xlabel("GOAL_SCALE"); ax[1].set_ylabel("train log-loss")
            ax[1].set_title("GOAL_SCALE calibration"); ax[1].legend()
            fig.tight_layout()
            p = os.path.join(OUT_DIR, f"reliability_{label.replace(' ','_')}.png")
            fig.savefig(p, dpi=130); plt.close(fig)
            print(f"\n  [saved figure -> {p}]")
        except Exception as e:
            print(f"  [plot skipped: {e}]")

    return table, dict(best_scale=best_scale, rho=rho, nu=nu, obs_draw=obs_draw,
                       pred_draw=float(pdraw_def.mean()))


# ----------------------------------------------------------------------------
# 10. WALK-FORWARD (EXPANDING-WINDOW) CROSS-VALIDATION
# ----------------------------------------------------------------------------
def run_cv(df, label, k=60.0, home_adv=DEFAULTS["HOME_ADV"], base=DEFAULTS["BASE"],
           n_folds=6, min_train_frac=0.40, devig_method="shin",
           make_plot=True, true=None):
    """Expanding-window CV. Elo is online (leakage-free) over the whole stream;
       for each fold the knobs (GOAL_SCALE, Dixon-Coles rho, Davidson nu) are
       RE-FITTED on everything before the fold, then frozen and used to predict
       that fold. OOS predictions from all folds are pooled and scored once, so
       every test match was predicted by a model that never saw it."""
    print("\n" + "=" * 78)
    print(f"WALK-FORWARD CV: {label}   (n={len(df)}, {df['date'].min().date()} -> {df['date'].max().date()})")
    print(f"  {n_folds} expanding folds; initial train = {min_train_frac:.0%} of history")
    print("=" * 78)

    eh, ea = rolling_elo(df, k=k, home_adv=home_adv)
    y = outcomes(df); neutral = df["neutral"].values
    d_all = (eh + np.where(neutral, 0.0, home_adv)) - ea
    P_mkt_all, mkt_mask = market_probs_from_df(df, devig_method)
    has_market = P_mkt_all is not None

    n = len(df); start = int(n * min_train_frac)
    edges = np.linspace(start, n, n_folds + 1).astype(int)
    scales = np.arange(380, 901, 20.0)

    pooled = {m: [] for m in ["def", "cal", "dc", "bench", "idx"]}
    fold_rows = []
    for f in range(n_folds):
        a, b = edges[f], edges[f + 1]
        if b <= a:  # guard against tiny folds
            continue
        tr = slice(0, a); te = slice(a, b)
        nu = fit_davidson_nu(d_all[tr], y[tr])
        sw = sweep_goal_scale(eh[tr], ea[tr], neutral[tr], y[tr], scales, DEFAULTS["HOME_ADV"], base)
        bscale = float(sw.loc[sw["logloss"].idxmin(), "GOAL_SCALE"])
        rho, _ = fit_rho(eh[tr], ea[tr], neutral[tr], y[tr], bscale, DEFAULTS["HOME_ADV"], base)

        P_def, _ = engine_probs(eh[te], ea[te], neutral[te], DEFAULTS["GOAL_SCALE"], DEFAULTS["HOME_ADV"], base)
        P_cal, _ = engine_probs(eh[te], ea[te], neutral[te], bscale, DEFAULTS["HOME_ADV"], base)
        P_dc, _  = engine_probs(eh[te], ea[te], neutral[te], bscale, DEFAULTS["HOME_ADV"], base, rho=rho)
        pHb, pDb, pAb = davidson_probs(d_all[te], nu)
        P_bench = np.vstack([pHb, pDb, pAb]).T
        yte = y[te]

        pooled["def"].append(P_def); pooled["cal"].append(P_cal); pooled["dc"].append(P_dc)
        pooled["bench"].append(P_bench); pooled["idx"].append(np.arange(a, b))
        fold_rows.append(dict(fold=f + 1,
                              test_from=str(df["date"].iloc[a].date()),
                              test_to=str(df["date"].iloc[b - 1].date()),
                              n=b - a, scale=int(bscale), rho=round(rho, 3),
                              ll_default=round(log_loss(P_def, yte), 4),
                              ll_calibrated=round(log_loss(P_cal, yte), 4),
                              ll_dixoncoles=round(log_loss(P_dc, yte), 4),
                              ll_elologit=round(log_loss(P_bench, yte), 4)))

    print("\n  PER-FOLD (out-of-sample log-loss; 'scale' is the fold's fitted GOAL_SCALE):")
    print(pd.DataFrame(fold_rows).to_string(index=False))

    idx = np.concatenate(pooled["idx"])
    yps = y[idx]
    Pd, Pc, Px, Pb = (np.vstack(pooled[m]) for m in ["def", "cal", "dc", "bench"])
    base_rate = np.tile([(y[:start] == c).mean() for c in (0, 1, 2)], (len(yps), 1))

    def card(name, P, yy=yps):
        return dict(model=name, logloss=round(log_loss(P, yy), 4), rps=round(rps(P, yy), 4),
                    brier=round(brier(P, yy), 4), acc=round(accuracy(P, yy), 3), n=len(yy))
    cards = [card("Base rate (no skill)", base_rate),
             card("Elo-logistic (Davidson)", Pb),
             card("Engine: default GOAL_SCALE=600", Pd),
             card("Engine: fitted GOAL_SCALE (per fold)", Pc),
             card("Engine: + Dixon-Coles (per fold)", Px)]

    # ---- market benchmark on the odds-available pooled subset ----
    mkt_line = None
    if has_market:
        msub = mkt_mask[idx]
        if msub.sum() >= 30:
            ym = yps[msub]
            cards.append(card("MARKET (de-vigged)", P_mkt_all[idx][msub], ym))
            # like-for-like: engine on the SAME rows the market covers
            cards.append(card("  Engine (same rows as market)", Pc[msub], ym))
            mkt_line = (log_loss(P_mkt_all[idx][msub], ym), log_loss(Pc[msub], ym), int(msub.sum()))

    print("\n  POOLED OUT-OF-SAMPLE SCORECARD (every test match predicted by a model blind to it):")
    print(pd.DataFrame(cards).set_index("model").to_string())

    obs_draw = float((yps == 1).mean()); pred_draw = float(Pd[:, 1].mean())
    print("\n  CRITIQUE TESTS (pooled OOS)")
    print(f"   (a) DRAW BIAS  — independent Poisson predicts {pred_draw*100:4.1f}% draws; "
          f"actual {obs_draw*100:4.1f}%  (gap {(pred_draw-obs_draw)*100:+.1f}pp)")
    print(f"   (b) DIXON-COLES — pooled logloss {log_loss(Px,yps):.4f} vs indep-Poisson {log_loss(Pc,yps):.4f} "
          f"({'better' if log_loss(Px,yps)<log_loss(Pc,yps) else 'not better'})")
    print(f"   (c) KNOB CALIBRATION — fitted-scale logloss {log_loss(Pc,yps):.4f} vs default-600 {log_loss(Pd,yps):.4f}")
    if has_market and mkt_line:
        verdict = "edge vs market" if mkt_line[1] < mkt_line[0] else "NO edge (market wins)"
        print(f"   (d) MARKET — market logloss {mkt_line[0]:.4f} vs engine {mkt_line[1]:.4f} "
              f"on {mkt_line[2]} matches  -> {verdict}")
    elif not has_market:
        print("   (d) MARKET — no odds columns in dataset. Add oh/od/oa (or psh/psd/psa, "
              "b365h/b365d/b365a, ...) decimal-odds columns to score the only benchmark that matters.")
    if true:
        print(f"   [synthetic ground truth: GOAL_SCALE={true['scale']:.0f}, rho={true['rho']:+.3f}]")

    if make_plot:
        try:
            import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
            rel = reliability(Pc[:, 0], (yps == 0).astype(float), 10)
            fig, ax = plt.subplots(1, 2, figsize=(11, 4.4))
            ax[0].plot([0, 1], [0, 1], "k--", lw=1, label="perfect")
            ax[0].plot(rel["pred"], rel["obs"], "o-", color="#2563eb")
            ax[0].set_xlabel("Predicted P(home win)"); ax[0].set_ylabel("Observed")
            ax[0].set_title(f"Reliability (pooled OOS) — {label}"); ax[0].legend()
            fr = pd.DataFrame(fold_rows)
            ax[1].plot(fr["fold"], fr["ll_default"], "o-", label="default 600", color="gray")
            ax[1].plot(fr["fold"], fr["ll_calibrated"], "o-", label="fitted scale", color="#16a34a")
            ax[1].plot(fr["fold"], fr["ll_elologit"], "o-", label="Elo-logistic", color="#a855f7")
            if has_market and mkt_line:
                ax[1].axhline(mkt_line[0], color="#dc2626", ls=":", label="market")
            ax[1].set_xlabel("fold"); ax[1].set_ylabel("OOS log-loss"); ax[1].set_title("Per-fold OOS"); ax[1].legend()
            fig.tight_layout()
            p = os.path.join(OUT_DIR, f"cv_{label.replace(' ','_')}.png")
            fig.savefig(p, dpi=130); plt.close(fig)
            print(f"\n  [saved figure -> {p}]")
        except Exception as e:
            print(f"  [plot skipped: {e}]")

    return pd.DataFrame(cards).set_index("model"), pd.DataFrame(fold_rows)


def compute_skill(df, split="2022-01-01", k=60.0, home_fit=60.0):
    """Clean out-of-sample skill scorecard for the modelling APPROACH: refit the
       Dixon-Coles model on matches before `split`, score it on matches after.
       Returns a dict of metrics vs a coin, the base rate, and an Elo-logistic,
       plus skill scores, a pseudo-R^2 and calibration error. None if too small."""
    from wc2026.goals_model import fit as _fitg
    df = df.sort_values("date").reset_index(drop=True)
    eh, ea = rolling_elo(df, k=k, home_adv=home_fit)
    y = outcomes(df); neu = df["neutral"].values
    d = eh - ea; hf = (~neu).astype(float)
    hg, ag = df["hg"].values, df["ag"].values
    te = (pd.to_datetime(df["date"]) >= split).values; tr = ~te
    if te.sum() < 200 or tr.sum() < 2000:
        return None
    gm = _fitg(d[tr], hf[tr], hg[tr], ag[tr])
    yte = y[te]
    P_model = np.array([gm.wdl(eh[i] + (gm.home_elo if not neu[i] else 0.0), ea[i])
                        for i in np.where(te)[0]])
    base = np.array([(y[tr] == c).mean() for c in (0, 1, 2)])
    P_base = np.tile(base, (te.sum(), 1)); P_coin = np.tile([1/3, 1/3, 1/3], (te.sum(), 1))
    dh = d + np.where(neu, 0.0, gm.home_elo)
    nu = fit_davidson_nu(dh[tr], y[tr])
    pH, pD, pA = davidson_probs(dh[te], nu); P_elo = np.vstack([pH, pD, pA]).T

    def m(P): return [round(log_loss(P, yte), 4), round(brier(P, yte), 4),
                      round(rps(P, yte), 4), round(accuracy(P, yte), 3)]
    rows = {"Coin (1/3 each)": m(P_coin), "Base rate (no skill)": m(P_base),
            "Elo-logistic": m(P_elo), "Model (Elo + DC-MLE)": m(P_model)}
    llm, llb, llc = log_loss(P_model, yte), log_loss(P_base, yte), log_loss(P_coin, yte)
    brm, brb, brc = brier(P_model, yte), brier(P_base, yte), brier(P_coin, yte)
    p = P_model.max(1); corr = (P_model.argmax(1) == yte).astype(float)
    idx = np.clip(np.digitize(p, np.linspace(0, 1, 11)) - 1, 0, 9); ece = 0.0
    for b in range(10):
        msk = idx == b
        if msk.sum(): ece += abs(p[msk].mean() - corr[msk].mean()) * msk.sum()
    ece /= len(p)
    return dict(split=str(pd.Timestamp(split).date()), n_train=int(tr.sum()), n_test=int(te.sum()),
                rows=rows,
                skill_coin_ll=round(1 - llm / llc, 3), skill_coin_brier=round(1 - brm / brc, 3),
                skill_base_ll=round(1 - llm / llb, 3), skill_base_brier=round(1 - brm / brb, 3),
                pseudo_r2=round(1 - llm / llb, 3), ece=round(ece, 3))


if __name__ == "__main__":
    real = load_real(min_year=2002)
    if real is not None and len(real) > 2000:
        run_cv(real, "Real internationals 2002+", make_plot=True)
    else:
        print("\n[no reachable real dataset -> SYNTHETIC demo of CV + market benchmark]")
        syn, _, true = make_synthetic(with_market=True)
        run_cv(syn, "Synthetic (with market)", make_plot=True, true=true)
