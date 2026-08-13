# 27 — Let the orchestrator choose and dispatch a role

**What to build:** Run one orchestrator decision over a bounded Slate, commit the runtime-validated choice and dispatch the correct production role without giving the model queue or egress authority.

**Blocked by:** 24 — Manage Task and Identity Leases through crashes; 25 — Reserve and reconcile campaign budgets; 26 — Rank Tasks by value, cost and unlock.

**Status:** resolved

- [x] The orchestrator receives only compact Slate entries and relevant bounded Program context, not the full Task queue or transcripts.
- [x] It may return one offered Task label or no choice and cannot invoke target, Skill or raw claim tools.
- [x] Runtime fallback and claim revalidation determine the actual claimed Task.
- [x] The claimed Task's kind selects an allowed role from the roster and rejects incompatible role or Skill combinations.
- [x] Agent dispatch uses the Leases and reservations from the committed claim and cannot substitute another Task or Program.
- [x] Malformed, off-Slate and empty model responses all leave a deterministic, safe and auditable outcome.

## Comments

Implemented on 2026-08-13 in one migration --
`20260814T000000Z__the_orchestrator_chooses_and_the_runtime_dispatches.sql` --
and four Python modules: `execution.py` runs the decision, `_launch.py` serves
the two tools it is made of, `agent.py` carries the Slate across the boundary
and `roster.py` publishes the kind-to-role lookup the dispatch checks against.

170000Z built both ends of the Slate and left the middle empty. `offer_slate`
wrote a bounded list, `pick_task` recorded a choice against it and `claim_task`
committed one, and nothing in the corpus ever ran a model over the list -- so
the only caller of the whole apparatus was a runtime taking entry one. ADR 0003
is a three-clause sentence and two of the clauses had no subject.

### The session is an Agent run with no Task

`open_orchestrator_session()` opens it, at the model and effort the roster row
states, and returns the two ceilings the child has no database to read: the
cross-role subagent cap from the active weights and the Program's per-run token
ceiling.

No Task, and that is the whole shape of it. `agent_runs.executes_tasks` is
generated from `task_id IS NOT NULL` and joined to `roles(role, executes_tasks)`
by a foreign key, so a planning session that held a Task would be refused by the
schema rather than by a rule someone remembered to write. The session therefore
never competes for a lane slot with the work it is choosing between.

No reservation either, and not by omission: `budget_reservations.task_id` is NOT
NULL and its `kind` is the lane the promise is held against, neither of which a
planning session has. What it spends is still counted -- `program_budget` sums
every run of the Program, not only the ones that held a Task -- so the choice
costs what it cost, it just cannot promise it in advance. It is closed with
`finish_task_attempt`, the same verb the worker attempt closes with, because a
run with no Task is a case that verb already answers.

### Five words, and the runtime dispatches on them

`record_choice(agent_run, outcome, task_label, detail)` writes one
`scheduler.chose` Event whatever came back:

- `chosen` -- one Slate label came back and is now the Program's outstanding
  pick; `claim_task()` re-validates it under the row lock.
- `off_slate` -- the label did not survive `pick_task`, because the entry went
  or the Slate expired while the model was thinking. Nothing is picked and
  nothing is claimed this pass.
- `no_choice` -- the session ran and picked nothing.
- `malformed` -- something came back that is not a choice. Recorded apart from
  `no_choice` because a model that answered unreadably and one that declined are
  different runs to read back, and treated the same by what happens next.
- `unavailable` -- no session answered at all: refused at startup, no boundary,
  or a child that died. The one outcome whose `actor_kind` is `runtime`, because
  it is the runtime's own finding and not a model's.

`off_slate` is the only word the caller cannot send. The runtime offers `chosen`
and the database downgrades it, inside the handler that catches `pick_task`'s
refusal, because the database is the authority on what the current Slate carries
and a runtime that pre-checked the label against its own copy would be checking
a list it holds no lock on. It is also the reason the downgrade is not a
fallback: ADR 0003 says a stale choice is refused and not substituted, so
claiming entry one after an off-Slate answer would be the runtime answering the
question it was told the model owns. The three silences do fall back, and the
fallback is `claim_task()` with no argument -- the walk the loop did before there
was an orchestrator.

### A Skill is a property of the role that would run it

Criterion 4's second half had no rule anywhere in the corpus.
`tasks.required_skills` was checked for registration (0023's trigger) and for
being enabled (the confidence factor), and never once against the role that
would have to load it. 0032 already answers this question for a playbook -- "a
skill a role lacks is a load-time error, not a runtime escalation" -- and
`playbooks_admissible` filters on exactly this join; a Task carrying the same
requirement was admitted anyway, claimed, dispatched, and discovered at load
time inside a child that had already spent its startup.

`claimable_for` gains one arm, `skill_not_granted_to_role`, joining `role_skills`
through `role_task_kinds`. It sits after `no_role_runs_this_kind` because it
presupposes it: with no role for the kind there is no grant to look for. The
first half of the criterion was already structural -- `role_task_kinds` is unique
on kind, so a Task's kind selects one role and there is nothing to reject.

### The Python side

`execution.Slice` gains one step between the offer and the claim. It opens the
session, starts one child with `egress=None` and the Slate in its job document,
maps what came back to one of the four words the verb takes, records it and
closes the session in a `finally`. Every failure on that path -- a session that
could not be opened, a refused startup, an unavailable boundary, a child that
died -- leaves the pass exactly where it was, with a Slate and no pick, which is
the case `claim_task()` already covers. The decision is an input to the claim and
never a precondition for it.

The child reaches two new tools. `get_slate` answers from the job document,
because there is no database on that side of the boundary: the container's one
network reaches the capability proxy. `pick_task` is an in-process latch that
supersedes rather than accumulates, answers an off-Slate label as refused so the
model can correct itself while it is still running, and still reports it -- this
process refusing outright would be it deciding an outcome only the database can
decide.

`_dispatchable` is the last statement before a child is started with a Lease and
a reservation. It asserts the two invariants criterion 5 names: the committed
choice and the claimed Task are the same Task, and the claimed role is the one
`roster.ROLE_FOR_KIND` gives that kind. Both are the database's already, so
neither is expected to fire; an invariant nothing asserts is a claim about the
code rather than about the run.

### The check

`check_orchestrator_dispatch()` has six arms. Two are textual and guard code:
`claimable_for` still asking `role_skills`, and neither new verb executable by
`rk2_state`. Four are about rows: an outstanding Slate entry whose Skills its
role cannot load, a session that recorded a choice and also opened a request to
a target, a recorded choice naming no Task-less orchestrator session, and a
recorded choice carrying a sixth outcome word.

Arm (c) keys on having recorded a choice rather than on the role, because `rk
send` records an operator's own request as an orchestrator session and that
request is a person's, not a model's.
