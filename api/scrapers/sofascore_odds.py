"""
Sofascore odds scraper — fetches 1x2 soft-book odds (provider 1, typically Bet365)
for upcoming EPL fixtures by gameweek round.

Used to populate b365_hw / b365_aw in the fixture dict so the Pinnacle vs
soft-book comparison row renders on signal cards.

Caller: api/scrapers/fixtures.py (fetch_upcoming_fixtures)
"""
from typing import Dict, List, Optional
import httpx

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Referer': 'https://www.sofascore.com/',
}

# EPL 2025-26 on Sofascore
_TOURNAMENT_ID = 17
_SEASON_ID = 76986

# Sofascore team name → internal football-data.co.uk name
_NAME_MAP = {
    'Leeds United':             'Leeds',
    'Manchester City':          'Man City',
    'Manchester United':        'Man United',
    'Tottenham Hotspur':        'Tottenham',
    'Wolverhampton':            'Wolves',
    'Brighton & Hove Albion':   'Brighton',
    'West Ham United':          'West Ham',
    'Newcastle United':         'Newcastle',
    'Nottingham Forest':        "Nott'm Forest",
}


def _normalise(name: str) -> str:
    return _NAME_MAP.get(name, name)


def _frac_to_dec(frac: str) -> Optional[float]:
    """Convert fractional odds string '67/100' → decimal 1.67."""
    try:
        n, d = frac.split('/')
        return round(1 + int(n) / int(d), 2)
    except Exception:
        return None


def fetch_sofascore_odds_for_rounds(rounds: List[int]) -> Dict[str, Dict[str, float]]:
    """
    Return a dict keyed by 'Home vs Away' → {'b365_hw': float, 'b365_aw': float}
    for all fixtures in the given round numbers.

    Makes 1 round-list call + 1 odds call per fixture.
    Returns {} silently on any failure.
    """
    results: Dict[str, Dict[str, float]] = {}

    for round_num in rounds:
        try:
            r = httpx.get(
                f'https://api.sofascore.com/api/v1/unique-tournament/'
                f'{_TOURNAMENT_ID}/season/{_SEASON_ID}/events/round/{round_num}',
                headers=_HEADERS, timeout=10,
            )
            r.raise_for_status()
            events = r.json().get('events', [])
        except Exception:
            continue

        for event in events:
            eid = event.get('id')
            home = _normalise(event.get('homeTeam', {}).get('name', ''))
            away = _normalise(event.get('awayTeam', {}).get('name', ''))
            if not eid or not home or not away:
                continue

            try:
                r2 = httpx.get(
                    f'https://api.sofascore.com/api/v1/event/{eid}/odds/1/all',
                    headers=_HEADERS, timeout=8,
                )
                if r2.status_code != 200:
                    continue
                markets = r2.json().get('markets', [])
                ft = next(
                    (m for m in markets if m.get('marketName') == 'Full time'),
                    None,
                )
                if not ft:
                    continue
                choices = {
                    c['name']: _frac_to_dec(c.get('fractionalValue', ''))
                    for c in ft.get('choices', [])
                }
                hw = choices.get('1')
                aw = choices.get('2')
                if hw and aw:
                    key = f'{home} vs {away}'
                    results[key] = {'b365_hw': hw, 'b365_aw': aw}
            except Exception:
                continue

    return results
