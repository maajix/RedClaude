# CodeGraph is not the engagement graph, but a projection of one may be

CodeGraph is a code-intelligence index -- `@colbymchenry/codegraph` 1.5.0, MIT,
`github.com/colbymchenry/codegraph`, a tree-sitter extractor over a local SQLite
graph, already serving this repository from `.codegraph/codegraph.db`. Ticket 90
asked two things that turned out to have different answers. Whether it can be
the graph an Agent reads instead of `entities` and `relationships`: no, and the
reason is in the schema rather than in the queries. Whether its concept -- a
graph you query instead of a directory you read -- can be used over the files an
engagement produces: yes, but only after those files are projected into
something a parser can see, and that projection is the whole of the work.

The queries are good and were never in doubt. One `codegraph_explore` returns a
working set with call paths and blast radius where a grep-and-read loop takes
dozens of round-trips, and it follows dynamic-dispatch hops that grep cannot
see. The premise the ticket wanted tested -- that a tool built to answer "what
reaches this, and what does this reach" over code would answer the same question
over an attack surface -- is a fair premise. It fails on the other half of the
sentence: there is nothing to put in the index.

`nodes` declares `file_path`, `language`, `start_line`, `end_line`,
`start_column` and `end_column` all `NOT NULL`, and
`edges.source`/`edges.target` are foreign keys into it. Every node in this
repository's own index -- all 8,864 of them -- has a file path; a count of the
ones without is zero. Node ids are `class:<hash>`, `import:<hash>`,
`file:<path>`. The only write path in the published API is `indexAll`, which
walks a project directory; language selection is by file extension and
`codegraph.json` can remap an extension to a supported language and nothing
else. A domain would have to be given a file, a language and a line range before
the schema would accept it, and the fabricated file would then be the thing the
graph is about. The closest CodeGraph comes to an endpoint is a genuine one --
it emits `route` nodes for twenty routing frameworks and links them by
`references` edges to their handlers -- but that node exists only when the
target's server-side routing source is on disk, and it is still anchored at a
line in `urls.py`.

Scope decides it a second time. `nodes` and `edges` have no tenant column; an
index is bound to one directory. Program scoping would be filesystem convention,
against a harness where `entities.program_id` is `NOT NULL`, row-level security
enforces it, `artifact_references` refuses to dedupe across Programs even though
storage does, `packet.compile` will not accept a Program identifier because "the
connection is the whole scope", and `proposal._subject_fault` drops a citation
that resolves to another Program's row. Two engagements sharing a domain get two
unlinked nodes in two indexes -- the sharing that would have been the point is
the one thing a per-directory index cannot express -- and the alternative, one
index over both, is the cross-Program read this harness refuses everywhere else.

Containment closes it a third time, and it is the cheapest of the three to
state. The child runs `--read-only`, as user 65534, with three mounts and one
peer. `run_tool` bind-mounts `/input` readonly from bytes the supervisor staged,
opens `/work` only for a tool that declares outputs, and refuses a declared
output that is not a bare filename. A CodeGraph index is a directory containing
a database, a WAL, a shared-memory file, a daemon log, a pid and a socket. It is
not an output this contract can carry, and an ephemeral container re-indexing
from scratch on every run has thrown away the cached intelligence that was the
reason to want it. There is also nothing for a Receipt to attach to: an offline
tool has no network, so what it can earn is a `tool_runs` row and an Artifact --
which is what `js_routes` already earns.

That settles the child's side and leaves the operator's, which is the half worth
building. Engagements will be kept in `~/engagements/` -- the directory exists
and is empty today -- and they will fill with notes, findings, captured
responses and recovered sources. Pointed at that directory as it ships,
CodeGraph would index nothing: markdown, JSON, plain text and HTTP captures are
not among its thirty-four languages, and there is no language id to map them
onto. The proof is in its own index of this repository, which holds 211 of 236
Python files and **zero of 320 markdown files and zero of 187 SQL files**. Five
yaml files appear in `files` with `node_count = 0`.

What survives that is the pattern rather than the pointing. A node must carry a
file, a language and a line range, and a finding genuinely has all three --
`findings/F1.md`, lines 12-40 -- which is not true of a domain and is the
difference between the two halves of this ticket. So the shape worth testing is
a **derived, regenerable projection**: one generated module per engagement in a
language the parser reads, where each entity is a symbol carrying its label and
descriptor and each edge is a reference, emitted by a `SELECT` over the
`entities` and `relationships` this harness already holds. CodeGraph then works
unmodified, `explore` returns the working set with its neighbours, FTS5 covers
the prose, and the token saving -- which is the actual ask -- comes from never
reading a directory to answer a question about it. The linking is still the
work; the graph engine is the cheap part, and this is the cheapest way to find
out whether the engine's borrowed edge vocabulary says what an engagement means.

The one job CodeGraph is unambiguously built for, target source, is declined
separately and for its own reason. On a target's open-source repository it would
win. On the case the harness actually meets -- a fetched JavaScript bundle -- it
declines to answer: files over 1 MB are skipped by default, with "generated
bundles, minified JS" named as the reason. `js_routes` was written for exactly
that shape and reports a path only because a call to something that makes
requests was given it as an argument, with the offset so the claim can be
checked against the bytes. Its grounding rule is the thing a symbol table does
not have. Putting CodeGraph inside the harness for that case would mean a new
offline-tool row, a binary in the tool image, a wrapper to make a directory look
like a declared filename, and an npm dependency tree beside an application whose
`pyproject.toml` says `dependencies = []` and whose release gate fails if that
ever stops being true -- to reach a case the operator can already reach by
running `codegraph init` on a checkout, outside the harness, where it is doing
what it was built for.

## Consequences

- **The graph a child reads does not change.** `entities` and `relationships`
  remain the only graph this harness holds, `mcp__rk2__get_attack_surface`
  remains the only way a child reads it, and the packet remains what decides how
  much of it a child sees. Nothing about the boundary moves, and no production
  code path depends on CodeGraph.
- **The engagement index is derived and one-way, or it is not built.** Postgres
  is the source of truth. `~/engagements/` holds a projection that can be
  deleted and regenerated, read by the operator and the main agent, and never a
  place a finding is first written. Anything that became canonical there would
  be a second route around `submit_mission_result` and the runtime's promotion
  step, which is the one thing this harness refuses everywhere.
- **One spike gates the build.** A throwaway engagement projected into a
  generated module under `/tmp`, indexed, and asked the questions an operator
  actually asks -- "what is this finding about", "what hangs off this endpoint"
  -- measured against reading the equivalent markdown, in facts and in tokens.
  If the parser's edge kinds cannot carry `resolves_to` and `tests`, the answer
  is a few hundred lines of stdlib `sqlite3` with FTS5 and an edge vocabulary
  designed rather than borrowed, and CodeGraph's contribution was the pattern.
- **CodeGraph as shipped does not read an engagement directory.** Markdown, JSON
  and HTTP captures have no parser and no extension mapping. Anyone who runs
  `codegraph init ~/engagements` will get an index of nothing and should be told
  so here rather than discover it.
- **The traversal gap is ours, not a missing store.** "Which endpoints hang off
  this application", "what resolves to this host" -- the reason a child cannot
  ask is that `relationships` is not projected into `v_records` and no agent
  verb traverses it. That is a packet section and a contract in a schema that
  already has `program_id`, RLS, per-record revisions and SQL-computed digests.
  It is not a second graph.
- **The 1 MB skip is the reusable finding.** Any future code-intelligence tool
  evaluated for bundle analysis will have the same problem: these tools are
  built for repositories, and a minified bundle is the shape they are configured
  to ignore. `js_parse` already reports `minified` for exactly this reason.
- **Nothing was added to the tree, so nothing new can fail.** As with 0004, the
  decline half is recorded here rather than in code, which is the honest form
  for "we looked, and no"; the adopt half is a spike under `/tmp` until it earns
  a ticket.
