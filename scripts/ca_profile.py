"""Validated CA *creation-time* profile sourced from .env.

These variables are read ONLY when generating a genuinely new Root/Issuing CA.
Editing them cannot change the subject or validity of existing signed certificates.
No private keys or passphrases are stored in this profile.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


_CERT_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.pem")
_DAYS_MIN_ROOT, _DAYS_MAX_ROOT = 365, 7300
_DAYS_MIN_ISSUER, _DAYS_MAX_ISSUER = 30, 3650


def _number(values: Mapping[str, str], key: str, default: int) -> int:
    raw = values.get(key, str(default))
    try:
        return int(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _name(value: str, key: str, *, required: bool) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
    # X.509 CN and Organization Name use a DirectoryString length limit of 64.
    if (not value and not required):
        return ""
    if (not value.strip() or value != value.strip() or
            len(value.encode("utf-8")) > 64 or
            any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise ValueError(f"{key} must be 1-64 UTF-8 bytes of printable text")
    return value


def _filename(value: str, key: str) -> str:
    if not _CERT_FILE.fullmatch(value):
        raise ValueError(f"{key} must be a simple PEM filename, not a path")
    return value


@dataclass(frozen=True)
class CAProfile:
    root_common_name: str = "CA-Panel Offline Root CA"
    issuer_common_name: str = "CA-Panel Online Issuing CA"
    root_organization: str = ""
    issuer_organization: str = ""
    root_validity_days: int = 3650
    issuer_validity_days: int = 365
    root_key_bits: int = 3072
    issuer_key_bits: int = 3072
    root_key_file: str = "root-key.pem"          # ONLY on offline admin machine
    root_cert_file: str = "root-cert.pem"        # copied as public cert to online
    issuer_key_file: str = "issuer-key.pem"      # encrypted and online
    issuer_cert_file: str = "issuer-cert.pem"    # public and online

    def __post_init__(self) -> None:
        for field, value in (
            ("CA_ROOT_CN", self.root_common_name),
            ("CA_ISSUER_CN", self.issuer_common_name),
        ):
            _name(value, field, required=True)
        for field, value in (
            ("CA_ROOT_ORGANIZATION", self.root_organization),
            ("CA_ISSUER_ORGANIZATION", self.issuer_organization),
        ):
            _name(value, field, required=False)
        for key, value, low, high in (
            ("CA_ROOT_VALIDITY_DAYS", self.root_validity_days, _DAYS_MIN_ROOT, _DAYS_MAX_ROOT),
            ("CA_ISSUER_VALIDITY_DAYS", self.issuer_validity_days, _DAYS_MIN_ISSUER, _DAYS_MAX_ISSUER),
        ):
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{key} must be an integer between {low} and {high}")
        if self.issuer_validity_days + 7 > self.root_validity_days:
            raise ValueError("CA_ISSUER_VALIDITY_DAYS must be at least 7 days less than CA_ROOT_VALIDITY_DAYS")
        for key, value in (
            ("CA_ROOT_KEY_BITS", self.root_key_bits),
            ("CA_ISSUER_KEY_BITS", self.issuer_key_bits),
        ):
            if value not in (3072, 4096) or type(value) is not int:
                raise ValueError(f"{key} must be 3072 or 4096 bits")
        for key, value in (
            ("CA_ROOT_KEY_FILE", self.root_key_file),
            ("CA_ROOT_CERT_FILE", self.root_cert_file),
            ("CA_ISSUER_KEY_FILE", self.issuer_key_file),
            ("CA_ISSUER_CERT_FILE", self.issuer_cert_file),
        ):
            _filename(value, key)
        if len({self.root_key_file, self.root_cert_file}) != 2:
            raise ValueError("Root CA key and certificate filenames must differ")
        if len({self.issuer_key_file, self.issuer_cert_file, self.root_cert_file}) != 3:
            raise ValueError("Online issuer key/cert and root cert filenames must differ")

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "CAProfile":
        return cls(
            root_common_name=values.get("CA_ROOT_CN", cls.root_common_name),
            issuer_common_name=values.get("CA_ISSUER_CN", cls.issuer_common_name),
            root_organization=values.get("CA_ROOT_ORGANIZATION", ""),
            issuer_organization=values.get("CA_ISSUER_ORGANIZATION", ""),
            root_validity_days=_number(values, "CA_ROOT_VALIDITY_DAYS", 3650),
            issuer_validity_days=_number(values, "CA_ISSUER_VALIDITY_DAYS", 365),
            root_key_bits=_number(values, "CA_ROOT_KEY_BITS", 3072),
            issuer_key_bits=_number(values, "CA_ISSUER_KEY_BITS", 3072),
            root_key_file=values.get("CA_ROOT_KEY_FILE", "root-key.pem"),
            root_cert_file=values.get("CA_ROOT_CERT_FILE", "root-cert.pem"),
            issuer_key_file=values.get("CA_ISSUER_KEY_FILE", "issuer-key.pem"),
            issuer_cert_file=values.get("CA_ISSUER_CERT_FILE", "issuer-cert.pem"),
        )


def read_env_values(path: Path) -> dict[str, str]:
    """Read a Compose-style dotenv file without sourcing code or shell expansion.

    Single quotes preserve literal $ characters; this is intended for the
    installer/CA creation profile, not as a full Docker Compose parser.
    """
    if path.is_symlink():
        raise ValueError("Refusing symlink .env file")
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        match = re.fullmatch(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", item)
        if not match:
            continue
        key, raw = match.groups()
        if key in values:
            raise ValueError(f"Duplicate setting in .env: {key}")
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
            value = raw[1:-1]
        else:
            value = raw.split(" #", 1)[0].rstrip()
        values[key] = value
    return values
