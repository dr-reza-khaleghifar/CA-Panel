# Public TLS CA — Multi-Root-Store Readiness Standard

**Status:** Architecture and compliance planning only. No production Root/Issuer keys or certificates are authorized for generation.  
**Last reviewed:** 2026-11-01  
**Owner decision:** Proceed with a globally oriented public TLS CA business and service model, subject to documented legal, sanctions, export-control, and Root Store eligibility review.  
**Target:** Prepare one dedicated, publicly operated TLS CA hierarchy for independent inclusion consideration by Mozilla, Google Chrome, Apple, and Microsoft.

> **Important:** There is no universal browser approval. Each Root Store makes an independent, discretionary decision and may impose additional requirements or reject an otherwise technically compliant applicant. This document defines a common-denominator design and tracks program-specific deltas; it does not promise inclusion.

## 1. Scope and trust objective

The new hierarchy is **TLS Server Authentication only**. It will not issue S/MIME, code-signing, document-signing, timestamping, VMC, or general-purpose client-authentication certificates. Each other trust purpose, if ever pursued, must use a separate hierarchy, key material, policy, audit scope, and application.

The CA must be a genuine public CA offering broadly useful TLS issuance to unrelated subscribers and domains across the public Internet, subject to applicable law and policy. It must not be an internal/enterprise CA, a MITM/interception CA, or a service limited to the operator's existing customers or a narrow TLD/domain set. Public benefit, real public TLS issuance, transparency, security culture, and long-term operational capability are application criteria, not optional marketing claims.

The existing Pardis AI Innovation Root/Issuing hierarchy is a separate legacy/private PKI. Preserve it unchanged. Do not reuse its key, certificate subject, key ceremony, or issuance chain for the new public TLS hierarchy.

### 1.1 Approved strategic direction — global public service

The project owner has agreed that the new CA should be designed as a **global public TLS CA**, not a service restricted to Iranian domains, the `.ir` namespace, or the operator's existing customers.

The target service model is:
- Accept eligible applications from unrelated subscribers internationally, for domains across the public DNS namespace, subject to applicable law, sanctions, export controls, fraud/abuse controls, and Root Store policy.
- Avoid policy or product restrictions based solely on customer geography or a narrow set of TLDs unless a documented legal, security, or program requirement makes the restriction necessary.
- Publish clear eligibility, validation, subscriber agreement, privacy, retention, complaint, abuse-reporting, incident, and revocation processes.
- Provide globally reachable ACME and certificate retrieval endpoints, validation perspectives, CT integration, OCSP/CRL services, status pages, and security contacts with resilient operations.
- Provide operational support and incident escalation appropriate for a public CA serving unrelated subscribers in multiple time zones.
- Demonstrate real public benefit and meaningful, sustained TLS issuance beyond the operator's existing customer base.

**Boundary:** “Global” is a service-design objective, not a claim that every person, country, entity, payment route, or domain can legally be served. Before launch, qualified counsel and the auditor must review the legal entity, ownership/control, operating jurisdictions, hosting and data locations, sanctions/export-control obligations, payment providers, customer eligibility, cross-border data transfers, and any required licenses or registrations. Maintain a documented country/region eligibility matrix and a process to update it. Any restriction must be evidence-based and disclosed; it must not be disguised as a technical limitation.

**Go/no-go:** Do not purchase production HSM capacity, generate a production Root key, or submit a Root Store application until the legal and commercial feasibility review confirms a credible lawful global public-service model and the independent auditor confirms an achievable audit path.


## 2. Root Store targets and policy baseline (reviewed 2026-11-01)

| Program / platform | Current policy reference | Common requirements and program-specific considerations |
|---|---|---|
| Mozilla Root Store (Firefox, Thunderbird, Mozilla products) | Mozilla Root Store Policy v3.1, effective 2026-07-01 | Public application and risk review; TLS-only Root for new Roots; annual WebTrust/ETSI audits covering Root and all technically capable intermediates; continuous full-surveillance audit coverage and annual key-lifecycle reports beginning immediately at CA key-pair generation with no gaps; auditor-witnessed Root key-generation report; Root key pair no more than 5 years old at submission and no more than 15 years from generation for the websites trust bit; automated issuance, domain validation, issuance and retrieval for each certificate type the CA intends to issue; publicly accessible test sites for valid, revoked and expired certificates, with test certificates renewed at least every 30 days; CCADB disclosures. |
| Google Chrome Root Program | Apply for Inclusion page, last updated 2026-02-05, plus current Chrome Root Program Policy | Application through CCADB and public discussion; discretionary assessment of broad value to Chrome users, security-first culture, reliability, public ecosystem contribution, active TLS use and incident history. A narrowly limited domain/TLD or issuance only to existing customers/business offerings can be a rejection factor. ACME and ARI are positive indicators. No guaranteed review time or acceptance. |
| Apple Root Program (Safari, macOS, iOS, iPadOS) | Apple Root Program Policy v2.0, effective 2026-08-01 | Root hierarchy dedicated to a single Trust Purpose; for Server Authentication, subordinate CA and subscriber profiles must use the required serverAuth EKU; subordinate CA certificates issued from 2026-08-01 require EKU and must not assert anyExtendedKeyUsage; Root inclusion minimum RSA-4096 or ECDSA P-384; annual WebTrust preferred (ETSI case-by-case); broad value to Apple users; CCADB; CP/CPS must be purpose-scoped; Apple approval is required before issuing to an externally operated subordinate CA. From 2027-07-01, subordinate CA certificates must be single-purpose and CP/CPS Markdown requirements apply; Detailed Controls Report attestation requirements also begin for audit periods starting on/after that date. |
| Microsoft Trusted Root Program (Windows; relevant Windows trust ecosystem) | Microsoft Root Program Requirements v1.2, effective 2026-05-20 | Commercial CA cannot be primarily an internal enterprise CA; at least two Trusted Agents and a 24/7 monitored incident/revocation contact; disclose full hierarchy and keep CCADB accurate; annual qualifying audit and pre-commercial audit; root X.509 v3, self-signed, unique subject/CN identifying publisher, critical CA Basic Constraints and critical Key Usage; newly minted Root validity maximum 10 years from submission; unique key and subject for each new Root; issuing CA and subscriber CRL/OCSP publication; reason-coded intermediate revocation, CCADB update within 30 days after intermediate revocation, and prompt response obligations; TLS, S/MIME, code-signing and timestamping trust purposes must be separated as specified. |
| Common CA disclosure | CCADB Policy v2.1, effective 2026-03-20 | Maintain accurate, timely, publicly disclosable CA owner, Root, subordinate, policy, audit, incident, contact and revocation information. Root Store operators may add stronger program-specific requirements. |
| Common issuance baseline | CA/Browser Forum TLS Baseline Requirements v2.3.1, dated 2026-10-04 | Applies throughout the publicly trusted TLS hierarchy; current domain/IP validation, CAA/DNSSEC, issuance controls, certificate profiles, CT, revocation, logging, audit and key lifecycle requirements must be implemented and kept current. |
| Common infrastructure security | CA/Browser Forum Network and Certificate System Security Requirements v2.0.5, dated 2025-07-09 | Physically secure CA environment, segmented networks, Root CA Systems on physically separate networks, least privilege, MFA, trusted roles, multi-party physical control of Root systems, logging, monitoring, vulnerability management, penetration testing, incident response and change control. |

### Official references

- Mozilla Root Store Policy: https://www.mozilla.org/en-US/about/governance/policies/security-group/certs/policy/
- Chrome Root Program — Apply for Inclusion: https://googlechrome.github.io/chromerootprogram/crp/apply-for-inclusion/
- Apple Root Program Policy: https://github.com/apple/apple-root-program/blob/main/policy.md
- Microsoft Root Program Requirements: https://github.com/TrustedRootProgram/Program-Requirements/blob/main/Requirements.md
- CCADB Policy: https://www.ccadb.org/policy
- TLS Baseline Requirements: https://cabforum.org/working-groups/server/baseline-requirements/requirements/
- Network and Certificate System Security Requirements: https://cabforum.org/working-groups/netsec/requirements/

## 3. Common-denominator target design

These are planning targets, not authority to generate keys. Final profiles must be checked against the exact effective policy revisions and approved by the independent auditor before the ceremony.

### 3.1 Trust hierarchy

- One new, self-signed Root CA, dedicated only to TLS Server Authentication.
- One or more subordinate Issuing CAs dedicated only to TLS Server Authentication.
- No subscriber/leaf certificates signed directly by the Root.
- No cross-purpose EKUs, no anyExtendedKeyUsage, and no S/MIME/code-signing/time-stamping under this hierarchy.
- No externally operated subordinate CA at launch; obtain explicit program approval before any such arrangement, including Apple approval where applicable.
- Separate hierarchy and key material for any future non-TLS product.
- Root private key never resides on the online CA Panel/API, CI, containers, cloud application hosts, or developer workstations.

### 3.2 Cryptography and Root certificate profile

| Item | Common-denominator planning target |
|---|---|
| Root and subordinate CA public keys | RSA 4096-bit minimum, because this satisfies Apple's new-Root minimum and the current TLS BR RSA minimum for Root and Subordinate CA keys. |
| Signature digest | SHA-384 with RSA as the initial profile candidate; verify exact current algorithm requirements and client interoperability before final approval. |
| Root validity | TLS BR Root profile currently specifies an approximately 8-year minimum and 25-year maximum; Microsoft imposes a 10-year maximum for newly minted Roots from submission. Plan within the common 8–10-year window, with exact dates confirmed by the auditor and programs. |
| Root subject | New, unique subject/CN identifying the legal CA publisher; do not reuse the legacy Root subject or key. |
| Root certificate | X.509 v3, self-signed, issuer equal to subject, positive non-sequential serial with required CSPRNG entropy, critical Basic Constraints CA=true, critical Key Usage keyCertSign+cRLSign, SKI; follow the exact current TLS BR Root profile. |
| Root extensions | Do not add an EKU to the Root certificate where the TLS BR Root profile prohibits it. Express the single trust purpose through hierarchy design, subordinate EKU, CP/CPS and program submissions. |
| Issuing CA | RSA 4096-bit minimum; critical CA constraints and keyCertSign+cRLSign; serverAuth-only EKU; no anyExtendedKeyUsage; appropriate path length, SKI/AKI, AIA/CRLDP and certificate policies as required by the exact profile. |
| Subscriber certificates | Follow current TLS BR subscriber key, signature, SAN, EKU, serial, validity, CT, AIA/CRL and policy profiles. Prefer customer-generated private keys and CSR; never retain customer private keys by default. |

**HSM / cryptographic module:** TLS BR v2.3.1 requires CA private keys to be protected in a validated system/device meeting at least FIPS 140-2 Level 3, FIPS 140-3 Level 3, or an appropriate Common Criteria Protection Profile/Security Target EAL 4 or higher. Select a module whose exact certificate, firmware, operating mode, configuration, lifecycle status and intended use are verified by the auditor. A product marketing statement alone is insufficient.

### 3.3 Root key-generation ceremony and lifecycle

Do not generate the Root key until every pre-ceremony gate in Section 8 is passed.

- Engage a qualified independent auditor before key generation.
- Prepare and approve a deterministic Key Generation Script, ceremony plan, participant list, trusted-role assignments, physical security plan, evidence plan and contingency/recovery plan.
- Have the qualified auditor witness the entire Root key generation ceremony or record the complete ceremony as permitted by TLS BR; obtain the auditor's report.
- Generate the key in the qualified cryptographic module in a physically secure environment.
- Use trusted-role personnel, multi-person control and split knowledge; no single-person custody or activation.
- Record UTC timestamps, module identity/certification, firmware, configuration, participant identities/roles, approvals, ceremony steps, outputs, exceptions and evidence hashes.
- Create the SHA-256 SPKI fingerprint and include it in the annual key-lifecycle reports.
- Define backup, recovery, transport, activation, deactivation, compromise response, rollover and destruction before key generation.
- Keep annual full-surveillance audit coverage continuous from the exact Root key-generation date. No audit gaps.
- Keep Root key physically and logically separated from all online Certificate Systems. Use a separate secured network/zone for Root systems.

Mozilla will not accept a new Root inclusion request if the corresponding Root key pair is more than five years old at submission. Mozilla also requires continuous annual audit coverage from key generation, so generating a key prematurely starts the evidence clock before the CA is ready.

### 3.4 CA infrastructure and roles

- Physically secure facilities and independently documented access controls.
- Root CA System on a physically separate network from all other CA infrastructure.
- Separate online Issuing CA signing service and issuance orchestration/API.
- HSM-backed CA signing; private key material is non-exportable where supported and required by the chosen module design.
- Trusted roles: CA management, security officer, system administrator, validation specialist, certificate approver, key custodian, auditor and incident responder. Document segregation and conflicts.
- MFA for all CA infrastructure and issuance-capable accounts; least privilege; individual identities; no shared credentials unless attributable and explicitly controlled.
- Multi-party physical access to Root CA systems; dual control and split knowledge for sensitive ceremonies and recovery.
- Quarterly access reviews, timely deprovisioning, secure workstation controls, hardened builds, vulnerability management, annual independent penetration testing, centralized immutable/tamper-evident logs, time synchronization, alerting and incident response.
- Inventory every Certificate System, Security Support System, network boundary control, delegated party, service account and dependency.
- Review every cloud provider, DNS provider, HSM vendor, validation service and other subcontractor against applicable requirements; the CA owner remains accountable.

### 3.5 Domain validation and issuance controls

- Implement current TLS BR-compliant DV first. Do not advertise OV/EV/IV until the corresponding identity-validation processes, CP/CPS, automation and audits are fully ready.
- Implement ACME v2 and ACME Renewal Information (ARI); automate account lifecycle, authorization, order, issuance, retrieval, renewal and revocation.
- DNS-01, HTTP-01 and TLS-ALPN-01 may be implemented only according to the exact currently permitted TLS BR methods and their effective dates. Keep method sunset dates in policy-as-code.
- Implement CAA processing and DNSSEC validation as required. A DNSSEC validation error must not be treated as permission to issue.
- Implement Multi-Perspective Issuance Corroboration. As of 2026-11-01, the TLS BR schedule requires at least four remote Network Perspectives across at least two distinct RIR service regions; from 2026-12-15 it requires at least five. Design and test five remote perspectives from day one, in addition to the primary perspective. Enforce perspective separation, resolver/network independence, required geographic distance, authenticated encrypted communication and no shared DNS cache that would defeat independence.
- Perform pre-sign certificate linting and policy checks. Reject malformed, unauthorized, weak-key, prohibited-name, CAA-prohibited or nonconforming requests.
- Apply abuse prevention, rate limits, high-risk request review, name authorization, account binding, incident escalation and mass-revocation readiness.
- Provide a publicly accessible, well-documented certificate repository and test websites for valid, revoked and expired certificates.
- Do not issue MITM/interception certificates or certificates without verified subscriber authorization.

### 3.6 Certificate transparency and revocation

- Integrate with currently accepted Certificate Transparency logs and validate SCT requirements for each issuance profile.
- Monitor CT logs for unauthorized or anomalous issuance and publish incident handling procedures.
- Operate reliable, externally reachable OCSP and CRL services with monitoring, redundancy, tested publication schedules and documented failure handling.
- Support reason-coded revocation, prompt subscriber notification, mass revocation, key compromise and incident response within the strictest applicable deadlines.
- Provide 24/7 monitored incident/revocation contacts and a tested escalation process.
- Maintain revocation status for Root/Issuing hierarchy as required; never use the Root to issue subscriber certificates.
- Microsoft requires issuing CA and subscriber certificate revocation information through the specified CRL/OCSP profile and requires reason codes for intermediate revocations.

### 3.7 Certificate validity and automation roadmap

The current TLS BR schedule requires the issuance engine to adapt to shorter certificate lifetimes. As of 2026-11-01, maximum subscriber validity is 200 days. The published schedule reduces the maximum to 100 days on 2027-03-15 and 47 days on 2029-03-15. Domain/IP validation reuse also becomes shorter (100 days in 2027 and 10 days in 2029).

Design for fully automated renewal well below these maximums. The CA must be capable of safe high-volume issuance, renewal, revocation and customer notification without manual bottlenecks. Build ACME ARI and lifecycle telemetry now, not as a later patch.

## 4. Program-specific readiness matrix

| Requirement | Mozilla | Chrome | Apple | Microsoft | Project control |
|---|---|---|---|---|---|
| Dedicated TLS-only Root | Required for new TLS Roots | Strongly align to dedicated public TLS hierarchy | Required single Trust Purpose | Required dedicated trust purpose for new Roots from 2026-07-01 | TLS-only Root and Issuer; no other EKUs/purposes |
| RSA 4096 CA keys | Meets conservative baseline; TLS BR min applies | Meets conservative baseline | Explicit new Root minimum | Supported; exceeds Windows TLS Root minimum | RSA 4096 for Root and subordinate CA keys |
| Root validity | Root key lifetime limited to 15 years from key generation for websites trust | Follow current policy | Follow current policy | New Root maximum 10 years from submission | Plan within TLS BR 8–25-year profile and MS max 10-year intersection |
| Root generation ceremony | Auditor-witnessed report; key age <=5 years at application | Evidence and security culture scrutinized | Key lifecycle reporting and applicable ceremony controls | Key generation/technical requirements and audit evidence | Qualified auditor engaged before ceremony; complete ceremony evidence |
| Continuous audit | Annual full-surveillance coverage from key generation, no gaps | Qualifying audits and operational maturity | Annual audit; WebTrust preferred | Pre-commercial and annual qualifying audit | WebTrust CA + TLS/SSL Baseline + Network Security; continuous annual schedule |
| Detailed control reporting | DCR for audit periods beginning on/after 2027-07-01 | Evidence of effective controls | DCR attestation from audit periods beginning on/after 2027-07-01 | Qualifying attestation | Auditor maps controls, tests, evidence, design and operating effectiveness |
| CP/CPS | Detailed, accurate and public; current practices | Public, accurate policy and operational disclosures | Single-purpose combined CP/CPS; Markdown requirement from 2027-07-01 | Public and updated before operational changes | One authoritative TLS-only Markdown CP/CPS with changelog |
| Broad public value | Risk-based public review | Explicit broad value, security-first culture, active TLS use; narrow scope/closed subscriber base risks rejection | Explicit broad value | Commercial public CA, not internal-only | Open public issuance to unrelated domains/subscribers, subject to law |
| Automated issuance | Automation for each intended TLS certificate type; test issuance at least every 30 days | ACME and ARI positive indicators | Automated operations expected through BRs | Operational automation supports reliability | ACME v2 + ARI + renewal and test-site automation |
| Multi-perspective validation | TLS BR | TLS BR | TLS BR | TLS BR | Five remote perspectives, >=2 RIR regions, from launch |
| Revocation/incident response | TLS BR timelines, mass revocation and public incidents | Strong incident record and prompt response | Annual lifecycle reporting, incident and revocation obligations | 24/7 contact, reason codes, revocation response | Redundant OCSP/CRL, 24/7 contacts, drills, mass revocation plan |
| CCADB disclosure | Required | Application path | Required | Required | Complete and maintain all owner/root/subordinate/audit/policy/incident data |
| Public test evidence | Valid/revoked/expired and recurring test issuance | Public evidence and discussion | Due diligence and public value | Audit and operational evidence | Public test endpoints, automated renewals, public CP/CPS and repository |

## 5. Important differences and non-guarantees

1. **No universal approval:** Mozilla, Google, Apple and Microsoft each control their own Root Store. Acceptance by one does not bind another. Other browsers, OS distributions, Java runtimes, Android OEMs, embedded devices and enterprise-managed stores may maintain additional trust stores or policies.
2. **Chrome's public-value threshold is substantive:** a technically compliant CA can still be rejected if it only serves existing subscribers, a limited set of TLDs, or does not demonstrate meaningful benefit to Chrome users and the public TLS ecosystem.
3. **Apple's Root Program is discretionary:** broad value, due diligence, purpose scoping and program priorities remain independent decision factors.
4. **Mozilla's five-year key-age limit and continuous audits make ceremony timing critical:** do not generate a Root key before readiness and auditor engagement.
5. **Microsoft's 10-year maximum Root validity is stricter than the TLS BR maximum:** use the intersection, not the less restrictive baseline.
6. **Other platforms are not automatically covered:** after the four major programs, evaluate Android/OEM, Java/OpenJDK, Linux distribution, embedded/browser-vendor and enterprise stores separately. Do not claim universal trust merely because the four primary programs accept the Root.
7. **No external CA in the issuance chain:** the intended new hierarchy is owned and operated by Iran CA Center. ACME is a protocol, not an external issuer. The Root Store applications are the mechanism by which clients may later trust the self-signed Root.

## 6. Business and legal eligibility gate

Before spending on HSMs or generating keys, confirm and document:

- The CA Owner is a real legal entity with authority to operate a public CA and publish CP/CPS, audit statements, certificate repositories, incident reports and contact information.
- Ownership, governance, controlling persons, jurisdictions, legal obligations, sanctions/export-control screening, data residency and service availability have been reviewed by qualified counsel and the prospective auditor.
- The CA can provide public issuance to unrelated subscribers worldwide (or clearly document lawful geographic limits and evaluate their effect on broad-value criteria).
- The CA can maintain 24/7 security, incident and revocation response with at least two named trusted program contacts.
- The business has a realistic plan for sufficient public TLS certificate issuance and long-term operations. Chrome explicitly considers active use and public ecosystem value.
- All cloud, hosting, DNS, HSM, validation and audit vendors can meet the applicable obligations and provide sufficient evidence.

A legal or commercial eligibility concern is a stop condition, not something to solve by changing certificate extensions.

## 7. Repository and product implications

CA Panel is an orchestration product, not itself proof of public trust. The new platform architecture must separate:

- Public-facing subscriber portal and ACME API;
- Registration Authority / domain-validation service;
- policy engine and certificate linting;
- multi-perspective validation orchestration;
- issuance approval and HSM signing service;
- CT submission and monitoring;
- OCSP/CRL publication;
- certificate inventory, audit evidence and immutable logs;
- incident, revocation and mass-revocation operations;
- CCADB/policy/audit disclosure workflows.

Production code must not have direct access to Root private keys. Issuing CA private keys must be protected by compliant cryptographic modules and tightly controlled signing services. All high-risk issuance and administrative operations must require strong authorization and immutable audit records.

## 8. Pre-ceremony go/no-go gates

**No Root key generation until every gate is evidenced and approved.**

- [ ] Legal entity, ownership, jurisdiction and global public-service model approved.
- [ ] Preliminary written feedback / eligibility discussions sought from target Root Programs where possible; no assumption of acceptance.
- [ ] Independent qualified WebTrust auditor engaged and audit criteria, scope and start date agreed.
- [ ] Current policy versions and future effective dates captured in a requirements register with an owner and review cadence.
- [ ] TLS-only CP/CPS drafted, reviewed by counsel/auditor and ready for publication.
- [ ] HSM procurement completed; exact FIPS/CC validation certificate, module version, firmware and operating mode independently verified.
- [ ] Root and Issuer facilities, network segmentation, access control, trusted roles, MFA and multi-party controls implemented and tested.
- [ ] Key Generation Script, witnessed ceremony, evidence retention, backup/recovery, compromise, rollover and destruction plans approved.
- [ ] Issuing CA, validation service, five remote network perspectives, DNSSEC/CAA, ACME/ARI, CT, OCSP/CRL and monitoring tested using disposable non-production keys.
- [ ] Mass revocation, incident response, disaster recovery and 24/7 escalation drills completed.
- [ ] Public test websites, repository, status/incident channels and automated test-certificate renewal are operational.
- [ ] Auditor confirms readiness and records the formal go/no-go approval.
- [ ] Only then schedule and perform the Root ceremony; begin uninterrupted annual audit coverage immediately.

## 9. Implementation phases

1. **Policy and eligibility:** legal entity, business case, target Root Store policies, qualified auditor, WebTrust path, CP/CPS.
2. **Facility and HSM:** physical security, module validation, Root/Issuer separation, trusted roles, ceremony and lifecycle controls.
3. **Non-production platform:** test hierarchy, ACME/ARI, five-perspective validation, CAA/DNSSEC, linting, CT, OCSP/CRL, monitoring, mass revocation, public test sites.
4. **Readiness audit:** independent control design and operating effectiveness review; close findings; verify all policy versions and effective dates.
5. **Root key ceremony:** auditor-witnessed generation and complete evidence package; no earlier.
6. **Issuing hierarchy and controlled public pilot:** only after the Root/Issuer chain, audits and policy requirements permit it; do not imply public browser trust before Root inclusion.
7. **Root Store applications:** CCADB and separate submissions to Mozilla, Chrome, Apple and Microsoft, each with tailored evidence and ongoing communications.
8. **Ongoing operation:** annual audits, continuous key lifecycle reports, policy updates, incident disclosures, automation, security testing and monitoring of all program changes.

## 10. Change control for this document

This is a living requirements baseline. Review it at least monthly during design and before each key ceremony, certificate profile change, audit period, and Root Store submission. Record the policy URL, version, effective date, review date, reviewer, impact, owner and evidence for each change.

No design decision in this document authorizes key generation, Root issuance, public issuance, migration of the existing CA, or a claim of browser trust.
