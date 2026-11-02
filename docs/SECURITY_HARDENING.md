# Iran CA Center — public issuance, administrator review and security boundaries

This release separates CA-Panel into a **public request portal** and a **single-administrator review console**. Anyone may submit a public DNS hostname and prove control with a unique TXT challenge. A certificate is **not signed** until an authenticated administrator reviews and approves the verified request. After approval, the requester uses an unguessable request capability to initiate signing and retrieve a short-lived, one-time private-key bundle.

The migration adds review columns to the existing SQLite `challenges` table. It does not create, replace or rotate Root/Issuing CA keys, and it preserves previously issued certificates and request history. This is not a third-party penetration-test certification or a multi-tenant PKI.

## 1. Public network edge

The public portal requires inbound **TCP 80 and TCP 443**:
- TCP 80 serves only the static Root CA trust guide, its local helper script and the two public Root CA downloads. Caddy also needs port 80 for ACME HTTP-01 challenges.
- TCP 443 serves the public portal and its APIs using a publicly trusted Caddy/ACME certificate.
- Do not expose API port 8000. The host API mapping remains bound to `127.0.0.1:8080`.
- Do not expose Docker's socket/API. Keep the offline Root private key entirely off the production server.

Docker-published ports may bypass ordinary UFW rules; enforce the intended public ports and API isolation at the cloud/network firewall as well as on the host. Since the portal is public, do not restrict TCP 443 to a VPN or a fixed administrator IP range.

The portal's own HTTPS certificate is managed by Caddy/ACME and should be trusted by ordinary browsers. Certificates issued for user domains are still signed by the **CA-Panel private CA**; they are not publicly browser-trusted. Users must independently verify the Root SHA-256 fingerprint and install the Root CA only on devices that are intended to trust this private PKI.

## 2. Upgrade on the existing Ubuntu CA server

This upgrade does **not** generate a new Root or Issuing CA and does **not** erase issuance history:

```bash
cd ~/CA-Panel
git pull --ff-only
python3 scripts/setup_admin.py   # only if administrator enrollment is missing
bash install.sh --public-https
```

The historical `--private-https` flag remains as a compatibility alias for `--public-https`; it no longer creates a private-CA leaf certificate for the portal. The legacy Compose profile name `private-tls` is also retained to avoid breaking existing deployment commands. Caddy obtains and renews the portal certificate through ACME.

`setup_admin.py` requires a real interactive TTY, prompts for a unique 16+ character administrator password, asks which DNS suffixes are authorized for issuance and generates a private TOTP MFA seed. The one-time seed is displayed only in the admin terminal; register it with an authenticator application (time-based, SHA-1, 6 digits, 30 seconds) and protect its backup offline. The web login account is `admin`. Do not share the seed, screenshots, password, generated PBKDF2 hash or `.env`.

The script updates only `.env` with mode 0600 using an atomic replace. Passwords are salted PBKDF2-SHA256 hashes with 600,000 iterations; plaintext passwords are not saved. The TOTP seed remains secret in `.env`, so host root/Docker administrators can still compromise it. Secure backups of `.env` and the online Issuing CA are required. Rotation is explicit:

```bash
python3 scripts/setup_admin.py --rotate
bash install.sh --public-https
```

Rotating resets the password/MFA seed and changes session generation; all old sessions are invalid after the API container is recreated. It does not rotate CA certificates.

## 3. Domain authorization and public request flow

`CERT_ALLOWED_DOMAINS` is a comma-separated list such as:

```dotenv
CERT_ALLOWED_DOMAINS='iravand.ir,example.org'
CERT_ALLOW_ANY_DOMAIN=0
```

With `CERT_ALLOW_ANY_DOMAIN=0` (default), only listed exact DNS names or subdomains are accepted. An empty allowlist denies all new requests. To accept requests for any syntactically valid public DNS hostname, set `CERT_ALLOW_ANY_DOMAIN=1` in the protected `.env`:

```dotenv
CERT_ALLOWED_DOMAINS=
CERT_ALLOW_ANY_DOMAIN=1
```

This setting allows a user to **submit** a request; it does not bypass DNS proof or administrator approval. In all-domains mode, the operator must understand the abuse implications and review every verified request before approval. Reserved/private suffixes, IP addresses and wildcard names remain unsupported.

The public flow is:

1. `POST /api/requests` creates a random 192-bit request ID and a domain-specific DNS TXT challenge.
2. The requester publishes the exact TXT value at `_ca-panel.<domain>` and calls `POST /api/requests/{id}/verify`.
3. The API checks DNS, expiry, per-IP/global request limits and verification-attempt limits.
4. The administrator reviews the verified request at `/admin/requests`. Approval rechecks the current domain policy and DNS proof; rejection prevents signing.
5. Only an approved requester can call `/api/requests/{id}/issue-server` or the CSR endpoint. DNS proof is checked again at signing time.
6. The private ZIP is served through a separate short-lived, one-time download capability held in memory only.

The request ID is itself a bearer capability: anyone who possesses it can see the request's challenge/status and, after administrator approval, initiate issuance. The browser keeps it in the URL fragment so it is not sent in HTTP requests or Referer headers. The UI warns users not to share this private tracking link. A one-time ZIP download URL is a separate bearer capability; it is consumed on first use and cannot be recovered after expiry or process restart.

## 4. Public and administrator security boundaries

- Public portal: `https://ca1.iravand.ir/`. It accepts only a single public DNS hostname (no IP, wildcard or reserved/private suffix).
- Public status/verification/signing routes are capability-scoped to a high-entropy request ID. There is no permissive CORS policy.
- Public mutation requests reject mismatched `Origin` and `Sec-Fetch-Site: cross-site` requests. The request ID is not accepted as an admin session.
- Admin console: `/admin`; request review queue: `/admin/requests`; login: `/login`. Admin review APIs are not in the public route allowlist.
- Admin operations require a server-held random 8-hour session, `Secure`, `HttpOnly`, `SameSite=Strict` cookie and CSRF token.
- Login requires a valid password and time-based one-time code. One-time MFA codes cannot be replayed; failures are throttled globally after 10 attempts per 15-minute window. This simple global throttle can temporarily lock out legitimate users if attacked, so network monitoring remains important.
- Security audit events are stored in the CA SQLite DB in `security_audit` without passwords, MFA codes, bearer download URLs or private keys.
- Missing admin credentials fail closed: new public request creation and signing return HTTP 503 until administrator enrollment. Public informational pages and already issued public certificates remain readable.
- Production Compose sets `TRUST_PROXY_HEADERS=1` because the API is bound to loopback and all public traffic enters through Caddy. Caddy overwrites `X-Real-IP` with the connected peer address; the application accepts only that header. Never expose the API port or bypass Caddy. Revisit this trust boundary if the network topology changes.
- No secret token is written to localStorage or sessionStorage. Do not access admin login over HTTP. Check NTP accuracy on the server and MFA device.

## 5. CI security tests

GitHub Actions runs the Python functional/authentication regression suite and a separate security job with `pip-audit` and Bandit. Tests cover public request submission, DNS proof, administrator approval/CSRF, cross-origin rejection, session logout, TOTP replay, domain policy, existing-database migration, audit privacy, one-use ZIP behavior and X.509/DNS checks. CI cannot validate your actual Ubuntu firewall, OS patching, Docker daemon policy, DNS resolver integrity, public ACME reachability, real certificates or private-key handling, nor substitute for a professional penetration test.

## 6. Verification without printing secrets

The portal uses public WebPKI trust, so do **not** pass the private Root CA to curl when checking the portal's HTTPS certificate:

```bash
cd ~/CA-Panel
docker compose --env-file "$HOME/CA-Panel-production.env" \
  -f compose.yaml --profile private-tls ps
curl --noproxy '*' --resolve ca1.iravand.ir:443:127.0.0.1 \
  https://ca1.iravand.ir/healthz
curl --noproxy '*' --resolve ca1.iravand.ir:443:127.0.0.1 \
  -o /dev/null -w 'Public portal HTTP: %{http_code}\\n' \
  https://ca1.iravand.ir/
curl --noproxy '*' --resolve ca1.iravand.ir:443:127.0.0.1 \
  -o /dev/null -w 'Admin queue unauthenticated: %{http_code}\\n' \
  https://ca1.iravand.ir/admin/requests
curl --noproxy '*' --resolve ca1.iravand.ir:443:127.0.0.1 \
  -o /dev/null -w 'Unknown request capability: %{http_code}\\n' \
  https://ca1.iravand.ir/api/requests/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
```

Expected: health 200, portal 200, admin queue 303 to `/login`, unknown well-formed request capability 404. Public request creation returns 503 if admin enrollment is incomplete. After enrollment, test a permitted domain with a real DNS TXT challenge, approve it from the admin queue and only then issue.

The HTTP trust guide should remain available at `http://ca1.iravand.ir/`; its only allowed resources are the static guide, local helper script and two public Root CA downloads. All login, request, status, approval and issuance operations require HTTPS.

## 7. Remaining risks — do not overstate assurance

This is single-administrator access control, not enterprise SSO, independent RBAC, hardware-backed keys, formally verified secure key custody, malware-resistant hosts, PKI revocation or public trust. Private keys are still produced temporarily inside the API process for server-issued ZIP packages, and the Issuing CA signing key is mounted into that process. The project still has no CRL/OCSP, HSM, independent external penetration test, or full security monitoring. ACME is used only for the portal's own HTTPS certificate, not for customer certificate issuance. For production CA operation, commission an independent assessment and plan issuer-key protection and incident response.
