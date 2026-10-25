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
