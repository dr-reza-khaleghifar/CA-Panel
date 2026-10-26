"""Static, dependency-free regression checks for the Persian UI integration."""
from html.parser import HTMLParser
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.lang = None
        self.direction = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "html":
            self.lang = attrs.get("lang")
            self.direction = attrs.get("dir")


def test_ui_has_all_issue_and_download_controls():
    parser = Elements()
    parser.feed((STATIC / "index.html").read_text(encoding="utf8"))
    expected = {
        "domain-form", "domain", "domain-submit", "dns-panel",
        "dns-name", "dns-value", "verify-button", "issue-panel",
        "issue-button", "success-panel", "issued-domain",
        "download-button", "leaf-link", "fullchain-link",
        "issuer-link", "root-link", "certificate-expiry",
        "download-expiry", "challenge-expiry", "message",
        "overview", "service-status", "transport-status", "toast", "step-1", "step-2", "step-3",
    }
    assert expected.issubset(parser.ids)
    assert len(parser.ids) == len(set(parser.ids))
    assert (parser.lang, parser.direction) == ("fa", "rtl")


def test_ui_keeps_server_issuance_and_secure_download_contract():
    js = (STATIC / "app.js").read_text(encoding="utf8")
    css = (STATIC / "style.css").read_text(encoding="utf8")
    assert "/issue-server" in js
    assert "download_url" in js
    assert "localStorage.setItem(THEME_KEY" not in js
    assert "document.documentElement.setAttribute(\'data-theme\', \'dark\')" in js
    assert "displayTransportStatus()" in js
    assert "localStorage.setItem(THE_KEY" not in js
    assert "issuedLinks" in js
    assert "dns-value" in js
    assert "@media(max-width:480px)" in css
    assert "prefers-reduced-motion" in css
    assert "[data-theme=dark]" in css
