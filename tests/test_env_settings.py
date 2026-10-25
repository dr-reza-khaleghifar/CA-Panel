"""Configuration contract: env loading, policy enforcement, real X.509 identity.

Never put CA private keys or passwords into the public /api/system JSON payload.
"""
from __future__ import annotations

import io
import time
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.main import Settings, create_app
from scripts.init_ca import create_ca


def test_env_settings_are_applied(monkeypatch):
    choices = {
        "CA_DISPLAY_NAME": "سامانه گواهی",
        "CA_ORGANIZATION": "Example IT",
        "CERT_VALIDITY_DAYS": "7",
        "SERVER_KEY_BITS": "3072",
        "CHALLENGE_SECONDS": "900",
        "MAX_REQUESTS_PER_HOUR": "5",
        "MAX_TOTAL_PER_HOUR": "50",
        "MAX_VERIFICATIONS": "4",
        "DOWNLOAD_TTL_SECONDS": "120",
        "MAX_PENDING_DOWNLOADS": "8",
        "CA_ISSUER_KEY_FILE": "signer-key.pem",
        "CA_ISSUER_CERT_FILE": "signer-cert.pem",
        "CA_ROOT_CERT_FILE": "company-root.pem",
        "DNS_RESOLVERS": "1.1.1.1",
    }
    for key, value in choices.items():
        monkeypatch.setenv(key, value)
    settings = Settings.from_env()
    assert settings.ca_display_name == "سامانه گواهی"
    assert settings.ca_organization == "Example IT"
    assert settings.certificate_validity_days == 7
    assert settings.server_key_bits == 3072
    assert settings.challenge_seconds == 900
    assert settings.max_requests_per_hour == 5
    assert settings.max_total_per_hour == 50
    assert settings.max_verifications == 4
    assert settings.download_ttl_seconds == 120
    assert settings.max_pending_downloads == 8
    assert settings.ca_issuer_key_file == "signer-key.pem"
    assert settings.ca_issuer_cert_file == "signer-cert.pem"
    assert settings.ca_root_cert_file == "company-root.pem"


@pytest.mark.parametrize("key,value", [
    ("CERT_VALIDITY_DAYS", "31"),
    ("CERT_VALIDITY_DAYS", "days"),
    ("SERVER_KEY_BITS", "1024"),
    ("CHALLENGE_SECONDS", "100"),
    ("DOWNLOAD_TTL_SECONDS", "700"),
    ("MAX_PENDING_DOWNLOADS", "1000"),
    ("CA_ISSUER_KEY_FILE", "../issuer-key.pem"),
    ("CA_ROOT_CERT_FILE", "/tmp/root-cert.pem"),
    ("CA_DISPLAY_NAME", ""),
])
def test_invalid_env_rejected(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match=key):
        Settings.from_env()


def test_public_config_from_real_ca_and_configured_policy(tmp_path, monkeypatch):
    create_ca(tmp_path / "secret", b"root-password-long-123", b"issuer-password-long-123")
    monkeypatch.setenv("CA_KEY_PASSWORD", "issuer-password-long-123")
    monkeypatch.setenv("CA_DIR", str(tmp_path / "secret" / "online"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "panel.sqlite"))
    monkeypatch.setenv("CA_DISPLAY_NAME", "My Public Label")
    monkeypatch.setenv("CA_ORGANIZATION", "Example Tech")
    monkeypatch.setenv("CERT_VALIDITY_DAYS", "2")
    monkeypatch.setenv("SERVER_KEY_BITS", "3072")
    monkeypatch.setenv("CHALLENGE_SECONDS", "600")
    monkeypatch.setenv("DOWNLOAD_TTL_SECONDS", "120")
    api = create_app(Settings.from_env())
    api.state.dns_checker = lambda _name, _expected: True
    with TestClient(api) as client:
        public = client.get("/api/system")
        assert public.status_code == 200
        info = public.json()
        assert info["display_name"] == "My Public Label"
        assert info["organization"] == "Example Tech"
        assert info["certificate_validity_days"] == 2
        assert info["server_key_bits"] == 3072
        assert info["challenge_seconds"] == 600
        assert info["download_ttl_seconds"] == 120
        assert info["issuer_common_name"] == "CA-Panel Online Issuing CA"
        assert info["root_common_name"] == "CA-Panel Offline Root CA"
        assert len(info["root_sha256"]) == 64
        assert set(info) == {
            "display_name", "organization", "certificate_validity_days",
            "server_key_bits", "challenge_seconds", "download_ttl_seconds",
            "issuer_common_name", "issuer_expires_at",
            "root_common_name", "root_sha256"
        }
        assert "issuer-password-long-123" not in public.text
        assert str(tmp_path) not in public.text
        created = client.post("/api/requests", json={"domain": "example.org"})
        assert created.status_code == 201, created.text
        assert 0 < created.json()["expires_at"] - time.time() <= 600
        rid = created.json()["request_id"]
        assert client.post(f"/api/requests/{rid}/verify").status_code == 200
        response = client.post(f"/api/requests/{rid}/issue-server")
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["download_expires_in_seconds"] == 120
        bundle = client.get(data["download_url"])
        assert bundle.status_code == 200
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
            key = serialization.load_pem_private_key(archive.read("example.org.key"), password=None)
            assert isinstance(key, rsa.RSAPrivateKey)
            assert key.key_size == 3072
            leaf = x509.load_pem_x509_certificate(archive.read("example.org.crt"))
            remaining = leaf.not_valid_after_utc - datetime.now(timezone.utc)
            assert timedelta(days=1) < remaining <= timedelta(days=2)


def test_ca_filenames_refer_to_existing_pem_not_env_pseudo_identity(tmp_path):
    import shutil
    create_ca(tmp_path / "secret", b"root-password-long-123", b"issuer-password-long-123")
    online = tmp_path / "secret" / "online"
    shutil.move(online / "issuer-key.pem", online / "signing-key.pem")
    shutil.move(online / "issuer-cert.pem", online / "signing-cert.pem")
    shutil.move(online / "root-cert.pem", online / "root-public.pem")
    settings = Settings(
        db_path=tmp_path / "data" / "panel.db",
        ca_dir=online, ca_key_password="issuer-password-long-123",
        ca_display_name="Decorative label, not X509 subject",
        ca_issuer_key_file="signing-key.pem",
        ca_issuer_cert_file="signing-cert.pem",
        ca_root_cert_file="root-public.pem",
    )
    with TestClient(create_app(settings)) as client:
        data = client.get("/api/system").json()
        assert data["display_name"] == "Decorative label, not X509 subject"
        assert data["root_common_name"] == "CA-Panel Offline Root CA"
        assert data["issuer_common_name"] == "CA-Panel Online Issuing CA"
