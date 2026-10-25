#!/usr/bin/env python3
"""First-run installer for CA-Panel (macOS / Linux, Docker Compose v2).

Usage:
  python3 install.py                    # Existing Issuing CA: configure and start
  python3 install.py --init-ca          # Generate a NEW CA on a trusted admin machine
  python3 install.py --no-start         # Prepare .env and local folders without Docker start
  python3 install.py --check            # Read-only readiness checks

NEVER regenerate or overwrite existing CA keys, certificates, database or .env.
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
ENV_SAMPLE = ROOT / ".env.example"
ONLINE_FILES = ("issuer-key.pem", "issuer-cert.pem", "root-cert.pem")


def fail(message: str) -> None:
    raise RuntimeError(message)


def info(message: str) -> None:
    print(f"[CA-Panel] {message}", flush=True)


def run(*command: str, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        command, cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def env_values(contents: str) -> dict[str, str]:
    """Read just simple Compose dotenv assignments; NEVER source/eval .env in shell."""
    values: dict[str, str] = {}
    for line in contents.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", stripped)
        if not match:
            continue
        key, value = match.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def dotenv_secret(secret: str) -> str:
    """Single-quoted Compose dotenv value prevents $VAR interpolation."""
    if any(char in secret for char in ("'", "\\", "\n", "\r", "\x00")):
        fail("Issuer passphrase contains quotes/backslashes/control characters. "
             "Set CA_KEY_PASSWORD manually in .env with correct Compose quoting.")
    if not secret or len(secret) < 12:
        fail("Issuing CA passphrase must contain at least 12 characters")
    return "'" + secret + "'"


def assign(contents: str, key: str, value: str) -> str:
    lines = contents.splitlines(keepends=True)
    matcher = re.compile(r"^\s*(?:export\s+)?" + re.escape(key) + r"\s*=")
    positions = [i for i, line in enumerate(lines) if matcher.match(line)]
    if len(positions) > 1:
        fail(f"Duplicate {key} assignments in .env; resolve manually before installation")
    entry = f"{key}={value}\n"
    if positions:
        lines[positions[0]] = entry
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(entry)
    return "".join(lines)


def write_env(contents: str) -> None:
    """Atomic, mode-0600 write; existing file is never overwritten without necessity."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=ROOT, prefix=".env.install-",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, ENV_FILE)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def configured_path(value: str, default: str) -> Path:
    given = value.strip() or default
    if "$" in given or "\n" in given or "\r" in given:
        fail("Host mount paths in .env must be literal, without variables or newlines")
    result = Path(given).expanduser()
    return (ROOT / result if not result.is_absolute() else result).resolve()


def validate_filenames(values: dict[str, str]) -> tuple[str, str, str]:
    keys = ("CA_ISSUER_KEY_FILE", "CA_ISSUER_CERT_FILE", "CA_ROOT_CERT_FILE")
    for key, filename in zip(keys, ONLINE_FILES):
        v = values.get(key, filename)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.pem", v):
            fail(f"Invalid {key}: expected a local PEM filename, not a path")
    return tuple(values.get(key, default) for key, default in zip(keys, ONLINE_FILES))


def prompt_secret(label: str, *, repeat: bool = False) -> str:
    if not sys.stdin.isatty():
        fail("Secret prompts require an interactive terminal (TTY)")
    try:
        first = getpass.getpass(f"{label} (hidden): ")
        if repeat:
            second = getpass.getpass(f"Repeat {label}: ")
            if first != second:
                fail("Passphrases do not match; no changes made")
    except (EOFError, KeyboardInterrupt):
        fail("Password entry cancelled")
    return first


def check_prerequisites(*, docker: bool, crypto: bool) -> None:
    if docker:
        if shutil.which("docker") is None:
            fail("Docker not found. Install Docker Desktop or Docker Engine + Compose v2.")
        try:
            run("docker", "compose", "version", capture=True)
            run("docker", "info", "--format", "{{.ServerVersion}}", capture=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            fail("Docker daemon / Compose v2 is not ready; start Docker and retry")
    if crypto:
        try:
            import cryptography  # noqa: F401
        except ImportError as exc:
            fail("Python cryptography package is needed to create a CA. "
                 "On the trusted admin machine, use: "
                 "python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt; "
                 "then run .venv/bin/python install.py --init-ca") from exc


def generate_ca() -> str:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from scripts.init_ca import create_ca

    output = ROOT / "secrets"
    if any((output / "online" / name).exists() for name in ONLINE_FILES):
        fail("Issuing CA files already exist. Refusing to regenerate or overwrite them.")
    if (output / "offline").exists() or (output / "online").exists():
        fail("Partial CA directories exist. Investigate before any new CA generation.")
    if not sys.stdin.isatty():
        fail("--init-ca requires an interactive terminal")
    print("\nSECURITY WARNING: A new Root CA private key will be created ON THIS MACHINE.")
    print("Use a trusted administration workstation, NOT a public production server.")
    print("You must move secrets/offline/ to secure OFFLINE storage before deployment.")
    answer = input("To create a NEW CA, type CREATE NEW CA: ").strip()
    if answer != "CREATE NEW CA":
        fail("CA creation cancelled; no existing keys were changed")
    root_pass = prompt_secret("NEW Root CA passphrase (12+ characters)", repeat=True)
    issuer_pass = prompt_secret("NEW Issuing CA passphrase (12+ characters)", repeat=True)
    if len(root_pass) < 12 or len(issuer_pass) < 12 or root_pass == issuer_pass:
        fail("Passphrases must differ and each contain at least 12 characters")
    dotenv_secret(issuer_pass)
    create_ca(output, root_pass.encode("utf-8"), issuer_pass.encode("utf-8"))
    cert = x509.load_pem_x509_certificate((output / "online" / "root-cert.pem").read_bytes())
    info("Root certificate SHA-256 (save and verify independently): "
         + cert.fingerprint(hashes.SHA256()).hex().upper())
    return issuer_pass


def assert_ca_files(online: Path, filenames: tuple[str, str, str]) -> None:
    available = [online / name for name in filenames]
    if any(not file.is_file() for file in available):
        fail("Missing existing Issuing CA files. Expected: "
             + ", ".join(str(file) for file in available)
             + ". Provision these securely or run --init-ca ON A TRUSTED WORKSTATION.")
    for path in available:
        if path.is_symlink():
            fail(f"Refusing symlink for CA file: {path}")


def maybe_check_issuer_password(online: Path, filename: str, password: str) -> None:
    # An existing CA can run without cryptography on the HOST; startup validates
    # the key inside Docker. When installed, catch password mismatches earlier.
    try:
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        return
    try:
        serialization.load_pem_private_key(
            (online / filename).read_bytes(), password=password.encode("utf-8")
        )
    except (ValueError, TypeError) as exc:
        fail("Issuing CA key cannot be decrypted with the configured password. "
             "Check CA_KEY_PASSWORD (not the Root CA password).") from exc


def check_health() -> bool:
    for _ in range(15):
        try:
            with urlopen("http://127.0.0.1:8080/healthz", timeout=2) as response:
                if response.status == 200 and b'"status":"ok"' in response.read():
                    return True
        except (OSError, URLError):
            pass
        time.sleep(1.5)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe first-run setup for CA-Panel")
    parser.add_argument("--init-ca", action="store_true",
                        help="Generate a NEW private CA on trusted workstation; never overwrite keys")
    parser.add_argument("--no-start", action="store_true",
                        help="Prepare only; do not run Docker Compose")
    parser.add_argument("--check", action="store_true",
                        help="Only check prerequisites, configured paths and CA files")
    args = parser.parse_args()
    if args.check and args.init_ca:
        parser.error("--check and --init-ca cannot be combined")
    os.chdir(ROOT)
    if not ENV_SAMPLE.is_file() or not (ROOT / "compose.yaml").is_file():
        fail("Run this installer from a complete CA-Panel repository checkout")

    # On --init-ca, allow the initial key-generation step before requiring Docker.
    check_prerequisites(docker=not (args.no_start or args.init_ca or args.check),
                        crypto=args.init_ca)
    if ENV_FILE.is_symlink():
        fail(".env must be a normal file, not a symlink")
    original = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else None
    content = original if original is not None else ENV_SAMPLE.read_text(encoding="utf-8")
    if original is None:
        content = assign(content, "APP_UID", str(os.getuid()))
        content = assign(content, "APP_GID", str(os.getgid()))
        if sys.stdin.isatty() and not args.check:
            for key, default, question in (
                ("CA_DISPLAY_NAME", "CA-Panel", "Panel display name"),
                ("CA_ORGANIZATION", "Private CA", "Organization label"),
            ):
                answer = input(f"{question} [{default}]: ").strip()
                if not answer:
                    continue
                if (len(answer) > 100 or any(ord(c) < 32 or ord(c) == 127 for c in answer)
                        or "'" in answer or "\\" in answer):
                    fail(f"Invalid {key}: use at most 100 printable characters without quotes/backslashes")
                content = assign(content, key, "'" + answer + "'")
    values = env_values(content)
    online = configured_path(values.get("CA_ONLINE_HOST_DIR", ""), "./secrets/online")
    data = configured_path(values.get("DATA_HOST_DIR", ""), "./data")
    filenames = validate_filenames(values)

    if args.init_ca:
        if original is not None and values.get("CA_KEY_PASSWORD", "") not in (
            "", "REPLACE_WITH_ISSUING_CA_PASSPHRASE",
        ):
            fail("Existing .env already contains an Issuing CA password. "
                 "Refusing to replace it during --init-ca; back up and review manually.")
        if online != (ROOT / "secrets" / "online").resolve():
            fail("--init-ca uses the default secrets/online location; "
                 "for custom mounts, create/import your CA manually")
        issuer_password = generate_ca()
        content = assign(content, "CA_KEY_PASSWORD", dotenv_secret(issuer_password))
        write_env(content)
        info(".env created/updated with Issuing CA password (mode 0600).")
        info("NEXT: Move secrets/offline to secure OFFLINE storage and back it up.")
        info("Only after that, run: python3 install.py")
        return 0

    assert_ca_files(online, filenames)
    secret = values.get("CA_KEY_PASSWORD", "")
    if not secret or secret == "REPLACE_WITH_ISSUING_CA_PASSPHRASE":
        if args.check:
            fail("CA_KEY_PASSWORD missing or placeholder in .env")
        secret = prompt_secret("Existing Issuing CA passphrase (NOT Root CA)")
        content = assign(content, "CA_KEY_PASSWORD", dotenv_secret(secret))
        values = env_values(content)

    # Compose reads exported shell variables before .env; prevent silent override.
    if os.getenv("CA_KEY_PASSWORD") and os.getenv("CA_KEY_PASSWORD") != secret:
        fail("Shell CA_KEY_PASSWORD overrides .env with a different value. "
             "Unset it or correct it before running.")
    if args.check:
        maybe_check_issuer_password(online, filenames[0], secret)
        info("CA files and .env values passed read-only checks.")
        return 0

    maybe_check_issuer_password(online, filenames[0], secret)
    if content != original:
        write_env(content)
        info(".env saved with private permissions (0600); existing values preserved.")
    else:
        current_mode = stat.S_IMODE(ENV_FILE.stat().st_mode)
        if current_mode & 0o077:
            ENV_FILE.chmod(0o600)
            info("Restricted .env permissions to owner only.")
        else:
            info("Existing .env preserved; no password or setting overwritten.")

    if not args.no_start and (ROOT / "secrets" / "offline" / "root-key.pem").is_file():
        fail("Offline Root CA private key is still inside this project. "
             "Move secrets/offline/ to protected OFFLINE storage before starting the service.")
    if data.exists() and (data.is_symlink() or not data.is_dir()):
        fail("DATA_HOST_DIR is not a regular directory")
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not args.no_start:
        check_prerequisites(docker=True, crypto=False)
        info("Building and launching CA-Panel API with Docker Compose...")
        run("docker", "compose", "up", "-d", "--build", "api")
        if not check_health():
            fail("Docker launch requested but /healthz is not healthy. "
                 "Run: docker compose ps && docker compose logs --tail=80 api")
        info("SUCCESS: CA-Panel is healthy at http://127.0.0.1:8080")
        info("Public CA metadata: http://127.0.0.1:8080/api/system")
    else:
        info("Configuration prepared; run: docker compose up -d --build api")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"[CA-Panel] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
