# 136 — An HTTP answer names neither its scope class nor its Identity

**What to build:** The two readings ticket 108 could not reach, put on
`mcp__rk2__http_request`'s answer: the scope class the door graded the request
at, and the Identity the request was actually spent under.

**Blocked by:** 131 — An egress run is opened under no Identity at all. The
Identity half of this ticket is unanswerable until there is an Identity to
name; `execution._authorize` opens every egress Tool run with
`"identity_slot": ""`, so a key added today would report the empty string on
every request and would be worse than its absence.

**Status:** resolved

- [x] The scope class reaches the model. The door already decides it, and the
      decision dies inside the proxy: `proxy._answer` / `_answered`
      (`src/redkraken/proxy.py:3735-3746`) grades the request and the grade
      never leaves. Three edits carry it out -- a field on `proxy.Answer`, the
      value set where the grade is taken, and a key in `_launch._spend` beside
      the ones ticket 108 added to `tool.serve`. Ticket 108's criterion 2 is
      this, moved rather than dropped.
- [x] The Identity reaches the model, once there is one. `agent.Egress` has to
      carry the slot and `_launch._spend` has to name it. Ticket 108's criterion
      3 is this, and it waits on 131.
- [x] The register says so. `tools/check_wiring.py`'s W5 arm measures fields a
      tool answer drops; ticket 108 removed the three rows it paid and this
      ticket's two are not registered anywhere, because the gate reads
      `tool.serve` and these belong to `http_request`. Either W5 is widened to
      read `_launch._spend` too and the two gaps are registered against this
      ticket, or the ticket records why the gate cannot see them.
- [x] `tests/test_tool.py`'s boundary table gains the row. Ticket 108 built that
      table so the gate and the table cannot disagree; a new boundary that is
      not in it is a boundary nothing re-measures.

## Why

Ticket 108 paid three of its five criteria and reported the other two exactly:
*"Criterion 2 (scope class) and criterion 3 (identity) are both
`mcp__rk2__http_request`'s answer, written in `_launch._spend`. Every file that
could carry them is outside my set."* Cut here rather than left as unticked
boxes on a resolved ticket, so that the work has an owner.

## The decision

**The grade travels as a header, not as a second return value.** `_answer`
already writes `X-RedKraken-Receipt`, `-Decision` and `-Detail` on the answer the
child reads; the scope class becomes a fourth, `X-RedKraken-Scope`, set at the
one place the grade is taken and read back in `_answered` into
`Answer.scope_class`. `_launch._spend` then names it. A second channel for one
string would have been a second thing to keep in step with the first.

`_refuse` sends the grade too, and sends `denied` when there is no authorization
yet -- a request refused on its body is refused before the door grades it, so
`denied` is the true answer and an absent header would read as "the door had no
opinion".

**The Identity is the slot the Task selected, and `anonymous` reports as no
slot.** `Claimed.identity_slot` is `""` when the selected Identity's class is
`anonymous`, and the slot name otherwise. That keeps ticket 97's rule intact --
a non-empty `identity_slot` on a Tool run means borrowed credentials and forces
`approval_required` -- while ticket 131's rule that every Task selects an
Identity explicitly no longer turns every egress run into an approval.

## What the register measures

W5 reads `_launch._spend` against `proxy.Answer` already, so `scope_class` is
measured the moment the field exists and needed no new row. The Identity comes
from `agent.Egress`, which W5 was not reading, so `BOUNDARIES` gains
`("_launch._spend egress", "_launch.py", "_spend", "agent.py", "Egress")` and
`tests/test_tool.py` gains the same row. It is inserted before the `tool.serve`
row because that test asserts `BOUNDARIES[-1]` is `tool.serve`.
