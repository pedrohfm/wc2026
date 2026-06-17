"""Unit tests for the data-fetch parsers (no network: mock payloads only)."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import fetch_odds as F

MOCK = [
    {"commence_time": "2026-06-20T18:00:00Z", "home_team": "Turkey", "away_team": "United States",
     "bookmakers": [
         {"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
             {"name": "Turkey", "price": 2.6}, {"name": "United States", "price": 2.7}, {"name": "Draw", "price": 3.3}]}]},
         {"key": "bet365", "markets": [{"key": "h2h", "outcomes": [
             {"name": "Turkey", "price": 2.5}, {"name": "United States", "price": 2.8}, {"name": "Draw", "price": 3.2}]}]}]},
]
OUTRIGHTS = [
    {"bookmakers": [{"key": "pinnacle", "markets": [{"key": "outrights", "outcomes": [
        {"name": "Spain", "price": 5.5}, {"name": "Ivory Coast", "price": 80.0}]}]},
                    {"key": "bet365", "markets": [{"key": "outrights", "outcomes": [
        {"name": "Spain", "price": 5.7}]}]}]},
]


def test_h2h_averages_and_normalizes():
    df = F.parse_h2h(MOCK)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["home"] == "Türkiye" and row["away"] == "United States"   # name-normalized
    assert abs(row["oh"] - 2.55) < 1e-9                                   # averaged across books
    assert abs(row["od"] - 3.25) < 1e-9
    assert row["date"] == "2026-06-20"


def test_h2h_skips_incomplete():
    bad = [{"commence_time": "2026-06-20", "home_team": "A", "away_team": "B",
            "bookmakers": [{"markets": [{"key": "h2h", "outcomes": [{"name": "A", "price": 2.0}]}]}]}]
    assert F.parse_h2h(bad).empty          # no draw/away price -> skipped


def test_outrights_average_and_normalize():
    o = F.parse_outrights(OUTRIGHTS)
    assert abs(o["Spain"] - 5.6) < 1e-9                  # (5.5+5.7)/2
    assert o["Côte d'Ivoire"] == 80.0                    # Ivory Coast -> our spelling


def test_norm_passthrough():
    assert F.norm("Spain") == "Spain"
    assert F.norm("Czech Republic") == "Czechia"
