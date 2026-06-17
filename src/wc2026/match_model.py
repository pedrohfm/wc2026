"""The match model: Elo -> win expectancy / expected goals, score simulation,
and the Elo update rule. Verbatim from the original monolith.
"""

from .config import GOAL_SCALE, K_FACTOR
from .structure import HOSTS


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


def sim_score(a, b, elo, rng, home_adv, hosts, goals_model=None):
    ha = _ha(a, b, home_adv, hosts)
    if goals_model is None:
        la, lb = expected_goals(elo[a], elo[b], ha=ha)
        return int(rng.poisson(la)), int(rng.poisson(lb))
    return goals_model.sample(elo[a] + ha, elo[b], rng)


def sim_knockout(a, b, elo, rng, home_adv, hosts, goals_model=None):
    ga, gb = sim_score(a, b, elo, rng, home_adv, hosts, goals_model)
    if ga != gb: return a if ga > gb else b
    ha = _ha(a, b, home_adv, hosts)
    if goals_model is None:
        la, lb = expected_goals(elo[a], elo[b], ha=ha)
    else:
        la, lb = goals_model.lambdas(elo[a] + ha, elo[b])
    ea, eb = int(rng.poisson(la * 0.33)), int(rng.poisson(lb * 0.33))
    if ea != eb: return a if ea > eb else b
    p = min(max(0.5 + (elo[a] + ha - elo[b]) / 2000.0, 0.40), 0.60)
    return a if rng.random() < p else b


def update_elo(elo, a, b, ga, gb, k=K_FACTOR, home_adv=0.0, hosts=HOSTS):
    ha = _ha(a, b, home_adv, hosts)
    we = win_expectancy(elo[a], elo[b], ha)
    w = 1.0 if ga > gb else (0.5 if ga == gb else 0.0)
    gd = abs(ga - gb)
    g = 1.0 if gd <= 1 else (1.5 if gd == 2 else (11 + gd) / 8.0)
    d = k * g * (w - we)
    elo[a] += d; elo[b] -= d
