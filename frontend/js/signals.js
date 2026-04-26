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
  const labels = {
    o25: 'Over 2.5 Goals', u25: 'Under 2.5 Goals',
    btts: 'Both Teams to Score', hw: 'Home Win',
    aw: 'Away Win', o35: 'Over 3.5 Goals'
  };
  return labels[m] || m;
}

document.addEventListener('DOMContentLoaded', () => {
  loadSignals().catch(err => {
    const cardsEl = document.getElementById('elev-cards');
    if (cardsEl) cardsEl.innerHTML = `<div style="color:var(--red);padding:24px">Error: ${err.message}</div>`;
  });
});
