const PARAM_META = {
  rho:      { label: 'Dixon-Coles ρ', desc: 'Low-score correction factor', pct: 55 },
  home_adv: { label: 'Home Advantage', desc: 'Lambda multiplier for home side', pct: 65 },
  blend:    { label: 'Form Blend', desc: 'Recent 6 games vs season average', pct: 35 },
  nr:       { label: 'Rolling Window', desc: 'Recent matches for form calc', pct: 60 },
  lhalf:    { label: 'λ Half-life', desc: 'Exponential decay for older matches', pct: 68 },
  elo_alpha:{ label: 'ELO α (HW blend)', desc: 'ELO weight in home-win ensemble', pct: 65 },
};

async function loadModel() {
  const data = await API.model();
  const { version, parameters, elo_ratings, data_ready, total_matches } = data;

  document.getElementById('hero-version').textContent = version || '4.1';
  document.getElementById('kpi-matches').textContent = (total_matches || 0).toLocaleString();
  document.getElementById('kpi-teams').textContent = Object.keys(elo_ratings || {}).length;
  document.getElementById('kpi-ready').textContent = data_ready ? 'Yes' : 'No';
  document.getElementById('sb-matches').textContent = (total_matches || 0).toLocaleString();

  // Parameter cards
  const grid = document.getElementById('param-grid');
  grid.innerHTML = Object.entries(parameters || {}).map(([key, val]) => {
    const meta = PARAM_META[key] || { label: key, desc: '', pct: 50 };
    const display = typeof val === 'number' ? val.toString() : val;
    return `
      <div class="kpi" style="position:relative">
        <div class="kpi-label">${meta.label}</div>
        <div class="kpi-val" style="font-size:36px;letter-spacing:-0.025em;line-height:1;margin-bottom:4px">
          <span style="color:var(--gold)">${display}</span>
        </div>
        <div class="kpi-sub">${meta.desc}</div>
        <div class="progress-bar">
          <div class="progress-fill" style="width:${meta.pct}%"></div>
        </div>
      </div>
    `;
  }).join('');
}

document.addEventListener('DOMContentLoaded', () => {
  loadModel().catch(err => {
    document.getElementById('param-grid').innerHTML =
      `<div style="color:var(--red);padding:24px">Error loading model data: ${err.message}</div>`;
  });
});
