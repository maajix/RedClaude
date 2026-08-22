# 138 — The incident response sweep has no caller

**What to build:** A caller for `find_in_database`, or the decision that it does
not need one and the register row that says so.

**Blocked by:** nothing. Ticket 125 established that the thing this gap was
recorded against will never be built.

**Status:** resolved

- [x] The row is re-pointed, from a ticket that refused the work to one that
      owns it. `tools/check_wiring.py:209` reads `"W3 find_in_database":
      "owed:125"`, and its comment records the gap "against the ticket that
      builds the redaction verifier, whose output is what a sweep would feed".
      Ticket 125 decided there is no honest implementation of that verifier and
      refused it rather than deferring it, so the row now names a resolved
      ticket whose gap is still here, which is a register error.
- [x] What the function actually is gets read before anything is decided. It is
      a synthetic-marker sweep for incident response
      (`20260810T173000Z__sealed_wire_artifacts.sql:178-218`, "For synthetic
      markers and incident response"), and it is unrelated to either half of
      ticket 125. Whether an incident-response verb needs a runtime caller at
      all, or is an operator's command, is the question this ticket answers.
- [x] Whichever way it goes, the answer is written where the next reader meets
      it. A verb with no caller and no explanation is what W3 exists to find; a
      verb with no caller and a recorded reason is a decision.

## Why

Ticket 125's agent measured the orphaned row and left the judgement rather than
guessing: *"The nearest open owner is ticket 65 ... That is a judgement call, so
I have left it to you."* Pointing it at ticket 65 would make an unrelated
function-without-caller a release-candidate blocker. It gets its own ticket
instead.


## Closing, 2026-08-22

**The answer is that it does not need one, and the register can now say so.**

### What was read

`find_in_database(needle text)` is defined at
`20260810T173000Z__sealed_wire_artifacts.sql:178-221` and redefined at
`20260814T020000Z__the_operator_answers_and_the_work_resumes.sql:759-798`. It
loops every `relkind IN ('r','p','m')` column in `public` and returns the ones
holding the needle. Measured against this tree and against the live `rk2hunt`
schema:

| Question | Answer |
|---|---|
| Callers in `src/` | none |
| Callers in `tests/` | seven, all in `tests/test_database.py` |
| `runtime_verb_surface` row | `find_in_database(text)`, added_by `66-seed` |
| Grants today | `rk2_runtime`, `rk2_owner` |

### Why a caller would be wrong rather than missing

The redefinition's own comment settles it: *"Every table column holding this
value **that the calling role may read** ... a scan that has to be complete is
run as a role that can read everything."* The verb's answer is a function of who
asked. A fixed runtime caller would pin it to one role, which is the single
thing it is built not to be, and the seven test call sites depend on exactly
that variability -- they run it as `rk2_runtime` to assert that a redacted value
is invisible to the role a child's connection holds.

The shape is wrong too. A sweep is `count(*)` over every column of every table.
That is an operator's command after an incident, not something a run does on a
cadence, and nothing in the Spec asks a run to do it.

The grant to `rk2_runtime` stays for the same reason. It is not an unused
privilege: it is what makes the leak assertions run as the role whose blindness
they are asserting. Revoking it would delete the test, not tighten the surface.

### What was built

`tools/check_wiring.py` gains a second register spelling, `decided:NN`, beside
`owed:NN`, and this row is the first to use it. The two are exact opposites
about the ticket and identical about the gap:

| | `owed:NN` | `decided:NN` |
|---|---|---|
| The ticket must be | open | resolved |
| The gap must be | present | present |

The gap requirement is unchanged on purpose. A `decided` row that outlived its
gap would excuse the next regression under the same name, which is the whole
reason the register fails in both directions. The rule was proved by running the
gate before this ticket was resolved: *"register: W3 find_in_database names
decided:138, which is not resolved, so the decision it cites has not been
made."*

### What this does not do

It does not widen to "a verb the suite calls is wired". W3 still reports
`find_in_database` as a gap on every run; what changed is that the register can
carry a reason instead of a promise. Any future verb wanting this spelling needs
its own ticket, read the same way.
