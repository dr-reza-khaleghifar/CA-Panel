"""End-to-end browser WebCrypto -> PKCS#10 -> CA signing + ZIP checks.

Node supplies the browser-compatible Web Crypto API to cert.js; this test does
not require a real DNS lookup or upload/send any private key to the API.
"""
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import NameOID

from app.main import certificate_for_domain, load_issuer
from scripts.init_ca import create_ca


def test_browser_auto_certificate_package(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js is required to test the browser WebCrypto integration")

    test_script = Path(__file__).with_name("browser_cert_check.js")
    subprocess.run(["node", str(test_script), str(tmp_path)], check=True, timeout=30)

    private_key = serialization.load_pem_private_key((tmp_path / "ca-panel-generated.key").read_bytes(), None)
    csr_pem = (tmp_path / "ca-panel-generated.csr").read_bytes()
    csr = x509.load_pem_x509_csr(csr_pem)
    assert csr.is_signature_valid
    assert csr.public_key().public_numbers() == private_key.public_key().public_numbers()
    assert csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "tizpo.ir"
    assert csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName) == ["tizpo.ir"]

    create_ca(tmp_path / "secrets", b"root-password-long-123", b"issuer-password-long-456")
    key, issuer, root = load_issuer(tmp_path / "secrets" / "online", "issuer-password-long-456")
    leaf = certificate_for_domain("tizpo.ir", csr_pem.decode("ascii"), key, issuer)
    assert leaf.public_key().public_numbers() == private_key.public_key().public_numbers()
    assert leaf.issuer == issuer.subject
    assert leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName) == ["tizpo.ir"]

    with zipfile.ZipFile(tmp_path / "ca-panel-generated.zip") as archive:
        assert set(archive.namelist()) == {
            "tizpo.ir.key", "tizpo.ir.crt", "tizpo.ir-fullchain.pem", "issuing-ca.pem", "root-ca.pem", "README.txt"
        }
        assert archive.testzip() is None
        assert archive.read("tizpo.ir.key").startswith(b"-----BEGIN PRIVATE KEY-----")
        assert archive.getinfo("tizpo.ir.key").external_attr >> 16 & 0o777 == 0o600
        assert archive.read("tizpo.ir-fullchain.pem").count(b"BEGIN CERTIFICATE") == 2


def test_auto_frontend_is_enabled():
    root = Path(__file__).resolve().parents[1]
    html = (root / "app/static/index.html").read_text(encoding="utf-8")
    js = (root / "app/static/app.js").read_text(encoding="utf-8")
    assert '/static/cert.js' in html
    assert 'id="download-button"' in html
    assert 'id="csr"' not in html  # no manual CSR paste needed
    assert 'await issueAutomatically()' in js
    assert 'generated.csrPem' in js  # only CSR uploaded, never private key
    assert 'generated.privateKeyPem' in js  # locally added to the ZIP
