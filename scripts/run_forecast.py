"""Command-line entrypoint — identical behaviour to the original
`python wc2026_engine.py`, but driven by the wc2026 package.

Run from the project root:
    python scripts/run_forecast.py
"""
import os
import sys

# make the src/ layout importable without installation
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import wc2026 as E


def main():
    elo = E.load_elo()
    kg, kk = E.load_results()
    state = "PRE-TOURNAMENT" if not (kg or kk) else f"DYNAMIC ({len(kg)} group + {len(kk)} KO results in)"
    print(f"=== Forecast — {state} ===")
    probs = E.run_monte_carlo(elo, kg=kg, kk=kk)
    print(probs.head(16).to_string())

    if not (kg or kk) and not os.path.exists("wc2026_forecast_exante.csv"):
        E.save_forecast(probs)

    print("\n=== Model vs Market (champion) ===")
    print(E.compare_to_market(probs).to_string())

    print("\n=== One simulated road to the final ===")
    sched, champ = E.simulate_schedule(elo, seed=E.SEED, kg=kg, kk=kk)
    print(sched[sched.Round.isin(["R16", "QF", "SF", "3rd", "Final"])].to_string(index=False))
    print(f"\nSimulated champion this run: {champ}")

    if 104 in kk:
        E.score_forecast(kg=kg, kk=kk)


if __name__ == "__main__":
    main()
