"""Navigation regression checks: real targets, accessible mobile drawer and no API changes."""
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import pytest

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


class NavParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.nav_links = []
        self._inside_nav = 0

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if data.get("id"):
            self.ids.add(data["id"])
        if tag == "nav" and "side-nav" in (data.get("class") or ""):
            self._inside_nav += 1
        if self._inside_nav and tag == "a":
            self.nav_links.append(data.get("href"))

    def handle_endtag(self, tag):
        if tag == "nav" and self._inside_nav:
            self._inside_nav -= 1


def test_menu_links_reference_real_sections():
    doc = NavParser()
    doc.feed((STATIC / "index.html").read_text(encoding="utf-8"))
    assert {"menu-toggle", "menu-close", "nav-backdrop", "sidebar", "faq"}.issubset(doc.ids)
    assert doc.nav_links == ["#overview", "#issue-workspace", "#how-it-works", "#faq", "#security"]
    assert all(href[1:] in doc.ids for href in doc.nav_links)


def test_navigation_behaviour_files_exist():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "/static/navigation.js?v=6" in html
    assert "/static/v5.css?v=5" in html
    assert "/static/v6.css?v=1" in html
    js = (STATIC / "navigation.js").read_text(encoding="utf-8")
    for hook in ["aria-expanded", "aria-current", "hashchange", "scrollIntoView",
                 "Escape", "nav-open", "resize", "setActive"]:
        assert hook in js
    css = (STATIC / "v5.css").read_text(encoding="utf-8")
    assert "@media(max-width:980px)" in css
    assert ".nav-open .sidebar" in css
    assert ".nav-backdrop" in css
    assert "prefers-reduced-motion:reduce" in css
    assert css.count("{") == css.count("}")


def test_navigation_javascript_syntax():
    if not shutil.which("node"):
        pytest.skip("Node.js not available")
    subprocess.run(["node", "--check", str(STATIC / "navigation.js")], check=True, timeout=15)


def test_navigation_interaction_contract():
    if not shutil.which("node"):
        pytest.skip("Node.js not available")
    subprocess.run(
        ["node", str(Path(__file__).with_name("navigation_behavior_check.js"))],
        check=True, timeout=15,
    )
