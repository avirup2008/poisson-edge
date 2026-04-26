"""Polymarket EPL match page scraper."""
from typing import Optional
import re
import httpx
from bs4 import BeautifulSoup


def fetch_polymarket_prob(home: str, away: str, match_date: str) -> Optional[float]:
    """match_date: 'YYYY-MM-DD'. Returns float 0-1 or None."""
    slug = _build_slug(home, away, match_date)
    url = f'https://polymarket.com/sports/epl/{slug}'
    try:
        r = httpx.get(url, timeout=15,
                      headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 404:
            return None
        r.raise_for_status()
    except Exception:
        return None

    return _parse_probability(r.text, home)


def _build_slug(home: str, away: str, date: str) -> str:
    def clean(s):
        return s.lower().replace(' ', '-').replace("'", '').replace('.', '')
    return f'epl-{clean(home)}-{clean(away)}-{date}'


def _parse_probability(html: str, home: str) -> Optional[float]:
    soup = BeautifulSoup(html, 'lxml')
    text = soup.get_text()
    matches = re.findall(r'(\d{1,3})%', text)
    if matches:
        try:
            return float(matches[0]) / 100
        except ValueError:
            return None
    return None
