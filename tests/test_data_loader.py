import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from api.data_loader import (
    season_url, cache_path, is_stale, load_season_csv,
    load_all_seasons, compute_ratings, DataStore,
)

def test_season_url():
    assert season_url('2526') == 'https://www.football-data.co.uk/mmz4281/2526/E0.csv'

def test_cache_path_contains_season():
    p = cache_path('2526')
    assert '2526' in str(p)

def test_is_stale_nonexistent_file(tmp_path):
    assert is_stale(tmp_path / 'missing.csv', ttl_hours=24) is True

def test_is_stale_fresh_file(tmp_path):
    f = tmp_path / 'test.csv'
    f.write_text('data')
    assert is_stale(f, ttl_hours=24) is False

def test_load_season_csv_returns_dataframe(tmp_path, monkeypatch):
    import api.data_loader as dl
    monkeypatch.setattr(dl, 'CACHE_DIR', tmp_path)
    csv_content = 'HomeTeam,AwayTeam,FTHG,FTAG\nArsenal,Chelsea,2,1\n'
    with patch('httpx.get') as mock_get:
        mock_get.return_value = MagicMock(status_code=200, text=csv_content)
        df = load_season_csv('2526', ttl_hours=0)
    assert isinstance(df, pd.DataFrame)
    assert 'HomeTeam' in df.columns

def test_compute_ratings_returns_dicts():
    df = pd.DataFrame({
        'HomeTeam': ['Arsenal', 'Chelsea', 'Arsenal'],
        'AwayTeam': ['Chelsea', 'Arsenal', 'Spurs'],
        'FTHG': [2, 1, 3],
        'FTAG': [1, 2, 0],
    })
    atk, def_ = compute_ratings(df)
    assert isinstance(atk, dict)
    assert isinstance(def_, dict)
    assert 'Arsenal' in atk
