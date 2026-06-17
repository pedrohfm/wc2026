"""Structural simulation logic: group play, third-place allocation, and a
single full-tournament realisation. Verbatim from the original monolith.
"""

from .config import HOME_ADV
from .structure import GROUPS, GROUP_FIXTURES, KO, THIRD_SLOTS, CONF, HOSTS
from .match_model import sim_score, sim_knockout, expected_goals  # noqa: F401


def play_group(g, elo, rng, kg, home_adv, hosts, goals_model=None):
    teams = GROUPS[g]; s = {t: {"pts":0,"gd":0,"gf":0} for t in teams}; scores = {}
    for m, (t1, t2, gg) in GROUP_FIXTURES.items():
        if gg != g: continue
        ga, gb = kg[m] if m in kg else sim_score(t1, t2, elo, rng, home_adv, hosts, goals_model)
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
                  sigma_team=0.0, sigma_conf=0.0, third_override=None, goals_model=None):
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
        order, s, sc = play_group(g, eff, rng, kg, home_adv, hosts, goals_model)
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
            w = sim_knockout(home, away, eff, rng, home_adv, hosts, goals_model)
            detail[m] = (home, away, None, w)
        mwin[m] = w; mlose[m] = away if w == home else home

    return {"winners": winners, "runners": runners, "thirds": qual_team,
            "mwin": mwin, "mlose": mlose, "detail": detail,
            "group_scores": gscores, "champion": mwin[104]}
