# Iran CA Center — hardening, access control and safe migration

This release separates the **public DNS-verified certificate portal** from the **single-administrator MFA-protected workspace**. Customers can request and automatically receive a certificate without an admin account; only the administrator can configure issuance scope and access the protected workspace. Public issuance is fail-closed until admin setup is complete and an issuance policy is configured. Existing CA keys and certificates are preserved. This is not a third-party penetration-test certification or a multi-tenant PKI.

## First: restrict access at the network edge

For the public portal, TCP 443 must be reachable by intended customers through Caddy/HTTPS. Do not publish the API's port 8080 to the internet; keep it bound to 127.0.0.1 and expose the application only through the trusted reverse proxy. Apply edge/WAF protections and monitor the built-in per-IP and global issuance limits. Keep the administrator workspace at `/admin` protected by MFA; add network-level restrictions for that path if your edge platform supports path-aware access controls. Docker-published ports may bypass ordinary UFW rules. Keep the **offline Root private key entirely off the server**; never paste `.env` or private keys into a ticket, chat, CI or browser.

The HTTPS certificate on this site is signed by the **Pardis private CA**. Users must independently trust its Root; this release does not make a private CA publicly trusted.

## Upgrade on existing Ubuntu CA server

This does NOT generate a new Root or Issuing CA and does NOT erase issuance history:

```bash
cd ~/CA-Panel
git pull
python3 scripts/setup_admin.py
bash install.sh --private-https
```

`setup_admin.py` requires a real interactive TTY, prompts twice (without echo) for a **unique 16+ character administrator password**, asks which DNS suffixes are authorized for issuance and generates a **new private TOTP MFA seed**. The one-time TOTP seed is displayed only in the admin terminal; register it with an authenticator application (time-based, SHA-1, 6 digits, 30 seconds) and protect its backup **offline**. The web login account is `admin`. Do not share the seed, screenshots, password, generated PBKDF2 hash or `.env`.

The script updates only `.env` with mode 0600 using an atomic replace. Passwords are salted PBKDF2-SHA256 hashes with 600,000 iterations; plaintext passwords are not saved. The TOTP seed remains secret in `.env`, so host root/Docker admin users can still compromise it. Secure backups of `.env` and the online Issuing CA are required. Rotation is explicit:

```bash
python3 scripts/setup_admin.py --rotate
bash install.sh --private-https
```

Rotating resets the password/MFA seed and changes session generation; **all old sessions are invalid** after the API container is recreated. It does not rotate CA certificates.

### Authorized certificate names

`CERT_ALLOWED_DOMAINS` is a comma-separated list such as:

```dotenv
CERT_ALLOWED_DOMAINS='iravand.ir,example.org'
```

With `CERT_ALLOW_ANY_DOMAIN=0` (default), the issuer accepts only the listed exact DNS names or subdomains. **An empty allowlist denies all issuance.** To opt into issuance for **any valid public DNS hostname**, set `CERT_ALLOW_ANY_DOMAIN=1` in the protected `.env`, or type `*` at the administrator-enrollment domain prompt and confirm by typing `ALLOW ANY DOMAIN`. This flag overrides the suffix list when enabled.

```dotenv
CERT_ALLOWED_DOMAINS=
CERT_ALLOW_ANY_DOMAIN=1
```

In all-domains mode **administrator-controlled policy, per-IP/global rate limits, normal DNS-name validation and mandatory domain-specific DNS TXT ownership proof still apply**; DNS TXT is rechecked at signing time. Public users do not need an admin session, but they must control the exact DNS hostname to be certified. Reserved/private suffixes, IP addresses and wildcard names remain unsupported. Enabling this for a Root trusted by many clients substantially increases issuance exposure; enable only with an understood abuse policy, rate limiting, monitoring and incident response. To revert, set `CERT_ALLOW_ANY_DOMAIN=0` and configure an explicit `CERT_ALLOWED_DOMAINS` list. Restart/recreate the API to apply settings; never edit or regenerate CA keys for this change.

### Login, security boundaries, auditing

- Public customer path: `https://ca1.iravand.ir/`; it does not require a user account or administrator cookie. Administrator path: `https://ca1.iravand.ir/login`, then `/admin`.
- Server-held, random, 8-hour opaque administrator sessions; the browser receives a `Secure`, `HttpOnly`, `SameSite=Strict` session cookie.
- All state-changing administrator/legacy endpoints reject missing or mismatched `X-CSRF-Token`. Public `/api/public/` endpoints intentionally do not use an admin session; they require the random domain-specific DNS TXT challenge and re-check it immediately before signing. An expired or invalid administrator session is rejected; logout deletes the server session.
- Login requires valid password and time-based one-time code. One-time MFA codes cannot be replayed; failures are throttled globally after 10 attempts per 15-minute window. This simple global throttle can temporarily lock out legitimate users if attacked, so a network firewall remains important.
- Security audit events are stored in the CA SQLite DB in `security_audit` without passwords, MFA codes, bearer download URLs or keys. Review logs from a trusted workstation.
- Public read-only `/healthz`, `/api/system`, `/api/ca.pem`, `/api/issuer.pem`, portal, login page and static assets remain accessible. The intentional anonymous issuance surface is limited to `/api/public/requests`, its status/verify/issue-server subroutes, and the one-time public download/artifact URLs. Legacy `/api/requests` and the administrator workspace remain session-protected.
- Missing admin credentials **fail closed**: `/api/public/*` issuance returns HTTP 503 until admin enrollment is complete. An empty allowlist with `CERT_ALLOW_ANY_DOMAIN=0` denies all new issuance.
- Request IDs and one-time download URLs are bearer credentials. The portal keeps them in page memory only; it does not write them to browser storage. Do not access admin login or public issuance over HTTP on external networks. Check NTP accuracy on server and MFA device.

### CI security tests

GitHub Actions runs the Python functional/authentication regression suite and adds a separate **`security` job** with `pip-audit` (published Python dependency advisories) and Bandit (static Python security scanning). Tests cover anonymous public DNS-verified issuance, fail-closed behavior before admin setup, protected legacy/admin routes, CSRF, session logout, TOTP replay, domain policy, audit privacy, one-use ZIP behavior and X.509/DNS checks. CI cannot validate your **actual Ubuntu firewall, OS patching, Docker daemon policy, DNS resolver integrity, real certificates and private-key handling**, nor substitute for a professional penetration test.

### Verification without printing secrets

```bash
cd ~/CA-Panel
docker compose --profile private-tls ps
curl --noproxy '*' --cacert secrets/online/root-cert.pem \
  --resolve ca1.iravand.ir:443:127.0.0.1 https://ca1.iravand.ir/healthz
curl --noproxy '*' --cacert secrets/online/root-cert.pem \
  --resolve ca1.iravand.ir:443:127.0.0.1 \
  -o /dev/null -w 'Anonymous request HTTP: %{http_code}\n' \
  https://ca1.iravand.ir/api/requests/does-not-exist
```

The last command should return HTTP **401** after the admin has been enrolled because it targets the protected legacy API. The site root should serve the public portal without redirecting to login; `/admin` should redirect unauthenticated browsers to `/login`. The public API returns HTTP 503 before admin enrollment, HTTP 403 for a domain outside the administrator policy, and HTTP 201 for an allowed domain. Complete an end-to-end test only with a domain you control and its actual DNS TXT challenge.

### Remaining risks — do not overstate assurance

This is **single-administrator access control**, not enterprise SSO, independent RBAC, hardware-backed keys, formally verified secure key custody, malware-resistant hosts, PKI revocation or public trust. Private keys are still produced temporarily inside the API process for server-issued ZIP packages, and the Issuing CA signing key is mounted into that process. The project still has no CRL/OCSP, HSM, independent external penetration test, or full security monitoring. For production CA operation, commission an independent assessment and plan issuer-key protection and incident response.

