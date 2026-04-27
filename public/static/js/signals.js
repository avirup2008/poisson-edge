/* signals.js — Signal Board v2 (Focus+Feed redesign) */

'use strict';

let _signals = [];      // full result array from /api/signals
let _bankroll = 1000;   // loaded from /api/bankroll
let _currentModalSig = null;

// ── Utilities ──────────────────────────────────────────────────

function marketLabel(m) {
  if (!m) return '';
  const MAP = {
    hw: 'Home Win', aw: 'Away Win',
    o25: 'Over 2.5', u25: 'Under 2.5',
    o35: 'Over 3.5', btts: 'BTTS',
    h2h_home: 'Home Win', h2h_away: 'Away Win', h2h_draw: 'Draw',
  };
  return MAP[m] || m;
}

/**
 * Team-specific bet label. E.g. "Nott'm Forest Away Win" or "Over 2.5 Goals".
 * Used in card headers so it's immediately clear who you're betting on.
 */
function betLabel(sig) {
  const m = sig.market;
  if (!m) return '';
  if (m === 'hw') return `${sig.home} Home Win`;
  if (m === 'aw') return `${sig.away} Away Win`;
  if (m === 'o25') return 'Over 2.5 Goals';
  if (m === 'u25') return 'Under 2.5 Goals';
  if (m === 'o35') return 'Over 3.5 Goals';
  if (m === 'btts') return 'Both Teams to Score';
  return marketLabel(m);
}

/**
 * Format a YYYY-MM-DD date string to "Sat 10 May".
 * Returns empty string if date is absent/invalid.
 */
function formatKickoff(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr + 'T12:00:00Z');
    return d.toLocaleDateString('en-GB', {
      weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC'
    });
  } catch (_) { return dateStr; }
}

/**
 * Derive gate states from signal fields.
 * Returns { ev, prob, odds, conf } each = 'pass' | 'warn' | 'fail'
 */
function parseGates(sig) {
  const gb = sig.gate_block || '';
  const hasHardBlock = gb.includes('HARD-BLOCK');
  const hasSoftWarn  = gb.length > 0 && !hasHardBlock;
  const modelP       = (sig.model_p || 0) * 100;

  return {
    ev:   sig.ev_pct >= 15 ? 'pass' : sig.ev_pct >= 4  ? 'warn' : 'fail',
    prob: hasHardBlock      ? 'fail' : modelP >= 65     ? 'pass' : modelP >= 50 ? 'warn' : 'fail',
    odds: hasSoftWarn       ? 'warn' : 'pass',
    conf: 'pass',
  };
}

const GATE_LABELS = { ev: 'EV', prob: 'Prob', odds: 'Odds range', conf: 'Model conf.' };
const GATE_ICON   = { pass: '✓', warn: '⚠', fail: '✗' };

function renderGateChips(gates) {
  return Object.entries(GATE_LABELS).map(([key, label]) => {
    const state = gates[key];
    return `<div class="gate-chip ${state}">${GATE_ICON[state]} ${label}</div>`;
  }).join('');
}

/**
 * Render the edge bar showing implied vs model probability.
 * impliedP and modelP are both 0-100 percentages.
 */
function renderEdgeBar(impliedP, modelP) {
  const ppEdge = modelP - impliedP;
  const sign   = ppEdge >= 0 ? '+' : '';
  const fillW  = Math.min(modelP, 100).toFixed(1);
  const markW  = Math.min(impliedP, 100).toFixed(1);

  return `
    <div class="edge-bar-wrap">
      <div class="edge-bar-label">
        <span>Market Implied vs Model</span>
        <span class="pp-edge">${sign}${ppEdge.toFixed(1)} pp edge</span>
      </div>
      <div class="edge-bar-track">
        <div class="edge-bar-fill" style="width:${fillW}%"></div>
        <div class="edge-bar-marker" style="left:${markW}%"></div>
      </div>
      <div class="edge-bar-ticks">
        <span>Pinnacle ${impliedP.toFixed(1)}%</span>
        <span>Model ${modelP.toFixed(1)}%</span>
      </div>
    </div>`;
}

function renderDataCells(sig) {
  const impliedP = (1 / sig.odds) * 100;
  const modelP   = sig.model_p * 100;
  const ppEdge   = modelP - impliedP;
  const sign     = ppEdge >= 0 ? '+' : '';
  const modelOdds = sig.model_p > 0 ? (1 / sig.model_p).toFixed(2) : '—';

  return `
    <div class="ec-data-row">
      <div class="ec-data-cell">
        <div class="dc-label">λH</div>
        <div class="dc-val">${(sig.lambda_home || 0).toFixed(2)}</div>
      </div>
      <div class="ec-data-cell">
        <div class="dc-label">λA</div>
        <div class="dc-val">${(sig.lambda_away || 0).toFixed(2)}</div>
      </div>
      <div class="ec-data-cell">
        <div class="dc-label">Model odds</div>
        <div class="dc-val">${modelOdds}</div>
      </div>
      <div class="ec-data-cell">
        <div class="dc-label">Edge</div>
        <div class="dc-val green">${sign}${ppEdge.toFixed(1)}pp</div>
      </div>
    </div>`;
}

// ── Pinnacle vs B365 comparison ────────────────────────────────

function renderPinnacleVsB365(sig) {
  if (!sig.b365_odds) return '';
  const pin = sig.odds;
  const b365 = sig.b365_odds;
  const pips = Math.round((pin - b365) * 100);
  // Negative pips = Pinnacle lower = sharp money agrees = green
  const label  = pips <= -5 ? '✅ CONFIRMED'
               : pips <=  5 ? '~ NEUTRAL'
               : '⚠ FLAGGED';
  const color  = pips <= -5 ? 'var(--green)'
               : pips <=  5 ? 'var(--gold)'
               : 'var(--red)';
  const pipStr = (pips >= 0 ? '+' : '') + pips + ' pips';
  return `
    <div class="pin-b365">
      <span class="pb-item">Pinnacle <strong>${pin}</strong></span>
      <span class="pb-sep">·</span>
      <span class="pb-item">DK <strong>${b365}</strong></span>
      <span class="pb-sep">·</span>
      <span class="pb-pips" style="color:${color}">${pipStr} ${label}</span>
    </div>`;
}

// ── Lambda detail panel ─────────────────────────────────────────

function renderLambdaDetail(sig) {
  const d = sig.lambda_detail;
  if (!d || !d.lh) return '';

  const hFatigue = d.home_fatigue != null ? d.home_fatigue : 1.0;
  const aFatigue = d.away_fatigue != null ? d.away_fatigue : 1.0;
  const hRest = d.home_rest_days != null ? d.home_rest_days : 7;
  const aRest = d.away_rest_days != null ? d.away_rest_days : 7;
  const hMult = d.home_atk_mult != null ? d.home_atk_mult : 1.0;
  const aMult = d.away_atk_mult != null ? d.away_atk_mult : 1.0;

  return `
    <div class="lambda-detail">
      <div class="ld-toggle" onclick="this.parentElement.classList.toggle('ld-open')">
        <span>λ Model detail</span><span class="ld-chevron">›</span>
      </div>
      <div class="ld-body">
        <div class="ld-col">
          <div class="ld-title">λH = ${(d.lh || 0).toFixed(3)}</div>
          <div class="ld-row"><span>Atk rating</span><span>${(d.home_atk || 0).toFixed(3)}</span></div>
          <div class="ld-row"><span>Opp def rating</span><span>${(d.away_def || 0).toFixed(3)}</span></div>
          <div class="ld-row"><span>λ half × home adv</span><span>${((d.lhalf || 1.36) * (d.home_adv || 1.06)).toFixed(3)}</span></div>
          <div class="ld-row"><span>Injury mult</span><span>×${hMult.toFixed(2)}</span></div>
          <div class="ld-row"><span>Fatigue (${hRest}d)</span><span>×${hFatigue.toFixed(3)}</span></div>
        </div>
        <div class="ld-col">
          <div class="ld-title">λA = ${(d.la || 0).toFixed(3)}</div>
          <div class="ld-row"><span>Atk rating</span><span>${(d.away_atk || 0).toFixed(3)}</span></div>
          <div class="ld-row"><span>Opp def rating</span><span>${(d.home_def || 0).toFixed(3)}</span></div>
          <div class="ld-row"><span>λ half</span><span>${(d.lhalf || 1.36).toFixed(3)}</span></div>
          <div class="ld-row"><span>Injury mult</span><span>×${aMult.toFixed(2)}</span></div>
          <div class="ld-row"><span>Fatigue (${aRest}d)</span><span>×${aFatigue.toFixed(3)}</span></div>
        </div>
      </div>
    </div>`;
}

// ── ELEV Card ──────────────────────────────────────────────────

function renderElevCard(sig, globalIdx, promoted = false) {
  const impliedP = (1 / sig.odds) * 100;
  const modelP   = sig.model_p * 100;
  const gates    = parseGates(sig);
  const stake    = (sig.kelly_stake || 0).toFixed(2);
  const kickoff  = formatKickoff(sig.date);

  const soBadge = sig.structural_override
    ? `<span class="so-badge">⚡ Structural override · €5 max · Pinnacle check required</span>`
    : '';

  return `
    <div class="elev-card${promoted ? ' promoted' : ''}${sig.structural_override ? ' structural-override' : ''}">
      <div class="ec-header">
        <div class="ec-match">${sig.home} vs ${sig.away}</div>
        <div class="ec-bet-label">${betLabel(sig)}</div>
        <div class="ec-meta">Pinnacle @ ${sig.odds}${kickoff ? ' · ' + kickoff : ''}</div>
        ${soBadge}
      </div>

      <div class="ec-ev-row">
        <div>
          <div class="ec-ev-label">Expected Value</div>
          <div class="ec-ev-big">+${sig.ev_pct.toFixed(1)}%</div>
        </div>
        <div class="ec-prob-block">
          <div class="ec-prob-val">${modelP.toFixed(1)}%</div>
          <div class="ec-prob-label">Model Prob</div>
        </div>
      </div>

      ${renderEdgeBar(impliedP, modelP)}
      ${renderPinnacleVsB365(sig)}
      ${renderDataCells(sig)}

      <div class="gate-chips">${renderGateChips(gates)}</div>

      <div class="inj-section" data-home="${sig.home}" data-away="${sig.away}">
        <div class="inj-label">Absences</div>
        <div class="inj-loading">Loading…</div>
      </div>

      <div class="ec-footer">
        <div class="ec-kelly">Kelly 25% · <span>€${stake}</span></div>
        <button class="btn-log-bet" onclick="event.stopPropagation();openLogBetModal('${globalIdx}')">
          LOG BET
        </button>
      </div>
      ${renderLambdaDetail(sig)}
    </div>`;
}

// ── Feed Row ────────────────────────────────────────────────────

/**
 * Shared injury loader. Accepts an .inj-section element, fetches both teams,
 * and injects the result. Guards against double-fetch with dataset.loaded.
 */
function loadInjurySection(injDiv) {
  if (!injDiv || injDiv.dataset.loaded) return;
  const home = injDiv.dataset.home;
  const away = injDiv.dataset.away;
  injDiv.dataset.loaded = '1';
  Promise.all([
    fetch(`/api/injuries/${encodeURIComponent(home)}`).then(r => r.json()).catch(() => []),
    fetch(`/api/injuries/${encodeURIComponent(away)}`).then(r => r.json()).catch(() => []),
  ]).then(([homeInj, awayInj]) => {
    const fmt = (team, injs) => {
      if (!injs || !injs.length) return '';
      const names = injs.slice(0, 4).map(i => i.player || i.name || '?').join(', ');
      return `<div class="inj-row"><span class="inj-team">${team}:</span> ${names}${injs.length > 4 ? ` +${injs.length - 4} more` : ''}</div>`;
    };
    const html = fmt(home, homeInj) + fmt(away, awayInj);
    injDiv.innerHTML = html
      ? `<div class="inj-label">Absences</div>${html}`
      : '<div class="inj-row" style="color:var(--text-3)">No confirmed absences</div>';
  });
}

function toggleRow(wrap) {
  document.querySelectorAll('.feed-row-wrap.expanded').forEach(el => {
    if (el !== wrap) el.classList.remove('expanded');
  });
  wrap.classList.toggle('expanded');

  // Lazy-load injuries when row opens
  if (wrap.classList.contains('expanded')) {
    loadInjurySection(wrap.querySelector('.inj-section'));
  }
}

function renderFeedRow(sig, globalIdx) {
  const tier     = (sig.tier || 'NO').toLowerCase();
  const impliedP = (1 / sig.odds) * 100;
  const modelP   = sig.model_p * 100;
  const gates    = parseGates(sig);
  const stake    = (sig.kelly_stake || 0).toFixed(2);
  const kickoff  = formatKickoff(sig.date);
  const isBettable = sig.tier === 'BET' || sig.tier === 'ELEV';

  const wrapClass = sig.tier === 'ELEV' ? 'tier-elev-feed'
                  : sig.tier === 'BET'  ? 'tier-bet'
                  : sig.tier === 'SIM'  ? 'tier-sim'
                  : 'tier-no';

  const footerHtml = isBettable ? `
    <div class="expand-footer">
      <div class="expand-kelly">Kelly 25% · <span>€${stake}</span></div>
      <button class="btn-log-bet" onclick="event.stopPropagation();openLogBetModal('${globalIdx}')">
        LOG BET
      </button>
    </div>` : '';

  return `
    <div class="feed-row-wrap ${wrapClass}" onclick="toggleRow(this)">
      <div class="feed-row">
        <div>
          <span class="f-badge ${tier}">${sig.tier}</span>
          ${sig.structural_override ? '<span class="f-so-badge">⚡</span>' : ''}
        </div>
        <div class="f-match">
          <div class="f-match-name">${sig.home} vs ${sig.away}</div>
          <div class="f-match-sub">${betLabel(sig)} · ${kickoff}</div>
        </div>
        <div class="f-lambda">
          <div>λH <span>${(sig.lambda_home || 0).toFixed(2)}</span></div>
          <div>λA <span>${(sig.lambda_away || 0).toFixed(2)}</span></div>
        </div>
        <div class="f-prob">${modelP.toFixed(0)}%</div>
        <div class="f-odds">${sig.odds}</div>
        <div class="f-ev">+${sig.ev_pct.toFixed(1)}%</div>
        <div class="f-kelly">€${stake}</div>
        <div class="f-chevron">›</div>
      </div>
      <div class="expand-panel">
        <div class="expand-inner">
          ${renderEdgeBar(impliedP, modelP)}
          ${renderPinnacleVsB365(sig)}
          ${renderDataCells(sig)}
          <div class="inj-section" data-home="${sig.home}" data-away="${sig.away}">
            <div style="font-size:10px;font-weight:600;color:var(--text-3);letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px">Absences</div>
            <div style="color:var(--text-3);font-size:11px">Loading…</div>
          </div>
          <div class="gate-chips">${renderGateChips(gates)}</div>
          ${renderLambdaDetail(sig)}
          ${footerHtml}
        </div>
      </div>
    </div>`;
}

// ── Statusbar ───────────────────────────────────────────────────

/**
 * Derive EPL 2025-26 GW number from a YYYY-MM-DD date string.
 * Ranges are inclusive; update when season extends beyond GW38.
 */
function gwFromDate(dateStr) {
  if (!dateStr) return null;
  if (dateStr <= '2026-05-04') return 35;
  if (dateStr <= '2026-05-12') return 36;
  if (dateStr <= '2026-05-19') return 37;
  if (dateStr <= '2026-05-26') return 38;
  return null;
}

function updateStatusbar(signals, bankroll) {
  const betSigs = signals.filter(s => s.tier === 'BET' || s.tier === 'ELEV');
  const avgEV   = betSigs.length
    ? (betSigs.reduce((s, r) => s + r.ev_pct, 0) / betSigs.length).toFixed(1)
    : '—';
  const avgP    = betSigs.length
    ? (betSigs.reduce((s, r) => s + r.model_p * 100, 0) / betSigs.length).toFixed(1)
    : '—';
  const totalK  = betSigs.reduce((s, r) => s + (r.kelly_stake || 0), 0).toFixed(2);

  // Derive GW from the earliest fixture date in the current signal set
  const minDate = signals.reduce((m, s) => s.date && s.date < m ? s.date : m, '9999-12-31');
  const gw = gwFromDate(minDate !== '9999-12-31' ? minDate : null);
  const gwLabel = gw ? `GW${gw}` : '—';

  const el = id => document.getElementById(id);
  if (el('sb-gw'))            el('sb-gw').textContent = gwLabel;
  if (el('gw-meta'))          el('gw-meta').textContent = gwLabel;
  if (el('sb-fixture-count')) el('sb-fixture-count').textContent = signals.length;
  if (el('sb-avg-ev'))        el('sb-avg-ev').textContent  = avgEV !== '—' ? `+${avgEV}%` : '—';
  if (el('sb-avg-p'))         el('sb-avg-p').textContent   = avgP  !== '—' ? `${avgP}%`   : '—';
  if (el('sb-kelly'))         el('sb-kelly').textContent   = `€${totalK}`;
  if (el('sb-bankroll'))      el('sb-bankroll').textContent = `€${(bankroll || 0).toFixed(2)}`;
}

// ── Main render ─────────────────────────────────────────────────

function renderBoard(signals, bankroll) {
  _signals  = signals;
  _bankroll = bankroll || 1000;

  const ORDER = { ELEV: 0, BET: 1, SIM: 2, NO: 3 };
  const sorted = [...signals].sort((a, b) => {
    const td = (ORDER[a.tier] || 0) - (ORDER[b.tier] || 0);
    return td !== 0 ? td : b.ev_pct - a.ev_pct;
  });

  const elevSignals = sorted.filter(s => s.tier === 'ELEV');
  const betSignals  = sorted.filter(s => s.tier === 'BET');
  const restSignals = sorted.filter(s => s.tier === 'SIM' || s.tier === 'NO');

  // ELEV strip — show ELEV cards if any; otherwise promote top 3 BET signals
  const elevSection = document.getElementById('elev-section');
  const elevRow     = document.getElementById('elev-cards-row');
  const elevCount   = document.getElementById('elev-count');
  const elevTitle   = document.getElementById('elev-title');

  const stripSignals = elevSignals.length > 0 ? elevSignals : betSignals.slice(0, 3);
  const isPromoted   = elevSignals.length === 0 && stripSignals.length > 0;

  if (stripSignals.length === 0) {
    if (elevSection) elevSection.style.display = 'none';
  } else {
    if (elevSection) elevSection.style.display = '';
    if (elevTitle)   elevTitle.textContent = isPromoted ? 'TOP SIGNALS (Backtest only)' : 'Elevated Signals';
    if (elevCount)   elevCount.textContent = isPromoted
      ? `${stripSignals.length} signal${stripSignals.length !== 1 ? 's' : ''} · Top EV`
      : `${stripSignals.length} signal${stripSignals.length !== 1 ? 's' : ''} · EV≥15%`;
    const elevSubtitle = document.getElementById('elev-subtitle');
    if (elevSubtitle) {
      if (isPromoted) {
        elevSubtitle.textContent = 'No elevated signals this GW — these are tracking entries only, not real money recommendations.';
        elevSubtitle.style.display = '';
      } else {
        elevSubtitle.style.display = 'none';
      }
    }
    if (elevRow) {
      elevRow.innerHTML = stripSignals.map(s => {
        const gi = sorted.indexOf(s);
        return renderElevCard(s, gi, isPromoted);
      }).join('');
      // Auto-fetch injuries for always-visible ELEV cards
      elevRow.querySelectorAll('.inj-section').forEach(loadInjurySection);
    }
  }

  // Feed — BET group
  const feedBet       = document.getElementById('feed-bet');
  const feedBetHdr    = document.getElementById('feed-bet-header');
  const feedBetCount  = document.getElementById('feed-bet-count');
  if (feedBet) {
    feedBet.innerHTML = betSignals.map(s => {
      const gi = sorted.indexOf(s);
      return renderFeedRow(s, gi);
    }).join('');
  }
  if (feedBetHdr)   feedBetHdr.style.display   = betSignals.length ? '' : 'none';
  if (feedBetCount) feedBetCount.textContent    = `${betSignals.length} signal${betSignals.length !== 1 ? 's' : ''}`;

  // Feed — SIM/NO group (ELEV also appears here as compact rows)
  const allSim       = [...sorted.filter(s => s.tier === 'ELEV'), ...restSignals];
  const feedSim      = document.getElementById('feed-sim');
  const feedSimHdr   = document.getElementById('feed-sim-header');
  const feedSimCount = document.getElementById('feed-sim-count');
  if (feedSim) {
    feedSim.innerHTML = allSim.map(s => {
      const gi = sorted.indexOf(s);
      return renderFeedRow(s, gi);
    }).join('');
  }
  if (feedSimHdr)   feedSimHdr.style.display   = allSim.length ? '' : 'none';
  if (feedSimCount) feedSimCount.textContent    = `${allSim.length} signal${allSim.length !== 1 ? 's' : ''}`;

  updateStatusbar(signals, bankroll);
}

// ── Data loading ────────────────────────────────────────────────

async function loadSignals() {
  try {
    const [sigsRes, brRes] = await Promise.all([
      fetch('/api/signals'),
      fetch('/api/bankroll'),
    ]);
    const sigs = await sigsRes.json();
    const br   = await brRes.json();
    const bankroll = br.current_bankroll || br.starting_bankroll || 1000;
    renderBoard(Array.isArray(sigs) ? sigs : [], bankroll);
  } catch (err) {
    console.error('loadSignals error:', err);
  }
}

// ── Log Bet modal ───────────────────────────────────────────────

function openLogBetModal(idxStr) {
  const sig = _signals[parseInt(idxStr, 10)];
  if (!sig) return;

  // Store for submit handler
  _currentModalSig = sig;

  const modal = document.getElementById('log-bet-modal');
  if (!modal) return;
  modal.style.display = 'flex';

  const setText = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };
  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = val;
  };

  setText('lbm-match',      `${sig.home} vs ${sig.away}`);
  setText('lbm-market',     `${marketLabel(sig.market)} · Pinnacle @ ${sig.odds}`);
  setText('lbm-model-odds', (sig.model_p > 0 ? 1 / sig.model_p : 0).toFixed(2));
  setText('lbm-ev',         `+${sig.ev_pct.toFixed(1)}%`);
  setVal('lbm-actual-odds', sig.odds);
  setVal('lbm-stake',       (sig.kelly_stake || 0).toFixed(2));

  const errEl = document.getElementById('lbm-error');
  if (errEl) errEl.textContent = '';
}

function closeLogBetModal() {
  const modal = document.getElementById('log-bet-modal');
  if (modal) modal.style.display = 'none';
  _currentModalSig = null;
}

// ── Bootstrap ───────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadSignals();

  // Modal close
  const closeBtn = document.getElementById('lbm-close');
  if (closeBtn) closeBtn.addEventListener('click', closeLogBetModal);

  // Modal submit
  const submitBtn = document.getElementById('lbm-submit');
  if (submitBtn) submitBtn.addEventListener('click', async () => {
    const sig = _currentModalSig;
    if (!sig) return;

    const errEl = document.getElementById('lbm-error');
    const actualOddsEl = document.getElementById('lbm-actual-odds');
    const stakeEl      = document.getElementById('lbm-stake');

    const actualOdds = parseFloat(actualOddsEl?.value);
    const stake      = parseFloat(stakeEl?.value);

    if (!actualOdds || actualOdds < 1.01) {
      if (errEl) errEl.textContent = 'Enter valid actual odds (≥ 1.01)';
      return;
    }
    if (!stake || stake <= 0) {
      if (errEl) errEl.textContent = 'Enter a valid stake (> 0)';
      return;
    }

    try {
      await API.logBet({
        home:        sig.home,
        away:        sig.away,
        market:      marketLabel(sig.market),
        date:        sig.date || '',
        tier:        sig.tier,
        model_ev:    sig.ev_pct,
        model_p:     sig.model_p,
        model_odds:  sig.model_p > 0 ? 1 / sig.model_p : 0,
        actual_odds: actualOdds,
        stake,
      });
      closeLogBetModal();
    } catch (err) {
      if (errEl) errEl.textContent = `Error: ${err.message}`;
    }
  });

  // Close on backdrop click
  const modal = document.getElementById('log-bet-modal');
  if (modal) modal.addEventListener('click', e => {
    if (e.target === modal) closeLogBetModal();
  });
});
