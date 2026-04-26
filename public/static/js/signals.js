// Signal data cached for modal pre-fill
let _signals = [];

async function loadSignals() {
  _signals = await API.signals();

  const elev = _signals.filter(s => s.tier === 'ELEV');
  document.getElementById('elev-count').textContent = elev.length;
  document.getElementById('gw-meta').textContent = 'Premier League';

  // ELEV cards
  const cardsEl = document.getElementById('elev-cards');
  if (elev.length === 0) {
    cardsEl.innerHTML = '<div style="color:var(--text-2);padding:24px">No elevated signals this gameweek.</div>';
  } else {
    cardsEl.innerHTML = elev.map((s, i) => {
      const pinnacle = s.gate_block
        ? `<span style="color:var(--gold);font-size:10px;font-weight:700;letter-spacing:0.06em">⚠ FLAGGED</span>`
        : `<span style="color:var(--green);font-size:10px;font-weight:700;letter-spacing:0.06em">✓ CONFIRMED</span>`;
      return `
      <div class="card">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:22px">
          <div style="display:flex;align-items:center;gap:7px;font-size:10px;font-weight:700;color:var(--gold);letter-spacing:0.1em;text-transform:uppercase">
            <div class="elev-pip"></div> Elevated
          </div>
          ${pinnacle}
        </div>
        <div style="font-size:24px;font-weight:700;letter-spacing:-0.02em;margin-bottom:7px">${s.home} vs ${s.away}</div>
        <div style="font-size:14px;color:var(--text-2);margin-bottom:24px">${marketLabel(s.market)} <strong style="color:var(--text-1)">@ ${s.odds}</strong></div>
        <div style="display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:20px">
          <div>
            <div style="font-size:10px;font-weight:500;color:var(--text-3);letter-spacing:0.09em;text-transform:uppercase;margin-bottom:3px">Expected Value</div>
            <div style="font-size:38px;font-weight:700;color:var(--gold);letter-spacing:-0.025em;line-height:1">${s.ev_pct > 0 ? '+' : ''}${s.ev_pct.toFixed(1)}%</div>
          </div>
          <div style="text-align:right">
            <div style="font-size:10px;font-weight:500;color:var(--text-3);letter-spacing:0.09em;text-transform:uppercase;margin-bottom:3px">Kelly 25%</div>
            <div style="font-size:22px;font-weight:600;letter-spacing:-0.01em">€${s.kelly_stake.toFixed(2)}</div>
          </div>
        </div>
        <div style="padding-top:16px;border-top:1px solid var(--border);display:flex;align-items:center;justify-content:space-between">
          <div style="display:flex;align-items:center;gap:5px">
            <span style="font-size:9px;font-weight:500;color:var(--text-3);letter-spacing:0.09em;text-transform:uppercase;margin-right:4px">Gates</span>
            <div class="gp pass"></div><div class="gp pass"></div><div class="gp pass"></div>
            <div class="gp pass"></div><div class="gp pass"></div><div class="gp pass"></div>
            <div class="gp ${s.gate_block ? 'warn' : 'pass'}"></div>
          </div>
          <button onclick="openLogBetModal(${i})" style="
            background:var(--gold);color:#000;border:none;border-radius:7px;
            padding:7px 16px;font-size:11px;font-weight:700;letter-spacing:0.06em;
            text-transform:uppercase;cursor:pointer">Log Bet</button>
        </div>
      </div>`;
    }).join('');
  }

  // All signals table
  const tbody = document.getElementById('all-tbody');
  tbody.innerHTML = _signals.map(s => `
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

  document.getElementById('all-label').textContent = `All Signals · ${_signals.length} markets`;

  const elevAvgP = elev.length ? (elev.reduce((a,s) => a + s.model_p, 0) / elev.length * 100).toFixed(1) + '%' : '—';
  const elevAvgEV = elev.length ? '+' + (elev.reduce((a,s) => a + s.ev_pct, 0) / elev.length).toFixed(1) + '%' : '—';
  const totalStake = elev.reduce((a,s) => a + s.kelly_stake, 0);
  document.getElementById('sb-avg-p').textContent = elevAvgP;
  document.getElementById('sb-avg-ev').textContent = elevAvgEV;
  document.getElementById('sb-stake').textContent = `€${totalStake.toFixed(2)}`;
}

function marketLabel(m) {
  const labels = {
    o25: 'Over 2.5 Goals', u25: 'Under 2.5 Goals',
    btts: 'Both Teams to Score', hw: 'Home Win',
    aw: 'Away Win', o35: 'Over 3.5 Goals'
  };
  return labels[m] || m;
}

// ── Log Bet Modal ────────────────────────────────────────────────────────────

function openLogBetModal(idx) {
  const elev = _signals.filter(s => s.tier === 'ELEV');
  const s = elev[idx];
  if (!s) return;
  document.getElementById('lbm-match').textContent = `${s.home} vs ${s.away}`;
  document.getElementById('lbm-market').textContent = marketLabel(s.market);
  document.getElementById('lbm-model-odds').textContent = s.odds;
  document.getElementById('lbm-ev').textContent = `${s.ev_pct > 0 ? '+' : ''}${s.ev_pct.toFixed(1)}%`;
  document.getElementById('lbm-actual-odds').value = s.odds;
  document.getElementById('lbm-stake').value = s.kelly_stake.toFixed(2);
  document.getElementById('lbm-error').textContent = '';
  document.getElementById('lbm-submit').textContent = 'Log Bet';
  document.getElementById('lbm-submit').disabled = false;
  document.getElementById('log-bet-modal').dataset.signal = JSON.stringify(s);
  document.getElementById('log-bet-modal').style.display = 'flex';
}

function closeLogBetModal() {
  document.getElementById('log-bet-modal').style.display = 'none';
}

async function submitLogBet() {
  const modal = document.getElementById('log-bet-modal');
  const s = JSON.parse(modal.dataset.signal || '{}');
  const actualOdds = parseFloat(document.getElementById('lbm-actual-odds').value);
  const stake = parseFloat(document.getElementById('lbm-stake').value);
  const errEl = document.getElementById('lbm-error');

  if (!actualOdds || actualOdds < 1.01) { errEl.textContent = 'Enter valid odds (≥ 1.01)'; return; }
  if (!stake || stake <= 0) { errEl.textContent = 'Enter a positive stake'; return; }

  const btn = document.getElementById('lbm-submit');
  btn.textContent = 'Logging…'; btn.disabled = true;

  try {
    await API.logBet({
      home: s.home, away: s.away, market: s.market,
      date: s.date || new Date().toISOString().slice(0, 10),
      tier: s.tier, model_ev: s.ev_pct, model_p: s.model_p,
      model_odds: s.odds, actual_odds: actualOdds, stake,
    });
    closeLogBetModal();
    const flash = document.createElement('div');
    flash.textContent = '✓ Bet logged';
    flash.style.cssText = 'position:fixed;bottom:32px;right:32px;background:var(--green);color:#fff;padding:12px 20px;border-radius:8px;font-weight:600;z-index:9999;font-size:13px';
    document.body.appendChild(flash);
    setTimeout(() => flash.remove(), 2500);
  } catch (e) {
    errEl.textContent = `Error: ${e.message}`;
    btn.textContent = 'Log Bet'; btn.disabled = false;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  loadSignals().catch(err => {
    const cardsEl = document.getElementById('elev-cards');
    if (cardsEl) cardsEl.innerHTML = `<div style="color:var(--red);padding:24px">Error: ${err.message}</div>`;
  });
  document.getElementById('lbm-close')?.addEventListener('click', closeLogBetModal);
  document.getElementById('lbm-submit')?.addEventListener('click', submitLogBet);
  document.getElementById('log-bet-modal')?.addEventListener('click', e => {
    if (e.target === e.currentTarget) closeLogBetModal();
  });
});
