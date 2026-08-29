---
type: Playbook
title: "command-directory-injection"
description: "Ask whether a value the caller supplies is concatenated into a command line, by sending one separator with a token that would print, then one payload from each of three interpreter grammars, then a bounded delay beside an inert twin, and by reading an arrival on a declared channel where nothing comes back at all."
resource: ../../../src/redkraken/playbooks/command-directory-injection/playbook.md
tags: [injection, approval_required, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.command]
bb:triggers_all: [file_parameter, multipart_request, state_changing_method]
bb:skills: [compare-responses, use-identity]
bb:risk: approval_required
bb:effects: read_only
bb:baseline: stable_session
bb:version: b8a64215c4246de48ee2a188dee830b59fa3bc33dd1065ffb880f1d4cdf28e4e
bb:sha256: 6530ff50b09d8f2ba74bfed1831e01308d399b98ef6a225853be85a11c309edb
sources:
  - id: command-directory-injection--command-injection-filter-bypass
    resource: /references/command-directory-injection--command-injection-filter-bypass.md
    title: "Command injection filter bypass: read for the refutation, not the payload"
    author: human:maintainer
  - id: command-directory-injection--ldap-injections
    resource: /references/command-directory-injection--ldap-injections.md
    title: "LDAP injection: attached here, graded elsewhere"
    author: human:maintainer
  - id: command-directory-injection--os-command-injection
    resource: /references/command-directory-injection--os-command-injection.md
    title: "OS command injection: what the Playbook drives and what it refuses"
    author: human:maintainer
  - id: command-directory-injection--shells
    resource: /references/command-directory-injection--shells.md
    title: "Shells: the grammar behind the separator list"
    author: human:maintainer
  - id: command-directory-injection--xxe
    resource: /references/command-directory-injection--xxe.md
    title: "XXE: attached here, graded by structured-injection"
    author: human:maintainer
---

# Ask whether a value the caller supplies is concatenated into a command line, by sending one separator with a token that would print, then one payload from each of three interpreter grammars, then a bounded delay beside an inert twin, and by reading an arrival on a declared channel where nothing comes back at all.

## What it concludes about

- `injection.command`

## When it is selected

A subject carrying every one of these facts:

- `file_parameter`
- `multipart_request`
- `state_changing_method`

Risk `approval_required`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 53 as the v2 replacement for v1's command-directory-injection pack against the command leaf of the ticket 18 vocabulary; the pack's five pages are attached as maintainer references, two describe classes graded elsewhere, and every escalation step in the other three is refused by the closing section. Rewritten for ticket 101 against the merged ledger, which carries six procedures, one refusal and one blocked reading. Two keys moved and the arrival reading stops at an Observation. The supported variant row leaves timing_differential for response_differential, because five of this slug's six executable readings close on an echo or a shape the Test's own assertions carry and only one is a timing pair, so the shipped bar made five of them unclosable; the refuted variant row follows it, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes. The pre-211 sentence that a read_only selection sends no body is gone.

## Maintainer references

- [command-injection-filter-bypass.md](/references/command-directory-injection--command-injection-filter-bypass.md)[^command-directory-injection--command-injection-filter-bypass]
- [ldap-injections.md](/references/command-directory-injection--ldap-injections.md)[^command-directory-injection--ldap-injections]
- [os-command-injection.md](/references/command-directory-injection--os-command-injection.md)[^command-directory-injection--os-command-injection]
- [shells.md](/references/command-directory-injection--shells.md)[^command-directory-injection--shells]
- [xxe.md](/references/command-directory-injection--xxe.md)[^command-directory-injection--xxe]

[^command-directory-injection--command-injection-filter-bypass]: Command injection filter bypass: read for the refutation, not the payload
[^command-directory-injection--ldap-injections]: LDAP injection: attached here, graded elsewhere
[^command-directory-injection--os-command-injection]: OS command injection: what the Playbook drives and what it refuses
[^command-directory-injection--shells]: Shells: the grammar behind the separator list
[^command-directory-injection--xxe]: XXE: attached here, graded by structured-injection

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/command-directory-injection/playbook.md`](../../../src/redkraken/playbooks/command-directory-injection/playbook.md). This concept describes that document and never replaces it.
