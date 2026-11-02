# API v1 (JSON)

All examples presume the CA private-HTTPS deployment. Expose the public portal **only behind trusted HTTPS**. Content-Type for writes: `application/json`. Public request IDs and one-time download URLs are unguessable bearer credentials: **do not share them**.

## Public portal and anonymous issuance

- `GET /` serves the public certificate-request portal. It does not require an administrator session.
- `GET /admin` serves the administrator workspace and redirects unauthenticated visitors to `/login`.
- Public issuance endpoints are under `/api/public/`. They do not require an admin cookie or CSRF token, but they are enabled only after the administrator has completed `python3 scripts/setup_admin.py` and configured an issuance policy. Without admin setup they return HTTP 503.
- The default policy is restrictive: `CERT_ALLOWED_DOMAINS` must contain the approved DNS suffixes. To offer the service for any valid public DNS hostname, the administrator must explicitly opt in with `CERT_ALLOW_ANY_DOMAIN=1` (or confirm `*` during administrator setup). This is an operator decision; do not enable it without rate limiting and abuse response.
- Every public issuance still requires a fresh, random DNS TXT challenge for the exact hostname. The TXT record is checked at verification and again immediately before signing. IP addresses, wildcard names and reserved/private suffixes remain rejected.
- The server generates the private key and certificate after DNS verification. The private key is held only in process memory inside a one-time ZIP download; it is not stored in SQLite. The download URL is a secret bearer credential, valid for at most 10 minutes and one successful download.
- Default request limits are 20 new challenges/hour/IP and 200/hour globally. The bundled Caddyfiles overwrite `X-Forwarded-For` with the TCP peer address, and Compose defaults `TRUST_PROXY_HEADERS=1` for per-client rate limits. Keep API port 8080 private/localhost-bound. If you use a different proxy, enable this setting only when that proxy sanitizes client-supplied forwarded headers.

### Public endpoints

`POST /api/public/requests` accepts `{"domain":"example.org"}` and returns the request ID plus the TXT record name/value. `GET /api/public/requests/{request_id}` returns the request status and challenge details; treat the request ID as a secret. `POST /api/public/requests/{request_id}/verify` checks the DNS TXT record. Once verified, `POST /api/public/requests/{request_id}/issue-server` automatically generates and signs the certificate and returns public certificate links plus a one-time ZIP link. Public download and certificate routes are:

- `GET /api/public/downloads/{capability}` — one-time private-key ZIP.
- `GET /api/public/requests/{request_id}/leaf.crt` — public leaf certificate.
- `GET /api/public/requests/{request_id}/fullchain.pem` — leaf plus Issuing CA.
- `GET /api/issuer.pem` and `GET /api/ca.pem` — public Issuing and Root CA certificates.

The manual CSR endpoint `POST /api/requests/{request_id}/issue` and all legacy `/api/requests` routes remain administrator-session protected.

## Administrator authentication, session and CSRF

Before enabling public issuance, the server operator must complete `python3 scripts/setup_admin.py` and configure the allowed certificate domain suffixes or explicitly enable all public DNS hostnames. Without admin setup, `/api/public/*` returns HTTP 503; with an empty allowlist and all-domains mode disabled, new requests are denied. Administrator browser login is `GET /login`; `POST /api/auth/login` accepts:

```json
{ "username": "admin", "password": "<your-admin-password>", "code": "123456" }
```

The response sets a Secure, HttpOnly, SameSite=Strict session cookie and returns `csrf_token`. The session is valid up to eight hours. The browser stores the token in memory only. To inspect it while authenticated, `GET /api/auth/status` returns authenticated status and the CSRF token for that session; it is `Cache-Control: no-store`. All state-changing protected endpoints require the `X-CSRF-Token` header matching the session. `POST /api/auth/logout` requires the same CSRF header and clears the session.

The legacy `/api/requests` routes, including manual CSR signing and legacy ZIP download, require a valid admin session and CSRF token for state-changing operations. The separate `/api/public/` routes are the intentional anonymous customer workflow described above. Neither an admin session nor the public portal bypasses DNS ownership verification or the administrator-configured domain policy.

Use the official web UI for interactive login. For non-browser automation, a human-approved session-cookie + CSRF workflow can be implemented, but do **not** put administrator passwords/MFA secrets in scripts, URLs or CI logs. The legacy routes are not an anonymous issuance API; use the separate `/api/public/` workflow for public DNS-verified issuance. Read [SECURITY_HARDENING.md](SECURITY_HARDENING.md) before integrating.



### `GET /healthz`
Returns `{ "status": "ok" }`. Does not require authentication.

### `GET /api/ca.pem`
Returns public offline Root CA certificate (PEM). **Do not install blindly**; verify the fingerprint out-of-band.

### `POST /api/requests` (administrator session required)

The administrator-only legacy API retains the same request format. Public users should use `POST /api/public/requests`.

```json
{ "domain": "example.org" }
```

Returns HTTP 201:

```json
{
  "request_id": "<random-id>",
  "domain": "example.org",
  "dns_name": "_ca-panel.example.org",
  "dns_value": "ca-panel-verification=<random-token>",
  "expires_at": 1790000000,
  "verified": false,
  "issued": false
}
```

- Accepts a public FQDN or a full `http(s)` URL; normalizes IDN to punycode.
- Rejected: wildcard, IP, `.local`, and reserved/private TLDs.
- Limits: default 20 requests/hour/IP and 200/hour globally. Configure via `.env`.

### `GET /api/requests/{request_id}`
Status and TXT value. `issued=true` includes `serial_hex`.

### `POST /api/requests/{request_id}/verify`
No body. Looks up TXT. HTTP 200 if valid, HTTP 422 if DNS proof not found, 410 if expired, 429 after 10 verification attempts. TXT host may be a fully-qualified or relative name depending on your DNS provider.

### `POST /api/requests/{request_id}/issue`

```json
{ "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\n...\n-----END CERTIFICATE REQUEST-----\n" }
```

Requires a verified non-expired request and TXT proof still present. Returns HTTP 201:

```json
{
  "domain": "example.org",
  "certificate_pem": "-----BEGIN CERTIFICATE-----\n...",
  "chain_pem": "-----BEGIN CERTIFICATE-----\n...",
  "fullchain_pem": "-----BEGIN CERTIFICATE-----\n...",
  "expires_at": "2026-11-24T00:00:00+00:00",
  "serial_hex": "..."
}
```

- Issuance is **once per request**; repeat returns 409.
- The CSR must have a matching Common Name and, if present, exactly one matching DNS SAN. It must have a valid signature and RSA >=2048 / EC P-256 or P-384 key.
- Only the server's certificate is signed; the CSR's other extensions are never copied.

### `GET /api/requests/{request_id}/certificate`
Download issued public leaf + issuing CA + root CA chain as PEM. Returns 404 before issuance. Root CA trust and server TLS config are separate operations.

### Error model
FastAPI returns e.g. `{"detail":"..."}` and HTTP 403/404/409/410/422/429. Any API consumer should handle DNS propagation delays and create a fresh request after expiry.

## Legacy browser-only issuance (no longer the default UI)

The previous browser UI automated key and CSR generation **locally**; that optional legacy implementation remains in the source code, but the current interface uses server-side issuance. The backend API is unchanged: it accepts only a CSR at `POST /api/requests/{request_id}/issue`, verifies the current domain-bound DNS TXT challenge, and signs the certificate. **Do not send private keys to any API endpoint.**

Using the Web Crypto API requires a secure browser context (HTTPS or local `localhost`). The browser exports a PKCS#8 RSA-2048 private key locally, creates and signs a PKCS#10 CSR with CN and exactly one DNS SAN, then downloads a local ZIP containing `.key`, `.crt`, `-fullchain.pem`, the issuing and root CA certificates, and a README. The ZIP assembly runs fully in the browser, not in the API container. The private key is unencrypted and does not survive a page reload.


## Server-side issuance

The administrator-only legacy route is `POST /api/requests/{request_id}/issue-server`. The public portal uses `POST /api/public/requests/{request_id}/issue-server`. Both accept no CSR payload, validate the live DNS TXT challenge again, generate a new RSA private key (default 2048-bit) and matching CSR on the API server, sign a certificate (default 30 days; configurable via .env), and create a one-time ZIP in **process memory only**. The PEM private key is not written to disk/SQLite. The public route returns public-prefixed artifact URLs. Returns HTTP 201:

```json
{
  "domain": "example.org",
  "serial_hex": "...",
  "expires_at": "2026-11-24T00:00:00+00:00",
  "download_expires_in_seconds": 600,
  "download_url": "/api/public/downloads/<unguessable-bearer-token>",
  "certificate_url": "/api/public/requests/<request_id>/leaf.crt",
  "fullchain_url": "/api/public/requests/<request_id>/fullchain.pem",
  "issuer_url": "/api/issuer.pem",
  "root_url": "/api/ca.pem"
}
```

- The capability URL includes a private key; treat it as a **secret bearer credential**. It may be downloaded **once** and expires after the configured TTL (**10 minutes maximum**), including if no one uses it. Do not log, share, bookmark, prefetch or preview it. Always serve the public panel over HTTPS; the local-only Docker binding is not a public endpoint.
- `GET /api/public/downloads/{capability}` (or the protected legacy `/api/downloads/{capability}`) returns `application/zip` with `<domain>.key`, `<domain>.crt`, `<domain>-fullchain.pem`, `issuing-ca.pem`, `root-ca.pem`, and `README.txt`. Subsequent requests return HTTP 404. The ZIP is not password protected.
- Public artifacts: `GET /api/public/requests/{request_id}/leaf.crt` (leaf only), `GET /api/public/requests/{request_id}/fullchain.pem` (leaf + issuer), `GET /api/issuer.pem`, `GET /api/ca.pem`. The older `/certificate` route remains for compatibility.
- At most 100 unexpired private ZIPs are retained in process memory. Restarting the container drops all pending ZIPs. If the secret link is consumed/lost, start a **new DNS request**; the original key cannot be recovered.
- Existing manual CSR issuance `POST /issue` remains available for users who do not want their keys generated by the CA server.

A 30-second background sweeper removes expired private ZIP content from process memory. Pending ZIPs are also cleared on graceful shutdown; Python does not guarantee secure memory zeroization.


## Public CA system information: `GET /api/system`
This read-only endpoint is also used by the Persian UI. It returns an allowlist of **public** environment settings and names/fingerprints from the actual Root and Issuing CA PEM certificates. It never exposes the passphrase, PEM private keys, filesystem paths, challenge tokens or database content.

Default response shape:
```json
{
  "display_name": "CA-Panel",
  "organization": "Private CA",
  "certificate_validity_days": 30,
  "server_key_bits": 2048,
  "challenge_seconds": 3600,
  "download_ttl_seconds": 600,
  "issuer_common_name": "CA-Panel Online Issuing CA",
  "issuer_expires_at": "<real issuer certificate ISO 8601 timestamp>",
  "root_common_name": "CA-Panel Offline Root CA",
  "root_sha256": "<actual public root certificate SHA-256 fingerprint>"
}
```
The `issuer_common_name` and `root_common_name` fields reflect the mounted certificate subjects, not the display label. `CERT_VALIDITY_DAYS` and `SERVER_KEY_BITS` apply to both automatic server issuance and, for validity, the existing CSR issuance endpoint. Default values remain unchanged for existing installations.
