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

## Summary

This is a well-calibrated **Elo-based** forecaster: ~16% better than the
no-skill base rate out-of-sample (ECE 0.025), with a full Monte-Carlo
simulation behind the group tiebreakers and the knockout bracket. Every attempt
to beat the Elo ceiling *from within* (richer goals model, match-importance,
squad value, sigma tuning) was tested and rejected out-of-sample — so the
model-only forecast is the headline, and the simulation is where the Dixon-Coles
layer earns its keep (it ties the one-line Elo benchmark on match outcomes).

The market is the obvious *external* lever, but it isn't backable yet: there are
no historical international odds to backtest, and on the live tournament so far
the model is tracking **ahead** of the de-vigged market. So the market is shown
as a benchmark, not folded into the headline, and the blend stays optional and
evidence-gated. `backtest/live_market_scorecard.py` keeps that model-vs-market
read honest as results land.
