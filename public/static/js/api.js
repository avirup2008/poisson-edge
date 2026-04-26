// Thin fetch wrappers for all POISSON-EDGE API endpoints
const API = {
  async signals() {
    const r = await fetch('/api/signals');
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
  async bankroll() {
    const r = await fetch('/api/bankroll');
    if (!r.ok) throw new Error(`bankroll: ${r.status}`);
    return r.json();
  },
  async backtest() {
    const r = await fetch('/api/backtest');
    if (!r.ok) throw new Error(`backtest: ${r.status}`);
    return r.json();
  },
  async model() {
    const r = await fetch('/api/model');
    if (!r.ok) throw new Error(`model: ${r.status}`);
    return r.json();
  },
  async logBet(payload) {
    const r = await fetch('/api/bets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(`logBet: ${r.status}`);
    return r.json();
  },
  async bets() {
    const r = await fetch('/api/bets');
    if (!r.ok) throw new Error(`bets: ${r.status}`);
    return r.json();
  },
  async refreshResults() {
    const r = await fetch('/api/refresh-results', { method: 'POST' });
    if (!r.ok) throw new Error(`refresh-results: ${r.status}`);
    return r.json();
  },
};
