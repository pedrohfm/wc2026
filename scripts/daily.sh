#!/usr/bin/env bash
# One-shot daily update: pull results + odds, re-forecast, rebuild dashboard, deploy.
# Results auto-fetch from football-data.org (only fills blank cells), so manual
# score entry in wc2026_results.xlsx is optional — keep Excel CLOSED while running.
# Env: FOOTBALL_DATA_TOKEN (results), ODDS_API_KEY (odds). Both optional.
set -e
cd "$(dirname "$0")/.."

echo "==> 1/4  Refreshing odds"
python3 scripts/fetch_odds.py || echo "  (odds pull skipped — set ODDS_API_KEY to enable)"

echo "==> 2/4  Auto-fetching finished match results (football-data.org)"
python3 scripts/fetch_results.py || echo "  (results pull skipped — set FOOTBALL_DATA_TOKEN to enable)"
python3 scripts/fill_ko_labels.py || true     # resolve next-round team-name labels

echo "==> 3/4  Running forecast"
python3 scripts/build_and_forecast.py

echo "--- Model vs market (live OOS scorecard, honest read) ---"
python3 backtest/live_market_scorecard.py || echo "  (scorecard skipped)"

echo "==> 4/4  Building dashboard + deploying to GitHub Pages"
python3 scripts/publish.py --git

echo "Done. Your site will refresh in ~1 minute."
