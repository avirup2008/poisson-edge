from pathlib import Path

JS = Path("public/static/js/signals.js").read_text()

def test_render_elev_card_defined():
    assert "function renderElevCard" in JS

def test_render_feed_row_defined():
    assert "function renderFeedRow" in JS

def test_toggle_row_defined():
    assert "function toggleRow" in JS

def test_parse_gates_defined():
    assert "function parseGates" in JS

def test_render_edge_bar_defined():
    assert "function renderEdgeBar" in JS

def test_open_log_bet_modal_uses_signals_array():
    assert "_signals[" in JS

def test_no_old_elev_grid_reference():
    assert "elev-grid" not in JS
