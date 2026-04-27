"""
ESPN event summary odds scraper — fetches DraftKings 1x2 moneyline
for upcoming EPL fixtures. Accessible from Vercel cloud IPs (confirmed 2026-04-27).

American moneyline → decimal:
  positive (+360) → 1 + 360/100 = 4.60
  negative (-145) → 1 + 100/145 = 1.69

Used to populate b365_hw / b365_aw in the fixture dict so the soft-book
comparison row renders on signal cards. Source is DraftKings (via ESPN),
which serves the same comparison purpose as Bet365.

Caller: api/scrapers/fixtures.py (fetch_upcoming_fixtures)
"""
from datetime import date, timedelta
from typing import Dict
import httpx

_LEAGUE = 'eng.1'
_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json',
}

# ESPN team display name → internal football-data.co.uk name
_NAME_MAP = {
    'Nottingham Forest':        "Nott'm Forest",
    'Manchester City':          'Man City',
    'Manchester United':        'Man United',
    'Tottenham Hotspur':        'Tottenham',
    'Wolverhampton Wanderers':  'Wolves',
    'Brighton & Hove Albion':   'Brighton',
    'West Ham United':          'West Ham',
    'Newcastle United':         'Newcastle',
    'Leeds United':             'Leeds',
    'Leicester City':           'Leicester',
    'Ipswich Town':             'Ipswich',
    'Luton Town':               'Luton',
    'Sheffield United':         'Sheffield United',
}


def _normalise(name: str) -> str:
    return _NAME_MAP.get(name, name)


def _american_to_decimal(ml: float) -> float:
    """Convert American moneyline to decimal odds, rounded to 3 dp."""
    if ml > 0:
        return round(1 + ml / 100, 3)
    return round(1 + 100 / abs(ml), 3)


def fetch_espn_dk_odds() -> Dict[str, Dict[str, float]]:
    """
    Return dict keyed 'Home vs Away' → {'b365_hw': float, 'b365_aw': float}
    using DraftKings moneyline from ESPN event summaries.

    Covers today + 21 days of EPL fixtures. One scoreboard call +
    one summary call per fixture. Returns {} on any failure.
    """
    results: Dict[str, Dict[str, float]] = {}

    # Scoreboard: get all EPL events in the next 3 weeks
    today = date.today()
    end = today + timedelta(days=21)
    dates = f"{today.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
    sb_url = (f'https://site.api.espn.com/apis/site/v2/sports/soccer/'
              f'{_LEAGUE}/scoreboard?dates={dates}')

    try:
        r = httpx.get(sb_url, headers=_HEADERS, timeout=10)
        if r.status_code != 200:
            print(f'[espn_odds] scoreboard {r.status_code}')
            return {}
        events = r.json().get('events', [])
        print(f'[espn_odds] scoreboard → {len(events)} events')
    except Exception as exc:
        print(f'[espn_odds] scoreboard error: {exc}')
        return {}

    for event in events:
        event_id = event.get('id')
        competitions = event.get('competitions', [])
        if not event_id or not competitions:
            continue

        # Extract home/away team names from competitors list
        competitors = competitions[0].get('competitors', [])
        home_name = away_name = None
        for c in competitors:
            name = _normalise(c.get('team', {}).get('displayName', ''))
            if c.get('homeAway') == 'home':
                home_name = name
            elif c.get('homeAway') == 'away':
                away_name = name

        if not home_name or not away_name:
            continue

        # Event summary → pickcenter[0] contains DraftKings moneyline
        try:
            r2 = httpx.get(
                f'https://site.api.espn.com/apis/site/v2/sports/soccer/'
                f'{_LEAGUE}/summary?event={event_id}',
                headers=_HEADERS, timeout=10,
            )
            if r2.status_code != 200:
                continue
            pc = r2.json().get('pickcenter', [])
            if not pc:
                continue
            home_ml = pc[0].get('homeTeamOdds', {}).get('moneyLine')
            away_ml = pc[0].get('awayTeamOdds', {}).get('moneyLine')
            if home_ml is not None and away_ml is not None:
                key = f'{home_name} vs {away_name}'
                hw = _american_to_decimal(home_ml)
                aw = _american_to_decimal(away_ml)
                results[key] = {'b365_hw': hw, 'b365_aw': aw}
                print(f'[espn_odds] {key}: hw={hw} aw={aw} (DK)')
        except Exception as exc:
            print(f'[espn_odds] event {event_id} error: {exc}')
            continue

    print(f'[espn_odds] total enriched: {len(results)}')
    return results
