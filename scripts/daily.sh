#!/usr/bin/env bash
# One-shot daily update: refresh odds, re-forecast, rebuild dashboard, deploy.
# Before running: enter any finished scores in wc2026_results.xlsx and save.
# Requires ODDS_API_KEY in your environment for the odds pull.
set -e
cd "$(dirname "$0")/.."

echo "==> 1/3  Refreshing odds"
python3 scripts/fetch_odds.py || echo "  (odds pull skipped — set ODDS_API_KEY to enable)"

echo "==> 2/3  Running forecast"
python3 scripts/build_and_forecast.py

echo "--- Model vs market (live OOS scorecard, honest read) ---"
python3 backtest/live_market_scorecard.py || echo "  (scorecard skipped)"

echo "==> 3/3  Building dashboard + deploying to GitHub Pages"
python3 scripts/publish.py --git

echo "Done. Your site will refresh in ~1 minute."
