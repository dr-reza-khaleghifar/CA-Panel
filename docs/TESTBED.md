# Isolated CA-Panel Testbed

## Purpose and safety boundary

The testbed runs the existing CA-Panel application as a **separate disposable private-CA environment**. It is intended for functional testing of the current MVP and for safely developing future CA lifecycle features.

It is not publicly trusted. The Test Root must never be presented as a public Root Store candidate or installed into general-purpose devices. Install it only in a dedicated test browser or disposable test machine when explicitly needed.

The live deployment is not reused:
- Live deployment continues to use `compose.yaml`, `.env`, `secrets/` and `data/`.
- Test deployment uses `compose.test.yaml`, `.env.test` and `.testbed/`.
- The Compose project is named `ca-panel-testbed`.
- Test API and HTTPS ports bind to host loopback only (defaults: 18080 and 18443).
- The test database, CA files, TLS leaf key and Caddy state are separate.
- Never run `docker compose down -v` from the live deployment.

The first testbed stage provides isolated deployment and the current CSR/DNS issuance flow. ACME, ARI, CRL, OCSP, CT, DNSSEC, multi-perspective validation and HSM integration are separate future implementation phases; this document does not claim they already exist.

## 1. Create a disposable Test Root and Issuer OFFLINE

Generate the Test CA on a trusted workstation that is separate from the application server. Do not generate or retain the Test Root private key on the live Ubuntu host.

On the trusted workstation, use a clean checkout of this repository:

```bash
cp .env.test.example .env.test
chmod 600 .env.test
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/init_ca.py --output ca-panel-test-ca --env .env.test
```

The script prompts twice for two different passphrases:
- Test Root passphrase: protects `ca-panel-test-ca/offline/root-key.pem`.
- Test Issuer passphrase: protects `ca-panel-test-ca/online/issuer-key.pem`.

Record the Test Issuer passphrase in the server's `.env.test` as `CA_KEY_PASSWORD`. It must be exactly the same value entered during CA creation. Use a strong unique passphrase that does not contain a single quote, backslash or newline (the dotenv writer deliberately rejects those characters); do not place it in shell arguments, environment exports, chat, GitHub, or command history.

Keep the entire `ca-panel-test-ca/offline/` directory and especially `root-key.pem` offline in encrypted storage with a separate backup. Transfer **only** the three public/online files from `ca-panel-test-ca/online/` to the Ubuntu testbed. Never transfer the Root private key.

## 2. Prepare isolated directories on Ubuntu

From the existing repository on the server:

```bash
cd ~/CA-Panel
install -d -m 700 .testbed .testbed/data .testbed/pki .testbed/pki/online .testbed/secrets .testbed/secrets/tls
cp .env.test.example .env.test
chmod 600 .env.test
```

Edit `.env.test`:
- Set `APP_UID` and `APP_GID` to the output of `id -u` and `id -g`.
- Set `CA_KEY_PASSWORD` to the exact Test Issuer passphrase, enclosed in single quotes.
- Keep the Test CA profile values consistent with the values used on the offline workstation.
- Keep `CERT_ALLOW_ANY_DOMAIN=0`.
- Choose a test hostname under a domain you control for `PANEL_DOMAIN`. It is used for the local test HTTPS endpoint; it does not itself prove domain ownership for customer certificate issuance.

Transfer only the online directory from the trusted workstation, for example:

```bash
scp ca-panel-test-ca/online/*.pem ca1@YOUR_SERVER:~/CA-Panel/.testbed/pki/online/
```

Then on Ubuntu, restrict permissions:

```bash
chmod 700 .testbed .testbed/data .testbed/pki .testbed/pki/online .testbed/secrets .testbed/secrets/tls
chmod 600 .env.test .testbed/pki/online/*.pem
chown -R "$(id -u):$(id -g)" .testbed
```

Do not copy any file from the offline directory. Do not change the live `.env`, `secrets/` or `data/`.

## 3. Enroll a separate test administrator

The enrollment utility supports a separate dotenv file:

```bash
python3 scripts/setup_admin.py --env .env.test
```

This writes the test administrator's password hash, TOTP seed and session generation only to `.env.test`. It does not modify the live `.env`. Save the one-time TOTP seed in a secure test-only authenticator and do not paste it into chat or GitHub.

Choose only domain suffixes you control and intend to test. Every certificate request must still pass DNS TXT ownership validation. Do not enable `CERT_ALLOW_ANY_DOMAIN` just to simplify testing.

## 4. Issue a test-only HTTPS certificate and start the testbed

Issue the local panel TLS leaf from the Test Issuer. This is an explicit local operator action; it does not bypass DNS validation for customer issuance endpoints.

```bash
python3 scripts/issue_panel_tls.py --env .env.test
docker compose --env-file .env.test -f compose.test.yaml config -q
docker compose --env-file .env.test -f compose.test.yaml up -d --build
```

The test Caddy service listens only on `127.0.0.1:18443` by default. The API diagnostic port listens only on `127.0.0.1:18080`. No test port is published to public interfaces and the test Compose file does not publish port 80.

Check service health:

```bash
docker compose --env-file .env.test -f compose.test.yaml ps
curl --noproxy '*' -fsS http://127.0.0.1:18080/healthz
curl --noproxy '*' --cacert .testbed/pki/online/root-cert.pem \
  --resolve ca-panel-test.iravand.ir:18443:127.0.0.1 \
  https://ca-panel-test.iravand.ir:18443/healthz
```

If you changed `PANEL_DOMAIN`, replace `ca-panel-test.iravand.ir` in the last command with that exact hostname. The second check validates the test TLS chain using the Test Root certificate; it does not install trust system-wide.

For browser testing from an administrator workstation, create an SSH tunnel to port 18443, map the chosen test hostname to 127.0.0.1 on that workstation, and import the Test Root only into a dedicated test browser/profile. Do not install the Test Root into your normal operating-system trust store.

## 5. Operate and stop only the testbed

```bash
docker compose --env-file .env.test -f compose.test.yaml logs --tail=100
docker compose --env-file .env.test -f compose.test.yaml ps
docker compose --env-file .env.test -f compose.test.yaml down
```

The `down` command above stops only the project named `ca-panel-testbed`. It does not delete the bind-mounted `.testbed/` data. Do not add `-v` unless intentionally deleting the test Caddy named volumes after confirming the project name.

Never use the live deployment's Compose commands to reset the testbed, and never use testbed commands with the live `.env`.

## 6. Isolation acceptance checklist

- [ ] `.env.test` is mode 0600 and ignored by Git and Docker build context.
- [ ] `.testbed/` is ignored by Git and Docker build context.
- [ ] Test Root private key exists only on the offline workstation and its protected backup.
- [ ] Only Test Issuer key/certificate and Test Root public certificate are on the server.
- [ ] Test Issuer key is mounted read-only at `/run/ca-test`.
- [ ] Test database is `.testbed/data/ca-panel-test.sqlite3`, separate from live `data/ca-panel.sqlite3`.
- [ ] Test API is bound to `127.0.0.1:18080` and test Caddy to `127.0.0.1:18443`.
- [ ] Test Caddy has no HTTP listener and no public ACME automation.
- [ ] Test administrator credentials are stored only in `.env.test`.
- [ ] Health and TLS-chain checks pass.
- [ ] Live `.env`, Root/Issuer material, database, containers and ports remain unchanged.

Only after this isolation gate passes should the project begin adding certificate inventory, revocation state, CRL/OCSP, ACME/ARI, CT integration and the signing-service boundary.
