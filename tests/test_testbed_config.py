"""Static safety contracts for the separate loopback-only CA testbed."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_testbed_compose_is_a_distinct_loopback_only_project():
    compose = (ROOT / "compose.test.yaml").read_text(encoding="utf-8")
    assert "name: ca-panel-testbed" in compose
    assert "127.0.0.1:${TEST_API_PORT:-18080}:8000" in compose
    assert "127.0.0.1:${TEST_HTTPS_PORT:-18443}:8443" in compose
    assert "${CA_ONLINE_HOST_DIR:-./.testbed/pki/online}:/run/ca-test:ro" in compose
    assert "${DATA_HOST_DIR:-./.testbed/data}:/data" in compose
    assert "secrets/online" not in compose
    assert "- ./data:/data" not in compose
    assert "${DATA_HOST_DIR:-./data}" not in compose
    assert "0.0.0.0:" not in compose
    assert '"80:80"' not in compose
    assert '"443:443"' not in compose


def test_testbed_credentials_and_state_are_ignored_by_git_and_docker():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert ".env.test" in gitignore and ".testbed/" in gitignore
    assert ".env.test" in dockerignore and ".testbed" in dockerignore


def test_test_caddy_config_has_tls_only_and_no_public_automation():
    caddy = (ROOT / "Caddyfile.test").read_text(encoding="utf-8")
    assert "https://{$PANEL_DOMAIN}:8443" in caddy
    assert "tls /etc/caddy/tls/fullchain.pem /etc/caddy/tls/privkey.pem" in caddy
    assert "http://" not in caddy
