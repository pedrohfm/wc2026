# Evaluation: penaltyblog as a refinement

`penaltyblog` (martineastwood) was evaluated as an *additive* source of data and
modelling improvements — not a rewrite. Findings below are evidence-based, run on
our own historical dataset (international fixtures since 2002, held-out test from
2022 onward).

## What the library offers

- **Goal models**: Poisson, Dixon–Coles, bivariate Poisson, negative-binomial,
  zero-inflated Poisson, Weibull-copula, and Bayesian/hierarchical variants —
  all team attack/defence specifications, with optional time-decay weighting.
- **Ratings**: Elo, Massey, Colley, Pi.
- **Implied odds**: margin-removal methods beyond proportional (Shin, power,
  additive).
- **Metrics**: RPS, Brier, ignorance.
- **Scrapers**: FBRef, Understat, ClubElo, football-data.co.uk.

## Assessments

**Goal model (team attack/defence Dixon–Coles).** Tested directly: penaltyblog's
Dixon–Coles model fitted on our training data scored an out-of-sample log loss of
**0.897**, versus **0.882** for our existing Elo-based Dixon–Coles model on the
identical 4,375 test fixtures. The library model is therefore **worse on this
problem**, for two structural reasons: international schedules are sparse and
irregular, so per-team attack/defence parameters are noisily identified; and the
club-oriented specification assumes a home/away venue, whereas a large share of
international fixtures are at neutral venues. *Decision: do not adopt — it would
reduce accuracy and constitute a rewrite.*

**Data scrapers.** FBRef, Understat, ClubElo, and football-data.co.uk are
club-competition sources. They do not provide the national-team match history,
Elo, or outright markets this project requires. Our existing stack (martj42
results, eloratings.net, The Odds API, Transfermarkt) is better suited.
*Decision: do not adopt for data.*

**Implied-odds methods (Shin, power).** A legitimate refinement to market
de-vigging relative to the proportional method. The benchmark harness already
includes a Shin option; the live blend currently uses the proportional method.
*Decision: available as an option; immaterial to the headline forecast, not
adopted by default.*

**Time-decay weighting (the one adopted refinement).** penaltyblog's Dixon–Coles
weighting motivates weighting recent matches more heavily in the likelihood. We
implemented this in-house (no new runtime dependency) and validated it: holding
the train/test split fixed, exponential time decay reduced out-of-sample log loss
monotonically as the half-life shortened —

| Half-life | OOS log loss | vs no decay |
|---|---|---|
| none | 0.8817 | — |
| 4 years | 0.8803 | −0.0014 |
| 2 years | 0.8799 | −0.0018 |
| 1 year | 0.8796 | −0.0021 |

A two-year half-life was adopted as a robust default (the gain is consistent and
the effective sample remains large; a one-year half-life is marginally better but
carries more variance). This is now applied in the production goals-model fit
(`HALF_LIFE_YEARS` in `scripts/build_and_forecast.py`); setting it to `0`
restores equal weighting exactly, so the change is fully reversible.

## Conclusion

The headline finding is consistent with the project's prior results: our
purpose-built international model outperforms an off-the-shelf club model
out-of-sample, and gains come from information and disciplined estimation rather
than added model complexity. The single worthwhile refinement from penaltyblog —
time-decay weighting — was adopted, in-house and reversibly, for a small but
genuine improvement.
