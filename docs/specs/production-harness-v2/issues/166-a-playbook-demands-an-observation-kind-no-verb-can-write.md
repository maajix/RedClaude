# 166 — A Playbook demands an Observation kind no verb can write

**What to build:** Nothing yet. This ticket records a gap the synthetic vertical
run exposed and does not fix it. Thirty-three of the fifty Playbooks in the
corpus gate `supported` on an Observation kind that no runtime writer can put on
a hypothesis, so those Playbooks cannot be satisfied by any sequence of verbs
this tree serves.

**Blocked by:** nothing.

**Status:** claimed

**Touches:** `tests/test_database.py`, `tests/test_vertical.py`,
`docs/specs/production-harness-v2/TASKS.md`,
`docs/specs/production-harness-v2/issues/169-a-playbook-step-the-runtime-performs.md`.
Corrected after the build: the migration and
`src/redkraken/playbooks/webhooks/playbook.md` named at claim time turned out
to be work this ticket does not need.

**PRODUCES:** changed -- a `hypothesis_evidence` row carrying a kind
`close_test_replay` does not derive, written by `rk2_promote_hypotheses` out
of a `mcp__rk2__submit_mission_result` payload while the claim is still
`proposed`.

**CONSUMED BY:** `playbook_evidence_unmet` (`0032_playbooks.sql:509`), reading
`he.role` and `o.kind`, called by the trigger `a_playbook_evidence_guard`
(`:547-549`) on `INSERT INTO hypothesis_transitions`.

**CONSUMES:** `playbook_evidence` rows, written by the corpus migrations.

- [x] **The bar is real and it is enforced.** `enforce_playbook_evidence()`
      (`src/redkraken/migrations/0032_playbooks.sql:529`) fires
      `BEFORE INSERT ON hypothesis_transitions` (`:547-549`) and raises on the
      first row `playbook_evidence_unmet()` (`:509`) returns. That function
      counts `hypothesis_evidence` joined to `observations` and compares
      `o.kind` against `playbook_evidence.observation_kind` for the selected,
      undropped Playbook. A missing kind is not a warning; the transition
      raises.
- [x] **`playbooks/object-ownership/playbook.md` is the measured case.** Its
      `bb:evidence` line (`:14`) carries
      `{"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}`,
      seeded as `('supported', 'control', 'credential_effect', 'supports', 1)`
      at
      `src/redkraken/migrations/20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql:623`.
      The migration's own comment says why the row is there: "a refusal under
      the second Identity is only evidence of an enforced boundary if that
      Identity's session was working at the time" (`:614-617`). The reasoning is
      sound. The row is still unreachable.
- [x] **The replay path can write exactly two kinds.** `close_test_replay`
      derives an Observation's kind purely from the assertions that name the
      action -- `CASE WHEN EXISTS (... x ->> 'kind' IN ('status_differs',
      'body_differs') AND v_action.ordinal IN (...)) THEN
      'response_differential' ELSE 'response_invariant' END`
      (`src/redkraken/migrations/20260815T000000Z__a_test_runs_through_the_replay_lane.sql:1794-1801`,
      the decisive line at `:1800`), and the function is re-created identically
      at
      `src/redkraken/migrations/20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1063-1070`,
      the decisive line at `:1069`, which is the live definition (`:1016`). The
      Observation and the `hypothesis_evidence` edge are written together in the
      same loop (`20260815T000000Z...:1803` and `:1813`;
      `20260816T000000Z...:1072` and `:1082`), so the only kinds any replay can
      ever attach to a claim are `response_invariant` and
      `response_differential`.
- [x] **The other writer is shut by then.** `rk2_promote_hypotheses` is the only
      other function that writes `hypothesis_evidence`, and it refuses an
      evidence edge once the claim it converges on is past `proposed`:
      `IF v_status IS NOT NULL AND v_status <> 'proposed' THEN v_reason :=
      'claim_past_proposed'`
      (`src/redkraken/migrations/20261017T000000Z__an_evidence_edge_is_read_where_the_child_wrote_it.sql:417-418`,
      live at
      `src/redkraken/migrations/20261025T000000Z__a_refusal_names_its_cause_and_the_words_it_would_have_taken.sql:454-455`).
      A claim with a Test running is `testing`, not `proposed`. So by the time
      the replay is the thing moving the claim to `supported`, the proposal path
      can no longer add the row the Playbook is waiting for.
- [x] **Consequence: 33 of 50 Playbooks are unsatisfiable, measured.** Reading
      every `bb:evidence` line under `src/redkraken/playbooks/*/playbook.md`:
      33 name at least one of the six kinds no runtime writer produces --
      `credential_effect` (17 Playbooks), `content_match` (9), `state_change`
      (6), `header_policy_observed` (3), `reflected_input` (3),
      `callback_interaction` (1). Widening the test from those six to "any kind
      the replay path cannot write" adds four more and makes it **37 of 50**:
      `command-directory-injection` (`timing_differential`),
      `exceptional-conditions` and `structured-injection` (`error_detail`), and
      `http-desync` (`transport_parameters_observed`). Only 13 Playbooks --
      `agentic-ai`, `client-side-path-traversal`, `deployment`,
      `deserialization`, `file-resolution`, `file-upload`, `nosql-injection`,
      `orm`, `request-integrity`, `request-parsing`, `sql-injection`,
      `ssrf-url-routing`, `web-cache` -- ask only for the two kinds a replay can
      produce. `callback_interaction` is worth separating from the other five:
      `record_callback_interaction` does write that Observation
      (`src/redkraken/migrations/20261001T000000Z__a_control_arrival_is_what_makes_silence_a_finding.sql:543-555`
      is the live one), but it writes no `hypothesis_evidence` edge, so the kind
      exists and still cannot count towards a bar.
- [x] **Consequence for ticket 103's own evidence, stated plainly.**
      `tests/test_vertical.py`'s walk has exactly one arranged row.
      `the_control_the_playbook_asks_for()` (`:272-302`) writes the
      `credential_effect` Observation and its `control` evidence edge as owner,
      grounded in the recon lap's real Receipt. Everything downstream of that
      row is earned: the Test, the replay, the `supported` claim, the Finding,
      the impact demonstration, the severity, the pivot stamp, the chain and the
      report are all read off rows the walk itself wrote through served verbs.
      The one row is arranged because this ticket's gap makes it impossible to
      earn, not because the walk took a shortcut anywhere else.
- [x] **Two candidate fixes, neither chosen here.** Either `close_test_replay`
      learns to class a control action as `credential_effect` -- the information
      is present, since the plan already gives each action a role and the
      control leg is the one that proves the Identity was working -- or
      `enforce_playbook_evidence` stops demanding a kind no runtime writer can
      produce, by narrowing the corpus's `playbook_evidence` rows to kinds a
      verb can reach. The first buys one kind and leaves the other five; the
      second is 33 to 37 rows of corpus edit and loses the distinction the
      `control` row was written to make. Deciding between them is the ticket's
      first job.

## Why

The synthetic vertical run of Arbeitsblock 1 is the first walk in this tree that
had to satisfy a Playbook's `supported` bar with rows a verb produced. It could
not. Ticket 164 measured that fifty Playbooks had never been selected and fixed
the trigger stage, so a Playbook is now chosen; this is the next stage failing
for the same class of reason, one step later. A Playbook that is selected and
then cannot be satisfied is worse than one that is never selected, because the
selection is what the Task is dispatched under.

`enforce_playbook_evidence` is named to sort before
`enforce_hypothesis_transition` on purpose (`0032_playbooks.sql:541-546`): the
Playbook rule is meant to be strictly stronger than `transition_rules`, and a
conjunction of two rules is only useful if both are reachable. Today the second
one is a wall for two thirds of the corpus.

## Notes

Not a regression. The bar has been unreachable since `0032` and the corpus rows
were seeded between `20260823` and `20260902`; nothing selected a Playbook until
ticket 164, so nothing had ever run into it.

Not ticket 145's problem. 145 is about a kind being offered a provenance record
its `allowed_provenance` does not admit. Every kind named here is in the
vocabulary and has an `allowed_provenance` some writer could satisfy
(`0018_vocabularies.sql:219-236`, and `content_match` takes `{tool_run}` rather
than a Receipt); what is missing is a verb that writes the row and its evidence
edge, not a provenance the row could carry.

## Comments

**2026-08-24 -- the second fix, taken for five Playbooks and no others.**

Arbeitsblock 3 grades five High-Yield pairs, and reading this ticket against them
said every one of the five was unsatisfiable: `attack-surface` wanted
`content_match`, `object-ownership` `credential_effect`, `browser-script`
`reflected_input`, `cookies` `header_policy_observed` and `credential_effect`,
`payment-workflows` `state_change`. A 1650-run campaign against those five would
have returned five `fail` verdicts and measured this ticket rather than the
Playbooks -- `playbook_test_verdict` reads `discriminating_tp`, which counts
claims at `status = 'supported'`, which is the transition
`enforce_playbook_evidence` raises on.

So fix two is taken for the five: `20261106T000000Z` narrows their fifteen
`playbook_evidence` rows to `response_invariant` and `response_differential`, the
two kinds `close_test_replay` writes, and re-freezes the five documents. The
`control` role is untouched in all five, so the rule this corpus exists for --
no claim from a single reading -- still holds.

What it costs is stated in the migration and in
`tests/test_playbook.py`'s pinned case, which moved with it: a control row
naming `credential_effect` said the second session was working, and one naming
`response_invariant` says the control leg did not differ. The second is weaker.

**This ticket stays open**, and what is left is the larger half. Twenty-eight to
thirty-two Playbooks still carry an unreachable bar, and fix one -- teaching
`close_test_replay` to class a control leg as `credential_effect` -- is still the
better answer for the seventeen that want that kind, because it puts the
distinction back rather than dropping it. Deciding it for the whole corpus was
not this block's to do; deciding it for five Playbooks it was about to spend 330
million budget units grading was.

**2026-08-24 -- the narrowing was wrong in detail, and the detail is the ticket.**

`20261106T000000Z` put `response_invariant` on the `control` row of four of the
five. `tests.test_vertical` refused it:

    playbook playbooks/object-ownership/playbook.md requires 1 x
    (role=control, kind=response_invariant) for supported, found 0

The `CASE` this ticket quotes above was read one clause short.
`v_action.ordinal IN ((x ->> 'action')::numeric::integer, (x ->> 'against')::numeric::integer)`
matches an assertion's `against` as well as its `action`, so a comparison marks
**both** of its legs `response_differential`. `response_invariant` is written
only for an action that no `status_differs` or `body_differs` assertion names at
all. A control leg that a differential is measured against is never invariant.

`20261107T000000Z` corrects the five to `response_differential` on every row,
which is the shape `client-side-path-traversal` and `web-cache` already ship,
and re-freezes the five documents again.

**A second wall, found on the way, and larger than the first.** The kind is
derived from the Test *specification*, not from the outcome, so one specification
writes the same kinds whether its assertions hold or fail. Eighteen Playbooks --
`agentic-ai`, `api`, `client-side-path-traversal`, `deployment`,
`deserialization`, `file-resolution`, `file-upload`, `graphql`, `grpc`,
`nosql-injection`, `orm`, `realtime`, `request-integrity`, `request-parsing`,
`sql-injection`, `ssrf-url-routing`, `web-cache`, `workload-identities` -- name
`response_invariant` and `response_differential` on the *same role* across their
two outcomes. Each of those asks one specification to write two different kinds
for one action, so exactly one of `supported` and `refuted` is reachable and the
other raises. That set contains all thirteen this ticket called satisfiable, so
the honest count is that **no Playbook in the corpus could reach both of its
outcomes**, and the five graded ones are the only five that now can.

Still this ticket's, still open: the twenty-five Playbooks outside the five, and
the choice between teaching `close_test_replay` to class a control leg and
finishing the corpus edit.

**2026-09-02 -- the measurement above is stale, re-taken before building.**

Read against the corpus as it stands after ticket 101's rewrite and
`20261219T000000Z__the_corpus_is_rewritten_and_refrozen.sql`. Three of this
ticket's counts moved, and one of its two walls is gone.

```
playbooks carrying bb:evidence                          51
naming a kind close_test_replay cannot derive           26
one role carrying two kinds across its two outcomes      1   webhooks
```

The 33-of-50 and 37-of-50 counts above were taken before the rewrite. The
second wall -- eighteen Playbooks asking one Test specification to write two
kinds for one role -- is down to `webhooks` alone, whose `variant` role names
`callback_interaction` on `supported` and `response_differential` on
`refuted`. Every other Playbook now carries one kind per role.

**The first wall is probably not a wall, and nothing has ever run it.** This
ticket's fourth measured line says the proposal path "is shut by then", and
that is true only of an edge filed *after* the claim moves. It is not true of
an edge filed with the proposal:

- `mcp__rk2__submit_mission_result` (`src/redkraken/roster.py:1478-1500`)
  takes `observations`, whose `kind` is the whole `OBSERVATION_KINDS` enum,
  and `evidence`, carrying `role` and `polarity`, in one payload.
- `rk2_promote_hypotheses` writes both while the claim is `proposed`; the
  refusal at
  `20261025T000000Z__a_refusal_names_its_cause_and_the_words_it_would_have_taken.sql:454`
  fires only once the claim is past it, and the edge insert is at `:530`.
- Nothing in the corpus deletes from `hypothesis_evidence`:
  `grep -rn 'DELETE FROM hypothesis_evidence' src/` is empty.
- `playbook_evidence_unmet` (`0032_playbooks.sql:509`) counts rows at
  transition time, so a row written at proposal time is still counted.
- `credential_effect` allows `{receipt}` and `content_match` allows
  `{tool_run}` (`0018_vocabularies.sql:219-236`); `promote_proposal` writes
  `provenance_kind` from the element's own Receipt or Tool run
  (`20261008T000000Z__a_suggested_task_becomes_a_task_or_a_drop.sql:1116`).

Ticket 101's own rewrite already reasons this way:
`browser-storage/playbook.md:12` says its three agent-filed legs are "filed
with the proposal while the claim is still proposed".

All of that is read from source and none of it has been run. The first thing
this ticket builds is the test that runs it, and both outcomes are results:
if the transition lands, the wall is stale and what is left is `webhooks`; if
`enforce_playbook_evidence` raises, the wall is real, its message is the
`Red:` line, and the choice between this ticket's two candidate fixes becomes
live and goes through `hold-the-line`.

**WALL** -- this effort's tickets live at
`docs/specs/production-harness-v2/issues/`, not at `docs/issues/<effort>/`
where the plumbline flow expects them, and no ticket of the 231 carries a
`Touches` / `PRODUCES` / `CONSUMED BY` line, a `live-inputs.md` or a
`## Verify command` in the spec.
**PRICE** -- moving the effort onto that layout is 231 ticket files plus every
cross-reference in them, for one ticket's benefit.
**PURPOSE** -- those paths serve the plugin's commit guard and its frontier
scan. The guard greps `docs/issues/` literally, so it does not fire in this
repository at all.
**RULE** -- run the flow against this repository's paths. The seam fields are
filed on this ticket only, `live-inputs.md` is not created, and the seam check
runs with no replay block. The commit guard's discipline is manual here.

## Seam check, 2026-09-02

**WROTE** -- two `hypothesis_evidence` rows, `role='control'` and
`role='variant'`, both `polarity='supports'`, both citing an Observation of
kind `credential_effect`, both carrying a non-null `proposal_id`. Written by
`rk2_promote_hypotheses` (live at
`20261025T000000Z__a_refusal_names_its_cause_and_the_words_it_would_have_taken.sql:530`)
out of the payload `HypothesisPromotionTest.agent_filed()` sends through
`proposal.stage` and `promote_proposal`, in the same promotion that mints the
claim.

**READ** -- `playbook_evidence_unmet($1::uuid, 'supported')`
(`0032_playbooks.sql:509`) returns the empty set for that claim under
`playbooks/authentication/playbook.md`, whose bar names `credential_effect` for
both roles. That is the function the trigger `a_playbook_evidence_guard`
(`:547-549`) calls before it admits the transition, so the empty set is the
transition being admitted.

**Far end, read for real** -- `tests.test_vertical` walks one Program from a
recon Receipt to a composed report and asserts the `supported` transition at
`:685`. It now does that with **no arranged row at all**: the owner-written
`credential_effect` Observation and its `control` edge are removed, and
`20261107T000000Z` had already moved `object-ownership`'s bar onto
`response_differential`, which the replay writes for both legs of a comparison.
`Ran 3 tests / OK`.

No `NOBODY`. Both ends are in this repository and both are named above.

**Redemption grep** --
`grep -rn 'ticket 166' docs/specs/production-harness-v2/` returns no hit in a
seam-field head. The live prose hits were two and both are corrected in this
commit: `TASKS.md` caveat (a), which described the arranged row this ticket
removed, and ticket 169's forward note, which carried the stale 33-of-50 count
into a `ready-for-agent` criterion set. Hits in `101` are inside a resolved
ticket's history and stay. Hits in `20261106T000000Z` and `20261107T000000Z`
are inside applied migrations and are immutable.

## Build findings, 2026-09-02

- [build] **The ticket's own wall does not exist.** `blocker` by severity if it
  were true, and it is not: measured. Verdict **NOW** -- this is the ticket's
  first job and the answer is the resolution below, not a new ticket. Neither
  candidate fix is needed. `close_test_replay` is not taught a new kind and no
  `playbook_evidence` row is narrowed.
- [build] **`callback_interaction` is reachable and it is not proved here.**
  `required`. Its `allowed_provenance` is `{callback}`
  (`20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:349`), so no
  proposal can mint the Observation -- only `record_callback_interaction` can,
  and that verb writes no evidence edge. What closes it is that an edge may
  cite an **existing** Observation by label rather than by `ref`, which the
  fixture's own `claim()` payload already does, and the only guard on an edge's
  Observation is `enforce_evidential_kind` (`0018_vocabularies.sql:448-464`),
  which reads `is_evidential` and never provenance. `callback_interaction` is
  `is_evidential = true`. So `webhooks`, whose `variant` role names
  `callback_interaction` on `supported` and `response_differential` on
  `refuted`, has no conflict: the two kinds come from two writers, not from one
  Test specification. Verdict **CRITERION** -- read from source, not run.
  Recorded as owed below rather than fixed, because proving it needs a callback
  channel fixture that lives in `CallbackPublisherTest`, not in this seam.

- [x] **A callback arrival can be cited as evidence, read but not run.** The
      mechanism is the finding above and its evidence is source. The run that
      would close it is one edge citing a `record_callback_interaction`
      Observation by label, and it belongs in a callback fixture. Ticked
      because the CRITERION verdict is the record, not a promise.

## Resolution, 2026-09-02

The bar this ticket was opened against was never unreachable, and nothing had
ever run it. An evidence edge filed with the proposal that mints the claim --
while the claim is still `proposed`, so `rk2_promote_hypotheses`'s
`claim_past_proposed` refusal does not apply -- is still a row when
`enforce_playbook_evidence` counts rows at the `supported` transition, because
nothing in the corpus deletes from `hypothesis_evidence`. The ticket read
"the other writer is shut by then" as shutting the kind out; it shuts out only
*nachreichen*, an edge added after the claim moves. `mcp__rk2__submit_mission_result`
(`roster.py:1478-1500`) serves the whole `OBSERVATION_KINDS` enum and an
`evidence` list in one payload, so every kind in the vocabulary is reachable
and only the writer differs.

The seam is guarded by
`tests.test_database.HypothesisPromotionTest.test_an_agent_filed_kind_counts_towards_the_playbook_bar`,
which puts one claim carrying two `credential_effect` edges under
`playbooks/authentication/playbook.md` and asserts the unmet set is empty, and
by `test_the_edge_the_bar_counted_is_the_one_the_promotion_wrote`, which reads
the producer's two rows back with their `proposal_id`. The fixture opens a
fourth Program for it, the way ticket 155 has its own.

What this changes in the tree is one deletion: `tests/test_vertical.py`'s
`the_control_the_playbook_asks_for()` is gone, and with it the one arranged row
the whole vertical walk had. No migration, no corpus edit, no change to
`close_test_replay`, no change to `enforce_playbook_evidence`. The
`Touches` line filed at claim time named a migration and
`src/redkraken/playbooks/webhooks/playbook.md`; both turned out to be work this
ticket does not need, and the line is corrected above.

**Red:** none -- born green. The test measures a path that already worked and
had never been run, which is the ticket's own subject; both outcomes were
recorded as results before it ran.
**Mutated:** `CREDENTIAL_PLAYBOOK` from `playbooks/authentication/playbook.md`
to `playbooks/logging/playbook.md`, whose bar names `content_match` ->
`AssertionError: Lists differ: [] != [('control', 'content_match', 1, 0), ('variant', 'content_match', 1, 0)]`
**Forward references left standing:** none.

**Wrong in the ticket, named:** the fourth measured line ("The other writer is
shut by then") is false as a reachability claim. The fifth ("33 of 50 ...
37 of 50") is stale: 26 of 51 name a kind the replay does not derive, and that
is now a statement about which writer files the row rather than about whether
one exists. The seventh ("Two candidate fixes, neither chosen here") is
answered by taking neither.


## Bar, 2026-09-02

Line 1 -- every criterion ticked:

```
$ grep -c '^- \[ \]' <this ticket>
0
```

Line 2 -- the seam test read by name. This effort has no `## Verify command`
in its spec; the priced wall above rules that `docs/agents/testing.md` tier 1
stands in, and this is its database form.

```
$ RK_TEST_SUPERUSER_URL=... RK_TEST_DATABASE=rk2_t166 \
    uv run python -m unittest -v tests.test_database.HypothesisPromotionTest
test_an_agent_filed_kind_counts_towards_the_playbook_bar ... ok
test_the_edge_the_bar_counted_is_the_one_the_promotion_wrote ... ok
… (39 further test lines, all ok)
Ran 41 tests in 32.393s
OK
```

Line 3 -- forward references this ticket redeemed. Hits in a seam-field head:

```
$ grep -rn 'ticket 166' docs/specs/production-harness-v2/ \
    | grep -cE '\*\*CONSUMED BY:\*\*|\*\*CONSUMES:\*\*|deferred to'
0
```

Line 4 -- existing tests still pass, nothing skipped, deleted or weakened. The
far end ran whole:

```
$ uv run python -m unittest tests.test_vertical
Ran 3 tests in 26.218s
OK
```

One method was deleted, `the_control_the_playbook_asks_for()`, and it is an
arrangement rather than a test: it asserted nothing and its return value was
read by nothing. No `.skip` was added, no test file removed, no assertion
dropped. Lowering-move 2 does not apply -- the walk's own `supported`
assertion at `tests/test_vertical.py:685` is unchanged and still passes.

Line 5 -- the diff is what the ticket asked for:

```
$ git status --short --untracked-files=all
 M docs/specs/production-harness-v2/TASKS.md
 M docs/specs/production-harness-v2/issues/166-a-playbook-demands-an-observation-kind-no-verb-can-write.md
 M docs/specs/production-harness-v2/issues/169-a-playbook-step-the-runtime-performs.md
 M tests/test_database.py
 M tests/test_vertical.py
```

Four files. Two are the ticket's corrected `Touches`; two are the stale
forward claims §5's redemption grep found, both corrected in this commit.

Line 6 -- resolution present, bar present, no handoff:

```
$ grep -c '^## Resolution' <this ticket>
1
$ grep -c '^## Handoff' <this ticket>
0
```

**Judgement, red and mutated.** Born green, recorded as such on the `Red:`
line with the reason, and the `Mutated:` line carries the assertion the
broken literal produced. Both were watched in this session.

**Judgement, no unexplained NOBODY.** Both ends of the seam are named in
`## Seam check` and both are in this repository.

**Judgement, the live run reached this ticket's case.** It did: the case is
"an agent-filed edge counts at the bar", and `tests.test_vertical` now
reaches `supported` with no arranged row, which is the same claim measured
from the other side. There is no `live-inputs.md` in this effort; the priced
wall says why.

**Judgement, no injected double.** None was injected. The fixture drives
`proposal.stage` and `promote_proposal` against a real PostgreSQL 18
database.
