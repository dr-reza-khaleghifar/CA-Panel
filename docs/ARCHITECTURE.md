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
Browser Web Crypto creates private key and CSR locally      cert + chain

Offline Root CA signing key ── one-time signing ── Issuing CA certificate
         NEVER mounted in the API container
```

- Trust model: only independently trusted Root CA fingerprints should be installed in clients. This system does not participate in OS/browser public trust programs. Any attacker holding the online Issuing CA key **and** its passphrase can issue certificates for any name. Limit access and keep root offline.
- Domain validation: the requester creates a challenge and publishes an exact, random TXT value under `_ca-panel.<domain>`. Request IDs and challenge tokens are cryptographically random. Challenges expire after one hour. DNS is rechecked just before signing. DNS is queried via the configured resolver; this MVP does not implement DNSSEC validation or direct authoritative-name-server querying.
- Certificate profile: single DNS SAN, 30-day lifetime, EKU serverAuth, CA=false, RSA or ECDSA leaf key; other requested CSR extensions are not copied. No wildcard, IP, multi-domain or client authentication certificates.
- Data: SQLite holds domain, token, requester IP, verification attempts, timestamps, signed public certificates and serials. No end-user private keys. Expired **unissued** requests older than seven days are periodically pruned on new requests. Issued records persist until manually archived/purged.
- Key separation: offline root private key encrypted under a separate passphrase. Encrypted intermediate signing key is mounted into the running container; the decryption passphrase is passed through an environment variable. This is not hardware-backed isolation.
- Capacity: one Uvicorn worker, SQLite, synchronous DNS queries executed in FastAPI's worker pool. Suitable for small private installations; not a large public multi-tenant CA.

## Security decisions

1. Never accept a claim of ownership without DNS proof.
2. The signing authority cannot be selected by callers. Subject CN/SAN is constrained to the verified domain; user-supplied CSR extensions cannot request CA rights.
3. Refuse short RSA keys and unsupported EC curves; reject invalid CSR signatures.
4. Rate-limit anonymous requests per remote IP and globally, and cap verification attempts per request.
5. Service is non-root, filesystem is read-only except SQLite volume, Linux capabilities dropped; `/data` and `/run/ca` are separate mounts.
6. Full public HTTPS for the *panel* is handled separately from private-PKI leaf issuance.

## Roadmap (out of MVP scope)

- Administrator/user authentication, per-account quotas and audit events
- ACME RFC 8555 client protocol and automated certificate renewal
- Revocation / CRL and OCSP, certificate inventory and policy enforcement
- HSM/KMS/PKCS#11 key protection, intermediate rotation tooling, secure backups
- DNSSEC validation, trusted authoritative-resolution strategy, monitoring, abuse mitigation

## Automatic browser issuance (MVP)

The user adds the DNS TXT, presses the verification button once, and the browser creates a 2048-bit RSA keypair with `crypto.subtle.generateKey()`. It serializes a locally signed PKCS#10 CSR (CN and SAN restricted to the verified domain) and sends **only the CSR** to the existing issuance endpoint. The private key stays within the browser JavaScript process and is exported to a client-side ZIP together with returned leaf/intermediate/root PEM files. There are no additional server-side dependencies or private-key storage changes.

The ZIP contains an **unencrypted** private key; downloads/backups must be protected by the user, and private keys cannot be recovered from the server. Secure browser context (HTTPS or localhost) is mandatory. Automatic certificate creation is triggered after user-initiated DNS verification; **background auto-renewal or scheduled retries are not implemented**. Failed issuance should be retried while the same browser tab holds the generated key; a certificate already issued for that challenge cannot safely be paired with a new key.
