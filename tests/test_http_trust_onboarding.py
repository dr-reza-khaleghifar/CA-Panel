"""HTTP trust onboarding exposes only the static guide, its local helper and public Root CA files.

The HTTP listener must never expose login, API, MFA, issuance or private-key material.
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


def test_http_port_80_serves_only_guide_assets_and_public_root_downloads():
    block = trust_block()
    assert block.count("method GET HEAD") == 3
    assert "path /downloads/ca-panel-root-ca.pem /downloads/ca-panel-root-ca.cer" in block
    assert "path /trust.js" in block
    assert "path /\n" in block
    assert "/root-ca.pem" not in block
    assert "root * /srv/onboarding" in block
    assert "file_server" in block
    assert "respond" in block and "404" in block
    assert "reverse_proxy" not in block
    assert "redir" not in block
    for forbidden in ("api:8000", "api/", "login.html", "password", "issuer-key.pem",
                      "privkey.pem", "secrets/offline", "/.env"):
        assert forbidden not in block
    assert "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'" in block
    assert "X-Frame-Options" in block
    assert "no-store" in block
    assert "auto_https disable_redirects" in (ROOT / "Caddyfile.private").read_text("utf-8")


def test_compose_mounts_only_public_guide_assets_and_root_certificate_files():
    compose = (ROOT / "compose.yaml").read_text("utf-8")
    private = compose.split("\n  caddy-private:", 1)[1].split("\n  caddy:", 1)[0]
    assert '${PANEL_HTTP_BIND_IP:-0.0.0.0}:80:80' in private
    assert "./app/static/trust.html:/srv/onboarding/index.html:ro" in private
    assert "./app/static/trust.js:/srv/onboarding/trust.js:ro" in private
    assert "/root-cert.pem:/srv/onboarding/ca-panel-root-ca.pem:ro" in private
    assert "/ca-panel-root-ca.cer:/srv/onboarding/ca-panel-root-ca.cer:ro" in private
    assert ":/srv/onboarding/issuer-key.pem" not in private
    assert ":/srv/onboarding/.env" not in private


def test_http_page_is_persian_read_only_trust_guide_with_current_ca_metadata():
    page = (ROOT / "app/static/trust.html").read_text("utf-8")
    assert 'lang="fa"' in page and 'dir="rtl"' in page
    assert '<style>' in page and '</style>' in page
    assert 'src="/trust.js"' in page
    assert 'href="/downloads/ca-panel-root-ca.pem"' in page
    assert 'href="/downloads/ca-panel-root-ca.cer"' in page
    assert "CA-Panel Root CA" in page
    assert "Pardis AI Innovation" in page
    assert "RSA · 4096 bit" in page
    assert "SHA256 with RSA" in page
    assert "29 Oct 2036" in page
    assert "0E:3B:D2:5A:45:8A:0A:7E:48:5F:0C:2F:F1:BD:8A:67:59:6A:B2:47:D7:74:D2:64:31:D8:3C:44:1A:12:A6:06" in page
    assert "اثر انگشت" in page and "مستقل" in page
    assert "Trusted Root Certification Authorities" in page
    assert re.search(r"<form\b", page, re.I) is None
    assert re.search(r"<input\b[^>]*type=[\"']password", page, re.I) is None
    assert len(re.findall(r"<script\b", page, re.I)) == 1
    assert re.search(r"<script[^>]*\bsrc=[\"']/trust\.js", page, re.I)
    assert "document.execCommand(\"copy\")" not in page  # Clipboard fallback lives in the local helper asset.
    assert 'src="http://' not in page and 'href="http://' not in page
    for platform in ("windows", "macos", "ios", "android", "linux", "fedora",
                     "arch", "chromeos", "browsers", "java", "other"):
        assert f'id="{platform}"' in page
    assert "certutil -hashfile ca-panel-root-ca.cer SHA256" in page
    assert "openssl x509 -in ca-panel-root-ca.pem" in page


def test_bundled_https_proxies_overwrite_untrusted_forwarded_for():
    for filename in ("Caddyfile", "Caddyfile.private"):
        config = (ROOT / filename).read_text(encoding="utf-8")
        assert "header_up X-Forwarded-For {remote_host}" in config

    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert 'TRUST_PROXY_HEADERS: "${TRUST_PROXY_HEADERS:-1}"' in compose
