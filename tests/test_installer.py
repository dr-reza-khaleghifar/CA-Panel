"""First-run installer regression tests; no Docker daemon, network, or private CA required."""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

import install


def prepare(tmp_path: Path, monkeypatch, *, existing_env: str | None = None):
    monkeypatch.setattr(install, "ROOT", tmp_path)
    monkeypatch.setattr(install, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(install, "ENV_SAMPLE", tmp_path / ".env.example")
    (tmp_path / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text(
        "APP_UID=1000\nAPP_GID=1000\nCA_KEY_PASSWORD=REPLACE_WITH_ISSUING_CA_PASSPHRASE\n",
        encoding="utf-8",
    )
    if existing_env is not None:
        (tmp_path / ".env").write_text(existing_env, encoding="utf-8")
    online = tmp_path / "secrets" / "online"
    online.mkdir(parents=True)
    for filename in install.ONLINE_FILES:
        (online / filename).write_text("test fixture, NOT private CA material", encoding="utf-8")
    monkeypatch.setattr(install, "check_prerequisites", lambda **kwargs: None)
    monkeypatch.setattr(install, "maybe_check_issuer_password", lambda *args: None)
    monkeypatch.setattr(sys, "argv", ["install.py", "--no-start"])
    monkeypatch.chdir(tmp_path)


def test_first_setup_creates_private_env_and_preserves_certs(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(install, "prompt_secret", lambda *args: "aGoodSecret$Hash#1234")
    before = {name: (tmp_path / "secrets" / "online" / name).read_bytes()
              for name in install.ONLINE_FILES}
    assert install.main() == 0
    created = tmp_path / ".env"
    assert created.exists()
    assert stat.S_IMODE(created.stat().st_mode) == 0o600
    content = created.read_text(encoding="utf-8")
    assert "CA_KEY_PASSWORD='aGoodSecret$Hash#1234'" in content
    assert f"APP_UID={os.getuid()}" in content
    assert f"APP_GID={os.getgid()}" in content
    for name, original in before.items():
        assert (tmp_path / "secrets" / "online" / name).read_bytes() == original


def test_existing_env_kept_byte_for_byte(tmp_path, monkeypatch):
    contents = "CA_KEY_PASSWORD='knownPassword$123456'\nCERT_VALIDITY_DAYS=7\n"
    prepare(tmp_path, monkeypatch, existing_env=contents)
    monkeypatch.setattr(install, "prompt_secret",
                        lambda *args: pytest.fail("An existing secret must never be prompted or replaced"))
    original = (tmp_path / ".env").read_bytes()
    assert install.main() == 0
    assert (tmp_path / ".env").read_bytes() == original


def test_missing_ca_files_causes_no_change(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch)
    (tmp_path / "secrets" / "online" / "issuer-key.pem").unlink()
    with pytest.raises(RuntimeError, match="Missing existing Issuing CA"):
        install.main()
    assert not (tmp_path / ".env").exists()


def test_dry_check_does_not_create_env(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["install.py", "--check"])
    with pytest.raises(RuntimeError, match="CA_KEY_PASSWORD"):
        install.main()
    assert not (tmp_path / ".env").exists()


def test_new_ca_mode_refuses_overwriting_existing_password(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch, existing_env="CA_KEY_PASSWORD='existingPassword123'\n")
    monkeypatch.setattr(sys, "argv", ["install.py", "--init-ca"])
    monkeypatch.setattr(install, "generate_ca",
                        lambda: pytest.fail("Do not generate a new CA over existing configured CA"))
    with pytest.raises(RuntimeError, match="Refusing to replace"):
        install.main()


def test_env_serialization_does_not_interpolate_dollar():
    secret = "ThisIsASafe$Password#7"
    serial = install.dotenv_secret(secret)
    assert serial == "'" + secret + "'"
    assert install.env_values("CA_KEY_PASSWORD=" + serial)["CA_KEY_PASSWORD"] == secret
    for unsafe in ["short", "Contains'QuoteAndLong", "Contains\\BackslashLong"]:
        with pytest.raises(RuntimeError):
            install.dotenv_secret(unsafe)


def test_env_parser_never_executes_shell_and_rejects_traversal():
    content = "CA_KEY_PASSWORD='abc$(touch /tmp/nope)'\nCA_ISSUER_KEY_FILE=../evil.pem\n"
    values = install.env_values(content)
    assert values["CA_KEY_PASSWORD"] == "abc$(touch /tmp/nope)"
    with pytest.raises(RuntimeError, match="CA_ISSUER_KEY_FILE"):
        install.validate_filenames(values)
    assert install.assign("A=old\n", "A", "new") == "A=new\n"
    with pytest.raises(RuntimeError, match="Duplicate"):
        install.assign("A=1\nA=2\n", "A", "new")


def test_offline_root_key_blocks_auto_start(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch, existing_env="CA_KEY_PASSWORD='knownPassword123'\n")
    root = tmp_path / "secrets" / "offline"
    root.mkdir(parents=True)
    (root / "root-key.pem").write_text("offline root key must leave the server", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["install.py"])
    # The guard must trigger before attempting a Docker start.
    monkeypatch.setattr(install, "run",
                        lambda *args, **kwargs: pytest.fail("Must not run Docker with Root key on host"))
    with pytest.raises(RuntimeError, match="Offline Root CA private key"):
        install.main()


def test_no_forced_recreate_for_idempotent_restart(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch, existing_env="CA_KEY_PASSWORD='knownPassword123'\n")
    commands = []
    monkeypatch.setattr(sys, "argv", ["install.py"])
    monkeypatch.setattr(install, "run", lambda *args, **kwargs: commands.append(args))
    monkeypatch.setattr(install, "check_health", lambda: True)
    assert install.main() == 0
    assert ("docker", "compose", "up", "-d", "--build", "api") in commands
    assert all("--force-recreate" not in cmd for cmd in commands)
