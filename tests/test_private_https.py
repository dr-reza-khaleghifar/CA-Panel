"""Offline regression checks for the own-CA HTTPS :443 profile and ZIP provisioning.

These tests issue throwaway CA/leaf certificates under tmp_path; no private key,
external DNS or Docker daemon is touched.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.main import build_server_bundle, certificate_for_domain, load_issuer
from scripts.init_ca import create_ca
from scripts import setup_private_tls as https


DOMAIN = "ca1.iravand.ir"


def make_bundle(tmp_path: Path, *, domain: str = DOMAIN):
    create_ca(tmp_path / "secrets", b"root-password-very-long", b"issuer-password-very-long")
    signing_key, issuer, root = load_issuer(tmp_path / "secrets" / "online", "issuer-password-very-long")
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
        .sign(leaf_key, hashes.SHA256())
    )
    leaf = certificate_for_domain(
        domain, csr.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        signing_key, issuer,
    )
    key_pem = leaf_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    data = build_server_bundle(domain, key_pem, leaf, issuer, root)
    z = tmp_path / "bundle.zip"
    z.write_bytes(data)
    (tmp_path / ".env").write_text(
        "PANEL_DOMAIN=ca1.iravand.ir\n"
        "PANEL_TLS_HOST_DIR=./secrets/tls\n"
        "CA_ONLINE_HOST_DIR=./secrets/online\n"
        "CA_ROOT_CERT_FILE=root-cert.pem\n",
        encoding="utf-8",
    )
    return z


def test_private_tls_caddy_profile_and_manual_certificate_config():
    root = Path(__file__).resolve().parents[1]
    caddyfile = (root / "Caddyfile.private").read_text(encoding="utf-8")
    assert "https://{$PANEL_DOMAIN}" in caddyfile
    assert "tls /etc/caddy/tls/fullchain.pem /etc/caddy/tls/privkey.pem" in caddyfile
    assert "reverse_proxy api:8000" in caddyfile
    assert "auto_https disable_redirects" in caddyfile
    assert "tls internal" not in caddyfile
    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    assert 'profiles: ["private-tls"]' in compose
    assert "caddy-private:" in compose
    assert '"443:443"' in compose
    assert ":/etc/caddy/tls:ro" in compose
    assert "PANEL_TLS_HOST_DIR" in compose
    assert "secrets/tls" in (root / ".env.example").read_text(encoding="utf-8")


def test_verified_own_ca_zip_installs_leaf_and_key_only(tmp_path, monkeypatch):
    archive = make_bundle(tmp_path)
    monkeypatch.setattr(https, "ROOT", tmp_path)
    install_dir, domain = https.install_archive(archive)
    assert domain == DOMAIN
    assert install_dir == tmp_path / "secrets" / "tls"
    assert sorted(p.name for p in install_dir.iterdir()) == ["fullchain.pem", "privkey.pem"]
    assert (install_dir / "privkey.pem").read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----")
    assert b"PRIVATE KEY" not in (install_dir / "fullchain.pem").read_bytes()
    assert not (install_dir / "issuer-key.pem").exists()
    with pytest.raises(ValueError, match="already installed"):
        https.install_archive(archive)
    https.install_archive(archive, replace=True)


def test_wrong_hostname_fails_before_any_tls_write(tmp_path, monkeypatch):
    archive = make_bundle(tmp_path, domain="other.example.net")
    monkeypatch.setattr(https, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="Expected exactly one small file"):
        https.install_archive(archive)
    assert not (tmp_path / "secrets" / "tls").exists()


def test_bad_key_or_chain_fails_closed(tmp_path, monkeypatch):
    archive = make_bundle(tmp_path)
    monkeypatch.setattr(https, "ROOT", tmp_path)
    with zipfile.ZipFile(archive) as opened:
        contents = {name: opened.read(name) for name in opened.namelist()}
    # Correct format but wrong RSA private key: matching check must reject.
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    contents[DOMAIN + ".key"] = wrong_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    changed = tmp_path / "wrong-key.zip"
    with zipfile.ZipFile(changed, "w") as out:
        for name, data in contents.items():
            out.writestr(name, data)
    with pytest.raises(ValueError, match="Private key does not match"):
        https.install_archive(changed)
    assert not (tmp_path / "secrets" / "tls" / "privkey.pem").exists()


def test_private_https_setup_rejects_unsafe_hostnames():
    for name in ("localhost", "ca1.*.org", "../root", "CA1.IRAVAND.IR", "127.0.0.1"):
        with pytest.raises(ValueError):
            https.safe_domain(name)
    assert https.safe_domain(DOMAIN) == DOMAIN
