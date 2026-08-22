# 114 — The retest lane has no input and no reader

**What to build:** The three connections the "re-test when the surface changes"
design is missing: the property-class mapping for the thirty-nine classes that
have none, a writer for `hypothesis_retest_triggers`, and a reader for the two
views that would show the answer.

**Blocked by:** nothing.

**Status:** resolved

- [x] The mapping covers every class a Playbook emits.
      `rk2_negative_relevant_deltas`
      (`20260814T080000Z__a_refutation_is_kept_and_made_due.sql:569-592`) is
      what puts a recorded refutation back in the queue when the surface moves,
      and it inner-joins `surface_delta_property_classes` on
      `pc.kind = d.kind AND pc.property_class_id = n.property_class`. That table
      is seeded once, at
      `20260813T140000Z__the_surface_gets_a_fingerprint.sql:335`, and holds rows
      for eighteen classes. The vocabulary now holds fifty-seven. Counted
      independently from the migration corpus: 57 declared, 18 mapped, **39
      with no row**. A refutation recorded in any of those thirty-nine is never
      made due again, whatever changes on the target.
- [x] The thirty-nine are not treated as one bucket. Three of them are the
      classes `transport_makeability` declares `unmakeable` or that nothing
      emits, which are already ticket 101's and 100's; the rest are classes a
      shipped Playbook produces. The mapping added is for the classes with an
      emitter, and the ticket says which ones it deliberately leaves out.
- [x] `hypothesis_retest_triggers` acquires a writer.
      `grep -rn "INSERT INTO hypothesis_retest_triggers"` over
      `src/redkraken/migrations/*.sql` and `src/redkraken/*.py` returns nothing.
      The table is declared at `0007_epistemics.sql:97` and read by four
      functions -- `cancel_reason_for`, `novelty_for`, `scheduler_idle_report`
      and `refresh_negative_knowledge`, the last of which *updates* `fired_at`
      and `fingerprint` on rows that never exist. The re-test input to
      scheduling is permanently empty.
- [x] The two views that compute the answer acquire a reader.
      `v_negative_knowledge`
      (`20260814T080000Z...:1049`, `GRANT SELECT ... TO rk2_runtime` at `:1094`)
      projects seventeen columns of refuted hypotheses and their retest
      standing, and is read only by `tests/test_database.py`.
      `v_surface_deltas`
      (`20260813T140000Z...:733`) projects twelve columns of what changed
      between two fingerprints and is likewise read only by the test suite. A
      view granted to `rk2_runtime` with no reader is the strongest form of the
      signal, because the grant is a claim that somebody reads it.
- [x] The reader is named, not implied. `rk state` (`src/redkraken/cli.py:313`)
      and the operator panels are the two candidates on the operator side;
      whether the agent gets one is ticket 129's, because
      `negative_knowledge` and `negative_knowledge_retests` are both on the
      agent read surface
      (`20260814T080000Z...:1127-1135`) and no tool reads either.
- [x] The seeding is done the way the original was: `INSERT ... SELECT` from a
      `VALUES` list with a `note` per row saying why that delta kind
      invalidates that class, so the table stays the argument it was written as
      rather than becoming a cross product.

## Why

`docs/research/wiring/20-vocabulary-wiring.md` section 1b: "the harness ships a
retest lane, the playbook produces claims, and the two are not connected." The
mapping was seeded on 2026-08-13 covering the eighteen classes that had
Playbooks then, and the forty-three Playbook classes that arrived from
2026-08-26 onward never extended it.

`docs/research/wiring/23-database-wiring.md` section 3.1 reaches
`hypothesis_retest_triggers` from the other side and grades it load-bearing for
the same reason, and its section 6.1 finds the two unread views. All three are
one design -- keep a refutation, notice when the ground moved, say so -- and it
is disconnected at the input, at the mapping and at the output.

`negative_knowledge` is what the report calls "the single highest-value read for
not repeating work". An entire migration exists to keep refutations and make
them due, and nothing consumes any part of it.

## What was built

`20260927T010000Z__the_retest_lane_has_an_input_and_a_reader.sql`, the reader in
`rk run`'s pass, and the tests for both.

**The mapping.** One hundred rows into `surface_delta_property_classes`,
`INSERT ... SELECT` from a fifty-row `VALUES` list of `(delta prefix,
property class, note)` joined to `surface_projection_sections` and
`surface_delta_kinds` on `k.change IN ('added', 'changed')`, so each hand-written
row becomes the two kinds that can put its class back in question and the
removals stay mapped to nothing. Every one of the thirty-three classes a shipped
Playbook declares as an output now has a row; the table went from 44 rows to
144. The join is the reason the list is fifty rows rather than a hundred: the
argument is "an added or changed endpoint invalidates this class", and saying it
once per section is what keeps it an argument.

**The input.** `arm_retest_watches()`, security invoker, granted to
`rk2_runtime`, declared in `runtime_verb_surface`. It writes one
`response_fingerprint_changed` row per `supported` or `inconclusive` claim of
the current Program, at the Application's current fingerprint, `ON CONFLICT DO
NOTHING`, and returns `{armed, watching, unwatched}`. It deliberately never arms
a `refuted` claim: every door into `refuted` writes a `negative_knowledge`
record, and that record is the precise lane -- made due by a *class-relevant*
delta. A watch would make the same claim due on any fingerprint change at all,
so arming one for a refuted claim would pre-empt the mapping this same file just
finished seeding. The two lanes are exhaustive over settled claims and disjoint,
and `unwatched` is the count that proves it: settled claims of this Program with
no watch row at all, which is exactly the claims whose subject reaches no
Application.

**The output.** Both views are dropped and recreated carrying `pr.slug AS
program`, following `v_decision_queue`'s precedent
(`20260814T020000Z__the_operator_answers_and_the_work_resumes.sql:601`) for the
reason that precedent gives. This was not
cosmetic. `rk2_runtime`'s row level security policies on `negative_knowledge`
and `surface_deltas` are `USING (true)` -- the runtime serves every Program --
so a runtime that selected either view would have silently mixed Programs
together. Neither view carried a uuid before and neither carries one now: 020
rule 5 holds, and `program` is a slug like every other citation in them.

**The reader.** `Attempt._retests` in `src/redkraken/execution.py`, run once per
pass before ranking, in one transaction: arm the watches, refresh the negative
knowledge, then read `v_negative_knowledge WHERE standing = 'due'` and
`v_surface_deltas`, both filtered to the pass's own Program by slug. It records
one `hold` on the ledger naming what it armed and what became due, and a failure
records a `fail` and returns rather than stopping the pass -- the retest lane is
a thing the pass reports, not a thing the pass depends on.

**The verb nobody called.** `rk2_hypothesis_negative(uuid)` was executable by
`rk2_runtime` and called from exactly one place in the corpus, the body of the
`v_records` view, which `rk2_state` reads. Section 4 of the migration revokes the
runtime's grant and deletes the matching `66-seed` row from
`runtime_verb_surface`. `rk2_state` keeps its grant. This is the register row
`tools/check_wiring.py` booked to this ticket, and closing it by reachability was
not possible: W3 follows calls from one function body to another and a view body
contributes no call edge, so no reader given to a view could ever have reached
it. The runtime's reader of this lane is `v_negative_knowledge`, a strict
superset of the three keys that function builds.

### Where this ticket was wrong

**Criterion 2 says three.** It is six. Two are what
`transport_makeability` declares `unmakeable` -- `transport.datagram_transport`
and `transport.request_framing` -- and four more have no emitter at all:
`authentication.recovery_flow`, `rate_limiting.per_origin`,
`rate_limiting.resource_cost` and `transport.certificate_trust`. Measured on a
scratch database with the whole corpus applied, as the difference between the
classes `playbook_outputs` names and the classes `property_classes` declares.
The remaining thirty-three are mapped, and the migration asserts the count both
ways: a thirty-fourth emitted class arriving with no mapping row fails the
migration rather than joining the six quietly.

**Criterion 5 offers `rk state` as a candidate reader.** It cannot be one.
`rk state` reads on the `rk2_state` connection, and neither view is granted to
`rk2_state` -- `v_negative_knowledge` is granted to `rk2_runtime` at
`20260814T080000Z...:1094` and `v_surface_deltas` likewise, and nothing anywhere
grants either to the agent's role. Giving `rk state` the read would have meant
granting the model the Surface fingerprints that 020 deliberately keeps away from
it, which is the same decision `rk2_hypothesis_negative` exists to honour. The
reader is the runtime's own pass instead, which is the role both grants already
name.
