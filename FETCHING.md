# Automated data feeds — odds & squad values

Two accumulators that build the historical data the last two model levers need.
Both run on YOUR machine (normal HTTP clients) and degrade gracefully.

## Why "accumulators", not one-shot historical pulls

Neither feed has a clean, free, bulk-historical source: The Odds API's free tier
returns current/upcoming odds (deep history is a paid endpoint), and Transfermarkt
has no sanctioned API. So instead of a one-time backfill, these scripts **snapshot
what's live now and append it to a dated history**. Run them on a schedule and the
history builds itself — which is exactly what the as-of feature test and the blend
tuner consume.

---

## 1. Odds — `scripts/fetch_odds.py`

**What it does.** Pulls current soccer **h2h** match odds and **outright** winner
odds from The Odds API, averages across bookmakers, normalizes team names to our
spelling, then:
- appends match odds to `data/match_odds.csv` (de-duped on date+home+away), and
- refreshes `data/odds_champion.csv` (the outright market the forecast uses).

**Setup.**
1. Free key: <https://the-odds-api.com> (~500 requests/month free).
2. `export ODDS_API_KEY=xxxxx`
3. `python scripts/fetch_odds.py`

The active sport key changes around the event — check it with
`python scripts/fetch_odds.py --list-sports` and pass `--sport <key>`
(`--outrights-sport <key>` for the winner market).

**What it unlocks.** Once `data/match_odds.csv` has enough rows, the backtest
market benchmark switches on (`attach_match_odds`) and you can OOS-tune the blend
weight with `wc2026.optimize_blend_weight()` instead of the 0.30 prior. The
refreshed `odds_champion.csv` feeds STEP 7 of the forecast automatically.

**Limits.** Free tier = current odds only; you accumulate history by running it
regularly (a daily scheduled run through the tournament is ideal). Bulk past odds
need the paid `/historical` endpoint — the parser handles the same shape if you
have it.

---

## 2. Squad values — `scripts/snapshot_squad_values.py`

**What it does.** Appends the current `data/squad_values.csv` to
`data/squad_values_history.csv` (long: `team,date,value`), stamped with the date.
Over time this becomes the as-of history that `feature_importance.build_features(df,
mv_table=...)` joins without look-ahead.

**Usage.**
```
python scripts/snapshot_squad_values.py                  # snapshot, dated today
python scripts/snapshot_squad_values.py --date 2026-05-01 # backfill a known past value set
```

There is no shipped Transfermarkt scraper (no sanctioned free API, and scraping
violates their terms). If you run your own value source that returns JSON
(`{"Team": value}` in EUR millions), point the script at it:
`--api-url https://your-host/...`. Otherwise just keep updating
`data/squad_values.csv` by hand and snapshotting — the history accrues either way.

**What it unlocks.** Several dated snapshots → a real time series → the squad-value
feature gets a fair, leakage-free out-of-sample test (today's single snapshot
showed no signal, but that test is low-power; history fixes that).

---

## Run them on a schedule

A daily odds pull during the tournament is the high-value cadence (it captures
closing-ish prices per match). For squad values, monthly is plenty. You can wire
these to any scheduler (cron, Task Scheduler) — e.g. cron:

```
0 9 * * *  cd /path/to/world-cup-2026 && ODDS_API_KEY=xxx python3 scripts/fetch_odds.py
0 9 1 * *  cd /path/to/world-cup-2026 && python3 scripts/snapshot_squad_values.py
```
