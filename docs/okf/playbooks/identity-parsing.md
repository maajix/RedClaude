---
type: Playbook
title: "identity-parsing"
description: "Ask whether the identity an assertion is trusted for is the identity its signature actually covers, by submitting one signed document whose subject is stated twice, one with every signature removed, one missing a required element, and one where a genuine credential is posted beside somebody else's name."
resource: ../../../src/redkraken/playbooks/identity-parsing/playbook.md
tags: [authentication, approval_required, mutates_session]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: authentication
bb:outputs: [authentication.federation_trust]
bb:triggers_all: [state_changing_method, tech_saml]
bb:skills: [compare-responses, handle-untrusted-content, use-identity]
bb:risk: approval_required
bb:effects: mutates_session
bb:baseline: none
bb:version: 4a93ed2454899ccc60ed8b6901fd6377524e0349cb8df12fe9b6d2daf2469024
bb:sha256: 8ce46d7df05f2ad54e57f9dc1c4f2e644c9f4efc6e9c31263016942b4ea18d22
sources:
  - id: identity-parsing--saml
    resource: /references/identity-parsing--saml.md
    title: "SAML: signature wrapping, canonicalisation, and the parts that are not findings"
    author: human:maintainer
---

# Ask whether the identity an assertion is trusted for is the identity its signature actually covers, by submitting one signed document whose subject is stated twice, one with every signature removed, one missing a required element, and one where a genuine credential is posted beside somebody else's name.

## What it concludes about

- `authentication.federation_trust`

## When it is selected

A subject carrying every one of these facts:

- `state_changing_method`
- `tech_saml`

Risk `approval_required`, effects `mutates_session`, baseline `none`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [handle-untrusted-content](/skills/handle-untrusted-content.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `credential_effect` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's identity-parsing pack, against the federation-trust leaf of the ticket 18 vocabulary; the v1 saml text is attached as a maintainer reference and is the source of the wrapping technique this Playbook uses. Rewritten for ticket 101 against the merged ledger, which carries four readings and one blocked reading for this slug; three of the four are new. One key moved. The refuted variant row named response_invariant while the supported row of the same role names credential_effect, and one role writes one kind whichever way a reading goes, so the refuted row now names credential_effect too.

## Maintainer references

- [saml.md](/references/identity-parsing--saml.md)[^identity-parsing--saml]

[^identity-parsing--saml]: SAML: signature wrapping, canonicalisation, and the parts that are not findings

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/identity-parsing/playbook.md`](../../../src/redkraken/playbooks/identity-parsing/playbook.md). This concept describes that document and never replaces it.
