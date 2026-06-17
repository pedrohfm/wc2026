# World Cup 2026 forecasting engine — user manual

This is the operating manual for the whole system. If you read one thing, read
**§3 (the 60-second path)**; everything after it is detail you can reach for
when you need it.

You have **two models**:

- **The tournament forecaster** — simulates the whole World Cup 10,000 times and
  gives each team a probability of reaching each round and winning. This is the
  one you'll use day to day.
- **The match/feature model** — a calibrated Dixon-Coles match model and an
  evaluation suite that scores accuracy out-of-sample and measures which
  variables actually add predictive power. This is the one that tells you
  whether to *trust* the forecaster.

---

## 1. One-time setup

You need **Python 3.9+**. From the project folder:

```bash
pip install numpy pandas openpyxl scipy matplotlib pytest
```

What each is for: `numpy/pandas` (everything), `openpyxl` (read the results
Excel file), `scipy` (the maximum-likelihood fit), `matplotlib` (the charts),
`pytest` (the tests). The first three are essential; the last two are only for
calibration/validation.

Confirm it works:

```bash
python -m pytest          # expect: 17 passed
```

## 2. Get the data

You can forecast immediately with what's in the folder. To **calibrate** the
model, add the historical match file — see **`DATA_REQUIRED.md`** for the exact
files, schemas, and where to download them. The single most useful addition is
`backtest/data/results.csv` (auto-downloads on a networked machine).

## 3. The 60-second path

```bash
python scripts/build_and_forecast.py            # full run (10,000 sims)
python scripts/build_and_forecast.py --quick    # fast run (2,000 sims)
```

This one command does everything: calibrates the goals model (if the historical
data is present), runs the tournament forecast with the calibrated model,
attaches Monte Carlo standard errors, shows how sensitive the picks are to the
uncertainty settings, compares to the market (if you've added odds), and writes
a dated forecast to `outputs/forecast_YYYY-MM-DD.csv`.

If the historical data isn't present yet, it still forecasts — it just tells you
it's using the uncalibrated model and points you to `DATA_REQUIRED.md`.

---

## 4. Using the tournament forecaster

### 4.1 Read the forecast table

Each row is a team; columns are the probability (%) of reaching each round:

```
              Elo  Conf  Grp    SF  Final   Win  Win_SE
Spain        2171  UEFA    H  ...   ...    22.4    0.42
Argentina    2113  CON...  J  ...   ...    14.4    0.36
```

- `Win` is the champion probability. `Win_SE` is its **Monte Carlo standard
  error** in percentage points — the noise from simulating rather than computing.
  At 10,000 sims a favourite's `Win` is good to roughly ±0.4pp; if two teams are
  within a standard error or two of each other, treat them as tied.
- Don't over-read a single champion number. A 48-team knockout is high-entropy;
  even the best side tops out around 15–22%. The model's value is the **whole
  distribution and its calibration**, not the one pick.

### 4.2 Calibrated vs legacy goals model

The pipeline uses the **calibrated Dixon-Coles model** if `params/goals_params.json`
exists (created when you fit on real data), otherwise the original ad-hoc map.
To run it yourself in Python:

```python
import sys; sys.path.insert(0, "src")
import wc2026 as E
elo = E.load_elo()
gm  = E.GoalsModel.load("params/goals_params.json")   # calibrated model
probs = E.run_monte_carlo(elo, goals_model=gm)         # omit goals_model for legacy
print(probs.head(16))
```

To (re)fit the goals model on your historical data:

```bash
python backtest/fit_goals_model.py     # fits by MLE, saves params/goals_params.json
```

### 4.3 Rating uncertainty (the sigmas) — and how to choose them

`SIGMA_TEAM` and `SIGMA_CONF` widen the outcome distribution to reflect that Elo
isn't a perfect strength estimate (drawn once per simulated tournament, so a
team that's secretly better is better in all its games). They are the **least
calibrated** part of the model. Rather than trust a single guessed value, the
pipeline prints a **sensitivity table** showing the champion picks at three
settings — off `(0,0)`, default `(40,35)`, and wide `(80,70)`. Use it: if the
ordering is stable across settings (it usually is), the sigmas aren't
load-bearing and the default is fine; if a pick flips, you've learned it's
fragile. Override explicitly when running yourself:

```python
E.run_monte_carlo(elo, goals_model=gm, sigma_team=40, sigma_conf=35)
```

### 4.4 Model vs market

Add outright odds to `data/odds_champion.csv` (`team,odds` decimal — see
`data/odds_champion.example.csv`) and the pipeline prints a comparison:
`Edge(pp)` = your model minus the de-vigged market; `Edge_x > 1` means the model
rates a team higher than the book. **Read this as a sanity check, not a betting
signal.** Your model uses less information than the market (no injuries,
lineups, money flow), so a large "edge" is more likely a model blind spot than
value. The right use is to find where your model and the market *disagree* and
ask why.

### 4.5 Updating as the tournament unfolds

1. A match finishes → open `wc2026_results.xlsx`, find the fixture's row, type
   the score in the yellow Home/Away cells, **save**. (Knockout penalty win:
   put `H` or `A` in the PK column.)
2. Re-run `python scripts/build_and_forecast.py`. The header switches to
   `DYNAMIC (N group + M KO results)`. The engine fixes the played matches,
   updates Elo from them, and re-simulates only the remainder; eliminated teams
   drop to 0%.

### 4.6 After the group stage — pin the real third-place allocation

The knockout bracket depends on which third-placed teams qualify and where they
slot, which FIFA fixes via a published table. Until you set it, the engine uses
a valid approximation. To see who's in each knockout match and to set the
official mapping:

```python
import sys; sys.path.insert(0, "src"); import wc2026 as E
elo = E.load_elo(); kg, kk = E.load_results("wc2026_results.xlsx")
E.show_fixtures(elo, kg, kk)                       # resolved fixtures
override = {74:"B", 77:"C", 79:"E", 80:"H", 81:"F", 82:"A", 85:"I", 87:"J"}  # EXAMPLE
probs = E.run_monte_carlo(elo, kg=kg, kk=kk, third_override=override)
```

---

## 5. Using the match/feature model (the trust layer)

These live in `backtest/`. They tell you whether the forecaster is any good and
which variables matter. Run them after you've added `backtest/data/results.csv`.

```bash
cd backtest
python backtest.py            # OOS scorecard, walk-forward CV, market benchmark
python feature_importance.py  # incremental OOS value of candidate variables
python fit_goals_model.py     # fit the Dixon-Coles model + recovery checks
python validate_synthetic.py  # ground-truth checks that the harness is sound
python validate_features.py
```

How to read them:

- **`backtest.py`** prints a pooled out-of-sample scorecard (log-loss, RPS,
  Brier). The engine should beat the base rate and the Elo-logistic; whether it
  beats the **market** row (if you added match odds) is the real test.
- **`feature_importance.py`** scores each candidate variable (squad value, rest,
  competitive-vs-friendly) by its *incremental* log-loss **over Elo**, with a
  bootstrap CI and a noise-feature control. A feature only "matters" if its CI
  sits clearly above zero. See `backtest/README_FEATURE_IMPORTANCE.md`.
- To test **squad market value**, pass a Transfermarkt table:
  `build_features(df, mv_table=...)` (schema in `DATA_REQUIRED.md`).
- To turn on the **market benchmark** in the backtest, either put `oh,od,oa`
  columns in `results.csv` or call `attach_match_odds(df, "data/match_odds.csv")`.

---

## 6. Interpreting results honestly (the part most people skip)

- **Calibration > champion pick.** Success is "when the model says 60%, it
  happens ~60% of the time," not "it called the winner." Read the reliability
  curve from `backtest.py`, not just the top of the table.
- **The market is the ceiling, not the target.** Beating the base rate and Elo
  is table stakes; the realistic goal is well-calibrated probabilities that
  modestly beat Elo-only and *track* the market. Treat a big model-vs-market gap
  as a hypothesis to investigate, not money on the table.
- **One variable, really.** Everything keys off Elo. Features earn their place
  only by adding OOS log-loss *over* Elo — which the feature study measures.
- **Sigmas are priors, not truths.** Use the sensitivity table; don't present a
  tight champion number as if the uncertainty settings were calibrated.

---

## 7. File map (where things live)

```
scripts/build_and_forecast.py   the one-command pipeline (start here)
scripts/run_forecast.py         the original CLI (legacy model, unchanged)
src/wc2026/                     the engine package (import wc2026 as E)
params/goals_params.json        the calibrated goals model (created by fitting)
backtest/                       evaluation suite + READMEs
wc2026_elo.csv                  team strengths  (REQUIRED input)
wc2026_results.xlsx             live results entry (REQUIRED for dynamic runs)
data/odds_champion.csv          outright odds (optional; header-only template)
data/match_odds.csv             match odds (optional)
outputs/forecast_<date>.csv     your saved forecasts
docs/METHODOLOGY.md             the why, and the ship-readiness assessment
DATA_REQUIRED.md                what data to add and where to get it
STRUCTURE.md                    project layout + design rationale
```

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError` | `pip install numpy pandas openpyxl scipy matplotlib` |
| "using the uncalibrated model / no historical dataset" | add `backtest/data/results.csv` (see `DATA_REQUIRED.md`) and re-run |
| Forecast says PRE-TOURNAMENT after you entered scores | you didn't **save** the Excel file, or you ran from the wrong folder |
| A match you entered isn't counted | both Home and Away goals must be filled; text in a goal cell is ignored on purpose |
| Knockout fixtures show "? vs ?" | normal until the feeding matches are entered |
| `'wc2026_results.xlsx' is locked` | it's open in Excel — save and close it, then re-run |
| Numbers shift slightly between runs | expected (Monte Carlo); raise iterations or read the `_SE` columns |
| pytest crashes on cleanup in a sandbox | `python -m pytest --basetemp=/tmp/pt` |

---

## 9. Daily loop (quick reference)

```
1.  Match ends.
2.  Type the score on its row in wc2026_results.xlsx, save.
3.  python scripts/build_and_forecast.py
4.  Read the updated probabilities (+ Win_SE) and the model-vs-market gap.
5.  After the group stage: show_fixtures(), then set third_override.
6.  Keep wc2026_elo.csv FROZEN once the tournament starts.
```
