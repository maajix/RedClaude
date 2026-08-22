# 138 — The incident response sweep has no caller

**What to build:** A caller for `find_in_database`, or the decision that it does
not need one and the register row that says so.

**Blocked by:** nothing. Ticket 125 established that the thing this gap was
recorded against will never be built.

**Status:** needs-triage

- [ ] The row is re-pointed, from a ticket that refused the work to one that
      owns it. `tools/check_wiring.py:209` reads `"W3 find_in_database":
      "owed:125"`, and its comment records the gap "against the ticket that
      builds the redaction verifier, whose output is what a sweep would feed".
      Ticket 125 decided there is no honest implementation of that verifier and
      refused it rather than deferring it, so the row now names a resolved
      ticket whose gap is still here, which is a register error.
- [ ] What the function actually is gets read before anything is decided. It is
      a synthetic-marker sweep for incident response
      (`20260810T173000Z__sealed_wire_artifacts.sql:178-218`, "For synthetic
      markers and incident response"), and it is unrelated to either half of
      ticket 125. Whether an incident-response verb needs a runtime caller at
      all, or is an operator's command, is the question this ticket answers.
- [ ] Whichever way it goes, the answer is written where the next reader meets
      it. A verb with no caller and no explanation is what W3 exists to find; a
      verb with no caller and a recorded reason is a decision.

## Why

Ticket 125's agent measured the orphaned row and left the judgement rather than
guessing: *"The nearest open owner is ticket 65 ... That is a judgement call, so
I have left it to you."* Pointing it at ticket 65 would make an unrelated
function-without-caller a release-candidate blocker. It gets its own ticket
instead.
