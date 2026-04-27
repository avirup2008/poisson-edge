"""
Injury scraper: Fantasy Premier League bootstrap API.
https://fantasy.premierleague.com/api/bootstrap-static/

No auth required. Publicly accessible from Vercel cloud IPs (confirmed 2026-04-27).

FPL updates every EPL player's availability directly from club injury reports:
  status:  'a' available | 'i' injured | 'd' doubtful | 's' suspended | 'u' unavailable
  news:    human-readable string e.g. "Hamstring injury - 25% chance of playing"
  chance_of_playing_next_round: 0/25/50/75 or null (null = fit)

Caller: api/main.py (GET /api/injuries/{team})
"""
from typing import List, Dict, Optional
import httpx

_FPL_URL = 'https://fantasy.premierleague.com/api/bootstrap-static/'
_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json',
}

_POSITION = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}

_STATUS_LABEL = {
    'i': 'Injured',
    'd': 'Doubtful',
    's': 'Suspended',
    'u': 'Unavailable',
}

# Internal name → FPL short name (for matching teams array)
_FPL_SHORT: Dict[str, str] = {
    'Arsenal':          'ARS',
    'Aston Villa':      'AVL',
    'Bournemouth':      'BOU',
    'Brentford':        'BRE',
    'Brighton':         'BHA',
    'Chelsea':          'CHE',
    'Crystal Palace':   'CRY',
    'Everton':          'EVE',
    'Fulham':           'FUL',
    'Ipswich':          'IPS',
    'Leeds':            'LEE',
    'Leicester':        'LEI',
    'Liverpool':        'LIV',
    'Man City':         'MCI',
    'Man United':       'MUN',
    'Newcastle':        'NEW',
    "Nott'm Forest":    'NFO',
    'Sunderland':       'SUN',
    'Tottenham':        'TOT',
    'West Ham':         'WHU',
    'Wolves':           'WOL',
}

# Module-level cache: short_name → FPL team id + player list
_cache: Optional[Dict] = None


def _load_bootstrap() -> Optional[Dict]:
    """Fetch and cache FPL bootstrap. Returns None on failure."""
    global _cache
    if _cache is not None:
        return _cache
    try:
        r = httpx.get(_FPL_URL, headers=_HEADERS, timeout=15)
        if r.status_code != 200:
            print(f'[injuries] FPL bootstrap {r.status_code}')
            return None
        data = r.json()
        # Build short_name → fpl_id map
        team_map = {t['short_name']: t['id'] for t in data.get('teams', [])}
        _cache = {'team_map': team_map, 'elements': data.get('elements', [])}
        print(f'[injuries] FPL loaded: {len(team_map)} teams, {len(_cache["elements"])} players')
        return _cache
    except Exception as exc:
        print(f'[injuries] FPL bootstrap error: {exc}')
        return None


def fetch_injuries(team: str) -> List[Dict]:
    """
    Return list of injured/doubtful/suspended players for an EPL team.
    Each entry: {player, status, role, source}
    Returns [] on any failure.
    """
    short = _FPL_SHORT.get(team)
    if not short:
        print(f'[injuries] unknown team: {team}')
        return []

    bootstrap = _load_bootstrap()
    if not bootstrap:
        return []

    fpl_id = bootstrap['team_map'].get(short)
    if not fpl_id:
        # Try fuzzy match
        for k, v in bootstrap['team_map'].items():
            if short[:3].upper() in k.upper():
                fpl_id = v
                break
    if not fpl_id:
        print(f'[injuries] no FPL id for {team} ({short})')
        return []

    results = []
    for p in bootstrap['elements']:
        if p.get('team') != fpl_id:
            continue
        status = p.get('status', 'a')
        if status == 'a':
            continue  # fit — skip

        name = p.get('web_name') or f"{p.get('first_name','?')} {p.get('second_name','')}"
        news = p.get('news', '')

        # Skip loan/transfer departures — FPL marks these 'u' with "joined" in news.
        # They're not at the club so shouldn't appear as match absences.
        news_lower = news.lower()
        if status == 'u' and any(kw in news_lower for kw in ('joined', 'loan', 'transferred', 'released', 'signed')):
            continue
        chance = p.get('chance_of_playing_next_round')

        # Build status label
        status_label = news or _STATUS_LABEL.get(status, 'Unknown')
        # Append chance % if available and not already in news string
        if chance is not None and str(chance) not in status_label:
            status_label = f'{status_label} ({chance}%)' if status_label else f'{chance}% chance'

        position_code = p.get('element_type', 0)
        results.append({
            'player': name,
            'status': status_label,
            'role': _POSITION.get(position_code, ''),
            'source': 'FPL',
        })

    print(f'[injuries] {team}: {len(results)} absences')
    return results
