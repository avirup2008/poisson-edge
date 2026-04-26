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
    result = compute_signal(
        home='Arsenal', away='Chelsea',
        market='o25', odds=1.05,
        historical=MINIMAL_DF, g_atk=MINIMAL_ATK, g_def=MINIMAL_DEF,
        bankroll=1000.0,
    )
    assert result.tier == 'NO'
    assert result.kelly_stake == 0.0

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
