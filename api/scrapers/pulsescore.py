"""
PulseScore Bet365 1x2 odds scraper for EPL.

Supports two auth modes (whichever key is set):
  RapidAPI:   RAPIDAPI_KEY    → X-RapidAPI-Key, host bet365data.p.rapidapi.com
  Direct API: PULSESCORE_KEY  → X-Secret header, host pulsescore.net

Endpoints used:
  RapidAPI (bet365data.p.rapidapi.com):   /leagues, /events  (no path prefix — confirmed via path probe)
  Direct   (pulsescore.net):              /api/v2/bet365/leagues, /api/v2/bet365/events

  bet365data RapidAPI response structure (confirmed 2026-04-28):
    /leagues → list of {type, live, sport, tournament, leagueName, league (composite), events[]}
    league composite key format: 'Country||League Name'  e.g. 'England||Premier League'
    embedded events: [{home, away, pd (encoded odds)}, ...]

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
            '',             # RapidAPI: no prefix at all — /leagues, /events at root
        )
    return (
        {'X-Secret': pulsescore_key, 'Accept': 'application/json'},
        _DIRECT_BASE,
        '/api/v2/bet365',  # direct pulsescore.net: /api prefix required
    )


def _find_epl_league(base: str, headers: Dict, path_prefix: str = '') -> Optional[Dict]:
    """Call {path_prefix}/leagues and return the full EPL league object (including embedded events)."""
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
            # bet365data API uses 'leagueName' (not 'nm'/'name')
            name = (
                lg.get('leagueName') or lg.get('nm') or lg.get('name') or ''
            ).lower()
            if any(kw in name for kw in _EPL_KEYWORDS):
                # Composite ID is the 'league' field, e.g. 'England||Premier League'
                lid = lg.get('league') or lg.get('id') or lg.get('fi') or lg.get('league_id')
                print(f'[pulsescore] EPL: "{name}" league={lid}')
                return lg          # return full object — events are embedded
        print(f'[pulsescore] EPL not found among {len(leagues)} leagues')
        # Log first few leagueNames to help debug
        for lg in leagues[:5]:
            print(f'[pulsescore]   sample leagueName={lg.get("leagueName")} tournament={lg.get("tournament")}')
        return None
    except Exception as exc:
        print(f'[pulsescore] leagues error: {exc}')
        return None


def _parse_1x2(event: Dict) -> Tuple[Optional[float], Optional[float]]:
    """
    Extract (home_odd, away_odd) from a bet365data event.

    bet365data embedded event format (confirmed 2026-04-28):
      event['outcomes'] = [
        {'name': '1', 'decimal': '1.4200', 'od': '21/50', ...},  # home
        {'name': 'X', 'decimal': '4.3333', 'od': '10/3',  ...},  # draw
        {'name': '2', 'decimal': '7.5000', 'od': '13/2',  ...},  # away
      ]
    '1' = home win, 'X' = draw, '2' = away win.
    'decimal' holds the decimal odds directly — no conversion needed.
    """
    # Strategy 1: top-level 'outcomes' list (bet365data embedded event format)
    top_outcomes = event.get('outcomes')
    if top_outcomes and isinstance(top_outcomes, list):
        hw: Optional[float] = None
        aw: Optional[float] = None
        for o in top_outcomes:
            nm = str(o.get('name', '')).strip()
            raw = o.get('decimal') or o.get('od') or o.get('odds') or o.get('price')
            try:
                odd = float(raw)
            except (TypeError, ValueError):
                continue
            if not (1.01 <= odd <= 50.0):
                continue
            if nm == '1':
                hw = odd
            elif nm == '2':
                aw = odd
        if hw and aw:
            return hw, aw

    # Strategy 2: market groups (pulsescore.net direct API format)
    market_groups = event.get('mg') or event.get('markets') or []
    for mg in market_groups:
        mg_name = (mg.get('nm') or mg.get('name') or '').lower()
        if not any(kw in mg_name for kw in ('fulltime', 'match result', '1x2', 'winner', 'result')):
            continue

        outcomes: List[Dict] = mg.get('ma') or mg.get('outcomes') or mg.get('selections') or []
        odds_vals: List[float] = []
        draw_pos: Optional[int] = None

        for o in outcomes:
            nm2 = (o.get('nm') or o.get('name') or '').strip()
            raw = o.get('od') or o.get('odds') or o.get('price') or o.get('decimal')
            try:
                odd = float(raw)
            except (TypeError, ValueError):
                continue
            if not (1.01 <= odd <= 50.0):
                continue
            if 'draw' in nm2.lower() or nm2 == 'X':
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

    bet365data RapidAPI structure (confirmed 2026-04-28):
      GET /leagues  → list of league objects, each with embedded 'events' list.
      GET /events   → does NOT exist ("Endpoint '/events' does not exist").
      League name field: 'leagueName'  (e.g. 'England Premier League')
      League composite:  'league' key, e.g. 'United Kingdom||England Premier League'
      Event home/away:   'home' / 'away' plain strings
      Event odds:        'outcomes' list at top level —
                         [{'name':'1','decimal':'1.42'}, {'name':'X',...}, {'name':'2',...}]
                         '1'=home win, 'X'=draw, '2'=away win.

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

    epl_league = _find_epl_league(base, headers, path_prefix)
    if not epl_league:
        return {}

    # Events are embedded in the league object — /events endpoint does not exist
    # on bet365data.p.rapidapi.com (confirmed 2026-04-28).
    events: List[Dict] = epl_league.get('events') or []
    print(f'[pulsescore] {len(events)} embedded EPL events')

    for event in events:
        # bet365data embeds home/away as plain strings at top level.
        home_raw = (
            event.get('home') if isinstance(event.get('home'), str) else None
        ) or (
            event.get('ht') or event.get('home_team') or
            (event.get('home') or {}).get('nm') or
            (event.get('home') or {}).get('name') or ''
        )
        away_raw = (
            event.get('away') if isinstance(event.get('away'), str) else None
        ) or (
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
        else:
            print(f'[pulsescore] no odds parsed for {home_raw} vs {away_raw} — event keys: {list(event.keys())}')

    print(f'[pulsescore] enriched {len(results)} fixtures with real Bet365 odds')
    return results


def debug_probe(rapidapi_key: str = '', pulsescore_key: str = '') -> Dict:
    """Diagnostic for /api/debug-pulsescore — probes multiple path variants to find correct RapidAPI paths."""
    if not rapidapi_key and not pulsescore_key:
        return {'error': 'No key set. Add RAPIDAPI_KEY or PULSESCORE_KEY to Vercel env vars.'}

    headers, base, path_prefix = _make_headers(rapidapi_key, pulsescore_key)
    out: Dict = {'base': base, 'auth': 'rapidapi' if rapidapi_key else 'direct', 'path_prefix': path_prefix}

    # For RapidAPI: probe multiple path variants to find which one the host actually accepts.
    # RapidAPI may strip /api, /api/v2/bet365, or just /api — we don't know without testing.
    if rapidapi_key:
        path_candidates = [
            '/v2/bet365/leagues',   # our current assumption (strips /api)
            '/leagues',             # fully stripped (RapidAPI maps root → /api/v2/bet365)
            '/v1/bet365/leagues',   # v1 instead of v2
            '/api/v2/bet365/leagues',  # full path (no stripping)
            '/bet365/leagues',      # no version
        ]
        probe: Dict[str, int] = {}
        working_prefix: Optional[str] = None
        for candidate in path_candidates:
            try:
                r = httpx.get(f'{base}{candidate}', headers=headers, timeout=8)
                probe[candidate] = r.status_code
                if r.status_code == 200 and working_prefix is None:
                    working_prefix = candidate.replace('/leagues', '')
            except Exception as exc:
                probe[candidate] = -1
        out['path_probe'] = probe
        out['working_prefix'] = working_prefix

        if working_prefix is None:
            out['conclusion'] = 'All paths returned non-200. Subscription may not cover prematch endpoints, or key is for a different API.'
            return out

        # Use the working prefix for the full diagnostic
        path_prefix = working_prefix

    try:
        r = httpx.get(f'{base}{path_prefix}/leagues', headers=headers, timeout=10)
        out['leagues_status'] = r.status_code
        raw = r.json() if r.status_code == 200 else {}
        leagues = raw if isinstance(raw, list) else (raw.get('data') or raw.get('leagues') or [])
        out['leagues_count'] = len(leagues)
        # Show actual field names from first league object
        out['first_leagues_raw'] = [str(lg)[:300] for lg in leagues[:3]]
        # Use correct field names for bet365data API
        out['leagues_sample'] = [
            {
                'leagueName': lg.get('leagueName'),
                'league':     lg.get('league'),
                'tournament': lg.get('tournament'),
                'sport':      lg.get('sport'),
            }
            for lg in leagues[:15]
        ]
        # Detect EPL using leagueName (bet365data field)
        epl = next(
            (lg for lg in leagues
             if any(kw in (lg.get('leagueName') or lg.get('nm') or lg.get('name') or '').lower()
                    for kw in _EPL_KEYWORDS)),
            None,
        )
        if epl:
            # Don't serialise the full embedded events list — it's huge
            epl_meta = {k: v for k, v in epl.items() if k != 'events'}
            epl_meta['embedded_events_count'] = len(epl.get('events') or [])
            out['epl_found'] = epl_meta
        else:
            out['epl_found'] = None
    except Exception as exc:
        out['leagues_error'] = str(exc)
        return out

    if epl:
        # Use composite league key for /events call
        league_composite = epl.get('league', '')
        out['league_composite'] = league_composite

        # Show first embedded event (full, not truncated) so we can see odds field names
        embedded = epl.get('events') or []
        if embedded:
            out['first_embedded_event_keys'] = list(embedded[0].keys())
            out['first_embedded_event_raw'] = str(embedded[0])[:1200]

        # Also try the /events endpoint with the composite key
        try:
            r2 = httpx.get(
                f'{base}{path_prefix}/events',
                params={'league': league_composite},
                headers=headers,
                timeout=12,
            )
            out['events_status'] = r2.status_code
            if r2.status_code == 200:
                data = r2.json()
                events = data if isinstance(data, list) else (
                    data.get('data') or data.get('events') or []
                )
                out['events_count'] = len(events)
                if events:
                    out['first_event_keys'] = list(events[0].keys())
                    out['first_event_raw'] = str(events[0])[:1200]
                    hw, aw = _parse_1x2(events[0])
                    out['first_event_parsed'] = {'hw': hw, 'aw': aw}
            else:
                out['events_body_snippet'] = r2.text[:300]
        except Exception as exc:
            out['events_error'] = str(exc)

    return out
