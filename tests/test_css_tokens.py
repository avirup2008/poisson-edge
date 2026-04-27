from pathlib import Path

CSS = Path("public/static/css/globals.css").read_text()

def test_blue_token_defined():
    assert "--blue:" in CSS

def test_elev_card_class_defined():
    assert ".elev-card" in CSS

def test_feed_row_wrap_class_defined():
    assert ".feed-row-wrap" in CSS

def test_expand_panel_class_defined():
    assert ".expand-panel" in CSS

def test_gate_chip_class_defined():
    assert ".gate-chip" in CSS
