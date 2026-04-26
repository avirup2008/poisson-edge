"""Fetch upcoming EPL fixtures with Pinnacle odds from OddsAPI."""
import json
from datetime import datetime, timezone, date
from pathlib import Path
from typing import List, Dict, Optional

import httpx

from api.scrapers.odds import ODDS_API_BASE, EPL_KEY, _fuzzy_match, _parse_pinnacle_event

_CACHE_FILE = Path('/tmp/poisson-edge-cache/fixtures_cache.json')
_CACHE_TTL_HOURS = 6

# OddsAPI team name → football-data.co.uk team name
_NAME_MAP = {
    'Manchester City': 'Man City',
    'Manchester United': 'Man United',
    'Tottenham Hotspur': 'Tottenham',
    'Wolverhampton Wanderers': 'Wolves',
    'Brighton & Hove Albion': 'Brighton',
    'West Ham United': 'West Ham',
    'Newcastle United': 'Newcastle',
    'Nottingham Forest': "Nott'm Forest",
    'Leicester City': 'Leicester',
    'Leeds United': 'Leeds',
    'Sheffield United': 'Sheffield United',
    'Ipswich Town': 'Ipswich',
    'Luton Town': 'Luton',
}


def _normalise(name: str) -> str:
    return _NAME_MAP.get(name, name)


def _days_since_last(team: str, df) -> int:
    if df is None or df.empty:
        return 7
    try:
        mask = (df['HomeTeam'] == team) | (df['AwayTeam'] == team)
        team_df = df[mask]
        if team_df.empty:
            return 7
        last = team_df['Date'].max()
        delta = date.today() - (last.date() if hasattr(last, 'date') else last)
        return max(1, delta.days)
    except Exception:
        return 7


def _parse_event(event: Dict, df) -> Optional[Dict]:
    raw_home = event.get('home_team', '')
    raw_away = event.get('away_team', '')
    home = _normalise(raw_home)
    away = _normalise(raw_away)

    commence = event.get('commence_time', '')
    try:
        dt = datetime.fromisoformat(commence.replace('Z', '+00:00'))
        date_str = dt.strftime('%Y-%m-%d')
    except (ValueError, AttributeError):
        print(f'[parse_event] DATE FAIL: {raw_home} vs {raw_away} commence={commence!r}')
        return None

    odds = {}
    bm_keys = [bm.get('key') for bm in event.get('bookmakers', [])]
    print(f'[parse_event] {raw_home} vs {raw_away} date={date_str} bookmakers={bm_keys}')
    for bm in event.get('bookmakers', []):
        if bm.get('key') != 'pinnacle':
            continue
        market_keys = [m.get('key') for m in bm.get('markets', [])]
        print(f'[parse_event]   pinnacle markets={market_keys}')
        for market in bm.get('markets', []):
            key = market.get('key')
            outcomes = market.get('outcomes', [])
            if key == 'totals':
                o25 = next((o for o in outcomes if o['name'] == 'Over' and abs(o.get('point', 0) - 2.5) < 0.01), None)
                u25 = next((o for o in outcomes if o['name'] == 'Under' and abs(o.get('point', 0) - 2.5) < 0.01), None)
                o35 = next((o for o in outcomes if o['name'] == 'Over' and abs(o.get('point', 0) - 3.5) < 0.01), None)
                if o25:
                    odds['o25'] = o25['price']
                if u25:
                    odds['u25'] = u25['price']
                if o35:
                    odds['o35'] = o35['price']
            elif key == 'h2h':
                for o in outcomes:
                    if _fuzzy_match(o['name'], raw_home):
                        odds['hw'] = o['price']
                    elif _fuzzy_match(o['name'], raw_away):
                        odds['aw'] = o['price']
            elif key == 'btts':
                yes = next((o for o in outcomes if o['name'] == 'Yes'), None)
                if yes:
                    odds['btts'] = yes['price']

    print(f'[parse_event]   odds built={odds} hw_set={"hw" in odds} o25_set={"o25" in odds}')
    if not any(k in odds for k in ('hw', 'o25')):
        print(f'[parse_event]   FILTERED OUT: {raw_home} vs {raw_away}')
        return None

    return {
        'home': home,
        'away': away,
        'date': date_str,
        'markets': odds,
        'home_rest_days': _days_since_last(home, df),
        'away_rest_days': _days_since_last(away, df),
    }


def _load_cache() -> Optional[List[Dict]]:
    try:
        if not _CACHE_FILE.exists():
            return None
        data = json.loads(_CACHE_FILE.read_text())
        fetched_at = datetime.fromisoformat(data['fetched_at'])
        age_hours = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
        return data['fixtures'] if age_hours <= _CACHE_TTL_HOURS else None
    except Exception:
        return None


def _save_cache(fixtures: List[Dict]) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps({
            'fetched_at': datetime.now(timezone.utc).isoformat(),
            'fixtures': fixtures,
        }))
    except Exception:
        pass


def fetch_upcoming_fixtures(api_key: str, df=None) -> List[Dict]:
    """
    Fetch all upcoming EPL fixtures with Pinnacle odds.
    Returns cached result if < 6h old. Returns [] on error.
    """
    cached = _load_cache()
    if cached is not None:
        return cached

    # OddsAPI requires raw commas in markets — httpx URL-encodes them causing 422
    url = (f'{ODDS_API_BASE}/sports/{EPL_KEY}/odds'
           f'?apiKey={api_key}&bookmakers=pinnacle&markets=totals,h2h,btts'
           f'&oddsFormat=decimal&regions=eu')
    try:
        r = httpx.get(url, timeout=15)
        print(f'[fixtures] OddsAPI status={r.status_code} remaining={r.headers.get("x-requests-remaining","?")} body_len={len(r.text)}')
        r.raise_for_status()
        events = r.json()
        print(f'[fixtures] raw events from OddsAPI: {len(events)}')
    except Exception as exc:
        print(f'[fixtures] OddsAPI fetch error: {exc}')
        return []

    fixtures = [f for e in events for f in [_parse_event(e, df)] if f]
    fixtures.sort(key=lambda x: x['date'])
    _save_cache(fixtures)
    return fixtures


def force_refresh(api_key: str, df=None) -> List[Dict]:
    """Bypass cache and re-fetch from OddsAPI."""
    _CACHE_FILE.unlink(missing_ok=True)
    return fetch_upcoming_fixtures(api_key, df)
