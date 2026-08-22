# 97 — Settle what an Identity slot is

**What to build:** The written answer to a question 29 of the 50 Playbooks have
been answering wrongly since they shipped, the rewrite of what those 29 say
instead, and the fix to the field that is broken in the other direction.

**Blocked by:** nothing. It is a decision and a corpus edit, and both are
reachable from what is already in the tree.

**Status:** resolved

- [x] The decision is recorded where a reader of the contract finds it:
      **`identity_slot` is a property of the Tool run, never an argument, and
      `mcp__rk2__http_request` continues to refuse it.** The contract's own
      comment already gives the reason (`roster.py:758-765`) and this ticket
      promotes it from a comment about something withheld to a settled rule --
      neither `body` nor `identity_slot` is in `FORBIDDEN_ARGUMENTS`
      (`roster.py:274`), so nothing structural stops a later ticket declaring
      one, and only a written decision does.
- [x] The decision names the four layers that already treat it as a run
      property, because the argument for it is that four of them would have to
      be rewritten: `resolve_egress_identity` reads it out of the Tool run's own
      row and then requires a live, unreleased, unexpired lease held by this
      agent run (`20260811T150000Z__encrypted_identity_slots.sql:437-453`); the
      proxy takes the Identity from the capability resolution and never from the
      request (`proxy.py:948-952`, `proxy.py:1174-1181`); a receipt trigger
      re-checks the same key a third time (`20260811T150000Z:764-780`); and the
      lease is granted to the agent run when the Task is claimed, on the same
      clock as the task lease (`0023_scheduler_ranking.sql:958-968`). Above all
      of them, `net_borrowed_identity` escalates any non-empty slot to
      `approval_required` with the question code `credential_needed`
      (`0026_human_control.sql:266-268`), assessed against a digest built at
      open -- so an argument named at call time is a model moving outside an
      answer a human already gave.
- [x] The 29 Playbooks say the executable thing instead. They currently write
      sentences like "Send the call as label A through `mcp__rk2__http_request`,
      with `identity_slot` set" (`playbooks/grpc/playbook.md:50`; the same
      instruction at `playbooks/graphql/playbook.md:42-43` and 27 others -- 29
      of the 50 `playbook.md` files name the field). Each becomes the form the
      research settles on: this reading runs as whichever Identity the Task was
      opened under, the step does not choose it and there is no argument for it,
      a reading that needs two Identities is two Tasks, and the differential is
      made by comparing their Receipts. `identity-lifecycle/playbook.md:41`,
      "Send the same read with no `identity_slot` at all", becomes "the
      unauthenticated half of the differential is a Task opened with no
      Identity".
- [x] `skills/use-identity/SKILL.md` stops instructing a call the gate refuses
      before the handler. Line 24 says "Call `mcp__rk2__http_request` with
      `identity_slot` set to the chosen label" and line 29 gives a JSON example
      using it; the schema is served closed (`roster.py:412-421`) and the gate
      re-checks the same statement afterwards (`roster.py:1393-1395`), so every
      call written to that instruction is denied by name.
- [ ] The defect in the other direction is fixed or is carried by a named
      ticket. The runtime opens every egress Tool run with the slot hardcoded
      empty -- `"identity_slot": ""` at `execution.py:1940`, inside the
      `json.dumps` at `execution.py:1936-1942` -- so today no agent-issued
      request can carry an Identity at all, however many Playbooks ask for one.
      The capability exists end to end, provisioning through injection through
      response redaction, and nothing ever names a slot. Fixing it means
      teaching `_authorize` to write the slot the Task's hypothesis was paired
      against; it does not mean adding an argument.

      **Not done, and not carried by any ticket that exists.** The fix is in
      `execution._authorize`, which this work was not given, and no open ticket
      owns it: 112 names 97 as the owner of "how a run says which one it spent"
      and hands it back, and nothing else in the tracker mentions the hardcoded
      slot. It also cannot be written as this criterion words it. A Task's
      Hypothesis is paired against *two* Identities, not one -- `claim_task`
      leases `unnest(ARRAY[h.identity_a_entity_id, h.identity_b_entity_id])`
      (`0023_scheduler_ranking.sql:962-968`) -- while `tool_runs.args` holds one
      slot, so "the slot the hypothesis was paired against" names two things and
      the run can spend one. Which of the two a Tool run is opened under is the
      undecided part, and it is a decision about the scheduler, not about this
      contract. A ticket for it needs writing.
- [x] The naming hazard the area exposes is written down where it would be read.
      The served tool is `mcp__rk2__http_request` (`roster.py:738`) and the Tool
      run is opened under `proxy.TOOL`, which is `mcp__rk2__net_request`
      (`proxy.py:332`, `execution.py:1935`). Every per-call risk rule is written
      against the second name (`0026_human_control.sql:266-268`), and a future
      ticket that opened a Tool run per agent call under the served name would
      silently stop those rules firing.

## Why

Capability C in
`docs/research/playbook-state-of-the-art/09-capability-matrix.md` -- 9 of the
131 techniques by the count, and its real weight elsewhere: it is why 29
Playbooks are prose. The settlement itself is from
`docs/research/harness-capabilities/11-request-primitive-design.md`, section
"The identity question", which states the conclusion in one line -- "Settled:
`identity_slot` is a property of the Tool run, not an argument, and the contract
should continue to refuse it" -- and gives the sentence the 29 Playbooks should
carry in its place.

`00-todo-and-harness-gaps.md` records the same defect from the other end: the
corpus tells the agent to set a field that does not exist, the capability behind
it does exist, and the two have never been introduced. The matrix adds the part
that makes it worse than a documentation bug -- `identity_slot` was searched for
in `src/redkraken/packet.py` and not found, so a child is not told which
Identity it is running as either, and can only learn the label afterwards from
`identity_label` on its own Receipt projection.

## What the measurement says

The ticket states the settlement as a conclusion and cites the research note
that reached it. It was re-derived here against a live database built from this
tree (`rk2_scratch_97m`, the full migration corpus applied clean), because a
decision that 29 Playbooks are rewritten on should rest on what the harness
does and not on what a note says it does. Five readings, none of which depends
on the others:

**1. The surface already refuses it, by the ordinary path.**
`roster.CONTRACTS["mcp__rk2__http_request"].arguments` is
`['body', 'headers', 'method', 'url']` and `.schema()` carries
`"additionalProperties": false`. A `Gate.decide` on a call adding
`identity_slot="member-a"` returns
`R-ARGVALUE: mcp__rk2__http_request takes no argument named 'identity_slot'`.
No contract on the surface declares the field:
`any("identity_slot" in c.arguments for c in roster.CONTRACTS.values())` is
`False`. And `"identity_slot" in roster.FORBIDDEN_ARGUMENTS` is `False`, which
is the ticket's point exactly -- the refusal today is "undeclared", not
"forbidden", so the only thing standing between a later ticket and declaring it
is a written decision. This one.

**2. The door has no parameter that could receive it.**
`pg_get_function_arguments` says `resolve_egress_identity(p_capability text)`
and `authorize_identity_egress_request(p_capability text, p_method text,
p_protocol text, p_host text, p_port integer, p_path_raw text, p_path_norm
text, p_has_body boolean DEFAULT false)`. Neither takes an identity. An
argument arriving at call time would have to be carried to a function with
nowhere to put it.

**3. And it could not be recorded on arrival either.**
`information_schema.role_table_grants` for `tool_runs` lists `rk2_owner` and
`rk2_runtime` and no one else; `rk2_proxy` holds no privilege of any kind on
that table. The party that would receive a call-time slot cannot write one
down, so a slot named at call time would be an unrecorded fact -- the shape of
thing this harness exists to not have.

**4. The class and the approval key are both taken before the call.**
`gate_tool_call(p_tool_run_id uuid)` and `current_request_digest(p_tool_run_id
uuid)` each take a Tool run id and nothing else, and the digest is
`canonical_request(tr.tool, coalesce(tr.args, '{}'::jsonb), nonce)` over the
row. The same request assessed both ways:

| `identity_slot` | risk class | rule | question | `equivalence_key` |
| --- | --- | --- | --- | --- |
| `""` | `constrained` | `tool_risk_classes:mcp__rk2__*` | `policy_unclear` | `81a1c796481651d9...` |
| `"member-a"` | `approval_required` | `call_risk_rules:net_borrowed_identity` | `credential_needed` | `3ccf87a4693b3312...` |

Two different classes and two different keys. An approval a human gave against
the first is not an approval for the second, and a slot named after the row was
written moves neither -- so the whole effect of the argument would be a model
spending a real account outside the answer a person gave. That is the layer the
ticket calls decisive, and it measures as decisive.

**5. One Tool run is many exchanges, so a per-call answer has no place to go.**
`receipts.tool_run_id` carries the plain foreign key `receipts_tool_run_id_fkey`
and no unique index mentions the column, so many Receipts hang off one run;
subresources and redirects share one capability by design. The slot is resolved
once per run and spent by every exchange under it. An argument would be
answering per call a question the row answers once.

**Settled, on that evidence: `identity_slot` is a property of the Tool run,
never an argument, and `mcp__rk2__http_request` continues to refuse it.**

## What was built

**The decision, at `src/redkraken/roster.py`.** The `mcp__rk2__http_request`
contract's `body` argument was already followed by a comment saying no identity
is declared and that "the honest form of 'not yet' is not to declare it". That
comment is now the rule and its four reasons, in the order the measurement
found them: the refusal is the ordinary undeclared-argument one and needs
nothing spelled to hold; the door has no parameter and no privilege on
`tool_runs`; the class and the approval key are both taken from the row before
the call, with the two outcomes named; and one run is many exchanges. It is in
the contract because that is where somebody about to declare a fifth argument
is standing.

The naming hazard is a second comment, above the contract key rather than
inside it, because a reader meets the served name there. `mcp__rk2__net_request`
is what `execution._authorize` opens the run under and what all three of
`net_unsafe_method`, `net_host_out_of_scope` and `net_borrowed_identity` are
written against. The comment says what would happen to a ticket that opened a
run per agent call under the served name: nothing visible. The static floor
still covers the served name through the `mcp__rk2__*` glob, so the run keeps a
class and only the escalations go quiet.

**The database's half, at
`migrations/20260928T000000Z__an_identity_is_a_property_of_the_run.sql`.** Two
`COMMENT ON FUNCTION` statements put the settlement on
`resolve_egress_identity` and `authorize_identity_egress_request`, where a
reader of the door meets it. The rest of the file is the measurement, turned
into assertions that run every time the schema is built: no identity parameter
appears on any of the four functions; `rk2_proxy` still holds nothing on
`tool_runs`; the receipt trigger still reads `identity_slot`; the empty and the
named slot still assess to `constrained` and to `approval_required` /
`net_borrowed_identity` / `credential_needed` with different equivalence keys;
`receipts` still has no unique index over `tool_run_id`; and every `net_*` risk
rule still names `mcp__rk2__net_request`. A migration was the only place to put
these, since `tests/test_database.py` is not this work's to edit -- and it is
the better place anyway, because the properties are about the schema and the
schema is what re-applies.

**The corpus, at 29 `playbook.md` files and one `SKILL.md`.** All 37 mentions
of `identity_slot` are gone and the string appears in no Playbook and no Skill.
Each site says the same three things instead: the call goes out as whichever
Identity the Task was opened under, the step does not choose it and there is no
argument for it; a reading that needs two Identities is two Tasks, one opened
under each; and the differential is made by comparing the Receipts the two
Tasks produced. `identity-lifecycle` step 2, which asked for "the same read with
no `identity_slot` at all", now asks for a Task opened with no Identity.
`use-identity` loses the JSON example that set the field, and its step 1 says
the label is read off `identity_label` on the Receipt after the first call
rather than chosen before it -- which is what the packet gap at the bottom of
this ticket leaves as the only way to learn it.

`playbooks.source_sha256`, `playbooks.version`, `skills.source_sha256`,
`skills.version` and the `use-identity` row in `skill_dependencies` are frozen
in migrations, so the corpus edit is only half done until they move.
`20260928T020000Z__the_corpus_is_refrozen_at_the_text_it_now_ships.sql` moves
all of them, and asserts that no Playbook lost standing to the edit and that
the catalogue is still fifty.

**The register, at `tools/check_wiring.py`.** W10 held twenty `owed:97` rows,
one per Playbook or Skill that named `identity_slot` in the same paragraph as a
Contract token. All twenty were measured gone before the rows were removed;
the check now reports no `identity_slot` gap at all.

## Where the ticket was wrong

The reasoning survives all of these; the line numbers do not.

- `roster.py:758-765`, cited for the contract's comment, is the
  `mcp__rk2__request_validation` contract. The comment was at 848-853 and the
  contract key at 795, not the 738 the last criterion gives -- 738 is the
  `title` argument on a Finding contract.
- `roster.py:1393-1395`, cited as the gate's re-check of the closed schema, is
  inside `_forbidden_argument`'s docstring, which is a different refusal (the
  forbidden-name one). The re-check that produces the named denial is
  `_argument_fault`, called from `Gate.decide` at 1260 and defined at 1478.
  `roster.py:412-421` and `roster.py:274` are both correct.
- `proxy.py:948-952` is `CONTAINER_MARKERS` and `proxy.py:1174-1181` is the
  `Fence` docstring. The claim they were cited for is true; its support is the
  capability-resolution SELECT that returns `identity_entity_id,
  identity_label` (`proxy.py:1019-1020`) and the binding built from it
  (`proxy.py:1250-1257`).
- `execution.py:1940` and `1936-1942` are stale by about eighty lines; the
  hardcoded `"identity_slot": ""` is at 2119, inside the `json.dumps` at
  2115-2122, in `_authorize` at 2077. The function name is the stable
  reference and the criterion above now uses it.
- The fifth criterion's prescribed fix is under-specified, not merely
  unimplemented; see the reason recorded on it.
- The closing paragraph of "Why" is correct. `identity_slot` does not appear in
  `src/redkraken/packet.py`, and `identity_label` is on the Receipt projection:
  `v_records` builds it from `entities.label` of the joined Identity Entity.

