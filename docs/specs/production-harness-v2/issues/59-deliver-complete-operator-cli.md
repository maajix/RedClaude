# 59 — Deliver the complete operator CLI

**What to build:** Give the operator one supported command surface for running, inspecting and controlling the full harness without raw database access or ad-hoc scripts.

**Blocked by:** 14 — Accept one explicitly configured callback Observation; 28 — Rotate the orchestrator and resume from a bounded capsule; 29 — Deliver pending decisions, Halt and resume verbs; 38 — Authorize and prove impact separately; 43 — Export a redacted evidence bundle; 57 — Close the 223-row v1 disposition ledger; 58 — Import v1 state without fabricating truth.

**Status:** resolved

**Reading on "complete":** thirty-nine of the forty-one verbs on this surface were built by
the tickets this one is blocked by, so what "deliver the complete operator CLI" asks for at
this point is the three things missing and one audit of the whole. The three are
`rk version`, `rk finding report` and `rk finding clear-gate`. The audit is
`OperatorSurfaceTest`, which asks the questions that are only answerable about a set rather
than about a command: that every area criterion 1 lists has a verb, that no command
anywhere takes SQL or a patch or a credential by value, that the commands wired to the
operator's own console are exactly the seven control verbs and nothing else, and that a
Program is an argument only where a person names one. It reads the parser rather than a
list written here, so a verb added later is audited by being added. It is an audit of the
surface and not of the database: that those seven are also the only ones `rk2_human` holds
is asked where it can be asked, as a refusal on the runtime connection in
`FindingReportTest` and in 29's cases for the rest.

**Reading on criterion 5:** 019 built every part of the last step and left it with no
caller. `transition_rules` has reserved `validated -> reported` for a human actor since 06,
`report_renderings` holds the exact bytes an approval may name, `enforce_report_approval`
refuses a transition that names none, and nothing in the corpus ever inserted the row --
so an operator's only route to the end of the harness was `psql`, and `findings.reported_at`
had been ranked on since 023 without anything writing it. Clearing is a verb of its own
rather than a flag on reporting because 42 refuses to keep bytes for a blocked Finding: an
operator who could only clear a gate as part of approving a rendering would have nothing to
approve.

Two of `report_blockers`'s nine codes are liftable and seven are not, and which two is a
row in `review_gates` rather than a list in a function body. `duplicate` and `known_issue`
are a judgement -- the report signature is deliberately coarser than a dedup key, and
whether a published do-not-send list meant this instance is a reading of somebody's words.
The other seven are computed from rows and are answered by changing the rows, which is why
`check_finding_reporting` fails if one of them is ever registered as a gate.

- [x] Supported verbs cover version, doctor, migrate, run/resume, Program lifecycle, compact/full reads, Halt/clear, pending decisions, integrity, import, validation, report and evidence export.
- [x] Read verbs are non-mutating and return stable structured output with labels, revisions, digests and omission markers.
- [x] Mutation verbs are narrow domain operations with explicit confirmation or standing-grant requirements where risk demands it.
- [x] There is no generic SQL, arbitrary JSON patch, credential read/write, raw Receipt insert or Program-selector argument on model-facing operations.
- [x] Human-only Finding reporting and review-gate clearing are distinct operator transitions with Events.
- [x] Help, exit codes, machine-readable output and redacted diagnostics are consistent and tested from a clean installation.

## Comments

Implemented on 2026-08-17.

`src/redkraken/migrations/20260906T000000Z__a_person_reports_a_finding_and_lifts_a_gate.sql`,
`migrate.revision` in `src/redkraken/migrate.py`, `report_finding` and `clear_gate` in
`src/redkraken/operator.py`, the `version`, `finding report` and `finding clear-gate`
subcommands in `src/redkraken/cli.py`, the digest the `--record` answer now carries in
`src/redkraken/reporting.py`, `FindingReportTest` and three negative controls in
`tests/test_database.py`, `OperatorSurfaceTest` plus the new `VersionTest` arms in
`tests/test_cli.py`, and the clean-install arm in `tests/test_packaging.py`.

### `rk version` answers what `--version` cannot

`--version` prints a line for a person reading a terminal. Two machines running the same
package version can still be running different databases, so the verb answers in the shape
every other command answers in and carries the number that actually decides whether they
agree: the corpus digest, over the identity and bytes of every migration file, beside the
count and the last identity. A corpus that will not load is a violation rather than a
silence -- an installation whose migrations are unreadable is one the operator has to be
told about, and this is the first command they run. It reaches no database and no network,
which the audit hook proves rather than the help text claiming it.

### A clearance is a row, not a flag

`finding_gate_clearances` records one person's act on one gate on one Finding: the reason
they gave, what the gate was saying at the time, who they were and when. It is immutable by
013's trigger, `human` by CHECK and by 026's guard, and unique on `(finding_id, code)`, so
a gate is lifted once and the record of why cannot be rewritten afterwards. The verb
answers with what is still blocking and not only with what it lifted, because a clearance
that read as permission to send would be exactly the thing this ticket is meant to prevent.
The operator reads the row through a policy written for them: `apply_state_rls` writes one
for each machine connection and none for a person, and row security with no policy returns
no rows, so the SELECT granted to `rk2_human` would otherwise have read an empty table.

`report_blockers` consults the table in its `known_issue` and `duplicate` arms and nowhere
else. The function is replaced rather than edited, on 38's body rather than 034's, because
38 replaced it last and a copy taken from the older file would have silently undone 38's
severity arm.

### The confirmation on the one verb that cannot be undone

Criterion 3 asks for explicit confirmation where risk demands it, and reporting is the one
mutation with nothing after it: `reported` is terminal in `transition_rules` and a
clearance cannot be withdrawn. A yes/no prompt would confirm that the operator meant to
press the key, which was never the question. `rk finding report` takes `--content-sha256`
instead, and `report_finding` refuses unless it matches the rendering's own digest -- so
the thing confirmed is which document was read. `rk report finding --record` prints the
digest beside the rendering id, which is where the operator copies it from.

### The operator's reason is not something a model reads

29 found that an operator's free text is reachable three ways -- the column, a view over
it, and the event payload -- and closed all three on `pending_decisions.answer`. A
clearance's reason is the same kind of sentence, and a worse one to leak: it is an argument
for sending a report a program said it did not want, so a model that can read it can learn
to make it. Section 6 of the migration closes the same three doors, three arms of
`check_finding_reporting` ask about all three as rows, and three negative controls open
each one in turn. Two of them are opened by doing nothing at all -- 029's default
privileges grant `rk2_runtime` SELECT on every table and view `rk2_owner` creates, so the
grant on `finding_gate_clearances` is a REVOKE followed by a column grant, and the view
control needs no GRANT of its own. `detail` is not redacted, because it is
`report_blockers`'s own computed sentence and hiding it would hide the machine from the
machine.

### What the surface audit could not ask

Two of the eight arms of `check_finding_reporting` are asserted by forging the state they
describe inside a transaction that is rolled back, because they cannot be put back
otherwise: `findings_status_guard` and 019's approval trigger are both ENABLE ALWAYS, so a
deleted `reported` transition can be re-inserted by nobody at all. The arm about a
clearance filed under a Program that is not the Finding's is refused by the composite
foreign key before it can be written, which is asserted directly instead. The first arm
reads `report_blockers`'s own body rather than a copy of the two liftable codes, so a gate
registered without an arm to consult it is caught by the check rather than by a list here
going stale.
