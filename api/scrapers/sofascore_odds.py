"""
Sofascore odds scraper — fetches 1x2 soft-book odds (provider 1, typically Bet365)
for upcoming EPL fixtures by gameweek round.

Used to populate b365_hw / b365_aw in the fixture dict so the Pinnacle vs
soft-book comparison row renders on signal cards.

Caller: api/scrapers/fixtures.py (fetch_upcoming_fixtures)
"""
from typing import Dict, List, Optional
import httpx

# More complete browser headers — required by the odds endpoint from cloud IPs
_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-GB,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Origin': 'https://www.sofascore.com',
    'Referer': 'https://www.sofascore.com/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
}

# EPL 2025-26 on Sofascore
_TOURNAMENT_ID = 17
_SEASON_ID = 76986

# Sofascore team name → internal football-data.co.uk name
_NAME_MAP = {
    'Leeds United':             'Leeds',
    'Manchester City':          'Man City',
    'Manchester United':        'Man United',
    'Tottenham Hotspur':        'Tottenham',
    'Wolverhampton':            'Wolves',
    'Brighton & Hove Albion':   'Brighton',
    'West Ham United':          'West Ham',
    'Newcastle United':         'Newcastle',
    'Nottingham Forest':        "Nott'm Forest",
}


def _normalise(name: str) -> str:
    return _NAME_MAP.get(name, name)


def _frac_to_dec(frac: str) -> Optional[float]:
    """Convert fractional odds string '67/100' → decimal 1.67."""
    try:
        n, d = frac.split('/')
        return round(1 + int(n) / int(d), 2)
    except Exception:
        return None


def fetch_sofascore_odds_for_rounds(rounds: List[int]) -> Dict[str, Dict[str, float]]:
    """
    Return a dict keyed by 'Home vs Away' → {'b365_hw': float, 'b365_aw': float}
    for all fixtures in the given round numbers.

    Makes 1 round-list call + 1 odds call per fixture.
    Returns {} on any failure; logs errors to stdout (visible in Vercel logs).
    """
    results: Dict[str, Dict[str, float]] = {}

    for round_num in rounds:
        try:
            url = (
                f'https://api.sofascore.com/api/v1/unique-tournament/'
                f'{_TOURNAMENT_ID}/season/{_SEASON_ID}/events/round/{round_num}'
            )
            r = httpx.get(url, headers=_HEADERS, timeout=10)
            if r.status_code != 200:
                print(f'[sofascore_odds] round {round_num} → {r.status_code}')
                continue
            events = r.json().get('events', [])
            print(f'[sofascore_odds] round {round_num} → {len(events)} events')
        except Exception as exc:
            print(f'[sofascore_odds] round {round_num} fetch error: {exc}')
            continue

        for event in events:
            eid = event.get('id')
            home = _normalise(event.get('homeTeam', {}).get('name', ''))
            away = _normalise(event.get('awayTeam', {}).get('name', ''))
            if not eid or not home or not away:
                continue

            try:
                odds_url = f'https://api.sofascore.com/api/v1/event/{eid}/odds/1/all'
                r2 = httpx.get(odds_url, headers=_HEADERS, timeout=10)
                if r2.status_code != 200:
                    print(f'[sofascore_odds] {home} vs {away} odds → {r2.status_code}')
                    continue
                markets = r2.json().get('markets', [])
                ft = next(
                    (m for m in markets if m.get('marketName') == 'Full time'),
                    None,
                )
                if not ft:
                    print(f'[sofascore_odds] {home} vs {away}: no Full time market')
                    continue
                choices = {
                    c['name']: _frac_to_dec(c.get('fractionalValue', ''))
                    for c in ft.get('choices', [])
                }
                hw = choices.get('1')
                aw = choices.get('2')
                if hw and aw:
                    key = f'{home} vs {away}'
                    results[key] = {'b365_hw': hw, 'b365_aw': aw}
                    print(f'[sofascore_odds] {key}: hw={hw} aw={aw}')
            except Exception as exc:
                print(f'[sofascore_odds] {home} vs {away} odds error: {exc}')
                continue

    print(f'[sofascore_odds] total enriched: {len(results)}')
    return results
