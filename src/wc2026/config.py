"""Tunable parameters and market odds. Verbatim from the original monolith.

NOTE: these remain reasoned defaults, not fitted values. The backtest harness
(../../backtest) is the tool for replacing them with values that minimise
out-of-sample log-loss. Keeping them here (instead of scattered in the code)
is the first step toward calibrating rather than guessing them.
"""

SIGMA_TEAM = 40.0   # within-confederation per-team rating uncertainty (Elo)
SIGMA_CONF = 35.0   # confederation-level shared shock (inter-confed uncertainty)
GOAL_SCALE = 800.0  # Elo->goals sharpness (400 = raw Elo, favourite-heavy)
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

# ---------------------------------------------------------------------------
# Official Round-of-32 third-place allocation (FIFA Annex C).
# Maps each R32 match number that hosts a third-placed team to the GROUP whose
# third-placed team fills that slot. The engine's allocate_thirds() only finds
# *a* valid matching (28 are valid for the current qualifiers) — this pins the
# single official one. Set once the group stage is complete and the eight
# qualifying third-placed groups are known; here for {B,D,E,F,G,I,J,L}.
# Set to None to fall back to the engine's approximation (reversible).
THIRD_OVERRIDE = {74: "D", 77: "F", 79: "E", 80: "J",
                  81: "B", 82: "I", 85: "G", 87: "L"}
