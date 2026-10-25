"""One-time, on-operator-machine private CA bootstrap. Never commit generated files."""
from __future__ import annotations
import argparse
import getpass
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def secure_write(path: Path, contents: bytes):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contents)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def password_twice(label: str) -> bytes:
    one = getpass.getpass(f"{label} passphrase (12+ characters): ")
    two = getpass.getpass(f"Repeat {label} passphrase: ")
    if one != two or len(one) < 12:
        raise SystemExit("Passphrases do not match or are too short")
    return one.encode()


def create_ca(output: Path, root_password: bytes, issuer_password: bytes):
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    offline, online = output / "offline", output / "online"
    offline.mkdir(mode=0o700, exist_ok=True)
    online.mkdir(mode=0o700, exist_ok=True)
    filenames = [offline / "root-key.pem", offline / "root-cert.pem", online / "issuer-key.pem", online / "issuer-cert.pem", online / "root-cert.pem"]
    if any(p.exists() for p in filenames):
        raise SystemExit("CA files already exist; refusing to overwrite keys")
    now = datetime.now(timezone.utc)
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    issuer_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CA-Panel Offline Root CA")])
    issuer_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CA-Panel Online Issuing CA")])
    root = (x509.CertificateBuilder().subject_name(root_name).issuer_name(root_name).public_key(root_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()), critical=False)
        .sign(root_key, hashes.SHA256()))
    issuer = (x509.CertificateBuilder().subject_name(issuer_name).issuer_name(root_name).public_key(issuer_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(issuer_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)
        .sign(root_key, hashes.SHA256()))
    pem_format = serialization.PrivateFormat.PKCS8
    encoding = serialization.Encoding.PEM
    secure_write(offline / "root-key.pem", root_key.private_bytes(encoding, pem_format, serialization.BestAvailableEncryption(root_password)))
    secure_write(offline / "root-cert.pem", root.public_bytes(encoding))
    secure_write(online / "issuer-key.pem", issuer_key.private_bytes(encoding, pem_format, serialization.BestAvailableEncryption(issuer_password)))
    secure_write(online / "issuer-cert.pem", issuer.public_bytes(encoding))
    secure_write(online / "root-cert.pem", root.public_bytes(encoding))
    print("CA initialized. Store secrets/offline OFFLINE (never on the application server).")
    print("Root certificate SHA256:", root.fingerprint(hashes.SHA256()).hex().upper())
    print("Issuer expiration:", issuer.not_valid_after_utc.isoformat())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create offline root and encrypted online issuing CA")
    parser.add_argument("--output", type=Path, default=Path("secrets"))
    args = parser.parse_args()
    create_ca(args.output, password_twice("Root CA"), password_twice("Issuing CA"))
