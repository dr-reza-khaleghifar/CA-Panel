"""CA-Panel: small, DNS-validated private PKI certificate issuer."""
from __future__ import annotations

import hashlib
import asyncio
import io
import threading
import zipfile
import ipaddress
import os
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from functools import partial
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import dns.exception
import dns.resolver
import idna
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
DISALLOWED_SUFFIXES = {"local", "localhost", "internal", "test", "example", "invalid", "onion", "home", "arpa"}

from app.config import Settings


class DomainInput(BaseModel):
    domain: str = Field(min_length=3, max_length=2048)


class CsrInput(BaseModel):
    csr_pem: str = Field(min_length=40, max_length=16384)


def normalize_domain(value: str) -> str:
    value = value.strip()
    if value.startswith(("http://", "https://")):
        u = urlsplit(value)
        if u.username or u.password or not u.hostname:
            raise ValueError("Invalid website URL")
        value = u.hostname
    value = value.removesuffix(".").lower()
    if not value or "*" in value or "@" in value or "/" in value or ":" in value:
        raise ValueError("Enter a single DNS hostname, not an IP, wildcard or path")
    try:
        ipaddress.ip_address(value)
        raise ValueError("IP certificates are not supported")
    except ValueError as e:
        if str(e) == "IP certificates are not supported":
            raise
    try:
        domain = idna.encode(value, uts46=True, std3_rules=True).decode("ascii").lower()
    except idna.IDNAError as e:
        raise ValueError("Invalid DNS hostname") from e
    labels = domain.split(".")
    if (len(domain) > 253 or len(labels) < 2 or
            any(not 1 <= len(part) <= 63 for part in labels) or
            labels[-1] in DISALLOWED_SUFFIXES or
            not re.fullmatch(r"[a-z]{2,63}", labels[-1])):
        raise ValueError("Only public DNS hostnames are supported")
    return domain


def configured_dns_resolver(resolvers: str = "") -> dns.resolver.Resolver:
    """Return system DNS by default, or specified IP-address resolvers.

    DNS_RESOLVERS is an opt-in escape hatch for stale or split DNS in Docker.
    Only literal IPs are accepted: no hostname resolution bootstrapping.
    """
    configured = resolvers.strip()
    if configured:
        parts = [item.strip() for item in configured.split(",")]
        if not 1 <= len(parts) <= 3 or any(not part for part in parts):
            raise ValueError("DNS_RESOLVERS must contain 1-3 comma-separated DNS server IP addresses")
        try:
            nameservers = [str(ipaddress.ip_address(part)) for part in parts]
        except ValueError as exc:
            raise ValueError("DNS_RESOLVERS must contain literal IPv4 or IPv6 addresses") from exc
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = nameservers
    else:
        resolver = dns.resolver.Resolver()
    resolver.timeout = 2
    resolver.lifetime = 5
    return resolver


def dns_has_challenge(name: str, expected_value: str, *, dns_resolvers: str = "") -> bool:
    resolver = configured_dns_resolver(dns_resolvers)
    try:
        for answer in resolver.resolve(name, "TXT", search=False):
            if b"".join(answer.strings).decode("utf-8", errors="replace") == expected_value:
                return True
    except dns.exception.DNSException:
        pass
    return False


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=10000")
    return connection


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript("""
            CREATE TABLE IF NOT EXISTS challenges (
                id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                token TEXT NOT NULL,
                client_ip TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                verification_attempts INTEGER NOT NULL DEFAULT 0,
                verified_at INTEGER,
                issued_at INTEGER,
                cert_pem TEXT,
                serial_hex TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_challenges_rate
                ON challenges (client_ip, created_at);
            CREATE INDEX IF NOT EXISTS idx_challenges_created
                ON challenges (created_at);
        """)


def load_issuer(ca_dir: Path, password: str,
                issuer_key_file: str = "issuer-key.pem",
                issuer_cert_file: str = "issuer-cert.pem",
                root_cert_file: str = "root-cert.pem"):
    if not password:
        raise RuntimeError("CA_KEY_PASSWORD must be set; never commit this secret")
    try:
        key = serialization.load_pem_private_key(
            (ca_dir / issuer_key_file).read_bytes(), password=password.encode("utf-8")
        )
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "Cannot decrypt Issuing CA private key (issuer-key.pem). "
            "Check CA_KEY_PASSWORD matches the Issuing CA passphrase, "
            "not the Root CA passphrase. Confirm .env quoting "
            "and the mounted key file. See docs/OPERATIONS.md. "
            "Never disclose your passphrase."
        ) from exc
    issuer = x509.load_pem_x509_certificate((ca_dir / issuer_cert_file).read_bytes())
    root = x509.load_pem_x509_certificate((ca_dir / root_cert_file).read_bytes())
    key_public = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    cert_public = issuer.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if key_public != cert_public:
        raise RuntimeError("Issuer private key does not match issuer certificate")
    if issuer.issuer != root.subject or not issuer.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise RuntimeError("Invalid issuing CA certificate")
    now = datetime.now(timezone.utc)
    if now < issuer.not_valid_before_utc or now >= issuer.not_valid_after_utc:
        raise RuntimeError("Issuing CA certificate has expired or is not yet valid")
    return key, issuer, root


def certificate_for_domain(domain: str, csr_pem: str, key, issuer: x509.Certificate,
                           validity_days: int = 30) -> x509.Certificate:
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode("ascii"))
        if not csr.is_signature_valid:
            raise ValueError("CSR signature is invalid")
        names = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if len(names) != 1 or normalize_domain(names[0].value) != domain:
            raise ValueError("CSR Common Name must match the verified domain")
        try:
            san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            if san.get_values_for_type(x509.DNSName) != [domain] or len(san) != 1:
                raise ValueError("CSR SAN must contain only the verified domain")
        except x509.ExtensionNotFound:
            pass
        public = csr.public_key()
        if isinstance(public, rsa.RSAPublicKey):
            if public.key_size < 2048:
                raise ValueError("RSA keys must be at least 2048 bits")
        elif isinstance(public, ec.EllipticCurvePublicKey):
            if not isinstance(public.curve, (ec.SECP256R1, ec.SECP384R1)):
                raise ValueError("Only P-256 and P-384 EC keys are supported")
        else:
            raise ValueError("CSR must use an RSA or P-256/P-384 public key")
    except (ValueError, TypeError, UnicodeError, x509.DuplicateExtension) as exc:
        raise ValueError(f"Invalid CSR: {exc}") from exc

    now = datetime.now(timezone.utc)
    end = min(now + timedelta(days=validity_days), issuer.not_valid_after_utc - timedelta(minutes=5))
    if end <= now + timedelta(days=1):
        raise ValueError("Issuer CA expires too soon; rotate it")
    return (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
        .issuer_name(issuer.subject)
        .public_key(public)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(end)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=isinstance(public, rsa.RSAPublicKey), data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(public), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )



def build_server_bundle(domain: str, private_key_pem: bytes, certificate: x509.Certificate,
                        issuer: x509.Certificate, root: x509.Certificate) -> bytes:
    """Build a private-key-bearing ZIP in memory only; never write keys to SQLite/disk."""
    leaf_pem = certificate.public_bytes(serialization.Encoding.PEM)
    issuer_pem = issuer.public_bytes(serialization.Encoding.PEM)
    root_pem = root.public_bytes(serialization.Encoding.PEM)
    instructions = (
        f"CA-Panel certificate files for {domain}\n\n"
        f"{domain}.key - UNENCRYPTED PRIVATE KEY; store securely (0600)\n"
        f"{domain}.crt - server certificate\n"
        f"{domain}-fullchain.pem - server certificate plus issuing CA\n"
        "issuing-ca.pem - issuing CA public certificate\n"
        "root-ca.pem - private CA root public certificate\n\n"
        "Example nginx: ssl_certificate <domain>-fullchain.pem; "
        "ssl_certificate_key <domain>.key;\n"
        "This private CA is NOT publicly browser trusted.\n"
        "The one-time private-key ZIP download cannot be recovered after use or expiry.\n"
    ).replace("<domain>", domain).encode("utf-8")
    files = {
        f"{domain}.key": private_key_pem,
        f"{domain}.crt": leaf_pem,
        f"{domain}-fullchain.pem": leaf_pem + issuer_pem,
        "issuing-ca.pem": issuer_pem,
        "root-ca.pem": root_pem,
        "README.txt": instructions,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for filename, content in files.items():
            info = zipfile.ZipInfo(filename)
            info.create_system = 3
            mode = 0o100600 if filename.endswith(".key") else 0o100644
            info.external_attr = mode << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def client_address(request: Request, settings: Settings) -> str:
    if settings.trust_proxy_headers:
        # Only turn this on when *all* incoming requests pass through a trusted proxy.
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"


def public_view(row: sqlite3.Row) -> dict:
    result = {
        "request_id": row["id"], "domain": row["domain"],
        "dns_name": "_ca-panel." + row["domain"],
        "dns_value": "ca-panel-verification=" + row["token"],
        "expires_at": row["expires_at"],
        "verified": row["verified_at"] is not None,
        "issued": row["issued_at"] is not None,
    }
    if row["issued_at"] is not None:
        result["serial_hex"] = row["serial_hex"]
    return result


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(settings.db_path)
        app.state.ca = load_issuer(
            settings.ca_dir, settings.ca_key_password,
            settings.ca_issuer_key_file, settings.ca_issuer_cert_file,
            settings.ca_root_cert_file,
        )
        # Validate DNS settings at startup rather than failing during issuance.
        configured_dns_resolver(settings.dns_resolvers)
        if not hasattr(app.state, "dns_checker"):
            app.state.dns_checker = partial(dns_has_challenge, dns_resolvers=settings.dns_resolvers)

        async def reap_expired_private_downloads():
            # Expiry is checked on download; also sweep to avoid lingering in-memory keys.
            while True:
                await asyncio.sleep(30)
                with app.state.downloads_lock:
                    now = time.monotonic()
                    for token, (expires, _, _) in list(app.state.downloads.items()):
                        if expires <= now:
                            del app.state.downloads[token]

        sweeper = asyncio.create_task(reap_expired_private_downloads())
        try:
            yield
        finally:
            sweeper.cancel()
            with suppress(asyncio.CancelledError):
                await sweeper
            with app.state.downloads_lock:
                app.state.downloads.clear()

    app = FastAPI(title="CA-Panel", version="0.2.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.downloads = {}
    app.state.downloads_lock = threading.Lock()
    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        return response

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(BASE / "static" / "index.html", media_type="text/html")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/api/system")
    def system_information():
        """Public settings and identities derived from real certificates; no secrets."""
        _, issuer, root = app.state.ca

        def common_name(cert: x509.Certificate) -> str:
            names = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            return names[0].value if names else cert.subject.rfc4514_string()

        return {
            "display_name": settings.ca_display_name,
            "organization": settings.ca_organization,
            "certificate_validity_days": settings.certificate_validity_days,
            "server_key_bits": settings.server_key_bits,
            "challenge_seconds": settings.challenge_seconds,
            "download_ttl_seconds": settings.download_ttl_seconds,
            "issuer_common_name": common_name(issuer),
            "issuer_expires_at": issuer.not_valid_after_utc.isoformat(),
            "root_common_name": common_name(root),
            "root_sha256": root.fingerprint(hashes.SHA256()).hex().upper(),
        }

    @app.get("/api/ca.pem")
    def root_certificate():
        _, _, root = app.state.ca
        return PlainTextResponse(root.public_bytes(serialization.Encoding.PEM).decode(), media_type="application/x-pem-file")

    @app.get("/api/issuer.pem")
    def issuer_certificate():
        _, issuer, _ = app.state.ca
        return PlainTextResponse(issuer.public_bytes(serialization.Encoding.PEM).decode(), media_type="application/x-pem-file")

    @app.post("/api/requests", status_code=201)
    def new_request(body: DomainInput, request: Request):
        try:
            domain = normalize_domain(body.domain)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        now = int(time.time())
        client_ip = client_address(request, settings)
        rid, token = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
        with connect(settings.db_path) as con:
            con.execute("DELETE FROM challenges WHERE issued_at IS NULL AND expires_at < ?", (now - 604800,))
            per_ip = con.execute("SELECT COUNT(*) FROM challenges WHERE client_ip=? AND created_at>=?", (client_ip, now - 3600)).fetchone()[0]
            global_count = con.execute("SELECT COUNT(*) FROM challenges WHERE created_at>=?", (now - 3600,)).fetchone()[0]
            if per_ip >= settings.max_requests_per_hour or global_count >= settings.max_total_per_hour:
                raise HTTPException(429, "Rate limit exceeded; try again later")
            con.execute("INSERT INTO challenges(id,domain,token,client_ip,created_at,expires_at) VALUES(?,?,?,?,?,?)", (rid, domain, token, client_ip, now, now + settings.challenge_seconds))
            row = con.execute("SELECT * FROM challenges WHERE id=?", (rid,)).fetchone()
        return public_view(row)

    def get_challenge_or_404(rid: str):
        if len(rid) > 100:
            raise HTTPException(404, "Request not found")
        with connect(settings.db_path) as con:
            row = con.execute("SELECT * FROM challenges WHERE id=?", (rid,)).fetchone()
        if row is None:
            raise HTTPException(404, "Request not found")
        return row

    @app.get("/api/requests/{rid}")
    def read_request(rid: str):
        return public_view(get_challenge_or_404(rid))

    @app.post("/api/requests/{rid}/verify")
    def verify_request(rid: str):
        row = get_challenge_or_404(rid)
        now = int(time.time())
        if row["expires_at"] < now:
            raise HTTPException(410, "DNS challenge has expired; start a new request")
        if row["issued_at"] is not None:
            return public_view(row)
        with connect(settings.db_path) as con:
            cur = con.execute("UPDATE challenges SET verification_attempts=verification_attempts+1 WHERE id=? AND verification_attempts<?", (rid, settings.max_verifications))
            if cur.rowcount == 0:
                raise HTTPException(429, "Too many verification attempts")
        if not app.state.dns_checker("_ca-panel." + row["domain"], "ca-panel-verification=" + row["token"]):
            raise HTTPException(422, f"DNS TXT verification failed for _ca-panel.{row['domain']}. The record may be missing, mismatched with this request, or invisible to the container resolver. See docs/OPERATIONS.md.")
        with connect(settings.db_path) as con:
            con.execute("UPDATE challenges SET verified_at=? WHERE id=?", (now, rid))
        return public_view(get_challenge_or_404(rid))

    @app.post("/api/requests/{rid}/issue", status_code=201)
    def issue_request(rid: str, body: CsrInput):
        row = get_challenge_or_404(rid)
        now = int(time.time())
        if row["expires_at"] < now:
            raise HTTPException(410, "Challenge expired")
        if row["issued_at"] is not None:
            raise HTTPException(409, "Certificate already issued for this request")
        if row["verified_at"] is None:
            raise HTTPException(403, "Verify DNS ownership first")
        # Re-check at signing time; a previously verified token is not indefinite authority.
        if not app.state.dns_checker("_ca-panel." + row["domain"], "ca-panel-verification=" + row["token"]):
            raise HTTPException(403, "DNS proof no longer exists; restore TXT record")
        key, issuer, root = app.state.ca
        try:
            cert = certificate_for_domain(row["domain"], body.csr_pem, key, issuer,
                                          settings.certificate_validity_days)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        chain_pem = issuer.public_bytes(serialization.Encoding.PEM).decode() + root.public_bytes(serialization.Encoding.PEM).decode()
        with connect(settings.db_path) as con:
            cur = con.execute("UPDATE challenges SET issued_at=?, cert_pem=?, serial_hex=? WHERE id=? AND issued_at IS NULL", (now, cert_pem, format(cert.serial_number, "x"), rid))
            if cur.rowcount != 1:
                raise HTTPException(409, "Certificate already issued")
        return {"domain": row["domain"], "certificate_pem": cert_pem, "chain_pem": chain_pem, "fullchain_pem": cert_pem + chain_pem, "expires_at": cert.not_valid_after_utc.isoformat(), "serial_hex": format(cert.serial_number, "x")}


    @app.post("/api/requests/{rid}/issue-server", status_code=201)
    def issue_server_side(rid: str):
        """Create a new RSA private key on server, issue and offer ONE-TIME ZIP download."""
        row = get_challenge_or_404(rid)
        now = int(time.time())
        if row["expires_at"] < now:
            raise HTTPException(410, "Challenge expired. Create a new DNS request.")
        if row["issued_at"] is not None:
            raise HTTPException(409, "Already issued. For a new private key start a new request.")
        if row["verified_at"] is None:
            raise HTTPException(403, "Verify DNS ownership first")
        if not app.state.dns_checker("_ca-panel." + row["domain"], "ca-panel-verification=" + row["token"]):
            raise HTTPException(403, "DNS proof no longer exists; restore TXT record")

        server_key = rsa.generate_private_key(public_exponent=65537, key_size=settings.server_key_bits)
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, row["domain"])]))
               .add_extension(x509.SubjectAlternativeName([x509.DNSName(row["domain"])]), critical=False)
               .sign(server_key, hashes.SHA256()))
        issuer_key, issuer, root = app.state.ca
        try:
            cert = certificate_for_domain(
                row["domain"], csr.public_bytes(serialization.Encoding.PEM).decode("ascii"),
                issuer_key, issuer, settings.certificate_validity_days
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        private_pem = server_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()
        )
        archive = build_server_bundle(row["domain"], private_pem, cert, issuer, root)
        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
        serial_hex = format(cert.serial_number, "x")
        capability = secrets.token_urlsafe(32)
        deadline = time.monotonic() + settings.download_ttl_seconds
        # Serialize issue result and secret ZIP allocation. Never store private key in DB.
        with app.state.downloads_lock:
            expired_tokens = [t for t, (expires, _, _) in app.state.downloads.items()
                              if expires <= time.monotonic()]
            for t in expired_tokens:
                del app.state.downloads[t]
            if len(app.state.downloads) >= settings.max_pending_downloads:
                raise HTTPException(503, "Private-key download capacity reached; retry later")
            with connect(settings.db_path) as con:
                cur = con.execute(
                    "UPDATE challenges SET issued_at=?, cert_pem=?, serial_hex=? "
                    "WHERE id=? AND issued_at IS NULL AND expires_at>=? AND verified_at IS NOT NULL",
                    (now, cert_pem, serial_hex, rid, now)
                )
                if cur.rowcount != 1:
                    raise HTTPException(409, "Challenge expired or certificate already issued")
            app.state.downloads[capability] = (deadline, archive, row["domain"] + "-certificates.zip")
        prefix = "/api/requests/" + rid
        return {
            "domain": row["domain"],
            "serial_hex": serial_hex,
            "expires_at": cert.not_valid_after_utc.isoformat(),
            "download_expires_in_seconds": settings.download_ttl_seconds,
            "download_url": "/api/downloads/" + capability,
            "certificate_url": prefix + "/leaf.crt",
            "fullchain_url": prefix + "/fullchain.pem",
            "issuer_url": "/api/issuer.pem",
            "root_url": "/api/ca.pem",
        }

    @app.get("/api/downloads/{capability}")
    def download_private_bundle(capability: str):
        """Bearer capability is unguessable; delete on first use and after ten minutes."""
        with app.state.downloads_lock:
            offer = app.state.downloads.pop(capability, None)
        if offer is None or offer[0] <= time.monotonic():
            raise HTTPException(404, "Download link expired or already used; start a new request")
        _, content, filename = offer
        return Response(
            content=content, media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store, private",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/api/requests/{rid}/leaf.crt")
    def download_leaf(rid: str):
        row = get_challenge_or_404(rid)
        if not row["cert_pem"]:
            raise HTTPException(404, "Certificate not yet issued")
        return PlainTextResponse(
            row["cert_pem"], media_type="application/x-pem-file",
            headers={"Content-Disposition": f'attachment; filename="{row["domain"]}.crt"'}
        )

    @app.get("/api/requests/{rid}/fullchain.pem")
    def download_fullchain(rid: str):
        row = get_challenge_or_404(rid)
        if not row["cert_pem"]:
            raise HTTPException(404, "Certificate not yet issued")
        _, issuer, _ = app.state.ca
        content = row["cert_pem"] + issuer.public_bytes(serialization.Encoding.PEM).decode("ascii")
        return PlainTextResponse(
            content, media_type="application/x-pem-file",
            headers={"Content-Disposition": f'attachment; filename="{row["domain"]}-fullchain.pem"'}
        )

    @app.get("/api/requests/{rid}/certificate")
    def download_certificate(rid: str):
        row = get_challenge_or_404(rid)
        if not row["cert_pem"]:
            raise HTTPException(404, "Certificate not yet issued")
        _, issuer, root = app.state.ca
        pem = row["cert_pem"] + issuer.public_bytes(serialization.Encoding.PEM).decode() + root.public_bytes(serialization.Encoding.PEM).decode()
        return PlainTextResponse(pem, media_type="application/x-pem-file", headers={"Content-Disposition": f'attachment; filename="{row["domain"]}-fullchain.pem"'})

    return app


app = create_app()
