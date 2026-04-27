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
