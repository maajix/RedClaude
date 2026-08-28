---
type: Playbook
title: "authentication"
description: "Ask whether the server actually checks the secret it was sent, by presenting one credential three ways -- correct, wrong, and structurally absent -- and reading which of the three it answers as if it had verified something."
resource: ../../../src/redkraken/playbooks/authentication/playbook.md
tags: [authentication, constrained, mutates_session]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: authentication
bb:outputs: [authentication.credential_verification]
bb:triggers_all: [email_valued_parameter, state_changing_method]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: mutates_session
bb:baseline: none
bb:version: 68ffc9b0ebfe543f9b8f0a8050f89906227d92001986fe40a995250872addff9
bb:sha256: d6c57e8546481aa8881da71ea46f2dfbc4c2a7675b0319c42a00a366455043b6
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

# Ask whether the server actually checks the secret it was sent, by presenting one credential three ways -- correct, wrong, and structurally absent -- and reading which of the three it answers as if it had verified something.

## What it concludes about

- `authentication.credential_verification`

## When it is selected

A subject carrying every one of these facts:

- `email_valued_parameter`
- `state_changing_method`

Risk `constrained`, effects `mutates_session`, baseline `none`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `control`
- to `supported`: at least 1 supports `credential_effect` observation(s) from a `variant`

## Provenance

Written for ticket 50 as the v2 replacement for v1's authentication pack, against the credential-verification leaf of the ticket 18 vocabulary; four v1 texts are attached as maintainer references and the type-juggling one is the only one that named this defect.

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
