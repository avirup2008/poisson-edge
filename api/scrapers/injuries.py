"""
Injury scraper: Sofascore lineups API (missingPlayers).
Returns list of {player, status, role, source} dicts.
"""
from typing import List, Dict, Optional
import httpx

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Referer': 'https://www.sofascore.com/',
}

# Internal team name → Sofascore team ID (EPL 2025-26)
_TEAM_ID: Dict[str, int] = {
    'Arsenal':          42,
    'Aston Villa':      40,
    'Bournemouth':      60,
    'Brentford':        50,
    'Brighton':         30,
    'Burnley':          6,
    'Chelsea':          38,
    'Crystal Palace':   7,
    'Everton':          48,
    'Fulham':           43,
    'Leeds':            34,
    'Liverpool':        44,
    'Man City':         17,
    'Man United':       35,
    'Newcastle':        39,
    "Nott'm Forest":    14,
    'Sunderland':       41,
    'Tottenham':        33,
    'West Ham':         37,
    'Wolves':           3,
}

# Sofascore reason code → readable label (fallback if description absent)
_REASON: Dict[int, str] = {
    1: 'Injured',
    2: 'Suspended',
    3: 'Unknown',
    4: 'Ill',
    5: 'International duty',
}


def fetch_injuries(team: str) -> List[Dict]:
    """
    Fetch missing/injured players for a team's next EPL fixture via Sofascore.
    Returns [] on any failure.
    """
    team_id = _TEAM_ID.get(team)
    if not team_id:
        return []

    event_id, side = _next_event(team_id)
    if not event_id:
        return []

    return _missing_players(event_id, side)


def _next_event(team_id: int):
    """Return (event_id, 'home'|'away') for team's next EPL fixture."""
    try:
        url = f'https://api.sofascore.com/api/v1/team/{team_id}/events/next/0'
        r = httpx.get(url, headers=_HEADERS, timeout=10)
        r.raise_for_status()
        for event in r.json().get('events', []):
            # Filter to EPL (Sofascore unique tournament ID 17)
            tid = (event.get('tournament', {})
                   .get('uniqueTournament', {})
                   .get('id'))
            if tid != 17:
                continue
            home = event.get('homeTeam', {})
            away = event.get('awayTeam', {})
            eid = event.get('id')
            if home.get('id') == team_id:
                return eid, 'home'
            elif away.get('id') == team_id:
                return eid, 'away'
    except Exception:
        pass
    return None, None


def _missing_players(event_id: int, side: str) -> List[Dict]:
    """Fetch lineup missingPlayers for given event + side."""
    try:
        url = f'https://api.sofascore.com/api/v1/event/{event_id}/lineups'
        r = httpx.get(url, headers=_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        missing = data.get(side, {}).get('missingPlayers', [])
        results = []
        for m in missing:
            player = m.get('player', {})
            reason_code = m.get('reason', 3)
            description = m.get('description') or _REASON.get(reason_code, 'Unknown')
            name = player.get('name') or player.get('shortName', '?')
            results.append({
                'player': name,
                'status': description,
                'role': player.get('position', ''),
                'source': 'Sofascore',
            })
        return results
    except Exception:
        return []
