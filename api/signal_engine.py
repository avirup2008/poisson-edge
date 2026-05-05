"""
Signal engine: orchestrates model functions → produces SignalResult objects.
No scraping, no HTTP, no data loading here.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

import pandas as pd

from model.poisson_edge_model import (
    calculate_lambdas, calculate_lambda_components,
    build_score_matrix, extract_probabilities,
    apply_elo_ensemble, calculate_ev, classify_signal, kelly_stake,
    check_probability_gate, ELO_RATINGS,
    classify_match_context,
)

MARKET_KEYS = ('o25', 'u25', 'btts', 'hw', 'aw', 'o35')

# Lambda thresholds — values outside these bounds are flagged SUSPECT.
# Genuine PL lambdas stay in [0.60, 3.50].
LAMBDA_MIN = 0.60
LAMBDA_MAX = 3.50

# EPL 2025-26 GW date calendar — update as season progresses
_GW_CALENDAR = [
    (35, '2026-04-28', '2026-05-05'),
    (36, '2026-05-06', '2026-05-12'),
    (37, '2026-05-13', '2026-05-19'),
    (38, '2026-05-20', '2026-05-26'),
]

# EPL 2025-26 context — update as season standings change
_TOP8_2526 = [
    'Liverpool', 'Arsenal', 'Man City', 'Chelsea',
    'Aston Villa', 'Tottenham', 'Newcastle', 'Man United',
]
_RELEGATION_ZONE_2526 = ['Sunderland', 'Burnley', 'Leeds']

# European fixtures — map team → date of next European game.
# Update each GW. Fatigue applies when rest < 7 days before PL fixture.
_EUROPEAN_FIXTURES: Dict[str, str] = {
    'Aston Villa':       '2026-05-01',   # EL semi-final leg 2
    'Nottingham Forest': '2026-05-01',   # EL semi-final leg 2
}


def _rest_days_from_europe(team: str, fix_date: str) -> int:
    """
    Return rest days between a team's European fixture and a PL fixture.
    Returns 7 (no fatigue) if no European fixture is known or dates are missing.
    """
    euro_date = _EUROPEAN_FIXTURES.get(team)
    if not euro_date or not fix_date:
        return 7
    try:
        delta = date.fromisoformat(fix_date) - date.fromisoformat(euro_date)
        return max(1, delta.days)
    except ValueError:
        return 7


def _current_gw_fixtures(fixtures: List[Dict]) -> List[Dict]:
    """
    Filter to the current/next gameweek using the GW calendar.
    Finds the first GW whose end date is >= today AND has upcoming fixtures.
    If the matched window is empty (all matches already played), advances to
    the next GW — handles the end-of-GW transition day correctly.
    Falls back to a 7-day sliding window if we're past the calendar.
    """
    today = date.today().isoformat()
    for _gw, start, end in _GW_CALENDAR:
        if today <= end:
            gw_fixes = [f for f in fixtures if start <= f.get('date', '') <= end]
            if gw_fixes:
                return gw_fixes
            # Window matched but OddsAPI has no upcoming fixtures in it
            # (all played) — fall through to advance to the next GW
    # Beyond calendar — fall back to 7-day window from earliest future fixture
    future = [f for f in fixtures if f.get('date', '') >= today]
    if not future:
        return fixtures
    anchor = min(f.get('date', '') for f in future)
    cutoff = (date.fromisoformat(anchor) + timedelta(days=7)).isoformat()
    return [f for f in fixtures if anchor <= f.get('date', '') <= cutoff]


def _context_note(
    home: str,
    away: str,
    historical: pd.DataFrame,
    full_historical: Optional[pd.DataFrame] = None,
) -> Optional[str]:
    """
    Build a context note for gate_block:
    - Cat A/B rivalry flag
    - Relegation-zone team flag
    - H2H last-8 record (uses full 16-season history when available)
    """
    notes: List[str] = []

    # Cat A / Cat B
    ctx = classify_match_context(home, away, _TOP8_2526)
    if ctx == 'CatA':
        notes.append('CAT-A rivalry')
    elif ctx == 'CatB':
        notes.append('CAT-B derby')

    # Relegation zone
    releg = [t for t in (home, away) if t in _RELEGATION_ZONE_2526]
    if releg:
        notes.append(f'RELEG-ZONE: {", ".join(releg)}')

    # H2H last 8 — prefer full 16-season history; fall back to current season
    h2h_df = (
        full_historical
        if (full_historical is not None and not full_historical.empty)
        else historical
    )
    if not h2h_df.empty and 'HomeTeam' in h2h_df.columns and 'FTR' in h2h_df.columns:
        mask = (
            ((h2h_df['HomeTeam'] == home) & (h2h_df['AwayTeam'] == away)) |
            ((h2h_df['HomeTeam'] == away) & (h2h_df['AwayTeam'] == home))
        )
        sort_col = 'Date' if 'Date' in h2h_df.columns else None
        h2h = (
            h2h_df[mask].sort_values(sort_col, ascending=False).head(8)
            if sort_col
            else h2h_df[mask].tail(8)
        )
        if not h2h.empty:
            home_w = sum(
                1 for _, row in h2h.iterrows()
                if (row['HomeTeam'] == home and row['FTR'] == 'H') or
                   (row['HomeTeam'] == away and row['FTR'] == 'A')
            )
            away_w = sum(
                1 for _, row in h2h.iterrows()
                if (row['HomeTeam'] == away and row['FTR'] == 'H') or
                   (row['HomeTeam'] == home and row['FTR'] == 'A')
            )
            d_count = len(h2h) - home_w - away_w
            notes.append(
                f'H2H({len(h2h)}): {home[:5]} {home_w}W-{d_count}D-{away_w}W'
            )

    return ' | '.join(notes) if notes else None


def _has_named_binary_context(gate_block: Optional[str]) -> bool:
    """True if gate_block contains a named binary structural factor."""
    if not gate_block:
        return False
    return any(k in gate_block for k in ('CAT-A', 'CAT-B', 'RELEG-ZONE'))


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
    structural_override: bool = False
    lambda_detail: dict = field(default_factory=dict)
    b365_odds: Optional[float] = None   # Bet365 reference odds (hw/aw only)


@dataclass
class GWSignals:
    fixtures: List[Dict]
    historical: pd.DataFrame           # current season — used for lambda ratings
    g_atk: Dict
    g_def: Dict
    bankroll: float = 1000.0
    elo_ratings: Dict = field(default_factory=lambda: dict(ELO_RATINGS))
    full_historical: Optional[pd.DataFrame] = None  # all 16 seasons — used for H2H

    def compute(self) -> List['SignalResult']:
        results = []
        for fix in _current_gw_fixtures(self.fixtures):
            fix_date = fix.get('date', '')
            home, away = fix['home'], fix['away']

            # Fatigue: calculate rest days from European fixtures
            home_rest = _rest_days_from_europe(home, fix_date)
            away_rest = _rest_days_from_europe(away, fix_date)

            for market, odds in fix.get('markets', {}).items():
                r = compute_signal(
                    home=home, away=away,
                    market=market, odds=odds,
                    historical=self.historical,
                    g_atk=self.g_atk, g_def=self.g_def,
                    bankroll=self.bankroll,
                    elo_ratings=self.elo_ratings,
                    home_rest_days=fix.get('home_rest_days', home_rest),
                    away_rest_days=fix.get('away_rest_days', away_rest),
                    home_atk_mult=fix.get('home_atk_mult', 1.0),
                    away_atk_mult=fix.get('away_atk_mult', 1.0),
                    home_def_boost=fix.get('home_def_boost', 1.0),
                    away_def_boost=fix.get('away_def_boost', 1.0),
                )
                r.date = fix_date

                # B365 reference odds (hw/aw only — for Pinnacle vs B365 display)
                b365 = fix.get('b365', {})
                if market == 'hw':
                    r.b365_odds = b365.get('b365_hw')
                elif market == 'aw':
                    r.b365_odds = b365.get('b365_aw')

                # Append context note (Cat A/B, RELEG, H2H)
                ctx = _context_note(home, away, self.historical, self.full_historical)
                if ctx:
                    r.gate_block = f'{r.gate_block} | {ctx}' if r.gate_block else ctx

                # Append fatigue note if applied
                if home_rest < 7 or away_rest < 7:
                    fatigue_parts = []
                    if home_rest < 7:
                        fatigue_parts.append(f'{home[:6]} {home_rest}d rest')
                    if away_rest < 7:
                        fatigue_parts.append(f'{away[:6]} {away_rest}d rest')
                    fatigue_note = 'FATIGUE: ' + ', '.join(fatigue_parts)
                    r.gate_block = f'{r.gate_block} | {fatigue_note}' if r.gate_block else fatigue_note

                # ── Post-context tier overrides ────────────────────────────

                # Cat A O25 upgrade: real money eligible (9/9 season record)
                match_ctx = classify_match_context(home, away, _TOP8_2526)
                if (market == 'o25' and match_ctx == 'CatA'
                        and r.ev_pct >= 15.0 and r.model_p >= 0.65
                        and r.tier != 'NO'):
                    r.tier = 'ELEV'
                    cat_a_note = 'CAT-A-O25: real money eligible (9/9 season record)'
                    r.gate_block = f'{r.gate_block} | {cat_a_note}' if r.gate_block else cat_a_note

                # U25 block: never real money for Cat A, Cat B, or relegation matches
                if market == 'u25' and match_ctx in ('CatA', 'CatB'):
                    r.tier = 'NO'
                    block_note = f'BLOCKED: u25 suppressed for {match_ctx} derby'
                    r.gate_block = f'{r.gate_block} | {block_note}' if r.gate_block else block_note
                elif market == 'u25' and any(t in _RELEGATION_ZONE_2526 for t in (home, away)):
                    r.tier = 'NO'
                    block_note = 'BLOCKED: u25 suppressed for relegation fixture'
                    r.gate_block = f'{r.gate_block} | {block_note}' if r.gate_block else block_note

                # Structural override: EV ≥ 20%, P ≥ 58%, named binary context
                if (r.ev_pct >= 20.0 and r.model_p >= 0.58
                        and _has_named_binary_context(r.gate_block)
                        and r.tier not in ('NO',)):
                    r.structural_override = True
                    # Cap stake at €5 for structural overrides (requires Pinnacle check)
                    r.kelly_stake = min(r.kelly_stake, 5.00)

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
    # Validate market key before any computation
    if market not in MARKET_KEYS:
        raise ValueError(f"Unknown market: {market!r}")

    lh, la = calculate_lambdas(
        home, away, historical, g_atk, g_def,
        home_rest_days, away_rest_days,
        home_atk_mult, away_atk_mult,
        home_def_boost, away_def_boost,
    )
    detail = calculate_lambda_components(
        home, away, historical, g_atk, g_def,
        home_rest_days, away_rest_days,
        home_atk_mult, away_atk_mult,
        home_def_boost, away_def_boost,
    )
    matrix = build_score_matrix(lh, la)
    probs = extract_probabilities(matrix)

    if market == 'hw':
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
        lambda_detail=detail,
    )
