# 29 — Deliver pending decisions, Halt and resume verbs

**What to build:** Let autonomous work park a typed operator question, continue unrelated Tasks and later resume only through explicit operator decisions and Program controls.

**Blocked by:** 13 — Enforce Halt and aggregate request budget at egress; 27 — Let the orchestrator choose and dispatch a role.

**Status:** resolved

- [x] Risk, scope ambiguity, third-party impact, credential need and policy uncertainty use stable question codes and Program-scoped rows.
- [x] Parking closes the current Agent and Tool runs, releases resources and leaves the Task in a distinct non-terminal state.
- [x] Other eligible Tasks may continue without waiting for the operator.
- [x] Only operator verbs can answer, reject or supersede a pending decision and clear Program Halt.
- [x] An answer is revalidated against current configuration before the Task becomes ready again.
- [x] Free-text operator context is write-only to the decision record and cannot enter validator or unrelated Agent context automatically.

## Comments

Implemented on 2026-08-14 in one migration --
`20260814T020000Z__the_operator_answers_and_the_work_resumes.sql` -- and one new
Python module, `operator.py`, reached by five new CLI verbs.

Ticket 11 built the door: a gate verdict of `ask` files a question, ends the run
and parks the Task. Ticket 13 built the Halt. What neither built is the other
side of the same transaction -- what an operator may do with the question once it
is filed, and what has to be true again before the work it parked is allowed to
move.

### The question codes are rows, and both writers point at them

The five codes were two independent CHECK lists, one on `pending_decisions` and
one on `call_risk_rules`. A code added to a rule and not to the decision is a
gate that files a question the table refuses to hold, and the migration that
adds the sixth word to one list is the migration that breaks the other.
`decision_question_codes` is now the one list, Program-global for the same reason
`call_risk_rules` is -- a per-program copy of the vocabulary would let one
Program mean something different by `credential_needed` than the rule filing it
does -- with a foreign key from each writer.

`assess_call_risk` names one code no rule carries: the static floor's own
`policy_unclear`, written in the function body where no foreign key reaches. The
migration asserts that literal against the registry, so a rename cannot leave the
floor filing a question the table now refuses and find out at the first `ask` in
production.

### Parking releases everything the run was holding

Two of the three parts were already right. The hand-rolled `UPDATE
identity_leases` is gone for ticket 24's `release_leases`, which moves both
halves of the Lease on one reading of the clock rather than leaving the Task's
`lease_expires_at` to a second statement below it. And a run's sibling Tool runs
are now closed with it: a run may have more than one open -- a background
exchange, a second call in flight -- and closing the Agent run without them left
a `running` receipt whose capability still resolved, attributed to a run that had
ended. They are abandoned with a `hook_error` saying whether the tool ran is
unknown, because from here that is not knowable.

The Task lands `parked` with its claim and priority dropped and its attempt count
untouched. Parking is not a failed attempt: nothing about the work was tried and
found wanting, and counting it would retire a Task after three questions.

### Nothing had to change for the third criterion

A parked Task is not `pending`, so `claimable_for` already refuses it and offers
its Program's others -- and it says so in the reason it returns, `not_pending`.
This file asserts that rather than implementing it: a test claims a Program's
other Task while one sits parked, and a second asserts the parked one is refused
by name. An implementation here would have been a second answer to a question the
scheduler already answers.

### Three verbs, and no fourth path

`answer_decision` was EXECUTE-able by `rk2_runtime`. The write was refused --
`assert_actor_kind_authentic` will not let a non-operator session claim
`actor_kind = 'human'` -- but a control verb whose only guard is a trigger three
tables away is a guard nobody reads. EXECUTE now goes to `rk2_human` alone, and
the verbs open with an explicit refusal naming the role.

The third verb is new. An operator holding a question they can neither approve
(the scope changed under it) nor honestly deny (the work is fine, the question is
stale) previously had one move left: wait for the deadline and let it be recorded
as a timeout against a person who did in fact read it. `supersede_decision`
withdraws the question and puts the Task back where the gate found it, with no
grant behind it, so what resolves it next is a fresh gate verdict under the
configuration in force then.

`resume_program` -- ticket 24's recovery verb, which unclaims Tasks, aborts runs
and releases Leases -- was reachable by every role including the two a model can
influence. It stays the runtime's: its first statement declares the runtime as
the actor, so an operator calling it would file every row it writes under a name
that decided nothing. The operator's half of resuming is clearing the Halt.

### An approval is revalidated; a denial needs nothing to still be true

`revalidate_decision` returns the first reason an answer no longer describes the
request the runtime would make now: the Program closed or Halted, the Task no
longer parked, the request reclassified, the rule now `forbidden`, or the policy
changed under it. It is read-only and reason-returning rather than raising, so
the console can show an operator why a question can no longer be approved before
they try. `answer_decision` asks it on approvals only, and refuses with a HINT
naming the two moves left -- deny it, or supersede it and let the runtime ask
again under the configuration that holds now.

Reclassification is asked by digest: `current_request_digest` is the
canonicalisation `gate_tool_call` builds inline, extracted so that revalidating
an answer asks the same question about the same request rather than a second
opinion about what a request is.

### The operator's words stay the operator's

`pending_decisions.answer` is free text a person wrote for one question, and it
had two ways into a model's context. The column grant is the first: the
table-level SELECT goes and every column except the answer comes back, generated
from `pg_attribute` rather than listed, because a copy of the column list here
would be one migration away from being wrong. `xmin` is granted by name --
`check_event_log_integrity` reads it on every table in `event_table_config`, and
a system column rides on a table grant or on a grant naming it, not on a grant of
every user column. Without that line the revoke does not hide the answer from the
integrity gate, it blinds the gate.

The `decision.answered` payload is the second, and it now carries the verdict,
the code and who answered -- never the sentence. `find_in_database` skips a
column its caller may not read rather than raising on it, which is what lets a
scan run at all now that one column is the operator's alone; it is deliberately
not SECURITY DEFINER, because the runtime holds EXECUTE on it and a definer scan
would answer "is the operator's answer the string I guessed" one guess at a time.
Three standing-check arms hold the shape: the column is unreadable by the
runtime, no view hands it to a non-operator role, and no event payload contains
it.

### The console

`rk decision list|answer|supersede`, `rk halt` and `rk resume`, all reading
`RK_HUMAN_URL`. Separate from `decisions.py` for the reason the two roles exist:
the sweep runs as `rk2_runtime` and may not read a word an operator wrote, this
runs as `rk2_human` and is the only connection that may. Nothing in the module
decides anything -- it names the Program, calls the verb and reports what came
back, appending the database's own HINT to a refusal so an operator holding a
Task that will not move is holding the sentence that says why.
