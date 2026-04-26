"""
Injury scraper: premierinjuries.com (primary) + BBC Sport (secondary).
Returns list of {player, status, role, source} dicts.
"""
from typing import List, Dict
import httpx
from bs4 import BeautifulSoup

PREMIER_INJURIES_URL = 'https://www.premierinjuries.com/injury-table.php'


def fetch_injuries(team: str) -> List[Dict]:
    """Fetch injury list for a team. Returns [] on failure."""
    injuries = []
    injuries.extend(_fetch_premier_injuries(team))
    injuries.extend(_fetch_bbc_injuries(team))
    # Deduplicate by player name
    seen = set()
    unique = []
    for inj in injuries:
        key = inj.get('player', '').lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(inj)
    return unique


def _fetch_premier_injuries(team: str) -> List[Dict]:
    try:
        r = httpx.get(PREMIER_INJURIES_URL, timeout=15,
                      headers={'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, 'lxml')
    results = []
    for row in soup.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 3:
            continue
        text = row.get_text(' ')
        if team.lower() in text.lower():
            results.append({
                'player': cells[0].get_text(strip=True),
                'status': cells[1].get_text(strip=True) if len(cells) > 1 else 'Unknown',
                'role': '',
                'source': 'premierinjuries.com',
            })
    return results


def _fetch_bbc_injuries(team: str) -> List[Dict]:
    slug = team.lower().replace(' ', '-').replace("'", '')
    url = f'https://www.bbc.com/sport/football/teams/{slug}/injuries-and-suspensions'
    try:
        r = httpx.get(url, timeout=15,
                      headers={'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, 'lxml')
    results = []
    for row in soup.select('table tr'):
        cells = row.find_all('td')
        if len(cells) >= 2:
            results.append({
                'player': cells[0].get_text(strip=True),
                'status': cells[1].get_text(strip=True),
                'role': cells[2].get_text(strip=True) if len(cells) > 2 else '',
                'source': 'BBC Sport',
            })
    return results
