# Data you need to add

Short version: **you already have everything needed to produce a forecast.** To
*calibrate* the model and unlock the market benchmark and the squad-value
feature, add the optional files below. Each one is independent — add what you
want, skip the rest, the pipeline degrades gracefully.

## At a glance

| File | Required? | Unlocks | You have it? |
|---|---|---|---|
| `wc2026_elo.csv` | **Required** | team strengths (the only model input) | ✅ yes |
| `wc2026_results.xlsx` | **Required** | live results entry / dynamic re-forecast | ✅ yes (you fill it in) |
| `backtest/data/results.csv` | **Strongly recommended** | calibrating the goals model + all backtests | ❌ auto-downloads, or add manually |
| `data/odds_champion.csv` | Optional | model-vs-market on the outright winner | ❌ template provided |
| `data/match_odds.csv` | Optional | market benchmark inside the backtest | ❌ template provided |
| squad market-value table | Optional | the `mv_diff` feature in feature-importance | ❌ see below |

---

## 1. `wc2026_elo.csv` — REQUIRED (you have it)

The model's only input: one strength number per team. **Refresh it once, just
before the first match, then leave it alone** (the engine updates Elo internally
from results during the tournament; refreshing mid-event double-counts).

- Schema: `Team,Group,Elo`
- Where: <https://www.eloratings.net/> — copy each qualified team's current
  rating. (Keep the spelling identical to the existing file, e.g. "Türkiye",
  "Côte d'Ivoire", "DR Congo".)
- Leakage note: set it pre-kickoff; never edit it again during the tournament.

## 2. `wc2026_results.xlsx` — REQUIRED (you have it)

Where you type actual scores as matches finish. The "Results" sheet already
lists all 104 fixtures. Enter Home/Away goals, save, re-run. For knockout ties
decided on penalties, put `H` or `A` in the PK column. (Full instructions in
`USER_MANUAL.md`.)

## 3. `backtest/data/results.csv` — STRONGLY RECOMMENDED

The continuous history of international matches used to **fit the Dixon-Coles
goals model** and to run every backtest. Without it the engine still forecasts,
but using the *uncalibrated* legacy map.

- Schema (the standard one — handled automatically):
  `date,home_team,away_team,home_score,away_score,tournament,city,country,neutral`
- Where: the **martj42** open dataset —
  <https://github.com/martj42/international_results> (file `results.csv`). On a
  normal machine the pipeline downloads it automatically on first run. If your
  network blocks that, download it manually (GitHub "Download raw file", or the
  Kaggle mirror "International football results from 1872 to date") and drop it
  at `backtest/data/results.csv`.
- Size: ~48,000 matches back to 1872; the harness uses 2002+ by default.

## 4. `data/odds_champion.csv` — OPTIONAL (outright market)

Enables the model-vs-market table on the tournament winner. A header-only
template is already there; fill in rows.

- Schema: `team,odds` (decimal odds, e.g. `Spain,5.0` means +400 / 16.7% raw)
- Where: any book's **"World Cup 2026 winner / outright"** market — Pinnacle,
  bet365, Oddschecker (aggregates many books). Copy the current decimal prices
  for the realistic contenders (12–20 teams is plenty).
- Tip: include the full contender set so the de-vig is accurate.
- Template: `data/odds_champion.example.csv`

## 5. `data/match_odds.csv` — OPTIONAL (match market for backtests)

Lets the backtest score the engine against the closing line on individual
matches — the only test that separates *edge* from *fit*.

- Schema: `date,home,away,oh,od,oa` (decimal odds for home/draw/away)
- Where: <https://www.football-data.co.uk> (some internationals), the-odds-api.com,
  or any historical-odds feed. Match `date,home,away` to the results file's
  spelling.
- How to use: `df = backtest.attach_match_odds(df, "data/match_odds.csv")`
  before `run_cv(...)`, or place columns directly in `results.csv`.
- Template: `data/match_odds.example.csv`

## 6. Squad market-value table — OPTIONAL (the `mv_diff` feature)

Only needed if you want to test squad market value in the feature-importance
study. Everything else (rest, competitive-vs-friendly) is derived for free from
the results file.

- Schema (long): `team,date,value` — total squad market value at a point in time.
- Where: **Transfermarkt** national-team market values
  (<https://www.transfermarkt.com> → national teams). Take periodic snapshots
  (e.g. before each major tournament); the harness does an as-of join so it only
  ever uses the value *before* each match (no look-ahead).
- How to use: `build_features(df, mv_table=your_table)`.

---

## Minimum to be "fully operational"

1. **Forecast today:** nothing to add — `python scripts/build_and_forecast.py`.
2. **Calibrated forecast + backtests:** add `backtest/data/results.csv` (item 3).
3. **Know if you beat the market:** add `data/odds_champion.csv` (item 4) and,
   for match-level, `data/match_odds.csv` (item 5).
4. **Test squad value as a feature:** add a Transfermarkt table (item 6).

Items 1–2 are the ones that matter. 3–4 are how you keep yourself honest.
