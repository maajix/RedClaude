# 107 — A label minted after launch must be resolvable in the run that minted it

**What to build:** Either a refresh path for the mission packet, or a rule that
act tools stop returning labels the read tools cannot honour. One of the two,
decided and written down.

**Blocked by:** 106 — Hand back the Artifact labels for the exchange the door
just filed.

**Status:** resolved

- [x] The defect is one thing and not three, and the ticket states it that way:
      the agent's read surface is a snapshot and the agent's act surface mints
      new rows into a database the read surface cannot see. `packet.compile`
      (`src/redkraken/packet.py:587`) runs once, on the supervisor's `rk2_state`
      connection, before the container starts -- `roster.py:596-599` says so:
      "The child has no database: `packet.compile` runs these on the
      supervisor's `rk2_state` connection before the container starts" -- and
      every `state.read` handler answers out of the document the child reads at
      launch.
- [x] The three symptoms are enumerated with the reason each returns, so a fix
      can be checked against them. A Receipt label from an exchange resolves to
      `{"reason": "not_staged", ...}` (`packet.py:907`); an Artifact label from
      a tool output or from ticket 106's answer resolves to
      `{"reason": "no_such_artifact", ...}` (`packet.py:947`); and a `tool_run`
      label resolves to nothing at all, because no Contract reads `tool_runs`.
- [x] The decision is between two shapes and the ticket picks one. Either
      `packet.SECTIONS` (`packet.py:43`) gains a refresh the child can ask for,
      or the answer stops naming a handle and carries the value instead. Both
      satisfy the property; silence does not, and silence is what ships today.
- [x] Whichever is chosen, the packet's existing honesty about what it dropped
      is kept. The bounded reads already report their own narrowing --
      `{"reason": "packet_bound", "count": ...}` at `packet.py:966` -- so a
      refresh path that answered "not staged" for a row written thirty seconds
      ago would be a worse answer than the one it replaced.
- [x] The half of the problem the code already acknowledges is separated from
      the half it does not. `packet.py:619-622` reasons that "An Artifact whose
      bytes were not staged is still an Artifact the child knows about and can
      hand to `exec.tool_run`", which is true for Artifacts that were in the
      packet's row set and is not true for ones created after compile: those are
      in no section at all.
- [x] The ticket is measured by an integration test, not by argument: one child
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

## What was built

Verdict A, as it was decided and without re-opening it. `refresh_packet` is the
sixth read on the agent surface and the only one answered by the runtime: it
takes Receipt, Artifact and Tool Run labels, reads the rows behind them off an
`rk2_state` connection, and folds them into the document the other five answer
from. After it, `get_receipts` resolves a Receipt an exchange filed a second ago
and `get_artifact` returns the head of an Artifact a tool run just wrote.

**The overturn condition did not fire.** This section named one thing that would
change the answer: "if ticket 106 lands handing back one Artifact label per
exchange rather than two". It landed two --
`request_artifact` and `response_artifact`, both named, because
`compare_responses` takes an ordered `first` and `second` and a run differencing
its own request against its own response needs to say which is which. So the 78
labels and 33,974 bytes stand, the refresh is scoped, and this ticket did not
have to re-decide anything. Worth adding for the next reader: even at the 68
labels and 30,454 bytes the one-label case would have produced, "unscoped" would
have meant a refresh that spent 93% of the packet's whole 32,768-byte ceiling on
one run's own rows. The condition was arithmetically live and was never
operationally attractive.

**What changed.**

`packet.refresh` is `compile`'s other half and is asked by label rather than by
rank (`src/redkraken/packet.py`). It is bounded by `REFRESH_BYTES`, which is
8,192 and is not the packet's ceiling on purpose: a packet is paid once before
the container starts, and a refresh is paid again every time a run asks, so a
refresh held to the packet's own ceiling would be a run that could spend its
whole read surface a second and a third time by asking twice more. What did not
fit comes back as `packet_bound`, which is the word `_page` already uses.

`packet.refresh` returns two things and not one. The fragment is what fitted;
`held` is which of the asked-for labels this Program has a row for at all,
measured before the fit. That is the whole of criterion 4: a label that exists
and did not fit must not be reported as a label that does not exist, because one
of those is fixed by asking for fewer and the other is not. `Reader.refresh`
turns the difference into three separate markers -- `not_held`, `packet_bound`,
`not_refreshable` -- and rolling them into one number would have been the "not
staged" answer for a row written thirty seconds ago that this ticket exists to
refuse.

`agent._Tools` grew a sixth arm, and it is the only one that does not run on
that object's connection. It opens its own as `rk2_state`, because `v_records`
is granted to that role alone and -- the reason that matters -- `rk2_state`'s
policies are `USING (program_id = rk2_program())` while `rk2_runtime`'s are
`USING (true)`. A verb that scopes inside itself is fine for a verdict; a read
that hands back whole rows is not a place to depend on remembering to write a
predicate. `state.assert_agent_connection` and `state.bind_agent_session` are
called rather than copied, which is what those two say in as many words they are
public for.

`_launch.Refresh` asks and folds. The folding is on the child's side because it
is the half of this verb that is not a question: the supervisor answers rows,
and what makes those rows part of what this child reads is an assignment here. A
handler that answered without folding would give the model the rows once and
leave `get_receipts` still saying they do not exist.

No migration. This ticket was allocated one and needs none: `v_records` already
projects a `tool_run` kind, `v_artifacts` already carries what an Artifact row
says, and both are already granted to `rk2_state`. Nothing new is executed, so
there is no `GRANT EXECUTE` to make and no `runtime_verb_surface` row to write.

**The defect this ticket found in its own transport.** The decision says A's
transport is already built and that a fourth arm "is one arm and not a
transport". True, and it is worth writing down what the arms disagree about:
`Channel.call` writes `{**arguments, "verb": verb}` -- the contract's arguments
*beside* the verb -- and `_Tools._propose` and `_Tools._callback` both read
`call.get("arguments")`, which in that frame is nothing at all. So a proposal
crosses as three empty strings and a correlator request as two. Both are
pre-existing and were proved so against `git archive HEAD`
(`agent.py:1234`, `:1237` in that tree); neither is this ticket's to fix. What
this ticket did fix is its own two: `refresh_packet` and ticket 106's
`rk2__name_transcripts` now read the frame the channel actually sends, and the
end-to-end test in `tests/test_agent.py` joins the two halves over one dispatch
rather than scripting the supervisor's answers, which is what catches a
disagreement about shape rather than about words.

**What criterion 6 measures, and the one word it needed.** Both integration
tests exist and both are the ticket's own sentences: one child runs
`http_request` and then `get_receipts` with the label it was handed and gets a
match; one runs `run_tool` and then `get_artifact` on each returned
`outputs[].label` and gets bytes. Each has a `refresh_packet` call between the
act and the read, and that is not a weakening of the criterion -- it is what
verdict A means. B would have put the value in the act tool's answer; A gives
the run a label and a way to resolve it, and the resolving is a call. The first
test asserts the `not_staged` answer before the refresh as well, so what is
measured is the change and not just the end state.

**Why this is not `resolved`.** One line in a file this work does not own.
`agent.Tooling` gained an optional `state: pg.Settings | None`, and the only
caller that builds a `Tooling` is `src/redkraken/execution.py:2254-2256`, which
passes `container`, `root` and `runtime` and would need `state=self.state`
beside them -- the same settings its own `_packet` at `:1955` already opens the
compile on. Until that keyword is added, every `refresh_packet` call in
production answers `unreachable_state` with the sentence saying this run was
started with no agent-scoped connection. The field is optional rather than
required precisely so that this is a refusal on one tool and not a run that
cannot start.

**Where this ticket was wrong.**

*The line numbers below `packet.py:590` are all six lines short.* `compile` is at
`:593` and not `:587`; `not_staged` at `:913` and `:999`, not `:907` and `:993`;
`no_such_artifact` at `:953`; `packet_bound` at `:972`; `_window` at `:987-1015`
with `range_beyond_excerpt` at `:1012`; `Reader.packet` at `:831-836`; the
`exec.tool_run` quotation at `:625-627`. The three the "What was measured"
section re-verified -- `SECTIONS` at `:43`, `RECORD_KINDS` at `:49`,
`DEFAULT_EXCERPT` at `:60` -- are all above the drift and are all correct, which
is how the drift is datable: something was inserted between `:60` and `:587`
after this section was written.

*Three other citations moved further.* `roster.py:596-599` is `:615-618`;
`agent.py:1207-1212` is `:1221-1226`; the ticket 94 excerpt in `_spend` is around
`_launch.py:973` rather than `:899-911`. Correct and unmoved:
`isolation.py:152-153`, `execution.py:1939-1978`, `tool.py:520-535`,
`tool.py:741-748`, `tool.py:790-804`, `proxy.py:850-882`, `README.md:204-205`,
and `_launch.py:399-467`.

*The dispatch had four arms and not three.* "Ticket 102 added a third arm to it
-- `propose_finding`" was true when document 31 measured it and was already
stale when this was written: ticket 98's `mint_callback` was the fourth, ticket
106's `rk2__name_transcripts` the fifth, and this one is the sixth. The argument
the sentence makes is unaffected and is the one this ticket relied on.

*"The one genuinely new cost" was one cost and one keyword.* The second
`pg.Settings` on `agent.Tooling` is exactly what the decision predicted. What it
did not predict is that the only thing that constructs a `Tooling` lives in a
different module, so the cost is a field plus a keyword at its one call site --
which is the whole of why this ticket spent a pass as `ready-for-human` rather
than `resolved`. The keyword has since landed; see the closing section.

*The arithmetic is correct.* `min(65536, 8192 * 4)` is 32,768 against the
158,222-byte `js_parse` answer, and `Limits().byte_ceiling` is asserted against
`REFRESH_BYTES` in `tests/test_packet.py` so that a later change to either is a
failing test rather than a silent one.

**Register rows removed.** Two, both measured gone rather than assumed.
`W5 tool_run: owed:107` closed because the gate reads label-shaped arguments off
READ-direction contracts and `refresh_packet` declares `tool_run_labels`.
`W4 tool_runs: owed:129` closed because the same contract declares it reads
`tool_runs`; the other three of ticket 129's four -- `tool_run_artifacts`,
`tool_run_inputs`, `tool_run_paths` -- are untouched, because a `tool_runs`
record is not its inputs or its paths. `tools/check_wiring.py` refuses a register
row whose gap no longer exists, so both had to go the moment the contract landed.

## Measured against a server, 2026-08-22

Everything above was measured against fake connections, and a fake connection
accepts a parameter no server will. Both of this ticket's statements were run
against a real schema before it was handed back, and one of them did not work.

**The defect: an array crossed as a Python list.** `_named_records` and
`_named_artifacts` passed `list(labels)` for the `= ANY($n)` parameter.
`pg._encode` writes every parameter that is not `bytes` with `str`, so what
reached the server was `['R7', 'R9']` and the answer was

    22P02: malformed array literal: "['R1', 'R2']"
    "[" must introduce explicitly-specified array dimensions.

Every `refresh_packet` call that named a single label would have failed this way
in production. `pg.quote_array` is the shape this client sends an array in --
`validation.py:371` and `integrity.py:147` already send theirs that way -- and
both statements now use it. The recorder in `tests/test_packet.py` decodes the
literal rather than accepting a list and refuses a parameter that is not a
string, so the shape is now measured rather than assumed; that is the change
that would have caught this.

**What was then measured, on rows rather than on an empty schema.** Against a
scratch database holding 32 Receipts, 20 `artifact_references` and 18 Tool runs,
as `rk2_state`, in a read-only transaction with one Program bound:

    107 records:   [('R1', 885), ('R5', 907)]
    107 artifact:  AF1 79eb8bfdd164c467 {"kind": "artifact", "label": "AF1", ...}
    107 artifact:  AF2 f0c1888dff5be5c3 {"kind": "artifact", "label": "AF2", ...}
    107 tool_run:  [('TR1', 897)]

So `v_records` answers a `tool_run` kind by label, `NAMED_ARTIFACTS` builds the
record and its digest, and the `tool_runs` section this ticket added to
`SECTIONS` has something real behind it.

Ticket 106's verb was exercised on the same rows and in the same session, as
`rk2_runtime`, because the two halves are one answer:

    106 R1   {"receipt_label": "R1", "request_artifact": null, "response_artifact": "AF1"}
    106 RZZ  {"receipt_label": null, "request_artifact": null, "response_artifact": null}

**Tests.** `tests.test_agent`, `tests.test_packet`, `tests.test_roster`,
`tests.test_isolation` and `tests.test_tool` are 397 tests, OK with 42 skipped.
`tests.test_database.CleanCreationTest`, `RuntimePrivilegeSurfaceTest`,
`MissionPacketTest` and `StateReadTest` are 51 tests, OK in 40.0s, which is where
ticket 106's migration and its `DO $$` assertions are applied from empty.

**Why this was still not `resolved` at the end of that pass.** `src/redkraken/execution.py`
lines 2254-2256 build the only `agent.Tooling` this system constructs and pass
`container`, `root` and `runtime`. Without `state=self.state` beside them --
`self.state` is the same `pg.Settings` that file's own `_packet` opens the
compile on at `:1955` -- `_Tools._refresh` answers `unreachable_state` for every
call in production, and the field is optional precisely so that this is a
refusal on one tool rather than a run that cannot start. That file was outside
this pass's ownership and nothing was written to it. It is one keyword.

**What this ticket could not pay, beyond that keyword.** There is no database
test for the refresh statements. The house pattern for a database-level
assertion is a `DO $$ ... $$;` block at the end of a migration and this ticket
has no migration, correctly: nothing here is executed that was not already
granted. What `tests/test_database.py` should assert once that file is free is
the shape this section measured by hand -- as `rk2_state`, with one Program
bound and a second Program's rows present, that `NAMED_RECORDS` for kind
`tool_run` and `NAMED_ARTIFACTS` each answer only the bound Program's labels and
answer nothing for a label the other Program holds. That is the one property the
fakes cannot check, because row level security is the thing being relied on.


## Closing, 2026-08-22

**The keyword landed.** `src/redkraken/execution.py` now builds its one
`agent.Tooling` with `state=self.state` beside `container`, `root` and
`runtime`. `Slice.state` is declared `pg.Settings` at `execution.py:943`, so the
value is always present at the one call site and the optional field is never
handed `None` by this path. `_Tools._refresh` therefore reaches `v_records` on
an agent-scoped connection in production rather than answering
`unreachable_state`.

That was the single unpaid item this ticket named, and it is paid. The database
test the pass could not write is not owed by this ticket: 107 ships no
migration, so there is no `DO $$` block for it to live beside, and the property
it would assert -- that `NAMED_RECORDS` and `NAMED_ARTIFACTS` answer only the
bound Program's labels because row level security says so -- belongs to the
`tests/test_database.py` state-read suite. It is recorded above rather than
carried forward as a blocker.
