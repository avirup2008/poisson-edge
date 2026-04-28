"""
PulseScore Bet365 1x2 odds scraper for EPL.

Supports two auth modes (whichever key is set):
  RapidAPI:   RAPIDAPI_KEY    → X-RapidAPI-Key, host bet365data.p.rapidapi.com
  Direct API: PULSESCORE_KEY  → X-Secret header, host pulsescore.net

Endpoints used:
  RapidAPI (bet365data.p.rapidapi.com):   /v2/bet365/leagues, /v2/bet365/events
  Direct   (pulsescore.net):              /api/v2/bet365/leagues, /api/v2/bet365/events
  (RapidAPI strips the /api prefix — pulsescore.net uses it for internal routing)

Free tier: 500 req/month. We use 2 calls per 6h cache cycle (~60/month). Well within limit.

Caller: api/scrapers/fixtures.py (fetch_upcoming_fixtures)
"""
import httpx
from typing import Dict, List, Optional, Tuple

_DIRECT_BASE   = 'https://pulsescore.net'
_RAPIDAPI_HOST = 'bet365data.p.rapidapi.com'
_RAPIDAPI_BASE = f'https://{_RAPIDAPI_HOST}'

_EPL_KEYWORDS  = ('premier league', 'english premier', 'england premier', 'epl')

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


def _make_headers(rapidapi_key: str, pulsescore_key: str) -> Tuple[Dict, str, str]:
    """Return (headers, base_url, path_prefix) for whichever key is available.

    RapidAPI serves endpoints at /v2/bet365/... (no /api prefix).
    Direct pulsescore.net uses /api/v2/bet365/... internally.
    """
    if rapidapi_key:
        return (
            {
                'X-RapidAPI-Key':  rapidapi_key,
                'X-RapidAPI-Host': _RAPIDAPI_HOST,
                'Accept':          'application/json',
            },
            _RAPIDAPI_BASE,
            '/v2/bet365',   # RapidAPI: no /api prefix
        )
    return (
        {'X-Secret': pulsescore_key, 'Accept': 'application/json'},
        _DIRECT_BASE,
        '/api/v2/bet365',  # direct pulsescore.net: /api prefix required
    )


def _find_epl_id(base: str, headers: Dict, path_prefix: str = '/api/v2/bet365') -> Optional[str]:
    """Call {path_prefix}/leagues and return the EPL league id."""
    try:
        r = httpx.get(f'{base}{path_prefix}/leagues', headers=headers, timeout=10)
        print(f'[pulsescore] leagues: HTTP {r.status_code}')
        if r.status_code != 200:
            return None
        raw = r.json()
        leagues = raw if isinstance(raw, list) else (
            raw.get('data') or raw.get('leagues') or []
        )
        for lg in leagues:
            name = (lg.get('nm') or lg.get('name') or '').lower()
            if any(kw in name for kw in _EPL_KEYWORDS):
                lid = lg.get('id') or lg.get('fi') or lg.get('league_id')
                print(f'[pulsescore] EPL: "{name}" id={lid}')
                return str(lid)
        print(f'[pulsescore] EPL not found among {len(leagues)} leagues')
        return None
    except Exception as exc:
        print(f'[pulsescore] leagues error: {exc}')
        return None


def _parse_1x2(event: Dict) -> Tuple[Optional[float], Optional[float]]:
    """
    Extract (home_odd, away_odd) from a PulseScore event.
    Searches market groups for Fulltime Result / 1X2 market.
    """
    market_groups = event.get('mg') or event.get('markets') or []
    for mg in market_groups:
        mg_name = (mg.get('nm') or mg.get('name') or '').lower()
        if not any(kw in mg_name for kw in ('fulltime', 'match result', '1x2', 'winner', 'result')):
            continue

        outcomes: List[Dict] = mg.get('ma') or mg.get('outcomes') or mg.get('selections') or []
        odds_vals: List[float] = []
        draw_pos: Optional[int] = None

        for o in outcomes:
            nm  = (o.get('nm') or o.get('name') or '').strip()
            raw = o.get('od') or o.get('odds') or o.get('price') or o.get('decimal')
            try:
                odd = float(raw)
            except (TypeError, ValueError):
                continue
            if not (1.01 <= odd <= 50.0):
                continue
            if 'draw' in nm.lower():
                draw_pos = len(odds_vals)
            odds_vals.append(odd)

        if len(odds_vals) == 3 and draw_pos is not None:
            non_draw = [o for i, o in enumerate(odds_vals) if i != draw_pos]
            return non_draw[0], non_draw[1]
        if len(odds_vals) == 2:
            return odds_vals[0], odds_vals[1]

    return None, None


def fetch_b365_pulsescore(
    rapidapi_key: str = '',
    pulsescore_key: str = '',
) -> Dict[str, Dict[str, float]]:
    """
    Fetch Bet365 1x2 odds for upcoming EPL fixtures via PulseScore.

    Args:
        rapidapi_key:    RapidAPI key (bet365data on RapidAPI).
        pulsescore_key:  Direct PulseScore API key (pulsescore.net).

    Returns:
        {'Home vs Away': {'b365_hw': float, 'b365_aw': float}}
        Empty dict if no key is set or on any failure.
    """
    if not rapidapi_key and not pulsescore_key:
        return {}

    headers, base, path_prefix = _make_headers(rapidapi_key, pulsescore_key)
    results: Dict[str, Dict[str, float]] = {}

    league_id = _find_epl_id(base, headers, path_prefix)
    if not league_id:
        return {}

    try:
        r = httpx.get(
            f'{base}{path_prefix}/events',
            params={'league': league_id},
            headers=headers,
            timeout=12,
        )
        print(f'[pulsescore] events: HTTP {r.status_code}')
        if r.status_code != 200:
            print(f'[pulsescore] events body: {r.text[:300]}')
            return {}

        data = r.json()
        events = data if isinstance(data, list) else (
            data.get('data') or data.get('events') or data.get('results') or []
        )
        print(f'[pulsescore] {len(events)} events')

        for event in events:
            home_raw = (
                event.get('ht') or event.get('home_team') or
                (event.get('home') or {}).get('nm') or
                (event.get('home') or {}).get('name') or ''
            )
            away_raw = (
                event.get('at') or event.get('away_team') or
                (event.get('away') or {}).get('nm') or
                (event.get('away') or {}).get('name') or ''
            )
            if not home_raw or not away_raw:
                continue

            hw, aw = _parse_1x2(event)
            if hw and aw:
                key = f'{_norm(home_raw)} vs {_norm(away_raw)}'
                results[key] = {'b365_hw': hw, 'b365_aw': aw}
                print(f'[pulsescore] {key}: hw={hw} aw={aw}')

    except Exception as exc:
        print(f'[pulsescore] events error: {exc}')

    print(f'[pulsescore] enriched {len(results)} fixtures with real Bet365 odds')
    return results


def debug_probe(rapidapi_key: str = '', pulsescore_key: str = '') -> Dict:
    """Diagnostic for /api/debug-pulsescore — shows raw response structure."""
    if not rapidapi_key and not pulsescore_key:
        return {'error': 'No key set. Add RAPIDAPI_KEY or PULSESCORE_KEY to Vercel env vars.'}

    headers, base, path_prefix = _make_headers(rapidapi_key, pulsescore_key)
    out: Dict = {'base': base, 'auth': 'rapidapi' if rapidapi_key else 'direct', 'path_prefix': path_prefix}

    try:
        r = httpx.get(f'{base}{path_prefix}/leagues', headers=headers, timeout=10)
        out['leagues_status'] = r.status_code
        raw = r.json() if r.status_code == 200 else {}
        leagues = raw if isinstance(raw, list) else (raw.get('data') or raw.get('leagues') or [])
        out['leagues_count'] = len(leagues)
        out['leagues_sample'] = [
            {'nm': lg.get('nm') or lg.get('name'), 'id': lg.get('id') or lg.get('fi')}
            for lg in leagues[:12]
        ]
        epl = next(
            (lg for lg in leagues
             if any(kw in (lg.get('nm') or lg.get('name') or '').lower()
                    for kw in _EPL_KEYWORDS)),
            None,
        )
        out['epl_found'] = epl
    except Exception as exc:
        out['leagues_error'] = str(exc)
        return out

    if epl:
        lid = str(epl.get('id') or epl.get('fi') or '')
        try:
            r2 = httpx.get(
                f'{base}{path_prefix}/events',
                params={'league': lid},
                headers=headers,
                timeout=12,
            )
            out['events_status'] = r2.status_code
            data = r2.json() if r2.status_code == 200 else {}
            events = data if isinstance(data, list) else (
                data.get('data') or data.get('events') or []
            )
            out['events_count'] = len(events)
            if events:
                out['first_event_keys'] = list(events[0].keys())
                out['first_event_raw'] = str(events[0])[:800]
                hw, aw = _parse_1x2(events[0])
                out['first_event_parsed'] = {'hw': hw, 'aw': aw}
        except Exception as exc:
            out['events_error'] = str(exc)

    return out
