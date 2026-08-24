# 166 — A Playbook demands an Observation kind no verb can write

**What to build:** Nothing yet. This ticket records a gap the synthetic vertical
run exposed and does not fix it. Thirty-three of the fifty Playbooks in the
corpus gate `supported` on an Observation kind that no runtime writer can put on
a hypothesis, so those Playbooks cannot be satisfied by any sequence of verbs
this tree serves.

**Blocked by:** nothing.

**Status:** ready-for-agent

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
