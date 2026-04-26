# POISSON-EDGE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working POISSON-EDGE v4.1 signal dashboard — Python model + FastAPI backend + 4-page vanilla JS frontend — that computes live EPL betting signals from real data sources.

**Architecture:** The locked Python model (`model/poisson_edge_model.py`) is called by a thin FastAPI layer that handles data loading, scraping, and JSON serialisation. The frontend is plain HTML/CSS/JS — four pages that fetch from the API on load. No framework, no build step.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, numpy, scipy, pandas, httpx, BeautifulSoup4, python-dotenv. Frontend: vanilla HTML/CSS/JS (no npm, no bundler).

---

## File Map

```
model/
  poisson_edge_model.py     # The locked model — drop in, do not edit

api/
  __init__.py
  main.py                   # FastAPI app — routes only, no logic
  data_loader.py            # CSV fetch + cache (24h TTL for current season)
  signal_engine.py          # Orchestrates model → signals for a full GW
  scrapers/
    __init__.py
    table.py                # BBC Sport live league table
    injuries.py             # premierinjuries.com + BBC Sport team pages
    odds.py                 # OddsAPI wrapper (Pinnacle odds)
    polymarket.py           # Polymarket EPL match page scraper

frontend/
  index.html                # Signal Board
  bankroll.html             # Bankroll + equity curve
  backtest.html             # Historical backtest results
  model.html                # Λ Model parameters + calibration
  css/
    globals.css             # Design tokens (dark/light, gold/blue system)
  js/
    theme.js                # Dark/light toggle, persisted to localStorage
    api.js                  # fetch() wrappers for all API endpoints
    signals.js              # Signal Board page logic
    bankroll.js             # Bankroll page logic
    backtest.js             # Backtest page logic
    model_page.js           # Λ Model page logic

data/
  cache/                    # gitignored — auto-downloaded CSVs live here
  bankroll.json             # Local ledger: bets placed, outcomes, P&L
  fixtures.json             # Current GW fixtures (manually maintained)

tests/
  test_model.py             # Ports the __main__ self-tests + adds coverage
  test_data_loader.py
  test_signal_engine.py
  test_scrapers.py

.env.example                # ODDS_API_KEY=your_key_here
requirements.txt            # Already exists
```

---

## Task 1: Drop in the model + install dependencies

**Files:**
- Create: `model/poisson_edge_model.py`
- Modify: `requirements.txt`
- Create: `.env.example`
- Create: `tests/test_model.py`

- [ ] **Step 1: Copy model file into project**

```bash
cp /Users/avi/Downloads/poisson_edge_model.py \
   /Users/avi/Downloads/Claude/Code/POISSON-EDGE/model/poisson_edge_model.py
```

- [ ] **Step 2: Update requirements.txt with scraping deps**

Replace contents of `requirements.txt`:
```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
numpy>=1.26.0
scipy>=1.13.0
pandas>=2.2.0
httpx>=0.27.0
python-dotenv>=1.0.0
beautifulsoup4>=4.12.0
lxml>=5.2.0
```

- [ ] **Step 3: Create .env.example**

```
ODDS_API_KEY=your_oddsapi_key_here
BANKROLL=1000.00
```

- [ ] **Step 4: Create virtual environment and install**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 5: Write test_model.py — port the __main__ self-tests**

Create `tests/test_model.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from model.poisson_edge_model import (
    build_score_matrix, extract_probabilities, poisson_pmf,
    dc_correction, elo_hw_probability, apply_elo_ensemble,
    fatigue_multiplier, calculate_ev, classify_signal, kelly_stake,
    apply_h2h_gate, check_probability_gate, check_pinnacle,
    check_structural_override, calculate_clv, ELO_RATINGS,
)

def test_probabilities_sum_to_one():
    m = build_score_matrix(1.5, 1.0)
    p = extract_probabilities(m)
    assert abs(p['hw'] + p['draw'] + p['aw'] - 1.0) < 0.001

def test_dc_correction_low_scores():
    assert dc_correction(0, 0, 1.5, 1.0) != 1.0
    assert dc_correction(2, 2, 1.5, 1.0) == 1.0

def test_elo_arsenal_vs_spurs():
    p = elo_hw_probability(ELO_RATINGS['Arsenal'], ELO_RATINGS['Tottenham'])
    assert 0.8 < p < 0.99

def test_fatigue_multipliers():
    assert fatigue_multiplier(3) == pytest.approx(0.94)
    assert fatigue_multiplier(7) == pytest.approx(1.00)
    assert fatigue_multiplier(10) == pytest.approx(1.00)

def test_kelly_stake_cap():
    stake = kelly_stake(0.72, 2.10, 1000.0)
    assert stake <= 8.00
    assert stake >= 1.00
    assert stake % 0.5 == 0.0

def test_kelly_stake_below_odds_floor():
    stake = kelly_stake(0.80, 1.30, 1000.0)
    assert stake == 0.0

def test_classify_signal_elev():
    assert classify_signal(16.0, 0.67, 'o25') == 'ELEV'

def test_classify_signal_under25_higher_threshold():
    # u25 requires EV >= 25%, not 15%
    assert classify_signal(20.0, 0.70, 'u25') == 'BET'
    assert classify_signal(26.0, 0.70, 'u25') == 'ELEV'

def test_h2h_gate():
    assert apply_h2h_gate(5, 6)['gate'] == 'BLOCK_UNDER'
    assert apply_h2h_gate(4, 6)['gate'] == 'WARN_UNDER'
    assert apply_h2h_gate(3, 6)['gate'] == 'CLEAR'

def test_probability_gate_hard_block():
    result = check_probability_gate(0.77, 'o25')
    assert result is not None and 'HARD-BLOCK' in result

def test_probability_gate_clear():
    result = check_probability_gate(0.60, 'o25')
    assert result is None

def test_pinnacle_lower_is_confirm():
    r = check_pinnacle(1.85, 1.90)
    assert r['result'] == 'STRONG_CONFIRM'
    assert r['pass'] is True

def test_pinnacle_higher_is_flag():
    r = check_pinnacle(2.05, 1.90)
    assert r['result'] == 'FLAG'
    assert r['pass'] is False

def test_clv_positive():
    r = calculate_clv(2.00, 1.90)
    assert r['clv'] == pytest.approx(0.95)
    assert r['signal'] == 'POSITIVE'
```

- [ ] **Step 6: Run tests**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
source .venv/bin/activate
pytest tests/test_model.py -v
```

Expected output: all 14 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add model/poisson_edge_model.py requirements.txt .env.example tests/test_model.py
git commit -m "feat: add locked model + test suite"
```

---

## Task 2: Data loader (CSV cache + opponent-adjusted ratings)

**Files:**
- Create: `api/data_loader.py`
- Create: `tests/test_data_loader.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_data_loader.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_data_loader.py -v
```

Expected: ImportError or ModuleNotFoundError — `api/data_loader.py` doesn't exist yet.

- [ ] **Step 3: Implement data_loader.py**

Create `api/data_loader.py`:
```python
"""
Data loading, CSV caching, and opponent-adjusted ratings.
All logic here; api/main.py calls DataStore only.
"""
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Tuple

import httpx
import pandas as pd

from model.poisson_edge_model import compute_opponent_adjusted_ratings, ELO_RATINGS

CACHE_DIR = Path(__file__).parent.parent / 'data' / 'cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Seasons to load: current first (stale after 24h), historical fetched once
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
    Current season: 24h TTL (results update during the day).
    Historical: fetch once (never stale after first download).
    """
    frames = []

    current = load_season_csv(CURRENT_SEASON, ttl_hours=24)
    frames.append(current)

    for code in HISTORICAL_SEASONS:
        try:
            df = load_season_csv(code, ttl_hours=24 * 365 * 10)
            frames.append(df)
        except Exception:
            pass  # missing season is non-fatal

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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_data_loader.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add api/data_loader.py tests/test_data_loader.py
git commit -m "feat: data loader with CSV cache and opponent-adjusted ratings"
```

---

## Task 3: Signal engine

**Files:**
- Create: `api/signal_engine.py`
- Create: `tests/test_signal_engine.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_signal_engine.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
import pandas as pd
from api.signal_engine import compute_signal, SignalResult, GWSignals

MINIMAL_DF = pd.DataFrame({
    'HomeTeam': ['Arsenal', 'Chelsea'] * 20,
    'AwayTeam': ['Chelsea', 'Arsenal'] * 20,
    'FTHG': [2, 1] * 20,
    'FTAG': [1, 2] * 20,
})
MINIMAL_ATK = {'Arsenal': 1.1, 'Chelsea': 0.9}
MINIMAL_DEF = {'Arsenal': 0.9, 'Chelsea': 1.1}

def test_compute_signal_returns_signal_result():
    result = compute_signal(
        home='Arsenal', away='Chelsea',
        market='o25', odds=1.90,
        historical=MINIMAL_DF, g_atk=MINIMAL_ATK, g_def=MINIMAL_DEF,
    )
    assert isinstance(result, SignalResult)
    assert result.market == 'o25'
    assert result.tier in ('ELEV', 'BET', 'SIM', 'NO')
    assert isinstance(result.ev_pct, float)
    assert isinstance(result.model_p, float)

def test_compute_signal_kelly_zero_for_no_tier():
    # Force a NO signal by using terrible odds with high model probability
    result = compute_signal(
        home='Arsenal', away='Chelsea',
        market='o25', odds=1.05,
        historical=MINIMAL_DF, g_atk=MINIMAL_ATK, g_def=MINIMAL_DEF,
        bankroll=1000.0,
    )
    assert result.tier == 'NO'
    assert result.kelly_stake == 0.0

def test_gw_signals_structure():
    fixtures = [
        {'home': 'Arsenal', 'away': 'Chelsea',
         'markets': {'o25': 1.90, 'btts': 1.80}},
    ]
    gw = GWSignals(
        fixtures=fixtures,
        historical=MINIMAL_DF,
        g_atk=MINIMAL_ATK,
        g_def=MINIMAL_DEF,
        bankroll=1000.0,
    )
    results = gw.compute()
    assert isinstance(results, list)
    assert all(isinstance(r, SignalResult) for r in results)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_signal_engine.py -v
```

Expected: ImportError — `api/signal_engine.py` doesn't exist.

- [ ] **Step 3: Implement signal_engine.py**

Create `api/signal_engine.py`:
```python
"""
Signal engine: orchestrates model functions → produces SignalResult objects.
No scraping, no HTTP, no data loading here.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from model.poisson_edge_model import (
    calculate_lambdas, build_score_matrix, extract_probabilities,
    apply_elo_ensemble, calculate_ev, classify_signal, kelly_stake,
    check_probability_gate, ELO_RATINGS,
)

MARKET_KEYS = ('o25', 'u25', 'btts', 'hw', 'aw', 'o35')


@dataclass
class SignalResult:
    home: str
    away: str
    market: str
    odds: float
    model_p: float
    ev_pct: float
    tier: str
    kelly_stake: float
    lambda_home: float
    lambda_away: float
    gate_block: Optional[str] = None


@dataclass
class GWSignals:
    fixtures: List[Dict]
    historical: pd.DataFrame
    g_atk: Dict
    g_def: Dict
    bankroll: float = 1000.0
    elo_ratings: Dict = field(default_factory=lambda: dict(ELO_RATINGS))

    def compute(self) -> List[SignalResult]:
        results = []
        for fix in self.fixtures:
            for market, odds in fix.get('markets', {}).items():
                r = compute_signal(
                    home=fix['home'], away=fix['away'],
                    market=market, odds=odds,
                    historical=self.historical,
                    g_atk=self.g_atk, g_def=self.g_def,
                    bankroll=self.bankroll,
                    elo_ratings=self.elo_ratings,
                    home_rest_days=fix.get('home_rest_days', 7),
                    away_rest_days=fix.get('away_rest_days', 7),
                    home_atk_mult=fix.get('home_atk_mult', 1.0),
                    away_atk_mult=fix.get('away_atk_mult', 1.0),
                    home_def_boost=fix.get('home_def_boost', 1.0),
                    away_def_boost=fix.get('away_def_boost', 1.0),
                )
                results.append(r)
        results.sort(key=lambda r: r.ev_pct, reverse=True)
        return results


def compute_signal(
    home: str, away: str, market: str, odds: float,
    historical: pd.DataFrame, g_atk: Dict, g_def: Dict,
    bankroll: float = 1000.0,
    elo_ratings: Dict = None,
    home_rest_days: int = 7, away_rest_days: int = 7,
    home_atk_mult: float = 1.0, away_atk_mult: float = 1.0,
    home_def_boost: float = 1.0, away_def_boost: float = 1.0,
) -> SignalResult:
    lh, la = calculate_lambdas(
        home, away, historical, g_atk, g_def,
        home_rest_days, away_rest_days,
        home_atk_mult, away_atk_mult,
        home_def_boost, away_def_boost,
    )
    matrix = build_score_matrix(lh, la)
    probs = extract_probabilities(matrix)

    if market == 'hw':
        model_p = apply_elo_ensemble(probs['hw'], home, away, elo_ratings)
    else:
        model_p = probs.get(market, 0.0)

    ev = calculate_ev(model_p, odds)
    tier = classify_signal(ev, model_p, market)
    gate_block = check_probability_gate(model_p, market)

    if gate_block and 'HARD-BLOCK' in gate_block:
        tier = 'NO'

    stake = kelly_stake(model_p, odds, bankroll) if tier != 'NO' else 0.0

    return SignalResult(
        home=home, away=away, market=market, odds=odds,
        model_p=round(model_p, 4), ev_pct=round(ev, 2),
        tier=tier, kelly_stake=stake,
        lambda_home=round(lh, 4), lambda_away=round(la, 4),
        gate_block=gate_block,
    )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_signal_engine.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add api/signal_engine.py tests/test_signal_engine.py
git commit -m "feat: signal engine orchestrating model → SignalResult"
```

---

## Task 4: Scrapers

**Files:**
- Create: `api/scrapers/__init__.py`
- Create: `api/scrapers/table.py`
- Create: `api/scrapers/injuries.py`
- Create: `api/scrapers/odds.py`
- Create: `api/scrapers/polymarket.py`
- Create: `tests/test_scrapers.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_scrapers.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock
from api.scrapers.table import fetch_table
from api.scrapers.injuries import fetch_injuries
from api.scrapers.odds import fetch_pinnacle_odds
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
        table = fetch_table()
    assert isinstance(table, list)
    assert len(table) >= 1
    assert 'team' in table[0]
    assert 'position' in table[0]

def test_fetch_table_top8_extracted():
    with patch('httpx.get') as mock:
        mock.return_value = MagicMock(status_code=200, text=BBC_TABLE_HTML)
        table = fetch_table()
    top8 = [t['team'] for t in table[:8]]
    assert 'Arsenal' in top8

def test_fetch_pinnacle_odds_structure():
    mock_response = {
        'data': [{
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
    }
    with patch('httpx.get') as mock:
        mock.return_value = MagicMock(status_code=200)
        mock.return_value.json.return_value = mock_response
        odds = fetch_pinnacle_odds('Arsenal', 'Chelsea', api_key='test')
    assert isinstance(odds, dict)

def test_fetch_injuries_returns_list():
    html = '<html><body><table><tr><td>Bukayo Saka</td><td>Doubtful</td></tr></table></body></html>'
    with patch('httpx.get') as mock:
        mock.return_value = MagicMock(status_code=200, text=html)
        injuries = fetch_injuries('Arsenal')
    assert isinstance(injuries, list)
```

- [ ] **Step 2: Run test to verify failure**

```bash
pytest tests/test_scrapers.py -v
```

Expected: ImportError.

- [ ] **Step 3: Create scraper package**

```bash
touch /Users/avi/Downloads/Claude/Code/POISSON-EDGE/api/scrapers/__init__.py
```

- [ ] **Step 4: Implement table.py**

Create `api/scrapers/table.py`:
```python
"""BBC Sport Premier League table scraper."""
from typing import List, Dict
import httpx
from bs4 import BeautifulSoup

TABLE_URL = 'https://www.bbc.com/sport/football/premier-league/table'


def fetch_table() -> List[Dict]:
    """
    Returns list of {position, team, points} dicts ordered 1→20.
    Falls back to empty list on any error — caller must handle.
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
```

- [ ] **Step 5: Implement injuries.py**

Create `api/scrapers/injuries.py`:
```python
"""
Injury scraper: premierinjuries.com (primary) + BBC Sport (secondary).
Returns list of {player, status, role, source} dicts.
"""
from typing import List, Dict
import httpx
from bs4 import BeautifulSoup

PREMIER_INJURIES_URL = 'https://www.premierinjuries.com/injury-table.php'


def fetch_injuries(team: str) -> List[Dict]:
    """
    Fetch injury list for a team. Returns [] on failure.
    Two-source minimum: premierinjuries.com + BBC Sport.
    Caller flags if either source returns empty (the model's transparency block
    generates the ⚠️ NO INJURIES FOUND warning).
    """
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
```

- [ ] **Step 6: Implement odds.py**

Create `api/scrapers/odds.py`:
```python
"""OddsAPI wrapper for Pinnacle odds (500 req/month free tier)."""
from typing import Dict, Optional
import httpx

ODDS_API_BASE = 'https://api.the-odds-api.com/v4'
EPL_KEY = 'soccer_epl'


def fetch_pinnacle_odds(home: str, away: str, api_key: str) -> Dict:
    """
    Returns {o25, u25, btts, hw, aw} Pinnacle odds for the fixture.
    Returns {} if fixture not found or API error.
    """
    url = f'{ODDS_API_BASE}/sports/{EPL_KEY}/odds'
    params = {
        'apiKey': api_key,
        'bookmakers': 'pinnacle',
        'markets': 'totals,h2h,btts',
        'oddsFormat': 'decimal',
        'regions': 'eu',
    }
    try:
        r = httpx.get(url, params=params, timeout=15)
        r.raise_for_status()
        events = r.json()
    except Exception:
        return {}

    for event in events:
        eh = event.get('home_team', '')
        ea = event.get('away_team', '')
        if _fuzzy_match(eh, home) and _fuzzy_match(ea, away):
            return _parse_pinnacle_event(event)
    return {}


def _fuzzy_match(a: str, b: str) -> bool:
    return a.lower().replace(' ', '') in b.lower().replace(' ', '') or \
           b.lower().replace(' ', '') in a.lower().replace(' ', '')


def _parse_pinnacle_event(event: Dict) -> Dict:
    result = {}
    for bm in event.get('bookmakers', []):
        if bm.get('key') != 'pinnacle':
            continue
        for market in bm.get('markets', []):
            key = market.get('key')
            outcomes = {o['name']: o['price'] for o in market.get('outcomes', [])}
            if key == 'totals':
                result['o25'] = outcomes.get('Over')
                result['u25'] = outcomes.get('Under')
            elif key == 'h2h':
                result['hw'] = outcomes.get(event.get('home_team'))
                result['aw'] = outcomes.get(event.get('away_team'))
            elif key == 'btts':
                result['btts'] = outcomes.get('Yes')
    return result
```

- [ ] **Step 7: Implement polymarket.py**

Create `api/scrapers/polymarket.py`:
```python
"""
Polymarket EPL match page scraper.
URL pattern: polymarket.com/sports/epl/epl-{home}-{away}-{YYYY-MM-DD}
Returns implied probability (0–1) for home win, or None on failure.
"""
from typing import Optional
import re
import httpx
from bs4 import BeautifulSoup


def fetch_polymarket_prob(home: str, away: str, match_date: str) -> Optional[float]:
    """
    match_date: 'YYYY-MM-DD'
    Returns float 0–1 or None if page not found / parse fails.
    """
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
    """Extract the home win probability percentage from the page."""
    soup = BeautifulSoup(html, 'lxml')
    # Look for percentage text near home team name
    text = soup.get_text()
    # Find patterns like "Arsenal 72%" or "72%"
    matches = re.findall(r'(\d{1,3})%', text)
    if matches:
        try:
            return float(matches[0]) / 100
        except ValueError:
            return None
    return None
```

- [ ] **Step 8: Run scraper tests**

```bash
pytest tests/test_scrapers.py -v
```

Expected: all 4 tests PASS (all use mocked HTTP).

- [ ] **Step 9: Commit**

```bash
git add api/scrapers/ tests/test_scrapers.py
git commit -m "feat: scrapers for table, injuries, Pinnacle odds, Polymarket"
```

---

## Task 5: FastAPI app

**Files:**
- Create: `api/main.py`

- [ ] **Step 1: Implement main.py**

Create `api/main.py`:
```python
"""
FastAPI app — thin routing layer only.
All logic lives in data_loader, signal_engine, and scrapers.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from api.data_loader import DataStore
from api.signal_engine import GWSignals, SignalResult
from api.scrapers.table import fetch_table
from api.scrapers.injuries import fetch_injuries
from api.scrapers.odds import fetch_pinnacle_odds
from api.scrapers.polymarket import fetch_polymarket_prob

load_dotenv()

store = DataStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Download CSVs and compute ratings at startup."""
    store.load()
    yield


app = FastAPI(title='POISSON-EDGE', version='4.1', lifespan=lifespan)

FRONTEND_DIR = Path(__file__).parent.parent / 'frontend'
app.mount('/static', StaticFiles(directory=str(FRONTEND_DIR)), name='static')


@app.get('/')
def root():
    return FileResponse(str(FRONTEND_DIR / 'index.html'))


@app.get('/health')
def health():
    return {'status': 'ok', 'data_ready': store.ready}


@app.get('/api/signals')
def get_signals(gw: int = 35, bankroll: float = None) -> List[Dict]:
    """
    Compute signals for all fixtures in fixtures.json.
    Fixtures file: data/fixtures.json
    """
    if not store.ready:
        raise HTTPException(503, 'Model not ready — data still loading')

    fixtures_path = Path(__file__).parent.parent / 'data' / 'fixtures.json'
    if not fixtures_path.exists():
        return []

    import json
    fixtures = json.loads(fixtures_path.read_text())
    bl = bankroll or float(os.getenv('BANKROLL', '1000'))

    gw_signals = GWSignals(
        fixtures=fixtures,
        historical=store.historical,
        g_atk=store.g_atk,
        g_def=store.g_def,
        bankroll=bl,
        elo_ratings=store.elo_ratings,
    )
    results = gw_signals.compute()
    return [_serialise(r) for r in results]


@app.get('/api/table')
def get_table() -> List[Dict]:
    return fetch_table()


@app.get('/api/injuries/{team}')
def get_injuries(team: str) -> List[Dict]:
    return fetch_injuries(team)


@app.get('/api/odds/{home}/{away}')
def get_odds(home: str, away: str) -> Dict:
    api_key = os.getenv('ODDS_API_KEY', '')
    if not api_key:
        raise HTTPException(400, 'ODDS_API_KEY not set in .env')
    return fetch_pinnacle_odds(home, away, api_key)


@app.get('/api/polymarket/{home}/{away}/{date}')
def get_polymarket(home: str, away: str, date: str) -> Dict:
    prob = fetch_polymarket_prob(home, away, date)
    return {'probability': prob}


def _serialise(r: SignalResult) -> Dict[str, Any]:
    return {
        'home': r.home, 'away': r.away,
        'market': r.market, 'odds': r.odds,
        'model_p': r.model_p, 'ev_pct': r.ev_pct,
        'tier': r.tier, 'kelly_stake': r.kelly_stake,
        'lambda_home': r.lambda_home, 'lambda_away': r.lambda_away,
        'gate_block': r.gate_block,
    }
```

- [ ] **Step 2: Create a sample fixtures.json**

Create `data/fixtures.json`:
```json
[
  {
    "home": "Arsenal",
    "away": "Chelsea",
    "date": "2026-04-26",
    "markets": {
      "o25": 1.90,
      "btts": 1.80,
      "hw": 2.10
    },
    "home_rest_days": 7,
    "away_rest_days": 4
  }
]
```

- [ ] **Step 3: Smoke-test the API**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
source .venv/bin/activate
uvicorn api.main:app --reload &
sleep 5
curl http://localhost:8000/health
```

Expected: `{"status":"ok","data_ready":true}`

```bash
curl http://localhost:8000/api/signals | python -m json.tool | head -40
```

Expected: JSON array of signal objects with `tier`, `ev_pct`, `kelly_stake`.

```bash
kill %1  # stop uvicorn
```

- [ ] **Step 4: Commit**

```bash
git add api/main.py data/fixtures.json
git commit -m "feat: FastAPI app with signals, table, injuries, odds endpoints"
```

---

## Task 6: CSS design system

**Files:**
- Create: `frontend/css/globals.css`

- [ ] **Step 1: Create globals.css from design spec**

Create `frontend/css/globals.css`:
```css
/* POISSON-EDGE design tokens — from 2026-04-26 spec */
:root {
  --bg:        #0D0F13;
  --surface:   #13151A;
  --surface-2: #1A1D24;
  --border:    rgba(255,255,255,0.06);
  --border-s:  rgba(255,255,255,0.11);
  --text-1:    #C9A84C;
  --text-2:    #6B7280;
  --text-3:    #374151;
  --gold:      #C9A84C;
  --gold-dim:  rgba(201,168,76,0.10);
  --green:     #22C55E;
  --red:       #EF4444;
}

html[data-theme="light"] {
  --bg:        #F7F5F0;
  --surface:   #FFFFFF;
  --surface-2: #F0EDE7;
  --border:    #E4E0D8;
  --border-s:  #C8C4BC;
  --text-1:    #1E40AF;
  --text-2:    #6B6560;
  --text-3:    #A8A29E;
  --green:     #1D4A35;
  --red:       #991B1B;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body {
  background: var(--bg);
  color: var(--text-1);
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  min-width: 960px;
  overflow-x: auto;
}

html[data-theme="light"] body {
  font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
}

/* Shell */
.layout { display: flex; height: 100vh; }

/* Sidebar */
.sidebar {
  width: 56px; background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column;
  align-items: center; padding: 18px 0; gap: 4px; flex-shrink: 0;
}
.logo {
  width: 30px; height: 30px; background: var(--gold);
  border-radius: 7px; display: flex; align-items: center;
  justify-content: center; font-size: 11px; font-weight: 800;
  color: #000; letter-spacing: -0.5px; margin-bottom: 20px;
}
html[data-theme="light"] .logo { background: #1A1814; color: #F7F5F0; }
.ni {
  width: 38px; height: 38px; border-radius: 9px;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-3); font-size: 15px; cursor: pointer;
  transition: color 0.15s, background 0.15s;
}
.ni:hover { color: var(--text-2); background: var(--surface-2); }
.ni.on { color: var(--gold); background: var(--gold-dim); }
html[data-theme="light"] .ni.on { color: #1D4A35; background: rgba(29,74,53,0.10); }

/* Main column */
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* Topbar */
.topbar {
  height: 50px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; padding: 0 40px;
  gap: 10px; flex-shrink: 0;
}
.tb-name { font-size: 12px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; }
.tb-dot  { color: var(--text-3); font-size: 10px; }
.tb-meta { font-size: 12px; color: var(--text-2); }
.topbar-right { margin-left: auto; display: flex; align-items: center; gap: 12px; }
.live { display: flex; align-items: center; gap: 6px; font-size: 10px; font-weight: 600; color: var(--green); letter-spacing: 0.08em; text-transform: uppercase; }
html[data-theme="light"] .live { color: #1D4A35; }
.live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--green); animation: blink 2s ease-in-out infinite; }
html[data-theme="light"] .live-dot { background: #1D4A35; }

/* Theme toggle */
.theme-toggle {
  width: 30px; height: 30px; border-radius: 7px;
  border: 1px solid var(--border-s); background: transparent;
  color: var(--text-2); font-size: 14px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.15s, color 0.15s;
}
.theme-toggle:hover { background: var(--surface-2); color: var(--text-1); }

/* Content */
.content { flex: 1; overflow-y: auto; padding: 52px 56px 40px; }

/* Hero */
.eyebrow { font-size: 11px; font-weight: 500; color: var(--text-3); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 14px; }
.hero-line { font-size: 52px; font-weight: 700; letter-spacing: -0.035em; line-height: 1; margin-bottom: 10px; }
html[data-theme="light"] .hero-line { font-family: 'Cormorant Garamond', Georgia, serif; font-style: italic; font-weight: 600; font-size: 58px; letter-spacing: -0.01em; }
.hero-line .g { color: var(--gold); }
.hero-line .pos { color: var(--green); }
.hero-sub { font-size: 14px; color: var(--text-2); margin-bottom: 52px; }

/* Section divider */
.sdiv { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
.sdiv-label { font-size: 10px; font-weight: 600; color: var(--text-3); letter-spacing: 0.12em; text-transform: uppercase; white-space: nowrap; }
.sdiv-line { flex: 1; height: 1px; background: var(--border); }

/* Cards */
.card {
  background: var(--surface); border: 1px solid var(--border-s);
  border-radius: 14px; padding: 28px 30px; position: relative;
  overflow: hidden; cursor: pointer;
  transition: border-color 0.2s, transform 0.2s, box-shadow 0.2s;
}
.card::before {
  content: ''; position: absolute; top: -30px; right: -30px;
  width: 140px; height: 140px;
  background: radial-gradient(circle, rgba(201,168,76,0.07) 0%, transparent 70%);
  pointer-events: none;
}
.card:hover { border-color: rgba(201,168,76,0.25); transform: translateY(-3px); box-shadow: 0 16px 40px rgba(0,0,0,0.35); }

/* Tier badges */
.tbadge { display: inline-block; font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; padding: 3px 8px; border-radius: 4px; }
.tb-elev { color: var(--gold); background: var(--gold-dim); }
.tb-bet  { color: var(--green); background: rgba(34,197,94,0.09); }
.tb-sim  { color: var(--text-2); background: var(--surface-2); }
.tb-no   { color: var(--text-3); border: 1px solid var(--border-s); }

/* Status bar */
.statusbar { height: 52px; border-top: 1px solid var(--border); display: flex; align-items: center; padding: 0 56px; gap: 32px; flex-shrink: 0; }
.sb-label { font-size: 10px; font-weight: 500; color: var(--text-3); letter-spacing: 0.09em; text-transform: uppercase; margin-bottom: 1px; }
.sb-val   { font-size: 14px; font-weight: 600; }
.sb-right { margin-left: auto; display: flex; gap: 32px; }

/* Table */
.tbl { width: 100%; border-collapse: collapse; }
.tbl th { font-size: 10px; font-weight: 600; color: var(--text-3); letter-spacing: 0.1em; text-transform: uppercase; text-align: left; padding: 0 0 14px; border-bottom: 1px solid var(--border); }
.tbl td { padding: 15px 0; border-bottom: 1px solid var(--border); vertical-align: middle; }
.tbl tr:last-child td { border-bottom: none; }

/* KPI strip */
.kpi-strip { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 48px; }
.kpi { background: var(--surface); border: 1px solid var(--border-s); border-radius: 12px; padding: 22px 24px; }
.kpi-label { font-size: 10px; font-weight: 500; color: var(--text-3); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 8px; }
.kpi-val { font-size: 28px; font-weight: 700; letter-spacing: -0.025em; line-height: 1; }
.kpi-sub { font-size: 12px; color: var(--text-2); margin-top: 4px; }

/* Gate pips */
.gp { width: 6px; height: 6px; border-radius: 50%; background: var(--text-3); }
.gp.pass { background: var(--green); }
.gp.warn { background: var(--gold); }

@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.35} }
.elev-pip { width: 7px; height: 7px; border-radius: 50%; background: var(--gold); animation: blink 2.5s ease-in-out infinite; }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/css/globals.css
git commit -m "feat: CSS design system — dark/light tokens from spec"
```

---

## Task 7: JS layer (theme + API client)

**Files:**
- Create: `frontend/js/theme.js`
- Create: `frontend/js/api.js`

- [ ] **Step 1: Create theme.js**

Create `frontend/js/theme.js`:
```javascript
// Persist and apply dark/light theme
const THEME_KEY = 'pe-theme';

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY) || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  const btn = document.querySelector('.theme-toggle');
  if (btn) btn.textContent = saved === 'dark' ? '◑' : '☀';
}

function toggleTheme() {
  const isLight = document.documentElement.getAttribute('data-theme') === 'light';
  const next = isLight ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem(THEME_KEY, next);
  const btn = document.querySelector('.theme-toggle');
  if (btn) btn.textContent = next === 'dark' ? '◑' : '☀';
}

document.addEventListener('DOMContentLoaded', initTheme);
```

- [ ] **Step 2: Create api.js**

Create `frontend/js/api.js`:
```javascript
// Thin fetch wrappers for all POISSON-EDGE API endpoints
const API = {
  async signals(gw = 35) {
    const r = await fetch(`/api/signals?gw=${gw}`);
    if (!r.ok) throw new Error(`signals: ${r.status}`);
    return r.json();
  },
  async table() {
    const r = await fetch('/api/table');
    if (!r.ok) throw new Error(`table: ${r.status}`);
    return r.json();
  },
  async injuries(team) {
    const r = await fetch(`/api/injuries/${encodeURIComponent(team)}`);
    if (!r.ok) throw new Error(`injuries: ${r.status}`);
    return r.json();
  },
  async odds(home, away) {
    const r = await fetch(`/api/odds/${encodeURIComponent(home)}/${encodeURIComponent(away)}`);
    if (!r.ok) throw new Error(`odds: ${r.status}`);
    return r.json();
  },
  async polymarket(home, away, date) {
    const r = await fetch(`/api/polymarket/${encodeURIComponent(home)}/${encodeURIComponent(away)}/${date}`);
    if (!r.ok) throw new Error(`polymarket: ${r.status}`);
    return r.json();
  },
};
```

- [ ] **Step 3: Commit**

```bash
git add frontend/js/theme.js frontend/js/api.js
git commit -m "feat: theme persistence and API fetch layer"
```

---

## Task 8: Signal Board page (index.html)

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/js/signals.js`

- [ ] **Step 1: Create index.html**

Create `frontend/index.html` — copy the structure from the approved mockup in `compare2.html` but with real data slots:

```html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>POISSON-EDGE — Signal Board</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,600;1,600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/css/globals.css">
</head>
<body>
<div class="layout">

  <nav class="sidebar">
    <div class="logo">PE</div>
    <a class="ni on" href="/" title="Signals">⚡</a>
    <a class="ni" href="/static/bankroll.html" title="Bankroll">◈</a>
    <a class="ni" href="/static/backtest.html" title="Backtest">↗</a>
    <div style="flex:1"></div>
    <a class="ni" href="/static/model.html" title="Λ Model">λ</a>
  </nav>

  <div class="main">
    <div class="topbar">
      <span class="tb-name">Signal Board</span>
      <span class="tb-dot">·</span>
      <span class="tb-meta" id="gw-meta">Loading…</span>
      <div class="topbar-right">
        <div class="live"><div class="live-dot"></div> Live</div>
        <button class="theme-toggle" onclick="toggleTheme()">◑</button>
      </div>
    </div>

    <div class="content">
      <div class="eyebrow">Elevated signals</div>
      <div class="hero-line"><span class="g" id="elev-count">—</span> bets tonight</div>
      <div class="hero-sub" id="hero-sub">EV ≥ +15% · probability ≥ 65% · all gates cleared</div>

      <div class="sdiv"><span class="sdiv-label">★ Elevated</span><div class="sdiv-line"></div></div>
      <div class="cards" id="elev-cards" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px;margin-bottom:60px">
        <div style="color:var(--text-2);padding:24px">Computing signals…</div>
      </div>

      <div class="sdiv"><span class="sdiv-label" id="all-label">All Signals</span><div class="sdiv-line"></div></div>
      <table class="tbl" id="all-table">
        <thead>
          <tr>
            <th style="width:72px">Tier</th>
            <th>Match</th>
            <th style="text-align:right;width:80px">EV</th>
          </tr>
        </thead>
        <tbody id="all-tbody"></tbody>
      </table>
    </div>

    <div class="statusbar">
      <div>
        <div class="sb-label">Gameweek</div>
        <div class="sb-val" id="sb-gw">GW—</div>
      </div>
      <div class="sb-right">
        <div><div class="sb-val" id="sb-avg-p">—</div><div class="sb-label">Avg Prob</div></div>
        <div><div class="sb-val" id="sb-avg-ev">—</div><div class="sb-label">Avg EV</div></div>
        <div><div class="sb-val" id="sb-stake">—</div><div class="sb-label">Total Stake</div></div>
      </div>
    </div>
  </div>
</div>
<script src="/static/js/theme.js"></script>
<script src="/static/js/api.js"></script>
<script src="/static/js/signals.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create signals.js**

Create `frontend/js/signals.js`:
```javascript
async function loadSignals() {
  const signals = await API.signals();

  const elev = signals.filter(s => s.tier === 'ELEV');
  document.getElementById('elev-count').textContent = elev.length;
  document.getElementById('gw-meta').textContent = 'Premier League';

  // ELEV cards
  const cardsEl = document.getElementById('elev-cards');
  if (elev.length === 0) {
    cardsEl.innerHTML = '<div style="color:var(--text-2);padding:24px">No elevated signals this gameweek.</div>';
  } else {
    cardsEl.innerHTML = elev.map(s => `
      <div class="card">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:22px">
          <div style="display:flex;align-items:center;gap:7px;font-size:10px;font-weight:700;color:var(--gold);letter-spacing:0.1em;text-transform:uppercase">
            <div class="elev-pip"></div> Elevated
          </div>
          <div style="font-size:11px;color:var(--text-3);text-align:right">${marketLabel(s.market)} @ ${s.odds}</div>
        </div>
        <div style="font-size:24px;font-weight:700;letter-spacing:-0.02em;margin-bottom:7px">${s.home} vs ${s.away}</div>
        <div style="font-size:14px;color:var(--text-2);margin-bottom:24px">${marketLabel(s.market)} <strong style="color:var(--text-1)">@ ${s.odds}</strong></div>
        <div style="display:flex;align-items:flex-end;justify-content:space-between">
          <div>
            <div style="font-size:10px;font-weight:500;color:var(--text-3);letter-spacing:0.09em;text-transform:uppercase;margin-bottom:3px">Expected Value</div>
            <div style="font-size:38px;font-weight:700;color:var(--gold);letter-spacing:-0.025em;line-height:1">${s.ev_pct > 0 ? '+' : ''}${s.ev_pct.toFixed(1)}%</div>
          </div>
          <div style="text-align:right">
            <div style="font-size:10px;font-weight:500;color:var(--text-3);letter-spacing:0.09em;text-transform:uppercase;margin-bottom:3px">Kelly 25%</div>
            <div style="font-size:22px;font-weight:600;letter-spacing:-0.01em">€${s.kelly_stake.toFixed(2)}</div>
          </div>
        </div>
        <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border);display:flex;align-items:center;gap:5px">
          <span style="font-size:9px;font-weight:500;color:var(--text-3);letter-spacing:0.09em;text-transform:uppercase;margin-right:4px">Gates</span>
          <div class="gp pass"></div><div class="gp pass"></div><div class="gp pass"></div>
          <div class="gp pass"></div><div class="gp pass"></div><div class="gp pass"></div>
          <div class="gp ${s.gate_block ? 'warn' : 'pass'}"></div>
        </div>
      </div>
    `).join('');
  }

  // All signals table
  const tbody = document.getElementById('all-tbody');
  tbody.innerHTML = signals.map(s => `
    <tr>
      <td><span class="tbadge tb-${s.tier.toLowerCase()}">${s.tier}</span></td>
      <td>
        <div style="font-size:15px;font-weight:500">${s.home} vs ${s.away}</div>
        <div style="font-size:11px;color:var(--text-2);margin-top:2px">${marketLabel(s.market)} · @ ${s.odds}</div>
      </td>
      <td style="text-align:right;font-size:15px;font-weight:600;color:${s.ev_pct >= 15 ? 'var(--gold)' : s.ev_pct >= 0 ? 'var(--green)' : 'var(--text-3)'}">
        ${s.ev_pct > 0 ? '+' : ''}${s.ev_pct.toFixed(1)}%
      </td>
    </tr>
  `).join('');

  document.getElementById('all-label').textContent = `All Signals · ${signals.length} markets`;

  // Status bar
  const elevAvgP = elev.length ? (elev.reduce((a,s) => a + s.model_p, 0) / elev.length * 100).toFixed(1) + '%' : '—';
  const elevAvgEV = elev.length ? '+' + (elev.reduce((a,s) => a + s.ev_pct, 0) / elev.length).toFixed(1) + '%' : '—';
  const totalStake = elev.reduce((a,s) => a + s.kelly_stake, 0);
  document.getElementById('sb-avg-p').textContent = elevAvgP;
  document.getElementById('sb-avg-ev').textContent = elevAvgEV;
  document.getElementById('sb-stake').textContent = `€${totalStake.toFixed(2)}`;
}

function marketLabel(m) {
  const labels = { o25: 'Over 2.5 Goals', u25: 'Under 2.5 Goals', btts: 'Both Teams to Score', hw: 'Home Win', aw: 'Away Win', o35: 'Over 3.5 Goals' };
  return labels[m] || m;
}

document.addEventListener('DOMContentLoaded', () => {
  loadSignals().catch(err => {
    document.getElementById('elev-cards').innerHTML = `<div style="color:var(--red);padding:24px">Error: ${err.message}</div>`;
  });
});
```

- [ ] **Step 3: Smoke test Signal Board**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
source .venv/bin/activate
uvicorn api.main:app --reload &
sleep 8
open http://localhost:8000
```

Expected: Signal Board loads, shows computed signals for Arsenal vs Chelsea from fixtures.json.

```bash
kill %1
```

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html frontend/js/signals.js
git commit -m "feat: Signal Board page with live computed signals"
```

---

## Task 9: Remaining pages (Bankroll, Backtest, Λ Model)

**Files:**
- Create: `frontend/bankroll.html` + `frontend/js/bankroll.js`
- Create: `frontend/backtest.html` + `frontend/js/backtest.js`
- Create: `frontend/model.html` + `frontend/js/model_page.js`
- Create: `data/bankroll.json`

- [ ] **Step 1: Create bankroll.json ledger schema**

Create `data/bankroll.json`:
```json
{
  "starting_bankroll": 1000.00,
  "current_bankroll": 1000.00,
  "bets": []
}
```

Each bet entry (added manually or via future endpoint):
```json
{
  "date": "2026-04-26",
  "gw": 35,
  "home": "Arsenal",
  "away": "Chelsea",
  "market": "o25",
  "tier": "ELEV",
  "odds": 1.90,
  "stake": 4.50,
  "result": "WIN",
  "pnl": 4.05
}
```

- [ ] **Step 2: Add bankroll API endpoints to main.py**

Add to `api/main.py` (after existing routes):
```python
import json as _json

BANKROLL_PATH = Path(__file__).parent.parent / 'data' / 'bankroll.json'

@app.get('/api/bankroll')
def get_bankroll() -> Dict:
    if not BANKROLL_PATH.exists():
        return {'starting_bankroll': 1000.0, 'current_bankroll': 1000.0, 'bets': []}
    return _json.loads(BANKROLL_PATH.read_text())
```

- [ ] **Step 3: Create bankroll.html + bankroll.js**

Use the same shell as index.html (sidebar, topbar, statusbar). The content area renders:
- Hero: current balance from `/api/bankroll`
- KPI strip: ROI, bets placed, win rate, avg stake — all computed from `bets[]`
- Static SVG equity curve placeholder (live chart in v2)
- Recent bets table from `bets[]` array

Create `frontend/bankroll.html` following the same HTML pattern as index.html, with `.ni.on` on the bankroll icon.

Create `frontend/js/bankroll.js`:
```javascript
async function loadBankroll() {
  const data = await API.bankroll ? API.bankroll() : fetch('/api/bankroll').then(r => r.json());
  const { starting_bankroll, current_bankroll, bets } = data;

  document.getElementById('hero-balance').textContent =
    `€${current_bankroll.toFixed(2)}`;

  const roi = ((current_bankroll - starting_bankroll) / starting_bankroll * 100).toFixed(1);
  document.getElementById('kpi-roi').textContent = `${roi > 0 ? '+' : ''}${roi}%`;
  document.getElementById('kpi-bets').textContent = bets.length;

  const wins = bets.filter(b => b.result === 'WIN').length;
  const winRate = bets.length ? (wins / bets.length * 100).toFixed(0) + '%' : '—';
  document.getElementById('kpi-winrate').textContent = winRate;

  const avgStake = bets.length ? (bets.reduce((a,b) => a + b.stake, 0) / bets.length).toFixed(2) : '—';
  document.getElementById('kpi-avgstake').textContent = `€${avgStake}`;

  // Recent bets table
  const tbody = document.getElementById('bets-tbody');
  tbody.innerHTML = bets.slice(-10).reverse().map(b => `
    <tr>
      <td><span class="tbadge tb-${b.tier.toLowerCase()}">${b.tier}</span></td>
      <td>
        <div style="font-size:14px;font-weight:500">${b.home} vs ${b.away}</div>
        <div style="font-size:11px;color:var(--text-2)">${b.market} · @ ${b.odds}</div>
      </td>
      <td style="font-size:14px;font-weight:500">€${b.stake.toFixed(2)}</td>
      <td style="text-align:right">
        <span style="font-size:12px;font-weight:600;color:${b.result === 'WIN' ? 'var(--green)' : b.result === 'LOSS' ? 'var(--red)' : 'var(--text-2)'}">${b.result}</span>
      </td>
      <td style="text-align:right;font-size:14px;font-weight:600;color:${b.pnl >= 0 ? 'var(--green)' : 'var(--red)'}">
        ${b.pnl >= 0 ? '+' : ''}€${Math.abs(b.pnl).toFixed(2)}
      </td>
    </tr>
  `).join('');
}

document.addEventListener('DOMContentLoaded', () => {
  loadBankroll().catch(console.error);
});
```

- [ ] **Step 4: Create backtest.html + backtest.js**

Backtest page shows historical season performance. For v1, this reads directly from the historical CSV data via a `/api/backtest` endpoint that computes actual vs model EV by GW.

Add to `api/main.py`:
```python
@app.get('/api/backtest')
def get_backtest() -> Dict:
    """Return per-GW signal counts from historical data."""
    if not store.ready:
        raise HTTPException(503, 'Model not ready')
    gw_col = 'Wk' if 'Wk' in store.historical.columns else None
    total = len(store.historical)
    return {
        'total_matches': total,
        'seasons': len(HISTORICAL_SEASONS) + 1,
        'note': 'Per-GW backtest requires full signal replay — available in v2',
    }
```

`backtest.js` fetches `/api/backtest` and renders the KPI strip + a placeholder GW table with a "Full backtest replay coming in v2" notice.

- [ ] **Step 5: Create model.html + model_page.js**

Model page is mostly static — the parameters are locked. Add a `/api/model` endpoint that returns the current ELO ratings and locked parameters:

Add to `api/main.py`:
```python
from model.poisson_edge_model import RHO, HOME_ADV, BLEND, NR, LHALF, ELO_ALPHA

@app.get('/api/model')
def get_model_info() -> Dict:
    return {
        'version': '4.1',
        'parameters': {
            'rho': RHO, 'home_adv': HOME_ADV,
            'blend': BLEND, 'nr': NR,
            'lhalf': LHALF, 'elo_alpha': ELO_ALPHA,
        },
        'elo_ratings': store.elo_ratings,
        'data_ready': store.ready,
        'total_matches': len(store.historical) if store.ready else 0,
    }
```

`model_page.js` fetches `/api/model` and renders the parameter cards with the locked values from the spec.

- [ ] **Step 6: Commit**

```bash
git add frontend/ data/bankroll.json api/main.py
git commit -m "feat: Bankroll, Backtest, and Λ Model pages + bankroll/model API endpoints"
```

---

## Task 10: Wire up and end-to-end test

- [ ] **Step 1: Run the full test suite**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
source .venv/bin/activate
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 2: Start the server and verify all 4 pages**

```bash
uvicorn api.main:app --reload
```

Open each URL and verify it loads without console errors:
- `http://localhost:8000` — Signal Board
- `http://localhost:8000/static/bankroll.html` — Bankroll
- `http://localhost:8000/static/backtest.html` — Backtest
- `http://localhost:8000/static/model.html` — Λ Model

Verify dark/light toggle persists across page navigations (localStorage).

- [ ] **Step 3: Verify health endpoint**

```bash
curl http://localhost:8000/health | python -m json.tool
```

Expected: `{"status": "ok", "data_ready": true}`

- [ ] **Step 4: Verify signals endpoint**

```bash
curl http://localhost:8000/api/signals | python -m json.tool
```

Expected: JSON array with at least one signal object containing `tier`, `ev_pct`, `kelly_stake`, `lambda_home`, `lambda_away`.

- [ ] **Step 5: Final commit + push**

```bash
git add -A
git commit -m "feat: complete POISSON-EDGE v4.1 — all pages wired, tests passing"
git push origin main
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| Dark/light toggle | Task 7, Task 6 |
| Signal Board hero + ELEV cards | Task 8 |
| All signals table | Task 8 |
| 7-gate pip display | Task 8 (simplified — full gate data in v2) |
| Kelly staking (25%, €8 cap, €1 floor) | Task 1 (model), Task 3 (engine) |
| Bankroll page + ledger | Task 9 |
| Equity curve | Task 9 (static SVG; live chart v2) |
| Backtest page | Task 9 |
| Λ Model page + parameters | Task 9 |
| CSV data fetching + cache | Task 2 |
| Opponent-adjusted ratings | Task 2 |
| Pinnacle odds scraper | Task 4 |
| Injury scraper (2 sources) | Task 4 |
| Live table scraper | Task 4 |
| Polymarket scraper | Task 4 |
| ELO ensemble (HW only) | Task 1 (model), Task 3 (engine) |
| Dixon-Coles ρ=−0.05 | Task 1 (locked parameter) |
| Probability gate hard blocks | Task 3 (signal engine) |
| CLV calculation | Task 1 (model function available, UI in v2) |

**Deferred to v2 (per spec):**
- Full backtest signal replay by GW
- Live equity curve SVG (needs time-series data)
- Gate detail drawer on card click
- CLV display in UI
