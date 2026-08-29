---
type: Playbook
title: "workload-identities"
description: "Ask whether a machine-to-machine credential is confined to the tenant it was issued in, by sending one leased workload token to a route while a second tenant is named first in the request line and then in the header that selects one, and closing on a Test whose own assertions carry the difference."
resource: ../../../src/redkraken/playbooks/workload-identities/playbook.md
tags: [authorization, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: authorization
bb:outputs: [authorization.tenant_isolation]
bb:triggers_all: [header_parameter, tenant_boundary, unknown_auth_endpoint]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 59906c89cb22236c240fb05c240cc66d0a48e0a6d5388db8d079cbe13b416c93
bb:sha256: 2f5fba4e2ef6b9b486444fc6dc4ca89bb9d5a398a1b2b8b331874b68924a4e83
---

# Ask whether a machine-to-machine credential is confined to the tenant it was issued in, by sending one leased workload token to a route while a second tenant is named first in the request line and then in the header that selects one, and closing on a Test whose own assertions carry the difference.

## What it concludes about

- `authorization.tenant_isolation`

## When it is selected

A subject carrying every one of these facts:

- `header_parameter`
- `tenant_boundary`
- `unknown_auth_endpoint`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's workload-identities pack against the tenant-isolation leaf of the ticket 18 vocabulary, and rewritten for ticket 101 against the merged ledger's four readings for this slug. The shipped page put the tenant selector in a header alone, which before ticket 211 no Test action could state; the request-line reading is now spelled first and the header reading second, and both close a Test. The refuted variant kind is response_differential rather than an invariant, because close_test_replay reads the Observation kind off the Test specification and not off the outcome. The duplicated-header variant is blocked and credential harvesting is refused, and both are named at the end rather than dropped. Repaired in review -- section 4 had no control action of its own and both sections leaned on a second Task's refusal that no Test can cite, so the negative is now an arm the leased credential itself sends and each Test carries an in-spec control.

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/workload-identities/playbook.md`](../../../src/redkraken/playbooks/workload-identities/playbook.md). This concept describes that document and never replaces it.
