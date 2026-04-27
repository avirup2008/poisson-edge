"""
Signal engine: orchestrates model functions → produces SignalResult objects.
No scraping, no HTTP, no data loading here.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

import pandas as pd

from model.poisson_edge_model import (
    calculate_lambdas, build_score_matrix, extract_probabilities,
    apply_elo_ensemble, calculate_ev, classify_signal, kelly_stake,
    check_probability_gate, ELO_RATINGS,
)

MARKET_KEYS = ('o25', 'u25', 'btts', 'hw', 'aw', 'o35')

# Lambda thresholds — values outside these bounds are flagged SUSPECT.
# Genuine PL lambdas stay in [0.60, 3.50].
LAMBDA_MIN = 0.60
LAMBDA_MAX = 3.50


def _current_gw_fixtures(fixtures: List[Dict]) -> List[Dict]:
    """
    Filter to the current/next gameweek only.

    Strategy: find the earliest fixture date that is today or future; include
    all fixtures within 7 days of that anchor. This isolates a single GW window
    and excludes the following GW. If all fixtures are in the past, return the
    latest day's fixtures (graceful degradation).
    """
    today = date.today().isoformat()
    future = [f for f in fixtures if f.get('date', '') >= today]

    if not future:
        # All past — return most recent GW
        dates = sorted({f.get('date', '') for f in fixtures if f.get('date')}, reverse=True)
        if not dates:
            return fixtures
        anchor = dates[0]
    else:
        anchor = min(f.get('date', '') for f in future)

    cutoff = (date.fromisoformat(anchor) + timedelta(days=7)).isoformat()
    return [f for f in fixtures if anchor <= f.get('date', '') <= cutoff]


@dataclass
class SignalResult:
    home: str
    away: str
    market: str
    odds: float
    model_p: float
    ev_pct: float
    tier: str
    kelly_stake: float
    lambda_home: float
    lambda_away: float
    gate_block: Optional[str] = None
    date: Optional[str] = None


@dataclass
class GWSignals:
    fixtures: List[Dict]
    historical: pd.DataFrame
    g_atk: Dict
    g_def: Dict
    bankroll: float = 1000.0
    elo_ratings: Dict = field(default_factory=lambda: dict(ELO_RATINGS))

    def compute(self) -> List['SignalResult']:
        results = []
        for fix in _current_gw_fixtures(self.fixtures):
            for market, odds in fix.get('markets', {}).items():
                r = compute_signal(
                    home=fix['home'], away=fix['away'],
                    market=market, odds=odds,
                    historical=self.historical,
                    g_atk=self.g_atk, g_def=self.g_def,
                    bankroll=self.bankroll,
                    elo_ratings=self.elo_ratings,
                    home_rest_days=fix.get('home_rest_days', 7),
                    away_rest_days=fix.get('away_rest_days', 7),
                    home_atk_mult=fix.get('home_atk_mult', 1.0),
                    away_atk_mult=fix.get('away_atk_mult', 1.0),
                    home_def_boost=fix.get('home_def_boost', 1.0),
                    away_def_boost=fix.get('away_def_boost', 1.0),
                )
                r.date = fix.get('date')
                results.append(r)
        results.sort(key=lambda r: r.ev_pct, reverse=True)
        return results


def compute_signal(
    home: str, away: str, market: str, odds: float,
    historical: pd.DataFrame, g_atk: Dict, g_def: Dict,
    bankroll: float = 1000.0,
    elo_ratings: Dict = None,
    home_rest_days: int = 7, away_rest_days: int = 7,
    home_atk_mult: float = 1.0, away_atk_mult: float = 1.0,
    home_def_boost: float = 1.0, away_def_boost: float = 1.0,
) -> SignalResult:
    # Fix 3: validate market key before any computation
    if market not in MARKET_KEYS:
        raise ValueError(f"Unknown market: {market!r}")

    lh, la = calculate_lambdas(
        home, away, historical, g_atk, g_def,
        home_rest_days, away_rest_days,
        home_atk_mult, away_atk_mult,
        home_def_boost, away_def_boost,
    )
    matrix = build_score_matrix(lh, la)
    probs = extract_probabilities(matrix)

    if market == 'hw':
        # Fix 2: ensure elo_ratings is never None for hw market
        model_p = apply_elo_ensemble(probs['hw'], home, away, elo_ratings or dict(ELO_RATINGS))
    else:
        model_p = probs.get(market, 0.0)

    ev = calculate_ev(model_p, odds)
    tier = classify_signal(ev, model_p, market)
    gate_block = check_probability_gate(model_p, market)

    if gate_block and 'HARD-BLOCK' in gate_block:
        tier = 'NO'

    # Lambda sanity check — flag values outside credible PL range
    if lh < LAMBDA_MIN or lh > LAMBDA_MAX or la < LAMBDA_MIN or la > LAMBDA_MAX:
        suspect_note = f'SUSPECT: λH={lh:.3f} λA={la:.3f} outside [{LAMBDA_MIN},{LAMBDA_MAX}]'
        gate_block = f'{gate_block} | {suspect_note}' if gate_block else suspect_note

    stake = kelly_stake(model_p, odds, bankroll) if tier != 'NO' else 0.0

    return SignalResult(
        home=home, away=away, market=market, odds=odds,
        model_p=round(model_p, 4), ev_pct=round(ev, 2),
        tier=tier, kelly_stake=stake,
        lambda_home=round(lh, 4), lambda_away=round(la, 4),
        gate_block=gate_block,
    )
