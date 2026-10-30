"""HTTP trust onboarding must never expose the private issuance interface.

These tests enforce static-only routing and independent fingerprint verification
copy. A separate Caddy integration test exercises actual request behavior.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def trust_block():
    config = (ROOT / "Caddyfile.private").read_text(encoding="utf-8")
    marker = "http://{$PANEL_DOMAIN} {"
    assert config.count(marker) == 1
    return config.split(marker, 1)[1]


def test_http_port_80_serves_only_static_trust_assets():
    block = trust_block()
    assert "method GET HEAD" in block
    assert "path / /trust.css /root-ca.pem" in block
    assert "root * /srv/onboarding" in block
    assert "file_server" in block
    assert "respond" in block and "404" in block
    assert "reverse_proxy" not in block
    assert "redir" not in block
    for forbidden in ("api:8000", "api/", "login.html", "password", "issuer-key.pem",
                      "privkey.pem", "secrets/offline", "/.env"):
        assert forbidden not in block
    assert "default-src 'none'; style-src 'self'" in block
    assert "X-Frame-Options" in block
    assert "no-store" in block
    assert "auto_https disable_redirects" in (ROOT / "Caddyfile.private").read_text("utf-8")


def test_compose_mounts_only_public_root_and_static_page_on_http():
    compose = (ROOT / "compose.yaml").read_text("utf-8")
    private = compose.split("\n  caddy-private:", 1)[1].split("\n  caddy:", 1)[0]
    assert '${PANEL_HTTP_BIND_IP:-0.0.0.0}:80:80' in private
    assert "./app/static/trust.html:/srv/onboarding/index.html:ro" in private
    assert "./app/static/trust.css:/srv/onboarding/trust.css:ro" in private
    assert "${CA_ROOT_CERT_FILE:-root-cert.pem}:/srv/onboarding/root-ca.pem:ro" in private
    # Restrict HTTP root to public cert; never mount the .env or issuer private key.
    assert ":/srv/onboarding/issuer-key.pem" not in private
    assert ":/srv/onboarding/.env" not in private


def test_http_page_warns_users_and_cannot_collect_credentials():
    page = (ROOT / "app/static/trust.html").read_text("utf-8")
    assert 'lang="fa"' in page and 'dir="rtl"' in page
    assert 'href="/root-ca.pem"' in page
    assert "https://ca1.iravand.ir/login" in page
    assert "اثر انگشت" in page and "مستقل" in page
    assert "HTTP" in page and "MFA" in page
    assert "Trusted Root Certification Authorities" in page
    assert re.search(r"<form\b|<input\b|<script\b", page, re.I) is None
    assert 'http://' not in page
    assert 'certutil -decode' in page  # DER file hash, not misleading PEM file hash.
