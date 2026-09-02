# 166 — A Playbook demands an Observation kind no verb can write

**What to build:** Nothing yet -- as cut, and **superseded 2026-09-02; read
`## Resolution` first.** The gap this ticket was opened on does not exist in the
form stated here. The corpus does not hold thirty-three of fifty Playbooks
gating `supported` on an Observation kind no runtime writer can put on a
hypothesis: re-measured it is 26 of 51 naming a kind `close_test_replay` cannot
*derive*, and each of those is reachable through an evidence edge an agent files
with the proposal that mints the claim. Exactly one bar in the corpus is
genuinely unreachable, for a reason unrelated to the writer, and it is now
ticket 233.

**Blocked by:** nothing.

**Status:** resolved

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

**CONSUMES:** `playbook_evidence` rows for
`playbooks/authentication/playbook.md`, written by
`src/redkraken/migrations/20261219T000000Z__the_corpus_is_rewritten_and_refrozen.sql:123-128`
(deleted at `:39`, re-inserted at `:94`), which is the last writer of that
path's rows and so the definition the trigger reads today.

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
edge, not a provenance the row could carry. One correction from the review
pass: that range does not contain `callback_interaction`, which is added at
`20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:349` with
`{callback}` alone, and the migration's own comment says the point is "so an
agent cannot file a Receipt under it and inherit the weight of an out-of-band
confirmation". For that one kind the sentence above is false, and the `## Build
findings` entry below is where it is worked out.

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
(`:547-549`) calls before it admits the transition.

**Corrected by the review pass, 2026-09-02.** "So the empty set is the
transition being admitted" was inference across a hop, and it is now run.
`playbook_evidence_unmet` has a second on-path reader,
`hypothesis_transition_refusal`
(`20261112T000000Z__the_refusal_preview_asks_both_halves_of_the_bar.sql:104`),
which is the function `close_test_replay` asks *instead of* attempting the
transition and which ticket 182 made ask the Playbook conjunct first. That is
the skipped grep hit this report should have recorded.
`test_the_gate_the_runtime_is_handed_does_not_name_the_playbook` now reads it
for the agent-filed claim and gets back
`transition testing -> supported requires a tool receipt` -- the *base* rule,
named, with no Playbook in the sentence. So the Playbook half admits these
edges at the real gate. The whole `supported` insert is still not reachable in
this fixture, and deliberately: `transition_rules`
(`0007_epistemics.sql:126`) wants a test-linked receipt and two rows in roles
`baseline,variant`, and this payload files one `variant`. The bar is a
conjunction of two triggers and only one of them was ever this ticket's
subject.

**Far end, read for real** -- the far end of *this* seam is
`enforce_playbook_evidence` admitting the insert, and it is read by the gate
test named above. `tests.test_vertical` is a second, weaker reading and the
review pass corrected the claim that it stood in for the first: it walks one
Program from a recon Receipt to a composed report and asserts the `supported`
transition at `:685`, but that transition is met by the `response_differential`
rows the replay writes, with no agent-filed edge and no `credential_effect`
anywhere in the walk. What it demonstrates is that the deletion below was safe,
not that an agent-filed kind counts. It now runs with **no arranged row at
all**: the owner-written `credential_effect` Observation and its `control` edge
are removed, and `object-ownership`'s bar had already moved onto
`response_differential` -- by `20261107T000000Z`, then deleted and re-inserted
with every other Playbook's rows by
`20261219T000000Z__the_corpus_is_rewritten_and_refrozen.sql:285-290`, which is
the writer the trigger reads today. `Ran 3 tests / OK`.

No `NOBODY`. Both ends are in this repository and both are named above.

**Redemption grep** --
`grep -rn 'ticket 166' docs/specs/production-harness-v2/` returns no hit in a
seam-field head, so bar line 3 passes. **Re-walked by the review pass**, because
the narrative first written here did not match the grep: it returns seven hits,
not two live ones, and the walk was also scoped to `docs/` when this ticket's
forward references had been written into source.

- `TASKS.md` caveat (a) -- described the arranged row this ticket removed.
  Corrected in the build commit, and the caveat count above it corrected by the
  review.
- `169:181` -- still true as written; left.
- `169:120-123` -- carried the stale 33-of-50 count and the "thirteen
  satisfiable" set into an **unticked criterion** of a `ready-for-agent` ticket.
  The build corrected only 169's `## How this relates` section and reported the
  criterion as corrected too; the review corrected the criterion.
- `175:44` -- cites this ticket only as the shape a bug was found in. Still
  true; left. Not mentioned by the build at all.
- `101:30` and `101:293` -- a criteria line and a `## Comments` line, both
  stating the retired claim. Reported by the build as "inside a resolved
  ticket's history"; they are not, by the bar's own list of dated `##` blocks.
  Left in place and declined by the review, with the reason recorded in the
  findings block: 101 is `resolved`, editing its criteria list to chase a stale
  count would be a REOPEN of settled work, and `101:30` being unticked at all
  is a pre-existing defect of 101's own bar rather than this ticket's.
- `tests/test_playbook.py:452-454` and `:464` -- source, therefore invisible to
  both the build's grep and bar line 3, which are scoped to
  `docs/specs/production-harness-v2/`. The first stated the retired claim as
  measured fact; the second assigned standing ownership of unfinished work to
  this ticket. Both corrected by the review, which is why
  "Forward references left standing: none" was wrong as first written.
- `20261106T000000Z` and `20261107T000000Z` -- inside applied migrations,
  immutable, and `103`'s hit is inside a dated block of a resolved ticket.
  Left.

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

- [x] **A callback arrival can be cited as evidence, read but not run --
      deferred to ticket 84.** The mechanism is the finding above and its
      evidence is source. The run that would close it is one edge citing a
      `record_callback_interaction` Observation by label, and it belongs in a
      callback fixture rather than in this seam. 84 grades every in-scope
      Playbook at its shipped text through the door, `webhooks` among them, so
      84's campaign is the run that settles it. Written ticked with its ticket
      named, which is the one form `standing-bar.md` line 1 admits for work
      that is owed -- the review pass corrected this, because the criterion as
      built named no ticket and was therefore invisible to both the line-1 and
      the line-3 grep.

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
`evidence` list in one payload, so **every kind a proposal can mint** is
reachable and only the writer differs.

That sentence read "every kind in the vocabulary" until the review pass, and
the wider form is false in three places, all of which the review made explicit:

- `promote_proposal` drops an element whose kind's `allowed_provenance` the
  payload cannot satisfy, as `incompatible_provenance`
  (`20261008T000000Z__a_suggested_task_becomes_a_task_or_a_drop.sql:1101-1103`).
  The enum is *offered* whole; it is not reachable whole through this writer.
- `callback_interaction` takes `{callback}` alone and no proposal supplies it.
  It is reachable only by an edge citing an Observation
  `record_callback_interaction` already wrote, which is the `## Build findings`
  entry below and is deferred to ticket 84.
- `transport_parameters_observed` needs a `transport_citable` Receipt, and the
  inverse case is worse: `transport_evidence_guard`
  (`0025_transport_claims.sql:361-394`) refuses a `supports` edge on a
  `probe_only` Property class unless the Observation is exactly that kind. So
  for such a claim the reachable set is one kind and every other is refused, no
  matter who writes it. `http-desync` gates `supported` on two kinds that
  trigger forbids, which is one genuinely unreachable bar in the corpus and is
  now ticket 233. This ticket's sweep asked which writer could produce a kind
  and never asked which kinds a claim's own Property class admits.

The seam is guarded by three tests in
`tests.test_database.HypothesisPromotionTest`.
`test_an_agent_filed_kind_counts_towards_the_playbook_bar` puts one claim
carrying two `credential_effect` edges under
`playbooks/authentication/playbook.md` and asserts the unmet set is empty, the
selection it is reached through exists, and the Playbook declares two
`supported` rows -- the last of those added by the review, because an empty
unmet set alone cannot tell "bar met" from "this Playbook asks for nothing".
`test_the_edge_the_bar_counted_is_the_one_the_promotion_wrote` reads the
producer's two rows back with their `proposal_id`.
`test_the_gate_the_runtime_is_handed_does_not_name_the_playbook`, added by the
review, reads the same bar through `hypothesis_transition_refusal` -- the
function `close_test_replay` actually asks, and the one ticket 182 made ask the
Playbook conjunct first -- and pins the sentence it returns. The fixture opens a
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
**Forward references left standing:** ticket 84, named on the callback
criterion above, and ticket 233, cut by the review pass for the one bar that is
genuinely unreachable. This line read "none" as built; the review pass found
two live forward references in `tests/test_playbook.py` that the redemption
grep could not see, because both it and bar line 3 are scoped to
`docs/specs/production-harness-v2/`. Both are corrected in the review commit
and the walk is recorded in `## Seam check`.

**Wrong in the ticket, named.** The fourth measured line ("The other writer is
shut by then") is false as a reachability claim. The fifth ("33 of 50 ...
37 of 50") is stale: 26 of 51 name a kind the replay does not derive, and that
is now a statement about which writer files the row rather than about whether
one exists. The seventh ("Two candidate fixes, neither chosen here") is
answered by taking neither.

Four more, added by the review pass because the build's list stopped at the
lines it had measured and left the ones it had invalidated:

- **The opening paragraph.** It still asserted the thirty-three-of-fifty wall a
  frontier scan and the close walk read first. Corrected in place, with a
  pointer to this block.
- **The second measured line.** It quotes `object-ownership/playbook.md:14` as
  carrying `credential_effect` on the `control` role. Line 14 carries
  `response_differential` on all three legs, as this ticket's own
  `20261107T000000Z` made it and `20261219T000000Z:285-290` re-froze it. The
  `20260823T000000Z:623` half of that criterion is still true of an immutable
  migration; the `:14` half is not.
- **The sixth measured line.** It says in the present tense that the walk "has
  exactly one arranged row" written by `the_control_the_playbook_asks_for()`
  at `:272-302`. This commit deletes that method, so the claim is false and the
  line range points at unrelated code.
- **The fourth measured line's scope, once more.** It is false as a
  *reachability* claim and true as written about `nachreichen`. It is also not
  the whole story, because reachability turns on the Property class as well as
  the writer -- see the third bullet of the correction above and ticket 233.


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

### Re-run by the review pass, 2026-09-02

Under the existing heading, not a new dated one: this is a review's NOW repair
re-running the machine lines, per `hold-the-line` verdict 1. Nine NOW repairs
touched test code (`tests/test_database.py`, `tests/test_playbook.py`,
`tests/test_vertical.py`); the rest were prose.

Line 1 -- every criterion ticked, and the count the line above does not print:

```
$ grep -c '^- \[ \]' <this ticket>
0
$ grep -c '^- \[[ x]\]' <this ticket>
8
```

Eight against `hold-the-line`'s ceiling of six. Declined in the findings block
with the reason, and the review added none of them.

Line 2 -- the seam test read by name. Two of the three tests below are the
review's; `CleanCreationTest` is in the invocation because
`docs/agents/testing.md` tier 1 says it belongs in every database run, which
the build's paste omitted:

```
$ RK_TEST_SUPERUSER_URL=... RK_TEST_DATABASE=rk2_rev166e \
    uv run python -m unittest -v tests.test_database.CleanCreationTest \
                                tests.test_database.HypothesisPromotionTest
test_an_agent_filed_kind_counts_towards_the_playbook_bar ... ok
test_the_edge_the_bar_counted_is_the_one_the_promotion_wrote ... ok
test_the_gate_the_runtime_is_handed_does_not_name_the_playbook ... ok
… (48 further test lines, all ok)
Ran 51 tests in 38.049s
OK
```

Line 3 -- forward references. The filtered form, and then the plain form the
line actually specifies, which the build did not read hit by hit:

```
$ grep -rn 'ticket 166' docs/specs/production-harness-v2/ \
    | grep -cE '\*\*CONSUMED BY:\*\*|\*\*CONSUMES:\*\*|deferred to'
0
$ grep -rn 'ticket 166' docs/specs/production-harness-v2/ | wc -l
7
$ grep -rn 'ticket 166' --include=*.py --include=*.sql . | wc -l
9
```

Seven and nine, not two. Every hit is walked in `## Seam check` with what
happened to it. The two in `tests/test_playbook.py` are why this ticket's
`Forward references left standing` line was wrong as built.

Line 4 -- existing tests still pass; and what the deletion cost, stated:

```
$ uv run python -m unittest tests.test_vertical tests.test_playbook
Ran 65 tests in 26.782s
OK
```

Two commands rather than one, and that is the substitution the priced wall
allows rather than a single verify command: `docs/agents/testing.md` tier 1
covers the modules touched, and the modules touched here span the database
suite and the two behaviour suites.

**The deletion did cost coverage, and the build's line 4 did not say so.**
"It asserted nothing and its return value was read by nothing" is true of
`cls.control` and false of the rows the method wrote. `propose_finding` copies
every `polarity='supports'` edge into `finding_evidence`, so the arranged
`credential_effect` Observation was a `finding_evidence` row, and
`read_what_the_finding_cites`'s `JOIN test_run_receipts` (`:555-558`) was what
excluded it -- four candidates down to three. With the row gone the filter has
nothing to exclude, so `assert len(cls.witness) == 3` still passes but no
longer discriminates a non-test-run-receipt Observation from a replay one. Not
lowering-move 2 by the letter -- no `.skip`, no deleted file, no removed
assertion -- but a weaker assertion by its spirit, and the honest fix is to say
so rather than to re-arrange the row this ticket removed. The docstring that
explained the filter by that row is corrected in the review commit.

Line 5 -- the diff is what the ticket asked for. Corrected arithmetic: the
build's paste said "Four files. Two are the ticket's corrected `Touches`", but
the corrected `Touches` names all four non-ticket files.

```
$ git status --short --untracked-files=all
 M docs/specs/production-harness-v2/TASKS.md
 M docs/specs/production-harness-v2/issues/166-...md
 M docs/specs/production-harness-v2/issues/169-...md
 M docs/specs/production-harness-v2/issues/84-grade-the-shipped-playbook-corpus.md
 M tests/test_database.py
 M tests/test_playbook.py
 M tests/test_vertical.py
?? docs/specs/production-harness-v2/issues/233-...md
```

Eight paths at review time. Four are the build's, all on the corrected
`Touches`; `84` and `233` are the TICKET verdict's edge and the ticket it
points at; `tests/test_playbook.py` is a NOW repair on a forward reference in
source; this ticket file carries the findings. `hold-the-line` expects a review
commit to hold exactly this set.

Line 6 -- resolution, bar, no handoff. All three greps this time; the build
pasted two:

```
$ grep -c '^## Resolution' <this ticket>
1
$ grep -c '^## Bar' <this ticket>
1
$ grep -c '^## Handoff' <this ticket>
0
```

Effort-wide pending sentinel, which is the close walk's line and is what the
findings block below had to clear:

```
$ grep -rn '— verdict pending' docs/specs/production-harness-v2/ | wc -l
1
$ grep -rn '^- \[[a-z]*\] .*— verdict pending' docs/specs/production-harness-v2/ | wc -l
0
```

One hit and no entry lines. The one hit is the first command of this very
paste, which `standing-bar.md` rules history by its own words -- "a hit that
only quotes the marker inside a paste is history, and a cycle line says
`undecided` and cannot match". The second grep is the one that decides the
line, and it prints `0`.

**Judgement, red and mutated.** Unchanged and still standing: born green, with
the reason on the `Red:` line, and `build-slice` §2 grants that form to a
criterion asserting behaviour that is already correct, which is this ticket's
whole subject. The review's own repairs added no production code, so
`hold-the-line` verdict 1 owes them no red test; the three test additions are
themselves the check.

**Judgement, no unexplained NOBODY.** Both ends named, and the review added the
second on-path reader (`hypothesis_transition_refusal`) the report had skipped.

**Judgement, the live run reached this ticket's case.** It does now, at the gate
rather than at the predicate. The build asserted `playbook_evidence_unmet`
directly and inferred the transition; the review reads the same bar through the
function `close_test_replay` asks and pins the sentence, which names the base
rule and not the Playbook.

**Judgement, no injected double.** None was injected, and the arrangement that
*is* there is now named rather than passed over: `put_the_claim_under_a_playbook_bar`
hand-writes the `tasks` row and the `playbook_selections` row the bar is read
through, bypassing the selection verb, exactly as
`ask_the_preview_about_the_playbook_bar` does. The fixture drives
`proposal.stage` and `promote_proposal` against a real PostgreSQL 18 database.

## Review findings, 2026-09-02 — cycle 1

Fixed point `1ba74ee9`, the parent of this ticket's first and only build commit
`766b21e1`. 204 changed code lines and 260 changed doc lines: one logical
change, reviewable in one sitting. Four axes read in parallel, apart.

- [ticket] **`http-desync`'s `supported` bar is unreachable, and the gate is a per-property-class trigger no measurement in this ticket opened.** `transport_evidence_guard` (`0025_transport_claims.sql:361-394`, `ENABLE ALWAYS`) refuses any `polarity='supports'` edge on a claim whose `property_class` is `probe_only` unless the Observation kind is `transport_parameters_observed`. `http-desync` declares `transport.tls_configuration` in `bb:outputs` (`:4`), which is `probe_only` (`0025:204`), and its bar (`:13`) asks `response_invariant` for `control` and `response_differential` for `variant`, both `supports`. Neither edge can be inserted by any writer. The Resolution's "every kind in the vocabulary is reachable and only the writer differs" is false, and the block is neither provenance nor the replay's kind derivation. — blocker — NOW. The Resolution now says "every kind a proposal can mint" and names this trigger, the Property-class question the sweep never asked, and ticket 233. No production code changed, so no red test is owed; the corpus work is the next entry.
- [ticket] **The corpus defect behind that bar, which ticket 101's rewrite introduced.** `http-desync`'s own `bb:provenance` (`:12`) says the rewrite moved its evidence rows "off `transport_parameters_observed`, which the ledger established has no agent-reachable writer by any path" — onto the two kinds `transport_evidence_guard` forbids for exactly this class. The rewrite inverted reachability rather than restoring it, and nothing records that. — required — TICKET 233. Blocks 84 -- grading `http-desync` at its shipped text would return `fail` and measure this trigger rather than the Playbook, which is what ticket 166's own 2026-08-24 comment recorded happening to five Playbooks at 330 million budget units. 233 is on 84's `Blocked by` line in this commit.
- [seam] **The far end was never run.** Both new tests stop at `playbook_evidence_unmet`; no test inserts a `hypothesis_transitions` row for the `barred` claim, so `enforce_playbook_evidence` (`0032:529`) and `a_playbook_evidence_guard` (`:547-549`) never fire on the agent-filed case. `## Seam check`'s "the empty set is the transition being admitted" is inference across a hop. `tests/test_vertical.py:685` does not stand in: that transition is met by replay-written `response_differential` under `object-ownership`, with no agent-filed edge anywhere in the walk. — required — NOW. `test_the_gate_the_runtime_is_handed_does_not_name_the_playbook` reads the bar through `hypothesis_transition_refusal`, the function `close_test_replay` asks and the one ticket 182 made ask the Playbook conjunct first, and pins the returned sentence: `transition testing -> supported requires a tool receipt`. The base rule, named, with no Playbook in it. The Playbook half admits these edges at the real gate.
- [ticket] **Converged with the seam axis, from the ticket's own promise.** "The first thing this ticket builds is the test that runs it ... if `enforce_playbook_evidence` raises, the wall is real, its message is the `Red:` line." What shipped asserts the predicate, not the transition. A whole transition is in fact unreachable in this fixture: `transition_rules` `testing -> supported` (`0007_epistemics.sql:126`) wants `min_supporting_evidence` 2 counted over roles `baseline,variant` and a test-linked receipt (`0015:195`), and the payload files one `variant`. — required — NOW. Same repair. The seam report now states plainly that the whole `supported` insert is unreachable in this fixture by design -- `transition_rules` wants two `baseline,variant` rows and a test-linked receipt, and the payload files one `variant` -- so the conjunction is described as a conjunction.
- [ticket] **A ticked criterion whose work is owed to nobody.** "- [x] A callback arrival can be cited as evidence, read but not run ... Ticked because the CRITERION verdict is the record, not a promise." `standing-bar.md` line 1 admits exactly one ticked-but-undone form, `- [x] … deferred to ticket NN`, "because the redemption grep below guards it". This carries no ticket number, so it is invisible to the line-1 grep and to the line-3 redemption grep alike. — blocker — NOW. Rewritten as `- [x] ... deferred to ticket 84`, which is the one ticked-but-undone form `standing-bar.md` line 1 admits, and 84's door campaign grades `webhooks` and so is the run that settles it. The debt is now visible to both the line-1 and the line-3 grep.
- [seam] **`tests/test_playbook.py` still states the refuted claim as measured fact and names this ticket as its owner.** `:452-454` "ticket 166 measured that no runtime verb writes that kind, `enforce_playbook_evidence` raises on the transition, and so this Playbook could never reach `supported` at all"; `:464` "ticket 166 owns putting that distinction back". Both the §5 redemption grep and Bar line 3 are scoped to `docs/specs/production-harness-v2/`, so neither can see a source comment, and "Forward references left standing: none" is unproven. — required — NOW. Both comments corrected: `:452-454` no longer states the retired claim as measured fact, and `:464` no longer assigns standing ownership to this ticket. The redemption walk in `## Seam check` now records that it was scoped to `docs/` and says so.
- [seam] **"Every kind in the vocabulary is reachable" is a non-sequitur for the one callback bar.** `webhooks` `supported`/`variant` names `callback_interaction`, whose `allowed_provenance` is `{callback}` (`20260812T040000Z:349`), with the migration's own comment saying the point is "so an agent cannot file a Receipt under it". No proposal-minted Observation can carry it; the mechanism that would reach it is a different one, which this ticket files as read-not-run and then ticks. — required — NOW. Folded into the same scoping. `callback_interaction` is named as one of the three exceptions, with the migration comment that makes it deliberate, and the run is deferred to ticket 84 on the criterion above.
- [ticket] **Converged with the seam axis: reachability is attributed to the wrong mechanism.** `promote_proposal` drops any element whose kind's `allowed_provenance` the payload cannot satisfy — `incompatible_provenance` (`20261008T000000Z:1101-1103`). The enum is *offered* whole by `mcp__rk2__submit_mission_result`; it is not *reachable* whole through that writer. `transport_parameters_observed` is a second exception, needing a `transport_citable` receipt. — required — NOW. Same repair; `incompatible_provenance` is cited and the offered-versus-reachable distinction is drawn in the Resolution.
- [bar] **The `tests/test_vertical.py` deletion cost coverage, and Bar line 4's defence does not cover it.** "It asserted nothing and its return value was read by nothing" is true of `cls.control` and false of the rows the method wrote. `propose_finding` copies every `supports` edge into `finding_evidence`, so the arranged `credential_effect` Observation was a `finding_evidence` row, and `read_what_the_finding_cites`'s `JOIN test_run_receipts` (`:555-558`) existed to filter it out. With the row gone the filter filters nothing, and the surviving `assert len(cls.witness) == 3` (`:571`) no longer discriminates a non-test-run-receipt Observation from a replay one. — required — NOW, as honesty rather than restoration. Bar line 4 below now records the coverage the deletion cost, and the docstring is corrected. Re-arranging a row purely to keep the filter meaningful would put back the one arranged row this ticket removed, which is the wrong fix; what the count now rests on is stated instead.
- [craft] **Converged with the bar axis: the docstring explaining that filter names a row this diff deleted.** `tests/test_vertical.py:548-550` still reads "the Playbook's `control` row above is evidence of the claim and is cited as such, but it stands on the lap's Receipt rather than on an action of the run this report reproduces." There is no such row above any more, and it is the only explanation a reader gets for a filter that no longer filters. — required — NOW. Same edit as the entry above.
- [bar] **Ticket 169's stale count survives in an unticked criterion.** `## Seam check` says 169's forward note "carried the stale 33-of-50 count into a `ready-for-agent` criterion set" and was "corrected in this commit". The edit landed only in `## How this relates`; the phase-zero criterion at `169:120-123` still reads "one of the thirteen Playbooks 166 lists as satisfiable today and is **not** one of the thirty-three that gate `supported` on a kind no verb can write". — required — NOW. `169:120-123` corrected: it no longer claims a thirteen-satisfiable set or a thirty-three-unreachable set, and it says why `file-resolution` is still the right phase-zero pick -- it needs no agent-filed edge. The bullet's `(resolved)` annotation is restored to match its three siblings.
- [bar] **The redemption-grep narrative does not match the grep.** The plain `grep -rn 'ticket 166' docs/specs/production-harness-v2/` the bar specifies returns 7 hits, not "two live prose hits". `101:30` sits in a criteria list and `101:293` under `## Comments` — neither is a dated `##` block, so "hits in 101 are inside a resolved ticket's history and stay" does not hold by the bar's own list. `175:44` is not mentioned. The filtered form still prints `0`, so line 3 passes; the record of it does not. — required — NOW. The paragraph is replaced by the seven hits, each with its real location and what happened to it. The two `101` hits are left in place and declined there in writing: 101 is `resolved`, editing its criteria list to chase a stale count would reopen settled work, and `101:30` being unticked is a pre-existing defect of 101's own bar.
- [craft] **The head still asserts the wall the Resolution says never existed.** "**What to build:** Nothing yet ... Thirty-three of the fifty Playbooks in the corpus gate `supported` on an Observation kind that no runtime writer can put on a hypothesis" — the first thing a frontier scan and the close walk read, and the one paragraph "Wrong in the ticket, named" omits. — required — NOW. Corrected in place and marked superseded with a pointer to `## Resolution`, and added to `Wrong in the ticket, named`.
- [bar] **Criterion 6 is ticked, present tense, and false by this commit's own action.** "`tests/test_vertical.py`'s walk has exactly one arranged row. `the_control_the_playbook_asks_for()` (`:272-302`) writes the `credential_effect` Observation ... as owner." The method is deleted in this diff and the line range now points at unrelated code. — required — NOW. Added to `Wrong in the ticket, named`, with the deletion and the dead line range called out.
- [ticket] **Criterion 2 cites a line that now says the opposite.** It quotes `object-ownership/playbook.md:14` as carrying `credential_effect` on `control`; line 14 carries `response_differential` on all three legs, as this ticket's own `## Seam check` says `20261107T000000Z` made it. — required — NOW. Added to `Wrong in the ticket, named`, separating the still-true `20260823T000000Z:623` half from the false `:14` half.
- [bar] **Eight criteria against a ceiling of six.** `grep -c '^- \[[ x]\]'` prints `8`. `hold-the-line` "Watch the criteria": more than six "has stopped satisfying `cut-slices` Rule 4. Split it. Rule 4 has no enforcement point after cutting, so this is it." Seven were cut with the ticket; the build's own CRITERION verdict added the eighth, which is the growth path that rule guards. — required — DECLINED. The eight checkboxes on this ticket are recorded measurements on an investigation ticket whose `What to build` is "Nothing yet"; `cut-slices` Rule 4 counts work spanning seams, and splitting a ticket whose deliverable is one measurement would split the measurement rather than the work. The review added none of them and put its own two repairs on a new ticket and on 84 instead, which is the behaviour the rule exists to produce. Recorded here rather than acted on.
- [seam] **An empty unmet set is ambiguous and the fixture does not close the ambiguity.** `read_the_playbook_bar` guards the selection-to-Task half with `barred_selections` but never asserts the Playbook declares `supported` rows at all, so an empty result means "bar met" only by reading the corpus. True today, latently vacuous after any corpus rewrite — which is the failure mode this ticket exists to document. — required — NOW. `barred_declared` counts the Playbook's `supported` rows in the same fixture and the test asserts `2`, so an empty unmet set can no longer be read as "this Playbook asks for nothing".
- [bar] **Bar line 6 omits one of its three greps.** The paste carries `grep -c '^## Resolution'` and `grep -c '^## Handoff'` but not `grep -c '^## Bar'`, the one whose heading the block itself creates. Re-run it prints `1`, so nothing fails; a third of the line's evidence is simply absent. — required — NOW. The third grep is run and pasted under the existing `## Bar` heading.
- [craft] **`read_the_playbook_bar` is three responsibilities under a name that says one.** It writes the Task and the selection, publishes `cls.barred_hypothesis` and `cls.barred_selections` as side effects, and returns a third value. Every sibling fixture classmethod in the class is single-mode, and the precedent its docstring cites, `ask_the_preview_about_the_playbook_bar`, assigns and returns nothing. — required — NOW. Renamed to `put_the_claim_under_a_playbook_bar`, returns `None`, and assigns every reading to `cls.*` inside -- which is what `ask_the_preview_about_the_playbook_bar`, the precedent its own docstring cites, does.
- [craft] **`gefilt` is not a German word.** `TASKS.md` caveat (a): "dass eine Evidenzkante mit dem Vorschlag gefilt wird". The nearest real word, `gefüllt`, changes the meaning, and the rest of the paragraph keeps proper register. — required — NOW. `gefilt` to `eingereicht`.
- [craft] **TASKS.md still counts two caveats where one remains.** `:301` "Zwei Vorbehalte, ausdrücklich und nicht stillschweigend:" and `:30` "Die beiden Vorbehalte stehen bei Freigabe B." (a) is now a resolved history note; only (b) is live. — required — NOW. `:301` now reads one caveat with (a) filed as a dated correction, and `:30` matches it.
- [seam] **Two dead fixture assignments.** `cls.filed, cls.agent_kinds = cls.promote("barred", cls.agent_filed())` binds two names no test or fixture reads, and `cls.filed` shadows an attribute four other classes use for something else. Raised by three axes. — nit — NOW. Dropped; the promotion result is discarded the way four sibling calls in the same fixture already discard it.
- [craft] **`SELECT *` then positional indexing.** `read_the_playbook_bar` reads a six-column `RETURNS TABLE` and indexes `row[1], row[2], row[4], row[5]`; the order lives in `0032_playbooks.sql:509-510` and a re-created function reorders it silently. The sibling test added in the same commit names its columns. — nit — NOW. Columns named -- `SELECT req_role, req_kind, need, have` -- with the reason in a comment.
- [seam] **The seam report records no skipped hit and misattributes the live bar writer.** `hypothesis_transition_refusal` (`20261112T000000Z:104`) is a second on-path reader of `playbook_evidence_unmet` and is what `close_test_replay` asks before attempting a transition; it is unrecorded. The far-end bar is attributed to `20261107T000000Z`, but `20261219T000000Z` deleted and re-inserted every Playbook's evidence rows and is the current writer. — nit — NOW. `hypothesis_transition_refusal` is recorded as the skipped hit, and the live writer of the bar the walk reads is corrected from `20261107T000000Z` to `20261219T000000Z:285-290`.
- [ticket] **Three thin citations.** `0018_vocabularies.sql:219-236` is offered for "every kind named here" but does not contain `callback_interaction`; the `CONSUMES` head names no file or line; Bar line 5's "Four files. Two are the ticket's corrected `Touches`" contradicts the `Touches` line, which names all four. — nit — NOW. `0018_vocabularies.sql:219-236` now carries the `20260812T040000Z:349` companion citation for the kind it does not contain; the `CONSUMES` head cites `20261219T000000Z:123-128`; Bar line 5's arithmetic is corrected below.
- [bar] **Two Bar-block bookkeeping slips.** The substituted verify command differs between line 2 (one class, no `CleanCreationTest`) and line 4 (a different module), so "the same verify command, read whole" is not what ran; and "Judgement, no injected double — none was injected" does not name the hand-inserted `tasks` and `playbook_selections` rows the bar is read through. — nit — NOW. Bar line 4 now names both commands and why two were needed, and the injected-double judgement names the hand-written `tasks` and `playbook_selections` rows.
- [craft] **Three taste calls on the new fixture and the Bar block.** `CREDENTIAL_PLAYBOOK` is a single-use constant 400 lines from its use; `agent_filed`/`read_the_playbook_bar` import a sentence-style naming register the class does not use; the `## Bar` block restates the three sections above it. — nit — DECLINED. `CREDENTIAL_PLAYBOOK` is named because the `Mutated:` line's evidence is the result of swapping exactly that constant, so the name is what made the mutation legible; the sentence-style register matches the replay fixture the new code sits beside; and the `## Bar` block's restatement is what `standing-bar.md` mandates as the ticket's evidence, not duplication to clean up.

Tickets minted by this cycle: 1 (233). Criteria added to this ticket: 0 --
the ticket is already at eight against a ceiling of six, so no verdict was
allowed to land here. Criteria added to any other ticket: 0; the TICKET
verdict wrote a `Blocked by` edge on 84 and left its six criteria alone.

Review cycle 1 of 3 — undecided: none
