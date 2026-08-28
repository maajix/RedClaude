---
type: Playbook
title: "identity-parsing"
description: "Ask whether the identity an assertion is trusted for is the identity its signature actually covers, by submitting one signed document whose subject is stated twice and reading which of the two the relying party logged in."
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
bb:version: 9a1a02568efdbc9f93384474fb0c2774518fd31c821f3e0eb7a7d4551482fd00
bb:sha256: d6ba8d7fa539c4f3ecff595c2af3ff5d6f2b44ccbed1ac02867afe0cd10595cb
sources:
  - id: identity-parsing--saml
    resource: /references/identity-parsing--saml.md
    title: "SAML: signature wrapping, canonicalisation, and the parts that are not findings"
    author: human:maintainer
---

# Ask whether the identity an assertion is trusted for is the identity its signature actually covers, by submitting one signed document whose subject is stated twice and reading which of the two the relying party logged in.

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

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's identity-parsing pack, against the federation-trust leaf of the ticket 18 vocabulary; the v1 saml text is attached as a maintainer reference and is the source of the wrapping technique this Playbook uses.

## Maintainer references

- [saml.md](/references/identity-parsing--saml.md)[^identity-parsing--saml]

[^identity-parsing--saml]: SAML: signature wrapping, canonicalisation, and the parts that are not findings

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/identity-parsing/playbook.md`](../../../src/redkraken/playbooks/identity-parsing/playbook.md). This concept describes that document and never replaces it.
