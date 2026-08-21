# 107 — A label minted after launch must be resolvable in the run that minted it

**What to build:** Either a refresh path for the mission packet, or a rule that
act tools stop returning labels the read tools cannot honour. One of the two,
decided and written down.

**Blocked by:** 106 — Hand back the Artifact labels for the exchange the door
just filed.

**Status:** needs-triage

- [ ] The defect is one thing and not three, and the ticket states it that way:
      the agent's read surface is a snapshot and the agent's act surface mints
      new rows into a database the read surface cannot see. `packet.compile`
      (`src/redkraken/packet.py:587`) runs once, on the supervisor's `rk2_state`
      connection, before the container starts -- `roster.py:596-599` says so:
      "The child has no database: `packet.compile` runs these on the
      supervisor's `rk2_state` connection before the container starts" -- and
      every `state.read` handler answers out of the document the child reads at
      launch.
- [ ] The three symptoms are enumerated with the reason each returns, so a fix
      can be checked against them. A Receipt label from an exchange resolves to
      `{"reason": "not_staged", ...}` (`packet.py:907`); an Artifact label from
      a tool output or from ticket 106's answer resolves to
      `{"reason": "no_such_artifact", ...}` (`packet.py:947`); and a `tool_run`
      label resolves to nothing at all, because no Contract reads `tool_runs`.
- [ ] The decision is between two shapes and the ticket picks one. Either
      `packet.SECTIONS` (`packet.py:43`) gains a refresh the child can ask for,
      or the answer stops naming a handle and carries the value instead. Both
      satisfy the property; silence does not, and silence is what ships today.
- [ ] Whichever is chosen, the packet's existing honesty about what it dropped
      is kept. The bounded reads already report their own narrowing --
      `{"reason": "packet_bound", "count": ...}` at `packet.py:966` -- so a
      refresh path that answered "not staged" for a row written thirty seconds
      ago would be a worse answer than the one it replaced.
- [ ] The half of the problem the code already acknowledges is separated from
      the half it does not. `packet.py:619-622` reasons that "An Artifact whose
      bytes were not staged is still an Artifact the child knows about and can
      hand to `exec.tool_run`", which is true for Artifacts that were in the
      packet's row set and is not true for ones created after compile: those are
      in no section at all.
- [ ] The ticket is measured by an integration test, not by argument: one child
      runs `http_request` and then `get_receipts` with the label it was handed
      and gets a match; one runs `run_tool` and then `get_artifact` on each
      returned `outputs[].label` and gets bytes. Both fail today.

## Why

`docs/research/wiring/21-agent-surface-wiring.md` section 5.4 calls this "the
structural loss" and section 6's gate G6 says why it is the check that forces
the design question: "either the packet gains a refresh path, or the act tools
stop returning labels the read tools cannot honour. Either answer satisfies the
gate; silence does not."

It also gets worse before it is noticed. Tickets 98 and 99 each mint more such
labels -- an out-of-band correlator and a browser mission -- and ticket 106
mints two more per exchange. Every Observation the runtime asks a model to
ground on a Receipt (`packet.py:878-884` describes exactly this dependency) is
grounded on a label the model was told about and cannot read back.
