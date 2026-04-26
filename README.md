# POISSON-EDGE

Quantitative football betting signal dashboard. Poisson + Dixon-Coles (ρ=−0.05) + ELO ensemble (α=0.65), 7-gate validation, Kelly 25% fractional staking.

## Stack

- **Model** — Python (numpy, scipy, pandas)
- **API** — FastAPI + uvicorn
- **Frontend** — Vanilla HTML/CSS/JS

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload
```

Open `http://localhost:8000` in your browser.

## Structure

```
model/       Poisson, Dixon-Coles, ELO, ensemble, gates, Kelly
api/         FastAPI app — serves /signals, /bankroll, /backtest
frontend/    HTML pages + CSS design tokens + JS fetch layer
data/        Fixture and results JSON (gitignored: raw/cache)
scripts/     Fixture fetching utilities
```

## Signal Tiers

| Tier | Criteria |
|------|----------|
| ELEV | EV ≥ +15% · P ≥ 65% · all 7 gates pass |
| BET  | EV ≥ +4% |
| SIM  | EV ≥ 0% |
| NO   | EV < 0% |
