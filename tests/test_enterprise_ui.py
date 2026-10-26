"""Iran CA Center enterprise UI contract; no CA keys or network access."""
from __future__ import annotations

import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "static"


class Scan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.styles = []
        self.scripts = []
        self.links = []
        self.html_attrs = {}

    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if tag == "html":
            self.html_attrs = props
        if "id" in props:
            self.ids.append(props["id"])
        if tag == "link" and props.get("rel") == "stylesheet":
            self.styles.append(props.get("href"))
        if tag == "script":
            self.scripts.append(props.get("src"))
        if tag == "a":
            self.links.append(props.get("href"))


def test_brand_and_enterprise_dark_design_are_explicit():
    markup = (UI / "index.html").read_text("utf-8")
    style = (UI / "v6.css").read_text("utf-8")
    app = (UI / "app.js").read_text("utf-8")
    dom = Scan()
    dom.feed(markup)
    assert dom.html_attrs["lang"] == "fa" and dom.html_attrs["dir"] == "rtl"
    assert dom.html_attrs["data-theme"] == "dark"
    assert "گواهی دیجیتال ایران" in markup
    assert "Iran CA Center" in markup
    assert len(dom.ids) == len(set(dom.ids))
    assert any(h.startswith("/static/v6.css") for h in dom.styles)
    assert "/static/favicon.svg" in markup
    assert (UI / "favicon.svg").is_file()
    assert not any("http://" in (u or "") or "https://" in (u or "")
                   for u in dom.styles + dom.scripts)
    assert "id=\"theme-toggle\"" not in markup
    assert "localStorage" not in app
    assert "data-theme', 'dark'" in app
    assert "--page:#080e1a" in style
    assert "--primary:#7aafff" in style
    assert "@media(max-width:480px)" in style
    assert "prefers-reduced-motion:reduce" in style
    assert style.count("{") == style.count("}")


def test_dashboard_reports_only_measurable_status_and_preserves_dns_flow():
    html = (UI / "index.html").read_text("utf-8")
    js = (UI / "app.js").read_text("utf-8")
    for id in (
        "overview", "service-status", "transport-status",
        "dashboard-validity-days", "header-health", "issue-workspace",
        "domain-form", "dns-panel", "success-panel", "ca-root-fingerprint",
        "download-button", "toast",
    ):
        assert f'id="{id}"' in html
    assert "/api/system" in js
    assert "data.certificate_validity_days" in js
    assert "location.protocol === 'https:'" in js
    assert "api('/api/requests'" in js
    assert "'/verify'" in js
    assert "'/issue-server'" in js
    assert "safeURL(" in js
    assert "zipDeadlineMs" in js
    assert "data-copy=\"ca-root-fingerprint\"" in html
    # Do not claim the port is reachable or a certificate is publicly trusted.
    assert 'id="port-443-status"' not in html
    assert "document.title = data.display_name" not in js


def test_brand_defaults_are_not_ca_subject_rotation():
    config = (ROOT / "app" / "config.py").read_text("utf-8")
    template = (ROOT / ".env.example").read_text("utf-8")
    assert "CA_DISPLAY_NAME='گواهی دیجیتال ایران'" in template
    assert "CA_ORGANIZATION='Iran CA Center'" in template
    assert 'ca_display_name: str = "گواهی دیجیتال ایران"' in config
    assert "CA_ROOT_CN=CA-Panel Offline Root CA" in template
    assert "CA_ISSUER_CN=CA-Panel Online Issuing CA" in template


@pytest.mark.parametrize("name", ["app.js", "navigation.js"])
def test_frontend_javascript_parses(name):
    if not shutil.which("node"):
        pytest.skip("Node is not available")
    subprocess.run(["node", "--check", str(UI / name)], check=True, timeout=15)
