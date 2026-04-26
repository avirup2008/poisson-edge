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
    a_tokens = a.lower().split()
    b_tokens = b.lower().split()

    def tokens_match(t1, t2):
        """True if t1 token matches t2 token (exact or prefix)."""
        return t1 == t2 or t1.startswith(t2) or t2.startswith(t1)

    # Count how many tokens in the shorter list match a token in the longer list
    if len(a_tokens) <= len(b_tokens):
        shorter, longer = a_tokens, b_tokens
    else:
        shorter, longer = b_tokens, a_tokens

    if not shorter:
        return False

    matched = sum(1 for t in shorter if any(tokens_match(t, u) for u in longer))
    return matched > 0 and matched / len(shorter) > 0.5


def _parse_pinnacle_event(event: Dict) -> Dict:
    result = {}
    for bm in event.get('bookmakers', []):
        if bm.get('key') != 'pinnacle':
            continue
        for market in bm.get('markets', []):
            key = market.get('key')
            outcomes = {o['name']: o['price'] for o in market.get('outcomes', [])}
            if key == 'totals':
                # Filter to 2.5-goal line only
                over_2_5 = next(
                    (o for o in market.get('outcomes', [])
                     if o['name'] == 'Over' and abs(o.get('point', 2.5) - 2.5) < 0.01),
                    None
                )
                under_2_5 = next(
                    (o for o in market.get('outcomes', [])
                     if o['name'] == 'Under' and abs(o.get('point', 2.5) - 2.5) < 0.01),
                    None
                )
                if over_2_5:
                    result['o25'] = over_2_5['price']
                if under_2_5:
                    result['u25'] = under_2_5['price']
            elif key == 'h2h':
                result['hw'] = outcomes.get(event.get('home_team'))
                result['aw'] = outcomes.get(event.get('away_team'))
            elif key == 'btts':
                result['btts'] = outcomes.get('Yes')
    return result
