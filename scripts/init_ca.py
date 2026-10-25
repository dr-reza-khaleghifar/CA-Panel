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

# Support both "python scripts/init_ca.py" and "python -m scripts.init_ca".
try:
    from scripts.ca_profile import CAProfile, read_env_values
except ModuleNotFoundError:
    from ca_profile import CAProfile, read_env_values


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


def create_ca(output: Path, root_password: bytes, issuer_password: bytes,
              profile: CAProfile | None = None):
    """Create a new CA only; profile applies to creation, never existing keys."""
    profile = profile if profile is not None else CAProfile()
    if len(root_password) < 12 or len(issuer_password) < 12 or root_password == issuer_password:
        raise ValueError("Root and Issuing CA passphrases must differ and be 12+ characters")
    if output.is_symlink():
        raise ValueError("Refusing symlink as CA output directory")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    offline, online = output / "offline", output / "online"
    offline.mkdir(mode=0o700, exist_ok=True)
    online.mkdir(mode=0o700, exist_ok=True)
    filenames = [
        offline / profile.root_key_file, offline / profile.root_cert_file,
        online / profile.issuer_key_file, online / profile.issuer_cert_file,
        online / profile.root_cert_file,
    ]
    if any(path.exists() or path.is_symlink() for path in filenames):
        raise SystemExit("CA files already exist; refusing to overwrite keys")
    now = datetime.now(timezone.utc)
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=profile.root_key_bits)
    issuer_key = rsa.generate_private_key(public_exponent=65537, key_size=profile.issuer_key_bits)

    def subject(name: str, organization: str) -> x509.Name:
        parts = [x509.NameAttribute(NameOID.COMMON_NAME, name)]
        if organization:
            parts.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization))
        return x509.Name(parts)

    root_name = subject(profile.root_common_name, profile.root_organization)
    issuer_name = subject(profile.issuer_common_name, profile.issuer_organization)
    root = (x509.CertificateBuilder().subject_name(root_name).issuer_name(root_name).public_key(root_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=profile.root_validity_days))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()), critical=False)
        .sign(root_key, hashes.SHA256()))
    issuer = (x509.CertificateBuilder().subject_name(issuer_name).issuer_name(root_name).public_key(issuer_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=profile.issuer_validity_days))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(issuer_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)
        .sign(root_key, hashes.SHA256()))
    pem_format = serialization.PrivateFormat.PKCS8
    encoding = serialization.Encoding.PEM
    secure_write(offline / profile.root_key_file, root_key.private_bytes(encoding, pem_format, serialization.BestAvailableEncryption(root_password)))
    secure_write(offline / profile.root_cert_file, root.public_bytes(encoding))
    secure_write(online / profile.issuer_key_file, issuer_key.private_bytes(encoding, pem_format, serialization.BestAvailableEncryption(issuer_password)))
    secure_write(online / profile.issuer_cert_file, issuer.public_bytes(encoding))
    secure_write(online / profile.root_cert_file, root.public_bytes(encoding))
    print("CA initialized. Store secrets/offline OFFLINE (never on the application server).")
    print("Root certificate SHA256:", root.fingerprint(hashes.SHA256()).hex().upper())
    print("Issuer expiration:", issuer.not_valid_after_utc.isoformat())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create offline root and encrypted online issuing CA")
    parser.add_argument("--output", type=Path, default=Path("secrets"))
    parser.add_argument("--env", type=Path, default=Path(".env"),
                        help="Creation-time CA settings from .env (defaults if file absent)")
    args = parser.parse_args()
    profile = CAProfile.from_mapping(read_env_values(args.env))
    create_ca(args.output, password_twice("Root CA"), password_twice("Issuing CA"), profile)
