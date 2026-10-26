#!/usr/bin/env python3
"""Safely install a CA-Panel one-time ZIP as HTTPS material for Caddy :443.

Example:
    python3 scripts/setup_private_tls.py --zip ~/Downloads/ca1.iravand.ir-certificates.zip

Does not call the CA issuance API, contact a server or bypass TLS validation.
Uses the system OpenSSL executable to verify the chain, hostname and key match.
Does not store the CA Issuing private key on the HTTPS reverse proxy.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    from scripts.ca_profile import read_env_values
except ModuleNotFoundError:
    from ca_profile import read_env_values


ROOT = Path(__file__).resolve().parents[1]
MAX_ITEM_SIZE = 1024 * 1024


def error(message: str) -> None:
    raise ValueError(message)


def safe_domain(domain: str) -> str:
    if domain != domain.lower() or len(domain) > 253:
        error("PANEL_DOMAIN must be a lower-case DNS hostname")
    labels = domain.split(".")
    if len(labels) < 2 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
        for part in labels
    ):
        error("PANEL_DOMAIN must be a DNS hostname, not an IP or wildcard")
    return domain


def host_path(value: str) -> Path:
    if not value or any(c in value for c in ("$", "\n", "\r", "\0")):
        error("Invalid host directory in .env")
    base = Path(value).expanduser()
    return (ROOT / base if not base.is_absolute() else base)


def openssl(*args: str, input_data: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(
            ["openssl", *args], input=input_data,
            capture_output=True, check=True, timeout=20,
        )
        return result.stdout
    except FileNotFoundError as exc:
        raise RuntimeError("OpenSSL is required (installed by default on macOS)") from exc
    except subprocess.CalledProcessError as exc:
        # Do not echo private key contents or arbitrary stderr from untrusted ZIP.
        raise ValueError(f"Certificate/key validation failed during: openssl {args[0]}") from exc


def checked_zip_item(archive: zipfile.ZipFile, name: str) -> bytes:
    records = [z for z in archive.infolist() if z.filename == name]
    if len(records) != 1 or records[0].file_size > MAX_ITEM_SIZE or records[0].is_dir():
        error(f"Expected exactly one small file in ZIP: {name}")
    data = archive.read(records[0])
    if not data or len(data) > MAX_ITEM_SIZE:
        error(f"Empty or oversized file in ZIP: {name}")
    return data


def install_archive(archive_file: Path, *, replace: bool = False) -> tuple[Path, str]:
    values = read_env_values(ROOT / ".env")
    domain = safe_domain(values.get("PANEL_DOMAIN", "ca1.iravand.ir"))
    tls_dir = host_path(values.get("PANEL_TLS_HOST_DIR", "./secrets/tls"))
    ca_dir = host_path(values.get("CA_ONLINE_HOST_DIR", "./secrets/online"))
    root_file_name = values.get("CA_ROOT_CERT_FILE", "root-cert.pem")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.pem", root_file_name):
        error("Invalid CA_ROOT_CERT_FILE in .env")
    root_cert = ca_dir / root_file_name
    if not root_cert.is_file() or root_cert.is_symlink():
        error("Trusted Root certificate missing: configure CA_ONLINE_HOST_DIR and CA_ROOT_CERT_FILE")
    if tls_dir.is_symlink():
        error("Refusing symlink as PANEL_TLS_HOST_DIR")
    key_dest = tls_dir / "privkey.pem"
    cert_dest = tls_dir / "fullchain.pem"
    if not replace and (key_dest.exists() or cert_dest.exists()):
        error("HTTPS certificate/key already installed; specify --replace to rotate deliberately")

    if not archive_file.is_file() or archive_file.stat().st_size > 8 * MAX_ITEM_SIZE:
        error("ZIP does not exist or is unreasonably large")

    with zipfile.ZipFile(archive_file) as archive:
        leaf = checked_zip_item(archive, f"{domain}.crt")
        chain = checked_zip_item(archive, f"{domain}-fullchain.pem")
        issuer = checked_zip_item(archive, "issuing-ca.pem")
        private = checked_zip_item(archive, f"{domain}.key")
        if chain != leaf + issuer:
            error("ZIP fullchain must be exactly the leaf certificate followed by Issuing CA")
        if b"-----BEGIN PRIVATE KEY-----" not in private:
            error("Expected an unencrypted domain-specific TLS key, not a CA key")

    # Everything is staged with restrictive permissions; validation happens
    # before either final destination file is modified.
    tls_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=tls_dir, prefix=".tls-check-") as temp:
        path = Path(temp)
        crt = path / "leaf.pem"
        full = path / "fullchain.pem"
        issuer_crt = path / "issuer.pem"
        key = path / "privkey.pem"
        for out, data in ((crt, leaf), (full, chain), (issuer_crt, issuer), (key, private)):
            out.write_bytes(data)
            out.chmod(0o600)

        cert_detail = openssl("x509", "-in", str(crt), "-noout", "-text").decode("utf-8", errors="replace")
        if not re.search(r"DNS:" + re.escape(domain) + r"(?=[,\s]|$)", cert_detail):
            error(f"TLS certificate has no matching DNS SAN for {domain}")
        openssl("verify", "-CAfile", str(root_cert), "-untrusted", str(issuer_crt),
                "-purpose", "sslserver", "-verify_hostname", domain, str(crt))
        # Verify leaf cert and private key have byte-identical public keys.
        key_pub = openssl("pkey", "-in", str(key), "-pubout", "-outform", "DER")
        leaf_pub_pem = openssl("x509", "-in", str(crt), "-noout", "-pubkey")
        cert_pub = openssl("pkey", "-pubin", "-outform", "DER", input_data=leaf_pub_pem)
        if not key_pub or hashlib.sha256(key_pub).digest() != hashlib.sha256(cert_pub).digest():
            error("Private key does not match the certificate public key")
        openssl("x509", "-in", str(crt), "-noout", "-checkend", "0")

        for origin, destination in ((full, cert_dest), (key, key_dest)):
            temporary = tls_dir / (".new-" + destination.name)
            try:
                with temporary.open("xb") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(origin.read_bytes())
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        tls_dir.chmod(0o700)
    return tls_dir, domain


def main() -> int:
    parser = argparse.ArgumentParser(description="Install and verify CA-Panel private HTTPS certificate for :443")
    parser.add_argument("--zip", dest="archive", type=Path, required=True,
                        help="CA-Panel one-time ZIP from the issuance page")
    parser.add_argument("--replace", action="store_true",
                        help="Deliberately replace an existing HTTPS leaf cert+key during renewal")
    args = parser.parse_args()
    try:
        destination, domain = install_archive(args.archive, replace=args.replace)
    except (ValueError, RuntimeError, OSError, zipfile.BadZipFile) as exc:
        print(f"Private HTTPS setup failed: {exc}", file=sys.stderr)
        return 1
    print("Verified private CA certificate, TLS hostname and matching leaf key.")
    print("Installed private HTTPS TLS files in:", destination)
    print("Ready for: docker compose --profile private-tls up -d --build api caddy-private")
    print("Test with: curl --noproxy '*' --cacert secrets/online/root-cert.pem "
          f"--resolve {domain}:443:127.0.0.1 https://{domain}/healthz")
    print("Protect or securely remove the original ZIP; it contains an unencrypted private key.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
