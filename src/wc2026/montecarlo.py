"""Monte Carlo forecasting, single-realisation schedule, and market comparison.
Verbatim from the original monolith.
"""

import pandas as pd

from .config import HOME_ADV, SIGMA_TEAM, SIGMA_CONF, ITERATIONS, SEED, MARKET_ODDS
from .structure import CONF, HOSTS, GROUP_FIXTURES, KO, _GROUP_OF, R32, R16, QFM, SFM
from .elo_dynamics import apply_known_results
from .tournament import simulate_once

import numpy as np


def run_monte_carlo(elo, iterations=ITERATIONS, seed=SEED, kg=None, kk=None,
                    home_adv=None, hosts=HOSTS, sigma_team=SIGMA_TEAM,
                    sigma_conf=SIGMA_CONF, third_override=None, verbose=True,
                    goals_model=None):
    # Resolve the host home advantage (Elo points added to a host on home soil):
    #   explicit value   -> used exactly as given (e.g. home_adv=60)
    #   None + model      -> the model's fitted home_elo
    #   None + no model   -> the package default HOME_ADV
    # NOTE: the model's fitted home_elo is estimated on real HOME games
    # (qualifiers/friendlies) and tends to overstate a host's edge at a neutral-
    # venue World Cup, so passing an explicit, tamer value is sensible.
    if home_adv is None:
        home_adv = goals_model.home_elo if goals_model is not None else HOME_ADV
    rng = np.random.default_rng(seed)
    base = apply_known_results(elo, kg or {}, kk or {}, third_override) if (kg or kk) else dict(elo)
    teams = list(base)
    cnt = {t: dict(R32=0, R16=0, QF=0, SF=0, Final=0, Win=0) for t in teams}
    for i in range(iterations):
        r = simulate_once(base, rng, kg, kk, home_adv, hosts, sigma_team, sigma_conf, third_override, goals_model)
        for t in set(r["winners"].values()) | set(r["runners"].values()) | set(r["thirds"].values()):
            cnt[t]["R32"] += 1
        for t in {r["mwin"][m] for m in R32}: cnt[t]["R16"] += 1
        for t in {r["mwin"][m] for m in R16}: cnt[t]["QF"] += 1
        for t in {r["mwin"][m] for m in QFM}: cnt[t]["SF"] += 1
        for t in {r["mwin"][m] for m in SFM}: cnt[t]["Final"] += 1
        cnt[r["champion"]]["Win"] += 1
        if verbose and (i + 1) % 2000 == 0: print(f"  ...{i+1}/{iterations}")
    df = (pd.DataFrame(cnt).T / iterations * 100).round(1)
    df.insert(0, "Elo", [round(base[t]) for t in df.index])
    df.insert(1, "Conf", [CONF.get(t, "?") for t in df.index])
    df.insert(2, "Grp", [_GROUP_OF[t] for t in df.index])
    return df.sort_values("Win", ascending=False)


def simulate_schedule(elo, seed=None, kg=None, kk=None, home_adv=None,
                      hosts=HOSTS, sigma_team=SIGMA_TEAM, sigma_conf=SIGMA_CONF,
                      third_override=None, goals_model=None):
    if home_adv is None:
        home_adv = goals_model.home_elo if goals_model is not None else HOME_ADV
    rng = np.random.default_rng(seed)
    base = apply_known_results(elo, kg or {}, kk or {}, third_override) if (kg or kk) else dict(elo)
    r = simulate_once(base, rng, kg, kk, home_adv, hosts, sigma_team, sigma_conf, third_override, goals_model)
    rows = []
    for m in sorted(GROUP_FIXTURES):
        t1, t2, g = GROUP_FIXTURES[m]; ga, gb = r["group_scores"][m]
        rows.append({"Match": m, "Round": f"Group {g}", "Home": t1, "Away": t2,
                     "Score": f"{ga}-{gb}", "Winner": t1 if ga>gb else (t2 if gb>ga else "Draw")})
    for m in sorted(KO):
        home, away, sc, w = r["detail"][m]
        rows.append({"Match": m, "Round": KO[m][0], "Home": home, "Away": away,
                     "Score": f"{sc[0]}-{sc[1]}" if sc else "(sim)", "Winner": w})
    return pd.DataFrame(rows), r["champion"]


def compare_to_market(model_df, market=MARKET_ODDS, kind="decimal", col="Win", devig=True):
    """Compare model champion probs to bookmaker odds.
       market: {team: decimal_odds}  (or implied % if kind='implied_pct').
       Edge(pp) = model% - market%.  Edge_x = model/market (>1 => model sees value).
       NOTE: de-vig normalises over the teams you provide, so include the full
       realistic contender set or the market column will be slightly inflated."""
    if kind == "decimal": imp = {t: 1.0 / o for t, o in market.items()}
    elif kind == "implied_pct": imp = {t: o / 100.0 for t, o in market.items()}
    else: imp = dict(market)
    s = sum(imp.values()); overround = (s - 1) * 100
    rows = []
    for t, p in imp.items():
        mk = (p / s) if devig else p
        mp = (model_df.loc[t, col] / 100.0) if t in model_df.index else 0.0
        rows.append({"Team": t, "Model%": round(mp*100, 1), "Market%": round(mk*100, 1),
                     "Edge(pp)": round((mp-mk)*100, 1),
                     "Edge_x": round(mp/mk, 2) if mk > 0 else None})
    out = pd.DataFrame(rows).set_index("Team").sort_values("Market%", ascending=False)
    print(f"[market overround: {overround:.1f}%  (de-vig={'on' if devig else 'off'})]")
    return out
