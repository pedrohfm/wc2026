"""
Build a self-contained interactive HTML dashboard from the forecast CSVs.

Scans outputs/forecast_*.csv (dated) + outputs/forecast_exante.csv, assembles a
time series, and writes outputs/dashboard.html — a single file with no external
dependencies (hand-built SVG), so it opens offline in any browser.

Run it after a forecast:
    python scripts/build_dashboard.py
then open outputs/dashboard.html.
"""
import glob
import json
import os
import re
import sys
import datetime as dt

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
try:
    from wc2026.blend import shin_probs            # Shin (1992) margin removal
except Exception:
    shin_probs = None
try:
    from wc2026.config import THIRD_OVERRIDE        # official R32 3rd-place slots
    from wc2026.structure import KO as _KO
    # slot match-number -> winning group it faces; lets the site map the official
    # override (match->3rd group) to the design's (winner-group->3rd group) form
    _SLOT_WINNER = {m: (hs[1] if hs[0] == "W" else as_[1])
                    for m, (rnd, hs, as_) in _KO.items()
                    if rnd == "R32" and "3" in (hs[0], as_[0])}
    THIRD_OVERRIDE_DESIGN = {_SLOT_WINNER[m]: g for m, g in (THIRD_OVERRIDE or {}).items()
                             if m in _SLOT_WINNER}
except Exception:
    THIRD_OVERRIDE_DESIGN = {}
OUT = os.path.join(ROOT, "outputs")
ODDS = os.path.join(ROOT, "data", "odds_champion.csv")
SCHED = os.path.join(ROOT, "data", "schedule.csv")
ELO_CSV = os.path.join(ROOT, "wc2026_elo.csv")
RESULTS = os.path.join(ROOT, "wc2026_results.xlsx")
KO_PENS = os.path.join(OUT, "ko_penalties.json")
ROUNDS = ["R32", "R16", "QF", "SF", "Final", "Win"]


def collect_ko():
    """Resolved knockout bracket + results for matches 73-104, advancing ACTUAL
       winners as results are entered. Each entry: {round, home, away, winner,
       played, hg, ag, pkwin, pens}. Returns {} if the engine/results aren't
       available. Powers the bracket and the match card (score + highlights)."""
    try:
        import wc2026 as E
        from wc2026.structure import KO as KODEF
        from wc2026.elo_dynamics import _deterministic_groups
        elo = E.load_elo(ELO_CSV)
        kg, kk = E.load_results(RESULTS)
        e = E.apply_known_results(elo, kg, kk, THIRD_OVERRIDE)
        res = _deterministic_groups(e, kg)
        if res is None:
            return {}
        winners, runners, thirds = res
        thirds.sort(key=lambda x: (x[2]["pts"], x[2]["gd"], x[2]["gf"], e[x[1]]), reverse=True)
        qual = {g: t for g, t, _ in thirds[:8]}
        slot_group = dict(THIRD_OVERRIDE) if THIRD_OVERRIDE else E.allocate_thirds(list(qual))
        slot_team = {m: qual.get(g) for m, g in slot_group.items()}
        pens = {}
        if os.path.exists(KO_PENS):
            try:
                pens = json.load(open(KO_PENS))
            except Exception:
                pens = {}
        mwin, mlose, out = {}, {}, {}
        for m in sorted(KODEF):
            rnd, hs, as_ = KODEF[m]
            def part(slot):
                typ, ref = slot
                return {"W": winners.get(ref), "RU": runners.get(ref), "3": slot_team.get(ref),
                        "WIN": mwin.get(ref), "LOSE": mlose.get(ref)}[typ]
            home, away = part(hs), part(as_)
            rec = {"round": rnd, "home": home, "away": away, "played": m in kk}
            if m in kk:
                ga, gb, pk = kk[m]
                if ga > gb: w = home
                elif gb > ga: w = away
                else: w = home if pk == "H" else (away if pk == "A" else
                          (home if e.get(home, 0) >= e.get(away, 0) else away))
                mwin[m] = w; mlose[m] = away if w == home else home
                rec.update(hg=int(ga), ag=int(gb), pkwin=pk, winner=w)
                if pk and str(m) in pens:
                    rec["pens"] = pens[str(m)]
            out[str(m)] = rec
        return out
    except Exception:
        return {}


def collect_schedule():
    """match number -> {date, et, utc, venue, city, state, country}.
       Returns {} if the schedule file is absent (the UI then just omits times)."""
    if not os.path.exists(SCHED):
        return {}
    df = pd.read_csv(SCHED)
    out = {}
    for _, r in df.iterrows():
        out[str(int(r["match"]))] = {
            "date": str(r["date"]), "et": str(r["et"]), "utc": str(r["utc"]),
            "venue": str(r["venue"]), "city": str(r["city"]),
            "state": str(r["state"]), "country": str(r["country"])}
    return out


def _load(path):
    df = pd.read_csv(path, index_col=0)
    df.index = df.index.astype(str)
    return df


def collect():
    snaps = []  # list of {date, label, teams:{team:{...}}}
    # ex-ante baseline first
    ex = os.path.join(OUT, "forecast_exante.csv")
    if os.path.exists(ex):
        snaps.append(("0000-00-00", "Ex-ante", _load(ex)))
    for p in sorted(glob.glob(os.path.join(OUT, "forecast_*.csv"))):
        m = re.search(r"forecast_(\d{4}-\d{2}-\d{2})\.csv$", os.path.basename(p))
        if not m:
            continue
        d = m.group(1)
        snaps.append((d, d[5:], _load(p)))   # label MM-DD
    return snaps


def market_probs():
    if not os.path.exists(ODDS):
        return {}
    df = pd.read_csv(ODDS)
    try:
        odds = {str(r["team"]): float(r["odds"]) for _, r in df.iterrows() if float(r["odds"]) > 1}
    except Exception:
        return {}
    if not odds:
        return {}
    if shin_probs is not None:                       # Shin (1992) margin removal
        teams = list(odds); ps = shin_probs([odds[t] for t in teams])
        return {t: round(ps[i] * 100, 2) for i, t in enumerate(teams)}
    imp = {t: 1.0 / o for t, o in odds.items()}; s = sum(imp.values())   # proportional fallback
    return {t: round(p / s * 100, 2) for t, p in imp.items()} if s else {}


def _num(v):
    try:
        f = float(v)
        return f if f == f else ""   # NaN -> ""
    except (ValueError, TypeError):
        return ""


def collect_group():
    """Latest group-stage match probabilities + per-match home-prob history.
       Returns None if no group_matches_*.csv exist (tile then auto-hides)."""
    files = sorted(glob.glob(os.path.join(OUT, "group_matches_*.csv")))
    if not files:
        return None
    dates, hist = [], {}
    for f in files:
        m = re.search(r"group_matches_(\d{4}-\d{2}-\d{2})\.csv$", os.path.basename(f))
        if not m:
            continue
        dates.append(m.group(1)[5:])
        d = pd.read_csv(f)
        for _, r in d.iterrows():
            hist.setdefault(int(r["match"]), []).append(_num(r["m_home"]) or 0)
    latest = pd.read_csv(files[-1])
    rows = []
    for _, r in latest.iterrows():
        rows.append({"match": int(r["match"]), "group": str(r["group"]),
                     "home": str(r["home"]), "away": str(r["away"]),
                     "m_home": _num(r["m_home"]), "m_draw": _num(r["m_draw"]), "m_away": _num(r["m_away"]),
                     "mkt_home": _num(r["mkt_home"]), "mkt_draw": _num(r["mkt_draw"]), "mkt_away": _num(r["mkt_away"]),
                     "actual": ("" if pd.isna(r["actual"]) else str(r["actual"])),
                     "score": ("" if pd.isna(r["score"]) else str(r["score"])),
                     "played": int(r["played"])})
    return {"dates": dates, "rows": rows, "hist": {str(k): v for k, v in hist.items()}}


def build_data():
    snaps = collect()
    if not snaps:
        raise SystemExit("No forecast CSVs found in outputs/. Run build_and_forecast.py first.")
    labels = [s[1] for s in snaps]
    dates = [s[0] for s in snaps]
    teams = sorted(snaps[-1][2].index)
    # static info from latest
    latest = snaps[-1][2]
    info = {t: {"Elo": int(latest.loc[t, "Elo"]) if t in latest.index else None,
                "Conf": str(latest.loc[t, "Conf"]) if t in latest.index else "?",
                "Grp": str(latest.loc[t, "Grp"]) if t in latest.index else "?"} for t in teams}
    # series: team -> round -> [values aligned to snaps]
    series = {}
    for t in teams:
        series[t] = {r: [] for r in ROUNDS}
        for _, _, df in snaps:
            for r in ROUNDS:
                v = float(df.loc[t, r]) if (t in df.index and r in df.columns) else None
                series[t][r].append(v)
    return {
        "labels": labels, "dates": dates, "rounds": ROUNDS,
        "teams": teams, "info": info, "series": series,
        "market": market_probs(),
        "gm": collect_group(),
        "sched": collect_schedule(),
        "ko": collect_ko(),
        "thirdOverride": THIRD_OVERRIDE_DESIGN,
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def main():
    data = build_data()
    # PRIMARY for the live site: the Claude-Design pages read window.WC_DATA from
    # this file, so it is regenerated with fresh data every run.
    with open(os.path.join(OUT, "WCData.js"), "w") as f:
        f.write("window.WC_DATA = " + json.dumps(data) + ";\n")
    print(f"  WCData.js -> outputs/WCData.js  ({len(data['teams'])} teams, "
          f"{len(data['labels'])} snapshots, generated {data['generated']})")

    # Legacy self-contained dashboard (kept as an offline fallback; not deployed
    # when the new design is present).
    html = TEMPLATE.replace("/*DATA*/", json.dumps(data))
    for name in ("dashboard.html", "index.html"):
        with open(os.path.join(OUT, name), "w") as f:
            f.write(html)
    with open(os.path.join(OUT, "about.html"), "w") as f:
        f.write(build_about(data))
    print("  legacy fallback -> outputs/dashboard.html, about.html")


# ---------------------------------------------------------------------------
TEMPLATE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>World Cup 2026 — Forecast Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#f4f6f9; --panel:#ffffff; --panel2:#f7f9fc; --ink:#1f2a37; --mut:#64748b;
  --line:#e6e9ef; --accent:#2563eb; --good:#15803d; --bad:#dc2626; --chip:#eef2f7;
}
*{box-sizing:border-box} html,body{margin:0}
body{background:var(--bg);color:var(--ink);
  font:14px/1.5 "Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:26px 22px 40px}
.sub{color:var(--mut);font-size:12.5px;margin-top:3px}
/* masthead */
.mast{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;
  border-bottom:3px solid var(--ink);padding-bottom:14px}
.brand .eyebrow{font-size:11px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:var(--accent)}
.brand h1{font-size:40px;line-height:.98;font-weight:800;letter-spacing:-.025em;margin:7px 0 0;color:var(--ink)}
.tabs{display:flex;gap:6px}
.tabs a{font-size:12.5px;font-weight:700;letter-spacing:.02em;text-transform:uppercase;text-decoration:none;
  color:var(--mut);padding:8px 15px;border-radius:8px;white-space:nowrap}
.tabs a.on{color:#fff;background:var(--ink)}
.tabs a:not(.on):hover{background:var(--chip)}
.sec{font-size:13px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--ink)}
.sec .sub{text-transform:none;letter-spacing:normal;font-weight:500}
@media(max-width:600px){.brand h1{font-size:30px}.mast{flex-direction:column;align-items:flex-start;gap:12px}}
.row{display:flex;gap:16px;flex-wrap:wrap}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;
  box-shadow:0 1px 2px rgba(16,24,40,.04),0 1px 3px rgba(16,24,40,.06);margin-top:16px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:13px 15px;
  box-shadow:0 1px 2px rgba(16,24,40,.04)}
.kpi .l{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.7px}
.kpi .v{font-size:21px;font-weight:800;letter-spacing:-.01em;margin-top:5px}
.kpi .d{font-size:12px;margin-top:2px}
.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:2px 0 10px}
.controls .seg{display:flex;background:var(--panel2);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.controls .seg button{background:none;border:0;color:var(--mut);padding:6px 11px;cursor:pointer;font-size:12.5px}
.controls .seg button.on{background:var(--accent);color:#fff}
label.lbl{color:var(--mut);font-size:12px;margin-left:6px}
select,input[type=search]{background:var(--panel2);border:1px solid var(--line);color:var(--ink);
  border-radius:9px;padding:6px 9px;font-size:12.5px}
.chartwrap{position:relative}
svg{display:block;width:100%}
.tip{position:absolute;pointer-events:none;background:#fff;border:1px solid var(--line);color:var(--ink);
  border-radius:8px;padding:6px 9px;font-size:12px;opacity:0;transition:opacity .1s;white-space:nowrap;z-index:5;
  box-shadow:0 4px 14px rgba(16,24,40,.12)}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}
.grid-2>*{min-width:0}
.kpis,.grid-2,.card{width:100%}
@media(max-width:860px){.grid-2{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,1fr)}}
@media(max-width:600px){
 .wrap{padding:14px}
 h1{font-size:20px}
 nav{flex-wrap:wrap;gap:10px}
 .kpis{grid-template-columns:repeat(2,1fr);gap:8px}
 .kpi{padding:10px 12px}.kpi .v{font-size:17px}
 .controls{gap:6px}
 .controls .seg button{padding:6px 9px;font-size:12px}
 .card{padding:13px}
 table{font-size:12px}.tbar{width:64px}th,td{padding:6px 6px}
}
.mover{display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px dashed var(--line)}
.mover:last-child{border-bottom:0}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:8px;vertical-align:middle}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 9px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.5px;cursor:pointer;position:sticky;top:0;background:var(--panel);z-index:2}
td.team,th.team{text-align:left}
.cellv{display:flex;flex-direction:column;align-items:flex-end;gap:3px;min-width:54px}
.cellv .num{font-size:11.5px;color:var(--ink)}
.cellv .bt{height:4px;width:100%;background:#eef2f7;border-radius:2px;position:relative;overflow:hidden}
.cellv .bt > i{position:absolute;left:0;top:0;bottom:0;border-radius:2px;opacity:.9}
.flag{width:20px;height:15px;border-radius:2px;margin-right:7px;vertical-align:-2px;object-fit:cover;box-shadow:0 0 0 1px rgba(0,0,0,.07)}
.chip{font-size:10.5px;padding:2px 9px;border-radius:20px;font-weight:500}
.up{color:var(--good)} .down{color:var(--bad)} .flat{color:var(--mut)}
.tablewrap{max-height:560px;overflow:auto;border-radius:10px}
.legend{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
.legend .it{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--mut);cursor:pointer;padding:2px 6px;border-radius:7px}
.legend .it.dim{opacity:.35}
.foot{color:var(--mut);font-size:11.5px;margin-top:18px;text-align:center}
.mkt{display:flex;align-items:center;gap:10px;margin:7px 0}
.mkt .nm{width:110px;font-size:12.5px;flex:none}
.mcol{flex:1;min-width:0;display:flex;flex-direction:column;gap:3px}
.mrow{display:flex;align-items:center;gap:6px}
.mrow > i{height:9px;border-radius:3px;display:block;min-width:2px}
.mrow > span{font-size:11px;color:var(--mut);width:34px;flex:none;text-align:right}
/* group-stage tile (fully responsive: stacked rows, full-width bars) */
.gmkey{display:inline-block;width:10px;height:10px;border-radius:2px;vertical-align:middle;margin:0 3px 0 6px}
.gmlegend{display:flex;flex-wrap:wrap;gap:6px 4px;font-size:12px;color:var(--mut);margin:2px 0 10px}
.gmgrp{font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--ink);margin:16px 0 6px}
.gmrow{padding:9px 0;border-bottom:1px solid var(--line)}
.gmrow:last-child{border-bottom:0}
.gmhead{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.gmhead .t{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px;display:flex;align-items:center;gap:2px}
.gmhead .t .vs{color:var(--mut);font-size:11px;margin:0 4px;flex:none}
.gmhead .r{flex:none;display:flex;align-items:center;gap:8px}
.gmline{display:flex;align-items:center;gap:8px;margin-top:4px}
.gmline .lab{width:54px;flex:none;font-size:10px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut)}
.gmbar2{flex:1;min-width:0;display:flex;height:13px;border-radius:4px;overflow:hidden;background:#eef2f7}
.gmbar2 > span{display:block;height:100%}
.gmpct{flex:none;width:92px;text-align:right;font-size:11px;color:var(--mut);font-variant-numeric:tabular-nums}
.gmchip{font-size:11px;font-weight:600;padding:2px 8px;border-radius:6px;white-space:nowrap}
.gmspark{flex:none}
@media(max-width:600px){.gmpct{width:78px}.gmline .lab{width:46px}.gmspark{display:none}}
</style></head>
<body><div class="wrap">
  <div class="mast">
    <div class="brand">
      <div class="eyebrow">FIFA World Cup 2026 · Forecast model</div>
      <h1>Forecast&nbsp;Tracker</h1>
    </div>
    <div style="text-align:right">
      <div class="tabs"><a href="index.html" class="on">Tracker</a><a href="about.html">Methodology</a></div>
      <div class="sub" id="gen" style="margin-top:9px"></div>
    </div>
  </div>
  <div class="sub" id="sub" style="margin:9px 0 2px"></div>

  <div class="kpis" id="kpis"></div>

  <div class="card">
    <div class="controls">
      <span class="sec">Progression</span>
      <div class="seg" id="metricSeg"></div>
      <div class="seg" id="modeSeg">
        <button data-mode="prob" class="on">Probability</button>
        <button data-mode="rank">Rank</button>
      </div>
      <label class="lbl">Show</label>
      <select id="topN"><option value="8">Top 8</option><option value="16">Top 16</option>
        <option value="32">Top 32</option></select>
    </div>
    <div class="chartwrap"><svg id="chart" viewBox="0 0 1000 460" preserveAspectRatio="xMidYMid meet"></svg>
      <div class="tip" id="tip"></div></div>
    <div class="legend" id="legend"></div>
  </div>

  <div class="card">
    <div class="sec" style="margin-bottom:10px">Standings — latest
      <span class="sub" id="latlbl"></span></div>
    <div class="controls"><input type="search" id="search" placeholder="filter team…" style="flex:1">
      <span class="lbl">Δ vs ex-ante</span></div>
    <div class="tablewrap"><table id="tbl"></table></div>
  </div>

  <div class="grid-2">
    <div class="card"><div class="sec" style="margin-bottom:10px">Biggest movers
      <span class="sub">(champion %, vs ex-ante)</span></div>
      <div id="movers"></div></div>
    <div class="card"><div class="sec" style="margin-bottom:10px">Model vs market
      <span class="sub">champion %</span></div>
      <div id="market"></div></div>
  </div>

  <div class="card" id="gmcard" style="display:none;margin-top:16px">
    <div class="sec" style="margin-bottom:10px">Group-stage matches
      <span class="sub">model &amp; market win / draw / loss, with results as they come in</span></div>
    <div class="controls"><label class="lbl">Group</label><select id="gmsel"></select></div>
    <div class="gmlegend">
      <span><b>Model</b>&nbsp; <span class="gmkey" style="background:#2563eb"></span>home
        <span class="gmkey" style="background:#94a3b8"></span>draw
        <span class="gmkey" style="background:#d97706"></span>away</span>
      <span style="margin-left:14px"><b>Market</b>&nbsp; <span class="gmkey" style="background:#0d9488"></span>home
        <span class="gmkey" style="background:#cbd5e1"></span>draw
        <span class="gmkey" style="background:#db2777"></span>away</span>
    </div>
    <div id="gmlist"></div>
  </div>

  <div class="foot">
    © 2026 Pedro Henrique Figueiredo Magalhães · Independent research project, not affiliated with or endorsed by FIFA.<br>
    Probabilities are Monte-Carlo estimates for informational and educational purposes — not betting advice.
    Small day-to-day wiggles are simulation noise. &nbsp;·&nbsp; <a href="about.html" style="color:var(--accent)">Methodology &amp; data sources →</a>
  </div>
</div>

<script>
const DATA = /*DATA*/;
const PAL = ["#2563eb","#e8590c","#16a34a","#9333ea","#0891b2","#dc2626","#ca8a04","#db2777",
             "#4d7c0f","#0f766e","#7c3aed","#b45309","#1d4ed8","#be123c","#15803d","#6d28d9",
             "#0e7490","#a16207","#9d174d","#3f6212","#1e40af","#92400e","#5b21b6","#155e75"];
const CONF = {UEFA:"#2563eb",CONMEBOL:"#d97706",CONCACAF:"#dc2626",CAF:"#16a34a",AFC:"#ea580c",OFC:"#0d9488"};
const CONF2 = {UEFA:["#e6effb","#1d4ed8"],CONMEBOL:["#fdf0d9","#b45309"],CONCACAF:["#fdeaea","#b91c1c"],
               CAF:["#e7f6ec","#15803d"],AFC:["#feeede","#c2410c"],OFC:["#e3f5f3","#0f766e"]};
const ISO = {Mexico:"MX",Canada:"CA","United States":"US",Haiti:"HT","Curaçao":"CW",Panama:"PA",
 Brazil:"BR",Paraguay:"PY",Ecuador:"EC",Uruguay:"UY",Colombia:"CO",Argentina:"AR","South Korea":"KR",
 Qatar:"QA",Australia:"AU",Japan:"JP",Iran:"IR","Saudi Arabia":"SA",Iraq:"IQ",Jordan:"JO",Uzbekistan:"UZ",
 "South Africa":"ZA",Morocco:"MA","Côte d'Ivoire":"CI",Tunisia:"TN",Egypt:"EG","Cabo Verde":"CV",
 Senegal:"SN",Algeria:"DZ","DR Congo":"CD",Ghana:"GH",Czechia:"CZ",Switzerland:"CH",
 "Bosnia & Herzegovina":"BA","Türkiye":"TR",Germany:"DE",Netherlands:"NL",Sweden:"SE",Belgium:"BE",
 Spain:"ES",France:"FR",Norway:"NO",Austria:"AT",Portugal:"PT",Croatia:"HR","New Zealand":"NZ"};
// Flag IMAGES (cross-platform: emoji flags don't render on Windows). flagcdn
// supports subdivisions (gb-eng, gb-sct). onerror removes a broken img so it
// degrades to just the team name (e.g. offline).
const FLAGC = Object.assign({}, ISO, {England:"gb-eng", Scotland:"gb-sct"});
function flagImg(t){ const c=FLAGC[t]; if(!c) return "";
  const lc=c.toLowerCase();
  return `<img class="flag" src="https://flagcdn.com/40x30/${lc}.png" srcset="https://flagcdn.com/80x60/${lc}.png 2x" width="20" height="15" loading="lazy" alt="" onerror="this.remove()">`; }
function nm(t){ return flagImg(t)+t; }
const R = DATA.rounds, L = DATA.labels, N = L.length;
const state = {metric:"Win", mode:"prob", topN:8, sort:"Win", dir:1, hi:null, search:""};

const latest = t => DATA.series[t][state.metric][N-1] ?? 0;
const exante = (t,m=state.metric) => DATA.series[t][m][0] ?? 0;
function rankedTeams(){ return [...DATA.teams].sort((a,b)=> (latest(b)-latest(a))); }
function topTeams(){ return rankedTeams().slice(0, state.topN); }
function colorFor(teams){ const m={}; teams.forEach((t,i)=> m[t]=PAL[i%PAL.length]); return m; }

/* ---------- KPIs ---------- */
function kpis(){
  const r = rankedTeams(), fav=r[0];
  const mk = DATA.market||{}; const mfav = Object.keys(mk).sort((a,b)=>mk[b]-mk[a])[0];
  // biggest riser by Win since exante
  let best=null,bestd=-1e9,worst=null,worstd=1e9;
  DATA.teams.forEach(t=>{const d=(DATA.series[t].Win[N-1]??0)-(DATA.series[t].Win[0]??0);
    if(d>bestd){bestd=d;best=t} if(d<worstd){worstd=d;worst=t}});
  const cards=[
    ["Model favorite", fav, `${latest(fav).toFixed(1)}% to win`],
    ["Market favorite", mfav||"—", mfav?`${mk[mfav].toFixed(1)}% implied`:"add odds"],
    ["Top riser", best, `<span class="up">▲ ${bestd>=0?'+':''}${bestd.toFixed(1)} pp</span>`],
    ["Top faller", worst, `<span class="down">▼ ${worstd.toFixed(1)} pp</span>`],
  ];
  document.getElementById("kpis").innerHTML = cards.map(c=>
    `<div class="kpi"><div class="l">${c[0]}</div><div class="v">${nm(c[1])}</div><div class="d">${c[2]}</div></div>`).join("");
}

/* ---------- line / bump chart ---------- */
function draw(){
  const svg=document.getElementById("chart"); const W=1000,H=460;
  const padL=46,padR=120,padT=18,padB=34; const iw=W-padL-padR, ih=H-padT-padB;
  const teams=topTeams(); const col=colorFor(teams);
  const x = i => padL + (N===1? iw/2 : iw*i/(N-1));
  let y, ticks;
  if(state.mode==="prob"){
    let max=0; teams.forEach(t=>DATA.series[t][state.metric].forEach(v=>{if(v>max)max=v}));
    max=Math.max(5,Math.ceil(max/10)*10); y=v=> padT+ih-ih*(v/max);
    ticks=[]; for(let g=0; g<=max; g+= max<=20?5:(max<=50?10:20)) ticks.push(g);
  } else {
    const ny=Math.min(state.topN, teams.length);
    y=rk=> padT+ih*((rk-1)/(Math.max(1,ny-1))); ticks=null;
  }
  // rank per snapshot (over the displayed set)
  const rankAt = (t,i) => { const arr=teams.map(tt=>[tt, DATA.series[tt][state.metric][i]??-1])
        .sort((a,b)=>b[1]-a[1]); return arr.findIndex(e=>e[0]===t)+1; };

  let s=`<defs></defs>`;
  // gridlines
  if(ticks){ ticks.forEach(g=>{const yy=y(g);
    s+=`<line x1="${padL}" y1="${yy}" x2="${W-padR}" y2="${yy}" stroke="var(--line)"/>`;
    s+=`<text x="${padL-8}" y="${yy+4}" fill="var(--mut)" font-size="11" text-anchor="end">${g}%</text>`;}); }
  else { for(let rk=1;rk<=Math.min(state.topN,teams.length);rk++){const yy=y(rk);
    s+=`<line x1="${padL}" y1="${yy}" x2="${W-padR}" y2="${yy}" stroke="var(--line)"/>`;
    s+=`<text x="${padL-8}" y="${yy+4}" fill="var(--mut)" font-size="11" text-anchor="end">#${rk}</text>`;} }
  // x labels
  L.forEach((lb,i)=>{ s+=`<text x="${x(i)}" y="${H-12}" fill="var(--mut)" font-size="11" text-anchor="middle">${lb}</text>`; });

  // lines
  teams.forEach(t=>{
    const dim = state.hi && state.hi!==t;
    const pts = L.map((_,i)=>{ const v = state.mode==="prob" ? (DATA.series[t][state.metric][i]??null) : rankAt(t,i);
        return v==null? null : [x(i), y(v)]; });
    const path = pts.filter(Boolean).map((p,i)=> (i?"L":"M")+p[0].toFixed(1)+" "+p[1].toFixed(1)).join(" ");
    s+=`<path d="${path}" fill="none" stroke="${col[t]}" stroke-width="${state.hi===t?3.4:2}" opacity="${dim?.18:1}"
         stroke-linejoin="round" stroke-linecap="round"/>`;
    pts.forEach((p,i)=>{ if(!p)return;
      s+=`<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="${state.hi===t?3.6:2.6}" fill="${col[t]}"
           opacity="${dim?.18:1}" data-t="${t}" data-i="${i}" class="pt"/>`; });
    // right label
    const last=pts.filter(Boolean).slice(-1)[0];
    if(last){ s+=`<text x="${last[0]+8}" y="${last[1]+4}" fill="${col[t]}" font-size="11.5"
         opacity="${dim?.3:1}" font-weight="600">${t}</text>`; }
  });
  svg.innerHTML=s;
  // hover: show tooltip only (no redraw, so handlers stay bound and highlight never sticks)
  const tip=document.getElementById("tip");
  svg.querySelectorAll(".pt").forEach(c=>{
    c.addEventListener("mouseenter",()=>{ const t=c.getAttribute("data-t"),i=+c.getAttribute("data-i");
      const v=DATA.series[t][state.metric][i];
      tip.innerHTML=`<b>${t}</b> · ${L[i]}<br>${state.metric}: ${v==null?"—":v.toFixed(1)+"%"}`;
      const r=svg.getBoundingClientRect(); const sx=r.width/1000, sy=r.height/460;
      tip.style.left=(+c.getAttribute("cx")*sx+10)+"px"; tip.style.top=(+c.getAttribute("cy")*sy-6)+"px";
      tip.style.opacity=1; });
    c.addEventListener("mouseleave",()=>{ tip.style.opacity=0; });
  });
}

/* ---------- legend ---------- */
function legend(){
  const teams=topTeams(), col=colorFor(teams);
  document.getElementById("legend").innerHTML = teams.map(t=>
    `<div class="it ${state.hi&&state.hi!==t?'dim':''}" data-t="${t}">
       <span class="dot" style="background:${col[t]}"></span>${nm(t)} <b style="color:var(--ink)">${latest(t).toFixed(1)}%</b></div>`).join("");
  document.querySelectorAll("#legend .it").forEach(el=>{
    el.onmouseenter=()=>{state.hi=el.getAttribute("data-t");draw()};
    el.onmouseleave=()=>{state.hi=null;draw()};});
}

/* ---------- movers ---------- */
function movers(){
  const arr=DATA.teams.map(t=>({t, d:(DATA.series[t].Win[N-1]??0)-(DATA.series[t].Win[0]??0),
        now:DATA.series[t].Win[N-1]??0})).filter(o=>Math.abs(o.d)>=0.05);
  arr.sort((a,b)=>b.d-a.d); const top=arr.slice(0,5), bot=arr.slice(-5).reverse();
  const row=o=>`<div class="mover"><span>${nm(o.t)}</span>
     <span><span class="${o.d>0?'up':(o.d<0?'down':'flat')}">${o.d>0?'▲':'▼'} ${o.d>0?'+':''}${o.d.toFixed(1)}</span>
     <span class="sub" style="margin-left:8px">${o.now.toFixed(1)}%</span></span></div>`;
  document.getElementById("movers").innerHTML =
    `<div class="sub" style="margin-bottom:4px">Risers</div>${top.map(row).join("")}
     <div class="sub" style="margin:8px 0 4px">Fallers</div>${bot.map(row).join("")}`;
}

/* ---------- market ---------- */
const MODEL_C="#5b8cff", MARKET_C="#f59e0b";
function market(){
  const mk=DATA.market||{}; const el=document.getElementById("market");
  if(!Object.keys(mk).length){ el.innerHTML=`<div class="sub">No odds yet. Add data/odds_champion.csv and rerun.</div>`; return; }
  const teams=rankedTeams().slice(0,10);
  const mx=Math.max(...teams.map(t=>Math.max(latest(t)||0, mk[t]||0)))||1;
  el.innerHTML=teams.map(t=>{const m=mk[t]||0,p=latest(t)||0;
    return `<div class="mkt"><div class="nm">${nm(t)}</div><div class="mcol">
       <div class="mrow"><i style="width:${(p/mx*100).toFixed(1)}%;background:${MODEL_C}"></i><span>${p.toFixed(1)}</span></div>
       <div class="mrow"><i style="width:${(m/mx*100).toFixed(1)}%;background:${MARKET_C}"></i><span>${m.toFixed(1)}</span></div>
     </div></div>`;}).join("")
    +`<div style="display:flex;gap:16px;margin-top:8px;font-size:12px;color:var(--mut)">
        <span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${MODEL_C};vertical-align:middle;margin-right:5px"></span>model</span>
        <span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${MARKET_C};vertical-align:middle;margin-right:5px"></span>market</span></div>`;
}

/* ---------- table ---------- */
function table(){
  const q=state.search.toLowerCase();
  let rows=DATA.teams.filter(t=>t.toLowerCase().includes(q));
  rows.sort((a,b)=>{ const get=t=> state.sort==="Elo"?DATA.info[t].Elo:(DATA.series[t][state.sort][N-1]??0);
                     return (get(b)-get(a))*(state.dir); });   // dir=1 -> descending
  const head=`<tr><th class="team" data-c="team">Team</th><th data-c="Conf">Conf</th><th data-c="Elo">Elo</th>`+
    R.map(r=>`<th data-c="${r}">${r}</th>`).join("")+`<th data-c="dW">Δ Win</th></tr>`;
  const mx={}; R.forEach(r=>mx[r]=Math.max(...DATA.teams.map(t=>DATA.series[t][r][N-1]??0)));
  const body=rows.map(t=>{
    const inf=DATA.info[t]; const c=CONF[inf.Conf]||"#94a3b8"; const ch=CONF2[inf.Conf]||["#eef2f7","#64748b"];
    const cells=R.map(r=>{const v=DATA.series[t][r][N-1]??0; const w=mx[r]?Math.max(3,v/mx[r]*100):0;
      return `<td><div class="cellv"><span class="num">${v.toFixed(1)}</span><span class="bt"><i style="width:${w}%;background:${c}"></i></span></div></td>`;}).join("");
    const dW=(DATA.series[t].Win[N-1]??0)-(DATA.series[t].Win[0]??0);
    const dcls=dW>0.05?'up':(dW<-0.05?'down':'flat'); const arr=dW>0.05?'▲':(dW<-0.05?'▼':'·');
    return `<tr><td class="team">${nm(t)}</td><td><span class="chip" style="background:${ch[0]};color:${ch[1]}">${inf.Conf}</span></td>
      <td>${inf.Elo??''}</td>${cells}<td class="${dcls}">${arr} ${dW>0?'+':''}${dW.toFixed(1)}</td></tr>`;}).join("");
  const tbl=document.getElementById("tbl"); tbl.innerHTML=head+body;
  tbl.querySelectorAll("th").forEach(th=>th.onclick=()=>{const c=th.getAttribute("data-c");
    if(c==="team"||c==="dW")return; if(state.sort===c)state.dir*=-1; else {state.sort=c;state.dir=1;} table();});
}

/* ---------- group-stage matches ---------- */
const MOD={h:"#2563eb",d:"#94a3b8",a:"#d97706"};   // model colours
const MKT={h:"#0d9488",d:"#cbd5e1",a:"#db2777"};   // market colours (distinct set)
function gspark(arr){
  if(!arr||arr.length<2) return "";
  const w=62,h=16; const x=i=>i/(arr.length-1)*w; const y=v=>h-2-(Math.max(0,Math.min(100,v))/100)*(h-4);
  const d=arr.map((v,i)=>(i?"L":"M")+x(i).toFixed(1)+" "+y(v).toFixed(1)).join(" ");
  return `<svg class="gmspark" width="${w}" height="${h}" style="vertical-align:middle" aria-hidden="true"><path d="${d}" fill="none" stroke="${MOD.h}" stroke-width="1.5"/></svg>`;
}
function gmBar(lab, h, dd, a, C){
  return `<div class="gmline"><span class="lab">${lab}</span>
    <div class="gmbar2"><span style="width:${h}%;background:${C.h}"></span><span style="width:${dd}%;background:${C.d}"></span><span style="width:${a}%;background:${C.a}"></span></div>
    <span class="gmpct">${(+h).toFixed(0)} / ${(+dd).toFixed(0)} / ${(+a).toFixed(0)}</span></div>`;
}
function paintGroups(g){
  const rows=DATA.gm.rows.filter(r=>g==="ALL"||r.group===g);
  const byG={}; rows.forEach(r=>{(byG[r.group]=byG[r.group]||[]).push(r);});
  let html="";
  Object.keys(byG).sort().forEach(grp=>{
    html+=`<div class="gmgrp">Group ${grp}</div>`;
    byG[grp].forEach(r=>{
      const hasM = r.mkt_home!=="" && r.mkt_home!=null;
      let right;
      if(r.played){ const oc=r.actual, col=oc==="H"?MOD.h:(oc==="A"?MOD.a:MOD.d);
        right=`<span class="gmchip" style="background:${col}22;color:${col}">FT ${r.score}</span>`; }
      else right=gspark(DATA.gm.hist[String(r.match)]);
      html+=`<div class="gmrow">
        <div class="gmhead"><div class="t">${nm(r.home)}<span class="vs">v</span>${nm(r.away)}</div><div class="r">${right}</div></div>
        ${gmBar("Model", r.m_home, r.m_draw, r.m_away, MOD)}
        ${hasM ? gmBar("Market", r.mkt_home, r.mkt_draw, r.mkt_away, MKT) : ""}</div>`;
    });
  });
  document.getElementById("gmlist").innerHTML=html;
}
function renderGroups(){
  if(!DATA.gm || !DATA.gm.rows || !DATA.gm.rows.length) return;   // tile stays hidden
  document.getElementById("gmcard").style.display="";
  const sel=document.getElementById("gmsel");
  const groups=[...new Set(DATA.gm.rows.map(r=>r.group))].sort();
  sel.innerHTML=`<option value="ALL">All groups</option>`+groups.map(g=>`<option value="${g}">Group ${g}</option>`).join("");
  sel.onchange=()=>paintGroups(sel.value);
  paintGroups("ALL");
}

/* ---------- controls ---------- */
function metricSeg(){
  document.getElementById("metricSeg").innerHTML = R.map(r=>
    `<button data-m="${r}" class="${r===state.metric?'on':''}">${r}</button>`).join("");
  document.querySelectorAll("#metricSeg button").forEach(b=>b.onclick=()=>{
    state.metric=b.getAttribute("data-m"); metricSeg(); draw(); legend(); });
}
document.querySelectorAll("#modeSeg button").forEach(b=>b.onclick=()=>{
  document.querySelectorAll("#modeSeg button").forEach(x=>x.classList.remove("on"));
  b.classList.add("on"); state.mode=b.getAttribute("data-mode"); draw(); });
document.getElementById("topN").onchange=e=>{state.topN=+e.target.value; draw(); legend();};
document.getElementById("search").oninput=e=>{state.search=e.target.value; table();};

/* ---------- init ---------- */
document.getElementById("sub").textContent =
  `${DATA.teams.length} teams · ${N} snapshots (${L[0]} → ${L[N-1]})`;
document.getElementById("gen").textContent = "generated "+DATA.generated;
document.getElementById("latlbl").textContent = "· "+L[N-1];
metricSeg(); kpis(); draw(); legend(); movers(); market(); table(); renderGroups();
window.addEventListener("resize", ()=>{});
</script>
</body></html>
"""

def _load_json(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def build_about(data):
    import math
    gp = _load_json(os.path.join(ROOT, "params", "goals_params.json"),
                    {"mu": 0.20, "gamma": 0.73, "home_elo": 112, "rho": -0.046})
    mu, gamma, home_elo, rho = gp.get("mu", 0.20), gp.get("gamma", 0.73), gp.get("home_elo", 112), gp.get("rho", -0.046)
    scale = 400.0 * math.log(10.0) / (2.0 * gamma) if gamma else 0
    sk = _load_json(os.path.join(ROOT, "params", "skill_cache.json"), {}).get("data", {})
    rows = sk.get("rows", {"Coin (1/3 each)": [1.099, 0.667, 0.479, 0.478],
                           "Base rate (no skill)": [1.050, 0.633, 0.457, 0.478],
                           "Elo-logistic": [0.880, 0.520, 0.346, 0.597],
                           "Model (Elo + DC-MLE)": [0.880, 0.518, 0.346, 0.595]})
    n_test = sk.get("n_test", 4572); n_train = sk.get("n_train", 18703); split = sk.get("split", "2022-01-01")
    sc_coin = sk.get("skill_coin_ll", 0.199); sc_base = sk.get("skill_base_ll", 0.162)
    r2 = sk.get("pseudo_r2", 0.162); ece = sk.get("ece", 0.025)
    skrows = "".join(
        f"<tr><td class='l'>{m}</td><td>{v[0]:.4f}</td><td>{v[1]:.4f}</td><td>{v[2]:.4f}</td><td>{v[3]*100:.0f}%</td></tr>"
        for m, v in rows.items())

    css = """
:root{--bg:#f4f6f9;--panel:#ffffff;--ink:#1f2a37;--mut:#64748b;--line:#e6e9ef;--accent:#2563eb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.7 "Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:800px;margin:0 auto;padding:26px 22px 48px}
nav{display:flex;gap:8px;align-items:center;border-bottom:3px solid var(--ink);padding-bottom:13px;margin-bottom:20px}
nav .bk{font-weight:800;letter-spacing:-.01em;margin-right:auto;font-size:15px}
nav a{text-decoration:none;font-size:12.5px;font-weight:700;text-transform:uppercase;letter-spacing:.02em;color:var(--mut);padding:8px 14px;border-radius:8px}
nav a.on{background:var(--ink);color:#fff}
h1{font-size:34px;margin:.3em 0;font-weight:800;letter-spacing:-.025em}
h2{font-size:18px;margin:1.8em 0 .5em;border-bottom:1px solid var(--line);padding-bottom:7px;font-weight:600}
h3{font-size:14px;margin:1.3em 0 .3em;color:#334155;font-weight:600}
p,li{color:#334155}.mut{color:var(--mut)}a{color:var(--accent)}
code{background:#eef2f7;border:1px solid var(--line);border-radius:5px;padding:1px 5px;font-size:13px}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:13.5px}
th,td{padding:8px 9px;border-bottom:1px solid var(--line);text-align:right}th{color:var(--mut);font-size:11.5px;text-transform:uppercase;letter-spacing:.5px}
td.l,th.l{text-align:left}
.box{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin:12px 0;box-shadow:0 1px 2px rgba(16,24,40,.04)}
.kbd{display:inline-block;background:#eef2f7;border:1px solid var(--line);border-radius:6px;padding:2px 8px;margin:2px;font-size:12.5px}
.src{display:flex;justify-content:space-between;gap:10px;padding:9px 0;border-bottom:1px dashed var(--line)}
.src:last-child{border-bottom:0}.foot{color:var(--mut);font-size:12.5px;margin:26px 0 8px;border-top:1px solid var(--line);padding-top:14px}
"""

    body = f"""
<nav><span class="bk">World Cup 2026</span>
 <a href="index.html">Tracker</a>
 <a href="about.html" class="on">Methodology</a></nav>

<div style="font-size:11px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:var(--accent)">FIFA World Cup 2026 · Quantitative forecast</div>
<h1>Methodology &amp; disclosure</h1>
<p class="mut">A documented, out-of-sample-validated probabilistic model of the 2026 FIFA World Cup. This note
sets out the data inputs, estimation procedure, validation results, assumptions, and limitations in full, so
that the construction and the performance of the forecast can be assessed independently.</p>

<div class="box"><b>Summary.</b> Each national team is assigned a single latent strength rating (Elo). For a
given fixture, the rating differential is mapped to a joint distribution over scorelines through a
bivariate-Poisson (Dixon–Coles) specification whose parameters are estimated by maximum likelihood on
historical results. The complete 104-match tournament — group stage, qualification of the eight best
third-placed teams, and the knockout bracket — is evaluated by Monte Carlo simulation over 10,000 paths,
producing each team's probability of reaching every stage and of winning the tournament. Because regulated
betting markets aggregate information not available to the model, the championship distribution is
additionally combined with the de-vigged market through a weighted opinion pool. Out-of-sample performance
statistics are recomputed and disclosed on every run.</div>

<h2>Interpreting the output</h2>
<p>All figures are probabilities, not point predictions. A value of 18% for a given team denotes that the
team prevailed in approximately 18% of simulated tournaments; it is not an assertion that the team will or
will not win. In a 48-team single-elimination format the outcome carries high entropy, and even the strongest
entrant rarely exceeds approximately 20%. The informative content therefore resides in the full predictive
distribution and, critically, in its calibration: when the model assigns 20%, the event should occur in
approximately 20% of cases. Calibration is evidenced in the validation section below. Movements of a few
tenths of a percentage point between runs reflect Monte Carlo sampling error rather than a material change in
the forecast.</p>

<h2>Data inputs and variables</h2>
<p>The forecast is driven by a single strength factor together with the fixed tournament structure.
Additional variables were evaluated as candidate predictors or are used solely as an external benchmark, as
set out below.</p>
<table>
<tr><th class="l">Variable</th><th class="l">Role</th><th class="l">Status</th></tr>
<tr><td class="l">Elo rating (per team)</td><td class="l">latent team strength; updated from in-tournament results</td><td class="l">Primary input</td></tr>
<tr><td class="l">Host advantage</td><td class="l">Elo adjustment for host nations on home soil</td><td class="l">Applied (capped at +60 Elo)</td></tr>
<tr><td class="l">Live match results</td><td class="l">fix completed fixtures, re-estimate, re-simulate the remainder</td><td class="l">Applied as entered</td></tr>
<tr><td class="l">Market-implied probabilities</td><td class="l">external benchmark and blend counterpart</td><td class="l">Benchmark and blend only</td></tr>
<tr><td class="l">Squad market value</td><td class="l">candidate predictor (Transfermarkt)</td><td class="l">Evaluated; no incremental signal</td></tr>
<tr><td class="l">Rest days, match importance</td><td class="l">candidate predictors</td><td class="l">Evaluated; no incremental signal</td></tr>
</table>

<h2>Methodology</h2>
<h3>1 · Strength estimation (Elo)</h3>
<p>Each team carries a rating that updates after every observed match by <code>K · G · (result − expected)</code>,
where the expected result is the logistic function of the rating differential and <code>G</code> weights the
revision by margin of victory. The rating is the model's sole measure of team quality. During the tournament,
ratings are revised from completed fixtures, so the forecast is re-priced as matches are played.</p>
<h3>2 · Match model (Dixon–Coles, maximum likelihood)</h3>
<p>Each fixture is represented by two goal counts modelled as Poisson processes with the Dixon–Coles (1997)
low-score correction — a dependence parameter ρ that restores the empirical frequency of low-scoring draws,
which the independent-Poisson benchmark understates. Goal intensities follow a log-linear link,
<code>log λ = μ ± γ·d/400</code>, where <code>d</code> is the rating differential inclusive of the home term.
The four parameters are estimated by maximum likelihood (L-BFGS-B) on approximately {n_train+n_test:,}
international fixtures since 2002, under exponential time-decay weighting (approximately a two-year
half-life) so that recent results — reflecting current squads — carry greater weight. Current estimates:
<span class="kbd">μ = {mu:.3f}</span><span class="kbd">γ = {gamma:.3f} (≈ GOAL_SCALE {scale:.0f})</span>
<span class="kbd">home = {home_elo:.0f} Elo</span><span class="kbd">ρ = {rho:+.3f}</span>.</p>
<h3>3 · Tournament simulation (Monte Carlo)</h3>
<p>Each of the 104 fixtures is sampled from its estimated scoreline distribution; the group stage, the
allocation of the eight best third-placed teams, and the knockout bracket are resolved exactly per the
official format; and the champion is recorded. Ten thousand independent paths convert match-level
probabilities into stage-by-stage and championship probabilities, each reported with its Monte Carlo standard
error.</p>
<h3>4 · Combination with the market</h3>
<p>The outright market, de-vigged using the Shin (1992) method — which removes the bookmaker margin while
correcting the favourite–longshot bias that simple proportional normalisation leaves in — is combined with the
model through a weighted opinion pool (default 70% market, 30% model). Because the two sources err on partially
independent information sets, the combination attains lower out-of-sample loss than either constituent alone.</p>
<h3>5 · Variable selection (ordered logit, walk-forward cross-validation)</h3>
<p>To assess whether additional variables carry information beyond the rating, an ordered-logit Win/Draw/Loss
model is estimated by maximum likelihood and each candidate is scored by its <i>incremental</i> out-of-sample
log loss relative to an Elo-only specification, under expanding-window (walk-forward) cross-validation with
paired-bootstrap confidence intervals. No candidate produced a statistically distinguishable improvement
(see Limitations).</p>

<h2>Out-of-sample validation</h2>
<p>Performance is assessed strictly out of sample: parameters are estimated on fixtures prior to {split} and
evaluated on the {n_test:,} international fixtures played subsequently. Lower log loss, Brier score, and ranked
probability score (RPS) indicate better probabilistic accuracy; accuracy is the share of Win/Draw/Loss
outcomes correctly assigned the highest probability. Benchmarks are a uniform (no-information) forecast, the
empirical base rate, and a parsimonious Elo-only ordered-logit specification.</p>
<table>
<tr><th class="l">Specification</th><th>Log loss</th><th>Brier</th><th>RPS</th><th>Accuracy</th></tr>
{skrows}
</table>
<p>On the held-out sample, the model reduces log loss by approximately {sc_coin*100:.0f}% relative to the
uniform benchmark and {sc_base*100:.0f}% relative to the empirical base rate (McFadden pseudo-R² ≈ {r2:.2f}),
and is well calibrated, with an expected calibration error of {ece:.3f}. Its discriminative performance is
statistically indistinguishable from the Elo-only benchmark; the additional structure of the scoreline model
is therefore justified by its role in resolving group-stage tie-breakers and bracket progression rather than
by superior match-level discrimination. Calibration is corroborated by a reliability analysis under six-fold
expanding-window cross-validation.</p>

<h2>Assumptions</h2>
<p>The framework assumes that goals follow a Poisson/Dixon–Coles law; that team quality is adequately
summarised by a single rating; that the rating differential maps log-linearly to goal intensities; that
fixtures are conditionally independent given ratings; that team strength is fixed within a tournament apart
from results-driven revisions and a single per-tournament rating-uncertainty draw; that home advantage is
additive in the rating and confined to host nations; that penalty shoot-outs are approximately symmetric with
a small skill component; and that the relationship estimated over 2002 to the present is stationary through
2026.</p>

<h2>Limitations and scope</h2>
<p>The model is deliberately constrained to a single latent strength factor and consequently incorporates less
information than regulated betting markets, which price squad availability, team selection, recent form, and
order flow. It should therefore be expected to track, rather than to outperform, an efficient closing price,
and it exhibits mild over-concentration on the highest-rated entrants. Several extensions intended to relax the
single-factor constraint were evaluated and did not improve out-of-sample performance: a friendly-adjusted
scoreline fit, a match-importance interaction, and squad market value — the last approximately 0.80 correlated
with the rating, with no measurable signal in its orthogonal component. The tournament-level
rating-uncertainty parameter could not be identified from match-level data. Only the incorporation of external
information, through the market blend, produced a measurable improvement. These negative results are disclosed
rather than omitted.</p>

<h2>Data sources and attribution</h2>
<div class="box">
<div class="src"><span><b>Match results</b> — historical international results since 1872, community-maintained
 by Mart Jürisoo.</span><span><a href="https://github.com/martj42/international_results">github.com/martj42</a></span></div>
<div class="src"><span><b>Elo ratings</b> — World Football Elo Ratings (pre-tournament team strengths).</span>
 <span><a href="https://www.eloratings.net/">eloratings.net</a></span></div>
<div class="src"><span><b>Squad market values</b> — Transfermarkt national-team valuations (tested as a feature).</span>
 <span><a href="https://www.transfermarkt.com/">transfermarkt.com</a></span></div>
<div class="src"><span><b>Betting odds</b> — The Odds API, aggregating major bookmakers (blend &amp; benchmark).</span>
 <span><a href="https://the-odds-api.com/">the-odds-api.com</a></span></div>
</div>
<p class="mut">All datasets remain the property of their respective providers and are used here for
non-commercial research purposes. The project is independent and is not affiliated with, authorised by, or
endorsed by FIFA, the data providers, or any bookmaker. Methodological lineage: Elo (1978); Dixon &amp; Coles,
<i>Applied Statistics</i> (1997); and the probabilistic scoring rules of Brier (1950) and Epstein (1969).</p>

<h2>Reproducibility</h2>
<p>The full pipeline — data ingestion, leakage-free rating, maximum-likelihood estimation, simulation,
backtesting, and the generation of this site — is fully scripted and covered by an automated test suite. The
methodology, the validation diagnostics, and the complete record of specifications evaluated and rejected are
maintained alongside the source code.</p>

<h2>Disclaimer</h2>
<p>This material is provided for informational and educational purposes only. It does not constitute
financial, investment, or betting advice, nor an offer or solicitation to enter into any transaction. Past
performance and out-of-sample diagnostics are not guarantees of future results.</p>

<div class="foot">© 2026 <b>Pedro Henrique Figueiredo Magalhães</b>. Model design, implementation, analysis,
and documentation by Pedro Henrique Figueiredo Magalhães. All rights reserved. Data © their respective
providers (see above).<br>
Last generated {data.get('generated','')}.</div>
"""
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'>" \
           f"<meta name='viewport' content='width=device-width,initial-scale=1'>" \
           f"<title>About — World Cup 2026 Model</title>" \
           f"<link rel='preconnect' href='https://fonts.googleapis.com'><link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>" \
           f"<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap' rel='stylesheet'>" \
           f"<style>{css}</style></head>" \
           f"<body><div class='wrap'>{body}</div></body></html>"


if __name__ == "__main__":
    main()
