async function loadBacktest() {
  const data = await API.backtest();

  document.getElementById('hero-matches').textContent = (data.total_matches || 0).toLocaleString();
  document.getElementById('kpi-seasons').textContent = data.seasons || '—';
  document.getElementById('kpi-matches').textContent = (data.total_matches || 0).toLocaleString();
  document.getElementById('sb-seasons').textContent = data.seasons || '—';
  document.getElementById('sb-matches').textContent = (data.total_matches || 0).toLocaleString();

  document.getElementById('backtest-note').innerHTML = `
    <strong style="color:var(--text-1)">${(data.total_matches || 0).toLocaleString()} EPL fixtures</strong> loaded across
    <strong style="color:var(--text-1)">${data.seasons || 16} seasons</strong> (2010–2026).<br><br>
    ${data.note || 'Full per-gameweek signal replay available in v2.'}
  `;
}

document.addEventListener('DOMContentLoaded', () => {
  loadBacktest().catch(console.error);
});
