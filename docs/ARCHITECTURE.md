# Architecture and trust boundaries

```
Browser ── HTTPS (optional Caddy/ACME) ── FastAPI (single worker)
   │                                       │     │
   │                         DNS TXT lookup│     ├─ SQLite (data/)
   │                                       ▼     │
   │                               DNS resolver │
   │                                             ▼
   │                                encrypted Issuing CA key (read-only)
   │                                             │
   │                                        signed leaf cert
   ▼                                             ▼
Web UI requests server-side key generation and private ZIP   cert + chain

Offline Root CA signing key ── one-time signing ── Issuing CA certificate
         NEVER mounted in the API container
```

- Trust model: only independently trusted Root CA fingerprints should be installed in clients. This system does not participate in OS/browser public trust programs. The public portal does not grant public-browser trust; each client must install the private Root CA. Any attacker holding the online Issuing CA key **and** its passphrase can issue certificates for any name. Limit access and keep root offline.
- Access boundary: customers use the public portal and anonymous `/api/public/*` DNS-proof workflow. The administrator uses `/admin` with MFA to control domain policy and CA operations. Public issuance is disabled until administrator enrollment is complete.
- Domain validation: the requester creates a challenge and publishes an exact, random TXT value under `_ca-panel.<domain>`. Request IDs and challenge tokens are cryptographically random. Challenges expire after the configurable TTL (default one hour). DNS is rechecked just before signing. DNS is queried via the configured resolver; this MVP does not implement DNSSEC validation or direct authoritative-name-server querying.
- Certificate profile: single DNS SAN, configurable 1–30 day lifetime (default 30), EKU serverAuth, CA=false, RSA or ECDSA leaf key; other requested CSR extensions are not copied. No wildcard, IP, multi-domain or client authentication certificates.
- Data: SQLite holds domain, token, requester IP, verification attempts, timestamps, signed public certificates and serials. End-user private keys are created temporarily in server RAM (not persisted to SQLite or disk). Expired **unissued** requests older than seven days are periodically pruned on new requests. Issued records persist until manually archived/purged.
- Key separation: offline root private key encrypted under a separate passphrase. Encrypted intermediate signing key is mounted into the running container; the decryption passphrase is passed through an environment variable. This is not hardware-backed isolation.
- Capacity: one Uvicorn worker, SQLite, synchronous DNS queries executed in FastAPI's worker pool. Suitable for small private installations; not a large public multi-tenant CA.

## Security decisions

1. Never accept a claim of ownership without DNS proof.
2. The signing authority cannot be selected by callers. Subject CN/SAN is constrained to the verified domain; user-supplied CSR extensions cannot request CA rights.
3. Refuse short RSA keys and unsupported EC curves; reject invalid CSR signatures.
4. Rate-limit anonymous public requests per remote IP and globally, and cap verification attempts per request.
5. Service is non-root, filesystem is read-only except SQLite volume, Linux capabilities dropped; `/data` and `/run/ca` are separate mounts.
6. Full public HTTPS for the *panel* is handled separately from private-PKI leaf issuance.

## Roadmap (out of MVP scope)

- Multi-admin RBAC, user accounts, per-account quotas, request approval/cancellation and audit-console UI
- ACME RFC 8555 client protocol and automated certificate renewal
- Revocation / CRL and OCSP, certificate inventory and policy enforcement
- HSM/KMS/PKCS#11 key protection, intermediate rotation tooling, secure backups
- DNSSEC validation, trusted authoritative-resolution strategy, monitoring, abuse mitigation

## Public portal and server-side private-key generation

The public portal is served at `/`; customers do not need administrator credentials. The administrator workspace is served at `/admin` and remains protected by MFA. The public API is available only after administrator setup and only for domains allowed by the administrator policy. For each request, the user publishes the exact DNS TXT challenge; the API verifies it and rechecks it immediately before signing.

FastAPI generates an RSA private key (default 2048-bit; configurable), signs a matching CSR with the encrypted online Issuing CA and writes only the **public certificate/serial** to SQLite. The private key (PEM) and ZIP are held in the single-worker process memory for at most ten minutes (configurable shorter), exposed once via a high-entropy bearer download URL, then removed from the downloadable registry. The PEM private key is not persisted to disk or SQLite.

The current UI no longer relies on browser WebCrypto: after DNS TXT validation, FastAPI generates an RSA private key (default 2048-bit; configurable), signs a matching CSR with the encrypted online Issuing CA and writes only the **public certificate/serial** to SQLite. The private key (PEM) and ZIP are held in the single-worker process memory for at most ten minutes (configurable shorter), exposed once via a high-entropy bearer download URL, then removed from the downloadable registry. One-time downloading does not guarantee secure deletion of Python memory buffers; memory snapshots, crash dumps and a compromised server remain sensitive. There is no key escrow or durable recovery. For higher-assurance deployments, use the existing manual CSR workflow where the key never touches this server.

Private ZIP capability tokens must not be passed to analytics, access logs, chat, third-party URL previewers, or external download managers. The TLS reverse proxy must protect the entire public session; `Referrer-Policy: no-referrer` and `Cache-Control: no-store` are emitted. The service remains one worker; extra workers would each hold separate ephemeral key registries and break links.
