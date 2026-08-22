# 161 — A chooser that ran out of budget is reported as an empty queue

**What to build:** The difference between a session that looked at the Slate and
picked nothing, and a session that never got to look. Today both are
`no_choice`, both end the pass as `nothing_to_execute`, and an operator's loop
reads the second one as "the campaign is finished".

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] **A session cut off is not a session that answered.**
      `execution.Dispatch._answered` returns `no_choice` whenever the result
      carries neither a choice nor a pick attempt. The result also carries
      `stop_reason`, which said `budget`, and that word is dropped on the floor.
      A run that stopped on `budget`, `max_turns` or an error answered nothing
      and must say so with a word of its own.
- [ ] **`nothing_to_execute` means the Slate was empty.** `program._report`
      reaches it as the `else` of three tests, so it is what a pass says when it
      cannot think of anything better. Its own comment claims it "covers both
      ways of having nothing to do"; a Slate with three ready entries on it is
      neither of those ways. Either a fifth stop reason, or the existing one
      narrowed to the case its comment describes.
- [ ] **A driver loop can tell the two apart.** `hunt.sh` stops on
      `nothing_to_execute` and is right to: it means the campaign is done. It
      must not stop on a chooser that ran out of room, because the next pass
      opens a new session and the work is still there.
- [ ] **Say whether the session should have rotated.**
      `orchestrator_sessions` carries `rotated_from` and `generation` and
      `rk2hunt17` holds exactly one row: `OS1`, generation 1, `close_reason`
      `tokens`, `rotated_from` null. Rotation exists and did not happen. Settle
      whether a session closed on `tokens` is meant to rotate inside the pass
      that closed it, on the next pass, or only when an operator says so — and
      make the answer visible, because right now the campaign simply stops.
- [ ] **Checked by something that would go red.** A test that stands a Slate
      with a ready Task on it, has the chooser return a result whose
      `stop_reason` is `budget`, and asserts the pass does not report
      `nothing_to_execute`.

## Why

`rk2hunt17`, 22 August, lap 6:

```
slate    T5 perform APP2   T6 perform APP2   T7 perform APP2
choice   {"agent_run": "AR13", "outcome": "no_choice", "task": null}
AR13     orchestrator   stop_reason: budget   input 175027  output 34
stop     nothing_to_execute
```

and in the database at that moment:

```
T5 perform pending READY
T6 perform pending READY
T7 perform pending READY
```

Three Tasks ready, offered, on the Slate, and the campaign reported that there
was nothing to execute. `hunt.sh` believed it and stopped with six of twelve
laps unused.

Those three Tasks are the ones that replay the three authored Tests. A held
replay is what moves a claim to `supported`, and a supported claim is what
ticket 156 turned into a `conclude` Task and a Finding. So the first end-to-end
Finding this tree has ever been one step from was lost to a stop reason.

## Notes

The budget ceiling itself is a separate question and not this ticket's.
`_launch._usage` counts `input_tokens + cache_read_input_tokens +
cache_creation_input_tokens` at weight 1 and says why: "a cached read is
cheaper, not free, and a ceiling that ignored the cache would be a ceiling a
long session walks straight through." That is a defensible ceiling. What is not
defensible is that reaching it is indistinguishable from an empty queue.

The two words are also not the same severity. A pass that ends because a model
declined the Slate is a campaign decision. A pass that ends because the chooser
was cut off mid-sentence is an installation running out of something, and an
operator should be told which one they are looking at.
