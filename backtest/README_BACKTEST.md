# Backtest Harness — measuring whether the engine actually predicts

## The point in one paragraph

The engine maps **Elo → goals** through six hand-set constants (`GOAL_SCALE`,
`HOME_ADV`, `K`, `base`, `SIGMA_TEAM`, `SIGMA_CONF`) that have **never been
scored on a real match**. Without that, any champion probability it prints is
an *unfalsifiable* number. This harness is the missing instrument: it replays
real international matches in date order, assigns each one a **leakage-free
pre-match Elo**, turns the engine's `expected_goals()` into analytic
**P(Home / Draw / Away)**, and scores those probabilities **out-of-sample**
with proper metrics — then checks the three critiques from the model review.

A model has *predictive power* only if it beats benchmarks **out-of-sample**.
This harness makes that test runnable.

---

## How to get YOUR real numbers (one command)

```bash
cd backtest
pip install numpy pandas matplotlib
python backtest.py
```

On your machine it auto-downloads the standard open dataset
(`martj42/international_results`, ~48k matches, 1872→today), caches it to
`backtest/data/results.csv`, and runs the full backtest on internationals from
2002 onward. If you are offline, drop that `results.csv` into `backtest/data/`
yourself and re-run. (This environment is firewalled to PyPI only, so the
shipped run here uses the synthetic validation below — but the code path for
real data is identical.)

Output: an out-of-sample scorecard, the three critique tests, and a reliability
+ `GOAL_SCALE` calibration figure in `backtest/outputs/`.

---

## What it measures

**Metrics (all out-of-sample, lower = better except accuracy):**

- **Log-loss** — the headline. Punishes confident wrong calls; this is what you
  minimise to calibrate the knobs.
- **RPS (Ranked Probability Score)** — the football-specific scoring rule. It
  rewards being *close* on an ordered outcome (predicting a draw when the away
  team wins is penalised less than predicting a home win).
- **Multiclass Brier** and **accuracy** — secondary.
- **Reliability curve** — does "when the model says 60%, it happens ~60% of the
  time?" This is calibration, and it is the right success criterion — not
  whether the single champion pick was correct.

**Benchmarks it must beat (a model with no edge ties these):**

1. **Base rate** — the unconditional Home/Draw/Away frequencies. No skill.
2. **Elo-logistic (Davidson)** — Elo straight into W/D/L with one fitted draw
   parameter. If the engine's whole goals apparatus can't beat this, the
   apparatus is adding nothing.
3. *(You supply)* **Market odds** — de-vigged closing prices. This is the real
   bar. Beating 1–2 is table stakes; beating the market is the actual claim,
   and on priors you should expect **not** to, because the engine uses strictly
   less information (no injuries, lineups, momentum, money flow).

---

## The three critiques, made testable

| # | Critique | How the harness tests it |
|---|----------|--------------------------|
| (a) | Independent Poisson **under-predicts draws** | Compares mean predicted P(draw) to the realised draw rate OOS. |
| (b) | **Dixon–Coles** low-score correction should help | Fits `rho` on the training window, scores DC vs independent Poisson OOS. |
| (c) | The six **knobs are guessed, not calibrated** | Sweeps `GOAL_SCALE` (and `HOME_ADV`) to the OOS-log-loss optimum and compares to the engine default of 600. |

---

## Synthetic validation (proving the instrument before trusting it)

Because the full continuous history can't be reached from this sandbox, the
shipped run validates the **harness itself** against a known data-generating
process: teams get hidden true strengths, scores are drawn from the engine's
own `expected_goals()` at a known `GOAL_SCALE`, with a known Dixon–Coles draw
inflation. A correct harness must recover those truths. Result:

```
[ORACLE]  true GOAL_SCALE=520  recovered=520            -> PASS

OUT-OF-SAMPLE SCORES (n=3,200 test matches)
  Base rate (no skill)                logloss 1.0659   rps 0.4702
  Elo-logistic (Davidson)             logloss 0.9691   rps 0.4015
  Engine: default GOAL_SCALE=600      logloss 0.9825   rps 0.4077
  Engine: fitted GOAL_SCALE=800       logloss 0.9651   rps 0.4000
  Engine: +Dixon-Coles rho=-0.070     logloss 0.9655   rps 0.4000

CRITIQUE TESTS
  (a) DRAW BIAS  — indep. Poisson predicts 19.9% draws; actual 22.6%  (-2.7pp)
  (b) DIXON-COLES — fitted rho=-0.070; OOS basically tied here
  (c) KNOB CALIBRATION — OOS-optimal GOAL_SCALE≈800 vs default 600
                          logloss 0.9651 vs 0.9825

ALL VALIDATION ASSERTIONS PASSED
```

Run it yourself: `python validate_synthetic.py`.

### Two lessons that already fall out, before any real data

1. **The default `GOAL_SCALE=600` is not optimal even on the engine's own DGP**
   — calibration cut OOS log-loss from 0.9825 to 0.9651. The number you ship
   matters, and "sensible by taste" left ~1.8% of log-loss on the table here.

2. **`GOAL_SCALE` is only meaningful *relative to the Elo spread you feed it*.**
   The oracle (fed the *true* strengths) recovered 520 exactly; the end-to-end
   run (rebuilding Elo online) preferred 800 — not a bug, but the scale
   absorbing the mismatch between online-Elo dispersion and true-strength
   dispersion. **Implication:** you cannot tune `GOAL_SCALE` in isolation. It is
   jointly identified with the `K`/MoV settings that determine how wide your Elo
   ratings spread. Calibrate them *together*, and never copy a `GOAL_SCALE`
   from another system that uses different ratings.

(The Dixon–Coles gain looks small on this particular synthetic DGP because at
the recalibrated scale independent Poisson already fits the draw mass tolerably;
the draw-rate diagnostic (a) still exposes the systematic gap. On **real** data,
where draw structure is messier, this is the comparison to watch.)

---

## Files

- `backtest.py` — the harness (data load, rolling Elo, engine probabilities,
  metrics, benchmarks, `GOAL_SCALE`/`rho` calibration, reliability plot).
- `validate_synthetic.py` — synthetic ground-truth validation; run as a test.
- `outputs/` — figures and any saved scorecards.
- `data/` — cached `results.csv` (created on first online run).

## Market benchmark + walk-forward CV (now wired in)

`run_cv()` is the upgraded path: **expanding-window cross-validation**. Elo runs
online over the whole stream (leakage-free); for each fold the knobs
(`GOAL_SCALE`, Dixon-Coles `rho`, Davidson `nu`) are **re-fitted on everything
before the fold**, frozen, and used to predict that fold. All folds' OOS
predictions are pooled and scored once, so every test match was predicted by a
model blind to it. You get a per-fold table (incl. each fold's fitted scale)
and a pooled scorecard.

The **market benchmark** activates automatically when the dataset has decimal-
odds columns — any of `oh/od/oa`, `psh/psd/psa` (Pinnacle), `b365h/b365d/b365a`,
`avgh/avgd/avga`. It de-vigs (proportional or Shin) and scores the market on the
odds-available subset, plus the engine on the *same rows* for a like-for-like
comparison. This is the only test that separates **edge** from **fit**.

Demonstration on the synthetic DGP with a fabricated (deliberately sharp)
bookmaker — note the engine correctly **loses to the market**, as it should
given it uses less information:

```
POOLED OUT-OF-SAMPLE SCORECARD (6 expanding folds, n=4,800)
  Base rate (no skill)                  logloss 1.0761
  Elo-logistic (Davidson)               logloss 0.9637
  Engine: default GOAL_SCALE=600        logloss 0.9788
  Engine: fitted GOAL_SCALE (per fold)  logloss 0.9638
  Engine: + Dixon-Coles (per fold)      logloss 0.9619
  MARKET (de-vigged)                    logloss 0.9430   <- sharpest
    Engine (same rows as market)        logloss 0.9707

CRITIQUE TESTS (pooled OOS)
  (a) DRAW BIAS  — indep. Poisson 19.9% vs actual 25.0%   (-5.2pp)
  (b) DIXON-COLES — 0.9619 vs 0.9638                       (better)
  (c) KNOB CALIBRATION — 0.9638 vs default 0.9788
  (d) MARKET — market 0.9430 vs engine 0.9707             -> NO edge (market wins)
```

To score YOUR real data against the market, add an odds column-set to
`backtest/data/results.csv` (the base martj42 file has none) and re-run.

## Honest limitations / next steps

- **Single split vs CV.** `run()` (single split) is kept for a quick look;
  `run_cv()` (walk-forward) is the robust estimate and is now the default in
  `__main__`.
- **Elo is the only feature.** Once the harness is on real data, add candidate
  features (squad market value, rest/travel, competitive-vs-friendly weight,
  confederation effects) and measure each one's *incremental* OOS log-loss — the
  only honest definition of a variable's predictive power.
- **`SIGMA_TEAM`/`SIGMA_CONF`** affect the *tournament* dispersion, not single
  matches, so they are calibrated against historical tournament round-reach
  frequencies, not the match log-loss here — a second, separate calibration.
