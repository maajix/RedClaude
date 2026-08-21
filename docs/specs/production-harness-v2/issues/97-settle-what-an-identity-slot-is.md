# 97 — Settle what an Identity slot is

**What to build:** The written answer to a question 29 of the 50 Playbooks have
been answering wrongly since they shipped, the rewrite of what those 29 say
instead, and the fix to the field that is broken in the other direction.

**Blocked by:** nothing. It is a decision and a corpus edit, and both are
reachable from what is already in the tree.

**Status:** ready-for-agent

- [ ] The decision is recorded where a reader of the contract finds it:
      **`identity_slot` is a property of the Tool run, never an argument, and
      `mcp__rk2__http_request` continues to refuse it.** The contract's own
      comment already gives the reason (`roster.py:758-765`) and this ticket
      promotes it from a comment about something withheld to a settled rule --
      neither `body` nor `identity_slot` is in `FORBIDDEN_ARGUMENTS`
      (`roster.py:274`), so nothing structural stops a later ticket declaring
      one, and only a written decision does.
- [ ] The decision names the four layers that already treat it as a run
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
- [ ] The 29 Playbooks say the executable thing instead. They currently write
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
- [ ] `skills/use-identity/SKILL.md` stops instructing a call the gate refuses
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
- [ ] The naming hazard the area exposes is written down where it would be read.
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
