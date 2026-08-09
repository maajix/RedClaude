---
description: Use when a response may differ across identities, tenants, or object owners, and the difference needs to be established rather than assumed.
allowed-tools: Read, Bash
bb:evidence_profile: two_identity_receipts
bb:scripts:
  - name: compare_responses.py
    description: Diff two captured responses, reporting only semantically meaningful differences.
    args:
      type: object
      properties:
        left: {type: string, description: Receipt id of the baseline response.}
        right: {type: string, description: Receipt id of the differential response.}
        ignore_headers: {type: array, items: {type: string}}
      required: [left, right]
      additionalProperties: false
---

# Authorization differential testing

Fixture skill for the ticket-09 probes. The prose body is the method — there is
no declarative step list, because the runtime executes gates, not procedures
(Q1).

Vary one authorization dimension at a time and compare response semantics, not
bytes. Detail in [references/methodology.md](references/methodology.md).
