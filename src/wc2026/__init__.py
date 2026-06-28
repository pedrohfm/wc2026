"""World Cup 2026 Monte Carlo engine (package form).

Behaviour is identical to the original wc2026_engine.py monolith; the code is
just split into cohesive modules. The parity test in tests/test_parity.py
asserts byte-for-byte-equal numeric output against a frozen copy of the
original. Public API mirrors the old module, so:

    import wc2026 as E
    elo = E.load_elo()
    kg, kk = E.load_results()
    probs = E.run_monte_carlo(elo, kg=kg, kk=kk)
"""

# --- tunable parameters & market odds ---
from .config import (SIGMA_TEAM, SIGMA_CONF, GOAL_SCALE, HOME_ADV, K_FACTOR,
                     ITERATIONS, SEED, MARKET_ODDS, THIRD_OVERRIDE)

# --- structure ---
from .structure import (GROUP_FIXTURES, KO, THIRD_SLOTS, HOSTS, CONF, GROUPS,
                        _GROUP_OF, _teams_in_group, R32, R16, QFM, SFM)

# --- match model ---
from .match_model import (win_expectancy, expected_goals, _ha, sim_score,
                          sim_knockout, update_elo)

# --- structural simulation ---
from .tournament import play_group, allocate_thirds, simulate_once

# --- dynamic Elo ---
from .elo_dynamics import (apply_known_results, _deterministic_groups,
                           _update_elo_from_ko)

# --- calibrated Dixon-Coles goals model (optional upgrade for the match engine) ---
from .goals_model import (GoalsModel, fit as fit_goals_model, negloglik as goals_negloglik,
                          time_decay_weights)

# --- model + market blending ---
from .blend import (blend_linear, blend_logpool, optimize_blend_weight,
                    blend_champion, devig as devig_odds, shin_probs, shin_devig)

# --- orthogonal feature injection (squad value -> Elo nudge) ---
from .features import elo_nudge_from_values

# --- monte carlo / outputs ---
from .montecarlo import run_monte_carlo, simulate_schedule, compare_to_market

# --- io ---
from .io import (load_elo, load_results, _coerce_results, show_fixtures,
                 save_forecast, score_forecast, load_champion_odds)

__all__ = [
    "SIGMA_TEAM", "SIGMA_CONF", "GOAL_SCALE", "HOME_ADV", "K_FACTOR",
    "ITERATIONS", "SEED", "MARKET_ODDS", "THIRD_OVERRIDE",
    "GROUP_FIXTURES", "KO", "THIRD_SLOTS", "HOSTS", "CONF", "GROUPS",
    "R32", "R16", "QFM", "SFM",
    "win_expectancy", "expected_goals", "sim_score", "sim_knockout", "update_elo",
    "play_group", "allocate_thirds", "simulate_once",
    "apply_known_results", "_deterministic_groups",
    "GoalsModel", "fit_goals_model",
    "run_monte_carlo", "simulate_schedule", "compare_to_market",
    "load_elo", "load_results", "show_fixtures", "save_forecast", "score_forecast",
]
