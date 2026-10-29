"""Security boundary regressions: anonymous, MFA, CSRF, allowlist, cookie and replay."""
from __future__ import annotations

import sqlite3
import time

import pytest
from fastapi.testclient import TestClient
from app.auth import (
    check_password, domain_permitted, domain_suffixes, hash_password, matching_totp_step,
    new_totp_seed, totp_for_step
)
from app.main import Settings, create_app
from scripts.init_ca import create_ca


@pytest.fixture
def secured(tmp_path):
    create_ca(tmp_path / "secret", b"security-root-password-123", b"security-issuer-password-123")
    seed = new_totp_seed()
    settings = Settings(
        db_path=tmp_path / "data" / "ca.db",
        ca_dir=tmp_path / "secret" / "online",
        ca_key_password="security-issuer-password-123",
        admin_password_hash=hash_password("secure-test-password-123456"),
        admin_totp_secret=seed, admin_session_generation="d" * 64,
        cert_allowed_domains="iravand.ir,example.org",
    )
    api = create_app(settings)
    api.state.dns_checker = lambda _name, _value: True
    with TestClient(api, base_url="https://testserver", follow_redirects=False) as client:
        yield client, settings, seed


def valid_code(seed):
    return totp_for_step(seed, int(time.time()) // 30)


def login(client, seed, password="secure-test-password-123456", code=None):
    return client.post("/api/auth/login", json={
        "username": "admin", "password": password,
        "code": code if code is not None else valid_code(seed)
    })


def test_password_hash_and_totp_validation():
    digest = hash_password("strong-private-admin-password")
    assert "strong-private-admin-password" not in digest
    assert check_password("strong-private-admin-password", digest)
    assert not check_password("incorrect-admin-password", digest)
    seed = new_totp_seed()
    now = int(time.time())
    assert matching_totp_step(seed, totp_for_step(seed, now // 30), now) == now // 30
    assert matching_totp_step(seed, "00000", now) is None


def test_anonymous_cannot_issue_read_challenges_or_download_secrets(secured):
    client, _, _ = secured
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/ca.pem").status_code == 200
    assert client.get("/api/system").status_code == 200
    assert client.get("/api/auth/status").json()["authenticated"] is False
    page = client.get("/")
    assert page.status_code == 303 and page.headers["location"] == "/login"
    assert client.get("/login").status_code == 200
    assert client.post("/api/requests", json={"domain": "example.org"}).status_code == 401
    assert client.get("/api/requests/guess").status_code == 401
    assert client.post("/api/requests/guess/verify").status_code == 401
    assert client.post("/api/requests/guess/issue-server").status_code == 401
    assert client.get("/api/downloads/guessedtoken").status_code == 401


def test_secure_cookie_csrf_and_logout(secured):
    client, _, seed = secured
    assert login(client, seed, password="wrong-password-123456").status_code == 401
    assert login(client, seed, code="12345X").status_code == 401
    result = login(client, seed)
    assert result.status_code == 200, result.text
    cookie = result.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    csrf = result.json()["csrf_token"]
    assert len(csrf) > 32
    assert client.get("/api/auth/status").json()["authenticated"] is True
    assert client.post("/api/requests", json={"domain":"example.org"}).status_code == 403
    assert client.post("/api/requests", json={"domain":"example.org"},
                       headers={"X-CSRF-Token": "forged"}).status_code == 403
    allowed = client.post("/api/requests", json={"domain":"example.org"},
                          headers={"X-CSRF-Token": csrf})
    assert allowed.status_code == 201, allowed.text
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/auth/status").json()["authenticated"] is False
    assert client.post("/api/requests", json={"domain":"example.org"},
                       headers={"X-CSRF-Token": csrf}).status_code == 401


def test_totp_cannot_be_replayed_after_success(secured):
    client, _, seed = secured
    code = valid_code(seed)
    assert login(client, seed, code=code).status_code == 200
    assert login(client, seed, code=code).status_code == 401


def test_allowlist_is_strict_domain_boundary(secured):
    client, _, seed = secured
    suffixes = domain_suffixes("iravand.ir,example.org")
    assert domain_permitted("ca1.iravand.ir", suffixes)
    assert domain_permitted("iravand.ir", suffixes)
    assert not domain_permitted("iravand.ir.evil.org", suffixes)
    assert not domain_permitted("evil-iravand.ir", suffixes)
    assert not domain_permitted("attacker.example.net", suffixes)
    assert login(client, seed).status_code == 200
    csrf = client.get("/api/auth/status").json()["csrf_token"]
    denied = client.post("/api/requests", json={"domain":"attacker.example.net"},
                         headers={"X-CSRF-Token": csrf})
    assert denied.status_code == 403
    allowed = client.post("/api/requests", json={"domain":"app.iravand.ir"},
                          headers={"X-CSRF-Token": csrf})
    assert allowed.status_code == 201


def test_existing_challenge_cannot_escape_new_allowlist(tmp_path):
    create_ca(tmp_path / "secret", b"security-root-password-123", b"security-issuer-password-123")
    seed = new_totp_seed()
    db = tmp_path / "data" / "ca.db"
    def config(allow):
        return Settings(db_path=db, ca_dir=tmp_path / "secret" / "online",
                        ca_key_password="security-issuer-password-123",
                        admin_password_hash=hash_password("secure-test-password-123456"),
                        admin_totp_secret=seed, admin_session_generation="e" * 64,
                        cert_allowed_domains=allow)
    api = create_app(config("example.org"))
    api.state.dns_checker = lambda *_: True
    with TestClient(api, base_url="https://testserver") as client:
        assert login(client, seed).status_code == 200
        csrf = client.get("/api/auth/status").json()["csrf_token"]
        rid = client.post("/api/requests", json={"domain":"example.org"},
                          headers={"X-CSRF-Token": csrf}).json()["request_id"]
        assert client.post("/api/requests/" + rid + "/verify",
                           headers={"X-CSRF-Token": csrf}).status_code == 200
    # No second MFA login needed: use direct authenticated session from old
    # generation, but switch the allowlist in app settings.
    api2 = create_app(config("iravand.ir"))
    api2.state.dns_checker = lambda *_: True
    with TestClient(api2, base_url="https://testserver") as client:
        # Retain a valid session before applying the new authorization policy
        # by inserting a token bound to this admin generation.
        from app.auth import SESSION_COOKIE
        import hashlib, secrets
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with sqlite3.connect(db) as con:
            con.execute("INSERT INTO admin_sessions(token_hash,csrf_token,generation,expires_at) "
                        "VALUES(?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), csrf,
                                           "e" * 64, int(time.time()) + 120))
        client.cookies.set(SESSION_COOKIE, token)
        response = client.post("/api/requests/" + rid + "/issue-server",
                               headers={"X-CSRF-Token": csrf})
        assert response.status_code == 403
        assert "authorized" in response.text


def test_unenrolled_admin_fail_closed_and_secrets_never_public(tmp_path):
    create_ca(tmp_path / "secret", b"security-root-password-123", b"security-issuer-password-123")
    api = create_app(Settings(db_path=tmp_path / "data" / "ca.db",
                              ca_dir=tmp_path / "secret" / "online",
                              ca_key_password="security-issuer-password-123"))
    with TestClient(api, base_url="https://testserver", follow_redirects=False) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/auth/status").json()["configured"] is False
        assert client.post("/api/auth/login", json={
            "username":"admin", "password":"unconfigured-password-123",
            "code":"123456"}).status_code == 503
        assert client.post("/api/requests", json={"domain":"example.org"}).status_code == 503
        assert client.get("/api/downloads/guess").status_code == 503
        assert "ADMIN_PASSWORD_HASH" not in client.get("/api/system").text
        assert "password" not in client.get("/api/system").text.lower()


def test_security_audit_excludes_credentials_and_bearer_secrets(secured):
    client, settings, seed = secured
    assert login(client, seed).status_code == 200
    csrf = client.get("/api/auth/status").json()["csrf_token"]
    client.post("/api/requests", json={"domain":"example.org"},
                headers={"X-CSRF-Token": csrf})
    with sqlite3.connect(settings.db_path) as con:
        events = con.execute("SELECT action,detail FROM security_audit").fetchall()
    assert any(a == "admin_login_success" for a, _ in events)
    assert any(a == "issuance_requested" for a, _ in events)
    assert "secure-test-password-123456" not in repr(events)
    assert seed not in repr(events)
    assert csrf not in repr(events)


def test_login_bruteforce_lockout_rejects_without_unbounded_audit(secured):
    client, settings, seed = secured
    for _ in range(10):
        assert login(client, seed, password="wrong-password-123456").status_code == 401
    before = None
    with sqlite3.connect(settings.db_path) as con:
        before = con.execute("SELECT COUNT(*) FROM security_audit").fetchone()[0]
    assert before == 10
    for _ in range(4):
        assert login(client, seed, password="wrong-password-123456").status_code == 429
    with sqlite3.connect(settings.db_path) as con:
        after = con.execute("SELECT COUNT(*) FROM security_audit").fetchone()[0]
    assert after == before, "Blocked login requests must not grow the security audit database"


def test_all_domains_opt_in_requires_admin_mfa_and_dns_ownership(tmp_path):
    """A broad domain policy must NOT allow anonymous or proof-free signing."""
    create_ca(tmp_path / "secret", b"security-root-password-123", b"security-issuer-password-123")
    seed = new_totp_seed()
    settings = Settings(
        db_path=tmp_path / "data" / "ca.db", ca_dir=tmp_path / "secret" / "online",
        ca_key_password="security-issuer-password-123",
        admin_password_hash=hash_password("secure-test-password-123456"),
        admin_totp_secret=seed, admin_session_generation="f" * 64,
        cert_allowed_domains="", cert_allow_any_domain=True,
    )
    api = create_app(settings)
    api.state.dns_checker = lambda *_: False
    with TestClient(api, base_url="https://testserver") as client:
        assert client.post("/api/requests", json={"domain": "other.example.com"}).status_code == 401
        assert login(client, seed).status_code == 200
        csrf = client.get("/api/auth/status").json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}
        for invalid in ("127.0.0.1", "*.example.org", "service.internal", "localhost", "one.local"):
            assert client.post("/api/requests", json={"domain": invalid}, headers=headers).status_code == 422
        first = client.post("/api/requests", json={"domain": "a.example.org"}, headers=headers)
        assert first.status_code == 201, first.text
        rid = first.json()["request_id"]
        # No certificate may be signed before real DNS TXT proof (even in all-domains mode).
        assert client.post(f"/api/requests/{rid}/issue-server", headers=headers).status_code == 403
        assert client.post(f"/api/requests/{rid}/verify", headers=headers).status_code == 422
        api.state.dns_checker = lambda *_: True
        assert client.post(f"/api/requests/{rid}/verify", headers=headers).status_code == 200
        api.state.dns_checker = lambda *_: False
        assert client.post(f"/api/requests/{rid}/issue-server", headers=headers).status_code == 403
        api.state.dns_checker = lambda *_: True
        issued = client.post(f"/api/requests/{rid}/issue-server", headers=headers)
        assert issued.status_code == 201, issued.text
        assert issued.json()["domain"] == "a.example.org"
        # No free-form, unauthenticated download even with the capability URL.
        client.cookies.clear()
        assert client.get(issued.json()["download_url"]).status_code == 401


def test_all_domains_flag_defaults_off_and_rejects_invalid_configuration(monkeypatch):
    monkeypatch.delenv("CERT_ALLOW_ANY_DOMAIN", raising=False)
    assert Settings.from_env().cert_allow_any_domain is False
    assert domain_permitted("example.org", (), allow_any=False) is False
    assert domain_permitted("example.org", (), allow_any=True) is True
    for value in ("true", "yes", "*", "", "2"):
        monkeypatch.setenv("CERT_ALLOW_ANY_DOMAIN", value)
        with pytest.raises(ValueError, match="CERT_ALLOW_ANY_DOMAIN"):
            Settings.from_env()
    monkeypatch.setenv("CERT_ALLOW_ANY_DOMAIN", "1")
    assert Settings.from_env().cert_allow_any_domain is True
    monkeypatch.setenv("CERT_ALLOW_ANY_DOMAIN", "0")
    assert Settings.from_env().cert_allow_any_domain is False


def test_without_all_domains_flag_empty_allowlist_fails_closed(secured):
    client, settings, seed = secured
    # The helper is only allowed to relax the issuer boundary with an explicit flag.
    assert not domain_permitted("some-other.net", (), allow_any=False)
    assert not domain_permitted("some-other.net", ("iravand.ir",), allow_any=False)
    assert domain_permitted("deep.other.net", (), allow_any=True)
