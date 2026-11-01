"""Test administrator enrollment can target the isolated dotenv without touching live credentials."""
from __future__ import annotations

import io
from pathlib import Path

import install
from scripts import setup_admin


class TTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_test_admin_enrollment_writes_only_test_env(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_admin, "ROOT", tmp_path)
    monkeypatch.setattr(install, "ROOT", tmp_path)
    monkeypatch.setattr(install, "ENV_FILE", tmp_path / ".env")

    live_env = tmp_path / ".env"
    live_content = "CA_KEY_PASSWORD='live-issuer-secret-value'\n"
    live_env.write_text(live_content, encoding="utf-8")

    test_env = tmp_path / ".env.test"
    test_env.write_text(
        "CA_KEY_PASSWORD='test-issuer-secret-value'\n"
        "PANEL_DOMAIN=ca-panel-test.example.org\n"
        "CA_DISPLAY_NAME='CA Panel Test'\n"
        "CA_ORGANIZATION='Test Lab'\n"
        "ADMIN_PASSWORD_HASH=\nADMIN_TOTP_SECRET=\nADMIN_SESSION_GENERATION=\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(setup_admin.sys, "stdin", TTY(""))
    monkeypatch.setattr(setup_admin.sys, "stdout", TTY(""))
    passwords = iter(["a-unique-test-admin-password-2026", "a-unique-test-admin-password-2026"])
    monkeypatch.setattr(setup_admin.getpass, "getpass", lambda _prompt: next(passwords))
    answers = iter(["example.org"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(setup_admin, "new_totp_seed", lambda: "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP")
    monkeypatch.setattr(setup_admin.secrets, "token_hex", lambda _n: "c" * 64)

    setup_admin.configure(test_env, rotate=False)

    assert live_env.read_text(encoding="utf-8") == live_content
    updated = test_env.read_text(encoding="utf-8")
    assert "CA_KEY_PASSWORD='test-issuer-secret-value'" in updated
    assert "ADMIN_PASSWORD_HASH='" in updated
    assert "ADMIN_TOTP_SECRET='JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'" in updated
    assert "ADMIN_SESSION_GENERATION='" + "c" * 64 + "'" in updated
    assert "CERT_ALLOWED_DOMAINS='example.org'" in updated
    assert test_env.stat().st_mode & 0o777 == 0o600


def test_admin_enrollment_rejects_other_env_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_admin, "ROOT", tmp_path)
    monkeypatch.setattr(setup_admin.sys, "stdin", TTY(""))
    monkeypatch.setattr(setup_admin.sys, "stdout", TTY(""))
    outside = tmp_path.parent / ".env.test"
    outside.write_text("CA_KEY_PASSWORD='not-used'\n", encoding="utf-8")

    import pytest
    with pytest.raises(RuntimeError, match="project root"):
        setup_admin.configure(outside, rotate=False)
