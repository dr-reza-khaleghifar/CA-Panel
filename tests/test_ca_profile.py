"""Certificate Authority creation profile reads .env without rewriting issued CA PEMs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from scripts.ca_profile import CAProfile, read_env_values
from scripts.init_ca import create_ca


def attr(cert, oid):
    return cert.subject.get_attributes_for_oid(oid)[0].value


def test_profile_from_dotenv(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "CA_ROOT_CN='Example Offline Root CA'\n"
        "CA_ISSUER_CN='Example Online Issuing CA'\n"
        "CA_ROOT_ORGANIZATION='Example International'\n"
        "CA_ISSUER_ORGANIZATION=Example IT\n"
        "CA_ROOT_VALIDITY_DAYS=2500\n"
        "CA_ISSUER_VALIDITY_DAYS=450\n"
        "CA_ROOT_KEY_BITS=3072\n"
        "CA_ISSUER_KEY_BITS=4096\n"
        "CA_ROOT_KEY_FILE=offline-secret.pem\n"
        "CA_ROOT_CERT_FILE=offline-public.pem\n"
        "CA_ISSUER_KEY_FILE=online-secret.pem\n"
        "CA_ISSUER_CERT_FILE=online-public.pem\n",
        encoding="utf-8",
    )
    values = read_env_values(dotenv)
    assert CAProfile.from_mapping(values) == CAProfile(
        root_common_name="Example Offline Root CA",
        issuer_common_name="Example Online Issuing CA",
        root_organization="Example International",
        issuer_organization="Example IT",
        root_validity_days=2500,
        issuer_validity_days=450,
        root_key_bits=3072,
        issuer_key_bits=4096,
        root_key_file="offline-secret.pem",
        root_cert_file="offline-public.pem",
        issuer_key_file="online-secret.pem",
        issuer_cert_file="online-public.pem",
    )


def test_generated_ca_uses_env_subjects_crypto_and_filenames(tmp_path):
    profile = CAProfile(
        root_common_name="Example Root",
        issuer_common_name="Example Issuer",
        root_organization="Example Operations",
        issuer_organization="Example PKI",
        root_validity_days=1460,
        issuer_validity_days=360,
        root_key_bits=3072,
        issuer_key_bits=3072,
        root_key_file="my-root-private.pem",
        root_cert_file="my-root-public.pem",
        issuer_key_file="my-issuer-private.pem",
        issuer_cert_file="my-issuer-public.pem",
    )
    output = tmp_path / "secrets"
    create_ca(output, b"safe-root-passphrase-123", b"safe-issuer-passphrase-123", profile)
    offline, online = output / "offline", output / "online"
    assert sorted(f.name for f in offline.iterdir()) == [
        "my-root-private.pem", "my-root-public.pem"
    ]
    assert sorted(f.name for f in online.iterdir()) == [
        "my-issuer-private.pem", "my-issuer-public.pem", "my-root-public.pem"
    ]
    assert not (online / profile.root_key_file).exists()
    root = x509.load_pem_x509_certificate((online / profile.root_cert_file).read_bytes())
    issuer = x509.load_pem_x509_certificate((online / profile.issuer_cert_file).read_bytes())
    assert root.public_bytes(serialization.Encoding.PEM) == (
        offline / profile.root_cert_file
    ).read_bytes()
    assert attr(root, NameOID.COMMON_NAME) == "Example Root"
    assert attr(issuer, NameOID.COMMON_NAME) == "Example Issuer"
    assert attr(root, NameOID.ORGANIZATION_NAME) == "Example Operations"
    assert attr(issuer, NameOID.ORGANIZATION_NAME) == "Example PKI"
    assert root.subject == root.issuer
    assert issuer.issuer == root.subject
    assert root.public_key().key_size == 3072
    assert issuer.public_key().key_size == 3072
    root_life = root.not_valid_after_utc - root.not_valid_before_utc
    issuer_life = issuer.not_valid_after_utc - issuer.not_valid_before_utc
    assert timedelta(days=1460) <= root_life <= timedelta(days=1461)
    assert timedelta(days=360) <= issuer_life <= timedelta(days=361)
    signing_key = serialization.load_pem_private_key(
        (online / profile.issuer_key_file).read_bytes(),
        password=b"safe-issuer-passphrase-123",
    )
    assert isinstance(signing_key, rsa.RSAPrivateKey)
    assert signing_key.key_size == 3072
    with pytest.raises((TypeError, ValueError)):
        serialization.load_pem_private_key(
            (offline / profile.root_key_file).read_bytes(), password=None
        )
    contents_before = {
        file.relative_to(output): file.read_bytes()
        for file in output.rglob("*.pem")
    }
    with pytest.raises((FileExistsError, SystemExit)):
        create_ca(output, b"safe-root-passphrase-123", b"safe-issuer-passphrase-123", profile)
    assert contents_before == {
        file.relative_to(output): file.read_bytes()
        for file in output.rglob("*.pem")
    }


@pytest.mark.parametrize("invalid", [
    {"CA_ROOT_CN": ""},
    {"CA_ISSUER_CN": "x" * 65},
    {"CA_ROOT_CN": "bad\nline"},
    {"CA_ROOT_ORGANIZATION": "x" * 65},
    {"CA_ROOT_VALIDITY_DAYS": "zero"},
    {"CA_ROOT_VALIDITY_DAYS": "100"},
    {"CA_ISSUER_VALIDITY_DAYS": "5"},
    {"CA_ISSUER_VALIDITY_DAYS": "3650", "CA_ROOT_VALIDITY_DAYS": "3650"},
    {"CA_ROOT_KEY_BITS": "1024"},
    {"CA_ISSUER_KEY_BITS": "2048"},
    {"CA_ROOT_KEY_FILE": "../root.pem"},
    {"CA_ROOT_KEY_FILE": "/tmp/root.pem"},
    {"CA_ROOT_CERT_FILE": "root-key.pem"},
    {"CA_ISSUER_CERT_FILE": "issuer-key.pem"},
    {"CA_ISSUER_CERT_FILE": "root-cert.pem"},
])
def test_profile_rejects_unsafe_values(invalid):
    with pytest.raises(ValueError):
        CAProfile.from_mapping(invalid)


def test_missing_env_uses_original_defaults(tmp_path):
    values = read_env_values(tmp_path / "missing.env")
    assert values == {}
    cfg = CAProfile.from_mapping(values)
    assert cfg.root_common_name == "CA-Panel Offline Root CA"
    assert cfg.issuer_common_name == "CA-Panel Online Issuing CA"
    assert cfg.root_validity_days == 3650
    assert cfg.issuer_validity_days == 365
    assert cfg.root_key_bits == cfg.issuer_key_bits == 3072
    assert cfg.root_key_file == "root-key.pem"


def test_env_parser_rejects_duplicate_keys_and_symlink(tmp_path):
    p = tmp_path / ".env"
    p.write_text("CA_ROOT_CN=One\nCA_ROOT_CN=Two\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        read_env_values(p)
    p.unlink()
    p.symlink_to(tmp_path / "another")
    with pytest.raises(ValueError, match="symlink"):
        read_env_values(p)
