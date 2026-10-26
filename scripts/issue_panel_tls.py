#!/usr/bin/env python3
"""Local-only HTTPS certificate bootstrap for the CA-Panel hostname.

This is an OPERATOR action, not an API endpoint. It uses the already-provisioned
encrypted online Issuing CA and signs only the exact PANEL_DOMAIN from .env.
DNS proof is still mandatory for every public /api/requests issuance workflow.

Invocation: bash install.sh --private-https
              or .venv/bin/python scripts/issue_panel_tls.py
No Root private key is loaded, and neither issuer key nor its password is copied
into the HTTPS web server directory or written to logs.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

try:
    from scripts.ca_profile import read_env_values
    from scripts.setup_private_tls import host_path, safe_domain
except ModuleNotFoundError:
    from ca_profile import read_env_values
    from setup_private_tls import host_path, safe_domain


ROOT = Path(__file__).resolve().parents[1]
_RENEWAL_WINDOW = timedelta(days=7)


def _named_pem(directory: Path, name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.pem", name):
        raise ValueError("Invalid configured certificate filename")
    path = directory / name
    if not path.is_file() or path.is_symlink():
        raise ValueError("Configured CA PEM is missing or is a symlink")
    return path


def _public_der(key) -> bytes:
    return key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _verify_rsa_signature(cert: x509.Certificate, issuer_cert: x509.Certificate) -> None:
    key = issuer_cert.public_key()
    if not isinstance(key, rsa.RSAPublicKey):
        raise ValueError("Only the existing RSA Root/Issuing CA profile is supported")
    key.verify(cert.signature, cert.tbs_certificate_bytes,
               padding.PKCS1v15(), cert.signature_hash_algorithm)


def _ca_signer(values: dict[str, str], project_root: Path):
    # Paths are never obtained from a web request. Only local, administrator-
    # writable .env and encrypted CA files authorize this operation.
    ca_raw = values.get("CA_ONLINE_HOST_DIR", "./secrets/online")
    ca_dir = host_path(ca_raw) if project_root == ROOT else _project_path(project_root, ca_raw)
    if ca_dir.is_symlink() or not ca_dir.is_dir():
        raise ValueError("Online Issuing CA directory is missing or is a symlink")
    key_path = _named_pem(ca_dir, values.get("CA_ISSUER_KEY_FILE", "issuer-key.pem"))
    issuer_path = _named_pem(ca_dir, values.get("CA_ISSUER_CERT_FILE", "issuer-cert.pem"))
    root_path = _named_pem(ca_dir, values.get("CA_ROOT_CERT_FILE", "root-cert.pem"))
    password = values.get("CA_KEY_PASSWORD", "")
    if not password or password == "REPLACE_WITH_ISSUING_CA_PASSPHRASE":
        raise ValueError("Issuing CA password not configured in .env")
    try:
        signing_key = serialization.load_pem_private_key(
            key_path.read_bytes(), password=password.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Cannot decrypt online Issuing CA key; check .env") from exc
    issuer = x509.load_pem_x509_certificate(issuer_path.read_bytes())
    root = x509.load_pem_x509_certificate(root_path.read_bytes())
    now = datetime.now(timezone.utc)
    if not isinstance(signing_key, rsa.RSAPrivateKey):
        raise ValueError("Only RSA Issuing CA signing keys are supported")
    if _public_der(signing_key.public_key()) != _public_der(issuer.public_key()):
        raise ValueError("Issuing CA certificate does not match its private key")
    if root.subject != root.issuer or issuer.issuer != root.subject:
        raise ValueError("Configured Root/Issuing CA subjects do not form a chain")
    for cert in (root, issuer):
        if not (cert.not_valid_before_utc <= now < cert.not_valid_after_utc):
            raise ValueError("Root/Issuing CA certificate is expired or not yet valid")
        if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError("Configured signing certificate is not a CA")
        if not cert.extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign:
            raise ValueError("Configured signing certificate cannot sign certificates")
    _verify_rsa_signature(root, root)
    _verify_rsa_signature(issuer, root)
    if issuer.not_valid_after_utc <= now + timedelta(days=1, minutes=5):
        raise ValueError("Issuing CA expires too soon; rotate Issuing CA first")
    return signing_key, issuer, root


def _project_path(project_root: Path, raw: str) -> Path:
    if not raw or any(s in raw for s in ("$", "\n", "\r", "\x00")):
        raise ValueError("Invalid host directory path")
    p = Path(raw).expanduser()
    return p if p.is_absolute() else project_root / p


def _existing_is_current(
    fullchain_path: Path, key_path: Path, domain: str, issuer: x509.Certificate,
    now: datetime,
) -> bool:
    if fullchain_path.is_symlink() or key_path.is_symlink():
        raise ValueError("Refusing symlink for deployed TLS certificate/key")
    fullchain = fullchain_path.read_bytes()
    leaf = x509.load_pem_x509_certificate(fullchain)
    if fullchain != leaf.public_bytes(serialization.Encoding.PEM) + issuer.public_bytes(serialization.Encoding.PEM):
        raise ValueError("Existing TLS fullchain differs from this Issuing CA")
    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    if san.get_values_for_type(x509.DNSName) != [domain] or len(san) != 1:
        raise ValueError("Existing TLS certificate does not match PANEL_DOMAIN")
    if leaf.issuer != issuer.subject:
        raise ValueError("Existing TLS leaf has an unexpected issuer")
    if leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise ValueError("Existing HTTPS certificate is a CA certificate")
    usages = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    if ExtendedKeyUsageOID.SERVER_AUTH not in usages:
        raise ValueError("Existing TLS certificate lacks serverAuth")
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if _public_der(key.public_key()) != _public_der(leaf.public_key()):
        raise ValueError("Existing TLS private key does not match certificate")
    _verify_rsa_signature(leaf, issuer)
    if leaf.not_valid_before_utc > now + timedelta(minutes=5):
        raise ValueError("Existing certificate is not yet valid")
    return leaf.not_valid_after_utc > now + _RENEWAL_WINDOW


def _sign_leaf(
    domain: str, signer: rsa.RSAPrivateKey, issuer: x509.Certificate,
    days: int, key_bits: int,
):
    now = datetime.now(timezone.utc)
    end = min(now + timedelta(days=days),
              issuer.not_valid_after_utc - timedelta(minutes=5))
    if end <= now + timedelta(days=1):
        raise ValueError("Issuing CA expires too soon; cannot issue a new server leaf")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_bits)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
        .issuer_name(issuer.subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(end)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=True,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer.public_key()), critical=False)
        .sign(signer, hashes.SHA256())
    )
    key_pem = private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    fullchain = cert.public_bytes(serialization.Encoding.PEM) + issuer.public_bytes(serialization.Encoding.PEM)
    return fullchain, key_pem


def ensure_panel_tls(project_root: Path | None = None) -> str:
    """Issue/renew only the configured panel hostname, never arbitrary API domains.

    Returns 'issued', 'renewed', or 'unchanged'. Never overwrites an unpaired
    file, foreign CA chain, or mismatched private key.
    """
    root = project_root if project_root is not None else ROOT
    values = read_env_values(root / ".env")
    if "PANEL_DOMAIN" not in values:
        raise ValueError("Set PANEL_DOMAIN explicitly in .env before local HTTPS issuance")
    domain = safe_domain(values["PANEL_DOMAIN"])
    validity = int(values.get("CERT_VALIDITY_DAYS", "30"))
    bits = int(values.get("SERVER_KEY_BITS", "2048"))
    if not 2 <= validity <= 90 or bits not in (2048, 3072, 4096):
        raise ValueError("Invalid TLS leaf policy: validity 2-90 days; RSA 2048/3072/4096")
    directory = _project_path(root, values.get("PANEL_TLS_HOST_DIR", "./secrets/tls"))
    if directory.is_symlink():
        raise ValueError("Refusing symlink PANEL_TLS_HOST_DIR")
    signer, issuer, _ = _ca_signer(values, root)
    cert_path, key_path = directory / "fullchain.pem", directory / "privkey.pem"
    present = [p.exists() or p.is_symlink() for p in (cert_path, key_path)]
    if present == [True, False] or present == [False, True]:
        raise ValueError("Only one HTTPS TLS file exists; refusing partial replacement")
    now = datetime.now(timezone.utc)
    if all(present) and _existing_is_current(cert_path, key_path, domain, issuer, now):
        return "unchanged"
    operation = "renewed" if all(present) else "issued"
    fullchain, private_key = _sign_leaf(domain, signer, issuer, validity, bits)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    with tempfile.TemporaryDirectory(dir=directory, prefix=".panel-tls-") as scratch:
        stage = Path(scratch)
        # Both staged files are mode 0600; never log the key or password.
        for name, data in (("fullchain.pem", fullchain), ("privkey.pem", private_key)):
            with (stage / name).open("xb") as f:
                os.fchmod(f.fileno(), 0o600)
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        # Fail closed before replacing working files.
        _existing_is_current(stage / "fullchain.pem", stage / "privkey.pem", domain, issuer, now)
        # Temporary-directory rename is atomic per file; Docker Caddy is reloaded
        # by install.py only after both files are in place.
        os.replace(stage / "fullchain.pem", cert_path)
        os.replace(stage / "privkey.pem", key_path)
    return operation


def main() -> int:
    try:
        result = ensure_panel_tls()
    except (OSError, ValueError, x509.ExtensionNotFound) as exc:
        print(f"[CA-Panel] Local panel TLS setup failed: {exc}", file=sys.stderr)
        return 1
    print(f"[CA-Panel] Panel TLS certificate: {result}; domain from PANEL_DOMAIN; no DNS proof needed for local administrator")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
