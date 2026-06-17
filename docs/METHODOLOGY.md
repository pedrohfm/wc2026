# World Cup 2026 forecasting engine — methodology & status

## Governing message

The project began as a clean Monte Carlo **simulator** whose entire behaviour
flowed from one input (Elo) through six hand-set constants that had never been
scored on a real match. It is now a **forecasting pipeline**: the match model is
fit by maximum likelihood, every claim is testable out-of-sample on the same
walk-forward scaffold, and the constants are being replaced by calibrated
values. The honest objective has also been reframed — away from "confidently
pick the champion" (irreducibly luck-dominated in a 48-team knockout) and toward
**calibrated probabilities that beat Elo-only and are measured against the
market**.

Three things follow and recur throughout: there is effectively *one* strength
variable (Elo), so "predictive power" only means *incremental* value over Elo;
the **market is the ceiling**, not the target, because the model uses strictly
less information; and several constants are **jointly identified with the Elo
spread**, so they must be calibrated together, never copied from another system.

---

## 1. Model architecture

A team's strength is a single Elo rating. A match turns the pre-match Elo gap
into two goal rates; a tournament is 104 such matches resolved through the real
fixture and knockout structure, repeated 10,000 times to produce round-by-round
and champion probabilities.

The match model has two implementations, selectable at run time:

- **Legacy (as shipped):** `lambda = base * sqrt(w/(1-w))` with `w` a logistic
  of the Elo gap (`base=1.35`, `GOAL_SCALE=600`), then **independent** Poisson
  goals. Constants chosen by judgement.
- **Calibrated (the upgrade):** a **Dixon-Coles** model fit by MLE,
  `log lambda_home = mu + gamma * d_eff/400`, `log lambda_away = mu - gamma * d_eff/400`,
  with `d_eff = (elo_home - elo_away) + home_elo * home_flag`, and a low-score
  correction `tau(rho)` that restores the right draw mass and the mild negative
  goal correlation. Parameters `(mu, gamma, home_elo, rho)` are estimated on
  historical matches and saved to `params/goals_params.json`.

The two are parameter-equivalent at the centre (`mu ≈ ln base`,
`gamma ≈ 400·ln10 / (2·GOAL_SCALE)`, `rho = 0` reproduces independent Poisson),
so the upgrade is an interpretable refinement, not a black box. The calibrated
model drops into the Monte Carlo through an optional `goals_model=` argument;
when it is absent the engine reproduces the original behaviour **byte-for-byte**
(enforced by parity tests).

---

## 2. The original critiques and what was done about each

| Critique (review) | Status | Evidence |
|---|---|---|
| Constants guessed, never scored | **Addressed** | Backtest harness scores OOS log-loss; `GOAL_SCALE`/`gamma` now fit by MLE. |
| Independent Poisson under-predicts draws | **Fixed + measured** | Dixon-Coles `rho` fit < 0; OOS draw rate moves from 19.9% to 23.3% vs 22.4% actual (synthetic). |
| Ad-hoc goals map double-transforms Elo | **Replaced** | Single log-linear MLE form supersedes the sqrt map. |
| Confederation shock discards real signal | **Open (by choice)** | Mean-zero shock retained; estimating confederation effects is a future feature. |
| Home advantage a flat guessed 60 | **Calibratable** | `home_elo` is now a fitted parameter (synthetic fit ≈ correct under oracle). |
| Single-seed headline, no MC error | **Partially** | CV pools many folds; per-run MC standard errors still to be reported. |
| "Predict the winner" is the wrong objective | **Reframed** | Success = calibration + log-loss vs benchmarks, not champion accuracy. |
| Market edge likely reflects model blind spots | **Built into framing** | Market is a scored benchmark and the explicit ceiling, not the target. |

The team/confederation rating noise was reviewed and found **structurally
correct** (drawn once per simulated tournament, held fixed across its matches —
genuine strength uncertainty, not per-match noise); only its magnitude is
uncalibrated.

---

## 3. The evaluation harness (`backtest/`)

Everything is judged out-of-sample, leakage-free, on the same scaffold:

- **Rolling pre-match Elo** replays history in date order; every match is
  predicted using only prior information.
- **Walk-forward (expanding-window) CV**: each fold re-fits the knobs on
  everything before it, predicts the fold blind, and all folds are pooled and
  scored once.
- **Proper metrics**: log-loss (headline), Ranked Probability Score (the
  football-appropriate ordinal rule), multiclass Brier, accuracy, and a
  reliability curve (the calibration test that matters more than any single
  pick).
- **Benchmarks**: a no-skill base rate, an Elo-logistic (Davidson) model, and —
  when odds columns are present — the **de-vigged market**, scored on the same
  rows as the engine. A feature or model only has *edge* if it beats the market;
  beating the base rate and Elo-logistic is merely *fit*.

### Feature importance (`feature_importance.py`)

To answer "do squad market value, rest/travel, and competitive-vs-friendly
weight actually help?", an ordered-logit W/D/L model is fit each fold and every
candidate is scored by **incremental OOS log-loss over a model that already
contains Elo** — marginal (added on top of Elo) and unique (lost if dropped from
the full model) — each with a paired-bootstrap 95% CI. A deliberate noise
feature is included as a negative control. On synthetic data with known truth,
the three real features land with CIs strictly above zero and the noise feature
straddles zero — i.e. the harness does not manufacture importance, and even a
model carrying all the real features still loses to a sharp market.

---

## 4. Validation evidence

Because this sandbox can't reach the full historical dataset, the **instruments
are validated against synthetic data-generating processes with known truth**,
which is the correct way to unit-test a forecasting harness. On the user's
machine the identical code paths run on real internationals (auto-downloaded).

What the synthetic validations establish:

- The GOAL_SCALE/`gamma` fitter is **unbiased given correct ratings** (oracle
  recovers the true value); on online Elo it shifts predictably, demonstrating
  the scale-vs-rating-spread entanglement.
- Dixon-Coles `rho` is recovered almost exactly (−0.106 vs −0.110 truth) and is
  **scale-independent**, and it improves OOS log-loss and draw calibration.
- The calibrated DC-MLE model **beats the ad-hoc map out-of-sample** and plugs
  into the tournament Monte Carlo (17/17 unit + parity tests pass).
- Feature-importance recovers the true ordering and passes its negative control.

These are demonstrations that the *machinery is sound*. They are **not** a claim
about the real model's accuracy — that number comes from running the harness on
real data, which is the first un-ticked box below.

---

## 5. Calibration status (fitted vs still guessed)

| Parameter | Was | Now |
|---|---|---|
| `gamma` / `GOAL_SCALE` | guessed 600 | MLE-fit (jointly with Elo spread) |
| `rho` (draw correction) | absent | MLE-fit (new) |
| `home_elo` / `HOME_ADV` | guessed 60 | MLE-fit |
| `mu` / `base` | guessed 1.35 | MLE-fit |
| `SIGMA_TEAM`, `SIGMA_CONF` | guessed 40 / 35 | **still guessed** — calibrate against historical tournament round-reach frequencies (separate study) |
| Confederation effects | mean-zero (off) | **not yet estimated** |

---

## 6. Are we ready to ship?

**Not yet — the engineering is ready, the empirical calibration is not.** The
distinction is the whole point of the project. What exists now is a sound,
tested, well-structured instrument and a *demonstrated* method; what's missing
is the one thing that turns it into a trustworthy forecast: **running it on real
data and reading the verdict.** Concretely, the gates before shipping:

1. **Run the backtest and fit on real internationals.** One command on a
   networked machine. Until the real OOS log-loss and reliability curve exist,
   the engine's accuracy is unverified. *(This is the single blocking item.)*
2. **Pin the real market as the benchmark.** Add closing odds and confirm where
   the engine sits relative to the line. Expect to lose to it; the question is
   by how much, and whether any feature narrows the gap.
3. **Calibrate the tournament-dispersion sigmas** against historical round-reach
   frequencies (a separate calibration from match log-loss).
4. **Write the fitted parameters into `config.py`** and flip the provenance note
   from "reasoned defaults" to "fitted on <data, date>".
5. **Operational correctness for 2026 specifically:** pin FIFA's official
   third-place allocation once published (the engine uses a valid approximation
   until then), and confirm the 48-team field/Elo snapshot is current and dated.
6. **Report Monte Carlo standard errors** on the headline probabilities (or
   average over seeds) so the numbers carry their own uncertainty.

Items 1–2 are substantive (they decide whether the model is any good); 3–6 are
finishing work. None require new architecture — the harness already produces
each output; they need real data and a calibration pass.

A blunt caveat to carry into shipping: even fully calibrated, this is an
Elo-plus-a-few-features model competing with a market that prices injuries,
lineups, and money flow. The realistic ambition is **well-calibrated
probabilities that modestly beat Elo-only and track the market**, not a
market-beating edge. Selling it as more than that would be the least rigorous
thing in the whole project.

---

## 7. How to run everything

```bash
# forecast (legacy engine, unchanged behaviour)
python scripts/run_forecast.py

# forecast with the calibrated Dixon-Coles model
python backtest/fit_goals_model.py          # fits + saves params/goals_params.json
#   then in Python:
#   import wc2026 as E
#   gm = E.GoalsModel.load("params/goals_params.json")
#   probs = E.run_monte_carlo(E.load_elo(), goals_model=gm)

# evaluation
cd backtest
python backtest.py            # OOS scorecard, walk-forward CV, market benchmark
python feature_importance.py  # incremental OOS value of candidate variables
python validate_synthetic.py  # harness ground-truth checks
python validate_features.py
python fit_goals_model.py      # model fit + recovery checks

# prove the refactor changed nothing + the new model path works
python -m pytest               # 17 passed
```

See also `STRUCTURE.md` (layout), `backtest/README_BACKTEST.md` (metrics &
benchmarks) and `backtest/README_FEATURE_IMPORTANCE.md` (the incremental-value
framing).

---

## 8. "Ultimate model" upgrades — one win and two honest negatives

After the model was validated on real data (well-calibrated, ECE 0.025, ~16%
better than no-skill, but tied with one-line Elo-logistic and beaten by the
market), three upgrades were attempted to push past the Elo ceiling. Reporting
all three outcomes, because the negatives are as informative as the win.

**WIN — model + market blend (`src/wc2026/blend.py`).** Because the market
out-predicts the model out-of-sample, combining them beats either alone. A
linear (or log-opinion-pool) blend of the model and de-vigged market, validated
on synthetic (the optimiser finds the market-leaning weight and the blend's
log-loss is below both components), is now the headline market-aware output
(STEP 7 of the pipeline). Weight defaults to 30% model / 70% market — a prior,
since champion-level data can't tune it; `optimize_blend_weight()` tunes it at
match level once you supply historical match odds.

**NEGATIVE — feeding match-importance into the goals engine doesn't help.** Two
principled forms were tested out-of-sample on competitive matches: (a) fitting
the goals model on competitive matches only, and (b) a friendly×gap interaction
that applies the steeper "competitive" slope to World Cup games. Both were
*slightly worse* than the plain all-data fit (0.873 vs 0.870 log-loss). The
competitive slope is steeper, which aggravates the model's known
over-concentration. Conclusion: the goals mapping is already near-optimal;
do not adopt these. The candidate for orthogonal signal was squad
market value. It has now been **obtained (all 48 teams, `data/squad_values.csv`)
and tested** — and it too is a negative on the available data: squad value is
0.80-correlated with Elo (80% redundant), and its Elo-orthogonal component shows
**no incremental signal** against teams' recent Elo-residuals (+0 Elo per SD of
orthogonal value, 95% CI [-13, +11]). So it is NOT injected into the forecast.
Caveat on power: this is a 48-team cross-sectional test using a single current
value snapshot; the definitive test needs historical (as-of-date) Transfermarkt
snapshots fed through `feature_importance.py`. The `elo_nudge_from_values()` hook
remains available if a positive, OOS-validated weight is ever established.

**NEGATIVE (degenerate) — sigma can't be cleanly calibrated.** A random-effects
estimate of the rating-uncertainty sigma from match residuals *undershot* known
truth on synthetic (29 vs 92), confirming sigma is a tournament-level parameter
that match data under-identifies. Calibrating it instead against the market's
champion dispersion (`backtest/calibrate_sigma.py`) is *degenerate*: the
optimum sits at the grid edge — the model is so much more concentrated than the
market that only an extreme, signal-destroying sigma would match it. So sigma is
kept at a transparent moderate default (with the sensitivity panel), and the
**blend** is the right way to import the market's dispersion — not sigma
inflation. This is itself the finding: over-concentration is real and large, and
the clean fix is the blend, not a knob.

**Net.** The "ultimate" configuration is: Elo → MLE Dixon-Coles → Monte Carlo,
with the outright **blended with the market**, hosts capped, and skill reported
up front. The rigorous lesson is that past the Elo ceiling, gains come from
*information* (the market; squad value if you add it), not from more modelling
on Elo alone — and we now have the evidence, not just the assertion.

### Updated run commands

```bash
python scripts/build_and_forecast.py        # skill panel + calibrated forecast + blend
python backtest/calibrate_sigma.py          # sigma-vs-market diagnostic (writes params/sigma_params.json)
python -m pytest                            # 21 passed
```
