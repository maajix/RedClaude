# 107 — A label minted after launch must be resolvable in the run that minted it

**What to build:** Either a refresh path for the mission packet, or a rule that
act tools stop returning labels the read tools cannot honour. One of the two,
decided and written down.

**Blocked by:** 106 — Hand back the Artifact labels for the exchange the door
just filed.

**Status:** ready-for-agent

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

## The decision, taken 2026-08-22

**A: the packet gains a refresh the child can ask for, scoped to the labels the
child names -- and the ticket says out loud that the way to read past byte 4,096
of any Artifact is a tool run, not a refresh.**

The number that decides it is **32,768**, the packet's whole byte ceiling, set
against **158,222**, the bytes one `js_parse` run produced on a real 88 KB
JavaScript bundle. The ceiling is `min(byte_limit, token_limit * BYTES_PER_TOKEN)`
with shipped defaults of 65,536 and 8,192 (`src/redkraken/packet.py:55`,
`:58-59`, `:133-134`). So one act-tool result carried inline under B would be 4.8
times the entire read surface the run is held to, and at 49,237 tokens it is 1.23
times the run's whole 40,000-token budget (`README.md:204`). The response side is
worse by another order: the `en.wikipedia.org/wiki/HTTP` transcript is 625,735
bytes and 195,582 tokens, which is 4.9 times that budget for one exchange, and a
run may make fifty (`README.md:205`).

**B is not a new design; it is the design that already shipped for the small
case.** `run_tool` already returns a 4,096-byte head of standard output
(`src/redkraken/tool.py:520-535`), and ticket 94 already put the response headers
and a `packet.DEFAULT_EXCERPT` body excerpt in `_spend`'s answer
(`src/redkraken/_launch.py:899-911`, `packet.py:60`). The measured
`compare_responses` output is 520 bytes and is already entirely inside that head.
Labels exist precisely for what those excerpts do not cover, so "carry the value
instead" either changes nothing or is the arithmetic above.

**A's transport is already built, and it has grown an arm since it was
measured.** `Channel.call` writes one JSON line under `rk2_call` on the child's
standard output and blocks on one line back under `rk2_answer`, matched by an
integer `id` (`src/redkraken/_launch.py:399-467`; `isolation.CALL` and
`isolation.ANSWER` at `src/redkraken/isolation.py:152-153`). The supervisor's side
is one closed dispatch on `verb` that answers `unknown_call` for anything else
(`src/redkraken/agent.py:1207-1212`), and since document 31 measured it, ticket
102 added a third arm to it -- `propose_finding` -- which is the proof that a
fourth is one arm and not a transport. Three further facts keep A small:
`v_records` already projects a `tool_run` kind, so a `tool_runs` section needs no
new SQL and `packet.RECORD_KINDS` (`packet.py:49`) maps only three of the kinds
that view offers; `Reader.packet` is a plain attribute holding a `replace`-able
dataclass (`packet.py:825-830`), so merging refreshed rows into what the child
reads is an assignment. The one genuinely new cost is that `packet.compile`
(`packet.py:587`) needs an `rk2_state` connection rather than the runtime one
`agent._Tools` holds: a second `pg.Settings` on `agent.Tooling` and the same four
calls `src/redkraken/execution.py:1939-1978` already makes.

**Two things go in the ticket with the verdict, because the measurement says
them.**

The refresh must be **scoped and must report its own bound**. One run of the
`authentication` Playbook mints 78 labels -- 10 exchanges and 16 tool runs, each
exchange one Receipt plus ticket 106's two Artifacts, each tool run one
`tool_runs` row plus the two Artifacts `tool._streams` keeps whether empty or not
(`src/redkraken/tool.py:790-804`). Those rows encode to 10 x 1,367 + 16 x 1,269 =
**33,974 bytes**, already over the 32,768 ceiling before a single Artifact head is
staged. So an unscoped refresh cannot honour criterion 4 by handing back
everything; it answers the labels the child names, which is what `Reader.receipts`
and `Reader.artifact` already take, and it reports what it dropped the way `_page`
already does with `{"reason": "packet_bound", ...}` (`packet.py:966`).

And **neither A nor B fixes the read the excerpt measurement is about.**
`_window` reads the staged head and nothing else: a `range` past the staged bytes
returns `{"reason": "range_beyond_excerpt", ...}` and no content at all
(`packet.py:981-1009`, the marker at `:1005-1007`). So even a perfect refresh
gives a child at most 4,096 bytes of any one Artifact, and on `github.com/login`
that is 8.7% of the body containing none of the sixteen input names. The route
that reads a whole Artifact exists and is the right one: `run_skill_script` hands
the program the entire Artifact untruncated (`tool.py:741-748`, `skill.envelope`
at `src/redkraken/skill.py:170-198`) and answers a bounded summary. What is
missing there is not a value and not a refresh but the label that makes that
route addressable from an exchange, which is ticket 106.

Rejected: B, the act tools carrying the value instead of a handle -- by the
arithmetic above. Also rejected: silence, which is what ships today.

## What was measured

Every registered offline tool run on a real input and its standard output weighed
(`docs/research/decisions/31-inline-values-and-nway-compare.md`, "Ticket 107").
The largest single answers: `js_parse` on `@octokit/plugin-rest-endpoint-methods`
10.4.1 at **158,222 bytes / 49,237 tokens**; `js_map` index on
`swagger-ui-bundle.js.map` at **260,942 / 80,938**; `jq '.'` over
`registry.npmjs.org/vue` at **2,775,503 / 966,253**. Ten live HTTP transcripts
assembled the way `src/redkraken/proxy.py:850-882` assembles them; the excerpt
`_spend` returns covered 0.7% to 11.9% of the five bodies with form or link
structure in them, and covered 0 of 16 named inputs on `github.com/login`. Row
weights in the packet's own encoder (`packet.encode`, `packet.py:101-108`): one
Receipt 663 bytes, one Artifact 352, one `tool_run` 565.

Re-verified against this tree: `SECTIONS` at `packet.py:43`, `RECORD_KINDS` at
`:49`, `DEFAULT_EXCERPT = 4096` at `:60`, `byte_ceiling` at `:132-134`,
`not_staged` at `:907` and `:993`, `no_such_artifact` at `:947`, `packet_bound` at
`:966`, `range_beyond_excerpt` at `:1006`.

## What would change the answer

Two things, both checkable. If the largest stdout any registered program can
produce on a realistic input fell below 32,768 bytes, B would be right; the
registry bounds it today at `max_output_bytes` of 4,194,304, 2,097,152 and
1,048,576, and lowering those is a one-line registry change -- but the octokit
answer is 158,222 bytes because that bundle holds 591 distinct API paths, and a
program that answered a bundle's whole surface in 32,768 bytes would be answering
a different question. And if ticket 106 lands handing back one Artifact label per
exchange rather than two, one `authentication` run mints 68 labels and 30,454
bytes of rows, which is under the ceiling and makes an unscoped refresh
expressible; that is worth re-measuring when 106 is written.

## Correction: the `tool_run` label is 129's third bucket

Criterion 2 says a `tool_run` label "resolves to nothing at all, because no
Contract reads `tool_runs`". Verified, and worth naming precisely rather than
leaving as a fourth symptom: `tool_runs` is one of the twenty-seven relations on
the agent read surface that no tool reaches, measured against this tree, and
`tool_runs`, `tool_run_artifacts`, `tool_run_inputs` and `tool_run_paths` are four
of them. That set is ticket 129's, which is why 129 is blocked by this one -- a
refresh path is what makes a read of those rows answerable at all.
