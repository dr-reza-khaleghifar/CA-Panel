"""Static UI smoke checks independent of Docker, CA passphrases and external fonts."""
from html.parser import HTMLParser
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
REQUIRED_IDS = {
    "domain-form", "domain", "domain-submit", "dns-panel", "domain-panel",
    "issue-panel", "success-panel", "dns-name", "dns-value",
    "verify-button", "issue-button", "download-button", "leaf-link",
    "fullchain-link", "issuer-link", "root-link", "overview", "service-status", "toast", "message",
}


class UIParts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.styles = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.append(attributes["id"])
        if tag == "link" and attributes.get("rel") == "stylesheet":
            self.styles.append(attributes["href"])
        if tag == "script" and "src" in attributes:
            self.scripts.append(attributes["src"])


def test_persian_dashboard_dependencies_and_unique_ids():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    parser = UIParts()
    parser.feed(html)
    assert 'lang="fa"' in html and 'dir="rtl"' in html
    assert len(parser.ids) == len(set(parser.ids))
    assert REQUIRED_IDS.issubset(parser.ids)
    assert any(x.startswith("/static/v4.css") for x in parser.styles)
    assert any(x.startswith("/static/v6.css") for x in parser.styles)
    assert 'data-theme="dark"' in html and 'id="theme-toggle"' not in html
    assert "گواهی دیجیتال ایران" in html and "Iran CA Center" in html
    assert all(x.startswith("/static/") for x in parser.styles + parser.scripts)
    assert "fonts.googleapis.com" not in html


def test_local_persian_font_css_and_accessibility():
    css = (STATIC / "v4.css").read_text(encoding="utf-8")
    assert '@font-face' in css
    assert '/static/fonts/Vazirmatn.woff2' in css
    assert 'html[data-theme=dark]' in css
    assert 'prefers-reduced-motion:reduce' in css
    assert css.count("{") == css.count("}")
    assert (STATIC / "fonts" / "OFL.txt").exists()


def test_docker_font_install_requires_no_network_on_build():
    dockerfile = (STATIC.parents[1] / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY app ./app" in dockerfile
    assert "urllib.request.urlopen(" not in dockerfile
    assert "Vazirmatn.woff2" in (STATIC / "v4.css").read_text(encoding="utf-8")
    script = (STATIC.parents[1] / "scripts" / "install_font.py").read_text(encoding="utf-8")
    assert "EXPECTED_GIT_BLOB" in script
    assert "ssl.create_default_context()" in script
