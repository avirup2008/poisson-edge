function marketLabel(m) {
  const labels = {
    o25: 'Over 2.5', u25: 'Under 2.5',
    btts: 'BTTS', hw: 'Home Win',
    aw: 'Away Win', o35: 'Over 3.5',
  };
  return labels[m] || m;
}

async function loadBankroll() {
  const data = await API.bankroll();
  const { starting_bankroll, current_bankroll, bets } = data;

  document.getElementById('hero-balance').textContent = `€${current_bankroll.toFixed(2)}`;

  const pnl = current_bankroll - starting_bankroll;
  document.getElementById('hero-sub').textContent =
    `Starting €${starting_bankroll.toFixed(2)} · ${pnl >= 0 ? '+' : ''}€${pnl.toFixed(2)} this season`;

  const roi = ((pnl / starting_bankroll) * 100).toFixed(1);
  document.getElementById('kpi-roi').textContent = `${roi > 0 ? '+' : ''}${roi}%`;
  document.getElementById('kpi-bets').textContent = bets.length;

  // Win rate: settled bets only (exclude pending/void)
  const settled = bets.filter(b => b.result === 'WIN' || b.result === 'LOSS');
  const wins = settled.filter(b => b.result === 'WIN').length;
  document.getElementById('kpi-winrate').textContent =
    settled.length ? `${(wins / settled.length * 100).toFixed(0)}%` : '—';

  const avgStake = bets.length
    ? `€${(bets.reduce((a, b) => a + b.stake, 0) / bets.length).toFixed(2)}`
    : '—';
  document.getElementById('kpi-avgstake').textContent = avgStake;

  // Recent bets table (last 10, newest first)
  const tbody = document.getElementById('bets-tbody');
  if (bets.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="color:var(--text-2);padding:24px 0">No bets recorded yet.</td></tr>';
  } else {
    tbody.innerHTML = bets.slice(-10).reverse().map(b => {
      const isPending = b.result === 'PENDING';
      const pnlColor = isPending ? 'var(--text-3)' : b.pnl >= 0 ? 'var(--green)' : 'var(--red)';
      const pnlText = isPending ? '—' : `${b.pnl >= 0 ? '+' : ''}€${Math.abs(b.pnl).toFixed(2)}`;
      const resultColor = b.result === 'WIN' ? 'var(--green)' : b.result === 'LOSS' ? 'var(--red)' : 'var(--text-2)';
      const scoreTag = b.result_score
        ? ` <span style="color:var(--text-3);font-size:10px">${b.result_score}</span>`
        : '';
      return `
      <tr>
        <td><span class="tbadge tb-${(b.tier || 'bet').toLowerCase()}">${b.tier || 'BET'}</span></td>
        <td>
          <div style="font-size:14px;font-weight:500">${b.home} vs ${b.away}</div>
          <div style="font-size:11px;color:var(--text-2)">${marketLabel(b.market)} · @ ${(b.odds || 0).toFixed(2)} · ${b.date || ''}</div>
        </td>
        <td style="font-size:14px;font-weight:500">€${(b.stake || 0).toFixed(2)}</td>
        <td style="text-align:right">
          <span style="font-size:12px;font-weight:600;color:${resultColor}">${b.result}${scoreTag}</span>
        </td>
        <td style="text-align:right;font-size:14px;font-weight:600;color:${pnlColor}">${pnlText}</td>
      </tr>`;
    }).join('');
  }

  // Status bar
  document.getElementById('sb-start').textContent = `€${starting_bankroll.toFixed(2)}`;
  document.getElementById('sb-pnl').textContent = `${pnl >= 0 ? '+' : ''}€${pnl.toFixed(2)}`;
  document.getElementById('sb-total-bets').textContent = bets.length;

  // Max drawdown (settled bets only)
  let peak = starting_bankroll;
  let maxDD = 0;
  let running = starting_bankroll;
  for (const b of bets) {
    if (b.result === 'WIN' || b.result === 'LOSS') {
      running += b.pnl || 0;
      peak = Math.max(peak, running);
      maxDD = Math.max(maxDD, peak - running);
    }
  }
  document.getElementById('sb-dd').textContent = maxDD > 0 ? `-€${maxDD.toFixed(2)}` : '—';
}

document.addEventListener('DOMContentLoaded', () => {
  loadBankroll().catch(err => {
    document.getElementById('bets-tbody').innerHTML =
      `<tr><td colspan="5" style="color:var(--red);padding:24px 0">Error loading bankroll: ${err.message}</td></tr>`;
  });
});
