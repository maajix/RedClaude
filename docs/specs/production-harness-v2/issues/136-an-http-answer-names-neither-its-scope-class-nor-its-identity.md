# 136 — An HTTP answer names neither its scope class nor its Identity

**What to build:** The two readings ticket 108 could not reach, put on
`mcp__rk2__http_request`'s answer: the scope class the door graded the request
at, and the Identity the request was actually spent under.

**Blocked by:** 131 — An egress run is opened under no Identity at all. The
Identity half of this ticket is unanswerable until there is an Identity to
name; `execution._authorize` opens every egress Tool run with
`"identity_slot": ""`, so a key added today would report the empty string on
every request and would be worse than its absence.

**Status:** needs-triage

- [ ] The scope class reaches the model. The door already decides it, and the
      decision dies inside the proxy: `proxy._answer` / `_answered`
      (`src/redkraken/proxy.py:3735-3746`) grades the request and the grade
      never leaves. Three edits carry it out -- a field on `proxy.Answer`, the
      value set where the grade is taken, and a key in `_launch._spend` beside
      the ones ticket 108 added to `tool.serve`. Ticket 108's criterion 2 is
      this, moved rather than dropped.
- [ ] The Identity reaches the model, once there is one. `agent.Egress` has to
      carry the slot and `_launch._spend` has to name it. Ticket 108's criterion
      3 is this, and it waits on 131.
- [ ] The register says so. `tools/check_wiring.py`'s W5 arm measures fields a
      tool answer drops; ticket 108 removed the three rows it paid and this
      ticket's two are not registered anywhere, because the gate reads
      `tool.serve` and these belong to `http_request`. Either W5 is widened to
      read `_launch._spend` too and the two gaps are registered against this
      ticket, or the ticket records why the gate cannot see them.
- [ ] `tests/test_tool.py`'s boundary table gains the row. Ticket 108 built that
      table so the gate and the table cannot disagree; a new boundary that is
      not in it is a boundary nothing re-measures.

## Why

Ticket 108 paid three of its five criteria and reported the other two exactly:
*"Criterion 2 (scope class) and criterion 3 (identity) are both
`mcp__rk2__http_request`'s answer, written in `_launch._spend`. Every file that
could carry them is outside my set."* Cut here rather than left as unticked
boxes on a resolved ticket, so that the work has an owner.
