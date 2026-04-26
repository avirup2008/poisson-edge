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


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows missing required columns and cast goal columns to int."""
    required = {'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG'}
    df = df.dropna(subset=list(required))
    df['FTHG'] = df['FTHG'].astype(int)
    df['FTAG'] = df['FTAG'].astype(int)
    return df


def load_current_season() -> pd.DataFrame:
    """Load and clean the current season CSV (24h TTL)."""
    return _clean_df(load_season_csv(CURRENT_SEASON, ttl_hours=24))


def load_all_seasons() -> pd.DataFrame:
    """
    Load and concatenate all seasons.
    Current season: 24h TTL. Historical: fetch once (TTL=10 years).
    Used for backtest display and result-marking only — NOT for live ratings.
    """
    frames = []

    try:
        frames.append(load_season_csv(CURRENT_SEASON, ttl_hours=24))
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

    return _clean_df(pd.concat(frames, ignore_index=True))


def compute_ratings(df: pd.DataFrame) -> Tuple[Dict, Dict]:
    """Compute opponent-adjusted attack/defence ratings from a season DataFrame."""
    return compute_opponent_adjusted_ratings(df)


@dataclass
class DataStore:
    """
    Singleton-style store initialised at FastAPI startup.

    Two DataFrames are maintained deliberately:
      current_season  — 2025-26 data only.  Used for opponent-adjusted ratings
                        and the form blend inside calculate_lambdas().  Passing
                        only current-season data prevents stale multi-season
                        averages from inflating ratings for teams whose form has
                        changed dramatically (e.g. a relegated side).
      historical      — All 16 seasons concatenated.  Used for backtest display
                        (/api/backtest total_matches) and auto_mark_results().

    ELO ratings are pre-computed from the full 16-season history and stored as
    a constant in poisson_edge_model.py — they are not recomputed here.
    """
    historical: pd.DataFrame = field(default_factory=pd.DataFrame)
    current_season: pd.DataFrame = field(default_factory=pd.DataFrame)
    g_atk: Dict = field(default_factory=dict)
    g_def: Dict = field(default_factory=dict)
    elo_ratings: Dict = field(default_factory=lambda: dict(ELO_RATINGS))

    def load(self) -> None:
        """Called once at startup. Downloads CSVs if needed, computes ratings."""
        self.historical = load_all_seasons()

        # Opponent-adjusted ratings from current season only.
        # Falls back to full history if current season has too few rows (<10).
        try:
            cs = load_current_season()
            if len(cs) >= 10:
                self.current_season = cs
            else:
                logger.warning(
                    "Current season has only %d rows — falling back to full history for ratings",
                    len(cs),
                )
                self.current_season = self.historical
        except Exception as exc:
            logger.error("Failed to load current season for ratings: %s — using full history", exc)
            self.current_season = self.historical

        self.g_atk, self.g_def = compute_ratings(self.current_season)

    @property
    def ready(self) -> bool:
        return not self.historical.empty
