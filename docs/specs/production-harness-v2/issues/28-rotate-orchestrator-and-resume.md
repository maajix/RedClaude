# 28 — Rotate the orchestrator and resume from a bounded capsule

**What to build:** End an orchestrator session at configured ceilings and continue the logical campaign in a fresh session using only newly compiled durable state.

**Blocked by:** 27 — Let the orchestrator choose and dispatch a role.

**Status:** resolved

- [x] Turn, token and decision ceilings are hard runtime settings rather than prompt guidance.
- [x] Reaching a ceiling closes the current session cleanly and emits one occurrence Event with usage and reason.
- [x] The replacement session receives a bounded capsule of Program lifecycle, budget, integrity, active work and the next Slate with revisions, digests and omission markers.
- [x] No old transcript, model-authored summary or in-memory scheduler object is required to continue.
- [x] Restarting the supervisor between rotations yields the same next eligible Slate as uninterrupted rotation.
- [x] Serialized capsule size and estimated tokens are measured and refused or further compacted when above configured limits.

## Comments

Implemented on 2026-08-13 in one migration --
`20260814T010000Z__rotate_the_orchestrator_and_resume.sql` -- and one new Python
module, `capsule.py`, wired into `execution.py`, `agent.py` and `_launch.py`.

27 opened one orchestrator session per pass and closed it at the end of the same
pass. That is a session with nothing to rotate: it never reaches a ceiling,
never hands anything on and never has to survive a restart. 27's own comments
say so and name this file. What ADR 0003 describes -- one long orchestrator
session that recomputes as slots free -- needed three things the corpus did not
have, and a fourth that belonged in Python.

### The ceilings are columns

`scheduler_weights` gains five: `session_max_turns` (100), `session_max_tokens`
(1000000), `session_max_decisions` (80), `capsule_max_bytes` (65536) and
`capsule_max_tokens` (8192). The first three bound a campaign, the last two
bound what a successor is handed, and the capsule pair are `packet.py`'s own
defaults because the capsule is fitted by the same fitter as the mission packet.

A session copies all five when it opens, along with the weights version it
copied them from. Copied and not joined, for `budget_reservations.kind`'s
reason: the ceilings are what this session was admitted under, and an operator
editing the active row mid-campaign must not retroactively rotate or un-rotate a
session that has already run, or shrink mid-campaign the capsule its successor
is compiled into. `max_concurrent_subagents` is deliberately not copied and is
still read live: it bounds how many children may exist at once, which is a fact
about now rather than about what this session was admitted under.

### The campaign is a row

`orchestrator_sessions` is one campaign: the ceilings, the generation, the
session it replaced and when and why it ended. A partial unique index on
`(program_id) WHERE closed_at IS NULL` is the whole of "one campaign at a time",
because two open sessions would make "resume" a question with two answers. The
self foreign key is composite -- `(rotated_from, program_id)` -- so a chain
cannot reach into another Program. `agent_runs.orchestrator_session_id` says
which campaign a pass was a turn of, with a check that only a Task-less
orchestrator run may carry one: a worker run and the operator request `rk send`
records are not turns of anything.

Usage is derived and never counted. `orchestrator_session_usage` sums turns from
the runs, tokens from what those runs recorded and decisions from the
`scheduler.chose` Events they wrote. A counter column would be a second copy of
all three, and the first thing a standing check would have to assert is that the
copy still agrees with the rows it was copied from. Nothing increments, so a
supervisor that died mid-campaign resumes to the numbers it would have had.

### Rotation happens inside the open

`rotate_orchestrator_session()` closes the open session if
`orchestrator_session_spent()` names a ceiling, and writes one
`scheduler.rotated` Event carrying usage and ceilings both -- "why did this
rotate" is a comparison, and a reader holding only the reason would have to go
and find the numbers the decision was made on. `open_orchestrator_session()`
calls it first and then resumes or opens, which makes the whole thing idempotent
by construction: every later pass calls it again and finds nothing to close.

The pass calls it a second time at its own end, in a `finally` so that no early
return skips it. Without that, a campaign that reached a ceiling on what turns
out to be the last pass of the day sits open with its Event unwritten until a
supervisor happens to run again. A rotation that cannot be written there is
reported and does not fail the pass: the work of the pass is already done, and
the next open will close the session anyway.

The token ceiling the child is handed is now the tighter of two -- the Program's
per-run allowance and what the session has left -- because a child handed the
first alone could spend a campaign's whole remainder in one turn and be inside
its own ceiling throughout.

### The capsule is compiled, not remembered

`capsule.py` compiles five sections on the runtime connection: lifecycle
(Program standing and the campaign), budget (`program_capacity` and each lane),
integrity (the standing checks), work (what is claimed or running right now) and
slate (what this pass was offered). `packet.py`'s `Row`, `Section`, `Limits`,
`fit` and `bound` do the fitting -- two documents cross into one child and one
fitter answers both -- and `bound` grew an `order` parameter so the capsule's
own five names can be gathered without teaching it about them.

Digests come from SQL, including for the two sections built in Python: the
integrity checks and the Slate entries are sent back to the server and hashed by
`jsonb_array_elements` with `sha256(value::text)`, which is the same definition
the three read sections are hashed by. A digest computed here would agree with
itself and with no row.

Revisions come from SQL too. The three read sections carry `rk2_revision(...)`
of the row they were read from; a Slate entry carries the revision of the Task
it ranks, read back by label for the labels the pass is carrying, so a successor
can tell an entry about a Task that has since moved from one that has not. The
integrity checks are the exception and stay at revision 0 on purpose: a check is
a reading of this moment and not a row anything revises.

Criterion 6 is `_compacted`: the fit runs against the byte ceiling minus the
measured cost of the empty document, each pass subtracts the excess the last one
actually measured, and a capsule still over after four passes is refused rather
than sent. The two refusals say different things, because they are different
faults: a ceiling too small for the document's framing is a setting to change,
and a fit that has not converged in four passes is this module not converging.
`byte_ceiling` is `min(bytes, tokens * 4)`, so both configured limits bind
exactly. Every section states its own omission, because a subtraction a
model has to perform first is a subtraction it can decline to perform.

The Slate crosses the boundary inside the capsule and nowhere else: the job
document's `slate` key is gone, `get_slate` is served from the capsule's slate
section, and the objective states `Capsule.brief()` -- the capsule minus the
Slate -- so one model is not handed two copies of the same list. The objective's
promised count is therefore the fitted section's and not what the scheduler
offered: compaction can drop entries, and a number the tool cannot serve is a
number the model would spend a turn looking for. A capsule compacted until no
entry is left at all is refused -- an orchestrator asked to choose from nothing
has no move that is not a mistake.

The standing checks are read inside the compile and nowhere else -- `compile`
takes no checks to quote instead. The pass's own gate ran before the scheduler
did, so carrying it in would put a sentence about an earlier moment inside a
document claiming to describe this one. The cost is one extra
`run_standing_checks()` per pass.

### What can go wrong, as rows

`check_orchestrator_rotation()` has seven arms: a session that ran past its
ceilings, a turn started in a closed session, a close with no Event, a broken
chain, a choice recorded outside any campaign, an open path that stopped asking
whether to rotate, and either rotation verb reachable by `rk2_state`. Four
negative controls in `tests/test_database.py` show it failing. "One open session
per Program" is deliberately not an arm: the index refuses it, and a check that
re-asserted an index would be asserting the database against itself.

`tests/test_capsule.py` (28 tests) is the document -- what the compile asks,
where a digest and a revision come from, what a tight ceiling omits and what a
malformed capsule does when the child reads it. `CapsuleTest` in
`tests/test_execution.py` is the seam. `OrchestratorRotationTest` in
`tests/test_database.py` is the campaign on live rows: one Program per way of
ending one, and two scenarios for criterion 5. `capsule` is the document half --
one moment compiled twice by two connections that share nothing. `restart` is
the campaign half -- `offer_slate` run before a rotation and again after it by a
process started afresh, which is the criterion in its own words: a supervisor
restarted between rotations is offered the same next Slate.
