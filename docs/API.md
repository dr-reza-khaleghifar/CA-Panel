# API v1 (JSON)

All examples presume the local-only default (`http://127.0.0.1:8080`). Expose the panel publicly **only behind HTTPS**. Content-Type for writes: `application/json`. Request IDs are unpredictable bearer-like identifiers: **do not share them**.

### `GET /healthz`
Returns `{ "status": "ok" }`. Does not require authentication.

### `GET /api/ca.pem`
Returns public offline Root CA certificate (PEM). **Do not install blindly**; verify the fingerprint out-of-band.

### `POST /api/requests`

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
- Limits: default 20 requests/hour/IP, 200/hour globally. These are fixed defaults in `Settings`.

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

## Browser automatic issuance and downloadable ZIP

The browser UI now automates key and CSR generation **locally**, after the user presses the DNS verification / issuance button. The backend API is unchanged: it accepts only a CSR at `POST /api/requests/{request_id}/issue`, verifies the current domain-bound DNS TXT challenge, and signs the certificate. **Do not send private keys to any API endpoint.**

Using the Web Crypto API requires a secure browser context (HTTPS or local `localhost`). The browser exports a PKCS#8 RSA-2048 private key locally, creates and signs a PKCS#10 CSR with CN and exactly one DNS SAN, then downloads a local ZIP containing `.key`, `.crt`, `-fullchain.pem`, the issuing and root CA certificates, and a README. The ZIP assembly runs fully in the browser, not in the API container. The private key is unencrypted and does not survive a page reload.


## Server-side issuance (default UI flow)

`POST /api/requests/{request_id}/issue-server` — **no CSR payload required**. Validates the live DNS TXT challenge again, generates a new RSA-2048 private key and matching CSR on the API server, signs a 30-day certificate, and creates a one-time ZIP in **process memory only**. The PEM private key is not written to disk/SQLite. Returns HTTP 201:

```json
{
  "domain": "example.org",
  "serial_hex": "...",
  "expires_at": "2026-11-24T00:00:00+00:00",
  "download_expires_in_seconds": 600,
  "download_url": "/api/downloads/<unguessable-bearer-token>",
  "certificate_url": "/api/requests/<request_id>/leaf.crt",
  "fullchain_url": "/api/requests/<request_id>/fullchain.pem",
  "issuer_url": "/api/issuer.pem",
  "root_url": "/api/ca.pem"
}
```

- The capability URL includes a private key; treat it as a **secret bearer credential**. It may be downloaded **once** and expires after **10 minutes**, including if no one uses it. Do not log, share, bookmark, prefetch or preview it. Always serve the public panel over HTTPS; the local-only Docker binding is not a public endpoint.
- `GET /api/downloads/{capability}` returns `application/zip` with `<domain>.key`, `<domain>.crt`, `<domain>-fullchain.pem`, `issuing-ca.pem`, `root-ca.pem`, and `README.txt`. Subsequent requests return HTTP 404. The ZIP is not password protected.
- Public artifacts: `GET /api/requests/{request_id}/leaf.crt` (leaf only), `GET /api/requests/{request_id}/fullchain.pem` (leaf + issuer), `GET /api/issuer.pem`, `GET /api/ca.pem`. The older `/certificate` route remains for compatibility.
- At most 100 unexpired private ZIPs are retained in process memory. Restarting the container drops all pending ZIPs. If the secret link is consumed/lost, start a **new DNS request**; the original key cannot be recovered.
- Existing manual CSR issuance `POST /issue` remains available for users who do not want their keys generated by the CA server.
