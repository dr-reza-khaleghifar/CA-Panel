#!/usr/bin/env python3
"""Interactive, TTY-only first administrator enrollment. Never modifies CA keys.

Usage: python3 scripts/setup_admin.py [--rotate]
Password is stored solely as salted PBKDF2, TOTP seed is a protected secret in
.env, and session generation invalidates sessions after credential rotation.
"""
from __future__ import annotations
import argparse
import getpass
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.auth import domain_suffixes, hash_password, new_totp_seed  # noqa: E402
from install import env_values, assign, write_env  # noqa: E402


def configure(path: Path, *, rotate: bool) -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("Administrator enrollment requires a private interactive terminal")
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Expected existing regular .env; configure your CA first")
    if path.parent.resolve() != ROOT.resolve():
        raise RuntimeError("Unexpected .env path")
    content = path.read_text(encoding="utf-8")
    values = env_values(content)
    if values.get("ADMIN_PASSWORD_HASH") and not rotate:
        raise RuntimeError("Admin already configured. To replace credentials explicitly use --rotate")
    if rotate and not values.get("ADMIN_PASSWORD_HASH"):
        raise RuntimeError("No existing admin credentials to rotate")
    if rotate:
        print("WARNING: Admin password/MFA seed will change and all old sessions will be invalidated.")
        if input("Type ROTATE ADMIN to continue: ").strip() != "ROTATE ADMIN":
            raise RuntimeError("Rotation cancelled")
    password = getpass.getpass("New admin password (16+ characters, hidden): ")
    repeat = getpass.getpass("Repeat admin password: ")
    if password != repeat:
        raise ValueError("Passwords do not match; .env unchanged")
    if len(password) < 16 or password.lower() in ("passwordpassword", "adminadminadminadmin"):
        raise ValueError("Use a unique administrator password at least 16 characters long")
    stored_hash = hash_password(password)
    del password, repeat
    base_domain = values.get("PANEL_DOMAIN", "ca1.iravand.ir")
    proposed = ".".join(base_domain.strip().lower().split(".")[-2:])
    current = values.get("CERT_ALLOWED_DOMAINS", "") if rotate else ""
    default = ("*" if rotate and values.get("CERT_ALLOW_ANY_DOMAIN") == "1"
               else current or proposed)
    print("Certificate domain policy: list allowed suffixes OR type * for ALL valid public DNS domains.")
    print("ALL-domains mode still requires administrator MFA and per-domain DNS TXT proof.")
    raw = input(f"Allowed domains (comma-separated) or * [{default}]: ").strip() or default
    if raw == "*":
        print("WARNING: certificates can be issued for ANY public DNS hostname with valid DNS proof.")
        if input("Type ALLOW ANY DOMAIN to confirm: ").strip() != "ALLOW ANY DOMAIN":
            raise RuntimeError("All-domains mode cancelled; no credentials or settings changed")
        validated, allow_any = "", "1"
    else:
        validated, allow_any = ",".join(domain_suffixes(raw)), "0"
    seed = new_totp_seed()
    generation = secrets.token_hex(32)
    content = assign(content, "ADMIN_PASSWORD_HASH", "'" + stored_hash + "'")
    content = assign(content, "ADMIN_TOTP_SECRET", "'" + seed + "'")
    content = assign(content, "ADMIN_SESSION_GENERATION", "'" + generation + "'")
    content = assign(content, "CERT_ALLOWED_DOMAINS", "'" + validated + "'")
    content = assign(content, "CERT_ALLOW_ANY_DOMAIN", allow_any)
    write_env(content)
    os.chmod(path, 0o600)
    print("\nAdministrator enrollment saved with permissions 0600.")
    print("Account: admin")
    print("TOTP account label: Iran CA Center (issuer: Iran CA Center)")
    print("TOTP secret (ONE-TIME DISPLAY, do NOT paste to chat or logs):")
    print(seed)
    print("Enter this secret into a trusted authenticator app as time-based, 6 digits, 30-second period, SHA1.")
    print("Save recovery instructions in encrypted offline storage. Protect .env and BACK IT UP securely.")
    print("NEXT: bash install.sh --private-https")
    print("Root/Issuing certificates, signing keys and SQLite issuance records were not replaced.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Enroll or rotate the single administrator with TOTP MFA")
    parser.add_argument("--rotate", action="store_true", help="Explicitly replace existing credentials")
    args = parser.parse_args()
    try:
        configure(ROOT / ".env", rotate=args.rotate)
    except (RuntimeError, ValueError, OSError, KeyboardInterrupt, EOFError) as exc:
        print(f"[security] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
