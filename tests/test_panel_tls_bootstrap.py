"""Local-only panel HTTPS bootstrap: no DNS API bypass and no Root private key."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from scripts.init_ca import create_ca
from scripts import issue_panel_tls


DOMAIN = "ca1.iravand.ir"


@pytest.fixture
def panel(tmp_path):
    create_ca(tmp_path / "secrets", b"strong-offline-test-password",
              b"strong-issuer-test-password")
    (tmp_path / ".env").write_text(
        "PANEL_DOMAIN=ca1.iravand.ir\n"
        "PANEL_TLS_HOST_DIR=./secrets/tls\n"
        "CA_ONLINE_HOST_DIR=./secrets/online\n"
        "CA_ROOT_CERT_FILE=root-cert.pem\n"
        "CA_ISSUER_KEY_FILE=issuer-key.pem\n"
        "CA_ISSUER_CERT_FILE=issuer-cert.pem\n"
        "CA_KEY_PASSWORD='strong-issuer-test-password'\n"
        "CERT_VALIDITY_DAYS=30\n"
        "SERVER_KEY_BITS=2048\n", encoding="utf-8",
    )
    return tmp_path


def test_local_bootstrap_issues_panel_leaf_without_dns_and_is_idempotent(panel):
    # No API or DNS client is ever touched.
    assert issue_panel_tls.ensure_panel_tls(panel) == "issued"
    tls = panel / "secrets" / "tls"
    assert {p.name for p in tls.iterdir()} == {"fullchain.pem", "privkey.pem"}
    assert tls.stat().st_mode & 0o077 == 0
    assert (tls / "privkey.pem").stat().st_mode & 0o077 == 0
    chain = (tls / "fullchain.pem").read_bytes()
    cert = x509.load_pem_x509_certificate(chain)
    issuer = x509.load_pem_x509_certificate(
        (panel / "secrets" / "online" / "issuer-cert.pem").read_bytes())
    assert chain == cert.public_bytes(serialization.Encoding.PEM) + issuer.public_bytes(serialization.Encoding.PEM)
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == DOMAIN
    assert cert.extensions.get_extension_for_class(
        x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName) == [DOMAIN]
    assert ExtendedKeyUsageOID.SERVER_AUTH in cert.extensions.get_extension_for_class(
        x509.ExtendedKeyUsage).value
    assert cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    assert cert.not_valid_after_utc > datetime.now(timezone.utc) + timedelta(days=29)
    private = (tls / "privkey.pem").read_bytes()
    assert b"BEGIN PRIVATE KEY" in private
    assert issue_panel_tls.ensure_panel_tls(panel) == "unchanged"
    assert private == (tls / "privkey.pem").read_bytes()


def test_bootstrap_requires_explicit_panel_domain(panel):
    env = panel / ".env"
    env.write_text(env.read_text().replace("PANEL_DOMAIN=ca1.iravand.ir\n", ""))
    with pytest.raises(ValueError, match="PANEL_DOMAIN"):
        issue_panel_tls.ensure_panel_tls(panel)
    assert not (panel / "secrets" / "tls").exists()


def test_bootstrap_refuses_foreign_or_mismatched_tls_key(panel):
    issue_panel_tls.ensure_panel_tls(panel)
    f = panel / "secrets" / "tls" / "privkey.pem"
    f.write_bytes(b"invalid private key")
    with pytest.raises(ValueError):
        issue_panel_tls.ensure_panel_tls(panel)
    assert f.read_bytes() == b"invalid private key"


def test_bootstrap_refuses_partial_tls_deployment(panel):
    tls = panel / "secrets" / "tls"
    tls.mkdir()
    (tls / "privkey.pem").write_bytes(b"mismatched key")
    with pytest.raises(ValueError, match="Only one HTTPS"):
        issue_panel_tls.ensure_panel_tls(panel)


def test_bootstrap_fails_wrong_password_without_writing_leaf(panel):
    env = panel / ".env"
    env.write_text(env.read_text().replace("strong-issuer-test-password",
                                           "definitely-incorrect-password"))
    with pytest.raises(ValueError, match="Cannot decrypt"):
        issue_panel_tls.ensure_panel_tls(panel)
    assert not (panel / "secrets" / "tls").exists()


def test_bootstrap_never_requires_dns_or_changes_certificate_request_handler():
    # Regression contract: only an administrative script issues this local
    # certificate; public issuance still invokes DNS ownership verification.
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "issue_panel_tls.py").read_text(encoding="utf-8")
    app = (root / "app" / "main.py").read_text(encoding="utf-8")
    assert "FastAPI(" not in script and "@app." not in script
    assert "PANEL_DOMAIN" in script
    assert "dns_checker" in app and "_ca-panel." in app
    assert "issue_panel_tls" not in app
