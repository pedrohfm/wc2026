"""
Group-stage match probabilities — a standalone, additive output.

For every group fixture it computes the model's Win / Draw / Loss probabilities
(the same calibrated goals model + post-results Elo + host adjustment the
forecast uses), the de-vigged market W/D/L if odds are on file, and the actual
result once the match has been played and entered. Output: a dated
outputs/group_matches_<date>.csv, so progression accrues run over run.

This module is read-only with respect to the engine (it imports wc2026 but
changes nothing), so it cannot affect the existing forecast. Delete this file
and the group_matches_*.csv outputs to remove the feature entirely.

Run:  python scripts/build_group_matches.py
"""
import datetime as dt
import math
import os
import sys

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
import wc2026 as E

ELO_CSV = os.path.join(ROOT, "wc2026_elo.csv")
RESULTS = os.path.join(ROOT, "wc2026_results.xlsx")
PARAMS = os.path.join(ROOT, "params", "goals_params.json")
ODDS = os.path.join(ROOT, "data", "match_odds.csv")
OUT_DIR = os.path.join(ROOT, "outputs")
HOST_ADV = 60.0   # same host cap the forecast uses


def _pois(lam, k):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def poisson_wdl(la, lb, kmax=10):
    pH = pD = pA = 0.0
    pa = [_pois(la, i) for i in range(kmax + 1)]
    pb = [_pois(lb, j) for j in range(kmax + 1)]
    for i in range(kmax + 1):
        for j in range(kmax + 1):
            p = pa[i] * pb[j]
            if i > j: pH += p
            elif i == j: pD += p
            else: pA += p
    s = pH + pD + pA
    return pH / s, pD / s, pA / s


def load_market():
    if not os.path.exists(ODDS):
        return {}
    df = pd.read_csv(ODDS)
    out = {}
    for _, r in df.iterrows():
        try:
            oh, od, oa = float(r["oh"]), float(r["od"]), float(r["oa"])
        except (ValueError, TypeError, KeyError):
            continue
        if min(oh, od, oa) <= 1:
            continue
        ph, pd_, pa = E.shin_probs([oh, od, oa])   # Shin (1992) margin removal
        out[(str(r["home"]), str(r["away"]))] = (ph, pd_, pa)
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    elo0 = E.load_elo(ELO_CSV)
    kg, kk = E.load_results(RESULTS)
    elo = E.apply_known_results(elo0, kg, kk, E.THIRD_OVERRIDE) if (kg or kk) else dict(elo0)
    gm = E.GoalsModel.load(PARAMS) if os.path.exists(PARAMS) else None
    market = load_market()

    rows = []
    for m in sorted(E.GROUP_FIXTURES):
        t1, t2, g = E.GROUP_FIXTURES[m]
        ha = E._ha(t1, t2, HOST_ADV, E.HOSTS)
        pred, xgh, xga = "", "", ""
        if gm is not None:
            pH, pD, pA = gm.wdl(elo[t1] + ha, elo[t2])
            pi, pj = gm.most_likely(elo[t1] + ha, elo[t2])
            la, lb = gm.lambdas(elo[t1] + ha, elo[t2])
            pred, xgh, xga = f"{pi}-{pj}", round(la, 1), round(lb, 1)
        else:
            la, lb = E.expected_goals(elo[t1], elo[t2], ha=ha)
            pH, pD, pA = poisson_wdl(la, lb)
        played = m in kg
        actual, score = "", ""
        if played:
            gh, ga = kg[m]
            actual = "H" if gh > ga else ("A" if ga > gh else "D")
            score = f"{gh}-{ga}"
        mk = market.get((t1, t2))
        row = dict(match=m, group=g, home=t1, away=t2,
                   m_home=round(pH*100, 1), m_draw=round(pD*100, 1), m_away=round(pA*100, 1),
                   mkt_home="", mkt_draw="", mkt_away="",
                   pred=pred, xg_home=xgh, xg_away=xga,
                   actual=actual, score=score, played=int(played))
        if mk:
            row["mkt_home"], row["mkt_draw"], row["mkt_away"] = (round(mk[0]*100, 1), round(mk[1]*100, 1), round(mk[2]*100, 1))
        rows.append(row)

    df = pd.DataFrame(rows)
    stamp = dt.date.today().isoformat()
    path = os.path.join(OUT_DIR, f"group_matches_{stamp}.csv")
    df.to_csv(path, index=False)
    n_played = int(df["played"].sum()); n_mkt = int((df["mkt_home"] != "").sum())
    print(f"  group matches -> {os.path.relpath(path, ROOT)}  "
          f"(72 fixtures; {n_played} played; {n_mkt} with market odds; "
          f"model={'calibrated DC' if gm else 'legacy'})")


if __name__ == "__main__":
    main()
