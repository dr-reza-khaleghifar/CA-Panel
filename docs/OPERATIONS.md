# Operations & security runbook

## Key management

- NEVER commit `secrets/`, `data/`, `.env`, `.key` or PEM private keys. These are gitignored and Docker build-ignored. Check **git status** before pushes. Never upload them to issue comments or CI logs.
- Generate Root CA on a trusted workstation, move `offline/root-key.pem` off the server, and back it up securely. Different, strong passwords for root and issuer. Preserve the displayed root SHA256 fingerprint using a trusted independent channel.
- The online `issuer-key.pem` is encrypted at rest but its passphrase exists as a container environment variable while running. Restrict Docker socket, host root, volume permissions and environment-file access. Avoid a public Docker API.
- Rotate the issuing CA before the one-year intermediate expiry. Current MVP lacks automated rotation and revocation; replacing online keys requires orderly migration and verification of the chain.
- With compromised **issuer**: stop issuance, remove compromised key/password, replace intermediate, redistribute relevant trust/revocation policy; since this MVP has no CRL/OCSP, affected certificates should be treated as untrustworthy until retired.
- With compromised **root**: you must distribute an entirely new trust anchor to all clients and distrust the old root.

## Deployment security

- Place service behind HTTPS reverse proxy and do not publish port 8000 publicly. Default binding is `127.0.0.1:8080`.
- Set `APP_UID`/`APP_GID` to host UID/GID that owns `data/` and `secrets/online/`. On Linux use `id -u`, `id -g`. Ensure `chmod 700 secrets/online`, `chmod 600 secrets/online/issuer-key.pem`, and `chmod 600 .env` (mounted files readable by the application UID). On SELinux hosts, additional volume labeling may be required.
- Never enable `TRUST_PROXY_HEADERS=1` unless every remote caller passes through a trusted proxy that sanitizes incoming `X-Forwarded-For`. If set, all direct access must be administratively controlled. Defaults to disabled, which can group public clients behind one reverse-proxy IP for rate limiting.
- Provide a reliable system DNS resolver. DNS TXT propagation and split-horizon DNS may affect verification. DNS spoofing/poisoning can undermine this basic model; use a secure resolver. DNSSEC is not checked.
- The interface and issuance API are intentionally **anonymous** in this MVP. Production internet exposure should include stronger rate-limits/WAF, admin oversight, authentication/accounting, monitoring and abuse controls. A challenge is necessary to obtain each certificate, but a large anonymous CA can still be abused.
- For user-browser trusted HTTPS, use public CA/ACME instead. Installing private CA roots on client machines grants broad trust; do so only under managed policy.

## Observability & backup

```bash
docker compose ps
docker compose logs --tail=100 api
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/healthz').read())"
```

Back up the encrypted `secrets/online` key and certificates and securely back up the `secrets/offline` root **off-server**; optionally back up `data/ca-panel.sqlite3` using SQLite's online backup API (rather than copying a hot WAL file alone). Back up `.env` only into restricted secure storage. No secret should enter GitHub Actions.

If backup restoration loses issued certificate records, users can generate a fresh CSR and DNS request. If the signing key is lost, existing certificates continue to work until expiry, but new issuance requires a new issuer signed by the offline root (manual procedure; no automated rotation yet).

## Verify certs and chain

```bash
openssl verify -CAfile secrets/online/root-cert.pem -untrusted secrets/online/issuer-cert.pem site-cert.pem
openssl x509 -in site-cert.pem -noout -subject -issuer -dates -ext subjectAltName
openssl x509 -in secrets/online/root-cert.pem -noout -fingerprint -sha256
```

`site-cert.pem` above should contain just the leaf cert (first PEM block) extracted from the downloaded fullchain. Trusting the root is a separate administrative action; copying root into a chain file does **not** make it browser-trusted.

## Limits and next steps

- No authentication/tenant management, cancellation, automatic renewal, revocation, CRL/OCSP, ACME, HSM or robust external CA compliance.
- DNS verification requests count against a one-hour challenge lifetime and a per-request verification attempt limit.
- Current default certificate lifetime is 30 days; intermediate is 365 days, root is ~10 years.
- Designed for low-cost pilot/private usage. Conduct an independent security audit before broader deployment.

## Startup fails: `Incorrect password, could not decrypt key`

This means the application cannot decrypt the **online Issuing CA** private key. During `scripts/init_ca.py` you selected **two different passphrases**: Root CA and Issuing CA. `CA_KEY_PASSWORD` must be the **Issuing CA** passphrase only. This issue is unrelated to the website/domain certificate or DNS.

1. On the host, from the CA-Panel directory, verify that the mounted key exists: `ls -l secrets/online/issuer-key.pem`. Do **not** paste the key or passphrase into tickets or chat.
2. Independently verify the passphrase with OpenSSL (which prompts invisibly, rather than placing the passphrase in command history):

   ```bash
   openssl pkey -in secrets/online/issuer-key.pem -noout
   ```

   Enter the **Issuing CA** passphrase from initialization. If OpenSSL cannot decrypt the file, you are using the wrong passphrase or the wrong key file. Restore the original online key and passphrase from a secure backup; **do not regenerate the Root CA or overwrite existing CA files** just to bypass this error.
3. Edit `.env`, and set `CA_KEY_PASSWORD` to the exact Issuing CA passphrase. Docker Compose interpolates `$` expressions in **unquoted/double-quoted** values. For passwords containing `$` or `#`, use a single-quoted literal value, e.g. `CA_KEY_PASSWORD='example$literal#not-a-real-secret'`. Avoid whitespace outside the quotes. Do not send this file to anybody.
4. Recreate the service (a simple `docker compose restart` may retain old environment variables):

   ```bash
   docker compose up -d --force-recreate api
   docker compose logs --tail=40 api
   ```

5. If still failing, **without printing the passphrase**, verify that the key and password *inside a Compose-created container* match:

   ```bash
   docker compose run --rm --no-deps --entrypoint python api -c 'import os; from pathlib import Path; from cryptography.hazmat.primitives import serialization; serialization.load_pem_private_key(Path("/run/ca/issuer-key.pem").read_bytes(), password=os.environ["CA_KEY_PASSWORD"].encode("utf-8")); print("OK: Issuing CA key and configured passphrase match")'
   ```

If OpenSSL succeeds but the container check fails, inspect `.env` quoting, other shell-exported `CA_KEY_PASSWORD` overrides, and whether `./secrets/online` points to the correct deployment directory. Never run `docker compose config` or `printenv` in shared terminals/logs because they can display secrets. For Docker Compose, exported environment variables override values in `.env`.

Once the check passes, the main application should start with `docker compose up -d --force-recreate api`. If the correct passphrase is permanently lost, encrypted PEM key data cannot be recovered by resetting a setting; restoring from backup or securely rotating the Issuing CA using the offline Root CA is required.

## Troubleshooting: DNS TXT record exists but verification fails

CA-Panel verifies an **exact match** against one DNS TXT value, using the **DNS resolver configured inside the API container**. The requested DNS name is always `_ca-panel.<the-exact-domain-entered-in-the-form>` (so a request for `www.example.org` requires `_ca-panel.www.example.org`, not `_ca-panel.example.org`). The TXT value is exactly `ca-panel-verification=<token for this request>`.

**The quickest check**, in the project directory on the Docker host:

```bash
docker compose exec api python -m app.dns_debug example.org
# Use the exact domain you entered in the panel.
# Or select a particular request with --request-id REQUEST_ID
```

This reads the most recent request for the given domain from SQLite and queries DNS **from inside the same container**. It displays the exact expected DNS name and TXT value, the current resolver(s), the returned TXT values, the challenge expiry, and whether they match. Treat request tokens and other TXT values as temporary operational data; redact them before sharing logs or screenshots publicly.

Interpret the results:

- **NXDOMAIN / NoAnswer / 0 TXT values:** Check the DNS provider's published zone and the active authoritative nameservers. Providers usually append the zone automatically: enter only `_ca-panel` for `example.org`, or `_ca-panel.www` for `www.example.org`, *unless* the provider explicitly requires a full hostname. Avoid `_ca-panel.example.org.example.org`.
- **TXT values returned but NO MATCH:** Copy the current request's entire value from the panel. An old token from an earlier request does not work. Avoid extra spaces, embedded quotes, or a wrong `www` subdomain. Normal quotes added by `dig` when rendering TXT values are fine. Multiple TXT RDATA chunks are joined automatically.
- **Public DNS resolves but container does not:** Compare `dig TXT _ca-panel.example.org @1.1.1.1 +short` (from the host, if `dig` is installed) with the command above. Check Docker DNS resolution, negative caching, firewall and upstream nameservers; CA-Panel does not bypass the configured resolver automatically.
- **Timeout / SERVFAIL:** DNS connectivity or upstream resolver issue; check Docker's DNS network and DNS servers. Do not disable ownership verification.
- **Expired:** Challenges expire after the configured TTL (default one hour) and each has a configurable verification-attempt limit (default ten). Create a new request and publish its newly generated token; do not reuse the previous TXT value.

You can also identify the authoritative nameservers using `dig NS example.org +short` and query one of them directly using `dig @<authoritative-nameserver> TXT _ca-panel.example.org +short` from a host with `dig`. Do not share `.env`, private CA keys, or full challenge tokens with third parties.

## Docker resolver returns NXDOMAIN, but a public resolver finds the exact TXT

Docker's `127.0.0.11` is the container DNS stub. If `dig @1.1.1.1 TXT _ca-panel.example.com +short` returns your challenge but the panel reports `NXDOMAIN`, the record may be correct while the DNS upstream used by Docker is stale or differently configured.

**Confirm from within the API container without changing any certificate policy:**

```bash
docker compose exec api python -m app.dns_debug --request-id YOUR_REQUEST_ID --resolver 1.1.1.1
```

If this reports `DNS verification: MATCH` and `Challenge expired: False`, edit the existing `.env` file on the Docker host and add the **optional** resolver override:

```dotenv
DNS_RESOLVERS=1.1.1.1,1.0.0.1
```

Recreate the API container (a restart will not refresh its environment):

```bash
docker compose up -d --build --force-recreate api
docker compose exec api python -m app.dns_debug --request-id YOUR_REQUEST_ID
```

The active lookup resolver should now show the chosen IP(s). If it reports `MATCH` and is not expired, press **Verify DNS** in the UI. Do not bypass DNS proof or change any challenge tokens.

The default `DNS_RESOLVERS=` uses the container's system DNS. Only literal IP addresses are accepted (maximum three). This setting sends DNS queries for certificate challenges to the chosen resolver(s); use trusted resolvers appropriate for your privacy/network requirements. Firewall restrictions may block public DNS over UDP/TCP 53. A cached negative DNS response can temporarily persist after creation, and a new challenge may be needed if the existing one expired (one-hour lifetime). When all resolvers fail the program denies verification (fail closed).

## Auto-issue UI and key download (browser only)

The frontend now generates RSA-2048 + PKCS#10 CSR with Web Crypto, requiring HTTPS or localhost. It signs no certificates locally: domain ownership must be verified via the normal challenge before the server issues a certificate. The CSR, and **not** the private key, goes to the API. The browser creates a ZIP containing a PKCS#8 **unencrypted private key**, leaf CRT, nginx fullchain PEM (leaf + intermediate), issuing CA and public root CA, and local setup instructions. The ZIP is NOT encrypted or backed up by the server. Recommend full-disk encryption, secure storage, and `chmod 600 <domain>.key` after extraction.

Some browsers block automatic downloads after asynchronous key generation; the success screen offers a manual ZIP download button. Download the ZIP before closing the page. Neither the API nor the browser can recover a lost key after refresh. Automatic UI issuance **does not mean automatic renewal**. A new challenge and fresh proof are needed for each new certificate. External CSR clients continue to work unchanged.

Do not weaken HTTPS or the verification logic to make the UI work from a nonsecure browser context; expose the panel behind Caddy HTTPS in public deployments. A compromised frontend script could steal browser-generated keys, so serve all frontend code over trusted HTTPS and restrict modifications to the repo/static assets.


## Server-generated keys and one-time ZIP links

After successful DNS proof, `POST /api/requests/{rid}/issue-server` generates an RSA private key (default 2048-bit, configurable) on the API server, stores only the signed **public** certificate in SQLite, and returns a one-time ZIP capability URL (default ten minutes, configurable shorter). The private key and ZIP are temporarily in *process RAM*, **not on disk, SQLite or Github**. This feature intentionally means the CA server can see end-user TLS private keys during issuance.

- **HTTPS is mandatory for internet users.** Keep the API bound to loopback and place the frontend behind the configured HTTPS Caddy proxy. Never expose port 8000/8080 publicly, never send a private ZIP over untrusted HTTP.
- Keep `--workers 1`; the download registry is in-process RAM. Restarting/redeploying destroys pending downloads. If a link is consumed/expired/lost, the user must submit a new domain request, complete TXT validation again and generate a **new key**. A previously issued request cannot mint another private-key URL.
- Each link is a high-entropy bearer secret, **one-use**, with max 10-minute lifetime. Avoid logging full URLs, placing them in tickets or chat, link scanners, automated fetchers, and proxies/CDNs that cache requests. Responses use `no-store` and `no-referrer` headers. Clean backups of the application and SQLite must not contain generated end-user keys.
- Restrict operator access to the container's process memory, debugging tools and Docker socket. An attacker who compromises the CA application may read private keys during issuance. Memory is not securely zeroized by Python's garbage collector. For strict confidentiality, continue using the manual CSR API and create keys exclusively on the user's machine.
- All individual certificate and CA links are public material; **only ZIP** includes a private key. The ZIP is unencrypted; protect it and set filesystem permission 0600 on the extracted `.key`.

An asynchronous 30-second in-memory sweeper removes expired private ZIPs without requiring another request. Pending ZIPs are also cleared at app shutdown. Python memory is not securely zeroized.


## Configure the CA-Panel system via `.env`
Docker Compose automatically loads the root `.env` file and forwards explicitly allowed settings defined in `compose.yaml`. **Keep your existing .env file** (especially `CA_KEY_PASSWORD`), and append only the keys you want to override, using [`.env.example`](../.env.example) as a reference.

Settings and defaults:

| Environment variable | Purpose and safe range |
| --- | --- |
| `CA_DISPLAY_NAME=CA-Panel`, `CA_ORGANIZATION=Private CA` | Public labels displayed in the UI; no cryptographic renaming |
| `CA_KEY_PASSWORD` | Secret for decrypting the online **Issuing** CA key; never publish |
| `CA_ONLINE_HOST_DIR=./secrets/online` | Host directory with encrypted Issuing key, Issuing cert, and Root **public** cert, read-only mount |
| `CA_DIR=/run/ca` | Internal mount point; must match Compose mount |
| `CA_ISSUER_KEY_FILE=issuer-key.pem`, `CA_ISSUER_CERT_FILE=issuer-cert.pem`, `CA_ROOT_CERT_FILE=root-cert.pem` | PEM **file basenames** within the mount; traversal and absolute paths rejected |
| `DATA_HOST_DIR=./data`, `DB_PATH=/data/ca-panel.sqlite3` | Writable host directory and container-local SQLite file |
| `CERT_VALIDITY_DAYS=30` | Leaf certificate validity: 1–30 days, never past Issuing CA expiry |
| `SERVER_KEY_BITS=2048` | RSA private key size for server-generated keys: 2048, 3072 or 4096 |
| `CHALLENGE_SECONDS=3600` | DNS challenge validity: 300–86400 seconds |
| `MAX_REQUESTS_PER_HOUR=20` | Rate limit per IP: 1–1000 |
| `MAX_TOTAL_PER_HOUR=200` | Global request limit: 1–10000 |
| `MAX_VERIFICATIONS=10` | DNS verification attempts per request: 1–100 |
| `DOWNLOAD_TTL_SECONDS=600` | One-time private key ZIP link: 60–600 seconds (no extension beyond 10 minutes) |
| `MAX_PENDING_DOWNLOADS=100` | At most 1–100 live ZIPs in RAM |
| `DNS_RESOLVERS`, `TRUST_PROXY_HEADERS`, `PANEL_DOMAIN` | Existing DNS, trusted proxy and HTTPS hosting options |

**Important:** Root/Issuing CA cryptographic names, validity and trust are part of existing X.509 certificates and are **not** changed by editing `.env`. The panel reads and displays those actual values. Never put an offline Root private key into the container; never commit `.env`. Invalid settings fail early on API startup. Changing settings does **not** require re-creating the CA keys; it requires restarting the container.

To apply and verify:
```bash
docker compose up -d --build --force-recreate api
docker compose ps
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/api/system
```
The last endpoint is public metadata only; `/healthz` remains unchanged. For secret checking, avoid `docker compose config` in shared logs because it may print `CA_KEY_PASSWORD`.


## Automated first-run installer

Use `bash install.sh` for an existing online CA, or `bash install.sh --init-ca` **only on a trusted administrative workstation** to provision a genuinely new Root/Issuer pair. The first-run installer never overwrites keys or an existing `.env`; it refuses partial CA folders, requires two distinct passphrases for new CA generation, writes fresh `.env` with `0600` mode and checks the local `/healthz` endpoint before reporting success. For safety, new CA generation deliberately does not auto-start the panel until the offline Root key has been moved off-server. See [FIRST_RUN.md](FIRST_RUN.md).