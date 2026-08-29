# 221 — Severity waits on a validation nothing in this runtime can ask for

**What to build:** Nothing here. This ticket is the measurement that shows what
ticket 105 costs, taken by building the wrong fix first and watching it be
refused. Close it when 105 lands.

**Blocked by:** 105.

**Status:** ready-for-agent

## The chain, measured end to end

`rk2here`, 2026-08-29, after the door restart of ticket 220 put test grading
back:

```
findings                     8   every one severity=info, status=candidate
severity_statements          0
validate tasks, ever         0
report tasks, ever           0
```

`state_severity` is the only writer of `findings.severity` --
`20260816T000000Z:2172-2179` raises if any other function carries the UPDATE,
and a query against the live `pg_proc` returns exactly that one name. It is
served (`agent.SERVED`), described in nine good lines (`_launch.py:1269-1277`),
and reachable by `web_hunter` through `state.conclude`.

It was never called, so the obvious reading was that no objective asks for it.
That reading was wrong, and the cheapest way to find out was to add the
sentence and dispatch one `conclude` Task with it. Run `AR989`, 22:44:12:

```
tools_called => ['get_evidence', 'get_hypotheses', 'get_receipts',
                 'http_request', 'propose_finding', 'state_severity',
                 'submit_mission_result']
denials     => []
```

The child called it. `severity_statements` stayed at 0 and `denials` stayed
empty, because `propose_severity` (`20261031T000000Z:194-215`) catches the
`RAISE` and answers `outcome: refused` rather than aborting -- deliberately,
and the file says so. Reproduced directly, in a rolled-back transaction:

```
SELECT propose_severity('F8','low','program_context', '...');

{"outcome": "refused",
 "refusal": "finding F8 is candidate and severity is stated about a validated Finding"}
```

So the order is fixed and it is the right order: a band is a claim about a
Finding somebody has reproduced, and a `conclude` child has just created one
that nobody has. The full chain to a severity is

```
test holds -> hypothesis supported -> Finding, candidate, info
           -> [ validation ] -> Finding validated -> state_severity
```

and the runtime cannot take the bracketed step. `mcp__rk2__request_validation`
is declared (`roster.py:1015`) and served by nothing (ticket 105), so no
`validate` Task has ever existed in this Program. The only way past it is an
operator running `rk finding validate`, which needs the Agent network the hunt
is holding (ticket 219).

## The wall, priced

```
WALL    state_severity's validated-only rule, reached through
        `propose_severity` (`20261031T000000Z:194-215`) and reproduced above.
        Read in source and exercised against the live database 2026-08-29;
        both ends read -- the verb that refuses, and the objective that now
        reaches it.
PRICE   Zero here and all of it in ticket 105. The severity verb needs no
        change, no new objective and no new sentence: a `conclude` child that
        calls it is refused for a true reason, and one that does not call it
        loses nothing. What is missing is upstream.
PURPOSE This Program exists to find something worth reporting. It has eight
        candidate Findings and no way to say what any of them is worth, and
        the two facts look like one working harness from outside.
RULE    Capability before catalogue. The severity capability is complete. The
        validation capability is declared and unserved, which is 105.
```

## What was tried and reverted

The `conclude` objective was extended to ask for a severity, with two tests, and
reverted the same hour once the refusal was read. It is recorded here rather
than dropped because the next session to notice `severity_statements = 0` will
reach for the same fix: the verb is served, the objective is silent, and the
sentence is one line. It does not work, and the reason is one query away.

## Acceptance criteria

- [ ] **A Finding reaches `validated` without an operator.** Ticket 105's, not
      this one's.
- [ ] **A validated Finding gets a band.** Once 105 lands, whichever run holds
      a validated Finding asks for the severity -- and the objective sentence
      reverted here is the one to restore, moved to that kind.
- [ ] **`rk finding` says where severity comes from.** An operator reading
      eight `info` Findings cannot tell a judgement from a gap. Free, and true
      whether or not 105 lands.
