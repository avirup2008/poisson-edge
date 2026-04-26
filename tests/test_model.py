import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from model.poisson_edge_model import (
    build_score_matrix, extract_probabilities, poisson_pmf,
    dc_correction, elo_hw_probability, apply_elo_ensemble,
    fatigue_multiplier, calculate_ev, classify_signal, kelly_stake,
    apply_h2h_gate, check_probability_gate, check_pinnacle,
    check_structural_override, calculate_clv, ELO_RATINGS,
)

def test_probabilities_sum_to_one():
    m = build_score_matrix(1.5, 1.0)
    p = extract_probabilities(m)
    assert abs(p['hw'] + p['draw'] + p['aw'] - 1.0) < 0.001

def test_dc_correction_low_scores():
    # (0,0): 1 - lh*la*rho = 1 - 1.5*1.0*(-0.05) = 1.075
    assert dc_correction(0, 0, 1.5, 1.0) == pytest.approx(1.075)
    # (1,0): 1 + la*rho = 1 + 1.0*(-0.05) = 0.95
    assert dc_correction(1, 0, 1.5, 1.0) == pytest.approx(0.95)
    # (0,1): 1 + lh*rho = 1 + 1.5*(-0.05) = 0.925
    assert dc_correction(0, 1, 1.5, 1.0) == pytest.approx(0.925)
    # (1,1): 1 - rho = 1 - (-0.05) = 1.05
    assert dc_correction(1, 1, 1.5, 1.0) == pytest.approx(1.05)
    # (2,2): pass-through branch always returns 1.0
    assert dc_correction(2, 2, 1.5, 1.0) == 1.0

def test_elo_arsenal_vs_spurs():
    p = elo_hw_probability(ELO_RATINGS['Arsenal'], ELO_RATINGS['Tottenham'])
    assert 0.8 < p < 0.99

def test_fatigue_multipliers():
    assert fatigue_multiplier(3) == pytest.approx(0.94)
    assert fatigue_multiplier(7) == pytest.approx(1.00)
    assert fatigue_multiplier(10) == pytest.approx(1.00)

def test_kelly_stake_cap():
    stake = kelly_stake(0.72, 2.10, 1000.0)
    assert stake <= 8.00
    assert stake >= 1.00
    assert stake % 0.5 == 0.0

def test_kelly_stake_below_odds_floor():
    stake = kelly_stake(0.80, 1.30, 1000.0)
    assert stake == 0.0

def test_classify_signal_elev():
    assert classify_signal(16.0, 0.67, 'o25') == 'ELEV'

def test_classify_signal_under25_higher_threshold():
    # u25 requires EV >= 25%, not 15%
    assert classify_signal(20.0, 0.70, 'u25') == 'BET'
    assert classify_signal(26.0, 0.70, 'u25') == 'ELEV'
    # 18% is above the o25 threshold (15%) but below the u25 threshold (25%) — must be BET not ELEV
    assert classify_signal(18.0, 0.70, 'u25') == 'BET'

def test_h2h_gate():
    assert apply_h2h_gate(5, 6)['gate'] == 'BLOCK_UNDER'
    assert apply_h2h_gate(4, 6)['gate'] == 'WARN_UNDER'
    assert apply_h2h_gate(3, 6)['gate'] == 'CLEAR'

def test_probability_gate_hard_block():
    result = check_probability_gate(0.77, 'o25')
    assert result is not None and 'HARD-BLOCK' in result

def test_probability_gate_clear():
    # 0.64 is just below the watch zone boundary (0.65) — must be clear
    result = check_probability_gate(0.64, 'o25')
    assert result is None
    # 0.74 is in the watch zone [0.65, 0.75) — returns WATCH string
    result = check_probability_gate(0.74, 'o25')
    assert result is not None and 'WATCH' in result
    # 0.76 is above 0.75 — hard block fires
    result = check_probability_gate(0.76, 'o25')
    assert result is not None and 'HARD-BLOCK' in result

def test_pinnacle_lower_is_confirm():
    r = check_pinnacle(1.85, 1.90)
    assert r['result'] == 'STRONG_CONFIRM'
    assert r['pass'] is True

def test_pinnacle_higher_is_flag():
    r = check_pinnacle(2.05, 1.90)
    assert r['result'] == 'FLAG'
    assert r['pass'] is False

def test_clv_positive():
    r = calculate_clv(2.00, 1.90)
    assert r['clv'] == pytest.approx(0.95)
    assert r['signal'] == 'POSITIVE'
