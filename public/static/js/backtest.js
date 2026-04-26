function renderCurve(curve, starting) {
  if (!curve || curve.length < 2) return '';
  const W = 560, H = 120, PAD = 8;
  const balances = curve.map(p => p.balance);
  const minB = Math.min(...balances);
  const maxB = Math.max(...balances);
  const range = maxB - minB || 1;
  const pts = curve.map((p, i) => {
    const x = PAD + (i / (curve.length - 1)) * (W - PAD * 2);
    const y = PAD + (1 - (p.balance - minB) / range) * (H - PAD * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const baseline = PAD + (1 - (starting - minB) / range) * (H - PAD * 2);
  const lastBal = balances[balances.length - 1];
  const color = lastBal >= starting ? 'var(--green)' : 'var(--red)';
  const lastX = (PAD + (W - PAD * 2)).toFixed(1);
  const lastY = (PAD + (1 - (lastBal - minB) / range) * (H - PAD * 2)).toFixed(1);
  return `
  <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:${H}px;display:block;margin-top:16px">
    <line x1="${PAD}" y1="${baseline.toFixed(1)}" x2="${W - PAD}" y2="${baseline.toFixed(1)}"
      stroke="var(--border)" stroke-width="1" stroke-dasharray="4,3"/>
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2"
      stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${lastX}" cy="${lastY}" r="3" fill="${color}"/>
  </svg>`;
}

function tierBlock(label, t) {
  if (!t || t.bets === 0) {
    return `<div style="color:var(--text-3);font-size:13px;padding:8px 0">${label}: no settled bets yet</div>`;
  }
  const roiColor = (t.roi || 0) >= 0 ? 'var(--green)' : 'var(--red)';
  const pnlColor = (t.total_pnl || 0) >= 0 ? 'var(--green)' : 'var(--red)';
  return `
  <div style="background:var(--surface-2);border-radius:10px;padding:16px 20px;
    display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:12px">
    <div>
      <div style="font-size:9px;font-weight:600;color:var(--text-3);letter-spacing:0.09em;
        text-transform:uppercase;margin-bottom:4px">${label} · Bets</div>
      <div style="font-size:22px;font-weight:700">${t.bets}
        <span style="font-size:13px;color:var(--text-3)">(${t.wins}W)</span></div>
    </div>
    <div>
      <div style="font-size:9px;font-weight:600;color:var(--text-3);letter-spacing:0.09em;
        text-transform:uppercase;margin-bottom:4px">Hit Rate</div>
      <div style="font-size:22px;font-weight:700">${t.hit_rate != null ? t.hit_rate + '%' : '—'}</div>
    </div>
    <div>
      <div style="font-size:9px;font-weight:600;color:var(--text-3);letter-spacing:0.09em;
        text-transform:uppercase;margin-bottom:4px">ROI</div>
      <div style="font-size:22px;font-weight:700;color:${roiColor}">
        ${t.roi != null ? (t.roi >= 0 ? '+' : '') + t.roi + '%' : '—'}</div>
    </div>
    <div>
      <div style="font-size:9px;font-weight:600;color:var(--text-3);letter-spacing:0.09em;
        text-transform:uppercase;margin-bottom:4px">P&amp;L</div>
      <div style="font-size:22px;font-weight:700;color:${pnlColor}">
        ${t.total_pnl != null
          ? (t.total_pnl >= 0 ? '+' : '') + '€' + Math.abs(t.total_pnl).toFixed(2)
          : '—'}</div>
    </div>
  </div>`;
}

async function loadBacktest() {
  const data = await API.backtest();

  // Hero + existing KPI strip
  document.getElementById('hero-matches').textContent = (data.total_matches || 0).toLocaleString();
  document.getElementById('kpi-seasons').textContent = data.seasons || '—';
  document.getElementById('kpi-matches').textContent = (data.total_matches || 0).toLocaleString();
  document.getElementById('sb-seasons').textContent = data.seasons || '—';
  document.getElementById('sb-matches').textContent = (data.total_matches || 0).toLocaleString();

  const pendingLabel = data.pending_bets > 0 ? ` · ${data.pending_bets} pending` : '';
  document.getElementById('backtest-note').innerHTML = `
    <strong style="color:var(--text-1)">${(data.total_matches || 0).toLocaleString()} EPL fixtures</strong>
    across <strong style="color:var(--text-1)">${data.seasons || 16} seasons</strong> (2010–2026).
    ${data.total_bets > 0
      ? `<strong style="color:var(--text-1)">${data.settled_bets} settled bets</strong>${pendingLabel} in the log.`
      : 'No bets logged yet.'}
  `;

  // Inject live stats below existing content
  document.getElementById('bt-live-stats')?.remove();
  const content = document.querySelector('.content');
  const elev = (data.by_tier || {}).ELEV || {};
  const bet  = (data.by_tier || {}).BET  || {};
  const clvLine = data.avg_clv != null
    ? `<div style="margin-top:12px;font-size:13px;color:var(--text-2)">
        Avg CLV: <strong style="color:${data.avg_clv >= 0 ? 'var(--green)' : 'var(--red)'}">
        ${data.avg_clv >= 0 ? '+' : ''}${data.avg_clv}%</strong>
       </div>`
    : '';

  const block = document.createElement('div');
  block.id = 'bt-live-stats';
  block.innerHTML = `
    <div class="sdiv" style="margin-top:32px">
      <span class="sdiv-label">Live Bet Performance</span><div class="sdiv-line"></div>
    </div>
    ${data.settled_bets === 0
      ? `<div style="color:var(--text-2);font-size:14px;padding:8px 0">
           No settled bets yet — log your first bet from the Signal Board.
         </div>`
      : `${tierBlock('ELEV', elev)}
         <div style="margin-top:10px"></div>
         ${tierBlock('BET', bet)}
         ${clvLine}`
    }
    <div class="sdiv" style="margin-top:32px">
      <span class="sdiv-label">Bankroll Curve</span><div class="sdiv-line"></div>
    </div>
    ${data.bankroll_curve && data.bankroll_curve.length > 1
      ? renderCurve(data.bankroll_curve, data.bankroll_curve[0]?.balance || 1000)
      : `<div style="color:var(--text-2);font-size:14px;padding:8px 0">
           Curve will appear once bets settle.
         </div>`
    }
  `;
  content.appendChild(block);
}

document.addEventListener('DOMContentLoaded', () => {
  loadBacktest().catch(err => {
    document.getElementById('backtest-note').innerHTML =
      `<span style="color:var(--red)">Error loading backtest data: ${err.message}</span>`;
  });
});
