# Signal Board Redesign — Design Spec

**Date:** 2026-04-27  
**Status:** Approved  
**Mockup:** `.superpowers/brainstorm/63516-1777277428/content/full-mockup-c5.html`

---

## Problem

The existing signal board (`public/index.html` + `public/static/js/signals.js`) is a flat, unsorted list showing only tier badge, match name, and EV. It exposes none of the model context that makes a signal actionable:

- No lambdas (λH / λA)
- No Pinnacle implied probability vs model probability comparison
- No gate chip status
- No grouping by tier
- No kickoff time
- No odds in context

Result: the board cannot be used to make a betting decision without opening a spreadsheet.

---

## Design Direction

**Focus + Feed** (option C, mockup c5).

- **Top strip:** ELEV cards in a horizontal row. Each card is `flex:1` so cards auto-fill the full width regardless of count.
- **Bottom area:** Scrollable feed of all signals, grouped BET → SIM/NO, with expandable rows that reveal the same context as ELEV cards on click.

---

## Layout Structure

```
┌─ sidebar (56px) ─┬─────────────────── main ────────────────────────┐
│ PE logo          │  topbar: Signal Board · GW35  [Refresh]  ● Live  │
│ ⚡ (signals, on) │─────────────────────────────────────────────────│
│ ◈ (backtest)     │  ELEV section (flex-shrink:0)                    │
│ ↗ (stats)        │    ● ELEVATED SIGNALS ─────── 2 signals · EV≥15%│
│                  │    [card flex:1] [card flex:1] ...               │
│ λ (debug)        │─────────────────────────────────────────────────│
│                  │  feed-section (flex:1, overflow-y:auto)          │
│                  │    ▸ BET ────────────────────── 3 signals        │
│                  │      [expandable row] ›                          │
│                  │      [expandable row] ›                          │
│                  │    ↓ SIM / NO ──────────────── 4 signals        │
│                  │      [expandable row] ›                          │
│                  ├─────────────────────────────────────────────────│
│                  │  statusbar: GW · Fixtures · Avg EV · Prob ·      │
│                  │             Total Kelly · Bankroll               │
└──────────────────┴─────────────────────────────────────────────────┘
```

---

## ELEV Card

Each ELEV card (`tier === 'ELEV'`) renders as a full-context card:

```
┌────────────────────────────────────────┐
│ Match name              Sat 10 May     │
│ Market · Pinnacle @ odds  15:00 BST    │
│                                        │
│ EXPECTED VALUE                         │
│ +25.1%              68.4%              │
│                     MODEL PROB         │
│                                        │
│ ┌ MARKET IMPLIED VS MODEL  +39.0 pp ┐  │
│ │ [■■■■■■■■■■■■▏░░░░░░░░░░░░░░░░░] │  │
│ │ Pinnacle implied 29.4%  Model 68.4%│ │
│ └────────────────────────────────────┘ │
│                                        │
│ [λH 1.21] [λA 1.74] [odds 2.72] [+0.68]│
│                                        │
│ ✓ EV  ✓ Prob  ✓ Odds range  ✓ Model conf│
│                                        │
│ Kelly 25% · €7.50          [LOG BET]   │
└────────────────────────────────────────┘
```

**Fields required from `SignalResult`:**
| Field | Usage |
|---|---|
| `home`, `away` | Match name |
| `market` | Market label ("Home Win", "Away Win", "Draw") |
| `odds` | Pinnacle odds shown as `@ {odds}` |
| `ev_pct` | Big EV number |
| `model_p` | Model probability (%) |
| `lambda_home`, `lambda_away` | λH / λA cells |
| `kelly_stake` | Kelly stake (€) |
| `gate_block` | Gate chip pass/warn/fail states |
| `kickoff` from fixture | Date + time displayed as e.g. `Sat 10 May · 15:00 BST` |

**Edge bar logic:**
- `implied_p = (1 / odds) * 100`
- Green bar fills to `model_p %`
- Grey marker line positioned at `implied_p %`
- `pp_edge = model_p - implied_p`
- Label: `+{pp_edge.toFixed(1)} pp edge`

**Gate chips:** 4 chips, one per gate. States:
- `pass` (green `✓`): gate cleared
- `warn` (gold `⚠`): gate marginal
- `fail` (red `✗`): gate failed

Gate labels: **EV** · **Prob** · **Odds range** · **Model conf.**

The `gate_block` field from the API returns a dict or encoded string mapping gate names to states. Parse it to render chips. If `gate_block` is absent/null/empty, render all four as `pass`.

---

## Feed Row (collapsed)

All signals (BET, SIM, NO) render as compact rows in an 8-column grid:

```
grid-template-columns: 38px 1fr 72px 44px 44px 56px 60px 20px
  [badge] [match+market+kickoff] [λH/λA stacked] [prob] [odds] [EV] [Kelly] [›]
```

- BET rows: `background: rgba(34,197,94,0.025)` — subtle green tint
- SIM/NO rows: `opacity: 0.45` — de-emphasised
- Chevron `›` rotates 90° when row is expanded

---

## Feed Row (expanded)

Click anywhere on the row wrapper to toggle. **Accordion** — only one row open at a time; clicking a new row closes the previously open one.

Expanded panel reveals (same components as ELEV card, without the big EV/prob headline):

1. **Edge bar** — implied vs model probability track (identical logic to ELEV card)
2. **4-cell data row** — λH, λA, model odds, edge value
3. **Gate chips** — same chip logic as ELEV cards
4. **Footer** (BET tier only) — Kelly stake + Log Bet button

SIM and NO rows do **not** show a Log Bet button in the expanded panel.

---

## Statusbar

Fixed 48px bar at the bottom. Two groups:

**Left:** Gameweek label · Fixture count  
**Right:** Avg EV (gold) · Avg Prob (green) · Total Kelly · Bankroll

Bankroll value read from `/api/bankroll`. Kelly stake displayed as `€{X.XX}`.

---

## Files to Change

| File | Change |
|---|---|
| `public/index.html` | Full rewrite — new layout, ELEV strip, feed section, expandable rows, statusbar |
| `public/static/js/signals.js` | Full rewrite — `renderElevCard()`, `renderFeedRow()`, expand toggle, statusbar update |
| `public/static/css/globals.css` | Add new classes: `.elev-cards-row`, `.elev-card`, `.ec-*`, `.feed-row-wrap`, `.expand-panel`, `.gate-chip.*`, `.f-chevron` |

No changes to `api/` — the existing `/api/signals` and `/api/bankroll` endpoints already return all required fields.

---

## CSS Design Tokens (existing — do not change)

```css
--bg:        #0D0F13
--surface:   #13151A
--surface-2: #1A1D24
--gold:      #C9A84C
--green:     #22C55E
--blue:      #60A5FA
--red:       #EF4444
--text-2:    #6B7280
--text-3:    #374151
```

---

## Key Behavioural Rules

1. **ELEV cards only appear** when `tier === 'ELEV'`. If zero ELEV signals exist, hide the ELEV section entirely.
2. **Feed shows all tiers** including ELEV (as compact rows), sorted by EV descending within each tier group. Order: ELEV → BET → SIM → NO.
3. **Accordion expand** — clicking a row collapses any previously expanded row before opening the new one.
4. **Log Bet button** in feed only appears on BET and ELEV rows. Not on SIM or NO.
5. **Implied probability** computed client-side: `implied_p = (1 / odds) * 100`. Not returned by the API.
6. **Gate block parsing** — if `gate_block` is null/undefined/empty string, treat all four gates as pass.
7. **Bankroll** — fetched from `/api/bankroll` separately. Kelly fraction × bankroll = displayed stake.
8. **No ELEV signals** — if the ELEV strip would be empty, set `display:none` on `.elev-section`.

---

## Out of Scope for This Spec

- SUSPECT cap logic (EV > 60% flagging) — deferred
- Totals markets (o25/o35) display fix — deferred
- ELO correction for `aw` market — deferred
- Bankroll initialisation to €53 — deferred
- Backtest page redesign — separate spec

---

## Approval

Design approved by user on 2026-04-27. Mockup: `full-mockup-c5.html`.
