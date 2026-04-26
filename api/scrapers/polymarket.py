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
    text = soup.get_text(' ')

    # Try to find a percentage near the home team name
    home_clean = home.lower()
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for i, line in enumerate(lines):
        if home_clean in line.lower():
            # Look for a percentage in this line or the next 2 lines
            window = ' '.join(lines[i:i+3])
            pcts = re.findall(r'(\d{1,3})%', window)
            if pcts:
                try:
                    p = float(pcts[0]) / 100
                    if 0.0 < p < 1.0:
                        return p
                except ValueError:
                    pass

    # Fallback: first valid percentage on page (documented as unreliable)
    all_pcts = re.findall(r'(\d{1,3})%', text)
    for pct in all_pcts:
        try:
            p = float(pct) / 100
            if 0.05 < p < 0.95:  # filter out obvious UI percentages (100%, 0%)
                return p
        except ValueError:
            continue
    return None
