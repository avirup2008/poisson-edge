"""
Vercel Blob storage for mutable runtime data.

Blob paths:
  bets/log.json          [{id, home, away, market, date, tier, model_ev,
                           model_p, model_odds, actual_odds, stake,
                           status, result_score, clv, logged_at}]
  bankroll/current.json  {starting_bankroll, current_bankroll, last_updated}
  clv/log.json           [{bet_id, closing_odds, clv_pct, timestamp}]

Falls back to local data/ files when BLOB_READ_WRITE_TOKEN is not set.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

_BLOB_API = 'https://vercel.com/api/blob'
_LOCAL_DATA = Path(__file__).parent.parent / 'data'


def available() -> bool:
    return bool(os.getenv('BLOB_READ_WRITE_TOKEN', ''))


def _headers(extra: dict | None = None) -> dict:
    h = {
        'Authorization': f'Bearer {os.getenv("BLOB_READ_WRITE_TOKEN", "")}',
        'x-api-version': '12',
    }
    if extra:
        h.update(extra)
    return h


# ── Core Blob operations ───────────────────────────────────────────────────

def put(pathname: str, data: Any) -> bool:
    """Upload JSON to Vercel Blob, overwriting any existing blob at pathname."""
    if not available():
        _local_write(pathname, data)
        return True
    try:
        r = httpx.put(
            f'{_BLOB_API}/',
            params={'pathname': pathname, 'addRandomSuffix': '0',
                    'allowOverwrite': '1', 'access': 'public'},
            content=json.dumps(data, default=str).encode(),
            headers=_headers({'content-type': 'application/json'}),
            timeout=15,
        )
        return r.is_success
    except Exception:
        return False


def get(pathname: str) -> Optional[Any]:
    """Read JSON from Vercel Blob by pathname. Returns None if not found."""
    if not available():
        return _local_read(pathname)
    try:
        # List blobs with this prefix to find the URL
        r = httpx.get(
            f'{_BLOB_API}/',
            params={'prefix': pathname, 'limit': 1},
            headers=_headers(),
            timeout=15,
        )
        if not r.is_success:
            return None
        blobs = r.json().get('blobs', [])
        if not blobs:
            return None
        r2 = httpx.get(blobs[0]['url'], timeout=15)
        return r2.json() if r2.is_success else None
    except Exception:
        return None


def delete(urls: list[str]) -> None:
    """Delete blobs by URL list."""
    if not urls or not available():
        return
    try:
        httpx.post(
            f'{_BLOB_API}/delete',
            json={'urls': urls},
            headers=_headers({'content-type': 'application/json'}),
            timeout=15,
        )
    except Exception:
        pass


# ── Local fallback (dev without BLOB token) ────────────────────────────────

def _local_path(pathname: str) -> Path:
    return _LOCAL_DATA / pathname.replace('/', '_')


def _local_write(pathname: str, data: Any) -> None:
    p = _local_path(pathname)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, default=str, indent=2))


def _local_read(pathname: str) -> Optional[Any]:
    p = _local_path(pathname)
    if not p.exists():
        # Also try legacy bankroll.json
        if 'bankroll' in pathname:
            legacy = _LOCAL_DATA / 'bankroll.json'
            if legacy.exists():
                try:
                    d = json.loads(legacy.read_text())
                    return {
                        'starting_bankroll': d.get('starting_bankroll', 1000.0),
                        'current_bankroll': d.get('current_bankroll', 1000.0),
                        'last_updated': None,
                    }
                except Exception:
                    pass
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


# ── High-level domain helpers ──────────────────────────────────────────────

def load_bets() -> list:
    return get('bets/log.json') or []


def save_bets(bets: list) -> bool:
    return put('bets/log.json', bets)


def load_bankroll() -> dict:
    blob = get('bankroll/current.json')
    if blob:
        return blob
    return {'starting_bankroll': 1000.0, 'current_bankroll': 1000.0, 'last_updated': None}


def save_bankroll(starting: float, current: float) -> bool:
    return put('bankroll/current.json', {
        'starting_bankroll': round(starting, 2),
        'current_bankroll': round(current, 2),
        'last_updated': datetime.now(timezone.utc).isoformat(),
    })


def recompute_bankroll(bets: list, starting: float) -> float:
    """Sum P&L from all settled bets and return new balance."""
    pnl = sum(_bet_pnl(b) for b in bets if b.get('status') in ('won', 'lost'))
    return round(starting + pnl, 2)


def _bet_pnl(bet: dict) -> float:
    stake = float(bet.get('stake', 0))
    odds = float(bet.get('actual_odds') or bet.get('model_odds') or 1.0)
    if bet.get('status') == 'won':
        return round(stake * (odds - 1), 2)
    if bet.get('status') == 'lost':
        return round(-stake, 2)
    return 0.0


def bet_pnl(bet: dict) -> float:
    """Public wrapper — used by endpoints to compute display P&L."""
    return _bet_pnl(bet)


def load_clv() -> list:
    return get('clv/log.json') or []


def save_clv(entries: list) -> bool:
    return put('clv/log.json', entries)
