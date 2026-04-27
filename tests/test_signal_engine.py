import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
import pandas as pd
from api.signal_engine import compute_signal, SignalResult, GWSignals

MINIMAL_DF = pd.DataFrame({
    'HomeTeam': ['Arsenal', 'Chelsea'] * 20,
    'AwayTeam': ['Chelsea', 'Arsenal'] * 20,
    'FTHG': [2, 1] * 20,
    'FTAG': [1, 2] * 20,
})
MINIMAL_ATK = {'Arsenal': 1.1, 'Chelsea': 0.9}
MINIMAL_DEF = {'Arsenal': 0.9, 'Chelsea': 1.1}

def test_compute_signal_returns_signal_result():
    result = compute_signal(
        home='Arsenal', away='Chelsea',
        market='o25', odds=1.90,
        historical=MINIMAL_DF, g_atk=MINIMAL_ATK, g_def=MINIMAL_DEF,
    )
    assert isinstance(result, SignalResult)
    assert result.market == 'o25'
    assert result.tier in ('ELEV', 'BET', 'SIM', 'NO')
    assert isinstance(result.ev_pct, float)
    assert isinstance(result.model_p, float)

def test_compute_signal_kelly_zero_for_no_tier():
    # Fix 1: use odds=1.01 (99% implied probability) so EV is deeply negative
    # at any realistic model_p < 0.99, guaranteeing classify_signal returns 'NO'.
    # This makes the NO tier deterministic rather than relying on the model's output.
    result = compute_signal(
        home='Arsenal', away='Chelsea',
        market='o25', odds=1.01,
        historical=MINIMAL_DF, g_atk=MINIMAL_ATK, g_def=MINIMAL_DEF,
        bankroll=1000.0,
    )
    assert result.tier == 'NO'
    assert result.kelly_stake == 0.0  # the real invariant: NO tier always yields zero stake

def test_signal_result_has_date(monkeypatch):
    """SignalResult.date is propagated from the fixture dict."""
    # Use a date within GW35 (Apr 28 – May 5) so the GW calendar filter passes it through.
    FIXTURES = [{
        "home": "Arsenal", "away": "Chelsea",
        "date": "2026-04-29",
        "markets": {"o25": 1.90},
        "h2h": {"home": 2.10, "away": 3.50, "draw": 3.20},
        "totals": {},
    }]
    historical = pd.DataFrame({
        "HomeTeam": ["Arsenal"] * 20 + ["Chelsea"] * 20,
        "AwayTeam": ["Chelsea"] * 20 + ["Arsenal"] * 20,
        "FTHG": [1] * 40, "FTAG": [1] * 40,
        "Season": ["2324"] * 40,
    })
    gw = GWSignals(
        fixtures=FIXTURES,
        historical=historical,
        g_atk={}, g_def={},
        bankroll=1000,
        elo_ratings={},
    )
    results = gw.compute()
    assert len(results) > 0, "Expected at least one result"
    assert all(r.date == "2026-04-29" for r in results), \
        f"Expected date='2026-04-29' on all results, got: {[r.date for r in results]}"


def test_signal_result_date_none_when_missing(monkeypatch):
    """SignalResult.date is None when fixture has no date key."""
    import api.signal_engine as se
    # Bypass GW calendar filter so the dateless fixture passes through.
    monkeypatch.setattr(se, '_current_gw_fixtures', lambda fixtures: fixtures)
    historical = pd.DataFrame({
        "HomeTeam": ["Arsenal"] * 20 + ["Chelsea"] * 20,
        "AwayTeam": ["Chelsea"] * 20 + ["Arsenal"] * 20,
        "FTHG": [1] * 40, "FTAG": [1] * 40,
        "Season": ["2324"] * 40,
    })
    FIXTURES_NO_DATE = [{
        "home": "Arsenal", "away": "Chelsea",
        "markets": {"o25": 1.90},
        "h2h": {"home": 2.10, "away": 3.50, "draw": 3.20},
        "totals": {},
    }]
    gw = GWSignals(
        fixtures=FIXTURES_NO_DATE,
        historical=historical,
        g_atk={}, g_def={},
        bankroll=1000,
        elo_ratings={},
    )
    results = gw.compute()
    assert len(results) > 0
    assert all(r.date is None for r in results), \
        f"Expected date=None for all results, got: {[r.date for r in results]}"


def test_gw_signals_structure():
    fixtures = [
        {'home': 'Arsenal', 'away': 'Chelsea',
         'markets': {'o25': 1.90, 'btts': 1.80}},
    ]
    gw = GWSignals(
        fixtures=fixtures,
        historical=MINIMAL_DF,
        g_atk=MINIMAL_ATK,
        g_def=MINIMAL_DEF,
        bankroll=1000.0,
    )
    results = gw.compute()
    assert isinstance(results, list)
    assert all(isinstance(r, SignalResult) for r in results)
    # Fix 4: results must be sorted descending by ev_pct
    if len(results) >= 2:
        assert results[0].ev_pct >= results[-1].ev_pct
