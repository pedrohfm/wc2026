"""
Automated odds pull (The Odds API) -> match odds + outright champion odds.

WHY AN ACCUMULATOR
------------------
The free tier of The Odds API returns CURRENT / upcoming odds, not deep history
(bulk history is a paid endpoint). So this script SNAPSHOTS what's live now and
APPENDS it to data/match_odds.csv (de-duplicated on date+home+away). Run it on a
schedule through the tournament and you accumulate the per-match closing-ish odds
that `optimize_blend_weight()` and the backtest market benchmark need — the
history builds itself. It also refreshes data/odds_champion.csv (the outright
market used by the forecast pipeline).

SETUP
-----
1. Get a free key at https://the-odds-api.com  (free tier ~500 req/month).
2. export ODDS_API_KEY=xxxxx        (or pass --key xxxxx)
3. python scripts/fetch_odds.py

The active sport key changes around the event; list them with
   python scripts/fetch_odds.py --list-sports
and pass e.g. --sport soccer_fifa_world_cup  (and --outrights-sport
soccer_fifa_world_cup_winner).

Network calls run on YOUR machine (this is a normal urllib client). Parsing is
unit-tested on mock payloads so the logic is verified without a live call.
"""
import argparse
import json
import os
import sys
import urllib.request

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MATCH_CSV = os.path.join(ROOT, "data", "match_odds.csv")
CHAMP_CSV = os.path.join(ROOT, "data", "odds_champion.csv")
API = "https://api.the-odds-api.com/v4"

# The Odds API spelling -> our (wc2026_elo.csv) spelling
NAME_MAP = {
    "Turkey": "Türkiye", "Ivory Coast": "Côte d'Ivoire", "Czech Republic": "Czechia",
    "Cape Verde": "Cabo Verde", "Cabo Verde Islands": "Cabo Verde", "Curacao": "Curaçao",
    "Bosnia and Herzegovina": "Bosnia & Herzegovina", "Bosnia & Herzegovina": "Bosnia & Herzegovina",
    "DR Congo": "DR Congo", "Congo DR": "DR Congo", "Democratic Republic of the Congo": "DR Congo",
    "South Korea": "South Korea", "Korea Republic": "South Korea", "United States": "United States",
    "USA": "United States", "IR Iran": "Iran", "Iran": "Iran",
}

def norm(name):
    return NAME_MAP.get(name, name)


# ---------------------------------------------------------------- parsers (pure)
def parse_h2h(events):
    """List of Odds-API events -> DataFrame[date,home,away,oh,od,oa] (avg across books)."""
    rows = []
    for ev in events:
        home_raw, away_raw = ev.get("home_team"), ev.get("away_team")
        if not home_raw or not away_raw:
            continue
        date = str(ev.get("commence_time", ""))[:10]
        oh, od, oa = [], [], []
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk.get("key") != "h2h":
                    continue
                for oc in mk.get("outcomes", []):
                    nm, price = oc.get("name"), oc.get("price")
                    if price is None:
                        continue
                    if nm == home_raw:
                        oh.append(price)
                    elif nm == away_raw:
                        oa.append(price)
                    elif str(nm).lower() == "draw":
                        od.append(price)
        if oh and od and oa:
            rows.append((date, norm(home_raw), norm(away_raw),
                         round(float(np.mean(oh)), 3), round(float(np.mean(od)), 3),
                         round(float(np.mean(oa)), 3)))
    return pd.DataFrame(rows, columns=["date", "home", "away", "oh", "od", "oa"])


def parse_outrights(events):
    """Odds-API outrights events -> {team: avg decimal odds}."""
    acc = {}
    for ev in events:
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk.get("key") != "outrights":
                    continue
                for oc in mk.get("outcomes", []):
                    p = oc.get("price")
                    if p and p > 1:
                        acc.setdefault(norm(oc.get("name")), []).append(p)
    return {t: round(float(np.mean(v)), 2) for t, v in acc.items()}


# ---------------------------------------------------------------- io helpers
def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "wc2026-odds"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def append_match_odds(new_df, path=MATCH_CSV):
    if new_df.empty:
        print("  no h2h events parsed."); return
    if os.path.exists(path):
        old = pd.read_csv(path)
        comb = pd.concat([old, new_df], ignore_index=True).drop_duplicates(
            ["date", "home", "away"], keep="last")
    else:
        comb = new_df
    comb.sort_values(["date", "home"]).to_csv(path, index=False)
    print(f"  match odds -> {os.path.relpath(path, ROOT)}  (now {len(comb)} rows; +{len(new_df)} this pull)")


def write_champion(odds, path=CHAMP_CSV):
    if not odds:
        print("  no outrights parsed."); return
    pd.DataFrame(sorted(odds.items(), key=lambda kv: kv[1]),
                 columns=["team", "odds"]).to_csv(path, index=False)
    print(f"  champion odds -> {os.path.relpath(path, ROOT)}  ({len(odds)} teams)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default=os.environ.get("ODDS_API_KEY"))
    ap.add_argument("--sport", default="soccer_fifa_world_cup")
    ap.add_argument("--outrights-sport", default="soccer_fifa_world_cup_winner")
    ap.add_argument("--regions", default="us,uk,eu")
    ap.add_argument("--list-sports", action="store_true")
    ap.add_argument("--mock", help="parse a local JSON file instead of calling the API (testing)")
    args = ap.parse_args()

    if args.mock:
        events = json.load(open(args.mock))
        append_match_odds(parse_h2h(events))
        print("  (mock outrights)"); print(parse_outrights(events))
        return 0
    if not args.key:
        print("No API key. Set ODDS_API_KEY or pass --key (free key: https://the-odds-api.com)."); return 1
    if args.list_sports:
        for s in _get(f"{API}/sports/?apiKey={args.key}"):
            if "soccer" in s["key"]:
                print(f"  {s['key']:40} {s['title']}  active={s.get('active')}")
        return 0
    try:
        h2h = _get(f"{API}/sports/{args.sport}/odds/?apiKey={args.key}"
                   f"&regions={args.regions}&markets=h2h&oddsFormat=decimal")
        append_match_odds(parse_h2h(h2h))
    except Exception as e:
        print(f"  [!] h2h pull failed: {e}")
    try:
        outs = _get(f"{API}/sports/{args.outrights_sport}/odds/?apiKey={args.key}"
                    f"&regions={args.regions}&markets=outrights&oddsFormat=decimal")
        write_champion(parse_outrights(outs))
    except Exception as e:
        print(f"  [!] outrights pull failed: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
