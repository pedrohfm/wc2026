"""Dynamic Elo updating from known results, and deterministic group resolution.
Verbatim from the original monolith.
"""

from .structure import GROUPS, GROUP_FIXTURES, KO
from .match_model import update_elo
from .tournament import allocate_thirds


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
