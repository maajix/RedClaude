# 131 — An egress run is opened under no Identity at all

**What to build:** The decision about which of a Hypothesis's two leased
Identities an egress Tool run is opened under, and the writer that puts it in
`tool_runs.args` instead of the empty string that is there now.

**Blocked by:** nothing. Ticket 97 settled that the slot is a property of the
run rather than an argument, which is what makes this a question about the
scheduler and not about the tool surface.

**Status:** resolved

- [x] The decision is taken and written into this ticket before the code is.
      A Task's Hypothesis is paired against **two** Identities, not one:
      `claim_task` leases
      `unnest(ARRAY[h.identity_a_entity_id, h.identity_b_entity_id])`
      (`0023_scheduler_ranking.sql:962-968`), while `tool_runs.args` carries one
      `identity_slot`. So "the slot the Hypothesis was paired against" names two
      things and a run can spend one, and which one is not derivable from
      anything in the tree today. The three shapes available are: the run is
      opened under `identity_a` and the differential is two Tasks (which is what
      ticket 97 rewrote 29 Playbooks to say); the Task carries the choice, which
      means a column and a writer for it; or the Tool run carries both and the
      door picks, which is the one shape ticket 97's measurement rules out --
      `gate_tool_call` grades an empty slot `constrained` and a filled one
      `approval_required`, two different classes and two different digests, so a
      slot chosen after the human answered would spend a real account outside
      the answer that was given.
- [x] The hardcoded empty string is gone. `execution._authorize` opens every
      egress Tool run with `"identity_slot": ""` (`execution.py:2119`, inside the
      `json.dumps` at `:2115-2122`, in `_authorize` at `:2077`), so today **no
      agent-issued request can carry an Identity at all**, however many
      Playbooks ask for one. The capability exists end to end -- provisioning,
      injection at the door, response redaction -- and nothing ever names a
      slot, which is why the whole of it has never been exercised by an agent.
- [x] The two-Identity case has a test that fails before the fix. A Hypothesis
      with `identity_a_entity_id` and `identity_b_entity_id` both set, a Task
      claimed against it, and an egress run opened: today the run's args carry
      an empty slot and the assertion is that they carry the decided one.
- [x] `check_wiring` W2 is re-measured afterwards. `identity_slot` is a
      declared column that the runtime writes and no contract declares, and this
      ticket is what makes the write real; if the gate has an `owed` row for it
      by then, the row goes.

## The decision

**The Task carries the choice, and the differential is two Tasks.** Both of the
first two shapes, because they answer different halves of the question and
neither is sufficient alone: a column says which Identity *this* run spends, and
two Tasks are how the difference between two Identities is ever measured. The
third shape -- the Tool run carries both and the door picks -- stays refused for
the reason this ticket already measured: the digest a human answers is taken
from the row, so a slot chosen afterwards spends an account outside the answer
that was given.

Written as `tasks.selected_identity_entity_id`, `NOT NULL`, referencing
`(entity_id, program_id)` so 0017's rule 3 makes cross-Program selection
unrepresentable rather than merely wrong.

**Anonymous is chosen, not left blank.** A `BEFORE INSERT` trigger defaults the
column to the Program's anonymous Identity, minting it if this is the first Task
to need one. Inheriting `identity_a` instead was considered and refused: a Task
holds a Lease on what it selects, and a named slot with no live Lease is refused
outright by `resolve_egress_identity` -- so inheritance would turn every derived
hunt into a run that cannot open its own door. The conservative default is the
run this system already knows how to make.

**`_anonymous` is a row, and the empty string is what the door is told.** The
selection is always a real Identity row, which is what `task_identities`, the
clamp and the Lease need. What reaches `tool_runs.args` is the slot name only
when the Identity carries credential material -- `identities.class <>
'anonymous'` -- and the empty string otherwise. Writing `_anonymous` on the wire
would name a slot the door would look for a Lease on and would grade every
unauthenticated hunt `approval_required` through `net_borrowed_identity`, which
escalates any non-empty slot as a borrowed account.

**The differential became derivable.** Two things made "two Tasks over one
Hypothesis" impossible before this ticket, and both moved:
`rk2_hypothesis_hunt_frontier` returned one row per claim and now returns one
per (claim, Identity); and `tasks_live_dedup_idx` did not include the Identity,
so the second half collided with the first as a duplicate.

**What did not move.** The two halves still take their turns rather than running
side by side: they are two runs against one subject, and 20260916T000000Z's
subject hold is what serialises them. That refusal is now `subject_held` where
it used to be `identity_held`, which is the whole of the change in one word --
the Identity is no longer what stands between a claim and its second reading.

**W2 needed nothing.** The register carries no `owed` row for `identity_slot`:
ticket 97 removed the twenty W10 rows that owed it, and no W2 row replaced them.

## Why

Ticket 97 settled what an Identity slot **is**: a property of the Tool run, set
by the runtime, never an argument a model may name. That settlement is written
into `roster.py`, into two `COMMENT ON FUNCTION` statements and into 29
Playbooks, and it is correct. What it does not do -- and said so, in its own
fifth criterion -- is make the runtime actually set one.

So the state of the tree after 97 is that the rule is right and the value is
empty. `resolve_egress_identity` takes a capability and resolves whatever the
run was opened under; the run is always opened under nothing; and the
identity-differential reading that eleven Playbooks are written around cannot be
taken by any agent, because both halves of the differential go out as the same
anonymous caller.

Ticket 112 names ticket 97 as the owner of "how a run says which one it spent"
and hands it back. Ticket 97 measured the problem, found the criterion
under-specified, and handed it here rather than guessing. This is the ticket.

## What is already known

- The gate's two answers, measured on a live database:
  empty slot grades `constrained` / `tool_risk_classes:mcp__rk2__*` /
  `policy_unclear`; slot `member-a` grades `approval_required` /
  `call_risk_rules:net_borrowed_identity` / `credential_needed`. Two classes,
  two digests. Whatever writes the slot has to write it before the digest is
  taken.
- `rk2_proxy` holds no privilege of any kind on `tool_runs`. The door cannot
  write the slot, which is why this is the runtime's decision and not the
  door's.
- `receipts.tool_run_id` carries a plain foreign key and no unique index, so one
  run has many Receipts. A per-call slot would have nowhere to be recorded.
