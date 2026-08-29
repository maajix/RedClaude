# 221 — The severity verb is served to a child no objective asks to use it

**What to build:** An objective that asks for a severity, or a statement that
severity is not a child's to state. Today `mcp__rk2__state_severity` is served,
described, and is the only writer of `findings.severity` -- and in four days of
hunting no child has ever called it, because the one sentence a `conclude`
child is given does not mention it.

**Blocked by:** nothing.

**Status:** ready-for-agent

## What was measured

`rk2here`, 2026-08-29, four days of running:

```
findings                              6   every one severity=info, status=candidate
severity_statements                   0
functions writing findings.severity   1   state_severity, and nothing else
```

The last line is enforced, not observed. `20260816T000000Z:2172-2179` raises if
any function besides `state_severity` carries `UPDATE findings SET severity`,
and a query against the live `pg_proc` returns exactly that one name. So the
column has one writer and the writer has one caller: an agent holding
`mcp__rk2__state_severity`.

The tool is served. `agent.SERVED` carries it, along with
`mcp__rk2__open_impact_task`, and `_launch.py:1269-1277` describes it in nine
lines of good prose the child never reads for a reason: nothing in its
objective sends it there.

The whole of what a `conclude` child is told (`execution.py:115`):

> `"conclude": "Say what the claim this Test settled is a Finding of."`

It does exactly that. Six times, over four days, in runs lasting two to three
minutes each -- the task is created, the Finding appears about two minutes
later, the run ends a minute after that. The work is done and done well. It is
just not the work that raises a severity, and `severity` appears nowhere in
`execution.py`.

There is no operator path either. `rk finding` offers `validate`, `report` and
`clear-gate`, and none of them states a band.

## The wall, priced

```
WALL    execution.py:115 -- the objective, one sentence, no severity in it.
        Read in source 2026-08-29; both ends read -- the objective that would
        ask, and `agent.SERVED` plus `_launch.py:1269-1277`, which show the
        verb is there to be asked for.
PRICE   Unknown until one question is answered, and that is why this is a
        ticket and not a patch: is severity a `conclude` child's to state?
        `state.conclude` is the group holding the verb and `web_hunter` is the
        only role with it, which says yes. `MISSIONS` also carries `analyze`
        ("say what it implies"), which has never had a Task in this Program,
        which might say no. Both readings are one sentence of work and they
        put it in different places, so the reading is the deliverable.
        Whichever it is, ticket 163's pattern applies: a child asked to name a
        word is a child shown the vocabulary, and the bands and bases are
        already closed enums (`0009_findings.sql:18`, `roster.py:514`).
PURPOSE This Program exists to find something worth reporting. Six Findings
        that are honestly `info` are a working harness; a harness that cannot
        say `medium` about anything at all is not, and the two look identical
        from the outside until someone counts `severity_statements`.
RULE    Capability before catalogue. The capability is built, served and
        guarded. What is missing is the sentence that reaches it.
```

## Acceptance criteria

- [ ] **One objective names the severity verb.** Whichever kind owns it, its
      line in `MISSIONS` sends the child to `state_severity`, and a run of that
      kind writes a `severity_statements` row.
- [ ] **The child is shown the bands and the bases.** Ticket 163's rule: the
      vocabulary comes from the closed enums, read per attempt, not copied into
      a Python constant that goes stale.
- [ ] **A Finding that is honestly `info` stays `info`.** The fix is a child
      that may state a severity, not one that must state a high one. A test
      that asserts every Finding leaves `info` is the wrong test.
- [ ] **`rk finding` says where severity comes from.** An operator reading six
      `info` Findings has no way today to learn whether that is a judgement or
      a gap.

## What this does not change

`state_severity` being the only writer, and the three bases it checks. Both are
right and both are why this is worth reaching rather than working around.
