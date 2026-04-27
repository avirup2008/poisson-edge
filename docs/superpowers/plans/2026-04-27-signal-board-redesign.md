# Signal Board Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat signal list with a Focus+Feed layout — ELEV cards in a horizontal top strip, a scrollable accordion feed below, and a live statusbar — so every signal is actionable without opening a spreadsheet.

**Architecture:** Three vanilla files are rewritten (index.html, signals.js, globals.css) and one API layer change adds the missing `date` field to the signal response. No new dependencies, no build step — all changes are drop-in replacements to the existing FastAPI + static-file setup.

**Tech Stack:** Python/FastAPI (signal_engine.py, main.py), vanilla JS (signals.js), vanilla CSS (globals.css), HTML (index.html)

**Spec:** `docs/superpowers/specs/2026-04-27-signal-board-redesign.md`
**Mockup:** `.superpowers/brainstorm/63516-1777277428/content/full-mockup-c5.html`

---

### Task 1: Add fixture date to signal API response

**Files:**
- Modify: `api/signal_engine.py` — add `date` field to `SignalResult` dataclass and populate it in `compute()`
- Modify: `api/main.py` — add `'date'` key to `_serialise()` return dict
- Test: `tests/test_signal_engine.py` (create if absent)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_engine.py
import json
from pathlib import Path
import pytest
from api.signal_engine import GWSignals

FIXTURES = [
    {
        "home": "Arsenal", "away": "Chelsea",
        "date": "2026-05-10",
        "h2h": {"home": 2.10, "away": 3.50, "draw": 3.20},
        "totals": {},
    }
]


def test_signal_result_has_date(tmp_path, monkeypatch):
    """SignalResult.date is propagated from the fixture dict."""
    import pandas as pd
    historical = pd.DataFrame({
        "HomeTeam": ["Arsenal"] * 10,
        "AwayTeam": ["Chelsea"] * 10,
        "FTHG": [1] * 10, "FTAG": [1] * 10,
        "Season": ["2324"] * 10,
    })
    gw = GWSignals(
        fixtures=FIXTURES,
        historical=historical,
        g_atk={}, g_def={},
        bankroll=1000,
        elo_ratings={},
    )
    results = gw.compute()
    # At least one result must carry the fixture date
    assert any(r.date == "2026-05-10" for r in results)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
python -m pytest tests/test_signal_engine.py::test_signal_result_has_date -v 2>&1 | head -30
```

Expected: `AttributeError: 'SignalResult' object has no attribute 'date'` or similar failure.

- [ ] **Step 3: Add `date` field to `SignalResult` and populate it**

In `api/signal_engine.py`, locate the `SignalResult` dataclass (search for `@dataclass` near the top of the file) and add `date` as an optional field:

```python
# BEFORE (inside the dataclass, after existing fields):
gate_block: Optional[str] = None

# AFTER:
gate_block: Optional[str] = None
date: Optional[str] = None          # YYYY-MM-DD from fixture
```

Then inside `GWSignals.compute()`, find the loop that creates `SignalResult` objects (look for `r = SignalResult(` or the equivalent assignment). After the object is constructed — or as a keyword argument — pass `date=fix.get('date', '')`:

```python
# Wherever SignalResult is instantiated, add date= kwarg:
r = SignalResult(
    home=...,
    away=...,
    # ... all existing fields ...
    gate_block=gate_block,
    date=fix.get('date', ''),      # <-- add this line
)
```

- [ ] **Step 4: Add `date` to `_serialise()` in main.py**

In `api/main.py`, find `_serialise()` at the bottom of the file (around line 388). Add `'date'` to the return dict:

```python
def _serialise(r: SignalResult) -> Dict[str, Any]:
    return {
        'home': r.home, 'away': r.away,
        'market': r.market, 'odds': r.odds,
        'model_p': r.model_p, 'ev_pct': r.ev_pct,
        'tier': r.tier, 'kelly_stake': r.kelly_stake,
        'lambda_home': r.lambda_home, 'lambda_away': r.lambda_away,
        'gate_block': r.gate_block,
        'date': r.date,             # <-- add this line
    }
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
python -m pytest tests/test_signal_engine.py::test_signal_result_has_date -v 2>&1 | head -30
```

Expected: `PASSED`

- [ ] **Step 6: Smoke-test the API endpoint locally**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
uvicorn api.main:app --reload --port 8000 &
sleep 3
curl -s http://localhost:8000/api/signals | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0].get('date','MISSING') if d else 'EMPTY')"
kill %1
```

Expected: prints a date string like `2026-05-10` (or `EMPTY` if no fixtures loaded — not `MISSING`).

- [ ] **Step 7: Commit**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
git add api/signal_engine.py api/main.py tests/test_signal_engine.py
git commit -m "feat: add date field to SignalResult and /api/signals response"
```

---

### Task 2: Update globals.css — design tokens + new component classes

**Files:**
- Modify: `public/static/css/globals.css` — add `--blue` token, fix `body`/`.content`/`.statusbar` rules, append all new layout + component classes

- [ ] **Step 1: Write the failing test (DOM structure check)**

Create `tests/test_css_tokens.py`:

```python
# tests/test_css_tokens.py
import re
from pathlib import Path

CSS = Path("public/static/css/globals.css").read_text()


def test_blue_token_defined():
    assert "--blue:" in CSS, "--blue token must be defined in :root"


def test_elev_card_class_defined():
    assert ".elev-card" in CSS


def test_feed_row_wrap_class_defined():
    assert ".feed-row-wrap" in CSS


def test_expand_panel_class_defined():
    assert ".expand-panel" in CSS


def test_gate_chip_class_defined():
    assert ".gate-chip" in CSS
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
python -m pytest tests/test_css_tokens.py -v 2>&1 | head -30
```

Expected: multiple `FAILED` — classes don't exist yet.

- [ ] **Step 3: Add `--blue` token to `:root`**

Open `public/static/css/globals.css`. In the `:root { … }` block, add after `--red`:

```css
--blue:      #60A5FA;
```

- [ ] **Step 4: Fix `body` rule**

Find the `body { … }` block. Change:
```css
/* BEFORE */
min-width: 960px;
overflow-x: auto;

/* AFTER */
min-width: 960px;
overflow: hidden;
```

- [ ] **Step 5: Fix `.content` rule**

Find `.content { … }`. Replace its contents so the block reads:

```css
.content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
```

(Remove any existing `padding` and `overflow-y` declarations from this block.)

- [ ] **Step 6: Fix `.statusbar` rule**

Find `.statusbar { … }`. Ensure it reads:

```css
.statusbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 32px;
  gap: 24px;
  border-top: 1px solid var(--surface-2);
  font-size: 11px;
  color: var(--text-2);
  flex-shrink: 0;
}
```

- [ ] **Step 7: Append all new component classes**

Append the following block verbatim to the end of `public/static/css/globals.css`:

```css
/* ── Signal Board Redesign ─────────────────────────────────────── */

/* Layout */
.elev-section {
  flex-shrink: 0;
  padding: 20px 32px 0;
}

.elev-section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .08em;
  color: var(--text-2);
  text-transform: uppercase;
}

.elev-section-header .elev-count {
  color: var(--gold);
  font-weight: 600;
}

.elev-cards-row {
  display: flex;
  gap: 16px;
}

.feed-section {
  flex: 1;
  overflow-y: auto;
  padding: 20px 32px 8px;
}

/* Statusbar items */
.sb-group {
  display: flex;
  align-items: center;
  gap: 16px;
}

.sb-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sb-label {
  color: var(--text-2);
  font-size: 11px;
}

.sb-val {
  font-size: 12px;
  font-weight: 600;
  color: #e5e7eb;
}

.sb-val.gold { color: var(--gold); }
.sb-val.green { color: var(--green); }

.sb-sep {
  width: 1px;
  height: 14px;
  background: var(--surface-2);
}

/* ELEV card */
.elev-card {
  flex: 1;
  background: var(--surface);
  border: 1px solid var(--surface-2);
  border-radius: 10px;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.ec-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.ec-match {
  font-size: 14px;
  font-weight: 700;
  color: #e5e7eb;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 60%;
}

.ec-meta {
  font-size: 11px;
  color: var(--text-2);
  margin-top: 2px;
}

.ec-kickoff {
  font-size: 11px;
  color: var(--text-2);
  text-align: right;
  white-space: nowrap;
}

.ec-ev-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}

.ec-ev-big {
  font-size: 28px;
  font-weight: 800;
  color: var(--gold);
  line-height: 1;
}

.ec-ev-label {
  font-size: 9px;
  color: var(--text-2);
  letter-spacing: .06em;
  text-transform: uppercase;
  margin-bottom: 4px;
}

.ec-prob-block {
  text-align: right;
}

.ec-prob-val {
  font-size: 20px;
  font-weight: 700;
  color: var(--green);
  line-height: 1;
}

.ec-prob-label {
  font-size: 9px;
  color: var(--text-2);
  letter-spacing: .06em;
  text-transform: uppercase;
  margin-top: 2px;
}

/* Edge bar (shared by ELEV card and expand panel) */
.edge-bar-wrap {
  background: rgba(255,255,255,.04);
  border-radius: 6px;
  padding: 10px 12px;
}

.edge-bar-label {
  font-size: 10px;
  color: var(--text-2);
  text-transform: uppercase;
  letter-spacing: .06em;
  margin-bottom: 8px;
  display: flex;
  justify-content: space-between;
}

.edge-bar-label .pp-edge {
  color: var(--green);
  font-weight: 700;
}

.edge-bar-track {
  position: relative;
  height: 8px;
  background: var(--surface-2);
  border-radius: 4px;
  overflow: visible;
}

.edge-bar-fill {
  height: 100%;
  background: var(--green);
  border-radius: 4px;
  transition: width .4s ease;
}

.edge-bar-marker {
  position: absolute;
  top: -3px;
  width: 2px;
  height: 14px;
  background: #fff;
  border-radius: 1px;
  transform: translateX(-50%);
}

.edge-bar-ticks {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 10px;
  color: var(--text-2);
}

/* Data cells row (λH, λA, odds, edge) */
.ec-data-row {
  display: flex;
  gap: 8px;
}

.ec-data-cell {
  flex: 1;
  background: var(--surface-2);
  border-radius: 6px;
  padding: 6px 8px;
  text-align: center;
}

.ec-data-cell .dc-label {
  font-size: 9px;
  color: var(--text-2);
  text-transform: uppercase;
  letter-spacing: .05em;
}

.ec-data-cell .dc-val {
  font-size: 13px;
  font-weight: 700;
  color: #e5e7eb;
  margin-top: 2px;
}

.dc-val.green { color: var(--green); }

/* Gate chips */
.gate-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.gate-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 99px;
  border: 1px solid;
}

.gate-chip.pass {
  color: var(--green);
  border-color: rgba(34,197,94,.3);
  background: rgba(34,197,94,.08);
}

.gate-chip.warn {
  color: var(--gold);
  border-color: rgba(201,168,76,.3);
  background: rgba(201,168,76,.08);
}

.gate-chip.fail {
  color: var(--red);
  border-color: rgba(239,68,68,.3);
  background: rgba(239,68,68,.08);
}

/* ELEV card footer */
.ec-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 4px;
  border-top: 1px solid var(--surface-2);
}

.ec-kelly {
  font-size: 12px;
  color: var(--text-2);
}

.ec-kelly span {
  color: #e5e7eb;
  font-weight: 600;
}

/* Feed section */
.feed-group-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0 6px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .08em;
  color: var(--text-2);
  text-transform: uppercase;
}

.feed-group-header .fg-count {
  color: var(--text-2);
  font-weight: 500;
}

.feed-group-header .fg-line {
  flex: 1;
  height: 1px;
  background: var(--surface-2);
}

/* Feed row wrapper */
.feed-row-wrap {
  border-radius: 8px;
  margin-bottom: 4px;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid transparent;
  transition: border-color .15s;
}

.feed-row-wrap:hover {
  border-color: var(--surface-2);
}

.feed-row-wrap.tier-bet {
  background: rgba(34,197,94,.025);
}

.feed-row-wrap.tier-sim,
.feed-row-wrap.tier-no,
.feed-row-wrap.tier-elev-feed {
  opacity: .55;
}

.feed-row-wrap.tier-sim:hover,
.feed-row-wrap.tier-no:hover,
.feed-row-wrap.tier-elev-feed:hover {
  opacity: 1;
}

/* Feed row collapsed grid */
.feed-row {
  display: grid;
  grid-template-columns: 38px 1fr 72px 44px 44px 56px 60px 20px;
  align-items: center;
  gap: 0;
  padding: 10px 12px;
  font-size: 12px;
}

.f-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 18px;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: .04em;
}

.f-badge.elev { background: rgba(201,168,76,.15); color: var(--gold); }
.f-badge.bet  { background: rgba(34,197,94,.15);  color: var(--green); }
.f-badge.sim  { background: rgba(255,255,255,.06); color: var(--text-2); }
.f-badge.no   { background: rgba(239,68,68,.1);   color: var(--red); }

.f-match {
  overflow: hidden;
}

.f-match-name {
  font-size: 12px;
  font-weight: 600;
  color: #e5e7eb;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.f-match-sub {
  font-size: 10px;
  color: var(--text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.f-lambda {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  font-size: 10px;
  color: var(--text-2);
  gap: 1px;
}

.f-lambda span {
  color: #e5e7eb;
  font-weight: 600;
}

.f-prob, .f-odds, .f-ev, .f-kelly {
  text-align: right;
  font-size: 12px;
  font-weight: 600;
  color: #e5e7eb;
}

.f-ev { color: var(--gold); }

.f-chevron {
  text-align: right;
  color: var(--text-2);
  font-size: 14px;
  transition: transform .2s;
}

.feed-row-wrap.expanded .f-chevron {
  transform: rotate(90deg);
}

/* Expand panel */
.expand-panel {
  max-height: 0;
  overflow: hidden;
  transition: max-height .25s ease;
  background: rgba(255,255,255,.02);
  border-top: 1px solid transparent;
}

.feed-row-wrap.expanded .expand-panel {
  max-height: 360px;
  border-top-color: var(--surface-2);
}

.expand-inner {
  padding: 14px 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Expand footer (BET/ELEV only) */
.expand-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 8px;
  border-top: 1px solid var(--surface-2);
}

.expand-kelly {
  font-size: 12px;
  color: var(--text-2);
}

.expand-kelly span {
  color: #e5e7eb;
  font-weight: 600;
}

/* Log Bet button */
.btn-log-bet {
  background: var(--gold);
  color: #0d0f13;
  border: none;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: opacity .15s;
}

.btn-log-bet:hover { opacity: .85; }
```

- [ ] **Step 8: Run test to verify it passes**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
python -m pytest tests/test_css_tokens.py -v
```

Expected: all `PASSED`

- [ ] **Step 9: Commit**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
git add public/static/css/globals.css tests/test_css_tokens.py
git commit -m "feat: add signal board redesign CSS classes and --blue token"
```

---

### Task 3: Rewrite index.html — Focus+Feed layout

**Files:**
- Modify: `public/index.html` — full rewrite of the `<main class="content">` block and statusbar IDs; keep sidebar, topbar, Log Bet modal unchanged

- [ ] **Step 1: Write the failing test**

```python
# tests/test_html_structure.py
from pathlib import Path
from html.parser import HTMLParser


class IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.classes = set()

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if 'id' in attrs_dict:
            self.ids.add(attrs_dict['id'])
        if 'class' in attrs_dict:
            for cls in attrs_dict['class'].split():
                self.classes.add(cls)


HTML = Path("public/index.html").read_text()
collector = IdCollector()
collector.feed(HTML)


def test_elev_section_present():
    assert "elev-section" in collector.classes


def test_feed_section_present():
    assert "feed-section" in collector.classes


def test_statusbar_ids_present():
    for expected_id in ("sb-gw", "sb-fixture-count", "sb-avg-ev", "sb-avg-p", "sb-kelly", "sb-bankroll"):
        assert expected_id in collector.ids, f"Missing statusbar id: {expected_id}"


def test_log_bet_modal_present():
    assert "log-bet-modal" in collector.ids
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
python -m pytest tests/test_html_structure.py -v 2>&1 | head -30
```

Expected: failures for `elev-section`, `feed-section`, statusbar IDs.

- [ ] **Step 3: Rewrite `<main class="content">` and the statusbar**

Replace the existing `<main class="content"> … </main>` block in `public/index.html` with:

```html
<main class="content">
  <!-- ELEV strip -->
  <section class="elev-section" id="elev-section">
    <div class="elev-section-header">
      <span>Elevated Signals</span>
      <span class="elev-count" id="elev-count">0 signals</span>
      <div class="fg-line"></div>
    </div>
    <div class="elev-cards-row" id="elev-cards-row"></div>
  </section>

  <!-- Feed -->
  <section class="feed-section" id="feed-section">
    <div id="feed-bet-header" class="feed-group-header" style="display:none">
      <span>BET</span>
      <span class="fg-count" id="feed-bet-count"></span>
      <div class="fg-line"></div>
    </div>
    <div id="feed-bet"></div>

    <div id="feed-sim-header" class="feed-group-header" style="display:none">
      <span>SIM / NO</span>
      <span class="fg-count" id="feed-sim-count"></span>
      <div class="fg-line"></div>
    </div>
    <div id="feed-sim"></div>
  </section>
</main>
```

Then replace the existing `<footer class="statusbar"> … </footer>` with:

```html
<footer class="statusbar">
  <div class="sb-group">
    <div class="sb-item">
      <span class="sb-label">GW</span>
      <span class="sb-val" id="sb-gw">—</span>
    </div>
    <div class="sb-sep"></div>
    <div class="sb-item">
      <span class="sb-label">Fixtures</span>
      <span class="sb-val" id="sb-fixture-count">—</span>
    </div>
  </div>
  <div class="sb-group">
    <div class="sb-item">
      <span class="sb-label">Avg EV</span>
      <span class="sb-val gold" id="sb-avg-ev">—</span>
    </div>
    <div class="sb-sep"></div>
    <div class="sb-item">
      <span class="sb-label">Avg Prob</span>
      <span class="sb-val green" id="sb-avg-p">—</span>
    </div>
    <div class="sb-sep"></div>
    <div class="sb-item">
      <span class="sb-label">Total Kelly</span>
      <span class="sb-val" id="sb-kelly">—</span>
    </div>
    <div class="sb-sep"></div>
    <div class="sb-item">
      <span class="sb-label">Bankroll</span>
      <span class="sb-val" id="sb-bankroll">—</span>
    </div>
  </div>
</footer>
```

Keep the Log Bet modal (`<div id="log-bet-modal" …>`) exactly as-is.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
python -m pytest tests/test_html_structure.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
git add public/index.html tests/test_html_structure.py
git commit -m "feat: rewrite index.html with Focus+Feed layout and statusbar IDs"
```

---

### Task 4: Rewrite signals.js — render engine + accordion

**Files:**
- Modify: `public/static/js/signals.js` — full rewrite; replaces all existing functions with `renderElevCard`, `renderFeedRow`, `toggleRow`, `parseGates`, `renderEdgeBar`, `renderDataCells`, `renderGateChips`, `formatKickoff`, `loadSignals`, `openLogBetModal`

- [ ] **Step 1: Write the failing test (DOM render check)**

```python
# tests/test_signals_js.py
"""
Structural smoke-tests: verify the new signals.js exports the expected
function names and does not reference old identifiers.
"""
from pathlib import Path
import re

JS = Path("public/static/js/signals.js").read_text()


def test_render_elev_card_defined():
    assert "function renderElevCard" in JS or "renderElevCard" in JS


def test_render_feed_row_defined():
    assert "function renderFeedRow" in JS or "renderFeedRow" in JS


def test_toggle_row_defined():
    assert "function toggleRow" in JS or "toggleRow" in JS


def test_parse_gates_defined():
    assert "function parseGates" in JS or "parseGates" in JS


def test_render_edge_bar_defined():
    assert "function renderEdgeBar" in JS or "renderEdgeBar" in JS


def test_open_log_bet_modal_uses_data_idx():
    # New signature: openLogBetModal(idxStr) looks up _signals[parseInt(idxStr)]
    assert "_signals[" in JS


def test_no_old_elev_grid_reference():
    # The old .elev-grid container no longer exists
    assert "elev-grid" not in JS
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
python -m pytest tests/test_signals_js.py -v 2>&1 | head -30
```

Expected: most tests fail (old function names / old references).

- [ ] **Step 3: Write the new signals.js**

Replace the entire content of `public/static/js/signals.js` with the following:

```javascript
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

  // Feed rows from ELEV tier get a dimmed style but still appear
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

  // Sort order: ELEV → BET → SIM → NO; within group sort EV desc
  const ORDER = { ELEV: 0, BET: 1, SIM: 2, NO: 3 };
  const sorted = [...signals].sort((a, b) => {
    const td = (ORDER[a.tier] || 0) - (ORDER[b.tier] || 0);
    return td !== 0 ? td : b.ev_pct - a.ev_pct;
  });

  // Build index map so cards reference position in `sorted`
  // (globalIdx used by openLogBetModal)
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

  // Feed — SIM/NO group (includes ELEV as compact rows too)
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
python -m pytest tests/test_signals_js.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
git add public/static/js/signals.js tests/test_signals_js.py
git commit -m "feat: rewrite signals.js with Focus+Feed render engine and accordion"
```

---

### Task 5: Manual smoke test

**Files:** No code changes — verification only.

- [ ] **Step 1: Start the dev server**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
uvicorn api.main:app --reload --port 8000
```

- [ ] **Step 2: Open the board and verify ELEV strip**

Open `http://localhost:8000` in a browser.

Check:
- If any ELEV signals exist → horizontal card strip appears at the top
- Cards fill the full width (`flex:1`) regardless of count
- Each card shows: match name, market + odds, EV% (gold big number), model prob (green), edge bar with green fill and white marker, λH/λA/model-odds/edge cells, 4 gate chips, Kelly + LOG BET button
- If zero ELEV signals → ELEV section is hidden

- [ ] **Step 3: Verify feed groups**

Check:
- BET group header appears (or is hidden if no BET signals)
- SIM/NO group header appears
- Feed rows are compact 8-column grid: badge, match+market+kickoff, λ stacked, prob%, odds, EV, Kelly, chevron
- BET rows have subtle green tint; SIM/NO rows are dimmed

- [ ] **Step 4: Test accordion expand**

Click a feed row:
- Expanded row reveals: edge bar, data cells, gate chips
- BET row shows LOG BET button in footer; SIM/NO does not
- Click a second row → first row collapses automatically
- Click the same row again → it collapses

- [ ] **Step 5: Verify statusbar**

Bottom bar shows: GW · Fixtures · Avg EV (gold) · Avg Prob (green) · Total Kelly · Bankroll

- [ ] **Step 6: Test Log Bet modal**

Click LOG BET on an ELEV card or expanded BET row:
- Modal opens with pre-filled fields: home, away, market, date, tier, model EV, model prob, model odds, actual odds, stake
- Close button dismisses modal

- [ ] **Step 7: Commit final verification note**

```bash
cd /Users/avi/Downloads/Claude/Code/POISSON-EDGE
git commit --allow-empty -m "chore: smoke test passed — signal board redesign complete"
```

---

## Self-Review

### Spec coverage check

| Spec requirement | Task |
|---|---|
| ELEV section with `flex:1` cards | Task 3 (HTML), Task 4 (renderElevCard) |
| Hide ELEV section when zero ELEV signals | Task 4 (`renderBoard`) |
| Feed sorted ELEV→BET→SIM→NO, EV desc within group | Task 4 (`renderBoard` sort) |
| Feed row 8-column grid | Task 2 (CSS `.feed-row`), Task 4 (`renderFeedRow`) |
| BET row green tint; SIM/NO dimmed | Task 2 (CSS `.tier-bet`, `.tier-sim`) |
| Accordion — only one row open at a time | Task 4 (`toggleRow`) |
| Edge bar: green fill to model_p, white marker at implied_p | Task 4 (`renderEdgeBar`) |
| `implied_p = (1/odds)*100` client-side | Task 4 (`renderEdgeBar`, `renderDataCells`) |
| Gate chips 4 states pass/warn/fail | Task 4 (`parseGates`, `renderGateChips`) |
| `gate_block` null → all pass | Task 4 (`parseGates`) |
| Log Bet button only on BET + ELEV | Task 4 (`renderFeedRow` `isBettable`, ELEV card footer) |
| Statusbar: GW · Fixtures · Avg EV · Avg Prob · Total Kelly · Bankroll | Task 3 (HTML IDs), Task 4 (`updateStatusbar`) |
| Bankroll from `/api/bankroll` | Task 4 (`loadSignals`) |
| Date field in API response | Task 1 |
| `--blue` token added | Task 2 |
| `body overflow:hidden` | Task 2 |
| `.content` flex column, no padding | Task 2 |
| `.statusbar` 48px | Task 2 |
| No changes to `api/` beyond date field | ✓ only Task 1 touches API |

All spec requirements covered. No placeholders. Type/function names consistent across tasks.
