# 74 — Purge a Program whose Finding cites a Hypothesis

**What to build:** Make `DELETE FROM programs` succeed for a Program holding a Finding that names a Hypothesis, so the whole-program purge does not depend on the order the catalogue happens to hold foreign keys in.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] A Program carrying a Finding, its Hypotheses and the `finding_hypotheses` edge between them is purged by one `DELETE FROM programs`.
- [ ] The purge no longer depends on which of two sibling cascades the catalogue reaches first, and a test seeds the row that proves it.
- [ ] Whatever `check_program_isolation` or `restore_fk_order` has to learn to keep it true is stated once, and fails when it stops being true.

## Why

`SlateClaimTest` is the first case in the suite to write a Finding, and its
teardown could not purge its own Programs:

```
23503: update or delete on table "hypotheses" violates foreign key constraint
"finding_hypotheses_hypothesis_id_fkey" on table "finding_hypotheses"
Key (id, program_id)=(019ffbb8-..., 019ffbb8-...) is still referenced
```

`0016_event_log_corrections.sql:189-221` gives `finding_hypotheses` exactly one
cascade edge, the finding side, and rewrites every other referencing key to NO
ACTION. The design note there is explicit about why that is supposed to work:

> `NO ACTION` and not `RESTRICT`: NO ACTION is checked at the end of the
> statement, by which time the program cascade has already removed the
> referencing rows, so the purge passes.

It has not removed them. `hypotheses_program_id_fkey` is older than
`findings_program_id_fkey`, so the program cascade reaches `hypotheses` first;
deleting those rows queues the NO ACTION check on `finding_hypotheses`, and that
check runs before the `findings` cascade that would have emptied the table. The
purge fails on an ordering the corpus never chose.

This is `0031_restore_fk_order.sql`'s failure in a place its finalizer does not
look. 031 repairs NO ACTION keys that a *restore* reordered ahead of the cascade
that feeds them; here nothing was restored -- the order is the one the corpus
builds, and it has simply never been exercised, because no test until now created
a Finding in a Program it then purged.

Two things follow. The purge is one of the four questions `test_database.py`
exists to ask, and it has a hole in it that only a Finding can reach. And the
whole-program delete is the only row delete the schema permits, so a Program in
this state cannot be removed by any other means either.

## How

Not decided here. Three shapes are open, and each says something different about
what the edge is:

- Give `finding_hypotheses` a second cascade edge, from the hypothesis side, and
  say in `purge_cascade_edges` why an edge table may have two -- which is the
  thing 016 wrote the one-edge rule to prevent.
- Make the hypothesis-side key `DEFERRABLE INITIALLY DEFERRED`, so the check
  happens at commit rather than at end of statement and every cascade has run.
- Extend `restore_fk_order`'s repair to the order the corpus builds rather than
  only to the order a restore leaves, so the offending NO ACTION key is rebuilt
  behind the cascade that feeds it in every database.

Whichever is chosen, the test is the same: seed a Program with a Finding, a
Hypothesis and the edge, purge it in one statement, and assert nothing is left.
`tests/test_database.py`'s `SlateClaimTest.tearDownClass` currently deletes the
edge rows by hand with a comment pointing here; that workaround comes out with
this ticket.
