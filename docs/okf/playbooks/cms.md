---
type: Playbook
title: "cms"
description: "Ask whether the platform under an application ships a second route to the same records that skips the check the application's own route makes, by reading the application's route under a leased Identity and then asking a representation suffix, a platform format parameter, the platform's own route index and the platform's user namespace for the same records from a second Task this run hands on rather than opens."
resource: ../../../src/redkraken/playbooks/cms/playbook.md
tags: [authorization, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-05-15T00:00:00Z
bb:category: authorization
bb:outputs: [authorization.parallel_route]
bb:triggers_all: [authenticated_endpoint, read_method, tech_cms]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: e51832384cb20a85faabc6d0c14b638377a9e2015ccc1d7c9927c68a6dac0ae0
bb:sha256: 479755ce2429867474a2e75ca7fcb7bab56b5fd81d98a8330bc58368280c3da6
sources:
  - id: cms--cms-drupal
    resource: /references/cms--cms-drupal.md
    title: "Drupal: JSON:API as the parallel route, and the exploit chain around it"
    author: human:maintainer
  - id: cms--cms-joomla
    resource: /references/cms--cms-joomla.md
    title: "Joomla: the web services route, and the component sprawl around it"
    author: human:maintainer
  - id: cms--cms-wordpress
    resource: /references/cms--cms-wordpress.md
    title: "WordPress: the second door the platform ships, and the scan around it"
    author: human:maintainer
---

# Ask whether the platform under an application ships a second route to the same records that skips the check the application's own route makes, by reading the application's route under a leased Identity and then asking a representation suffix, a platform format parameter, the platform's own route index and the platform's user namespace for the same records from a second Task this run hands on rather than opens.

## What it concludes about

- `authorization.parallel_route`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `read_method`
- `tech_cms`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `content_match` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `content_match` observation(s) from a `variant`

## Provenance

Written for ticket 55 as the v2 replacement for v1's cms pack against the parallel_route leaf ticket 55 added; the pack's three platform pages are attached as maintainer references and their version tables, their plugin enumeration and their exploit lists are refused by the last section. Rewritten for ticket 101 against the merged technique ledger, which holds five executable readings and one hand-off for this slug -- cms was one of the nine thin Playbooks, at two rows, with three references that had produced nothing between them. The refuted leg moves from response_invariant to content_match, which is the kind its own role already asked for on the supported leg.

## Maintainer references

- [cms-drupal.md](/references/cms--cms-drupal.md)[^cms--cms-drupal]
- [cms-joomla.md](/references/cms--cms-joomla.md)[^cms--cms-joomla]
- [cms-wordpress.md](/references/cms--cms-wordpress.md)[^cms--cms-wordpress]

[^cms--cms-drupal]: Drupal: JSON:API as the parallel route, and the exploit chain around it
[^cms--cms-joomla]: Joomla: the web services route, and the component sprawl around it
[^cms--cms-wordpress]: WordPress: the second door the platform ships, and the scan around it

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/cms/playbook.md`](../../../src/redkraken/playbooks/cms/playbook.md). This concept describes that document and never replaces it.
