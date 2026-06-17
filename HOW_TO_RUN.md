# World Cup 2026 Forecasting Engine — Operating Manual

A Monte Carlo tournament forecaster. You maintain two files; the engine does the rest:
forecasts, dynamic re-forecasting from real results, model-vs-market comparison, and a
final predicted-vs-actual scorecard.

---

## 0. ONE-TIME SETUP (do this once, before the tournament)

### Install Python + the three libraries
You need **Python 3.9 or newer**. Then, in a terminal:

```
pip install numpy pandas openpyxl
```

That's the *complete* dependency list:
- **numpy** — the random draws and math.
- **pandas** — reads/writes the CSV and Excel files.
- **openpyxl** — only needed so pandas can read the Excel results file. If you ever
  decide to use the CSV instead of Excel, openpyxl isn't required.

**There are NO web/internet dependencies.** The engine never makes a network call.
Nothing online can rate-limit it, time it out, or break it. The only time the web is
involved is when *you* manually look up Elo ratings or bookmaker odds and type them in.

### Put these files in ONE folder
```
wc2026_engine.py              <- the model (don't edit unless tuning)
wc2026_elo.csv                <- team strengths (your input; see below)
wc2026_results.xlsx           <- actual results (you fill this in as matches happen)
```
(There's also a `wc2026_results.csv` as a backup format — ignore it if you use Excel.)

### Confirm it runs
From inside that folder:
```
python wc2026_engine.py
```
If you see a forecast table print, you're operational. If you get
`ModuleNotFoundError`, re-run the pip install line above.

---

## 1. THE TWO FILES YOU TOUCH

### `wc2026_elo.csv` — team strength (mostly leave alone)
Three columns: `Team, Group, Elo`. This is the model's view of how good each team is.

- **Keep it STATIC during the tournament.** Set it once before kickoff and leave it.
- **Why:** eloratings.net already updates its numbers after every World Cup match. If you
  refresh this file mid-tournament *and* enter results in the results file, you count the
  same matches twice. Let the results file do the updating (the engine updates Elo
  internally from results each run — it just doesn't rewrite this CSV).
- **Optional pre-tournament refresh:** before the first match, you may want to replace the
  numbers with the latest from https://www.eloratings.net/ . Fine. Just stop refreshing
  once the tournament starts.

### `wc2026_results.xlsx` — actual results (your live input)
Open it in Excel. The **Results** sheet lists all 104 matches, already labelled:

| Match # | Date | Round | Fixture (Home vs Away) | Home Goals | Away Goals | PK Win | Status |
|--------|------|-------|------------------------|-----------|-----------|--------|--------|
| 1 | Jun 11 | Group A | Mexico vs South Africa | _(you type)_ | _(you type)_ | | |
| ... | | | | | | | |

**To record a result:** find the row (the fixture is spelled out — no need to memorise
match numbers), type the score in the yellow **Home Goals / Away Goals** cells, **save**.
That's it. Leave unplayed matches blank.

- **"Home" = the first team listed** in the Fixture column. Enter goals in that order.
- **Knockout penalties:** if a knockout tie is level after extra time, put **H** (home won
  the shootout) or **A** (away won) in the **PK Win** column. For group matches, leave it blank.
- The **Team Index** sheet is just a reference (team → group → Elo) for convenience.

> **Always press Ctrl+S before running the model.** If the file is open and unsaved, the
> engine reads the old version; if Excel has it locked, the engine will tell you to close it.

---

## 2. EX-ANTE: YOUR PRE-TOURNAMENT FORECAST (before June 11)

With the results file empty, run:
```
python wc2026_engine.py
```
You get four things:

1. **Forecast table** — for each team, the probability of reaching each round
   (R32 / R16 / QF / SF / Final) and winning. This is the model's pre-tournament view.
2. **Ex-ante forecast saved** — on this first run the engine writes
   `wc2026_forecast_exante.csv`. **Don't delete it** — it's what the final scorecard
   compares against. (It only saves once, while results are empty.)
3. **Model vs Market** — your model's champion odds next to de-vigged bookmaker odds, with
   the gap. Positive `Edge(pp)` / `Edge_x > 1` = model rates the team higher than the market.
   *To use this:* paste current champion odds into the `MARKET_ODDS` dict near the top of
   `wc2026_engine.py` first (decimal odds, e.g. Spain 5.0).
4. **One simulated road to the final** — a single plausible bracket, for flavour. It's ONE
   random draw, not a prediction — read the probability table for that.

**This is also the moment to lock in YOUR subjective bracket** in the separate Excel
prediction tool (`WorldCup2026_PredictionEngine.xlsx`). Commit your picks while they're
still falsifiable. You'll then have three views to compare later: your gut, the model, the market.

---

## 3. DYNAMIC: UPDATING AS THE TOURNAMENT HAPPENS

The workflow is the same every day:

1. A match finishes → type its score into `wc2026_results.xlsx` → **save**.
2. Run `python wc2026_engine.py`.
3. The header now says `DYNAMIC (N group + M KO results in)`. The engine fixes the matches
   you've entered, updates Elo from them, and re-simulates only the *unplayed* remainder.
   Teams that are eliminated drop to 0%; survivors get repriced.

You can enter one match at a time or a whole matchday at once — whatever suits you.

### After the group stage ends — TWO things

**(a) See who's actually in each knockout match.** The knockout fixtures depend on group
results, so once all 72 group games are in, find out who lands in each match number:
```python
import wc2026_engine as E
elo = E.load_elo()
kg, kk = E.load_results()
E.show_fixtures(elo, kg, kk)     # prints every match # with the resolved teams
```
Now you know, e.g., that "M73" is "Czechia vs Qatar", so you know which row to fill when
that game is played.

**(b) Pin the official 3rd-place allocation.** FIFA decides which 8 third-placed teams go
to which knockout slots via a fixed table they publish once the group stage ends. Until
then the engine uses a valid approximation. Once FIFA publishes, pass the real mapping as
`third_override` — a dict of `{match_number: group_letter}` for the eight 3rd-place slots
(matches 74, 77, 79, 80, 81, 82, 85, 87):
```python
override = {74:"B", 77:"C", 79:"E", 80:"H", 81:"F", 82:"A", 85:"I", 87:"J"}  # EXAMPLE
probs = E.run_monte_carlo(elo, kg=kg, kk=kk, third_override=override)
print(probs.head(16))
```
(Send me the official allocation after the group stage and I'll give you the exact line.)

---

## 4. EX-POST: PREDICTED vs ACTUAL (after the final)

Once match 104 (the Final) is entered and saved, just run the engine normally:
```
python wc2026_engine.py
```
At the bottom you now get the **EX-ANTE MODEL vs ACTUAL** scorecard:
- the model's pre-tournament favourite,
- the actual champion,
- the probability the model had assigned to the team that actually won,
- whether the favourite was called correctly.

For *your own* predictions vs actual (not the model's), use the Dashboard tab of the Excel
prediction tool — it compares your ex-ante bracket to the ex-post results match by match.

---

## 5. THE THREE CALIBRATION KNOBS (top of `wc2026_engine.py`)

You don't need to touch these, but if you want to experiment:

| Knob | Default | What it does |
|------|---------|--------------|
| `SIGMA_TEAM` | 40 | Per-team rating uncertainty. Higher = more upsets. |
| `SIGMA_CONF` | 35 | Shared confederation shock. Adds *uncertainty* to cross-confederation matchups without assuming a direction. Set to 0 to switch off. |
| `GOAL_SCALE` | 600 | How sharply Elo gaps turn into goals. 400 = raw Elo (favourite-heavy). Higher = flatter. This is the main lever on favourite over/under-confidence. |

These are *reasoned defaults, not fitted values.* The principled way to set them is to
minimise prediction error (log-loss / Brier) on historical international results — a
separate calibration project. Treat them as priors.

---

## 6. TROUBLESHOOTING

| Symptom | Fix |
|--------|-----|
| `ModuleNotFoundError: numpy/pandas/openpyxl` | `pip install numpy pandas openpyxl` |
| `'wc2026_results.xlsx' is open in Excel and locked` | Save and close the file, re-run. |
| Forecast says PRE-TOURNAMENT but you entered results | You didn't **save** the Excel file, or the engine is being run from a different folder. |
| A match you entered isn't being counted | Both Home and Away goals must be filled; text in a goals cell is ignored on purpose. |
| Knockout fixtures show "? vs ?" | Normal until the feeding matches are played/entered. |
| Numbers shift slightly between runs | Expected — it's Monte Carlo. Raise `ITERATIONS` (top of file) for steadier numbers; 10,000 ≈ ±0.5pp. |

---

## 7. QUICK REFERENCE — the daily loop

```
1. Match ends.
2. Open wc2026_results.xlsx, type the score on that fixture's row, Ctrl+S.
3. python wc2026_engine.py
4. Read the updated probabilities (and the Model-vs-Market gap).
5. After the group stage: run show_fixtures() + set third_override.
6. After the final: read the EX-ANTE vs ACTUAL scorecard.
```
