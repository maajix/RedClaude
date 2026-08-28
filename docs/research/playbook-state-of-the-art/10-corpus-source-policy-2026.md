# 10 — Corpus source policy for the fifty-Playbook rewrite

This file records the source boundary for ticket 101. It is the intake rule,
not yet the 50-row Playbook mapping that the ticket must produce.

## Local operator corpus

The operator's read-only sources are three directories, and the priority
between them is the operator's own instruction rather than a property of the
material.

**Primary intake, by operator direction:**
`/home/majix/Downloads/Pentest Docs` and
`/home/majix/Downloads/Personal-Knowledge-Base`. These are the operator's raw
personal notes. The operator stated the caveat when naming them: neither is
deduplicated and neither has been quality-checked. So a claim taken from them
is a lead, and the rewrite carries it only with the same provenance and stop
condition it would demand of any other source. Ticket 101's mining pass drew
444 of its local citations from this pair.

**Secondary intake:** `/home/majix/hacking-wiki`. Its index at
2026-08-27 lists 326 concept pages: 131 Web Attacks, 20 Authentication/JWT, 30
Infrastructure/Network, 15 Windows/AD/Lateral, 12 Crypto/TLS and smaller Cloud,
AI and methodology groups. The wiki schema carries source and confidence fields
and requires provenance markers for source-derived claims.

This corpus is not copied wholesale into Playbooks. For each technique the
rewrite extracts the precondition, harmless detection or control sequence,
payload family, ambiguity and stop condition. Tool instructions become Skills;
active values become registry rows; target-specific order becomes a Test. Raw
payload collections never become model-authored free-form actions merely
because they exist in the notes.

## Google Open Knowledge Format v0.2

The rewritten catalogue gets a dedicated OKF v0.2 knowledge view, using the
canonical specification at
<https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md>.
The older copy under Google's `knowledge-catalog/okf` repository explicitly
says it is frozen; it is not the implementation source.

The local hacking wiki is useful input and already has the central OKF shape --
Markdown concepts, YAML frontmatter, an index, a log and cross-links -- but it
is not currently evidence of v0.2 conformance. Its root `index.md` has no
`okf_version`, many Notion-imported pages omit the one always-required `type`,
and its `sources` and confidence fields predate v0.2's source objects,
`generated`, `verified`, `status` and `stale_after` families.

The integration therefore does not relabel the wiki as conformant. It builds a
validated project bundle whose concepts link to the authoritative Playbook,
Skill and maintained-reference files as resources. The domain compiler keeps
its closed `bb:` contract; OKF is the portable knowledge/provenance view, not a
second execution policy. Required checks are:

- root `index.md` declares `okf_version: "0.2"` and supports progressive
  disclosure;
- each concept has `type`, a concise description and normal Markdown links;
- sources use stable IDs and claims use matching Markdown footnotes;
- generation and independent verification remain separate, with OKF actor
  spellings;
- lifecycle and absolute freshness are explicit;
- unknown extension keys survive round trips;
- Playbook → Skill → Reference links are complete and unbroken inside the
  bundle;
- deprecated concepts remain linkable but are not routed into new work.

OKF trust tiers are advisory and are never treated as authorization. Likewise,
OKF Attested Computation is used only where a deterministic executor returns a
declared Receipt and a no-LLM attester can verify it; ordinary Playbook prose is
not mislabeled as an attested computation.

## Current external baseline

The external pass starts with versioned or dated primary sources:

- OWASP Web Security Testing Guide, using stable/versioned scenario identifiers:
  <https://wstg.owasp.org/>.
- OWASP ASVS 5.0.0, citing requirements as `v5.0.0-x.y.z`:
  <https://owasp.org/www-project-application-security-verification-standard/>.
- OWASP API Security Top 10 2023 for API-specific authorization, resource,
  inventory, SSRF and third-party-consumption risks:
  <https://owasp.org/API-Security/editions/2023/en/0x10-api-security-risks/>.
- PortSwigger Web Security Academy for executable black-box test sequences and
  PortSwigger Research for original technique papers:
  <https://portswigger.net/web-security> and
  <https://portswigger.net/research/top-10-web-hacking-techniques-of-2025>.
  The 2025 review is a discovery index, not authority by itself; the mapping
  follows each candidate to its original paper.
- NIST SP 800-115 for planning, execution, analysis and mitigation boundaries
  in technical infrastructure assessment:
  <https://csrc.nist.gov/pubs/sp/800/115/final>.
- MITRE ATT&CK Enterprise for platform-scoped infrastructure technique names
  and relationships, using a version permalink when the mapping freezes:
  <https://attack.mitre.org/matrices/enterprise/>.

The first current-research delta already visible is material. PortSwigger's
2025 review highlights parser differentials, HTTP/2 CONNECT, XS-Leaks, internal
cache poisoning, Unicode normalization, redirect-loop SSRF, ORM leaks and new
error-based SSTI techniques. `HTTP/1.1 Must Die` (published 2025) also makes the
existing `http-desync` Playbook name increasingly misleading: downgrade and
parser-discrepancy testing is current, while this harness still cannot safely
emit raw ambiguous framing. Ticket 101 must either give that Playbook a truthful
passive/differential scope and name the refusal, or rename/split it; it must not
pretend that a TLS reading executes desync.

## Required mapping row

Every one of the 50 Playbooks receives at least one ledger row with:

```text
playbook
technique
local_sources
external_sources (version/date)
preconditions
baseline / variant / control
payload_family
required_skill
runtime_writer
supported_evidence
refuted_evidence
stop_conditions
capability_state (reachable / blocked / refused / out_of_scope)
owner_ticket when not reachable
okf_concept
okf_source_ids
okf_trust_tier
okf_stale_after
```

A technique is admitted only when the row can name both a bounded execution
path and evidence the Runtime can write. Otherwise it is documented as blocked,
refused or out of scope with its reason. This is the join between ticket 101 and
ticket 166 and prevents a Playbook from looking complete while neither outcome
is reachable.
