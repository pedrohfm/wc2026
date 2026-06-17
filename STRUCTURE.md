# Project structure

The engine has been split from a single 580-line script into a cohesive
package, with the backtest harness and the personal Excel tool kept separate.
**Behaviour is unchanged** — `tests/test_parity.py` asserts the package
reproduces the original monolith byte-for-byte on identical seeds/inputs
(11/11 passing).

```
world-cup-2026/
├── src/wc2026/                # the engine, refactored (import wc2026 as E)
│   ├── config.py             # tunable knobs + MARKET_ODDS (the things to calibrate)
│   ├── structure.py          # fixtures, KO bracket, 3rd-place slots, confederations, hosts
│   ├── match_model.py        # Elo -> win expectancy / goals; score sim; Elo update rule
│   ├── tournament.py         # group play, 3rd-place allocation, one full realisation
│   ├── elo_dynamics.py       # apply known results, deterministic group resolution
│   ├── montecarlo.py         # run_monte_carlo, simulate_schedule, compare_to_market
│   └── io.py                 # load_elo/results, show_fixtures, save/score forecast
│
├── scripts/run_forecast.py   # CLI — same output as the old `python wc2026_engine.py`
│
├── tests/
│   ├── legacy_engine.py      # frozen copy of the original monolith (parity reference)
│   ├── conftest.py           # puts src/ and tests/ on the path
│   └── test_parity.py        # 11 tests: refactor == original, exactly
│
├── backtest/                 # out-of-sample evaluation (see README_BACKTEST.md)
│   ├── backtest.py           # rolling Elo, metrics, market benchmark, walk-forward CV
│   ├── validate_synthetic.py # ground-truth validation of the harness
│   └── outputs/              # reliability + CV figures
│
├── wc2026_engine.py          # ORIGINAL monolith — left in place, still runs
├── wc2026_elo.csv            # team strengths (input)
├── wc2026_results.xlsx/.csv  # actual results (input)
├── excel/                    # (suggested) move the personal prediction workbook here
│   └── WorldCup2026_PredictionEngine.xlsx
└── pyproject.toml            # package metadata + pytest config
```

## How to run

```bash
# forecast (package CLI — identical to the old script)
python scripts/run_forecast.py

# prove the refactor changed nothing
pip install pytest
python -m pytest                      # 11 passed

# out-of-sample backtest (auto-downloads data on your machine)
cd backtest && python backtest.py
```

## Why this shape

- **`config.py` isolates the six knobs.** They are the only things that should
  ever be *calibrated* (by the backtest), so they live in one place with a
  provenance note, not scattered through the logic.
- **`structure.py` is pure data**, so the bracket/3rd-place logic can be unit
  tested independently of the simulation.
- **Dependency direction is one-way:** config → structure → match_model →
  tournament → elo_dynamics → montecarlo → io. No import cycles.
- **The original file stays put** so nothing in your current workflow breaks;
  the package is the canonical version going forward, guaranteed equivalent by
  the parity tests.

## Notes / suggested follow-ups

- The personal `WorldCup2026_PredictionEngine.xlsx` is a *subjective* ex-ante/
  ex-post tracker, decoupled from the model — keeping it under `excel/` makes
  that separation explicit (move it there when convenient).
- Once the backtest yields calibrated knob values, write them into `config.py`
  and flip the docstring from "reasoned defaults" to "fitted on <data/date>".
