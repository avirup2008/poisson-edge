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

  const wins = bets.filter(b => b.result === 'WIN').length;
  document.getElementById('kpi-winrate').textContent =
    bets.length ? `${(wins / bets.length * 100).toFixed(0)}%` : '—';

  const avgStake = bets.length
    ? `€${(bets.reduce((a, b) => a + b.stake, 0) / bets.length).toFixed(2)}`
    : '—';
  document.getElementById('kpi-avgstake').textContent = avgStake;

  // Recent bets table (last 10, newest first)
  const tbody = document.getElementById('bets-tbody');
  if (bets.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="color:var(--text-2);padding:24px 0">No bets recorded yet.</td></tr>';
  } else {
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

  // Status bar
  document.getElementById('sb-start').textContent = `€${starting_bankroll.toFixed(2)}`;
  document.getElementById('sb-pnl').textContent = `${pnl >= 0 ? '+' : ''}€${pnl.toFixed(2)}`;
  document.getElementById('sb-total-bets').textContent = bets.length;

  // Max drawdown
  let peak = starting_bankroll;
  let maxDD = 0;
  let running = starting_bankroll;
  for (const b of bets) {
    running += b.pnl || 0;
    peak = Math.max(peak, running);
    maxDD = Math.max(maxDD, peak - running);
  }
  document.getElementById('sb-dd').textContent = maxDD > 0 ? `-€${maxDD.toFixed(2)}` : '—';
}

document.addEventListener('DOMContentLoaded', () => {
  loadBankroll().catch(console.error);
});
