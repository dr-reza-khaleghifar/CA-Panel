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
