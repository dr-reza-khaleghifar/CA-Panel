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
