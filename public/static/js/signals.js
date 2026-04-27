/* signals.js — Signal Board v2 (Focus+Feed redesign) */

'use strict';

let _signals = [];      // full result array from /api/signals
let _bankroll = 1000;   // loaded from /api/bankroll
let _currentModalSig = null;

// ── Utilities ──────────────────────────────────────────────────

function marketLabel(m) {
  if (!m) return '';
  if (m === 'h2h_home' || m === 'home') return 'Home Win';
  if (m === 'h2h_away' || m === 'away') return 'Away Win';
  if (m === 'h2h_draw' || m === 'draw') return 'Draw';
  return m;
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
        <div class="ec-meta">${marketLabel(sig.market)} · Pinnacle @ ${sig.odds}${kickoff ? ' · ' + kickoff : ''}</div>
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
      ${renderDataCells(sig)}

      <div class="gate-chips">${renderGateChips(gates)}</div>

      <div class="ec-footer">
        <div class="ec-kelly">Kelly 25% · <span>€${stake}</span></div>
        <button class="btn-log-bet" onclick="event.stopPropagation();openLogBetModal('${globalIdx}')">
          LOG BET
        </button>
      </div>
    </div>`;
}

// ── Feed Row ────────────────────────────────────────────────────

function toggleRow(wrap) {
  document.querySelectorAll('.feed-row-wrap.expanded').forEach(el => {
    if (el !== wrap) el.classList.remove('expanded');
  });
  wrap.classList.toggle('expanded');
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
          <div class="f-match-sub">${marketLabel(sig.market)} · ${kickoff}</div>
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
          ${renderDataCells(sig)}
          <div class="gate-chips">${renderGateChips(gates)}</div>
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
