"""
FastAPI app — thin routing layer only.
All logic lives in data_loader, signal_engine, and scrapers.
"""
import json as _json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from api.data_loader import DataStore, HISTORICAL_SEASONS
from api.signal_engine import GWSignals, SignalResult
from api.scrapers.table import fetch_table
from api.scrapers.injuries import fetch_injuries
from api.scrapers.odds import fetch_pinnacle_odds
from api.scrapers.polymarket import fetch_polymarket_prob

load_dotenv()

store = DataStore()

FRONTEND_DIR = Path(__file__).parent.parent / 'frontend'
DATA_DIR = Path(__file__).parent.parent / 'data'
FIXTURES_PATH = DATA_DIR / 'fixtures.json'
BANKROLL_PATH = DATA_DIR / 'bankroll.json'


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Download CSVs and compute ratings at startup."""
    store.load()
    yield


app = FastAPI(title='POISSON-EDGE', version='4.1', lifespan=lifespan)

# Mount frontend as static files — must come AFTER app creation
# Only mount if the directory exists (it won't until Task 8)
if FRONTEND_DIR.exists():
    app.mount('/static', StaticFiles(directory=str(FRONTEND_DIR)), name='static')


@app.get('/')
def root():
    index = FRONTEND_DIR / 'index.html'
    if index.exists():
        return FileResponse(str(index))
    return {'message': 'POISSON-EDGE API', 'version': '4.1', 'docs': '/docs'}


@app.get('/health')
def health():
    return {'status': 'ok', 'data_ready': store.ready}


@app.get('/api/signals')
def get_signals(gw: int = 35, bankroll: float = None) -> List[Dict]:
    # gw parameter reserved for v2 per-gameweek filtering
    # currently computes all fixtures in fixtures.json regardless of gw
    if not store.ready:
        raise HTTPException(503, 'Model not ready — data still loading')

    if not FIXTURES_PATH.exists():
        return []

    try:
        fixtures = _json.loads(FIXTURES_PATH.read_text(encoding='utf-8'))
    except (_json.JSONDecodeError, OSError) as exc:
        raise HTTPException(422, f'fixtures.json unreadable: {exc}') from exc
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


@app.get('/api/bankroll')
def get_bankroll() -> Dict:
    if not BANKROLL_PATH.exists():
        return {'starting_bankroll': 1000.0, 'current_bankroll': 1000.0, 'bets': []}
    try:
        return _json.loads(BANKROLL_PATH.read_text(encoding='utf-8'))
    except (_json.JSONDecodeError, OSError):
        return {'starting_bankroll': 1000.0, 'current_bankroll': 1000.0, 'bets': []}


@app.get('/api/backtest')
def get_backtest() -> Dict:
    if not store.ready:
        raise HTTPException(503, 'Model not ready')
    return {
        'total_matches': len(store.historical),
        'seasons': len(HISTORICAL_SEASONS) + 1,
        'note': 'Per-GW backtest requires full signal replay — available in v2',
    }


@app.get('/api/model')
def get_model_info() -> Dict:
    # Read locked parameters from the model module
    try:
        from model.poisson_edge_model import RHO, HOME_ADV, BLEND, NR, LHALF, ELO_ALPHA
        params = {
            'rho': RHO, 'home_adv': HOME_ADV,
            'blend': BLEND, 'nr': NR,
            'lhalf': LHALF, 'elo_alpha': ELO_ALPHA,
        }
    except ImportError:
        params = {'note': 'Parameters not exported as module constants in this model version'}

    return {
        'version': '4.1',
        'parameters': params,
        'elo_ratings': store.elo_ratings,
        'data_ready': store.ready,
        'total_matches': len(store.historical) if store.ready else 0,
    }


def _serialise(r: SignalResult) -> Dict[str, Any]:
    return {
        'home': r.home, 'away': r.away,
        'market': r.market, 'odds': r.odds,
        'model_p': r.model_p, 'ev_pct': r.ev_pct,
        'tier': r.tier, 'kelly_stake': r.kelly_stake,
        'lambda_home': r.lambda_home, 'lambda_away': r.lambda_away,
        'gate_block': r.gate_block,
    }
