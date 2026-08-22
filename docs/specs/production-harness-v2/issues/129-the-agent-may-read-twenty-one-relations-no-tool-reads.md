# 129 — The agent may read twenty-one relations no tool reads

**What to build:** For each relation on the agent's read surface that no tool
reaches, either the read that reaches it or the recorded decision that it stays
unreachable -- and then the grant follows the decision.

**Blocked by:** 107 — A label minted after launch must be resolvable in the run that minted it.

**Status:** ready-for-agent

- [ ] Every relation is placed in one of three buckets, in writing. The surface
      holds twenty-eight live relations after
      `20260922T000000Z__the_agent_connection_cannot_read_the_playbook_catalogue.sql:34-36`
      removed `playbooks` and `playbook_selections`; seven are named by a
      Contract's `reads=` tuple (`artifact_references`, `entities`, `findings`,
      `hypotheses`, `v_artifacts`, `v_evidence`, `v_records`); twenty-one are
      reached by no tool. The three buckets are: gets a read, keeps the grant
      with a stated reason, loses the grant.
- [ ] `negative_knowledge` and `negative_knowledge_retests`
      (`20260814T080000Z__a_refutation_is_kept_and_made_due.sql:1128`, `:1134`)
      are decided first, because they are the highest-value pair on the list:
      what has already been refuted, and when a refutation is due to be retried.
      An entire migration exists to keep refutations and make them due, both
      tables are on the surface, and no tool reads either. Ticket 114 owns the
      writer and the operator-side reader; this ticket owns the model's.
- [ ] `relationships` (`20260813T090000Z...:408`) is decided against a
      contradiction the audit found rather than in the abstract:
      `mcp__rk2__submit_mission_result` accepts a `relationships` element list
      (`src/redkraken/roster.py:686`), and `get_attack_surface` declares
      `reads=("v_records", "entities", "domains", ..., "identities")`
      (`roster.py:604-605`) without it. The model may propose graph edges it can
      never read back.
- [ ] The browser and tool-run evidence tables are decided as one group:
      `browser_runs`, `browser_steps`, `browser_step_results`
      (`20260814T040000Z...:519`, `:523`, `:527`), `tool_runs`
      (`20260814T030000Z...:429`), `tool_run_artifacts` (`:422`),
      `tool_run_inputs` (`20260814T050000Z...:243`), `tool_run_paths` (`:364`)
      and `test_run_receipts` (`20260815T000000Z...:2018`). These are what the
      model's own earlier work produced, and the reason they are unreadable
      today is ticket 107's: the packet is a pre-launch snapshot, so a row minted
      during the run has nowhere to be read from. That is why this ticket is
      blocked by 107 rather than beside it.
- [ ] The remainder is decided one by one and not in a batch: `entity_provenance`
      (`20260813T090000Z...:407`), `surface_facts` (`0032_playbooks.sql:700`),
      `events` (`20260810T094500Z...:366`), `report_templates`,
      `report_blocks` and `report_effects` (`20260820T000000Z...:939`, `:938`,
      `0034_reports.sql:1089`), `redaction_rules`
      (`20260821T000000Z...:595`), `program_required_headers`
      (`20260810T193000Z...:175`). Two are not defects and the ticket says so:
      `artifact_refs` (`20260810T151500Z...:211`) is reached indirectly through
      `v_artifacts`, and `rk2_state` (`0030_corpus_corrections.sql:263`) is a
      bookkeeping row.
- [ ] Where the answer is a read, the mechanism is the one that already exists
      rather than a new one: a `state.read` Contract, a section in
      `packet.SECTIONS` (`src/redkraken/packet.py:43`) and a `_records`-style
      compile step. Where the answer is no read, the grant comes off, because a
      grant is a claim that somebody reads it.

## Why

`docs/research/wiring/21-agent-surface-wiring.md` section 2.4. The read surface
is a declaration of what the model is allowed to know, and three quarters of it
is unreachable by any tool the model can call. Some of that is deliberate -- the
playbook catalogue removal has its own migration and its own reasoning -- and
the rest is undeclared, which the repo's own standard (`roster.py:800-805`)
counts as accidental.

Two neighbouring absences are recorded here rather than opened as their own
tickets, because both are plausibly operator-only and neither is stated as a
decision anywhere: the evidence bundle (`evidence.export` and `evidence.verify`,
reached only from `cli.py`) and the replay lane (`replay.run`, reached from
`cli.py` and `validation.py`). `redaction_rules` and `test_run_receipts` are
their read-surface halves, so whatever this ticket decides about those two
relations decides those two questions with them.

## The decision, taken 2026-08-22

**The default is that the grant comes off. A relation stays on the agent's read
surface only if this ticket can name the Contract that reads it and the packet
section that carries it; "somebody might want it" is not a reason, because that
is the reason all thirty-two are there. And the surface is not twenty-eight
relations, it is fifty-six -- the file view the ticket counts from is missing
twenty-one of them.**

### The measurement, taken against a live database

A database was provisioned from this checkout, all one hundred and fifty-three
migrations applied, and the grants read out of the catalogue. The result:

* **56 relations** carry a `SELECT` grant to `rk2_state`, every one of them a
  **column** grant -- `information_schema.table_privileges` returns *nothing* for
  that role, so there is no whole-table read anywhere on the surface. That is the
  design working: every read is an allowlist of columns.
* `state_read_surface` holds **exactly the same 56 names**. The registry and the
  grants do not disagree, which is what makes the registry the right place to make
  the change: edit the row and the grant together.
* **24** of the 56 are named by some Contract's `reads=` tuple.
* **32** are reached by no tool at all.

The ticket's twenty-eight and twenty-one come from reading the migration files,
and the file view cannot see the whole surface -- `tools/check_wiring.py` says so
itself, raising a `W4` row because "the read surface is catalogue-seeded and no
standing check asks whether" it matches. Twenty-one relations are granted by
statements a file reader does not resolve: `applications`, `artifacts`, `domains`,
`endpoints`, `finding_evidence`, `finding_hypotheses`, `hosts`,
`hypothesis_evidence`, `hypothesis_near_matches`, `identities`,
`interception_cas`, `parameters`, `receipts`, `services`, `task_slate`, `tasks`,
`technologies`, `test_runs`, `tests`, `transport_makeability`,
`vulnerability_classes`. Sixteen of those are read by a Contract, which is why
the unread count barely moves; five are not, and they join the list below.

**The thirty-two, in full:** `artifact_refs`, `browser_runs`,
`browser_step_results`, `browser_steps`, `entity_provenance`, `events`,
`finding_chain_step_citations`, `finding_chain_steps`, `finding_effects`,
`finding_hypotheses`, `hypothesis_near_matches`, `interception_cas`,
`negative_knowledge`, `negative_knowledge_retests`, `program_known_issues`,
`program_required_headers`, `redaction_rules`, `relationships`, `report_blocks`,
`report_effects`, `report_mechanisms`, `report_renderings`,
`report_template_blocks`, `report_templates`, `surface_facts`,
`test_run_receipts`, `tool_run_artifacts`, `tool_run_inputs`, `tool_run_paths`,
`tool_runs`, `transport_makeability`, `vulnerability_classes`.

### Why the default is removal rather than a read

Because the alternative has been tried and is what produced this list. Every one
of these grants was added by somebody who could imagine a read; none of them was
added with one. `roster.py:800-805` is the repo's own standard for exactly this
shape, and a grant is the strongest form of the claim: it says the model is
*allowed* to know something, and a model that is allowed to know something the
tooling cannot fetch is a model whose surface description is fiction. Removal is
also cheap to reverse -- one `state_read_surface` row and one column grant -- and
non-removal is not, because the next audit re-reports the same list.

### The three buckets

**A read is being built; the grant stays (10).** Each of these has a named
consumer already in the tree.

* `browser_runs`, `browser_step_results`, `browser_steps`, `tool_runs`,
  `tool_run_artifacts`, `tool_run_inputs`, `tool_run_paths` -- **ticket 107**.
  These are what the model's own earlier work produced, and the only reason they
  are unreadable is that the packet is a pre-launch snapshot. 107 decided the
  refresh path; these seven are its read. If 107's refresh is scoped to labels,
  these grants are what it serves from.
* `negative_knowledge`, `negative_knowledge_retests` -- the highest-value pair on
  the list and now the most clearly owed: **ticket 114 is `resolved`**, so the
  writer and the operator-side reader exist and the rows will arrive. A hunter
  that cannot read what has already been refuted repeats it, which is the one
  thing the whole refutation design exists to prevent. The model's read is this
  ticket's to open.
* `relationships` -- decided against the contradiction the ticket names rather
  than in the abstract. `mcp__rk2__submit_mission_result` accepts a
  `relationships` element list (`src/redkraken/roster.py:686`) and no read verb
  returns one, which `tools/check_wiring.py`'s own W5 prose calls "a write-only
  vocabulary: an agent may propose relationships it can never read back". Two
  repairs are available and the read is the right one: the graph edge is the
  Entity graph's structure, `get_attack_surface` already declares nine relations
  including `entities` and `domains` (`roster.py:604-605`), and a proposal
  vocabulary is not narrowed by removing the ability to see its result.

**The grant follows another ticket's answer, not this one's (8).** Named so the
implementer does not decide them here and so the next audit does not re-report
them as undeclared.

* `interception_cas` -- ticket 124. Its read-surface criterion is decided there,
  and the answer is that nine of the ten columns simply stop being NULL.
* `hypothesis_near_matches` -- ticket 127, which retires the two similarity-based
  actions and keeps `key_collision`. Whether the model reads its own near-match
  trace is a question about a table whose shape 127 changes first.
* `program_known_issues`, `redaction_rules` -- ticket 125, which gives the first a
  configuration writer and retires the second's verifier design.
* `surface_facts`, `vulnerability_classes`, `transport_makeability` -- **ticket
  110**, which is `ready-for-agent` and serves the closed vocabularies through
  `mcp_enum`, `mcp_enum_described` and `mcp_transport_makeability` at schema-build
  time. If a function serves the vocabulary, the table grant is the second copy
  and goes; that is 110's call and not this one's.
* `test_run_receipts` -- the replay lane's read-surface half, and the ticket's own
  note says this decision decides that question. The lane is reached from
  `cli.py` and `validation.py` and never from a tool; unless the model is given a
  replay-reading verb, the grant goes with the rest of the operator-only set.

**Everything else defaults to removal, and each keeper is argued in the ticket
that keeps it (14).** `artifact_refs` is the one exception already recorded and it
stands: it is reached indirectly through `v_artifacts`, so it is not a defect and
it is not a grant to remove. For the remaining thirteen -- `entity_provenance`,
`events`, `finding_chain_step_citations`, `finding_chain_steps`,
`finding_effects`, `finding_hypotheses`, `program_required_headers`,
`report_blocks`, `report_effects`, `report_mechanisms`, `report_renderings`,
`report_template_blocks`, `report_templates` -- the burden is on the read. Nine of
the thirteen are the reporting and chain-rendering family, and the corpus already
says whose path that is: `rk finding report` is "reserved for a human actor"
(`src/redkraken/cli.py:1327-1339`), `rk report finding` and `rk report chain` are
operator verbs (`cli.py:1497`, `:1517`), and ticket 103 decided that the model's
side of that work is three served Contracts whose answers come back through the
verb rather than through a table read. A Contract that returns a rendering does
not need the model to be able to SELECT `report_template_blocks`.

### The mechanism, where the answer is a read

Unchanged from the ticket's last criterion and worth restating because it is what
makes "argue each read that stays" checkable: a `state.read` Contract with the
relation in its `reads=` tuple, a section in `packet.SECTIONS`
(`src/redkraken/packet.py:43`) and a `_records`-style compile step. Anything kept
without all three is kept on an intention.

## What was measured

A database provisioned from this checkout with all 153 migrations applied, then
dropped. `information_schema.table_privileges` for grantee `rk2_state`,
`privilege_type = 'SELECT'`: **zero rows**.
`information_schema.column_privileges` for the same: **56 distinct relations**.
`SELECT DISTINCT table_name FROM state_read_surface`: **the same 56, exactly**.
Union of every `reads=` tuple in `roster.CONTRACTS`: 25 relations, 24 of them on
the surface. Difference: **32 relations granted and unread**.

## Correction: twenty-eight and twenty-one are both low

The ticket's first criterion says "The surface holds twenty-eight live relations
after `20260922T000000Z...:34-36` removed `playbooks` and `playbook_selections`;
seven are named by a Contract's `reads=` tuple ... twenty-one are reached by no
tool." Measured against a live database at this checkout it is **56, 24 and 32**.
The seven the ticket lists as read are right as far as they go and there are now
eight in the file-visible half -- `observations` joined them -- but the file view
is missing twenty-one relations outright, so the bucket exercise has to be driven
from the database or from `state_read_surface`, not from a grep of the migrations.

## Correction: `callback_interactions` is not a missing grant

One Contract declares a read of a relation that is **not** on the surface:
`mcp__rk2__get_evidence` lists `callback_interactions` in its `reads=` tuple
(`src/redkraken/roster.py:641-656`). That is deliberate on both sides and must not
be "fixed" by adding a grant. `20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:786-792`
is explicit: "`rk2_state` is the connection the model reads through and holds
nothing here at all -- not the verbs, and not the tables, which is what keeps live
correlators and the names they arrived at off the agent surface. **Nothing is
added to `state_read_surface`, so the absence is the grant.**" What the model gets
is a label and nothing else, through `callback_interaction_label(...)` projected
into `v_evidence` (`20260928T030000Z__an_arrival_has_a_name_the_agent_can_cite.sql:71`,
`:102`). The `reads=` entry records provenance, not privilege -- and it is the one
place in the roster where those two differ, which is worth a sentence in whatever
check compares them.
