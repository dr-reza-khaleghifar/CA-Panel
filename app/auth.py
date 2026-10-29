"""Private CA admin authentication: PBKDF2, RFC6238 MFA, replay protection, CSRF."""
from __future__ import annotations
import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from pathlib import Path

PASSWORD_ITERATIONS = 600_000
SESSION_SECONDS = 8 * 3600
FAILED_WINDOW = 15 * 60
FAILED_LIMIT = 10
SESSION_COOKIE = "iran_ca_session"


class LoginRateLimited(Exception):
    """Too many recent administrator login failures; do not expand audit logs."""


HASH_PATTERN = re.compile(r"^pbkdf2_sha256\$(\d{6,8})\$([0-9a-f]{32})\$([0-9a-f]{64})$")
DOMAIN_PATTERN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")

def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if not 16 <= len(password) <= 1024: raise ValueError("Admin password must contain 16-1024 characters")
    salt = salt if salt is not None else secrets.token_bytes(16)
    if len(salt) != 16: raise ValueError("Invalid password salt")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return "pbkdf2_sha256$" + str(PASSWORD_ITERATIONS) + "$" + salt.hex() + "$" + digest.hex()

def check_password(password: str, stored: str) -> bool:
    match = HASH_PATTERN.fullmatch(stored)
    if not match: return False
    iterations = int(match.group(1))
    if not 600_000 <= iterations <= 2_000_000: return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(match.group(2)), iterations)
    return hmac.compare_digest(actual, bytes.fromhex(match.group(3)))

def new_totp_seed() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")

def validate_totp_seed(value: str) -> bool:
    if not re.fullmatch(r"[A-Z2-7]{32}", value): return False
    try: return len(base64.b32decode(value, casefold=False)) == 20
    except ValueError: return False

def totp_for_step(seed: str, step: int) -> str:
    secret = base64.b32decode(seed, casefold=False)
    digest = hmac.new(secret, step.to_bytes(8, "big"), hashlib.sha1).digest()
    pos = digest[-1] & 15
    value = int.from_bytes(digest[pos:pos+4], "big") & 0x7fffffff
    return f"{value % 1_000_000:06d}"

def matching_totp_step(seed: str, code: str, now: int | None = None) -> int | None:
    if not re.fullmatch(r"[0-9]{6}", code): return None
    step = (int(time.time()) if now is None else now) // 30
    matches = [(step + shift, hmac.compare_digest(totp_for_step(seed, step + shift), code))
               for shift in (-1, 0, 1)]
    accepted = [candidate for candidate, match in matches if match]
    return max(accepted) if accepted else None

def domain_suffixes(raw: str) -> tuple[str, ...]:
    parts = [part.strip().lower().rstrip(".") for part in raw.split(",")]
    if not parts or len(parts) > 30 or any(not DOMAIN_PATTERN.fullmatch(p) for p in parts):
        raise ValueError("CERT_ALLOWED_DOMAINS must specify 1-30 DNS domain suffixes")
    return tuple(dict.fromkeys(parts))

def domain_permitted(domain: str, suffixes: tuple[str, ...], *, allow_any: bool = False) -> bool:
    """Optional admin-approved exception; caller must first normalize DNS names.

    This flag never bypasses authentication, DNS TXT proof or signing checks.
    """
    return allow_any or any(domain == name or domain.endswith("." + name) for name in suffixes)

def initialize_auth_db(db: Path) -> None:
    with sqlite3.connect(db, timeout=10) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS admin_sessions (
                token_hash TEXT PRIMARY KEY, csrf_token TEXT NOT NULL,
                generation TEXT NOT NULL, expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS admin_login_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_admin_login_failure_time
                ON admin_login_failures(created_at);
            CREATE TABLE IF NOT EXISTS admin_mfa_state (
                id INTEGER PRIMARY KEY CHECK(id=1), last_step INTEGER NOT NULL
            );
            INSERT OR IGNORE INTO admin_mfa_state (id,last_step) VALUES (1,-1);
            CREATE TABLE IF NOT EXISTS security_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL,
                action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT ''
            );
        """)

def audit(db: Path, action: str, detail: str = "") -> None:
    if not re.fullmatch(r"[a-z_]{2,60}", action) or len(detail) > 254:
        raise ValueError("Invalid security audit event")
    with sqlite3.connect(db, timeout=10) as con:
        con.execute("INSERT INTO security_audit(created_at,action,detail) VALUES(?,?,?)",
                    (int(time.time()), action, detail))

def authenticate(db: Path, *, username: str, password: str, code: str,
                 stored_hash: str, seed: str, generation: str) -> tuple[str, str] | None:
    """Global login throttle and atomic TOTP replay rejection."""
    now = int(time.time())
    with sqlite3.connect(db, timeout=10) as con:
        con.execute("BEGIN IMMEDIATE")
        con.execute("DELETE FROM admin_login_failures WHERE created_at < ?", (now - FAILED_WINDOW,))
        if con.execute("SELECT COUNT(*) FROM admin_login_failures").fetchone()[0] >= FAILED_LIMIT:
            con.commit()
            raise LoginRateLimited("Administrator login is temporarily rate-limited")
        counter = matching_totp_step(seed, code, now)
        verified = (hmac.compare_digest(username.encode(), b"admin") and
                    len(password) <= 1024 and check_password(password, stored_hash) and counter is not None)
        if verified:
            cur = con.execute("UPDATE admin_mfa_state SET last_step=? WHERE id=1 AND last_step<?",
                              (counter, counter))
            verified = cur.rowcount == 1
        if not verified:
            con.execute("INSERT INTO admin_login_failures(created_at) VALUES(?)", (now,))
            con.commit()
            return None
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        con.execute("DELETE FROM admin_sessions WHERE expires_at <= ? OR generation != ?", (now, generation))
        con.execute("DELETE FROM admin_login_failures")
        con.execute("INSERT INTO admin_sessions(token_hash,csrf_token,generation,expires_at) VALUES(?,?,?,?)",
                    (hashlib.sha256(token.encode()).hexdigest(), csrf, generation, now + SESSION_SECONDS))
        con.commit()
        return token, csrf

def get_session(db: Path, cookie: str | None, generation: str) -> str | None:
    if not cookie or len(cookie) > 256 or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", cookie): return None
    with sqlite3.connect(db, timeout=10) as con:
        row = con.execute("SELECT csrf_token,expires_at,generation FROM admin_sessions WHERE token_hash=?",
                          (hashlib.sha256(cookie.encode()).hexdigest(),)).fetchone()
    if not row or row[1] <= int(time.time()) or not hmac.compare_digest(row[2], generation): return None
    return row[0]

def end_session(db: Path, cookie: str | None) -> None:
    if cookie and re.fullmatch(r"[A-Za-z0-9_-]{32,128}", cookie):
        with sqlite3.connect(db, timeout=10) as con:
            con.execute("DELETE FROM admin_sessions WHERE token_hash=?",
                        (hashlib.sha256(cookie.encode()).hexdigest(),))
