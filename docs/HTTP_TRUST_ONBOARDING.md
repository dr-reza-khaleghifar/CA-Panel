# Iran CA Center — HTTP trust onboarding without insecure certificate issuance

The private CA HTTPS panel is at **https://ca1.iravand.ir**. An unmanaged browser that does not trust the Pardis Root CA will show a TLS trust warning. **Browsers cannot automatically fall back to HTTP after a certificate-validation failure**; attempting to bypass this through redirects or by disabling TLS validation is not supported.

A separate, informational landing page is provided at **http://ca1.iravand.ir/** under the private-TLS Caddy profile. Users must navigate there manually (HTTPS-Only mode or cached HSTS may prevent HTTP access). The page explains the trust process and offers the **public Root CA certificate only**, at `http://ca1.iravand.ir/root-ca.pem`.

## Security policy: no passwords or signing over HTTP

Port 80 uses a separate Caddy site with an explicit **GET/HEAD-only static allowlist**:

- `/` → publicly readable Persian trust guidance
- `/trust.css` → self-hosted dark styling
- `/root-ca.pem` → mounted **public Root certificate** file

Every other path (including `/login`, `/api/requests`, `/api/system`, `/api/downloads/*`, `.env`, script assets, and any key material) returns HTTP **404**. No reverse proxy to the API exists in the HTTP site. Requests do not transmit admin password, MFA, cookies, issuance challenges, ZIP download capabilities or private keys over HTTP. Protected API and all issuance remain **HTTPS-only** on 443.

**Important authenticity limitation:** HTTP content may be intercepted and modified. Never rely on the certificate or SHA-256 fingerprint downloaded or displayed over the same HTTP channel to authenticate the Root. The user must obtain the true Root SHA-256 fingerprint **out of band** from the CA operator, via an already-trusted, authenticated channel, and compare it with the downloaded certificate before granting trust. Installing a private Root extends trust broadly and is a security-sensitive administrative decision. Do not silently import a Root in a browser or OS.

The page includes manual instructions for Firefox, Windows and OpenSSL. Installing trust is not automatic and cannot be made automatic on unmanaged devices without consent.

## Deploy on existing Ubuntu

```bash
cd ~/CA-Panel
git pull --ff-only
bash install.sh --private-https
```

The private-TLS profile binds both TCP **443** (protected application) and TCP **80** (public-only trust page) by default. If an existing service occupies port 80 or the firewall restricts it, deployment will fail until that conflict is resolved. Set `PANEL_HTTP_BIND_IP` in the protected `.env` to a chosen **trusted interface IP** if needed; use the external firewall to limit who can access port 80. This is separate from `PANEL_TLS_BIND_IP`.

```bash
# From the Ubuntu server; no private TLS bypass required for the HTTP page.
curl --noproxy '*' -H 'Host: ca1.iravand.ir' -I http://127.0.0.1/
curl --noproxy '*' -H 'Host: ca1.iravand.ir' -I http://127.0.0.1/root-ca.pem
curl --noproxy '*' -H 'Host: ca1.iravand.ir' -I http://127.0.0.1/api/requests
```

Expected responses: `200`, `200`, `404`. The last result is deliberately **404**, not an API authentication response, because HTTP has no API proxy.

Confirm HTTPS remains available and authenticates to the privately trusted Root:

```bash
curl --noproxy '*' --cacert secrets/online/root-cert.pem \
  --resolve ca1.iravand.ir:443:127.0.0.1 \
  https://ca1.iravand.ir/healthz
```

The last command should return `{"status":"ok"}`. It verifies HTTPS certificate trust without disabling validation.

## Out-of-band Root SHA-256 fingerprint

The CA operator can obtain the **real certificate** fingerprint directly on the Ubuntu server:

```bash
openssl x509 -in secrets/online/root-cert.pem -noout -fingerprint -sha256
```

**Do not treat a matching fingerprint shown on an HTTP site as proof of authenticity.** Share the expected value through a separately authenticated channel. The page's Windows instructions decode PEM to DER before applying `certutil -hashfile`, so the hash represents certificate bytes rather than PEM text.

## Automated regression

`tests/test_http_trust_onboarding.py` enforces static-only configuration and user-facing safeguards. `tests/check_http_trust.sh` starts the **real Caddy image** with throwaway test certificates, verifies that GET/HEAD on the three allowlisted public paths works and that protected routes are unreachable on HTTP. No production CA keys are used.

## Browser behavior caveat

Some browsers upgrade HTTP to HTTPS automatically because of HTTPS-Only/HTTPS-First settings or previously learned HSTS. A site cannot reliably detect a failed certificate handshake in JavaScript or force a secure browser to downgrade. In these situations use a **separately trusted administrator channel** to distribute the Root; do not disable browser certificate checking.
