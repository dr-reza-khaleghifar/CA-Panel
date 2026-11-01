# CA-Panel Technical Testbed — Build and Acceptance Roadmap

**Status:** Approved technical-first direction for a disposable test environment.  
**Scope:** Build and prove a complete CA lifecycle in a lab before any public Root Store, legal/business, procurement, or production-Root work.  
**Safety:** Test Root and Issuing keys are disposable and must never be submitted as candidates for public trust. Existing legacy CA material must not be overwritten or silently reused.

## 1. Project decision

The current priority is to make the CA infrastructure technically complete and operational. Legal entity, global commercial service model, auditor engagement, Root Store application, and production HSM procurement are deferred.

The future architecture should remain compatible with public-CA requirements, but this testbed is **not a publicly trusted CA** and must not claim Chrome, Firefox, Safari, Edge, or operating-system trust.

## 2. Environment separation

Maintain three explicitly separate trust domains:

1. **Legacy CA:** existing Root/Issuing certificates and keys. Preserve unchanged. No destructive migration or reinitialization.
2. **Test CA:** new disposable Test Root and Test Issuing CA, created only for the lab. Separate directory, environment variables, database, passwords, container volumes, hostname, and trust-store instructions.
3. **Future Public CA:** not created yet. Its Root key pair must be generated only after a separate approved production ceremony and readiness gate. Never promote or rename the Test Root into the public Root.

Do not put private keys, passphrases, MFA seeds, recovery material, or unredacted .env files in GitHub, chat, CI artifacts, container images, or logs.

## 3. Current repository baseline (observed on main, 2026-11-01)

The repository already contains:
- FastAPI application, SQLite persistence, DNS TXT ownership challenges and re-check at signing time.
- Offline Root / online encrypted Issuing CA file layout in the bootstrap script.
- CSR-based issuance API and a server-side ephemeral-key ZIP workflow.
- Single-admin password + TOTP MFA, sessions and CSRF controls.
- Docker Compose with non-root API container, read-only filesystem, dropped capabilities, resource limits and optional Caddy profiles.
- Basic certificate-chain, API, browser/UI, installer, authentication, and security tests plus GitHub Actions.

The following important capabilities are not implemented or are explicitly documented as absent:
- ACME RFC 8555 protocol and ACME Renewal Information (ARI).
- Scheduled renewal and lifecycle automation.
- Certificate revocation state, CRL publication and OCSP responder.
- HSM/PKCS#11 integration and a separate signing service boundary; the current API loads the encrypted Issuing private key directly.
- DNSSEC validation and multi-perspective domain validation.
- Certificate Transparency submission, SCT handling and CT monitoring.
- Multi-user roles / separation of duties and external security monitoring.
- Automated Issuing CA rollover and recovery drills.

The current MVP is a small private CA, not a public-CA-complete platform. Do not infer that a feature exists merely because it appears in the future architecture.

## 4. Target testbed architecture

    Test client / ACME client
            |
            | HTTPS (test-only endpoint)
            v
    CA Panel UI + API ---- Authentication / tenant / policy
            |                         |
            v                         v
    Registration & Domain Validation Service
            | DNS TXT / CAA / DNSSEC test adapters
            | multi-perspective test adapter (later stage)
            v
    Certificate Policy + Linting Engine
            |
            v
    Issuance Orchestrator
            |
            | authenticated, narrow signing request
            v
    Isolated Issuer Signing Service ---- encrypted Test Issuer key
            |
            +---- certificate metadata / audit database
            +---- CRL publication service
            +---- OCSP responder
            +---- ACME directory / orders / authorizations
            +---- CT test integration / monitoring
            +---- metrics, logs, alerts and backup/restore

    Offline Test Root key ---- signs Test Issuer certificate only

The Root key is never mounted in the application or online signing containers. Initially, the Test Issuer may use an encrypted software key for functional tests, but signing must be behind a narrow service interface so a PKCS#11/HSM backend can replace the test backend without rewriting issuance policy. Do not treat a software test key as production key protection.

## 5. Build phases and exit criteria

### Phase 0 — Reproducible baseline and isolation
- [ ] Record the exact main commit, Python and OpenSSL versions, Docker/Compose versions and environment profile.
- [ ] Run the existing unit, API, browser/UI and security tests; record failures without modifying production secrets.
- [ ] Confirm Git ignore and Docker build context exclude secrets/, .env, data/, private keys, database files and test trust bundles.
- [ ] Create a dedicated Test CA deployment profile with separate test-only paths and volume names.
- [ ] Add a guard that refuses to initialize if target paths contain existing CA files.
- [ ] Document how to reset only disposable test data, without touching legacy CA data.
- **Exit:** a clean, repeatable lab can be created and destroyed without affecting the legacy deployment.

### Phase 1 — Test hierarchy and certificate profile
- [ ] Generate a disposable Test Root offline and a dedicated Test Issuing CA; never use the legacy Root for the test hierarchy.
- [ ] Enforce CA key separation, encrypted Test Issuer key at rest, distinct passphrases, file permissions and chain verification.
- [ ] Define versioned X.509 profiles for Root, Issuing CA and TLS subscriber certificates.
- [ ] Subscriber profile: SAN-only identity, serverAuth EKU, CA=false, appropriate Key Usage, random serials, SKI/AKI and bounded validity.
- [ ] Validate CSR signature, public-key strength/curve, requested SAN authorization and reject unrequested extensions.
- [ ] Add profile linting and negative tests for invalid, weak, mismatched and prohibited CSRs.
- **Exit:** automated tests prove only policy-compliant TLS certificates can be issued from the Test Issuer and validate through the Test Root.

### Phase 2 — Domain validation and issuance policy
- [ ] Keep DNS-01/TXT as the first supported validation method; use unpredictable single-use challenges with bounded lifetime.
- [ ] Enforce revalidation at signing time, challenge consumption, replay protection, rate limits and idempotency.
- [ ] Add CAA evaluation and explicit fail-closed handling for DNS lookup failures.
- [ ] Add DNSSEC validation and multi-perspective validation adapters behind interfaces; use deterministic fake adapters in unit tests.
- [ ] Add policy controls for allowed names, wildcard policy, IP SAN policy, maximum validity, key types, rate limits and account ownership.
- [ ] Add issuance preflight and a human-readable denial reason without leaking challenge tokens.
- **Exit:** positive and negative domain-authorization tests pass, including DNS failure, CAA denial, replay, race and resolver disagreement.

### Phase 3 — Revocation and certificate lifecycle
- [ ] Store authoritative certificate records: issuer, serial, subject/SAN, notBefore/notAfter, status, validation evidence, account, profile and issuance event.
- [ ] Implement revoke endpoint with authenticated authorization and permitted reason codes.
- [ ] Generate and publish signed CRLs with correct CRL Number, thisUpdate/nextUpdate, AKI and reason handling.
- [ ] Implement OCSP responder for good/revoked/unknown, signed responses, caching and freshness semantics.
- [ ] Ensure revoked certificates remain revoked across restart, backup restore and Issuer rollover.
- [ ] Add renewal and reissuance workflows; renewal must repeat required authorization checks.
- **Exit:** independent OpenSSL and HTTP tests confirm good, revoked, expired and unknown behavior; CRL/OCSP remain available during restart and recovery tests.

### Phase 4 — ACME and automation
- [ ] Implement ACME RFC 8555 directory, account, nonce, order, authorization, challenge, finalize, certificate download and problem documents.
- [ ] Begin with DNS-01; do not advertise unsupported challenge types.
- [ ] Implement JWS validation, nonce replay protection, account-key rollover, authorization/order state machines and rate limits.
- [ ] Implement ARI-compatible renewal information and renewal scheduling.
- [ ] Build an ACME integration suite using at least one independent ACME client.
- [ ] Ensure customer private keys are generated and retained by the customer/client by default; any server-generated key option must be explicit, test-only and carefully isolated.
- **Exit:** independent ACME clients can issue, retrieve, renew and revoke test certificates end-to-end.

### Phase 5 — CT, publication and trust testing
- [ ] Define a CT submission adapter and test against a local/test CT log before any public log integration.
- [ ] Implement SCT collection, certificate inclusion verification and CT monitoring/alerting interfaces.
- [ ] Publish test Root/Issuer, CP/CPS placeholder for lab use, CRL, OCSP, AIA and repository metadata at stable test URLs.
- [ ] Provide test endpoints demonstrating valid, expired and revoked leaf certificates.
- [ ] Test the chain in OpenSSL, Firefox and Chromium-based browsers after explicit manual installation of the disposable Test Root.
- [ ] Clearly label the trust as local/test trust; no public trust assertion.
- **Exit:** clients that have explicitly installed the Test Root validate the test site; clients without it correctly reject it.

### Phase 6 — Operations, security and resilience
- [ ] Replace the direct API-to-private-key dependency with an authenticated signing interface and a test signer backend.
- [ ] Add least-privilege service identities, secrets isolation, strict network boundaries and signing request authorization.
- [ ] Add structured audit events for key lifecycle, validation, issuance, revocation, admin actions and configuration changes.
- [ ] Add metrics and alerts for API health, signing errors, queue depth, issuance anomalies, DNS failures, CRL/OCSP freshness, certificate expiry and backup failures.
- [ ] Add encrypted backup and tested restore for database, issuer key and public certificate/status data; keep Root backup separately offline.
- [ ] Add Issuer rollover, disaster recovery, compromised-key and mass-revocation runbooks and drills.
- [ ] Add dependency scanning, static analysis, container image scanning and integration security tests to CI.
- **Exit:** a documented recovery exercise restores a separate lab from backups and proves issuance/revocation state is consistent.

### Phase 7 — End-to-end acceptance
- [ ] Fresh install from documented instructions.
- [ ] Admin enrollment, MFA, login, logout, CSRF and role checks.
- [ ] DNS challenge create/verify/expire/replay/deny.
- [ ] CSR issuance, SAN/EKU/profile lint, chain validation and client installation.
- [ ] ACME issue/download/renew/revoke with independent client.
- [ ] CRL and OCSP good/revoked/unknown checks.
- [ ] CT test submission/SCT verification.
- [ ] Issuer rotation, backup restore, outage and mass-revocation drills.
- [ ] Full test suite and clean CI.
- **Exit:** all acceptance tests pass in a fresh disposable lab and the operator can reproduce the complete lifecycle from the runbook.

## 6. Technical implementation order

Work in small, independently reviewable changes. Do not begin ACME before certificate profiles, lifecycle data model and revocation semantics are stable. Do not begin public CT integration before the test CT adapter and issuance pipeline are deterministic.

Recommended immediate sequence:
1. Phase 0 baseline audit and isolated test profile.
2. Phase 1 CA profile and test hierarchy correctness.
3. Phase 2 domain validation hardening.
4. Phase 3 revocation/CRL/OCSP.
5. Phase 4 ACME/ARI.
6. Phase 5 CT and client trust tests.
7. Phase 6 signing boundary, operations and resilience.
8. Phase 7 end-to-end acceptance.

## 7. Definition of done for the technical testbed

The testbed is considered technically complete only when:
- A fresh lab can be deployed reproducibly without touching legacy files.
- Root key stays offline and Issuer key is isolated behind a signer interface.
- Only authorized TLS SAN certificates can be issued.
- DNS validation, CAA policy and replay protection work and fail closed.
- Independent ACME clients can issue, retrieve, renew and revoke.
- CRL and OCSP correctly represent certificate status.
- CT test integration and SCT verification are exercised.
- OpenSSL and explicitly enrolled test browsers validate the chain; unenrolled clients reject it.
- Logs, metrics, backups, restore, Issuer rollover and incident drills work.
- CI and integration acceptance tests pass.

## 8. Deferred until after technical testbed

The following are deliberately deferred:
- Legal entity, international business model and country eligibility review.
- Auditor engagement, formal WebTrust/ETSI audits and Root Store applications.
- Production HSM procurement and production Root key ceremony.
- Public browser trust claims or external public certificate issuance.

These workstreams will be revisited only after the testbed's technical acceptance criteria are met. The test Root must never be promoted to a production/public Root.
