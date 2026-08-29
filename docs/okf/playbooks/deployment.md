---
type: Playbook
title: "deployment"
description: "Ask whether a rule the deployment enforces in front of the application is enforced by the application behind it, by asking one refused path again under a second spelling that resolves to the same route, under each method the tool contract offers, under a client address the caller writes, and under a path the router reads out of a header the authoriser never saw, each arm against a control on a path nobody restricted."
resource: ../../../src/redkraken/playbooks/deployment/playbook.md
tags: [authorization, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-05-15T00:00:00Z
bb:category: authorization
bb:outputs: [authorization.edge_rule]
bb:triggers_all: [read_method, tech_edge_proxy, web_surface]
bb:skills: [compare-responses]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:version: 4dbb32fe88a2f9840757a8d1f3f5aa17bbea86afc1b23accad17895d3159bfed
bb:sha256: 4109938d9072332e7fb152e1eaf94b68ae01fd9dc42fc08ef364424608874f8c
sources:
  - id: deployment--apache-tomcat
    resource: /references/deployment--apache-tomcat.md
    title: "Apache Tomcat: where the `/..;/` trick came from, and what it is evidence of"
    author: human:maintainer
  - id: deployment--http-attacks-tls-attacks
    resource: /references/deployment--http-attacks-tls-attacks.md
    title: "Transport attacks: the whole page is refused, and this is the argument"
    author: human:maintainer
---

# Ask whether a rule the deployment enforces in front of the application is enforced by the application behind it, by asking one refused path again under a second spelling that resolves to the same route, under each method the tool contract offers, under a client address the caller writes, and under a path the router reads out of a header the authoriser never saw, each arm against a control on a path nobody restricted.

## What it concludes about

- `authorization.edge_rule`

## When it is selected

A subject carrying every one of these facts:

- `read_method`
- `tech_edge_proxy`
- `web_surface`

Risk `constrained`, effects `read_only`, baseline `none`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_differential` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 55 as the v2 replacement for v1's deployment pack against a new edge_rule leaf added by ticket 55; the pack's server pages are attached as maintainer references and their desync techniques, their TLS downgrade work and their default-credential lists are refused by the closing section. Rewritten for ticket 101 against the merged ledger, which carries five readings, one lead and five refusals for this slug; three readings are new and two of them became closeable only when ticket 211 let a Test action state its headers. One key moved -- the refuted variant row now asks for the kind its own supported row asks for, because close_test_replay derives one kind per role from the specification and a refuted leg asking for a second kind is a leg nothing can write.

## Maintainer references

- [apache-tomcat.md](/references/deployment--apache-tomcat.md)[^deployment--apache-tomcat]
- [http-attacks-tls-attacks.md](/references/deployment--http-attacks-tls-attacks.md)[^deployment--http-attacks-tls-attacks]

[^deployment--apache-tomcat]: Apache Tomcat: where the `/..;/` trick came from, and what it is evidence of
[^deployment--http-attacks-tls-attacks]: Transport attacks: the whole page is refused, and this is the argument

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/deployment/playbook.md`](../../../src/redkraken/playbooks/deployment/playbook.md). This concept describes that document and never replaces it.
