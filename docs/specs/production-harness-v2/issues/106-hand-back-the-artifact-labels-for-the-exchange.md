# 106 — Hand back the Artifact labels for the exchange the door just filed

**What to build:** The Artifact labels for a request and its response, returned
from `mcp__rk2__http_request` beside the Receipt label, so that a run can name
the bytes it just fetched.

**Blocked by:** nothing. It is independent of ticket 94, which hands back the
response headers out of the same answer, and the two touch the same return
statement.

**Status:** resolved

- [x] The label already exists at the moment the Receipt does, and the ticket
      rests on that rather than minting anything.
      `hold_receipt_transcripts()`
      (`src/redkraken/migrations/20260811T220000Z__a_stored_transcript_is_held_by_name.sql:45-68`)
      is an `AFTER INSERT` trigger on `receipts`, enabled `ALWAYS` at `:83`,
      that writes one `artifact_references` row per agent-visible transcript the
      Receipt names -- request and response both -- and the `AF` label comes off
      that row. So an exchange that produced a Receipt label has produced two
      Artifact labels in the same transaction, and nothing hands them over.
- [x] `_launch._spend` returns them. Today it returns eight keys and none is a
      label but `receipt`: `served`, `status`, `receipt`, `decision`, `detail`,
      `byte_size`, `truncated`, `body` (`src/redkraken/_launch.py`, in `_spend`,
      declared at `:680` as of commit `cf70c5f`; the file is under concurrent
      edit for ticket 94, so the symbol is the reference and the line is not).
- [x] The Contract needs no change and the ticket says so.
      `mcp__rk2__http_request` already declares
      `writes=("receipts", "artifacts", "artifact_refs")`
      (`src/redkraken/roster.py:750`), which is exactly what
      `register_proxy_artifacts` (`0040_receipt_contract.sql:13-36`) and the
      transcript trigger write between them. What changes is the answer, not
      the declaration.
- [x] The two labels are distinguishable as request and response in the answer.
      `compare_responses` takes `first` and `second` and the registry says why
      order is part of the call
      (`20260922T030000Z__a_skill_script_is_a_program_the_harness_ships.sql:457-467`:
      "`only_in_first` is a different claim from `only_in_second`"), so an
      answer that returned an unordered pair would push that decision onto a
      model.
- [x] Only agent-visible bytes get a label, and the ticket does not widen that.
      The trigger's `WHERE` clause admits a hash only where the Artifact is
      `agent_visible`, unencrypted and unpurged, and the migration says why at
      `:40-43`: "What it must not do is name a wire hash: those are the sealed,
      credential-bearing halves, and a label pointing at one would be exactly
      the reachability `check_wire_artifact_secrecy` rule 3 exists to refuse."
- [x] The label is returned and is not yet resolvable in the same run, and the
      ticket states that plainly rather than implying otherwise. Ticket 107 is
      what makes `mcp__rk2__get_artifact` answer for it; this ticket is what
      makes there be something to ask about.

## Why

`docs/research/wiring/22-corpus-instruction-wiring.md` section 6 ranks this
first of the three highest-leverage surface repairs: "Return an `artifact_label`
from `http_request` -- unblocks the evidence step of 39 playbooks and all 5
partials." Thirty-nine of the fifty shipped Playbooks name `compare-responses`
in the body and are told to difference two answers the run just fetched, and
neither label is obtainable; the five Playbooks the same report grades `partial`
rather than `not runnable` all break at this exact step and at no other.

`docs/research/wiring/21-agent-surface-wiring.md` section 5.2 states the same
finding from the tool side: "`net.request` and `exec.tool_run` are designed to
compose -- `jq`, `js_parse`, `js_map`, `js_routes` and both skill scripts all
take an `artifact`-kind argument -- and an agent that has just fetched a
JavaScript bundle has no label to hand to `js_parse`."

The Contract's own comment at `roster.py:648-656` explains the narrowing it does
make and, read today, describes the gap exactly: "no label lists the ones this
packet reached, which is the only way a child learns a label exists".

## What was built

An exchange now answers `request_artifact` and `response_artifact` beside
`receipt`, and nothing was minted to make that true.

**The one thing this ticket did not know about itself.** Criterion 2 says
`_launch._spend` returns them and stops there, and there is a step missing from
that sentence: `_launch` runs *inside the container*. The module's own docstring
says so at `src/redkraken/_launch.py:8-10` -- "This runs as a child process ...
inside the container `redkraken.isolation` verifies" -- and `packet.py:9-13`
says what follows from it: "there is no route to PostgreSQL and no route to the
Artifact store: a handler inside the container cannot query anything". The
labels the trigger wrote are rows. The child cannot read a row. And the door's
answer carries no second label to read them out of: `proxy.Answer`
(`src/redkraken/proxy.py:3684-3706`) holds `status`, `body`, `receipt`,
`decision`, `detail` and `headers`, and `_answered` at `:3709-3746` reads
`receipt` out of one header and there is no other.

So the labels come back the way a tool run does: the child asks the side holding
a connection. That is the shape ticket 102 and ticket 98 already built, minus
the tool -- because no model asks for this. It completes the answer to a call
the model already made.

**What changed.**

`receipt_transcript_labels(text)`
(`src/redkraken/migrations/20261002T000000Z__an_exchange_names_the_transcripts_it_filed.sql`)
resolves one Receipt label to the two Artifact labels beside it. It is a verb
and not a query in the supervisor for one reason, which is the reason criterion 1
is worth what it says: the rows are already there, so the only judgement left is
*whose* rows, and `rk2_runtime`'s row level security is `USING (true)` on every
Program-scoped table (`0022_hooks_and_receipts.sql:695-697`). `R7` exists under
most Programs. The predicate has to be `rk2_program_required()`, and written in
Python it would be a predicate a later caller could leave out.

`agent._Tools` grew its fifth arm and its first non-tool one
(`src/redkraken/agent.py`). `agent.NAME_TRANSCRIPTS` is deliberately not spelled
`mcp__rk2__*` and deliberately not in `roster.CONTRACTS`: that shape is what
`agent.SERVED` and the startup assertion measure against the roster, and a verb
in it that no launch builds would be a tool nobody serves.

`_launch.Transcripts` asks, and `_spend` merges. Two keys and never a null: a
run with no supervisor, a blocked exchange whose Receipt names no transcript,
and a database that could not be reached all produce the same null, and a model
cannot tell them apart from the value. It can tell that there is no label. So
the answer carries no key.

**Criterion 6, and what it will cost ticket 107.** The tool's own description now
says the label is not resolvable by the read tools -- "the read tools answer from
the packet this run was started with, and a label minted after that will not be
in it" (`_launch.DESCRIPTIONS["http_request"]`). That sentence is true today and
is ticket 107's to amend, not to delete.

**Two labels, not one.** Criterion 4 is met by two named keys rather than an
ordered pair, and it is met deliberately, because ticket 107's decision section
names "106 lands one Artifact label per exchange" as the one thing that would
overturn its verdict. It landed two. The reason is `compare_responses`
(`20260922T030000Z__a_skill_script_is_a_program_the_harness_ships.sql:457-462`):
"`only_in_first` is a different claim from `only_in_second`", so the order is
part of the call, and a run differencing a request against a response needs to
know which it is holding.

**Where the ticket was wrong, with evidence.**

- Criterion 2 says `_spend` "returns eight keys". It returns ten in this tree:
  `served`, `status`, `receipt`, `decision`, `detail`, `byte_size`, `truncated`,
  `headers`, `headers_truncated`, `body`. Ticket 94 landed the two header keys
  while this ticket was open, which is the concurrency the criterion itself
  warned about. The claim the criterion actually rests on -- that none of them
  is a label but `receipt` -- was true and is now false in exactly the way this
  ticket intended.
- Criterion 3 cites `roster.py:750` for the `writes` tuple. It is at
  `roster.py:876` in this tree; ticket 97 added 129 lines to that file. The
  tuple itself is unchanged and the criterion holds.
- Criterion 1's `hold_receipt_transcripts()` is at `:46-68`, not `:45-68`. Every
  other line in the criterion is exact, including `:83` for the `ENABLE ALWAYS`
  and `:40-43` for the wire-hash rule.

**A correction made while ticket 107 was built.** The supervisor's arm read
`call.get("arguments")` and `Transcripts.names` sent the Receipt label beside the
verb, because that is what `Channel.call` writes: `{**arguments, "verb": verb}`,
with no envelope. The two halves were tested apart and each was right on its own,
so the pair was wrong and nothing said so. The arm now reads the frame it is
handed, and `tests/test_agent.py` joins the two halves over one dispatch rather
than scripting the supervisor's answers. The same disagreement is still live in
`_Tools._propose` and `_Tools._callback`, which are tickets 102 and 98 and are
not this ticket's to fix; it is written down here because this is where it was
found.

**What was left, and why this ticket was not `resolved` when it was written.**

The work is built, tested and green. What it cannot do from inside its own
ownership is retire the twenty register rows that record its absence.
`tools/check_wiring.py:1636-1655` emits `W10 <slug> fetch-then-analyse` from a
premise written as a constant -- "An exchange hands back a Receipt label and no
Artifact label" -- and the condition it fires on is `consuming and
"mcp__rk2__http_request" in tokens`, which reads the Playbook corpus and the
tool registry and never reads `_spend`'s answer. So the gap is still measured
after the gap is closed. Measured, not assumed:

    STILL-FOUND W10 api fetch-then-analyse owed:106
    ... twenty rows, every one of them ...

Deleting the rows without changing the reading produces twenty `unregistered:`
errors; marking this ticket `resolved` with the rows in place produces twenty
`names owed:106, which is resolved, and the gap is still here` errors. The fix
is one condition in a gate this ticket was not given write access to, and the
honest status until somebody makes it is `ready-for-human`.

## The gate was made to read it, 2026-08-22

The one thing the section above says was left. `tools/check_wiring.py` now reads
`_spend`'s answer where it used to carry a sentence about it, and the twenty
rows that recorded the gap are gone because the gap is.

**What the reading is.** `answers(tree, "_spend")` takes the keys of the dict
that function hands back, following one level of `**merged()` because that is
how this package writes a key that is only sometimes there -- `_transcripts` is
a dict comprehension over `("request_artifact", "response_artifact")`, merged
into the answer, and a reading that stopped at the `**` would have scored
exactly the two keys this ticket added as absent. `Surface.exchange` carries
them, `ARTIFACT_KEY` says what an Artifact label looks like as a key of an
answer, and the fetch-then-analyse arm fires only while no such key is there.

It is narrow on purpose and the file says why beside `carried`, which is the
generous reading directly above it. `carried` reports a loss, so a generous
reading makes it hard to argue with; this one reports that something *is* handed
over, and a name found in a comment or in a tool description would close a gap
that is still open. So it reads keys, not mentions.

**Measured both ways, on one tree at a time.** In a `git archive HEAD` tree
carrying only this ticket's files, the new reading finds `request_artifact` and
`response_artifact` and reports **0** fetch-then-analyse gaps. Put HEAD's own
`_launch.py` back into that same tree, changing nothing else, and the same
reading finds no Artifact key and reports **20** -- `api`, `api-authorization`,
`attack-surface` and the seventeen others, each naming `compare_responses`, `jq`
or whichever `artifact`-taking program its body instructs. Run as the gate
rather than as a function, that tree fails with twenty `unregistered:` lines. So
the check did not become weaker: it reports the same twenty bodies whenever the
answer stops naming the bytes, and it stops reporting them when the answer names
them.

**What was measured, and the numbers.** On a `git archive` of `f0a4c35`
carrying only this ticket's files, because the shared worktree holds three other
tickets in flight and a failure measured there belongs to whoever is holding it.

    W10 corpus instructions      1 owed   corpus bodies 56  tool mentions 35  roles derived 55
    register                    65 rows   tickets 12  findings 65  distinct 65

W10 owed 21 rows before and owes 1 after, which is `browser-evidence` and is
ticket 99's. All four gates are green on that tree: `check_audit` rc=0,
`check_wiring` rc=0, `check_baseline` rc=0, `check_coverage` rc=0.

`tests.test_agent`, `tests.test_packet`, `tests.test_roster`,
`tests.test_isolation` and `tests.test_tool` -- the last two being where
`_launch` is exercised from the other side -- are 397 tests, OK with 42 skipped.
`tests.test_wiring`, which is this gate's own suite, is 17 tests, OK in 33.8s.

**What this ticket could not pay.** `tests/test_audit.py:76` freezes the audit
report as a literal and is already stale at `f0a4c35`: it says
`tickets 136  resolved 111` and that commit measures `138  resolved 112`, so the
test is red before this ticket touches anything. Resolving this one makes it
`113`. The file belongs to no one ticket -- every ticket resolved in this tree
moves the same line -- so it is refreshed once, by re-measuring rather than by
relaxing:

    PYTHONPATH=$PWD python3 -s -c "import tools.check_audit as c; print(c.check())"
