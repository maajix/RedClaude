# 83 — Open the first Task of a Program

**What to build:** A supported way for a freshly opened Program to acquire its first Task, so that `rk run` has something to rank, offer and claim.

**Blocked by:** nothing.

**Status:** resolved

- [x] A Program with a compiled scope and no history reaches a claimed Task through the shipped surface, without a hand-written `INSERT`.
- [x] Whatever opens it is narrow: a Task kind and a subject the scope already admits, not an arbitrary row. Ticket 59's fourth criterion -- no generic SQL and no raw insert on model-facing operations -- holds for this too.
- [x] The Event record says who opened it and why, so a campaign's first Task is as attributable as every Task derived from one.
- [x] A test opens a Program from a configuration, runs a pass, and fails if the slate is still empty.

## Why

Found during authorised live validation on 2026-08-16, immediately after the
Agent boundary was made to work (ticket 82).

With the boundary configured, `rk run` against a real Program gets all the way
to the scheduler and stops there:

```
{"name": "slate", "ok": true,
 "detail": "no Task is ready; nothing was claimed"}
```

`execution.Slice._pass` is right to stop: an empty slate ends the pass before
the orchestrator session is opened, so no child runs and nothing is spent.

The question is where the first Task comes from, and the answer today is
nowhere. Every production `INSERT INTO tasks` is downstream of state a fresh
Program does not have:

- `20260815T180000Z__a_blind_validator_answers_from_the_packet.sql:956` needs a
  Finding.
- `20260819T000000Z__a_chain_unlock_earns_its_place_in_the_queue.sql:374` needs
  a Hypothesis.
- `20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1266` needs
  both.

`promote_proposal` does not open Tasks either -- it promotes Observations,
Surface and Hypotheses -- so an Agent cannot propose its own next Task into
existence, and there is no Agent running to propose anything while the slate is
empty.

The suite has never noticed because it opens Tasks directly:
`tests/test_database.py:858` and `:1851` write the row themselves. That is
correct for a database test and it is exactly what an operator has no verb for.

## Notes

The narrow shape this expects is a `recon` Task against a subject the Program's
own scope admits, because that is the one kind whose input is the configuration
and nothing else. `MISSIONS["recon"]` in `execution.py` already has the sentence
such a child would be told: "Map what this target exposes."

## What was built

`20260831T000000Z__a_program_opens_the_first_task_of_its_own_scope.sql`, three
functions, one helper and one standing check.

The thing that had to be built first is the Surface. A freshly opened Program
had no addressable Entity at all: `_project_identities` writes the Identity,
`_project_scope` writes the scope tables, and `add_entity` has no production
caller -- so "a subject the scope admits" named nothing that existed, and the
Task this ticket asks for had nowhere to point. `record_configured_subjects`
projects the live scope version's exact `target` rules, and does it in SQL
because the thing it reads is the compiled policy rather than the document: a
copy of the same reading in `program.py` would be free to disagree with the one
`scope_class_of_entity` will judge the result by.

What it records is Applications, and that is the load-bearing decision. An
inclusion is an address -- a protocol, a host, a port and a path prefix -- and
an Application is the one kind of subject a Task can be dispatched against:
`execution` resolves a target URL from `applications.base_url` or from an
Endpoint's template under one, and refuses a subject that is neither for
carrying no address to send a request to. A `host` Entity would have satisfied
"a subject the scope admits" and produced a Task no child could ever be sent
on.

It is spelled the way the promotion path spells one and keyed the way it keys
one. `rk2_base_url` is the canonical spelling -- the scheme's own port and a
root path left off -- and the key is `rk2_dedup_key('application',
ARRAY[base_url])`, which is exactly what `promote_proposal`'s application arm
writes. Agreeing with that arm means agreeing on all four parts, and two of them
are not the scope columns as stored: the path goes through `rk2_clean_path`,
because `rk2_parse_base_url` cleans before it returns while `scope.path_variants`
keeps the slash the operator wrote, so `/api/` verbatim would key the configured
Application on `.../api/` against a proposal of `.../api`; and an IPv6 host is
bracketed, because `scope.normalize_host` unbrackets one before storing it and
an unbracketed one in a URL is an authority with three colons that
`rk2_parse_base_url` refuses by name. A path with no canonical spelling gets no
URL and is skipped on the same ground as a wildcard. The scope columns keep the
rule's own prefix rather than the cleaned one, because they answer a different
question and `scope_path_under` reads a prefix as a subtree.
`FirstTaskTest::test_the_url_it_recorded_is_the_one_a_proposal_of_it_would_key_on`
holds the agreement as a fixed point over `rk2_parse_base_url`. So the recon
Agent this opens a Task for converges on the row it was sent to map instead of
standing up a second Application for the same address. A
rule naming two protocols compiles to two rows and is therefore two
Applications, which is what listing both asked for; `applications.kind` is left
NULL, because web, api, spa, graphql or websocket is a judgement about what
answered and nothing has asked yet.

Wildcards are not projected, and neither is CIDR. `*.example.com` names a set
of hosts and no address, and nothing in this build enumerates one, so a subject
recorded for it would be a subject with no verb. A Program whose scope is only
wildcards therefore opens nothing and says so in the count it reports, which is
a readable answer rather than a Task that fails after a child has been paid
for.

`open_task(program, kind, subject, reason)` is the narrow verb. It takes a kind
and an Entity, never a row: the subject has to be this Program's, has to be
`target` rather than merely in scope -- an `egress_support` Entity is the
harness's own callback listener and not somewhere to send a recon Agent -- and
has to carry no live Task of that kind already. The reason is not optional,
because the whole of criterion 3 is that a Task opened from a configuration is
as attributable as one derived from a Finding. Readiness is asked after the
insert rather than before it, since `ready_for` takes a `tasks` row and one
built by hand here would be a second copy of the row shape.

Criterion 3 is met with no new reading-side machinery. `open_task` writes a
`task.opened` occurrence and sets `app.caused_by_event_id` to it before the
insert, so the `task.created` event the existing trigger emits names the reason
as its cause -- and puts the caller's own cause back afterwards, so a caller
already writing under one does not have it dropped by the first Task it opens.
The actor is read from the session and never defaulted: an actor this function
supplied would be the answer to "who opened it" invented by the thing being
asked, which is why an unset `app.actor_kind` is a refusal here exactly as it
is in `refresh_scope_projection`. `check_opened_tasks` holds the other
direction: a `task.opened` event no `task.created` event cites is a reason
nobody can find.

That narrows ADR 0002, and the migration says so in its header rather than doing
it quietly. The ADR has causal context arriving through `SET LOCAL` session
settings the connection helper sets before any write, and until this file
`app.caused_by_event_id` was read in SQL and written only out in Python. What
the ADR protects is attribution -- "the single place an actor can be
misattributed" -- and the actor is untouched: `open_task` reads `app.actor_kind`
from the session and refuses outright when it is unset. What it sets is the
cause, to an event it wrote itself one statement earlier, and it puts the
caller's own back before returning. The alternative was for `program.py` to
write the `task.opened` event and set the cause around a `tasks` insert of its
own, which would move a row insert out of the one verb and back to a call site
-- the thing the ADR exists to stop. Worth reopening if a second function ever
needs this.

`open_configured_recon` is the seeding, and `program._open_program` is where it
is called from -- when the configuration is read, not every scheduler pass. A
pass that re-seeded would be the runtime re-deciding the Surface on a timer.
It is idempotent and so is calling it: a resume against an unchanged
configuration records no subject and opens no Task, and `rk run` reports both
counts as `first_tasks` in its facts.

`tests/test_database.py::FirstTaskTest` is one campaign carried from a file to
a claim in the order an operator meets it, with a second Program opened beside
it and left alone as the control for the Program predicate, and a third whose
inclusion is a wildcard as the control for an address that is not one. The pass
calls `execution.Slice._reconcile`, `._offer` and `._claim` on a real `Slice`
over a described boundary -- the shipped methods, not statements of its own --
so what it proves is that the code that answered "no Task is ready; nothing was
claimed" now reaches a claim, and that it reached it with an empty violation
ledger. It stops at the claim: `attempt` needs a door, and the child that would
run is ticket 82's ground rather than this one's. Five refusals are held: no
reason, no actor, another Program's subject, an Entity the scope does not admit,
and a second live Task of a kind the subject already carries.
