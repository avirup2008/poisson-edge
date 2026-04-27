"""
Betexplorer Bet365 1x2 odds scraper for EPL fixtures.
https://www.betexplorer.com/soccer/england/premier-league/

Used as fallback when OddsAPI plan does not include the bet365 bookmaker.
One league-page request + one per-match request (max 8 fixtures).

Caller: api/scrapers/fixtures.py (fetch_upcoming_fixtures)
"""
import re
import httpx
from typing import Dict, List, Optional, Tuple

_BASE = 'https://www.betexplorer.com'
_LEAGUE_URL = f'{_BASE}/soccer/england/premier-league/'

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-GB,en;q=0.5',
    'Connection': 'keep-alive',
    'Referer': 'https://www.google.com/',
}

# Betexplorer display name → internal name (same pattern as other scrapers)
_NAME_MAP: Dict[str, str] = {
    'Nottingham Forest':        "Nott'm Forest",
    "Nott'm Forest":            "Nott'm Forest",
    'Manchester City':          'Man City',
    'Manchester United':        'Man United',
    'Tottenham Hotspur':        'Tottenham',
    'Wolverhampton Wanderers':  'Wolves',
    'Wolverhampton':            'Wolves',
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
    s = name.strip()
    return _NAME_MAP.get(s, s)


def _to_float(s: str) -> Optional[float]:
    try:
        v = float(s.strip())
        return v if 1.01 <= v <= 50.0 else None
    except (ValueError, TypeError):
        return None


def _extract_match_heading(html: str) -> Optional[Tuple[str, str]]:
    """
    Return (home_raw, away_raw) from betexplorer match page.
    Tries multiple patterns: h1, title, og:title.
    """
    # Pattern 1: <h1 class="...">Home - Away</h1>
    m = re.search(r'<h1[^>]*>([^<]+) - ([^<]+)</h1>', html)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # Pattern 2: <title>Home - Away odds...</title>
    m = re.search(r'<title>([^|<-]+?) - ([^|<]+?) odds', html)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # Pattern 3: og:title
    m = re.search(r'property="og:title"[^>]*content="([^"]+) - ([^"]+)"', html)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    return None


def _extract_bet365_odds(html: str) -> Optional[Dict[str, float]]:
    """
    Extract Bet365 1x2 odds from a betexplorer match page.
    Returns {'b365_hw': float, 'b365_aw': float} or None.

    Betexplorer renders odds in a table where each bookmaker row has a
    data-bk attribute, followed by three <td> cells: home / draw / away.
    """
    # Strategy 1: data-bk attribute (betexplorer native markup)
    m = re.search(
        r'data-bk="(?:Bet365|bet365)"[^>]*>.*?'
        r'<td[^>]*>([\d]+\.[\d]+)</td>.*?'
        r'<td[^>]*>([\d]+\.[\d]+)</td>.*?'
        r'<td[^>]*>([\d]+\.[\d]+)</td>',
        html, re.DOTALL | re.IGNORECASE,
    )
    if m:
        hw = _to_float(m.group(1))
        aw = _to_float(m.group(3))
        if hw and aw:
            print(f'[betexplorer] strategy1 hw={hw} aw={aw}')
            return {'b365_hw': hw, 'b365_aw': aw}

    # Strategy 2: bookmaker name text followed by three decimal odds
    m2 = re.search(
        r'>(?:Bet365|bet365)<[^>]*>.*?'
        r'([\d]{1,2}\.[\d]{2})[^<]{0,60}'
        r'([\d]{1,2}\.[\d]{2})[^<]{0,60}'
        r'([\d]{1,2}\.[\d]{2})',
        html, re.DOTALL | re.IGNORECASE,
    )
    if m2:
        hw = _to_float(m2.group(1))
        aw = _to_float(m2.group(3))
        if hw and aw:
            print(f'[betexplorer] strategy2 hw={hw} aw={aw}')
            return {'b365_hw': hw, 'b365_aw': aw}

    # Strategy 3: JSON embedded in page
    m3 = re.search(
        r'"(?:bet365|Bet365)"\s*:\s*\{[^}]*"(?:home|1)"\s*:\s*([\d.]+)[^}]*"(?:away|2)"\s*:\s*([\d.]+)',
        html, re.IGNORECASE,
    )
    if m3:
        hw = _to_float(m3.group(1))
        aw = _to_float(m3.group(2))
        if hw and aw:
            print(f'[betexplorer] strategy3 hw={hw} aw={aw}')
            return {'b365_hw': hw, 'b365_aw': aw}

    return None


def fetch_b365_epl() -> Dict[str, Dict[str, float]]:
    """
    Scrape Bet365 1x2 odds for upcoming EPL fixtures from betexplorer.

    Returns:
        {'Home vs Away': {'b365_hw': float, 'b365_aw': float}}
        Empty dict on failure or if betexplorer blocks Vercel IPs.
    """
    results: Dict[str, Dict[str, float]] = {}

    # Step 1: fetch league page to get match links
    try:
        resp = httpx.get(
            _LEAGUE_URL, headers=_HEADERS, timeout=12, follow_redirects=True,
        )
        print(f'[betexplorer] league page: HTTP {resp.status_code}')
        if resp.status_code != 200:
            return {}
        league_html = resp.text
    except Exception as exc:
        print(f'[betexplorer] league page error: {exc}')
        return {}

    # Step 2: extract match links
    # URL pattern: /soccer/england/premier-league/chelsea-nott-m-forest/abc123/
    links: List[str] = list(dict.fromkeys(re.findall(
        r'href="(/soccer/england/premier-league/[^/"]+/[a-zA-Z0-9]+/)"',
        league_html,
    )))
    print(f'[betexplorer] found {len(links)} match links')

    # Step 3: per-match scrape — capped at 8 to avoid Vercel timeout
    for link in links[:8]:
        try:
            r2 = httpx.get(
                f'{_BASE}{link}',
                headers={**_HEADERS, 'Referer': _LEAGUE_URL},
                timeout=9,
                follow_redirects=True,
            )
            if r2.status_code != 200:
                print(f'[betexplorer] {link}: HTTP {r2.status_code}')
                continue
            page = r2.text

            teams = _extract_match_heading(page)
            if not teams:
                print(f'[betexplorer] {link}: could not extract team names')
                continue
            home_raw, away_raw = teams
            home = _norm(home_raw)
            away = _norm(away_raw)

            odds = _extract_bet365_odds(page)
            if odds:
                key = f'{home} vs {away}'
                results[key] = odds
                print(f'[betexplorer] {key}: b365_hw={odds["b365_hw"]} b365_aw={odds["b365_aw"]}')
            else:
                print(f'[betexplorer] {home} vs {away}: no Bet365 odds in page')

        except Exception as exc:
            print(f'[betexplorer] {link} error: {exc}')

    print(f'[betexplorer] enriched {len(results)} fixtures with B365 odds')
    return results


def debug_probe() -> Dict:
    """
    Lightweight probe used by /api/debug-betexplorer.
    Returns HTTP status, HTML snippet, match links, and parsed odds for the first match.
    Does NOT run the full multi-match scrape.
    """
    out: Dict = {}

    try:
        r = httpx.get(_LEAGUE_URL, headers=_HEADERS, timeout=10, follow_redirects=True)
        out['league_status'] = r.status_code
        out['league_final_url'] = str(r.url)
        html = r.text if r.status_code == 200 else ''
        out['league_html_len'] = len(html)
        out['league_html_snippet'] = html[:800] if html else ''

        if html:
            links = list(dict.fromkeys(re.findall(
                r'href="(/soccer/england/premier-league/[^/"]+/[a-zA-Z0-9]+/)"',
                html,
            )))
            out['match_links_found'] = len(links)
            out['match_links_sample'] = links[:5]

            if links:
                first = links[0]
                try:
                    r2 = httpx.get(
                        f'{_BASE}{first}',
                        headers={**_HEADERS, 'Referer': _LEAGUE_URL},
                        timeout=9, follow_redirects=True,
                    )
                    out['match_page_status'] = r2.status_code
                    out['match_page_final_url'] = str(r2.url)
                    page = r2.text if r2.status_code == 200 else ''
                    out['match_page_html_len'] = len(page)

                    if page:
                        out['teams_extracted'] = _extract_match_heading(page)
                        out['bet365_odds'] = _extract_bet365_odds(page)

                        # Show the context around 'bet365' in the HTML
                        idx = page.lower().find('bet365')
                        if idx >= 0:
                            out['bet365_html_context'] = page[max(0, idx - 60):idx + 300]
                        else:
                            out['bet365_found_in_html'] = False

                        out['match_page_snippet'] = page[:1200]

                except Exception as exc:
                    out['match_page_error'] = str(exc)

    except Exception as exc:
        out['league_error'] = str(exc)

    return out
