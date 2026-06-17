# Feature importance — does a variable actually add anything?

## The framing (read this first — it's the whole ballgame)

People ask "is squad market value predictive?" and answer it by correlating
value with results. That's the wrong question and it will mislead you, because
**market value correlates ~0.8+ with Elo** — most of its apparent power is just
Elo wearing a different hat. The right question is:

> Once a model already knows the Elo gap (and ideally the market price), how much
> does this variable *add*, out-of-sample?

So every feature here is scored by **incremental OOS log-loss over a baseline
that already contains Elo**, under the same walk-forward CV as the rest of the
harness. Two numbers per feature:

- **Marginal ΔLL** — improvement of `{Elo + home + feature}` over `{Elo + home}`.
- **Unique ΔLL** — the log-loss you *lose* by removing the feature from the
  full model (its contribution net of everything else — the strict test for
  redundancy).

Each comes with a **paired-bootstrap 95% CI** on the per-match log-loss delta.
A point estimate is worthless without it: if the CI straddles 0, the feature has
**no demonstrable power**, however pretty the bar looks.

## Model

An **ordered logit** for the ordinal outcome `away-win < draw < home-win`, fit
by MLE each fold (ordinal, not multinomial, because W/D/L sit on one latent
home-favourability axis). Features enter the linear index; standardisation is
fit on the training window only. This is the conventional, parsimonious choice
in the football-forecasting literature and it nests cleanly for the ΔLL tests.

## Run

```bash
cd backtest
pip install numpy pandas scipy matplotlib
python feature_importance.py     # real data on your machine; synthetic here
python validate_features.py      # ground-truth validation (all assertions)
```

## Validation against known truth

The synthetic DGP is rigged so we *know* the answer: squad value, rest, and the
friendly×Elo interaction genuinely drive results; `noise_feat` is pure noise.
The harness recovers exactly that, out-of-sample:

```
baseline (Elo + home) OOS log-loss : 0.7469
full model OOS log-loss            : 0.6921   (total gain +0.0548)

  feature   marginal_dLL          marg_CI  marg_p   unique_dLL
  mv_diff         0.0258 [+0.0198,+0.0324]    1.00       0.0297
  rest_diff       0.0141 [+0.0096,+0.0184]    1.00       0.0159
  fr_x_elo        0.0113 [+0.0077,+0.0153]    1.00       0.0135
  noise_feat     -0.0003 [-0.0008,+0.0001]    0.10      -0.0003   <- negative control

MARKET CEILING (4,383 odds-available matches):
  market 0.8177  vs  full feature model 0.8299  -> market still ahead
```

Two lessons baked into this result:

1. **The negative control works.** `noise_feat`'s CI straddles 0 — the harness
   does *not* manufacture importance from nothing. If you ever see a junk
   feature score "significant", your CV has a leak.
2. **Real features ≠ market edge.** Even a model carrying *all three* genuinely
   predictive variables still loses to a sharp market. Adding features lowers
   your log-loss; it does not entitle you to beat the closing line. Edge is a
   far higher bar than fit, and on priors you should expect the market to win.

## Plugging in your real data

`build_features()` produces these **strictly pre-match** columns from the
standard martj42 schema, no extra data required:

- `elo_diff` — pre-match rolling Elo gap (the incumbent baseline).
- `home_flag` — 1 if not neutral.
- `rest_diff` — days since each team's previous match (computed from prior
  fixtures only).
- `friendly`, `fr_x_elo` — competitive-vs-friendly weight from the `tournament`
  string, and its interaction with the Elo gap (favourites are softer in
  friendlies).

Two features need data the base dataset doesn't carry — supply them and they
light up automatically:

- **Squad market value** (`mv_diff`): pass a long table `[team, date, value]`
  (e.g. Transfermarkt snapshots) to `build_features(df, mv_table=...)`. It does
  an **as-of merge** — the most recent value *strictly before* each match — so
  there is no look-ahead. Use the value *as of the match date*, never current.
- **Travel/altitude**: add a `dist_diff` column from venue coordinates; same
  leakage rule (known pre-match, so always fine).

Add a decimal-odds column-set (`oh/od/oa`, `psh/psd/psa`, `b365*`, `avg*`) to
get the **market ceiling** for free.

## Honest caveats / how not to fool yourself

- **Collinearity** compresses unique ΔLL. A feature can be genuinely
  informative yet show a small *unique* number because a correlated feature
  already carries the signal — read marginal and unique together.
- **Multiple comparisons.** Testing many candidates inflates false positives.
  The bootstrap CI is the first guard; if you test a long list, treat a single
  marginally-significant feature with suspicion and demand it replicate on a
  later hold-out.
- **Leakage is the silent killer.** Every feature here is pre-match by
  construction; if you add your own, the rule is absolute — it must be knowable
  *before kickoff*, and any fitted transform (means, stds, value snapshots) must
  use training data only.
- **The tournament target ≠ the match target.** This scores *match* W/D/L. A
  feature that improves match calibration usually helps the tournament forecast,
  but `SIGMA_TEAM`/`SIGMA_CONF` (which govern tournament-level dispersion) are
  calibrated separately against historical round-reach frequencies.
