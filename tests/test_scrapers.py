import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock
from api.scrapers.table import fetch_table
from api.scrapers.injuries import fetch_injuries
from api.scrapers.odds import fetch_pinnacle_odds, _fuzzy_match
from api.scrapers.polymarket import fetch_polymarket_prob

BBC_TABLE_HTML = """
<html><body>
<table class="gs-o-table">
<tbody>
<tr><td class="gs-o-table__cell--rank">1</td><td>Arsenal</td><td>60</td></tr>
<tr><td class="gs-o-table__cell--rank">2</td><td>Man City</td><td>58</td></tr>
</tbody>
</table>
</body></html>
"""

def test_fetch_table_returns_list():
    with patch('httpx.get') as mock:
        mock.return_value = MagicMock(status_code=200, text=BBC_TABLE_HTML)
        mock.return_value.raise_for_status = MagicMock()
        table = fetch_table()
    assert isinstance(table, list)
    assert len(table) >= 1
    assert 'team' in table[0]
    assert 'position' in table[0]

def test_fetch_table_top8_extracted():
    with patch('httpx.get') as mock:
        mock.return_value = MagicMock(status_code=200, text=BBC_TABLE_HTML)
        mock.return_value.raise_for_status = MagicMock()
        table = fetch_table()
    top8 = [t['team'] for t in table[:8]]
    assert 'Arsenal' in top8

def test_fetch_pinnacle_odds_structure():
    mock_response = [{
        'home_team': 'Arsenal',
        'away_team': 'Chelsea',
        'bookmakers': [{
            'key': 'pinnacle',
            'markets': [{'key': 'totals', 'outcomes': [
                {'name': 'Over', 'price': 1.88},
                {'name': 'Under', 'price': 1.95},
            ]}]
        }]
    }]
    with patch('httpx.get') as mock:
        mock.return_value = MagicMock(status_code=200)
        mock.return_value.raise_for_status = MagicMock()
        mock.return_value.json.return_value = mock_response
        odds = fetch_pinnacle_odds('Arsenal', 'Chelsea', api_key='test')
    assert isinstance(odds, dict)

def test_fetch_injuries_returns_list():
    html = '<html><body><table><tr><td>Bukayo Saka</td><td>Doubtful</td></tr></table></body></html>'
    with patch('httpx.get') as mock:
        mock.return_value = MagicMock(status_code=200, text=html)
        mock.return_value.raise_for_status = MagicMock()
        injuries = fetch_injuries('Arsenal')
    assert isinstance(injuries, list)

def test_fuzzy_match_distinguishes_manchester_clubs():
    assert _fuzzy_match('Manchester City', 'Manchester City') is True
    assert _fuzzy_match('Man City', 'Manchester City') is True
    assert _fuzzy_match('Manchester United', 'Manchester City') is False
