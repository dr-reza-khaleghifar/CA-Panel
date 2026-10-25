"""Validated CA-Panel settings, explicitly sourced from the container environment.

Docker Compose reads .env and passes an allowlist of these variables to the API.
Root/issuer subjects always come from cryptographic PEM certificates, not labels.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path("/data/ca-panel.sqlite3")
    ca_dir: Path = Path("/run/ca")
    ca_key_password: str = ""
    challenge_seconds: int = 3600
    max_requests_per_hour: int = 20
    max_total_per_hour: int = 200
    max_verifications: int = 10
    trust_proxy_headers: bool = False
    dns_resolvers: str = ""

    ca_display_name: str = "CA-Panel"
    ca_organization: str = "Private CA"
    ca_issuer_key_file: str = "issuer-key.pem"
    ca_issuer_cert_file: str = "issuer-cert.pem"
    ca_root_cert_file: str = "root-cert.pem"
    certificate_validity_days: int = 30
    server_key_bits: int = 2048
    download_ttl_seconds: int = 600
    max_pending_downloads: int = 100

    def __post_init__(self) -> None:
        limits = {
            "CHALLENGE_SECONDS": (self.challenge_seconds, 300, 86400),
            "MAX_REQUESTS_PER_HOUR": (self.max_requests_per_hour, 1, 1000),
            "MAX_TOTAL_PER_HOUR": (self.max_total_per_hour, 1, 10000),
            "MAX_VERIFICATIONS": (self.max_verifications, 1, 100),
            "CERT_VALIDITY_DAYS": (self.certificate_validity_days, 1, 30),
            "DOWNLOAD_TTL_SECONDS": (self.download_ttl_seconds, 60, 600),
            "MAX_PENDING_DOWNLOADS": (self.max_pending_downloads, 1, 100),
        }
        for name, (value, low, high) in limits.items():
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer from {low} to {high}")
        if self.server_key_bits not in (2048, 3072, 4096):
            raise ValueError("SERVER_KEY_BITS must be 2048, 3072 or 4096")
        for name, value in (
            ("CA_DISPLAY_NAME", self.ca_display_name),
            ("CA_ORGANIZATION", self.ca_organization),
        ):
            if (not isinstance(value, str) or not 1 <= len(value.strip()) <= 100
                    or any(ord(char) < 32 or ord(char) == 127 for char in value)):
                raise ValueError(f"{name} must have 1-100 printable characters")
        for name, filename in (
            ("CA_ISSUER_KEY_FILE", self.ca_issuer_key_file),
            ("CA_ISSUER_CERT_FILE", self.ca_issuer_cert_file),
            ("CA_ROOT_CERT_FILE", self.ca_root_cert_file),
        ):
            if not isinstance(filename, str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.pem", filename
            ):
                raise ValueError(f"{name} must be a PEM filename within CA_DIR, not a path")

    @classmethod
    def from_env(cls) -> "Settings":
        """Evaluate at app startup (not Python module import)."""
        return cls(
            db_path=Path(os.getenv("DB_PATH", "/data/ca-panel.sqlite3")),
            ca_dir=Path(os.getenv("CA_DIR", "/run/ca")),
            ca_key_password=os.getenv("CA_KEY_PASSWORD", ""),
            challenge_seconds=env_int("CHALLENGE_SECONDS", 3600),
            max_requests_per_hour=env_int("MAX_REQUESTS_PER_HOUR", 20),
            max_total_per_hour=env_int("MAX_TOTAL_PER_HOUR", 200),
            max_verifications=env_int("MAX_VERIFICATIONS", 10),
            trust_proxy_headers=os.getenv("TRUST_PROXY_HEADERS", "0") == "1",
            dns_resolvers=os.getenv("DNS_RESOLVERS", ""),
            ca_display_name=os.getenv("CA_DISPLAY_NAME", "CA-Panel"),
            ca_organization=os.getenv("CA_ORGANIZATION", "Private CA"),
            ca_issuer_key_file=os.getenv("CA_ISSUER_KEY_FILE", "issuer-key.pem"),
            ca_issuer_cert_file=os.getenv("CA_ISSUER_CERT_FILE", "issuer-cert.pem"),
            ca_root_cert_file=os.getenv("CA_ROOT_CERT_FILE", "root-cert.pem"),
            certificate_validity_days=env_int("CERT_VALIDITY_DAYS", 30),
            server_key_bits=env_int("SERVER_KEY_BITS", 2048),
            download_ttl_seconds=env_int("DOWNLOAD_TTL_SECONDS", 600),
            max_pending_downloads=env_int("MAX_PENDING_DOWNLOADS", 100),
        )
