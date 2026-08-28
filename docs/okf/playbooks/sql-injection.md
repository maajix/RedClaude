---
type: Playbook
title: "sql-injection"
description: "Ask whether a query parameter is concatenated into a SQL statement rather than bound to it, by sending one request as two arms whose payloads differ only in a clause the database evaluates and differencing the two stored responses against a neutral baseline."
resource: ../../../src/redkraken/playbooks/sql-injection/playbook.md
tags: [injection, constrained, read_only]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: draft
stale_after: 2027-03-15T00:00:00Z
bb:category: injection
bb:outputs: [injection.query_language]
bb:triggers_all: [authenticated_endpoint, query_parameter, tech_sql]
bb:skills: [compare-responses, use-identity]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:version: 4413bd5b31231faceb33fa79bdde7608cb9a02cf033c658a71ba124a3e018602
bb:sha256: b262e279d54e33100001b80eeb603bedbcdedd9bd8e7ddbc992b4cd7fa16270d
sources:
  - id: sql-injection--sqli-advanced-sqli-techniques
    resource: /references/sql-injection--sqli-advanced-sqli-techniques.md
    title: "Advanced SQL injection techniques: mostly out, one thing kept"
    author: human:maintainer
  - id: sql-injection--sqli-advanced-sqlmap
    resource: /references/sql-injection--sqli-advanced-sqlmap.md
    title: "sqlmap: why this Playbook does not run it"
    author: human:maintainer
  - id: sql-injection--sqli-blind-sql-injection
    resource: /references/sql-injection--sqli-blind-sql-injection.md
    title: "Blind SQL injection: the differential without the extraction"
    author: human:maintainer
  - id: sql-injection--sqli-custom-tampering
    resource: /references/sql-injection--sqli-custom-tampering.md
    title: "Custom tampering: telling the filter apart from the database"
    author: human:maintainer
  - id: sql-injection--sqli-identifying-vulnerabilities
    resource: /references/sql-injection--sqli-identifying-vulnerabilities.md
    title: "Identifying SQL injection: where the reading actually starts"
    author: human:maintainer
  - id: sql-injection--sqli-intro-to-mssql-sql-server
    resource: /references/sql-injection--sqli-intro-to-mssql-sql-server.md
    title: "MSSQL: the dialect facts, minus the escalation path"
    author: human:maintainer
  - id: sql-injection--sqli-leaking-netntlm-hashes
    resource: /references/sql-injection--sqli-leaking-netntlm-hashes.md
    title: "Leaking NetNTLM hashes: out entirely"
    author: human:maintainer
  - id: sql-injection--sqli-out-of-band-dns
    resource: /references/sql-injection--sqli-out-of-band-dns.md
    title: "Out-of-band DNS: the last-resort channel, and the reasons it stays shut"
    author: human:maintainer
  - id: sql-injection--sqli-postgresql-specific-techniques
    resource: /references/sql-injection--sqli-postgresql-specific-techniques.md
    title: "PostgreSQL: the dialect facts, minus the escalation path"
    author: human:maintainer
  - id: sql-injection--sqli-remote-code-execution
    resource: /references/sql-injection--sqli-remote-code-execution.md
    title: "SQL injection to code execution: out, and where the impact goes instead"
    author: human:maintainer
  - id: sql-injection--sqli-time-based-sqli
    resource: /references/sql-injection--sqli-time-based-sqli.md
    title: "Time-based SQL injection: the noisiest channel, and its control"
    author: human:maintainer
  - id: sql-injection--sqli
    resource: /references/sql-injection--sqli.md
    title: "SQL injection: the core page and what survives of it"
    author: human:maintainer
---

# Ask whether a query parameter is concatenated into a SQL statement rather than bound to it, by sending one request as two arms whose payloads differ only in a clause the database evaluates and differencing the two stored responses against a neutral baseline.

## What it concludes about

- `injection.query_language`

## When it is selected

A subject carrying every one of these facts:

- `authenticated_endpoint`
- `query_parameter`
- `tech_sql`

Risk `constrained`, effects `read_only`, baseline `stable_session`.

## Skills it loads

- [compare-responses](/skills/compare-responses.md)
- [use-identity](/skills/use-identity.md)

## What it owes before a claim moves

- to `refuted`: at least 1 refutes `response_invariant` observation(s) from a `variant`
- to `supported`: at least 1 supports `response_invariant` observation(s) from a `control`
- to `supported`: at least 1 supports `response_differential` observation(s) from a `variant`

## Provenance

Written for ticket 53 as the v2 replacement for v1's sql-injection pack against the query_language leaf of the ticket 18 vocabulary; the pack's twelve pages are attached as maintainer references and every extraction, union and escalation step in them is refused by step 6.

## Maintainer references

- [sqli-advanced-sqli-techniques.md](/references/sql-injection--sqli-advanced-sqli-techniques.md)[^sql-injection--sqli-advanced-sqli-techniques]
- [sqli-advanced-sqlmap.md](/references/sql-injection--sqli-advanced-sqlmap.md)[^sql-injection--sqli-advanced-sqlmap]
- [sqli-blind-sql-injection.md](/references/sql-injection--sqli-blind-sql-injection.md)[^sql-injection--sqli-blind-sql-injection]
- [sqli-custom-tampering.md](/references/sql-injection--sqli-custom-tampering.md)[^sql-injection--sqli-custom-tampering]
- [sqli-identifying-vulnerabilities.md](/references/sql-injection--sqli-identifying-vulnerabilities.md)[^sql-injection--sqli-identifying-vulnerabilities]
- [sqli-intro-to-mssql-sql-server.md](/references/sql-injection--sqli-intro-to-mssql-sql-server.md)[^sql-injection--sqli-intro-to-mssql-sql-server]
- [sqli-leaking-netntlm-hashes.md](/references/sql-injection--sqli-leaking-netntlm-hashes.md)[^sql-injection--sqli-leaking-netntlm-hashes]
- [sqli-out-of-band-dns.md](/references/sql-injection--sqli-out-of-band-dns.md)[^sql-injection--sqli-out-of-band-dns]
- [sqli-postgresql-specific-techniques.md](/references/sql-injection--sqli-postgresql-specific-techniques.md)[^sql-injection--sqli-postgresql-specific-techniques]
- [sqli-remote-code-execution.md](/references/sql-injection--sqli-remote-code-execution.md)[^sql-injection--sqli-remote-code-execution]
- [sqli-time-based-sqli.md](/references/sql-injection--sqli-time-based-sqli.md)[^sql-injection--sqli-time-based-sqli]
- [sqli.md](/references/sql-injection--sqli.md)[^sql-injection--sqli]

[^sql-injection--sqli-advanced-sqli-techniques]: Advanced SQL injection techniques: mostly out, one thing kept
[^sql-injection--sqli-advanced-sqlmap]: sqlmap: why this Playbook does not run it
[^sql-injection--sqli-blind-sql-injection]: Blind SQL injection: the differential without the extraction
[^sql-injection--sqli-custom-tampering]: Custom tampering: telling the filter apart from the database
[^sql-injection--sqli-identifying-vulnerabilities]: Identifying SQL injection: where the reading actually starts
[^sql-injection--sqli-intro-to-mssql-sql-server]: MSSQL: the dialect facts, minus the escalation path
[^sql-injection--sqli-leaking-netntlm-hashes]: Leaking NetNTLM hashes: out entirely
[^sql-injection--sqli-out-of-band-dns]: Out-of-band DNS: the last-resort channel, and the reasons it stays shut
[^sql-injection--sqli-postgresql-specific-techniques]: PostgreSQL: the dialect facts, minus the escalation path
[^sql-injection--sqli-remote-code-execution]: SQL injection to code execution: out, and where the impact goes instead
[^sql-injection--sqli-time-based-sqli]: Time-based SQL injection: the noisiest channel, and its control
[^sql-injection--sqli]: SQL injection: the core page and what survives of it

## The authoritative document

The execution contract is the closed `bb:` frontmatter of [`playbooks/sql-injection/playbook.md`](../../../src/redkraken/playbooks/sql-injection/playbook.md). This concept describes that document and never replaces it.
