---
type: Playbook
title: "authentication"
description: "Ask whether the check happens rather than whether the secret is right, by presenting one credential in shapes the comparison was not written for, and by asking the same question of a recovery flow -- what its answer hands back, who addressed the link it built, whether the credential it minted is unique and single-use, and whether the step that completes the change compares anything at all."
resource: ../../../src/redkraken/playbooks/authentication/playbook.md
tags: [authentication, approval_required, mutates_account]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: authentication
bb:outputs: [authentication.credential_verification, authentication.recovery_flow]
bb:triggers_all: [email_valued_parameter, state_changing_method]
bb:skills: [compare-responses, enumerate-surface, use-identity]
bb:risk: approval_required
bb:effects: mutates_account
bb:baseline: none
bb:version: 452e7796fefa3352142175ff0625d345aa4d97fee211c572830bdedad7080a07
bb:sha256: 054b4f3cb96526a7ff8c940136978e2ad6b65db33d0d781ce69c088dd5525c11
sources:
  - id: authentication--cloud-aws-cognito
    resource: /references/authentication--cloud-aws-cognito.md
    title: "Hosted identity services, and which half of them is the target"
    author: human:maintainer
  - id: authentication--http-attacks-password-reset
    resource: /references/authentication--http-attacks-password-reset.md
    title: "Password reset: the flow the authentication Playbook is not allowed to run"
    author: human:maintainer
  - id: authentication--sign-up-login-register
    resource: /references/authentication--sign-up-login-register.md
    title: "Sign-up, login and register: three routes, and only one of them is the Playbook"
    author: human:maintainer
  - id: authentication--type-juggling
    resource: /references/authentication--type-juggling.md
    title: "Type juggling, and why it is the same question as a missing check"
    author: human:maintainer
---

# Ask whether the check happens rather than whether the secret is right, by presenting one credential in shapes the comparison was not written for, and by asking the same question of a recovery flow -- what its answer hands back, who addressed the link it built, whether the credential it minted is unique and single-use, and whether the step that completes the change compares anything at all.

## What it concludes about

- `authentication.credential_verification`
- `authentication.recovery_flow`

## When it is selected

A subject carrying every one of these facts:

- `email_valued_parameter`
- `state_changing_method`

Risk `approval_required`, effects `mutates_account`, baseline `none`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [enumerate-surface](/skills/enumerate-surface.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `credential_effect` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's authentication pack, against the credential-verification leaf of the ticket 18 vocabulary; four v1 texts are attached as maintainer references and the type-juggling one is the only one that named this defect. Rewritten for ticket 101 against the merged ledger, which carries eleven readings, three blocked and two refused for this slug. Four keys moved. bb:outputs gains authentication.recovery_flow, the emitter ticket 101 owes and the class ten of the sixteen rows read. bb:effects rises from mutates_session to mutates_account because section 5 completes a recovery on an account the Program designates, and bb:risk rises with it to approval_required, the floor that effect asks for. bb:skills gains enumerate-surface, already held by the role that executes this text. The refuted variant row moves from response_invariant to credential_effect, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification.

## Maintainer references

- [cloud-aws-cognito.md](/references/authentication--cloud-aws-cognito.md)[^authentication--cloud-aws-cognito]
- [http-attacks-password-reset.md](/references/authentication--http-attacks-password-reset.md)[^authentication--http-attacks-password-reset]
- [sign-up-login-register.md](/references/authentication--sign-up-login-register.md)[^authentication--sign-up-login-register]
- [type-juggling.md](/references/authentication--type-juggling.md)[^authentication--type-juggling]

[^authentication--cloud-aws-cognito]: Hosted identity services, and which half of them is the target
[^authentication--http-attacks-password-reset]: Password reset: the flow the authentication Playbook is not allowed to run
[^authentication--sign-up-login-register]: Sign-up, login and register: three routes, and only one of them is the Playbook
[^authentication--type-juggling]: Type juggling, and why it is the same question as a missing check

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/authentication/playbook.md`](../../../src/redkraken/playbooks/authentication/playbook.md). This concept describes that document and never replaces it.
