"""
API-Football (RapidAPI) Bet365 1x2 odds scraper for EPL.
https://api-football.com  — free tier: 100 calls/day via RapidAPI

Requires env var: RAPIDAPI_KEY
Set at: vercel env add RAPIDAPI_KEY production

Free RapidAPI account → subscribe to API-Football free plan:
https://rapidapi.com/api-sports/api/api-football

EPL = league 39, season 2024, bookmaker id 8 = Bet365

Caller: api/scrapers/fixtures.py (fetch_upcoming_fixtures)
"""
import httpx
from typing import Dict, Optional

_EPL_LEAGUE = 39
_SEASON     = 2024
_BET365_ID  = 8       # Bet365 bookmaker id in API-Football
_MATCH_WIN  = 1       # bet type id: Match Winner (1x2)
_URL = 'https://api-football-v1.p.rapidapi.com/v3/odds'

# API-Football team name → internal name
_NAME_MAP: Dict[str, str] = {
    'Nottingham Forest':        "Nott'm Forest",
    "Nott'm Forest":            "Nott'm Forest",
    'Manchester City':          'Man City',
    'Manchester United':        'Man United',
    'Tottenham Hotspur':        'Tottenham',
    'Wolverhampton Wanderers':  'Wolves',
    'Brighton & Hove Albion':   'Brighton',
    'Brighton and Hove Albion': 'Brighton',
    'West Ham United':          'West Ham',
    'Newcastle United':         'Newcastle',
    'Leeds United':             'Leeds',
    'Leicester City':           'Leicester',
    'Ipswich Town':             'Ipswich',
    'Luton Town':               'Luton',
    'Sheffield United':         'Sheffield United',
    'Sunderland AFC':           'Sunderland',
}


def _norm(name: str) -> str:
    return _NAME_MAP.get(name.strip(), name.strip())


def fetch_b365_apifootball(rapidapi_key: str) -> Dict[str, Dict[str, float]]:
    """
    Fetch Bet365 1x2 decimal odds for upcoming EPL fixtures via API-Football.

    Args:
        rapidapi_key: RapidAPI key with API-Football subscription (free tier ok).

    Returns:
        {'Home vs Away': {'b365_hw': float, 'b365_aw': float}}
        Empty dict on failure or missing key.
    """
    if not rapidapi_key:
        return {}

    results: Dict[str, Dict[str, float]] = {}

    try:
        r = httpx.get(
            _URL,
            params={
                'league':    _EPL_LEAGUE,
                'season':    _SEASON,
                'next':      10,           # next 10 EPL fixtures
                'bookmaker': _BET365_ID,
            },
            headers={
                'X-RapidAPI-Key':  rapidapi_key,
                'X-RapidAPI-Host': 'api-football-v1.p.rapidapi.com',
            },
            timeout=12,
        )
        print(f'[apifootball] status: {r.status_code}')
        if r.status_code != 200:
            print(f'[apifootball] error body: {r.text[:200]}')
            return {}

        data = r.json()
        events = data.get('response', [])
        print(f'[apifootball] {len(events)} events returned')

        for event in events:
            teams    = event.get('teams', {})
            home_raw = teams.get('home', {}).get('name', '')
            away_raw = teams.get('away', {}).get('name', '')
            if not home_raw or not away_raw:
                continue

            home = _norm(home_raw)
            away = _norm(away_raw)

            # Find Bet365 bookmaker → Match Winner (1x2) bet type
            hw: Optional[float] = None
            aw: Optional[float] = None
            for bm in event.get('bookmakers', []):
                if bm.get('id') != _BET365_ID:
                    continue
                for bet in bm.get('bets', []):
                    if bet.get('id') != _MATCH_WIN:
                        continue
                    for v in bet.get('values', []):
                        label = v.get('value', '')
                        try:
                            odd = float(v['odd'])
                        except (KeyError, ValueError, TypeError):
                            continue
                        if label == 'Home':
                            hw = odd
                        elif label == 'Away':
                            aw = odd

            if hw and aw:
                key = f'{home} vs {away}'
                results[key] = {'b365_hw': hw, 'b365_aw': aw}
                print(f'[apifootball] {key}: b365_hw={hw} b365_aw={aw}')

    except Exception as exc:
        print(f'[apifootball] error: {exc}')

    print(f'[apifootball] enriched {len(results)} fixtures with real Bet365 odds')
    return results
