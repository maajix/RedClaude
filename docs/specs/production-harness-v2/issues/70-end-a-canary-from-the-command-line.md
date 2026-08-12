# 70 — End a canary from the command line

**What to build:** `rk callback clear`, so ending a correlator early is a verb rather than SQL on the runtime connection.

**Blocked by:** 14 — Accept one explicitly configured callback Observation.

**Status:** ready-for-agent

- [ ] An operator can clear one correlator by id, and a second clear says it changed nothing.
- [ ] Clearing another Program's correlator answers the same as clearing an unknown one.
- [ ] The report names the channel and how many arrivals the correlator had already admitted.

## Why

`clear_callback_correlator(uuid)` exists, works, and is described in its own
comment as the operator's way to end a canary early -- when the test that carried
it is over, or when the payload turns out to have gone somewhere it should not
have. `rk callback` offers `provision` and `accept` and nothing else, so using it
means opening a runtime connection by hand and remembering to
`set_config('rk2.program_id', ...)` first, because the function filters on
`rk2_program()` and silently answers `false` without it. That was measured on
2026-08-12: the first call returned `false` for a correlator that existed, for
exactly that reason.

The second half of the argument is the one that matters. The reason to clear a
correlator early is usually that a payload leaked somewhere it should not have,
which is the moment nobody should be composing SQL.

## How

`rk callback clear --config <path> --correlator <uuid>`, on the runtime
connection, binding the Program the configuration names before calling the
function. The report carries `cleared: true|false` and, when the correlator was
this Program's, the channel it was minted on and the number of interactions
already filed under it -- an operator ending a canary in a hurry should see
whether it had already fired.

Nothing about the correlator's plaintext is involved: it is cleared by row id,
which is what `rk callback provision` already prints.
