# World Cup 2026 — Forecast Model & Tracker

A calibrated probabilistic forecaster for the 2026 World Cup: an Elo rating
system feeding a maximum-likelihood Dixon–Coles goals model, run through a
10,000-simulation Monte Carlo of the full 104-match tournament, blended with the
betting market, and published as a live dashboard.

**Live dashboard:** _(your GitHub Pages URL once deployed — see `HOSTING.md`)_

## What it does

- Simulates the whole tournament to give each team a probability of reaching
  every round and winning, with Monte Carlo standard errors.
- Calibrates the match model by MLE on ~23k internationals since 2002, and
  reports its own out-of-sample skill (log-loss / Brier / calibration) before
  every forecast — it beats a coin and the no-skill base rate, ties a one-line
  Elo model, and loses to the market (which is why it blends with the market).
- Tracks how each country moves up and down over time in an interactive,
  self-contained HTML dashboard.

## Quick start

```bash
pip install numpy pandas openpyxl scipy matplotlib pytest
python scripts/build_and_forecast.py     # forecast + skill panel + market blend
python scripts/build_dashboard.py        # -> outputs/dashboard.html
python -m pytest                         # 25 tests
```

## Daily loop (with the live site)

```bash
# 0. enter finished scores in wc2026_results.xlsx, save
export ODDS_API_KEY=xxxxx                 # once per session
bash scripts/daily.sh                      # odds -> forecast -> dashboard -> deploy
```

## Docs

| File | What |
|---|---|
| `USER_MANUAL.md` | how to use both models, day to day |
| `DATA_REQUIRED.md` | what data to add and where to get it |
| `FETCHING.md` | automated odds & squad-value feeds |
| `HOSTING.md` | publishing the dashboard (GitHub Pages etc.) |
| `docs/METHODOLOGY.md` | the method, the validation, and the honest limits |
| `STRUCTURE.md` | repo layout |

## Honest summary

This is a well-calibrated **Elo-based** forecaster, not a market-beater. Every
attempt to push past the Elo information ceiling from within (richer goals
model, match-importance features, squad value, sigma tuning) was tested and
rejected out-of-sample — only importing external information (the market blend)
helped. The model knows, and states, its own ceiling.
