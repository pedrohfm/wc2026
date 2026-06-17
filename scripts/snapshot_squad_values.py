"""
Squad-value accumulator -> builds the dated history the feature test needs.

WHY A SNAPSHOTTER, NOT A SCRAPER
--------------------------------
Transfermarkt has no official API and scraping it is fragile and against its
terms. The robust, legal way to get the AS-OF history that the squad-value
feature test requires is to snapshot the current values on a schedule: each run
appends data/squad_values.csv to data/squad_values_history.csv stamped with the
date. After a few months you have a genuine time series, and
feature_importance.build_features(df, mv_table=...) will as-of-join it with no
look-ahead. (One snapshot can't validate the feature; a history can.)

USAGE
-----
  python scripts/snapshot_squad_values.py          # snapshot current values, dated today
  python scripts/snapshot_squad_values.py --date 2026-06-01   # backfill a known past date

Optional refresh-from-endpoint (bring your own source that returns team->value):
  python scripts/snapshot_squad_values.py --api-url https://your-host/national-team-values
The endpoint must return JSON as {"Team": value, ...} or [{"team":..,"value":..}, ...]
in EUR millions, names matching wc2026_elo.csv. (No default endpoint is shipped,
because there is no sanctioned free Transfermarkt API.)
"""
import argparse
import datetime as dt
import json
import os
import urllib.request

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CURRENT = os.path.join(ROOT, "data", "squad_values.csv")
HISTORY = os.path.join(ROOT, "data", "squad_values_history.csv")


def refresh_from_api(url):
    req = urllib.request.Request(url, headers={"User-Agent": "wc2026-tmkt"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    if isinstance(data, dict):
        rows = [(t, v) for t, v in data.items()]
    else:
        rows = [(d["team"], d["value"]) for d in data]
    pd.DataFrame(rows, columns=["team", "value"]).to_csv(CURRENT, index=False)
    print(f"  refreshed {os.path.relpath(CURRENT, ROOT)} from endpoint ({len(rows)} teams)")


def snapshot(date):
    cur = pd.read_csv(CURRENT)[["team", "value"]].copy()
    cur["date"] = date
    cur = cur[["team", "date", "value"]]
    if os.path.exists(HISTORY):
        hist = pd.read_csv(HISTORY)
        comb = pd.concat([hist, cur], ignore_index=True).drop_duplicates(
            ["team", "date"], keep="last")
    else:
        comb = cur
    comb.sort_values(["date", "team"]).to_csv(HISTORY, index=False)
    n_dates = comb["date"].nunique()
    print(f"  snapshot dated {date} -> {os.path.relpath(HISTORY, ROOT)}")
    print(f"  history now: {len(comb)} rows across {n_dates} date(s), {comb['team'].nunique()} teams")
    if n_dates < 3:
        print("  [need several dated snapshots before the as-of squad-value feature test is meaningful]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--api-url", default=None)
    args = ap.parse_args()
    if args.api_url:
        refresh_from_api(args.api_url)
    snapshot(args.date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
