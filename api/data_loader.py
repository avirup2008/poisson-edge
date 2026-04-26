"""
Data loading, CSV caching, and opponent-adjusted ratings.
All logic here; api/main.py calls DataStore only.
"""
import logging
import os
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Tuple

import httpx
import pandas as pd

from model.poisson_edge_model import compute_opponent_adjusted_ratings, ELO_RATINGS

logger = logging.getLogger(__name__)

# Use /tmp on Vercel (project directory is read-only in serverless)
if os.environ.get('VERCEL'):
    CACHE_DIR = Path('/tmp/poisson-edge-cache')
else:
    CACHE_DIR = Path(__file__).parent.parent / 'data' / 'cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CURRENT_SEASON = '2526'
HISTORICAL_SEASONS = [
    '2425', '2324', '2223', '2122', '2021',
    '1920', '1819', '1718', '1617', '1516',
    '1415', '1314', '1213', '1112', '1011',
]


def season_url(season_code: str) -> str:
    return f'https://www.football-data.co.uk/mmz4281/{season_code}/E0.csv'


def cache_path(season_code: str) -> Path:
    return CACHE_DIR / f'E0_{season_code}.csv'


def is_stale(path: Path, ttl_hours: float = 24) -> bool:
    if not path.exists():
        return True
    age = time.time() - path.stat().st_mtime
    return age > ttl_hours * 3600


def load_season_csv(season_code: str, ttl_hours: float = 24 * 365) -> pd.DataFrame:
    """Fetch season CSV from football-data.co.uk, cache locally."""
    path = cache_path(season_code)
    if not is_stale(path, ttl_hours):
        return pd.read_csv(path, on_bad_lines='skip')

    url = season_url(season_code)
    r = httpx.get(url, timeout=30)
    r.raise_for_status()
    path.write_text(r.text, encoding='utf-8')
    return pd.read_csv(path, on_bad_lines='skip')


def load_all_seasons() -> pd.DataFrame:
    """
    Load and concatenate all seasons.
    Current season: 24h TTL. Historical: fetch once (TTL=10 years).
    """
    frames = []

    try:
        current = load_season_csv(CURRENT_SEASON, ttl_hours=24)
        frames.append(current)
    except Exception as exc:
        logger.error("Failed to load current season %s: %s", CURRENT_SEASON, exc)

    for code in HISTORICAL_SEASONS:
        try:
            df = load_season_csv(code, ttl_hours=24 * 365 * 10)
            frames.append(df)
        except Exception as exc:
            logger.warning("Failed to load season %s: %s", code, exc)

    if not frames:
        raise RuntimeError("No season data could be loaded — check network and cache")

    combined = pd.concat(frames, ignore_index=True)
    required = {'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG'}
    combined = combined.dropna(subset=list(required))
    combined['FTHG'] = combined['FTHG'].astype(int)
    combined['FTAG'] = combined['FTAG'].astype(int)
    return combined


def compute_ratings(df: pd.DataFrame) -> Tuple[Dict, Dict]:
    """Compute opponent-adjusted attack/defence ratings from a season DataFrame."""
    return compute_opponent_adjusted_ratings(df)


@dataclass
class DataStore:
    """
    Singleton-style store initialised at FastAPI startup.
    Holds historical data + pre-computed ratings in memory.
    """
    historical: pd.DataFrame = field(default_factory=pd.DataFrame)
    g_atk: Dict = field(default_factory=dict)
    g_def: Dict = field(default_factory=dict)
    elo_ratings: Dict = field(default_factory=lambda: dict(ELO_RATINGS))

    def load(self) -> None:
        """Called once at startup. Downloads CSVs if needed, computes ratings."""
        self.historical = load_all_seasons()
        self.g_atk, self.g_def = compute_ratings(self.historical)

    @property
    def ready(self) -> bool:
        return not self.historical.empty
