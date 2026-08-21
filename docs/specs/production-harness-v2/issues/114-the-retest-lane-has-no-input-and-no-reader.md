# 114 — The retest lane has no input and no reader

**What to build:** The three connections the "re-test when the surface changes"
design is missing: the property-class mapping for the thirty-nine classes that
have none, a writer for `hypothesis_retest_triggers`, and a reader for the two
views that would show the answer.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] The mapping covers every class a Playbook emits.
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
- [ ] The thirty-nine are not treated as one bucket. Three of them are the
      classes `transport_makeability` declares `unmakeable` or that nothing
      emits, which are already ticket 101's and 100's; the rest are classes a
      shipped Playbook produces. The mapping added is for the classes with an
      emitter, and the ticket says which ones it deliberately leaves out.
- [ ] `hypothesis_retest_triggers` acquires a writer.
      `grep -rn "INSERT INTO hypothesis_retest_triggers"` over
      `src/redkraken/migrations/*.sql` and `src/redkraken/*.py` returns nothing.
      The table is declared at `0007_epistemics.sql:97` and read by four
      functions -- `cancel_reason_for`, `novelty_for`, `scheduler_idle_report`
      and `refresh_negative_knowledge`, the last of which *updates* `fired_at`
      and `fingerprint` on rows that never exist. The re-test input to
      scheduling is permanently empty.
- [ ] The two views that compute the answer acquire a reader.
      `v_negative_knowledge`
      (`20260814T080000Z...:1049`, `GRANT SELECT ... TO rk2_runtime` at `:1094`)
      projects seventeen columns of refuted hypotheses and their retest
      standing, and is read only by `tests/test_database.py`.
      `v_surface_deltas`
      (`20260813T140000Z...:733`) projects twelve columns of what changed
      between two fingerprints and is likewise read only by the test suite. A
      view granted to `rk2_runtime` with no reader is the strongest form of the
      signal, because the grant is a claim that somebody reads it.
- [ ] The reader is named, not implied. `rk state` (`src/redkraken/cli.py:313`)
      and the operator panels are the two candidates on the operator side;
      whether the agent gets one is ticket 129's, because
      `negative_knowledge` and `negative_knowledge_retests` are both on the
      agent read surface
      (`20260814T080000Z...:1127-1135`) and no tool reads either.
- [ ] The seeding is done the way the original was: `INSERT ... SELECT` from a
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
