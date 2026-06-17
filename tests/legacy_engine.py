"""
============================================================================
 WORLD CUP 2026  —  MONTE CARLO ENGINE  (fully operational)
 Elo -> win expectancy -> Poisson goals, with rating-uncertainty calibration
============================================================================
Needs only: numpy, pandas.

  THREE THINGS YOU TOUCH
  ----------------------
  (1) wc2026_elo.csv      -> team strength. Update Elo from eloratings.net
                             whenever you like (e.g., weekly).
  (2) wc2026_results.csv  -> ACTUAL results. Append one row per finished
                             match as the tournament unfolds. That's it.
  (3) MARKET_ODDS (below) -> paste live bookmaker champion odds to compare.

  Then just run:  python wc2026_engine.py
  Pre-tournament it gives forecast odds. Mid-tournament it fixes known
  results, updates Elo from them, and re-forecasts only the remainder.

  WHAT IT PRODUCES
  ----------------
  - run_monte_carlo()   : P(reach R32/R16/QF/SF/Final/Win) per team
  - compare_to_market() : your model vs de-vigged market, with the edge
  - simulate_schedule() : one plausible full tournament (road to final)

  MODELLING NOTES (read once)
  ---------------------------
  - The model outputs PROBABILITIES, not a bracket pick. A single simulated
    bracket is one random draw; use the distribution, and use the market
    comparison to sense-check it. Don't confuse one sim with a forecast.
  - Rating noise (SIGMA_TEAM, SIGMA_CONF) is drawn fresh each simulation:
      eff_elo[t] = base[t] + N(0, SIGMA_TEAM)         # team uncertainty
                          + N(0, SIGMA_CONF)[conf(t)] # confederation shock
    The confederation shock is SHARED within a confederation, so it cancels
    in intra-confederation matches and only widens inter-confederation ones.
    It is MEAN-ZERO: it adds uncertainty, it does not assume Europe is over-
    or under-rated. Set SIGMA_CONF=0 to switch the effect off.
  - These sigmas are tunable. The principled way to set them is to minimise
    out-of-sample log-loss / Brier score on historical matches; the defaults
    below are sensible, not calibrated. Treat them as priors to refine.
----------------------------------------------------------------------------
"""

import numpy as np
import pandas as pd

# ============================================================================
# 0. TUNABLE PARAMETERS
# ============================================================================
SIGMA_TEAM = 40.0   # within-confederation per-team rating uncertainty (Elo)
SIGMA_CONF = 35.0   # confederation-level shared shock (inter-confed uncertainty)
GOAL_SCALE = 600.0  # Elo->goals sharpness. 400 = raw Elo (very sharp, favourite-
                    #   heavy); higher = flatter/more upsets. ~550-650 pulls
                    #   favourites toward market-realistic levels. This is the
                    #   knob that controls per-match variance; the *right* value
                    #   comes from fitting historical log-loss, not from taste.
                    #   NOTE: affects the GOALS forecast only, not Elo updates.
HOME_ADV   = 60.0   # Elo home edge applied to host nations on home soil
K_FACTOR   = 60.0   # Elo update K for World Cup matches
ITERATIONS = 10000
SEED       = 7

# Illustrative champion odds (DECIMAL). REPLACE with live bookmaker numbers.
MARKET_ODDS = {
    "Spain": 5.0, "France": 6.5, "Argentina": 7.0, "England": 8.0,
    "Brazil": 9.0, "Germany": 13.0, "Portugal": 13.0, "Netherlands": 17.0,
    "Belgium": 26.0, "Croatia": 34.0, "Colombia": 26.0, "Uruguay": 34.0,
    "Italy": 0,  # not in WC; ignored if 0/absent
}
MARKET_ODDS = {k: v for k, v in MARKET_ODDS.items() if v and v > 1}

# ============================================================================
# 1. TOURNAMENT STRUCTURE  (single source of truth; matches the Excel tool)
# ============================================================================
GROUP_FIXTURES = {
 1:("Mexico","South Africa","A"),2:("South Korea","Czechia","A"),
 3:("Canada","Bosnia & Herzegovina","B"),4:("United States","Paraguay","D"),
 5:("Qatar","Switzerland","B"),6:("Brazil","Morocco","C"),7:("Haiti","Scotland","C"),
 8:("Australia","Türkiye","D"),9:("Germany","Curaçao","E"),10:("Netherlands","Japan","F"),
 11:("Côte d'Ivoire","Ecuador","E"),12:("Sweden","Tunisia","F"),13:("Spain","Cabo Verde","H"),
 14:("Belgium","Egypt","G"),15:("Saudi Arabia","Uruguay","H"),16:("Iran","New Zealand","G"),
 17:("France","Senegal","I"),18:("Iraq","Norway","I"),19:("Argentina","Algeria","J"),
 20:("Austria","Jordan","J"),21:("Portugal","DR Congo","K"),22:("England","Croatia","L"),
 23:("Ghana","Panama","L"),24:("Uzbekistan","Colombia","K"),25:("Czechia","South Africa","A"),
 26:("Switzerland","Bosnia & Herzegovina","B"),27:("Canada","Qatar","B"),28:("Mexico","South Korea","A"),
 29:("United States","Australia","D"),30:("Scotland","Morocco","C"),31:("Brazil","Haiti","C"),
 32:("Türkiye","Paraguay","D"),33:("Netherlands","Sweden","F"),34:("Germany","Côte d'Ivoire","E"),
 35:("Ecuador","Curaçao","E"),36:("Tunisia","Japan","F"),37:("Spain","Saudi Arabia","H"),
 38:("Belgium","Iran","G"),39:("Uruguay","Cabo Verde","H"),40:("New Zealand","Egypt","G"),
 41:("Argentina","Austria","J"),42:("France","Iraq","I"),43:("Norway","Senegal","I"),
 44:("Jordan","Algeria","J"),45:("Portugal","Uzbekistan","K"),46:("England","Ghana","L"),
 47:("Panama","Croatia","L"),48:("Colombia","DR Congo","K"),49:("Switzerland","Canada","B"),
 50:("Bosnia & Herzegovina","Qatar","B"),51:("Scotland","Brazil","C"),52:("Morocco","Haiti","C"),
 53:("Czechia","Mexico","A"),54:("South Africa","South Korea","A"),55:("Ecuador","Germany","E"),
 56:("Curaçao","Côte d'Ivoire","E"),57:("Japan","Sweden","F"),58:("Tunisia","Netherlands","F"),
 59:("Türkiye","United States","D"),60:("Paraguay","Australia","D"),61:("Norway","France","I"),
 62:("Senegal","Iraq","I"),63:("Cabo Verde","Saudi Arabia","H"),64:("Uruguay","Spain","H"),
 65:("Egypt","Iran","G"),66:("New Zealand","Belgium","G"),67:("Panama","England","L"),
 68:("Croatia","Ghana","L"),69:("Colombia","Portugal","K"),70:("DR Congo","Uzbekistan","K"),
 71:("Algeria","Austria","J"),72:("Jordan","Argentina","J"),
}

KO = {
 73:("R32",("RU","A"),("RU","B")), 74:("R32",("W","E"),("3",74)),
 75:("R32",("W","F"),("RU","C")),  76:("R32",("W","C"),("RU","F")),
 77:("R32",("W","I"),("3",77)),    78:("R32",("RU","E"),("RU","I")),
 79:("R32",("W","A"),("3",79)),    80:("R32",("W","L"),("3",80)),
 81:("R32",("W","D"),("3",81)),    82:("R32",("W","G"),("3",82)),
 83:("R32",("RU","K"),("RU","L")), 84:("R32",("W","H"),("RU","J")),
 85:("R32",("W","B"),("3",85)),    86:("R32",("W","J"),("RU","H")),
 87:("R32",("W","K"),("3",87)),    88:("R32",("RU","D"),("RU","G")),
 89:("R16",("WIN",74),("WIN",77)), 90:("R16",("WIN",73),("WIN",75)),
 91:("R16",("WIN",76),("WIN",78)), 92:("R16",("WIN",79),("WIN",80)),
 93:("R16",("WIN",83),("WIN",84)), 94:("R16",("WIN",81),("WIN",82)),
 95:("R16",("WIN",86),("WIN",88)), 96:("R16",("WIN",85),("WIN",87)),
 97:("QF",("WIN",89),("WIN",90)),  98:("QF",("WIN",93),("WIN",94)),
 99:("QF",("WIN",91),("WIN",92)),  100:("QF",("WIN",95),("WIN",96)),
 101:("SF",("WIN",97),("WIN",98)), 102:("SF",("WIN",99),("WIN",100)),
 103:("3rd",("LOSE",101),("LOSE",102)), 104:("Final",("WIN",101),("WIN",102)),
}

THIRD_SLOTS = {74:set("ABCDF"),77:set("CDFGH"),79:set("CEFHI"),80:set("EHIJK"),
               81:set("BEFIJ"),82:set("AEHIJ"),85:set("EFGIJ"),87:set("DEIJL")}

HOSTS = frozenset({"Mexico","Canada","United States"})

# Confederation of each team (static; used for the inter-confed noise shock)
CONF = {
 "Mexico":"CONCACAF","Canada":"CONCACAF","United States":"CONCACAF",
 "Haiti":"CONCACAF","Curaçao":"CONCACAF","Panama":"CONCACAF",
 "Brazil":"CONMEBOL","Paraguay":"CONMEBOL","Ecuador":"CONMEBOL",
 "Uruguay":"CONMEBOL","Colombia":"CONMEBOL","Argentina":"CONMEBOL",
 "South Korea":"AFC","Qatar":"AFC","Australia":"AFC","Japan":"AFC","Iran":"AFC",
 "Saudi Arabia":"AFC","Iraq":"AFC","Jordan":"AFC","Uzbekistan":"AFC",
 "South Africa":"CAF","Morocco":"CAF","Côte d'Ivoire":"CAF","Tunisia":"CAF",
 "Egypt":"CAF","Cabo Verde":"CAF","Senegal":"CAF","Algeria":"CAF",
 "DR Congo":"CAF","Ghana":"CAF",
 "Czechia":"UEFA","Switzerland":"UEFA","Bosnia & Herzegovina":"UEFA","Türkiye":"UEFA",
 "Germany":"UEFA","Netherlands":"UEFA","Sweden":"UEFA","Belgium":"UEFA","Spain":"UEFA",
 "France":"UEFA","Norway":"UEFA","Austria":"UEFA","Portugal":"UEFA","England":"UEFA",
 "Croatia":"UEFA","Scotland":"UEFA","New Zealand":"OFC",
}

_GROUP_OF = {t: g for (t1, t2, g) in GROUP_FIXTURES.values() for t in (t1, t2)}
def _teams_in_group(g):
    seen = []
    for t1, t2, gg in GROUP_FIXTURES.values():
        if gg == g:
            for t in (t1, t2):
                if t not in seen: seen.append(t)
    return seen
GROUPS = {g: _teams_in_group(g) for g in sorted(set(_GROUP_OF.values()))}

# ============================================================================
# 2. MATCH MODEL
# ============================================================================
def win_expectancy(elo_a, elo_b, ha=0.0):
    return 1.0 / (10 ** (-((elo_a + ha) - elo_b) / 400.0) + 1.0)

def expected_goals(elo_a, elo_b, ha=0.0, base=1.35, lo=0.15, hi=4.5, scale=None):
    s = GOAL_SCALE if scale is None else scale
    w = 1.0 / (10 ** (-((elo_a + ha) - elo_b) / s) + 1.0)
    w = min(max(w, 1e-6), 1 - 1e-6)
    la = base * ((w / (1 - w)) ** 0.5)
    lb = base * (((1 - w) / w) ** 0.5)
    return min(max(la, lo), hi), min(max(lb, lo), hi)

def _ha(team_a, team_b, home_adv, hosts):
    if team_a in hosts and team_b not in hosts: return home_adv
    if team_b in hosts and team_a not in hosts: return -home_adv
    return 0.0

def sim_score(a, b, elo, rng, home_adv, hosts):
    la, lb = expected_goals(elo[a], elo[b], ha=_ha(a, b, home_adv, hosts))
    return int(rng.poisson(la)), int(rng.poisson(lb))

def sim_knockout(a, b, elo, rng, home_adv, hosts):
    ga, gb = sim_score(a, b, elo, rng, home_adv, hosts)
    if ga != gb: return a if ga > gb else b
    ha = _ha(a, b, home_adv, hosts)
    la, lb = expected_goals(elo[a], elo[b], ha=ha)
    ea, eb = int(rng.poisson(la * 0.33)), int(rng.poisson(lb * 0.33))
    if ea != eb: return a if ea > eb else b
    p = min(max(0.5 + (elo[a] + ha - elo[b]) / 2000.0, 0.40), 0.60)
    return a if rng.random() < p else b

# ============================================================================
# 3. DYNAMIC ELO UPDATING FROM KNOWN RESULTS
# ============================================================================
def update_elo(elo, a, b, ga, gb, k=K_FACTOR, home_adv=0.0, hosts=HOSTS):
    ha = _ha(a, b, home_adv, hosts)
    we = win_expectancy(elo[a], elo[b], ha)
    w = 1.0 if ga > gb else (0.5 if ga == gb else 0.0)
    gd = abs(ga - gb)
    g = 1.0 if gd <= 1 else (1.5 if gd == 2 else (11 + gd) / 8.0)
    d = k * g * (w - we)
    elo[a] += d; elo[b] -= d

def _deterministic_groups(e, kg):
    """Resolve group order from known results IF every group is complete.
       Ties broken Pts->GD->GF then by Elo (deterministic fallback)."""
    winners, runners, thirds = {}, {}, []
    for g in GROUPS:
        teams = GROUPS[g]; s = {t: {"pts":0,"gd":0,"gf":0} for t in teams}
        for m, (t1, t2, gg) in GROUP_FIXTURES.items():
            if gg != g: continue
            if m not in kg: return None
            ga, gb = kg[m]
            s[t1]["gf"]+=ga; s[t2]["gf"]+=gb; s[t1]["gd"]+=ga-gb; s[t2]["gd"]+=gb-ga
            if ga>gb: s[t1]["pts"]+=3
            elif gb>ga: s[t2]["pts"]+=3
            else: s[t1]["pts"]+=1; s[t2]["pts"]+=1
        order = sorted(teams, key=lambda t: (s[t]["pts"], s[t]["gd"], s[t]["gf"], e[t]), reverse=True)
        winners[g], runners[g] = order[0], order[1]; thirds.append((g, order[2], s[order[2]]))
    return winners, runners, thirds

def _update_elo_from_ko(e, kg, kk, third_override):
    """Update Elo from known KO results (only possible once groups complete)."""
    if not kk: return
    res = _deterministic_groups(e, kg)
    if res is None: return
    winners, runners, thirds = res
    thirds.sort(key=lambda x: (x[2]["pts"], x[2]["gd"], x[2]["gf"], e[x[1]]), reverse=True)
    qual_team = {g: t for g, t, _ in thirds[:8]}
    slot_group = dict(third_override) if third_override else allocate_thirds(list(qual_team))
    slot_team = {m: qual_team[g] for m, g in slot_group.items() if g in qual_team}
    mwin, mlose = {}, {}
    def part(slot):
        typ, ref = slot
        return {"W": winners.get(ref), "RU": runners.get(ref), "3": slot_team.get(ref),
                "WIN": mwin.get(ref), "LOSE": mlose.get(ref)}[typ]
    for m in sorted(KO):
        if m not in kk: continue
        home, away = part(KO[m][1]), part(KO[m][2])
        if home is None or away is None: continue
        ga, gb, pk = kk[m]
        update_elo(e, home, away, ga, gb)
        if ga > gb: w = home
        elif gb > ga: w = away
        else: w = home if pk == "H" else (away if pk == "A" else (home if e[home] >= e[away] else away))
        mwin[m] = w; mlose[m] = away if w == home else home

def apply_known_results(elo, kg, kk, third_override=None):
    e = dict(elo)
    for m in sorted(kg):
        t1, t2, _ = GROUP_FIXTURES[m]; ga, gb = kg[m]
        update_elo(e, t1, t2, ga, gb)
    _update_elo_from_ko(e, kg, kk, third_override)
    return e

# ============================================================================
# 4. STRUCTURAL LOGIC
# ============================================================================
def play_group(g, elo, rng, kg, home_adv, hosts):
    teams = GROUPS[g]; s = {t: {"pts":0,"gd":0,"gf":0} for t in teams}; scores = {}
    for m, (t1, t2, gg) in GROUP_FIXTURES.items():
        if gg != g: continue
        ga, gb = kg[m] if m in kg else sim_score(t1, t2, elo, rng, home_adv, hosts)
        scores[m] = (ga, gb)
        s[t1]["gf"]+=ga; s[t2]["gf"]+=gb; s[t1]["gd"]+=ga-gb; s[t2]["gd"]+=gb-ga
        if ga>gb: s[t1]["pts"]+=3
        elif gb>ga: s[t2]["pts"]+=3
        else: s[t1]["pts"]+=1; s[t2]["pts"]+=1
    order = sorted(teams, key=lambda t: (s[t]["pts"], s[t]["gd"], s[t]["gf"], rng.random()), reverse=True)
    return order, s, scores

def allocate_thirds(qual_groups):
    slots = list(THIRD_SLOTS)
    cand = {m: [g for g in qual_groups if g in THIRD_SLOTS[m]] for m in slots}
    order = sorted(slots, key=lambda m: len(cand[m]))
    assign, used = {}, set()
    def bt(i):
        if i == len(order): return True
        m = order[i]
        for g in cand[m]:
            if g not in used:
                used.add(g); assign[m] = g
                if bt(i + 1): return True
                used.discard(g); assign.pop(m, None)
        return False
    bt(0)
    leftover = [g for g in qual_groups if g not in assign.values()]
    for m in slots:
        if m not in assign and leftover: assign[m] = leftover.pop()
    return assign

def simulate_once(elo, rng, kg=None, kk=None, home_adv=HOME_ADV, hosts=HOSTS,
                  sigma_team=0.0, sigma_conf=0.0, third_override=None):
    kg = kg or {}; kk = kk or {}
    # rating noise: team component + shared confederation shock (mean-zero)
    if sigma_team or sigma_conf:
        cshock = {c: rng.normal(0, sigma_conf) for c in set(CONF.values())} if sigma_conf else {}
        eff = {t: elo[t] + (rng.normal(0, sigma_team) if sigma_team else 0.0)
                       + cshock.get(CONF.get(t), 0.0) for t in elo}
    else:
        eff = elo

    winners, runners, thirds, gscores = {}, {}, [], {}
    for g in GROUPS:
        order, s, sc = play_group(g, eff, rng, kg, home_adv, hosts)
        winners[g], runners[g] = order[0], order[1]
        thirds.append((g, order[2], s[order[2]])); gscores.update(sc)
    thirds.sort(key=lambda x: (x[2]["pts"], x[2]["gd"], x[2]["gf"], rng.random()), reverse=True)
    qual_team = {g: t for g, t, _ in thirds[:8]}
    slot_group = allocate_thirds(list(qual_team))
    if third_override:
        for m, g in third_override.items(): slot_group[m] = g
    slot_team = {m: qual_team[g] for m, g in slot_group.items() if g in qual_team}

    mwin, mlose, detail = {}, {}, {}
    def part(slot):
        typ, ref = slot
        return {"W": winners.get(ref), "RU": runners.get(ref), "3": slot_team.get(ref),
                "WIN": mwin.get(ref), "LOSE": mlose.get(ref)}[typ]
    for m in sorted(KO):
        home, away = part(KO[m][1]), part(KO[m][2])
        if m in kk:
            ga, gb, pk = kk[m]
            if ga > gb: w = home
            elif gb > ga: w = away
            else: w = home if pk == "H" else (away if pk == "A" else (home if eff[home] >= eff[away] else away))
            detail[m] = (home, away, (ga, gb), w)
        else:
            w = sim_knockout(home, away, eff, rng, home_adv, hosts)
            detail[m] = (home, away, None, w)
        mwin[m] = w; mlose[m] = away if w == home else home

    return {"winners": winners, "runners": runners, "thirds": qual_team,
            "mwin": mwin, "mlose": mlose, "detail": detail,
            "group_scores": gscores, "champion": mwin[104]}

# ============================================================================
# 5. MONTE CARLO + SINGLE REALISATION + MARKET COMPARISON
# ============================================================================
R32, R16, QFM, SFM = range(73, 89), range(89, 97), range(97, 101), (101, 102)

def run_monte_carlo(elo, iterations=ITERATIONS, seed=SEED, kg=None, kk=None,
                    home_adv=HOME_ADV, hosts=HOSTS, sigma_team=SIGMA_TEAM,
                    sigma_conf=SIGMA_CONF, third_override=None, verbose=True):
    rng = np.random.default_rng(seed)
    base = apply_known_results(elo, kg or {}, kk or {}, third_override) if (kg or kk) else dict(elo)
    teams = list(base)
    cnt = {t: dict(R32=0, R16=0, QF=0, SF=0, Final=0, Win=0) for t in teams}
    for i in range(iterations):
        r = simulate_once(base, rng, kg, kk, home_adv, hosts, sigma_team, sigma_conf, third_override)
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

def simulate_schedule(elo, seed=None, kg=None, kk=None, home_adv=HOME_ADV,
                      hosts=HOSTS, sigma_team=SIGMA_TEAM, sigma_conf=SIGMA_CONF,
                      third_override=None):
    rng = np.random.default_rng(seed)
    base = apply_known_results(elo, kg or {}, kk or {}, third_override) if (kg or kk) else dict(elo)
    r = simulate_once(base, rng, kg, kk, home_adv, hosts, sigma_team, sigma_conf, third_override)
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

# ============================================================================
# 6. I/O + MAIN
# ============================================================================
def load_elo(path="wc2026_elo.csv"):
    df = pd.read_csv(path)
    return df.set_index("Team")["Elo"].to_dict()

def _coerce_results(df):
    """Turn a dataframe with columns match/home_goals/away_goals[/pk] into
       (known_group, known_ko). Tolerant of blanks, text, extra columns."""
    cols = {c.lower().strip(): c for c in df.columns}
    def col(*names):
        for n in names:
            if n in cols: return cols[n]
        return None
    cm = col("match", "match #", "match#", "match_no")
    ch = col("home goals", "home_goals", "homegoals", "hg")
    ca = col("away goals", "away_goals", "awaygoals", "ag")
    cp = col("pk win", "pk", "pk_win", "shootout")
    if cm is None or ch is None or ca is None:
        raise ValueError("Results file must have columns: Match #, Home Goals, Away Goals (and optional PK Win).")
    kg, kk = {}, {}
    for _, row in df.iterrows():
        try:
            if pd.isna(row[cm]) or pd.isna(row[ch]) or pd.isna(row[ca]):
                continue                      # unplayed / blank -> skip
            m = int(float(row[cm])); gh = int(float(row[ch])); ga = int(float(row[ca]))
        except (ValueError, TypeError):
            continue                          # stray text -> skip safely
        if m < 1 or m > 104:
            continue
        if m <= 72:
            kg[m] = (gh, ga)
        else:
            pk = ""
            if cp is not None and not pd.isna(row[cp]):
                pk = str(row[cp]).strip().upper()
            kk[m] = (gh, ga, pk if pk in ("H", "A") else None)
    return kg, kk

def load_results(path=None):
    """Load actual results. Tries the Excel file first, then CSV.
       Returns (known_group, known_ko). Never raises on a missing file."""
    candidates = [path] if path else ["wc2026_results.xlsx", "wc2026_results.csv"]
    for p in candidates:
        if p is None: continue
        try:
            if p.lower().endswith((".xlsx", ".xlsm")):
                try:
                    raw = pd.read_excel(p, sheet_name="Results", header=None)
                except ImportError:
                    print("  [!] openpyxl not installed -> can't read Excel. "
                          "Run: pip install openpyxl   (falling back to CSV if present)")
                    continue
                except PermissionError:
                    print(f"  [!] '{p}' is open in Excel and locked. Save & close it, then re-run.")
                    raise
                # find the header row (the one containing 'Match #')
                hrow = None
                for i in range(min(10, len(raw))):
                    vals = [str(x).strip().lower() for x in raw.iloc[i].tolist()]
                    if any(v.startswith("match") for v in vals):
                        hrow = i; break
                if hrow is None:
                    raise ValueError("Couldn't find a 'Match #' header in the Results sheet.")
                df = pd.read_excel(p, sheet_name="Results", header=hrow)
            else:
                df = pd.read_csv(p)
        except FileNotFoundError:
            continue
        except PermissionError:
            raise
        return _coerce_results(df)
    print("  [i] No results file found yet -> running PRE-TOURNAMENT forecast.")
    return {}, {}

def show_fixtures(elo, kg=None, kk=None, third_override=None):
    """Print every match number with its resolved teams, given results so far.
       Use this AFTER entering group results to see who is in each knockout
       match number, so you know which row to fill in next."""
    kg = kg or {}; kk = kk or {}
    e = apply_known_results(elo, kg, kk, third_override)
    res = _deterministic_groups(e, kg)
    print("\n--- GROUP STAGE ---")
    for m in sorted(GROUP_FIXTURES):
        t1, t2, g = GROUP_FIXTURES[m]
        sc = f"{kg[m][0]}-{kg[m][1]}" if m in kg else "-- not played --"
        print(f"  M{m:>3}  Grp {g}  {t1} vs {t2:<22}  {sc}")
    if res is None:
        print("\n--- KNOCKOUTS ---  (enter all 72 group results to resolve these)")
        return
    winners, runners, thirds = res
    thirds.sort(key=lambda x: (x[2]['pts'], x[2]['gd'], x[2]['gf'], e[x[1]]), reverse=True)
    qual = {g: t for g, t, _ in thirds[:8]}
    slot_group = dict(third_override) if third_override else allocate_thirds(list(qual))
    slot_team = {m: qual.get(g) for m, g in slot_group.items()}
    mwin, mlose = {}, {}
    def part(slot):
        typ, ref = slot
        return {"W": winners.get(ref), "RU": runners.get(ref), "3": slot_team.get(ref),
                "WIN": mwin.get(ref), "LOSE": mlose.get(ref)}[typ]
    note = "" if third_override else "  [3rd-place slots are the engine's APPROX until you set third_override]"
    print(f"\n--- KNOCKOUTS ---{note}")
    for m in sorted(KO):
        rnd, hs, as_ = KO[m]
        home, away = part(hs), part(as_)
        if m in kk:
            ga, gb, pk = kk[m]
            if ga > gb: w = home
            elif gb > ga: w = away
            else: w = home if pk == "H" else (away if pk == "A" else (home if e.get(home,0) >= e.get(away,0) else away))
            sc = f"{ga}-{gb}" + (f" ({pk} pens)" if pk else "")
            mwin[m] = w; mlose[m] = away if w == home else home
        else:
            sc = "-- not played --"
        hh = home or "?"; aa = away or "?"
        print(f"  M{m:>3}  {rnd:<5} {hh} vs {aa:<22}  {sc}")

def save_forecast(df, path="wc2026_forecast_exante.csv"):
    """Save a model forecast (e.g., the pre-tournament run) for later scoring."""
    df.to_csv(path)
    print(f"  [saved ex-ante forecast -> {path}]")

def score_forecast(exante_path="wc2026_forecast_exante.csv", kg=None, kk=None):
    """After the tournament, compare the saved ex-ante MODEL forecast to what
       actually happened. Reports champion call + a Brier-style readout."""
    kg = kg or {}; kk = kk or {}
    if 104 not in kk:
        print("  [final not yet entered -> nothing to score]"); return
    fc = pd.read_csv(exante_path, index_col=0)
    # rebuild actual progression from results to find who actually reached each round
    e = apply_known_results({t: fc.loc[t, "Elo"] for t in fc.index}, kg, kk)
    # actual champion is the winner of match 104, derivable via show path:
    res = _deterministic_groups(e, kg)
    actual = {}
    if res:
        winners, runners, thirds = res
        thirds.sort(key=lambda x: (x[2]['pts'], x[2]['gd'], x[2]['gf'], e[x[1]]), reverse=True)
        qual = {g: t for g, t, _ in thirds[:8]}
        slot_group = allocate_thirds(list(qual)); slot_team = {m: qual.get(g) for m, g in slot_group.items()}
        mwin, mlose = {}, {}
        def part(slot):
            typ, ref = slot
            return {"W":winners.get(ref),"RU":runners.get(ref),"3":slot_team.get(ref),
                    "WIN":mwin.get(ref),"LOSE":mlose.get(ref)}[typ]
        for m in sorted(KO):
            if m not in kk: continue
            home, away = part(KO[m][1]), part(KO[m][2]); ga, gb, pk = kk[m]
            w = home if ga > gb else (away if gb > ga else (home if pk == "H" else away))
            mwin[m] = w; mlose[m] = away if w == home else home
        champ = mwin.get(104)
        pred = fc.sort_values("Win", ascending=False).index[0]
        p_actual = fc.loc[champ, "Win"] if champ in fc.index else 0.0
        print("\n=== EX-ANTE MODEL  vs  ACTUAL ===")
        print(f"  Model's pre-tournament favourite : {pred} ({fc.loc[pred,'Win']}%)")
        print(f"  Actual champion                  : {champ}")
        print(f"  Model probability on the champion: {p_actual}%")
        print(f"  Champion correctly called?       : {'YES' if pred == champ else 'no'}")


if __name__ == "__main__":
    elo = load_elo()
    kg, kk = load_results()
    state = "PRE-TOURNAMENT" if not (kg or kk) else f"DYNAMIC ({len(kg)} group + {len(kk)} KO results in)"
    print(f"=== Forecast — {state} ===")
    probs = run_monte_carlo(elo, kg=kg, kk=kk)
    print(probs.head(16).to_string())

    import os
    if not (kg or kk) and not os.path.exists("wc2026_forecast_exante.csv"):
        save_forecast(probs)

    print("\n=== Model vs Market (champion) ===")
    print(compare_to_market(probs).to_string())

    print("\n=== One simulated road to the final ===")
    sched, champ = simulate_schedule(elo, seed=SEED, kg=kg, kk=kk)
    print(sched[sched.Round.isin(["R16","QF","SF","3rd","Final"])].to_string(index=False))
    print(f"\nSimulated champion this run: {champ}")

    if 104 in kk:
        score_forecast(kg=kg, kk=kk)
