"""Fetch upcoming EPL fixtures with Pinnacle odds from OddsAPI."""
import json
from datetime import datetime, timezone, date
from pathlib import Path
from typing import List, Dict, Optional

import httpx

from api.scrapers.odds import ODDS_API_BASE, EPL_KEY, _fuzzy_match

_CACHE_FILE = Path('/tmp/poisson-edge-cache/fixtures_cache.json')
_CACHE_TTL_HOURS = 6

# OddsAPI team name → football-data.co.uk team name
_NAME_MAP = {
    'Manchester City': 'Man City',
    'Manchester United': 'Man United',
    'Tottenham Hotspur': 'Tottenham',
    'Wolverhampton Wanderers': 'Wolves',
    'Brighton & Hove Albion': 'Brighton',
    'Brighton and Hove Albion': 'Brighton',
    'West Ham United': 'West Ham',
    'Newcastle United': 'Newcastle',
    'Nottingham Forest': "Nott'm Forest",
    'Leicester City': 'Leicester',
    'Leeds United': 'Leeds',
    'Sheffield United': 'Sheffield United',
    'Ipswich Town': 'Ipswich',
    'Luton Town': 'Luton',
    'Sunderland': 'Sunderland',
    'Burnley': 'Burnley',
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
        return None

    odds: Dict[str, float] = {}
    for bm in event.get('bookmakers', []):
        if bm.get('key') != 'pinnacle':
            continue
        for market in bm.get('markets', []):
            key = market.get('key')
            if key != 'h2h':
                continue
            for o in market.get('outcomes', []):
                if _fuzzy_match(o['name'], raw_home):
                    odds['hw'] = o['price']
                elif _fuzzy_match(o['name'], raw_away):
                    odds['aw'] = o['price']

    if 'hw' not in odds:
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
    Fetch upcoming EPL fixtures with Pinnacle odds (h2h + totals).
    Makes two separate requests to avoid comma-encoding issues with httpx.
    Returns cached result if < 6h old. Returns [] on error.
    """
    cached = _load_cache()
    if cached is not None:
        return cached

    base = (f'{ODDS_API_BASE}/sports/{EPL_KEY}/odds'
            f'?apiKey={api_key}&bookmakers=pinnacle'
            f'&oddsFormat=decimal&regions=eu')

    # --- h2h ---
    try:
        r = httpx.get(base + '&markets=h2h', timeout=15)
        r.raise_for_status()
        h2h_events = r.json()
    except Exception:
        return []

    # --- totals (separate call — no comma in markets param) ---
    totals_by_id: Dict[str, Dict[str, float]] = {}
    try:
        rt = httpx.get(base + '&markets=totals', timeout=15)
        rt.raise_for_status()
        for e in rt.json():
            eid = e.get('id')
            if not eid:
                continue
            for bm in e.get('bookmakers', []):
                if bm.get('key') != 'pinnacle':
                    continue
                for mkt in bm.get('markets', []):
                    if mkt.get('key') != 'totals':
                        continue
                    for o in mkt.get('outcomes', []):
                        name = o.get('name', '')
                        point = o.get('point', 0) or 0
                        price = o.get('price')
                        if not price:
                            continue
                        if name == 'Over' and abs(point - 2.5) < 0.05:
                            totals_by_id.setdefault(eid, {})['o25'] = price
                        elif name == 'Under' and abs(point - 2.5) < 0.05:
                            totals_by_id.setdefault(eid, {})['u25'] = price
                        elif name == 'Over' and abs(point - 3.5) < 0.05:
                            totals_by_id.setdefault(eid, {})['o35'] = price
    except Exception:
        pass  # totals unavailable — h2h signals still work

    # Parse h2h events, merge in totals
    fixtures = []
    for e in h2h_events:
        fix = _parse_event(e, df)
        if fix is None:
            continue
        eid = e.get('id')
        if eid and eid in totals_by_id:
            fix['markets'].update(totals_by_id[eid])
        fixtures.append(fix)

    fixtures.sort(key=lambda x: x['date'])
    _save_cache(fixtures)
    return fixtures


def force_refresh(api_key: str, df=None) -> List[Dict]:
    """Bypass cache and re-fetch from OddsAPI."""
    _CACHE_FILE.unlink(missing_ok=True)
    return fetch_upcoming_fixtures(api_key, df)
