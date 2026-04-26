"""
Auto-mark pending bets won/lost using current-season CSV from football-data.co.uk.
The same DataFrame that data_loader already holds in memory — no extra HTTP calls.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def _outcome_for_market(market: str, fthg: int, ftag: int) -> str | None:
    """Return 'won' | 'lost' | None (unrecognised market)."""
    total = fthg + ftag
    if market == 'o25':
        return 'won' if total > 2 else 'lost'
    if market == 'u25':
        return 'won' if total < 3 else 'lost'
    if market == 'o35':
        return 'won' if total > 3 else 'lost'
    if market == 'hw':
        return 'won' if fthg > ftag else 'lost'
    if market == 'aw':
        return 'won' if ftag > fthg else 'lost'
    if market == 'btts':
        return 'won' if fthg > 0 and ftag > 0 else 'lost'
    return None


def _resolve_team(name: str, known: set) -> str:
    """Fuzzy-match a bet team name to the CSV's team name convention."""
    if name in known:
        return name
    from api.scrapers.odds import _fuzzy_match
    for candidate in known:
        if _fuzzy_match(name, candidate):
            return candidate
    return name


def auto_mark_results(bets: list, df: 'pd.DataFrame') -> tuple[list, int]:
    """
    For each pending bet, look for a finished match in df and mark outcome.

    Args:
        bets: list of bet dicts (mutated in place)
        df:   store.historical DataFrame (HomeTeam, AwayTeam, FTHG, FTAG)

    Returns:
        (bets, count_updated)
    """
    if df is None or df.empty:
        return bets, 0

    import pandas as pd

    required = {'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG'}
    if not required.issubset(df.columns):
        return bets, 0

    all_teams: set[str] = set(df['HomeTeam'].dropna()) | set(df['AwayTeam'].dropna())
    updated = 0

    for bet in bets:
        if bet.get('status') != 'pending':
            continue

        csv_home = _resolve_team(bet.get('home', ''), all_teams)
        csv_away = _resolve_team(bet.get('away', ''), all_teams)

        mask = (df['HomeTeam'] == csv_home) & (df['AwayTeam'] == csv_away)
        rows = df[mask]
        if rows.empty:
            continue

        row = rows.iloc[-1]

        # Skip if result not yet published (FTHG is NaN)
        if pd.isna(row.get('FTHG', float('nan'))):
            continue

        try:
            fthg = int(row['FTHG'])
            ftag = int(row['FTAG'])
        except (ValueError, TypeError):
            continue

        outcome = _outcome_for_market(bet.get('market', ''), fthg, ftag)
        if outcome is None:
            continue

        bet['status'] = outcome
        bet['result_score'] = f'{fthg}-{ftag}'
        updated += 1

    return bets, updated
