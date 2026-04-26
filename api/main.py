"""
FastAPI app — thin routing layer only.
All logic lives in data_loader, signal_engine, and scrapers.
"""
import json as _json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from api.data_loader import DataStore, HISTORICAL_SEASONS
from api.signal_engine import GWSignals, SignalResult
from api.scrapers.table import fetch_table
from api.scrapers.injuries import fetch_injuries
from api.scrapers.odds import fetch_pinnacle_odds
from api.scrapers.polymarket import fetch_polymarket_prob
from api.scrapers.fixtures import fetch_upcoming_fixtures, force_refresh
from api.scrapers.results import auto_mark_results
import api.blob_store as blob

load_dotenv()

store = DataStore()
_live_fixtures: List[Dict] = []

DATA_DIR = Path(__file__).parent.parent / 'data'
FIXTURES_PATH = DATA_DIR / 'fixtures.json'


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Download CSVs, compute ratings, then fetch live fixtures."""
    global _live_fixtures
    store.load()
    api_key = os.getenv('ODDS_API_KEY', '')
    if api_key:
        _live_fixtures = fetch_upcoming_fixtures(api_key, store.historical)
    yield


app = FastAPI(title='POISSON-EDGE', version='4.1', lifespan=lifespan)


@app.get('/health')
def health():
    return {'status': 'ok', 'data_ready': store.ready}


@app.get('/api/debug-odds')
def debug_odds() -> Dict:
    """Temporary: show raw OddsAPI response + full fetch pipeline for diagnosis."""
    import httpx as _httpx
    from api.scrapers.odds import ODDS_API_BASE, EPL_KEY
    from api.scrapers.fixtures import _parse_event, _normalise, fetch_upcoming_fixtures, force_refresh
    api_key = os.getenv('ODDS_API_KEY', '')
    if not api_key:
        return {'error': 'ODDS_API_KEY not set', 'key_set': False}

    # 1) Direct OddsAPI call — raw commas required, httpx encodes them causing 422.
    # btts market not supported by this endpoint.
    url = (f'{ODDS_API_BASE}/sports/{EPL_KEY}/odds'
           f'?apiKey={api_key}&bookmakers=pinnacle&markets=h2h,totals'
           f'&oddsFormat=decimal&regions=eu')
    raw_error = None
    body = []
    try:
        r = _httpx.get(url, timeout=20)
        r.raise_for_status()
        body = r.json()
        remaining = r.headers.get('x-requests-remaining')
        status_code = r.status_code
    except Exception as exc:
        raw_error = str(exc)
        remaining = None
        status_code = None

    # 2) Run parse pipeline on first 3 raw events
    parse_results = []
    if isinstance(body, list):
        for e in body[:3]:
            parsed = _parse_event(e, None)
            parse_results.append({
                'home': e.get('home_team'), 'away': e.get('away_team'),
                'parsed': parsed,
                'bookmaker_keys': [bm.get('key') for bm in e.get('bookmakers', [])],
                'pinnacle_markets': [m.get('key') for bm in e.get('bookmakers', [])
                                     if bm.get('key') == 'pinnacle'
                                     for m in bm.get('markets', [])],
            })

    # 3) Run the full fetch_upcoming_fixtures pipeline and capture result/error
    fetch_result = None
    fetch_error = None
    try:
        from api.scrapers.fixtures import _CACHE_FILE
        _CACHE_FILE.unlink(missing_ok=True)  # clear cache so it makes a fresh call
        fetch_result = fetch_upcoming_fixtures(api_key, None)
    except Exception as exc:
        fetch_error = str(exc)

    return {
        'status_code': status_code,
        'remaining': remaining,
        'raw_error': raw_error,
        'event_count': len(body) if isinstance(body, list) else 0,
        'parse_sample': parse_results,
        'fetch_result_count': len(fetch_result) if fetch_result is not None else None,
        'fetch_error': fetch_error,
        'key_prefix': api_key[:8] + '…',
    }


@app.get('/api/refresh-fixtures')
def refresh_fixtures() -> Dict:
    """Force re-fetch of fixtures from OddsAPI (used by Vercel cron and manual refresh)."""
    global _live_fixtures
    api_key = os.getenv('ODDS_API_KEY', '')
    if not api_key:
        raise HTTPException(400, 'ODDS_API_KEY not configured')
    _live_fixtures = force_refresh(api_key, store.historical)
    return {'fixtures_loaded': len(_live_fixtures), 'source': 'oddsapi'}


@app.get('/api/signals')
def get_signals(bankroll: float = None) -> List[Dict]:
    if not store.ready:
        raise HTTPException(503, 'Model not ready — data still loading')

    # Prefer live fixtures fetched from OddsAPI; fall back to committed fixtures.json
    if _live_fixtures:
        fixtures = _live_fixtures
    elif FIXTURES_PATH.exists():
        try:
            fixtures = _json.loads(FIXTURES_PATH.read_text(encoding='utf-8'))
        except (_json.JSONDecodeError, OSError) as exc:
            raise HTTPException(422, f'fixtures.json unreadable: {exc}') from exc
    else:
        return []

    # Use live current bankroll from Blob (falls back to env var, then 1000)
    if bankroll:
        bl = bankroll
    else:
        br = blob.load_bankroll()
        bl = br.get('current_bankroll') or float(os.getenv('BANKROLL', '1000'))

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


# ── Bet logging ────────────────────────────────────────────────────────────

class BetIn(BaseModel):
    home: str
    away: str
    market: str
    date: str
    tier: str
    model_ev: float
    model_p: float
    model_odds: float
    actual_odds: float
    stake: float


@app.post('/api/bets')
def log_bet(bet: BetIn) -> Dict:
    """Log a placed bet. Pre-filled from signal card; user supplies actual_odds + stake."""
    bets = blob.load_bets()
    entry = {
        'id': str(uuid.uuid4()),
        'home': bet.home,
        'away': bet.away,
        'market': bet.market,
        'date': bet.date,
        'tier': bet.tier,
        'model_ev': bet.model_ev,
        'model_p': bet.model_p,
        'model_odds': bet.model_odds,
        'actual_odds': bet.actual_odds,
        'stake': bet.stake,
        'status': 'pending',
        'result_score': None,
        'clv': None,
        'logged_at': datetime.now(timezone.utc).isoformat(),
    }
    bets.append(entry)
    blob.save_bets(bets)
    # Keep bankroll in sync (staked amount tracked separately — bankroll unchanged until result)
    return {'ok': True, 'id': entry['id']}


@app.get('/api/bets')
def get_bets() -> List[Dict]:
    return blob.load_bets()


@app.patch('/api/bets/{bet_id}')
def update_bet(bet_id: str, status: str, result_score: Optional[str] = None) -> Dict:
    """Manual result override. status: won | lost | void"""
    if status not in ('won', 'lost', 'void'):
        raise HTTPException(400, 'status must be won | lost | void')
    bets = blob.load_bets()
    for bet in bets:
        if bet['id'] == bet_id:
            bet['status'] = status
            if result_score:
                bet['result_score'] = result_score
            break
    else:
        raise HTTPException(404, f'Bet {bet_id} not found')
    blob.save_bets(bets)
    br = blob.load_bankroll()
    blob.save_bankroll(br['starting_bankroll'],
                       blob.recompute_bankroll(bets, br['starting_bankroll']))
    return {'ok': True}


@app.api_route('/api/refresh-results', methods=['GET', 'POST'])
def refresh_results() -> Dict:
    """Auto-mark pending bets from current season CSV. Called by Vercel cron."""
    if not store.ready:
        raise HTTPException(503, 'Model not ready')
    bets = blob.load_bets()
    bets, updated = auto_mark_results(bets, store.historical)
    if updated:
        blob.save_bets(bets)
        br = blob.load_bankroll()
        blob.save_bankroll(br['starting_bankroll'],
                           blob.recompute_bankroll(bets, br['starting_bankroll']))
    return {'updated': updated, 'total_bets': len(bets)}


# ── Bankroll & backtest ────────────────────────────────────────────────────

@app.get('/api/bankroll')
def get_bankroll() -> Dict:
    """Returns bankroll summary + full bet log for the UI."""
    br = blob.load_bankroll()
    bets = blob.load_bets()
    starting = br['starting_bankroll']
    current = br['current_bankroll']

    bet_rows = []
    for b in bets:
        pnl = blob.bet_pnl(b)
        status = b.get('status', 'pending')
        bet_rows.append({
            'id': b.get('id'),
            'tier': b.get('tier', 'BET'),
            'home': b.get('home'),
            'away': b.get('away'),
            'market': b.get('market'),
            'odds': b.get('actual_odds') or b.get('model_odds'),
            'stake': b.get('stake'),
            'status': status,
            'result': 'WIN' if status == 'won' else 'LOSS' if status == 'lost' else status.upper(),
            'result_score': b.get('result_score'),
            'pnl': pnl,
            'date': b.get('date'),
            'logged_at': b.get('logged_at'),
        })

    return {
        'starting_bankroll': starting,
        'current_bankroll': current,
        'bets': bet_rows,
    }


@app.get('/api/backtest')
def get_backtest() -> Dict:
    """Real stats from logged bets + historical data context."""
    if not store.ready:
        raise HTTPException(503, 'Model not ready')

    bets = blob.load_bets()
    settled = [b for b in bets if b.get('status') in ('won', 'lost')]

    # Stats by tier
    def tier_stats(tier_bets):
        if not tier_bets:
            return {'bets': 0, 'wins': 0, 'hit_rate': None, 'roi': None, 'total_staked': 0}
        wins = [b for b in tier_bets if b.get('status') == 'won']
        total_staked = sum(b.get('stake', 0) for b in tier_bets)
        total_pnl = sum(blob.bet_pnl(b) for b in tier_bets)
        return {
            'bets': len(tier_bets),
            'wins': len(wins),
            'hit_rate': round(len(wins) / len(tier_bets) * 100, 1) if tier_bets else None,
            'roi': round(total_pnl / total_staked * 100, 1) if total_staked else None,
            'total_staked': round(total_staked, 2),
            'total_pnl': round(total_pnl, 2),
        }

    elev_settled = [b for b in settled if b.get('tier') == 'ELEV']
    bet_settled = [b for b in settled if b.get('tier') == 'BET']

    # CLV average
    clv_entries = [b.get('clv') for b in settled if b.get('clv') is not None]
    avg_clv = round(sum(clv_entries) / len(clv_entries), 2) if clv_entries else None

    # Running bankroll curve (for chart)
    br = blob.load_bankroll()
    running = br['starting_bankroll']
    curve = [{'label': 'Start', 'balance': running}]
    for b in sorted(bets, key=lambda x: x.get('logged_at', '')):
        if b.get('status') in ('won', 'lost'):
            running = round(running + blob.bet_pnl(b), 2)
            curve.append({'label': f"{b.get('home')} vs {b.get('away')}", 'balance': running})

    return {
        'total_matches': len(store.historical),
        'seasons': len(HISTORICAL_SEASONS) + 1,
        'total_bets': len(bets),
        'settled_bets': len(settled),
        'pending_bets': len(bets) - len(settled),
        'overall': tier_stats(settled),
        'by_tier': {
            'ELEV': tier_stats(elev_settled),
            'BET': tier_stats(bet_settled),
        },
        'avg_clv': avg_clv,
        'bankroll_curve': curve,
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
