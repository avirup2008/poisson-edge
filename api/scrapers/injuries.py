"""
Injury scraper: ESPN core API for EPL team injury reports.

Sofascore (previous source) returns 403 from Vercel cloud IPs.
ESPN's site.api and sports.core.api are both accessible from Vercel.

Pipeline:
  1. Look up ESPN team ID via the teams list endpoint (cached per process)
  2. Fetch injuries from sports.core.api.espn.com/v2/.../teams/{id}/injuries
  3. Parse items into {player, status, role, source} dicts

Returns [] on any failure — card degrades to "No injury data" rather
than silently showing "No confirmed absences" (which is misleading).
"""
from typing import List, Dict, Optional
import httpx

_H = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json',
}
_LEAGUE = 'eng.1'

# Internal name → ESPN display name (for fuzzy team lookup)
_ESPN_NAME: Dict[str, str] = {
    'Arsenal':          'Arsenal',
    'Aston Villa':      'Aston Villa',
    'Bournemouth':      'Bournemouth',
    'Brentford':        'Brentford',
    'Brighton':         'Brighton & Hove Albion',
    'Chelsea':          'Chelsea',
    'Crystal Palace':   'Crystal Palace',
    'Everton':          'Everton',
    'Fulham':           'Fulham',
    'Ipswich':          'Ipswich Town',
    'Leeds':            'Leeds United',
    'Leicester':        'Leicester City',
    'Liverpool':        'Liverpool',
    'Man City':         'Manchester City',
    'Man United':       'Manchester United',
    'Newcastle':        'Newcastle United',
    "Nott'm Forest":    'Nottingham Forest',
    'Sunderland':       'Sunderland',
    'Tottenham':        'Tottenham Hotspur',
    'West Ham':         'West Ham United',
    'Wolves':           'Wolverhampton Wanderers',
}

# Module-level cache: ESPN display name → team ID
_team_id_cache: Dict[str, int] = {}


def _load_team_ids() -> None:
    """Populate _team_id_cache from ESPN teams endpoint (called once per process)."""
    global _team_id_cache
    if _team_id_cache:
        return
    try:
        url = f'https://site.api.espn.com/apis/site/v2/sports/soccer/{_LEAGUE}/teams?limit=30'
        r = httpx.get(url, headers=_H, timeout=10)
        if r.status_code != 200:
            return
        sports = r.json().get('sports', [])
        leagues = sports[0].get('leagues', []) if sports else []
        teams = leagues[0].get('teams', []) if leagues else []
        for t in teams:
            team = t.get('team', {})
            tid = team.get('id')
            name = team.get('displayName', '')
            if tid and name:
                _team_id_cache[name] = int(tid)
        print(f'[injuries] ESPN team IDs loaded: {len(_team_id_cache)} teams')
    except Exception as exc:
        print(f'[injuries] team ID load error: {exc}')


def _espn_team_id(team: str) -> Optional[int]:
    _load_team_ids()
    espn_name = _ESPN_NAME.get(team, team)
    # Exact match
    if espn_name in _team_id_cache:
        return _team_id_cache[espn_name]
    # Partial match fallback
    for k, v in _team_id_cache.items():
        if team.lower() in k.lower() or k.lower() in team.lower():
            return v
    return None


def fetch_injuries(team: str) -> List[Dict]:
    """
    Fetch injured/suspended players for a team via ESPN core API.
    Returns [] on any failure or if ESPN has no data for this team.
    """
    team_id = _espn_team_id(team)
    if not team_id:
        print(f'[injuries] no ESPN team ID for: {team}')
        return []

    url = (f'https://sports.core.api.espn.com/v2/sports/soccer/'
           f'leagues/{_LEAGUE}/teams/{team_id}/injuries?limit=100')
    try:
        r = httpx.get(url, headers=_H, timeout=10)
        if r.status_code != 200:
            print(f'[injuries] {team} → HTTP {r.status_code}')
            return []
        data = r.json()
        items = data.get('items', [])
        print(f'[injuries] {team} (id={team_id}) → {len(items)} injury items')
        return [_parse_item(item) for item in items if _parse_item(item)]
    except Exception as exc:
        print(f'[injuries] {team} fetch error: {exc}')
        return []


def _parse_item(item: Dict) -> Optional[Dict]:
    """Parse one ESPN injury item into our standard dict format."""
    try:
        athlete = item.get('athlete', {})
        # athlete may be a $ref link object — we only parse inline athlete data
        name = athlete.get('fullName') or athlete.get('displayName')
        if not name:
            return None

        # Status type: OUT, QUESTIONABLE, DOUBTFUL, etc.
        status_type = (item.get('status', {})
                       .get('type', {})
                       .get('description', 'Unknown'))

        # Injury details
        details = item.get('details', {})
        injury_type = details.get('type', '')
        short_comment = details.get('shortComment', '')
        status_label = short_comment or injury_type or status_type

        # Position from athlete
        position = (athlete.get('position', {}).get('abbreviation', '')
                    if isinstance(athlete.get('position'), dict)
                    else athlete.get('position', ''))

        return {
            'player': name,
            'status': status_label,
            'role': position,
            'source': 'ESPN',
        }
    except Exception:
        return None
