/* signals.js — Signal Board v2 (Focus+Feed redesign) */

'use strict';

let _signals = [];      // full result array from /api/signals
let _bankroll = 1000;   // loaded from /api/bankroll

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

  return {
    ev:   sig.ev_pct >= 4  ? 'pass' : sig.ev_pct >= 0 ? 'warn' : 'fail',
    prob: hasHardBlock      ? 'fail' : 'pass',
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

function renderElevCard(sig, globalIdx) {
  const impliedP = (1 / sig.odds) * 100;
  const modelP   = sig.model_p * 100;
  const gates    = parseGates(sig);
  const stake    = (sig.kelly_stake || 0).toFixed(2);
  const kickoff  = formatKickoff(sig.date);

  return `
    <div class="elev-card">
      <div class="ec-header">
        <div>
          <div class="ec-match">${sig.home} vs ${sig.away}</div>
          <div class="ec-meta">${marketLabel(sig.market)} · Pinnacle @ ${sig.odds}</div>
        </div>
        <div class="ec-kickoff">${kickoff}</div>
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
        <div><span class="f-badge ${tier}">${sig.tier}</span></div>
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

function updateStatusbar(signals, bankroll) {
  const betSigs = signals.filter(s => s.tier === 'BET' || s.tier === 'ELEV');
  const avgEV   = betSigs.length
    ? (betSigs.reduce((s, r) => s + r.ev_pct, 0) / betSigs.length).toFixed(1)
    : '—';
  const avgP    = betSigs.length
    ? (betSigs.reduce((s, r) => s + r.model_p * 100, 0) / betSigs.length).toFixed(1)
    : '—';
  const totalK  = betSigs.reduce((s, r) => s + (r.kelly_stake || 0), 0).toFixed(2);

  const el = id => document.getElementById(id);
  if (el('sb-gw'))            el('sb-gw').textContent = 'GW35';
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

  // ELEV strip
  const elevSection = document.getElementById('elev-section');
  const elevRow     = document.getElementById('elev-cards-row');
  const elevCount   = document.getElementById('elev-count');

  if (elevSignals.length === 0) {
    if (elevSection) elevSection.style.display = 'none';
  } else {
    if (elevSection) elevSection.style.display = '';
    if (elevCount)   elevCount.textContent = `${elevSignals.length} signal${elevSignals.length !== 1 ? 's' : ''} · EV≥15%`;
    if (elevRow) {
      elevRow.innerHTML = elevSignals.map(s => {
        const gi = sorted.indexOf(s);
        return renderElevCard(s, gi);
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

  const modal = document.getElementById('log-bet-modal');
  if (!modal) return;
  modal.style.display = 'flex';

  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = val;
  };

  set('lb-home',       sig.home);
  set('lb-away',       sig.away);
  set('lb-market',     marketLabel(sig.market));
  set('lb-date',       sig.date || '');
  set('lb-tier',       sig.tier);
  set('lb-model-ev',   sig.ev_pct.toFixed(4));
  set('lb-model-p',    sig.model_p.toFixed(4));
  set('lb-model-odds', (1 / sig.model_p).toFixed(2));
  set('lb-actual-odds', sig.odds);
  set('lb-stake',       (sig.kelly_stake || 0).toFixed(2));
}

function closeLogBetModal() {
  const modal = document.getElementById('log-bet-modal');
  if (modal) modal.style.display = 'none';
}

// ── Bootstrap ───────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', loadSignals);
