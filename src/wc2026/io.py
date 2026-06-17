"""I/O: load Elo, parse results (CSV/Excel), print resolved fixtures, save and
score the ex-ante forecast. Verbatim from the original monolith.
"""

import pandas as pd

from .structure import GROUP_FIXTURES, KO
from .match_model import update_elo  # noqa: F401  (kept for API parity / convenience)
from .tournament import allocate_thirds
from .elo_dynamics import apply_known_results, _deterministic_groups


def load_elo(path="wc2026_elo.csv"):
    df = pd.read_csv(path)
    return df.set_index("Team")["Elo"].to_dict()


def load_champion_odds(path="data/odds_champion.csv"):
    """Load outright (to-win-the-tournament) decimal odds for the model-vs-market
       comparison. CSV with columns: team, odds  (decimal, e.g. 5.0 = +400).
       Returns {team: decimal_odds} for odds > 1, or {} if the file is absent."""
    import os
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    tcol = cols.get("team") or list(df.columns)[0]
    ocol = cols.get("odds") or cols.get("decimal") or cols.get("price") or list(df.columns)[1]
    out = {}
    for _, r in df.iterrows():
        try:
            t = str(r[tcol]).strip(); o = float(r[ocol])
            if t and o > 1: out[t] = o
        except (ValueError, TypeError):
            continue
    return out


def _coerce_results(df):
    """Turn a dataframe with columns match/home_goals/away_goals[/pk] into
       (known_group, known_ko). Tolerant of blanks, text, extra columns."""
    cols = {c.lower().strip(): c for c in df.columns}
    def col(*names):
        for n in names:
            if n in cols: return cols[n]
        return None
    cm = col("match", "match #", "match#", "match_no")
    ch = col("home goals", "home_goals", "homegoals", "hg")
    ca = col("away goals", "away_goals", "awaygoals", "ag")
    cp = col("pk win", "pk", "pk_win", "shootout")
    if cm is None or ch is None or ca is None:
        raise ValueError("Results file must have columns: Match #, Home Goals, Away Goals (and optional PK Win).")
    kg, kk = {}, {}
    for _, row in df.iterrows():
        try:
            if pd.isna(row[cm]) or pd.isna(row[ch]) or pd.isna(row[ca]):
                continue                      # unplayed / blank -> skip
            m = int(float(row[cm])); gh = int(float(row[ch])); ga = int(float(row[ca]))
        except (ValueError, TypeError):
            continue                          # stray text -> skip safely
        if m < 1 or m > 104:
            continue
        if m <= 72:
            kg[m] = (gh, ga)
        else:
            pk = ""
            if cp is not None and not pd.isna(row[cp]):
                pk = str(row[cp]).strip().upper()
            kk[m] = (gh, ga, pk if pk in ("H", "A") else None)
    return kg, kk


def load_results(path=None):
    """Load actual results. Tries the Excel file first, then CSV.
       Returns (known_group, known_ko). Never raises on a missing file."""
    candidates = [path] if path else ["wc2026_results.xlsx", "wc2026_results.csv"]
    for p in candidates:
        if p is None: continue
        try:
            if p.lower().endswith((".xlsx", ".xlsm")):
                try:
                    raw = pd.read_excel(p, sheet_name="Results", header=None)
                except ImportError:
                    print("  [!] openpyxl not installed -> can't read Excel. "
                          "Run: pip install openpyxl   (falling back to CSV if present)")
                    continue
                except PermissionError:
                    print(f"  [!] '{p}' is open in Excel and locked. Save & close it, then re-run.")
                    raise
                # find the header row (the one containing 'Match #')
                hrow = None
                for i in range(min(10, len(raw))):
                    vals = [str(x).strip().lower() for x in raw.iloc[i].tolist()]
                    if any(v.startswith("match") for v in vals):
                        hrow = i; break
                if hrow is None:
                    raise ValueError("Couldn't find a 'Match #' header in the Results sheet.")
                df = pd.read_excel(p, sheet_name="Results", header=hrow)
            else:
                df = pd.read_csv(p)
        except FileNotFoundError:
            continue
        except PermissionError:
            raise
        return _coerce_results(df)
    print("  [i] No results file found yet -> running PRE-TOURNAMENT forecast.")
    return {}, {}


def show_fixtures(elo, kg=None, kk=None, third_override=None):
    """Print every match number with its resolved teams, given results so far.
       Use this AFTER entering group results to see who is in each knockout
       match number, so you know which row to fill in next."""
    kg = kg or {}; kk = kk or {}
    e = apply_known_results(elo, kg, kk, third_override)
    res = _deterministic_groups(e, kg)
    print("\n--- GROUP STAGE ---")
    for m in sorted(GROUP_FIXTURES):
        t1, t2, g = GROUP_FIXTURES[m]
        sc = f"{kg[m][0]}-{kg[m][1]}" if m in kg else "-- not played --"
        print(f"  M{m:>3}  Grp {g}  {t1} vs {t2:<22}  {sc}")
    if res is None:
        print("\n--- KNOCKOUTS ---  (enter all 72 group results to resolve these)")
        return
    winners, runners, thirds = res
    thirds.sort(key=lambda x: (x[2]['pts'], x[2]['gd'], x[2]['gf'], e[x[1]]), reverse=True)
    qual = {g: t for g, t, _ in thirds[:8]}
    slot_group = dict(third_override) if third_override else allocate_thirds(list(qual))
    slot_team = {m: qual.get(g) for m, g in slot_group.items()}
    mwin, mlose = {}, {}
    def part(slot):
        typ, ref = slot
        return {"W": winners.get(ref), "RU": runners.get(ref), "3": slot_team.get(ref),
                "WIN": mwin.get(ref), "LOSE": mlose.get(ref)}[typ]
    note = "" if third_override else "  [3rd-place slots are the engine's APPROX until you set third_override]"
    print(f"\n--- KNOCKOUTS ---{note}")
    for m in sorted(KO):
        rnd, hs, as_ = KO[m]
        home, away = part(hs), part(as_)
        if m in kk:
            ga, gb, pk = kk[m]
            if ga > gb: w = home
            elif gb > ga: w = away
            else: w = home if pk == "H" else (away if pk == "A" else (home if e.get(home,0) >= e.get(away,0) else away))
            sc = f"{ga}-{gb}" + (f" ({pk} pens)" if pk else "")
            mwin[m] = w; mlose[m] = away if w == home else home
        else:
            sc = "-- not played --"
        hh = home or "?"; aa = away or "?"
        print(f"  M{m:>3}  {rnd:<5} {hh} vs {aa:<22}  {sc}")


def save_forecast(df, path="wc2026_forecast_exante.csv"):
    """Save a model forecast (e.g., the pre-tournament run) for later scoring."""
    df.to_csv(path)
    print(f"  [saved ex-ante forecast -> {path}]")


def score_forecast(exante_path="wc2026_forecast_exante.csv", kg=None, kk=None):
    """After the tournament, compare the saved ex-ante MODEL forecast to what
       actually happened. Reports champion call + a Brier-style readout."""
    kg = kg or {}; kk = kk or {}
    if 104 not in kk:
        print("  [final not yet entered -> nothing to score]"); return
    fc = pd.read_csv(exante_path, index_col=0)
    # rebuild actual progression from results to find who actually reached each round
    e = apply_known_results({t: fc.loc[t, "Elo"] for t in fc.index}, kg, kk)
    # actual champion is the winner of match 104, derivable via show path:
    res = _deterministic_groups(e, kg)
    actual = {}
    if res:
        winners, runners, thirds = res
        thirds.sort(key=lambda x: (x[2]['pts'], x[2]['gd'], x[2]['gf'], e[x[1]]), reverse=True)
        qual = {g: t for g, t, _ in thirds[:8]}
        slot_group = allocate_thirds(list(qual)); slot_team = {m: qual.get(g) for m, g in slot_group.items()}
        mwin, mlose = {}, {}
        def part(slot):
            typ, ref = slot
            return {"W":winners.get(ref),"RU":runners.get(ref),"3":slot_team.get(ref),
                    "WIN":mwin.get(ref),"LOSE":mlose.get(ref)}[typ]
        for m in sorted(KO):
            if m not in kk: continue
            home, away = part(KO[m][1]), part(KO[m][2]); ga, gb, pk = kk[m]
            w = home if ga > gb else (away if gb > ga else (home if pk == "H" else away))
            mwin[m] = w; mlose[m] = away if w == home else home
        champ = mwin.get(104)
        pred = fc.sort_values("Win", ascending=False).index[0]
        p_actual = fc.loc[champ, "Win"] if champ in fc.index else 0.0
        print("\n=== EX-ANTE MODEL  vs  ACTUAL ===")
        print(f"  Model's pre-tournament favourite : {pred} ({fc.loc[pred,'Win']}%)")
        print(f"  Actual champion                  : {champ}")
        print(f"  Model probability on the champion: {p_actual}%")
        print(f"  Champion correctly called?       : {'YES' if pred == champ else 'no'}")
