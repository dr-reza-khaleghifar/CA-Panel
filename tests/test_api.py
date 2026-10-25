from datetime import datetime, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from app.main import Settings, certificate_for_domain, create_app, normalize_domain, connect
from scripts.init_ca import create_ca


def csr_for(domain, san=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
    if san is not None:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]), critical=False)
    csr = builder.sign(key, hashes.SHA256())
    return csr.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture
def client(tmp_path):
    create_ca(tmp_path / 'secrets', b'long-root-test-passphrase', b'long-issuer-test-passphrase')
    settings = Settings(db_path=tmp_path / 'data' / 'panel.db', ca_dir=tmp_path / 'secrets' / 'online', ca_key_password='long-issuer-test-passphrase', max_requests_per_hour=3)
    api = create_app(settings)
    api.state.dns_checker = lambda _name, _value: True
    with TestClient(api) as test_client:
        yield test_client


def test_domain_normalization():
    assert normalize_domain('https://www.example.com/abc') == 'www.example.com'
    assert normalize_domain('bücher.de') == 'xn--bcher-kva.de'
    for bad in ['localhost', 'example.local', '127.0.0.1', '*.example.com', 'evil.com/a', 'co', 'admin@test.com']:
        with pytest.raises(ValueError):
            normalize_domain(bad)


def test_issue_end_to_end(client):
    result = client.post('/api/requests', json={'domain':'example.org'})
    assert result.status_code == 201, result.text
    data = result.json()
    assert data['dns_name'] == '_ca-panel.example.org'
    assert data['dns_value'].startswith('ca-panel-verification=')
    rid = data['request_id']
    assert client.post(f'/api/requests/{rid}/issue', json={'csr_pem':csr_for('example.org')}).status_code == 403
    assert client.post(f'/api/requests/{rid}/verify').json()['verified']
    resp = client.post(f'/api/requests/{rid}/issue', json={'csr_pem':csr_for('example.org', 'example.org')})
    assert resp.status_code == 201, resp.text
    cert = x509.load_pem_x509_certificate(resp.json()['certificate_pem'].encode())
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'example.org'
    assert cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    assert cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName) == ['example.org']
    assert cert.not_valid_after_utc > datetime.now(timezone.utc)
    assert client.get(f'/api/requests/{rid}/certificate').status_code == 200
    assert client.get('/api/ca.pem').status_code == 200
    assert client.post(f'/api/requests/{rid}/issue', json={'csr_pem':csr_for('example.org')}).status_code == 409


def test_cannot_issue_other_domain_or_extra_sans(client):
    rid = client.post('/api/requests', json={'domain':'example.org'}).json()['request_id']
    client.post(f'/api/requests/{rid}/verify')
    assert client.post(f'/api/requests/{rid}/issue', json={'csr_pem':csr_for('evil.org')}).status_code == 422
    assert client.post(f'/api/requests/{rid}/issue', json={'csr_pem':csr_for('example.org', 'evil.org')}).status_code == 422


def test_dns_proof_enforced(client):
    client.app.state.dns_checker = lambda name, expected: False
    rid = client.post('/api/requests', json={'domain':'example.org'}).json()['request_id']
    assert client.post(f'/api/requests/{rid}/verify').status_code == 422
    assert client.post(f'/api/requests/{rid}/issue', json={'csr_pem':csr_for('example.org')}).status_code == 403
    client.app.state.dns_checker = lambda name, expected: True
    assert client.post(f'/api/requests/{rid}/verify').status_code == 200
    client.app.state.dns_checker = lambda name, expected: False
    assert client.post(f'/api/requests/{rid}/issue', json={'csr_pem':csr_for('example.org')}).status_code == 403


def test_rate_limit(client):
    assert client.post('/api/requests', json={'domain':'a.example.org'}).status_code == 201
    assert client.post('/api/requests', json={'domain':'b.example.org'}).status_code == 201
    assert client.post('/api/requests', json={'domain':'c.example.org'}).status_code == 201
    assert client.post('/api/requests', json={'domain':'d.example.org'}).status_code == 429


def test_security_headers(client):
    r = client.get('/')
    assert r.status_code == 200
    assert 'frame-ancestors' in r.headers['content-security-policy']
    assert r.headers['cache-control'] == 'no-store'


def test_incorrect_issuer_passphrase_gives_actionable_error(tmp_path):
    create_ca(tmp_path / "secrets", b"long-root-test-passphrase", b"long-issuer-test-passphrase")
    settings = Settings(
        db_path=tmp_path / "data" / "panel.db",
        ca_dir=tmp_path / "secrets" / "online",
        ca_key_password="incorrect-passphrase",
    )
    with pytest.raises(RuntimeError, match="Issuing CA"):
        with TestClient(create_app(settings)):
            pass


def test_dns_debug_exact_match_and_chunked_txt():
    from app.dns_debug import probe_txt

    class TXT:
        strings = [b"ca-panel-verification=", b"abc123"]

    class Resolver:
        def resolve(self, name, rdtype, search):
            assert (name, rdtype, search) == ("_ca-panel.example.org.", "TXT", False)
            return [TXT()]

    matched, values, error = probe_txt("_ca-panel.example.org.", "ca-panel-verification=abc123", Resolver())
    assert matched is True
    assert values == ["ca-panel-verification=abc123"]
    assert error is None
    assert probe_txt("_ca-panel.example.org.", "ca-panel-verification=old-token", Resolver())[0] is False


def test_configured_dns_resolver_validation():
    from app.main import configured_dns_resolver

    resolver = configured_dns_resolver("1.1.1.1, 1.0.0.1")
    assert resolver.nameservers == ["1.1.1.1", "1.0.0.1"]
    assert resolver.timeout == 2
    assert resolver.lifetime == 5

    with pytest.raises(ValueError, match="DNS_RESOLVERS"):
        configured_dns_resolver("some-public-resolver.invalid")
    with pytest.raises(ValueError, match="DNS_RESOLVERS"):
        configured_dns_resolver("1.1.1.1,,8.8.8.8")
    with pytest.raises(ValueError, match="DNS_RESOLVERS"):
        configured_dns_resolver("1.1.1.1,8.8.8.8,1.0.0.1,9.9.9.9")


def test_dns_verifier_uses_custom_resolver_without_bypassing_txt(monkeypatch):
    import dns.resolver
    from app.main import dns_has_challenge

    class TXT:
        strings = [b"ca-panel-verification=correct-token"]

    observed = []

    def resolve(self, name, rdtype, search=False):
        observed.append((list(self.nameservers), name, rdtype, search))
        return [TXT()]

    monkeypatch.setattr(dns.resolver.Resolver, "resolve", resolve)
    assert dns_has_challenge("_ca-panel.example.org.", "ca-panel-verification=correct-token",
                             dns_resolvers="1.1.1.1") is True
    assert dns_has_challenge("_ca-panel.example.org.", "ca-panel-verification=WRONG",
                             dns_resolvers="1.1.1.1") is False
    assert observed == [(["1.1.1.1"], "_ca-panel.example.org.", "TXT", False)] * 2



def test_server_side_issuance_download_links_and_one_time_bundle(client):
    import io
    import zipfile
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    created = client.post("/api/requests", json={"domain": "example.org"})
    assert created.status_code == 201
    rid = created.json()["request_id"]
    assert client.post(f"/api/requests/{rid}/issue-server").status_code == 403
    assert client.post(f"/api/requests/{rid}/verify").status_code == 200
    issued = client.post(f"/api/requests/{rid}/issue-server")
    assert issued.status_code == 201, issued.text
    result = issued.json()
    assert result["download_expires_in_seconds"] == 600
    assert result["download_url"].startswith("/api/downloads/")
    assert client.post(f"/api/requests/{rid}/issue-server").status_code == 409

    leaf_response = client.get(result["certificate_url"])
    assert leaf_response.status_code == 200
    leaf = x509.load_pem_x509_certificate(leaf_response.content)
    assert client.get(result["fullchain_url"]).content.count(b"BEGIN CERTIFICATE") == 2
    assert client.get(result["issuer_url"]).status_code == 200
    assert client.get(result["root_url"]).status_code == 200

    bundle = client.get(result["download_url"])
    assert bundle.status_code == 200
    assert bundle.headers["cache-control"].startswith("no-store")
    assert bundle.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert set(archive.namelist()) == {
            "example.org.key", "example.org.crt", "example.org-fullchain.pem",
            "issuing-ca.pem", "root-ca.pem", "README.txt"
        }
        private = serialization.load_pem_private_key(archive.read("example.org.key"), password=None)
        assert private.public_key().public_numbers() == leaf.public_key().public_numbers()
        assert archive.read("example.org.crt") == leaf_response.content
        assert archive.read("example.org-fullchain.pem").count(b"BEGIN CERTIFICATE") == 2
    assert client.get(result["download_url"]).status_code == 404
    assert client.get(result["certificate_url"]).status_code == 200
    assert client.get("/api/downloads/not-a-valid-token").status_code == 404


def test_expired_private_bundle_link(client):
    rid = client.post("/api/requests", json={"domain": "example.org"}).json()["request_id"]
    assert client.post(f"/api/requests/{rid}/verify").status_code == 200
    result = client.post(f"/api/requests/{rid}/issue-server").json()
    token = result["download_url"].split("/")[-1]
    deadline, data, filename = client.app.state.downloads[token]
    client.app.state.downloads[token] = (0, data, filename)
    assert client.get(result["download_url"]).status_code == 404
    assert client.get(result["certificate_url"]).status_code == 200


def test_private_key_is_not_saved_in_sqlite(client, tmp_path):
    from app.main import connect
    rid = client.post("/api/requests", json={"domain": "example.org"}).json()["request_id"]
    client.post(f"/api/requests/{rid}/verify")
    result = client.post(f"/api/requests/{rid}/issue-server")
    assert result.status_code == 201
    with connect(tmp_path / "data" / "panel.db") as conn:
        row = conn.execute("SELECT cert_pem, serial_hex FROM challenges WHERE id=?", (rid,)).fetchone()
    assert row["cert_pem"].startswith("-----BEGIN CERTIFICATE-----")
    assert "PRIVATE KEY" not in row["cert_pem"]
