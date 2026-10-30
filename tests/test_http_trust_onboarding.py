"""HTTP trust onboarding must never expose the private issuance interface.

These tests enforce GET/HEAD / ONLY and no downloads, including the public root.
A separate Caddy integration test exercises actual HTTP request behavior.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def trust_block():
    config = (ROOT / "Caddyfile.private").read_text(encoding="utf-8")
    marker = "http://{$PANEL_DOMAIN} {"
    assert config.count(marker) == 1
    return config.split(marker, 1)[1]


def test_http_port_80_serves_only_one_static_guide():
    block = trust_block()
    assert "method GET HEAD" in block
    assert "path /\n" in block
    assert "path / /trust.css" not in block
    assert "/root-ca.pem" not in block
    assert "root * /srv/onboarding" in block
    assert "file_server" in block
    assert "respond" in block and "404" in block
    assert "reverse_proxy" not in block
    assert "redir" not in block
    for forbidden in ("api:8000", "api/", "login.html", "password", "issuer-key.pem",
                      "privkey.pem", "secrets/offline", "/.env"):
        assert forbidden not in block
    assert "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src https://{$PANEL_DOMAIN}" in block
    assert "X-Frame-Options" in block
    assert "no-store" in block
    assert "auto_https disable_redirects" in (ROOT / "Caddyfile.private").read_text("utf-8")


def test_compose_mounts_only_one_page_on_http():
    compose = (ROOT / "compose.yaml").read_text("utf-8")
    private = compose.split("\n  caddy-private:", 1)[1].split("\n  caddy:", 1)[0]
    assert '${PANEL_HTTP_BIND_IP:-0.0.0.0}:80:80' in private
    assert "./app/static/trust.html:/srv/onboarding/index.html:ro" in private
    assert ":/srv/onboarding/trust.css" not in private
    assert ":/srv/onboarding/root-ca.pem" not in private
    # Mount only the guide. No certificate, assets, .env or any CA key.
    assert ":/srv/onboarding/issuer-key.pem" not in private
    assert ":/srv/onboarding/.env" not in private


def test_http_page_warns_users_and_cannot_collect_credentials():
    page = (ROOT / "app/static/trust.html").read_text("utf-8")
    assert 'lang="fa"' in page and 'dir="rtl"' in page
    assert 'href="/root-ca.pem"' not in page
    assert '<style>' in page and '</style>' in page
    assert 'href="/trust.css"' not in page
    assert 'دانلود ارائه نمی‌کند' in page
    assert "https://ca1.iravand.ir/login" in page
    assert "اثر انگشت" in page and "مستقل" in page
    assert "HTTP" in page and "MFA" in page
    assert "Trusted Root Certification Authorities" in page
    assert re.search(r"<form\b|<input\b", page, re.I) is None
    assert len(re.findall(r"<script\b", page, re.I)) == 1
    assert re.search(r"<script[^>]*\bsrc=", page, re.I) is None
    assert "document.documentElement.classList.add('checking')" in page
    assert "new Image()" in page
    assert "/static/favicon.svg?trust_probe=" in page
    assert "image.onload" in page and "image.onerror" in page
    assert "window.location.replace(https + '/')" in page
    assert "6500" in page
    assert "probe-failed" in page
    assert 'http://' not in page
    assert 'certutil -decode' in page  # DER file hash, not misleading PEM file hash.
