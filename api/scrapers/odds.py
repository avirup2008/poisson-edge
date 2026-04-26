"""OddsAPI wrapper for Pinnacle odds."""
from typing import Dict
import httpx

ODDS_API_BASE = 'https://api.the-odds-api.com/v4'
EPL_KEY = 'soccer_epl'


def fetch_pinnacle_odds(home: str, away: str, api_key: str) -> Dict:
    """Returns {o25, u25, btts, hw, aw} Pinnacle odds. Returns {} on error."""
    url = f'{ODDS_API_BASE}/sports/{EPL_KEY}/odds'
    params = {
        'apiKey': api_key,
        'bookmakers': 'pinnacle',
        'markets': 'totals,h2h,btts',
        'oddsFormat': 'decimal',
        'regions': 'eu',
    }
    try:
        r = httpx.get(url, params=params, timeout=15)
        r.raise_for_status()
        events = r.json()
    except Exception:
        return {}

    for event in events:
        eh = event.get('home_team', '')
        ea = event.get('away_team', '')
        if _fuzzy_match(eh, home) and _fuzzy_match(ea, away):
            return _parse_pinnacle_event(event)
    return {}


def _fuzzy_match(a: str, b: str) -> bool:
    return (a.lower().replace(' ', '') in b.lower().replace(' ', '') or
            b.lower().replace(' ', '') in a.lower().replace(' ', ''))


def _parse_pinnacle_event(event: Dict) -> Dict:
    result = {}
    for bm in event.get('bookmakers', []):
        if bm.get('key') != 'pinnacle':
            continue
        for market in bm.get('markets', []):
            key = market.get('key')
            outcomes = {o['name']: o['price'] for o in market.get('outcomes', [])}
            if key == 'totals':
                result['o25'] = outcomes.get('Over')
                result['u25'] = outcomes.get('Under')
            elif key == 'h2h':
                result['hw'] = outcomes.get(event.get('home_team'))
                result['aw'] = outcomes.get(event.get('away_team'))
            elif key == 'btts':
                result['btts'] = outcomes.get('Yes')
    return result
