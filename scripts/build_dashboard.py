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
import datetime as dt

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "outputs")
ODDS = os.path.join(ROOT, "data", "odds_champion.csv")
ROUNDS = ["R32", "R16", "QF", "SF", "Final", "Win"]


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
        imp = {str(r["team"]): 1.0 / float(r["odds"]) for _, r in df.iterrows() if float(r["odds"]) > 1}
    except Exception:
        return {}
    s = sum(imp.values())
    return {t: round(p / s * 100, 2) for t, p in imp.items()} if s else {}


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
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def main():
    data = build_data()
    html = TEMPLATE.replace("/*DATA*/", json.dumps(data))
    out = os.path.join(OUT, "dashboard.html")
    with open(out, "w") as f:
        f.write(html)
    # also write index.html so the nav links (which target index.html, as on the
    # deployed site) resolve when opening the files locally too
    with open(os.path.join(OUT, "index.html"), "w") as f:
        f.write(html)
    print(f"  dashboard -> {os.path.relpath(out, ROOT)} (+ index.html)  "
          f"({len(data['teams'])} teams, {len(data['labels'])} snapshots)")
    ab = os.path.join(OUT, "about.html")
    with open(ab, "w") as f:
        f.write(build_about(data))
    print(f"  about     -> {os.path.relpath(ab, ROOT)}")
    print("  open dashboard.html in a browser.")


# ---------------------------------------------------------------------------
TEMPLATE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>World Cup 2026 — Forecast Tracker</title>
<style>
:root{
  --bg:#0b1020; --panel:#121a31; --panel2:#0f1730; --ink:#e8edf7; --mut:#8a97b5;
  --line:#22304f; --accent:#5b8cff; --good:#34d399; --bad:#fb7185; --chip:#1b2745;
}
*{box-sizing:border-box} html,body{margin:0}
body{background:linear-gradient(180deg,#0b1020,#0c1226);color:var(--ink);
  font:14px/1.45 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:22px}
h1{font-size:22px;margin:0;letter-spacing:.2px}
.sub{color:var(--mut);font-size:12.5px;margin-top:3px}
.row{display:flex;gap:16px;flex-wrap:wrap}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:0 6px 24px rgba(0,0,0,.25)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}
.kpi{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.kpi .l{color:var(--mut);font-size:11.5px;text-transform:uppercase;letter-spacing:.6px}
.kpi .v{font-size:20px;font-weight:650;margin-top:4px}
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
.tip{position:absolute;pointer-events:none;background:#0a1124;border:1px solid var(--line);
  border-radius:8px;padding:6px 9px;font-size:12px;opacity:0;transition:opacity .1s;white-space:nowrap;z-index:5}
.grid-2{display:grid;grid-template-columns:1.4fr 1fr;gap:16px;margin-top:16px}
@media(max-width:860px){.grid-2{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,1fr)}}
.mover{display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px dashed var(--line)}
.mover:last-child{border-bottom:0}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:8px;vertical-align:middle}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:7px 8px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--mut);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.5px;cursor:pointer;position:sticky;top:0;background:var(--panel)}
td.team,th.team{text-align:left}
.tbar{position:relative;height:16px;background:#0c1430;border-radius:4px;min-width:54px;overflow:hidden;display:inline-block;width:90px;vertical-align:middle}
.tbar > i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;opacity:.85}
.tbar > span{position:absolute;left:6px;top:0;line-height:16px;font-size:11px;color:#dfe7fb}
.chip{font-size:10.5px;padding:1px 7px;border-radius:20px;color:#dfe7fb;background:var(--chip)}
.up{color:var(--good)} .down{color:var(--bad)} .flat{color:var(--mut)}
.tablewrap{max-height:560px;overflow:auto;border-radius:10px}
.legend{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
.legend .it{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--mut);cursor:pointer;padding:2px 6px;border-radius:7px}
.legend .it.dim{opacity:.35}
.foot{color:var(--mut);font-size:11.5px;margin-top:18px;text-align:center}
.mkt{display:flex;align-items:center;gap:8px;margin:5px 0}
.mkt .nm{width:120px;font-size:12.5px}
.mbar{flex:1;display:flex;gap:4px}
.mbar .seg2{height:14px;border-radius:4px}
</style></head>
<body><div class="wrap">
  <div style="display:flex;gap:18px;align-items:center;border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:16px">
    <span style="font-weight:700;letter-spacing:.3px">WC&nbsp;2026 Model</span>
    <a href="index.html" style="color:var(--ink);text-decoration:none;font-size:13px;border-bottom:2px solid var(--accent);padding-bottom:11px">Forecast tracker</a>
    <a href="about.html" style="color:var(--mut);text-decoration:none;font-size:13px">About &amp; methodology</a>
  </div>
  <div class="row" style="justify-content:space-between;align-items:flex-end">
    <div><h1>World Cup 2026 — Forecast Tracker</h1>
      <div class="sub" id="sub"></div></div>
    <div class="sub" id="gen"></div>
  </div>

  <div class="kpis" id="kpis"></div>

  <div class="card">
    <div class="controls">
      <span style="font-weight:600">Progression</span>
      <div class="seg" id="metricSeg"></div>
      <div class="seg" id="modeSeg">
        <button data-mode="prob" class="on">Probability</button>
        <button data-mode="rank">Rank</button>
      </div>
      <label class="lbl">Show</label>
      <select id="topN"><option value="8">Top 8</option><option value="12">Top 12</option>
        <option value="16">Top 16</option><option value="24">Top 24</option></select>
    </div>
    <div class="chartwrap"><svg id="chart" viewBox="0 0 1000 460" preserveAspectRatio="xMidYMid meet"></svg>
      <div class="tip" id="tip"></div></div>
    <div class="legend" id="legend"></div>
  </div>

  <div class="grid-2">
    <div class="card">
      <div style="font-weight:600;margin-bottom:6px">Standings — latest
        <span class="sub" id="latlbl"></span></div>
      <div class="controls"><input type="search" id="search" placeholder="filter team…" style="flex:1">
        <span class="lbl">Δ vs ex-ante</span></div>
      <div class="tablewrap"><table id="tbl"></table></div>
    </div>
    <div>
      <div class="card"><div style="font-weight:600;margin-bottom:8px">Biggest movers
        <span class="sub">(champion %, vs ex-ante)</span></div>
        <div id="movers"></div></div>
      <div class="card" style="margin-top:16px"><div style="font-weight:600;margin-bottom:8px">Model vs market
        <span class="sub">champion %</span></div>
        <div id="market"></div></div>
    </div>
  </div>

  <div class="foot">
    © 2026 Pedro Henrique Figueiredo Magalhães · Independent research project, not affiliated with or endorsed by FIFA.<br>
    Probabilities are Monte-Carlo estimates for informational and educational purposes — not betting advice.
    Small day-to-day wiggles are simulation noise. &nbsp;·&nbsp; <a href="about.html" style="color:var(--accent)">Methodology &amp; data sources →</a>
  </div>
</div>

<script>
const DATA = /*DATA*/;
const PAL = ["#5b8cff","#34d399","#fbbf24","#fb7185","#a78bfa","#22d3ee","#f472b6","#4ade80",
             "#fb923c","#60a5fa","#e879f9","#2dd4bf","#facc15","#f87171","#818cf8","#38bdf8",
             "#c084fc","#fcd34d","#fda4af","#86efac","#93c5fd","#d8b4fe","#5eead4","#fde68a"];
const CONF = {UEFA:"#3b82f6",CONMEBOL:"#f59e0b",CONCACAF:"#ef4444",CAF:"#22c55e",AFC:"#f97316",OFC:"#14b8a6"};
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
    `<div class="kpi"><div class="l">${c[0]}</div><div class="v">${c[1]}</div><div class="d">${c[2]}</div></div>`).join("");
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
       <span class="dot" style="background:${col[t]}"></span>${t} <b style="color:var(--ink)">${latest(t).toFixed(1)}%</b></div>`).join("");
  document.querySelectorAll("#legend .it").forEach(el=>{
    el.onmouseenter=()=>{state.hi=el.getAttribute("data-t");draw()};
    el.onmouseleave=()=>{state.hi=null;draw()};});
}

/* ---------- movers ---------- */
function movers(){
  const arr=DATA.teams.map(t=>({t, d:(DATA.series[t].Win[N-1]??0)-(DATA.series[t].Win[0]??0),
        now:DATA.series[t].Win[N-1]??0})).filter(o=>Math.abs(o.d)>=0.05);
  arr.sort((a,b)=>b.d-a.d); const top=arr.slice(0,5), bot=arr.slice(-5).reverse();
  const row=o=>`<div class="mover"><span><span class="dot" style="background:${CONF[DATA.info[o.t].Conf]||'#888'}"></span>${o.t}</span>
     <span><span class="${o.d>0?'up':(o.d<0?'down':'flat')}">${o.d>0?'▲':'▼'} ${o.d>0?'+':''}${o.d.toFixed(1)}</span>
     <span class="sub" style="margin-left:8px">${o.now.toFixed(1)}%</span></span></div>`;
  document.getElementById("movers").innerHTML =
    `<div class="sub" style="margin-bottom:4px">Risers</div>${top.map(row).join("")}
     <div class="sub" style="margin:8px 0 4px">Fallers</div>${bot.map(row).join("")}`;
}

/* ---------- market ---------- */
function market(){
  const mk=DATA.market||{}; const el=document.getElementById("market");
  if(!Object.keys(mk).length){ el.innerHTML=`<div class="sub">No odds yet. Add data/odds_champion.csv and rerun.</div>`; return; }
  const teams=rankedTeams().slice(0,10);
  const mx=Math.max(...teams.map(t=>Math.max(latest(t), mk[t]||0)));
  el.innerHTML=teams.map(t=>{const m=mk[t]||0,p=latest(t);
    return `<div class="mkt"><div class="nm">${t}</div><div class="mbar">
       <div class="seg2" style="width:${(p/mx*100).toFixed(0)}%;background:var(--accent)" title="model ${p.toFixed(1)}%"></div>
       <div class="seg2" style="width:${(m/mx*100).toFixed(0)}%;background:#64748b" title="market ${m.toFixed(1)}%"></div>
     </div><div class="sub" style="width:96px;text-align:right">${p.toFixed(1)} / ${m.toFixed(1)}</div></div>`;}).join("")
    +`<div class="sub" style="margin-top:6px"><span style="color:var(--accent)">■</span> model &nbsp; <span style="color:#64748b">■</span> market</div>`;
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
    const inf=DATA.info[t]; const c=CONF[inf.Conf]||"#888";
    const cells=R.map(r=>{const v=DATA.series[t][r][N-1]??0; const w=mx[r]?Math.max(2,v/mx[r]*100):0;
      return `<td><span class="tbar"><i style="width:${w}%;background:${c}"></i><span>${v.toFixed(1)}</span></span></td>`;}).join("");
    const dW=(DATA.series[t].Win[N-1]??0)-(DATA.series[t].Win[0]??0);
    const dcls=dW>0.05?'up':(dW<-0.05?'down':'flat'); const arr=dW>0.05?'▲':(dW<-0.05?'▼':'·');
    return `<tr><td class="team">${t}</td><td><span class="chip" style="background:${c}33;color:${c}">${inf.Conf}</span></td>
      <td>${inf.Elo??''}</td>${cells}<td class="${dcls}">${arr} ${dW>0?'+':''}${dW.toFixed(1)}</td></tr>`;}).join("");
  const tbl=document.getElementById("tbl"); tbl.innerHTML=head+body;
  tbl.querySelectorAll("th").forEach(th=>th.onclick=()=>{const c=th.getAttribute("data-c");
    if(c==="team"||c==="dW")return; if(state.sort===c)state.dir*=-1; else {state.sort=c;state.dir=1;} table();});
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
metricSeg(); kpis(); draw(); legend(); movers(); market(); table();
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
:root{--bg:#0b1020;--panel:#121a31;--ink:#e8edf7;--mut:#8a97b5;--line:#22304f;--accent:#5b8cff}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#0b1020,#0c1226);color:var(--ink);
 font:15px/1.65 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:820px;margin:0 auto;padding:22px}
nav{display:flex;gap:18px;align-items:center;border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:18px}
nav a{text-decoration:none;font-size:13px}
h1{font-size:25px;margin:.2em 0}h2{font-size:18px;margin:1.7em 0 .5em;border-bottom:1px solid var(--line);padding-bottom:6px}
h3{font-size:14px;margin:1.3em 0 .3em;color:#cdd7f0}
p,li{color:#d6deef}.mut{color:var(--mut)}a{color:var(--accent)}
code{background:#0f1730;border:1px solid var(--line);border-radius:5px;padding:1px 5px;font-size:13px}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:13.5px}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:right}th{color:var(--mut);font-size:11.5px;text-transform:uppercase;letter-spacing:.5px}
td.l,th.l{text-align:left}
.box{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin:12px 0}
.kbd{display:inline-block;background:#0f1730;border:1px solid var(--line);border-radius:6px;padding:2px 8px;margin:2px;font-size:12.5px}
.src{display:flex;justify-content:space-between;gap:10px;padding:9px 0;border-bottom:1px dashed var(--line)}
.src:last-child{border-bottom:0}.foot{color:var(--mut);font-size:12.5px;margin:26px 0 8px;border-top:1px solid var(--line);padding-top:14px}
"""

    body = f"""
<nav><span style="font-weight:700">WC&nbsp;2026 Model</span>
 <a href="index.html" style="color:var(--mut)">Forecast tracker</a>
 <a href="about.html" style="color:var(--ink);border-bottom:2px solid var(--accent);padding-bottom:11px">About &amp; methodology</a></nav>

<h1>About this model</h1>
<p class="mut">A transparent, calibrated probabilistic forecast of the 2026 FIFA World Cup — what it does,
the data behind it, the methods, and exactly how good (and how limited) it is.</p>

<div class="box"><b>In one paragraph.</b> Every team carries a single strength rating (Elo). For any match,
the rating gap is turned into a probability distribution over scorelines by a Dixon–Coles goals model whose
parameters are <i>estimated from history by maximum likelihood</i>. The full 104-match tournament — group
stage, the 8 best third-placed teams, and the knockout bracket — is then simulated <b>10,000 times</b> to
estimate each team's chance of reaching every round and winning. Because the betting market prices
information the model can't see, the championship estimate is also <b>blended with the de-vigged market</b>.
The model reports its own out-of-sample accuracy before every run.</div>

<h2>For everyone: how to read it</h2>
<p>The numbers are <b>probabilities, not predictions</b>. "Spain 18%" means that across 10,000 simulated
tournaments Spain won about 1,800 of them — not that Spain will or won't win. In a 48-team knockout even the
strongest side rarely exceeds ~20%, so the value is in the <i>whole distribution</i> and whether it is
<b>well-calibrated</b>: when the model says 20%, that should happen about 20% of the time. It does (see tests
below). Day-to-day wiggles of a few tenths of a percent are simulation noise, not news.</p>

<h2>Inputs &amp; variables</h2>
<p>The forecast is driven by <b>one strength variable plus tournament structure</b>; other quantities are
either tested as candidates or used only as a benchmark.</p>
<table>
<tr><th class="l">Variable</th><th class="l">Role</th><th class="l">In the forecast?</th></tr>
<tr><td class="l">Elo rating (per team)</td><td class="l">team strength; updated live from results</td><td class="l">Yes — the core driver</td></tr>
<tr><td class="l">Host advantage</td><td class="l">Elo bump for the host nations on home soil</td><td class="l">Yes (capped, +60 Elo)</td></tr>
<tr><td class="l">Match results (live)</td><td class="l">fix played games, re-rate, re-simulate the rest</td><td class="l">Yes, as entered</td></tr>
<tr><td class="l">Betting market odds</td><td class="l">external benchmark &amp; blend partner</td><td class="l">Blend &amp; comparison only</td></tr>
<tr><td class="l">Squad market value</td><td class="l">candidate feature (Transfermarkt)</td><td class="l">Tested — no added signal (below)</td></tr>
<tr><td class="l">Rest days, match importance</td><td class="l">candidate features</td><td class="l">Tested — no added signal</td></tr>
</table>

<h2>Methods</h2>
<h3>1 · Strength — the Elo rating system</h3>
<p>Each team has a rating; after every match it updates by <code>K · G · (result − expected)</code>, where the
expected result is a logistic function of the rating gap and <code>G</code> scales the update by margin of
victory. This is the model's only measure of team quality. During the tournament, ratings update from the
results entered, so the forecast re-prices as games are played.</p>
<h3>2 · The match model — Dixon–Coles, fit by maximum likelihood</h3>
<p>Each match produces two goal counts modelled as Poisson processes with the Dixon–Coles (1997) low-score
correction (a parameter ρ that restores realistic draw frequencies, which independent Poisson under-states).
Goal rates follow a log-linear link, <code>log λ = μ ± γ·d/400</code>, where <code>d</code> is the Elo gap plus
a home term. The four parameters are estimated by maximum likelihood (L-BFGS-B) on ~{n_train+n_test:,}
international matches since 2002. Current fitted values:
<span class="kbd">μ = {mu:.3f}</span><span class="kbd">γ = {gamma:.3f} (≈ GOAL_SCALE {scale:.0f})</span>
<span class="kbd">home = {home_elo:.0f} Elo</span><span class="kbd">ρ = {rho:+.3f}</span>.</p>
<h3>3 · The tournament — Monte Carlo simulation</h3>
<p>Each of the 104 matches is sampled from that scoreline distribution; groups, the official-style
third-place allocation, and the knockout bracket are resolved exactly per the real format; the champion is
recorded. Repeating 10,000 times turns single-match probabilities into round-by-round and championship
probabilities, each reported with a <b>Monte-Carlo standard error</b>.</p>
<h3>4 · Market blend</h3>
<p>The de-vigged outright market is combined with the model (default 70% market / 30% model), because the
two err partly independently and the blend out-predicts either alone.</p>
<h3>5 · Feature testing — ordered logistic regression + walk-forward CV</h3>
<p>To ask whether extra variables (squad value, rest, match importance) add value, an ordered-logit
Win/Draw/Loss model is fit by maximum likelihood and each candidate is scored by its <i>incremental</i>
out-of-sample log-loss <b>over Elo</b>, under expanding-window (walk-forward) cross-validation with
paired-bootstrap confidence intervals. None beat Elo (see limitations).</p>

<h2>How it is tested, and the results</h2>
<p>The model is scored <b>out of sample</b>: parameters are fit on matches before {split} and judged on the
<b>{n_test:,}</b> internationals played since. Lower log-loss / Brier / RPS is better; accuracy is the share
of Win/Draw/Loss called correctly. It is measured against a coin, the no-skill base rate, and a one-line
Elo-logistic benchmark.</p>
<table>
<tr><th class="l">Model</th><th>Log-loss</th><th>Brier</th><th>RPS</th><th>Accuracy</th></tr>
{skrows}
</table>
<p><b>Verdict.</b> The model beats a coin by ≈{sc_coin*100:.0f}% and the no-skill base rate by ≈{sc_base*100:.0f}%
on log-loss (a McFadden pseudo-R² of ≈{r2:.2f}), and it is <b>well-calibrated</b> — expected calibration error
{ece:.3f} (when it says X%, it happens about X%). It essentially ties the simple Elo-logistic, which is the
honest, important caveat: the elaborate goals machinery earns its keep on <i>scorelines</i> (needed for group
tie-breakers and the bracket), not on sharper Win/Draw/Loss calls. Calibration is also confirmed on a
reliability curve from a 6-fold walk-forward cross-validation.</p>

<h2>Assumptions</h2>
<p>Goals follow a Poisson / Dixon–Coles law; a team's quality is summarised by one rating; the Elo gap maps
log-linearly to goal rates; matches are independent given ratings; team strength is fixed within a tournament
apart from results-driven updates and a once-per-tournament rating-uncertainty draw; home advantage is
additive in Elo and applied only to hosts; penalty shootouts are near coin-flips with a small skill tilt; and
the relationship fit on 2002–present is assumed to hold for 2026.</p>

<h2>Limitations &amp; honest caveats</h2>
<p>This is a well-calibrated <b>Elo-based</b> forecaster, not a market-beater. It uses less information than
the betting market (no injuries, line-ups, form, or money flow) and therefore tends to <b>track, not beat</b>,
a sharp price — and to be somewhat over-concentrated on the highest-rated teams. Every attempt to push past
this "Elo ceiling" from within was tested and <b>rejected out of sample</b>: a friendly-aware goals fit, a
match-importance interaction, and squad market value all failed to improve accuracy (squad value is ~0.80
correlated with Elo and its orthogonal part showed no signal), and the rating-uncertainty parameter could not
be cleanly identified from match data. Only importing external information — the market blend — helped. The
model states its own ceiling rather than hiding it.</p>

<h2>Data sources &amp; credits</h2>
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
<p class="mut">All data remains the property of its respective providers and is used here for non-commercial,
educational research. This project is independent and is not affiliated with, authorised by, or endorsed by
FIFA, the data providers, or any bookmaker. Academic lineage: Elo (1978); Dixon &amp; Coles, <i>Applied
Statistics</i> (1997); standard probabilistic-forecast scoring (Brier 1950; ranked probability score, Epstein
1969).</p>

<h2>Reproducibility</h2>
<p>The full pipeline — data ingestion, leakage-free rating, MLE fitting, simulation, backtesting and this
dashboard — is scripted and covered by an automated test suite. The methodology, validation figures, and the
record of what was tried and rejected are documented alongside the code.</p>

<div class="foot">© 2026 <b>Pedro Henrique Figueiredo Magalhães</b>. Model, code, analysis, and writing by
Pedro Henrique Figueiredo Magalhães. Provided for informational and educational purposes only — not betting
advice. Not affiliated with FIFA. Data © respective providers (see above).<br>
Generated {data.get('generated','')}.</div>
"""
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'>" \
           f"<meta name='viewport' content='width=device-width,initial-scale=1'>" \
           f"<title>About — World Cup 2026 Model</title><style>{css}</style></head>" \
           f"<body><div class='wrap'>{body}</div></body></html>"


if __name__ == "__main__":
    main()
