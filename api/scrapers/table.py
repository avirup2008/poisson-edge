"""BBC Sport Premier League table scraper."""
from typing import List, Dict
import httpx
from bs4 import BeautifulSoup

TABLE_URL = 'https://www.bbc.com/sport/football/premier-league/table'


def fetch_table() -> List[Dict]:
    """
    Returns list of {position, team} dicts ordered 1->20.
    Falls back to empty list on any error.
    """
    try:
        r = httpx.get(TABLE_URL, timeout=15,
                      headers={'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, 'lxml')
    table = soup.find('table', class_='gs-o-table')
    if not table:
        return []

    rows = []
    for i, tr in enumerate(table.find('tbody').find_all('tr'), start=1):
        cells = tr.find_all('td')
        if len(cells) < 2:
            continue
        team_text = cells[1].get_text(strip=True)
        rows.append({'position': i, 'team': team_text})

    return rows
