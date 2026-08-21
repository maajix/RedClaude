# 90 — Evaluate CodeGraph as the engagement graph

**What to build:** An answer, on record, to whether CodeGraph — the code-intelligence index this repository is already served by, whose publisher and licence are criterion 1 — can hold what an engagement actually is — domains, hosts, endpoints and the edges between them — and whether holding it there buys a hunt anything the Program-scoped `entities` and `relationships` tables do not already give it.

**Blocked by:** nothing. This is a reading and a measurement, and it changes no code unless the decision is adopt.

**Status:** resolved

- [x] What CodeGraph is, is written down before it is judged: publisher, licence, version, distribution, where the index lives, and what a node in it may be — specifically whether a node that is not a source symbol can exist at all, or whether every node is something a parser found in a file.
- [x] Where engagements live is written down as a path and a layout, together with what a hunt reads out of that directory today and what it writes back into it.
- [x] The comparison against what this harness already holds is a table of what each side can store and answer, not a preference. The other side of the table is `entities`, `relationships`, `artifact_references` and `mcp__rk2__get_attack_surface`.
- [x] The scope question is answered: a CodeGraph index is one directory's index, and a Program is the root of everything this harness scopes. Whether an index can be Program-scoped, and what happens when two engagements share a domain, is answered rather than assumed.
- [x] The containment question is answered: an index is a file on the runtime's disk and the child has no such file. Whether an Agent could read one, whether reading it would cross the door, and whether anything read out of it can become evidence with a Receipt behind it.
- [ ] The one job CodeGraph is unambiguously built for is tested against the real case: **target source code** — a fetched JavaScript bundle, an open-source repository belonging to the target — indexed, and the routes found in it linked to a domain. Measured against what `js_routes`, `js_map` and `extract_paths.py` already answer, in facts found and in tokens read.
- [x] A decision is recorded — adopt, adopt for one named job, or decline — with the reason, as an ADR under `docs/adr/` at `0006`. Declining is a result and closes this ticket. (`0005` belongs to ticket 89.)
- [x] No production code path depends on CodeGraph unless the decision is adopt. A spike lives under `/tmp` or is deleted.
- [x] The separation is respected and said out loud: engagement files live in the engagement directory and the harness repository holds none of them. Nothing proposed here puts an engagement path, an index, or a generated projection of one inside this repository or inside anything this repository commits.

## Why this is asked

The operator uses CodeGraph on this repository and asked whether the same thing
would help on the other side of the work: an engagement is a pile of domains,
hosts, endpoints, parameters and the relations between them, and that is a
graph whether or not anything calls it one. The premise worth testing is that a
tool built to answer "what reaches this, and what does this reach" over code
would answer the same question over an attack surface, and answer it in fewer
tokens than paging a packet.

The premise worth doubting is in the same sentence. CodeGraph's nodes are
symbols a parser found in a file. A domain is not a symbol and an endpoint is
not a file, so the question is not whether the queries would be useful — they
would — but whether there is anything to put in the index at all.

## What is already here, so the comparison is against the real thing

This harness already holds an engagement's surface as a graph, in Postgres, and
has since the schema was first written:

- `entities` are the nodes — hosts, endpoints, parameters and the rest — and
  every one of them is scoped to a Program. `relationships` are the edges.
- The Agent does not query that graph directly. `mcp__rk2__get_attack_surface`
  reads a **staged packet**, and the packet is what decides how much of the
  graph a child may see. `packet.Reader.attack_surface` is the whole of that
  surface: filter by entity type, take a page.
- Nothing an Agent proposes becomes a node by itself. `submit_mission_result`
  carries `new_entities` and `relationships` as *proposals*, and the runtime
  promotes them. A second graph an Agent could write to directly would be a
  second route around that.
- What an Agent reads out of a file is already recorded: `js_routes`, `js_map`
  and `js_parse` are registered offline tools, `extract_paths.py` is a Skill
  script, and every one of them files its output as an Artifact linked to a
  Tool run.

So the bar is not "CodeGraph can hold a graph". The bar is: it can hold one
**scoped to a Program**, reachable **without a second egress**, and producing
facts that are **attributable to a Receipt or an Artifact** — or it is a tool
the operator uses beside the harness rather than inside it, which is a smaller
and perfectly good answer.

## The boundary that must not move

The operator keeps engagements in `~/engagements/` and the harness in this
repository, and they are two places on purpose. An engagement holds captured
responses, scope documents, credentials and findings about somebody else's
system. This repository is a git repository that is pushed. A file that crossed
from the first into the second would be a disclosure, and it would be one that
happened quietly, because nothing about copying a file says who it belongs to.

So this ticket may not answer with anything that mixes them. An index over
`~/engagements/` lives under `~/engagements/`. A projection generated from the
database is written where the engagement is, not where the code is. This
repository gains, at most, the code that writes such a thing — never its output,
and never a path that only makes sense on one operator's machine.

`~/engagements/.codegraph/` already exists; the operator created it. It ships its
own `.gitignore` that ignores everything but itself, which is the same rule
stated one directory down.

## The questions, in the order they decide the ticket

1. **Is there anything to index?** An engagement directory holds notes,
   findings, captured responses and Artifacts. If CodeGraph indexes source
   symbols, most of that has no node. Establish what a node may be before
   anything else, because a negative answer here ends the ticket for the
   engagement half and leaves only question 4.
2. **Can an index be Program-scoped?** One index per directory is one scope per
   directory. Two engagements that share a domain either share a node — which
   is a cross-Program read this harness refuses everywhere else — or they do
   not, and the graph's value was the sharing.
3. **Who may read it, and does anything it says count?** The child has no disk
   but its own container and no peer but the door. An index the supervisor reads
   and stages into the packet is one design; an index the child reads is
   another and needs a mount, a tool row and a Receipt story. Say which, and
   what the evidence chain is either way.
4. **Does it beat what we have on target source?** This is the question that
   can be answered by measuring rather than by reading. One fetched JavaScript
   bundle, one open-source repository. Index it, ask it for routes, and set what
   comes back against what `js_routes` files today — same facts, fewer facts,
   more facts, and how many tokens each costs the model.

## What "no" looks like, and why it is fine

If CodeGraph's nodes are source symbols and nothing else, then the engagement
half is a decline and the honest form of it is one sentence: the graph an
engagement needs is the one already in `entities` and `relationships`, and what
was missing was never a graph engine. The operator keeps using CodeGraph on this
repository, where it is doing exactly what it was built for, and nothing about
the harness changes.

A partial yes is also a real result: **adopt for one named job** — indexing
target source code the harness has already fetched — is a smaller claim, has a
measurement behind it, and would sit next to `js_routes` rather than next to the
packet.

## Comments
Decided: decline it as the graph, keep it as a pattern. Recorded as
`docs/adr/0006-codegraph-is-not-the-engagement-graph.md`.

The schema answers question 1 and the answer ends the engagement half. `nodes`
declares `file_path`, `language`, `start_line` and `end_line` all `NOT NULL`,
node ids are `class:<hash>`, `import:<hash>` and `file:<path>`, and the only
write path in the published API is a directory walk. A domain is not a span in a
file, so it cannot be a node without being given a fabricated one. Pointed at an
engagement directory as it ships, CodeGraph indexes nothing: its own index of
this repository holds 211 of 236 Python files and zero of 320 markdown files and
zero of 187 SQL files.

Question 2 and question 3 each close it again on their own. `nodes` and `edges`
have no tenant column, so an index is one directory's scope and two engagements
sharing a domain get two unlinked nodes -- the sharing was the point. And an
index is a directory holding a database, a WAL, a shared-memory file, a log, a
pid and a socket, which is not a declared output `run_tool` can carry to a child
that has no disk but its own container.

What survives is the pattern, on the operator's side only: a derived,
regenerable projection of `entities` and `relationships` into a module a parser
can read, written under the engagement directory and never canonical. That is
the spike the ADR gates the build on, and it is deliberately not a ticket yet.

**Criterion 6 is not ticked and is not owed.** The measurement it asks for was
not run, because the case the harness actually meets removes its subject:
CodeGraph skips files over 1 MB by default and names "generated bundles,
minified JS" as the reason, so a fetched bundle is the shape it is configured to
ignore. The other half -- a target's open-source repository -- it would win, and
the operator can already reach that by running `codegraph init` on a checkout
outside the harness. Both are recorded in the ADR as a decline with a reason
rather than as work somebody still has to do. Anyone who disagrees should reopen
this criterion rather than assume it was forgotten.

The separation held throughout: nothing under `~/engagements/` was read into this
repository and nothing in this repository names a path under it.
