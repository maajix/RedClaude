# 74 — Purge a Program whose Finding cites a Hypothesis

**What to build:** Make `DELETE FROM programs` succeed for a Program holding a Finding that names a Hypothesis, so the whole-program purge does not depend on the order the catalogue happens to hold foreign keys in.

**Blocked by:** nothing.

**Status:** resolved

**Reading on the How:** none of the three, because the headline case was already
fixed and measuring it found four more. What every one of them has in common is a
table that reaches the purge root a generation later than a parent it names with a
NO ACTION key, so the repair is the shape 016 gave every table it saw: the row
reaches `programs` directly, and is therefore gone before any check can be asked.

- [x] A Program carrying a Finding, its Hypotheses and the `finding_hypotheses` edge between them is purged by one `DELETE FROM programs`.
- [x] The purge no longer depends on which of two sibling cascades the catalogue reaches first, and a test seeds the row that proves it.
- [x] Whatever `check_program_isolation` or `restore_fk_order` has to learn to keep it true is stated once, and fails when it stops being true.

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

## Comments

Implemented on 2026-08-17.

`src/redkraken/migrations/20260908T000000Z__a_purge_reaches_every_row_before_it_is_checked.sql`,
one new `ProgramPurgeTest`, four `Control`s and four teardown workarounds removed
in `tests/test_database.py`. No Python: the purge is one statement the schema
either permits or does not, and nothing in `src/` orders it.

Three things ship here that no criterion asks for, all found by measuring the one
that does. The `interception_cas` key is rewritten, because a Program that has
minted a CA could not be purged by any statement the schema permits and this
ticket is the one holding the question "does `DELETE FROM programs` work". Two
`purge_cascade_edges` rows that name a key with no delete action come out, because
they are the CA's lie in its own register and arm (a) is what makes it visible.
And arms (a) and (b) restate 016's one-time rewrite loop as a standing question
rather than only answering criterion 3's "keep it true" for the generation rule.
The alternative was three follow-up tickets against a corpus that cannot purge a
Program in the meantime.

### The headline case was fixed by accident

The Why's traceback is real and was reproducible when 71 hit it, but it is not
reproducible now: `20260815T120000Z__a_supported_claim_becomes_a_candidate.sql`
rewrote the hypothesis side of `finding_hypotheses` to `ON DELETE CASCADE` on its
way past, for the rollup's own reasons, and registered it. The finding side has
cascaded since `0009_findings.sql:34` and was registered by 016, so both ends now
cascade and the edge table is emptied in the same generation as either parent. So
criterion 1 was met before this ticket opened, which is worth saying plainly
rather than quietly ticking: `SlateClaimTest.tearDownClass` came out and its 36
tests pass with the Program purged in one statement.

That left the question of what the defect actually was, and it is not one edge. It
is a rule nobody had written down.

### The rule

`DELETE FROM programs` queues one RI trigger event per referencing key, drains
that queue FIFO, and every event drained can queue more at the end. So the queue
has generations: a table is emptied at the length of the shortest chain of
cascades from `programs` that reaches it, and a NO ACTION check on `child ->
parent` is queued while the parent is being emptied, which puts it one generation
after the parent. The check passes if and only if `generation(child) <=
generation(parent)`, and when it does not, the purge succeeds or fails depending
on which of two sibling keys the catalogue holds first -- measured on a synthetic
four-table schema that fails one way round and succeeds the other with nothing
else different.

Four keys in the corpus were on the wrong side of that rule:
`finding_chain_step_citations -> observations` and `-> receipts`, `finding_effects
-> observations`, and `hypothesis_evidence -> proposals`, the last of which was
passing on luck. Three harness teardowns were deleting in front of exactly those
tables: `ReportFixture`'s named "an order PostgreSQL picks", `MissionPacketTest`'s
claimed a schema intent -- "the hypothesis side cascades and the observation side
does not" -- that had stopped being true two migrations earlier, and
`OperatorDecisionTest`'s deleted `finding_hypotheses` with no comment at all,
which is the same workaround with the pointer to this ticket left off. All three
came out.

The repair is the root edge, and the corpus states the rule for it twice in
opposite directions, so the migration says which one it follows. 016:188 is
"every program-scoped table reaches the purge root directly". 017:134 is "No
`REFERENCES programs(id)` on the derived tables ... a second edge would put a
sixteenth delete action into the purge graph that `purge_cascade_edges` and check
B13 would then have to carry for nothing". "For nothing" is what this ticket
measured and disproved: the composite key to the owner does pin the program, and
it does not empty the row in time. Of the three tables given the edge here only
`hypothesis_evidence` is 017-derived; `finding_effects` and
`finding_chain_step_citations` (034) declared `program_id` themselves and simply
never got the edge 016 would have given them.

### The one no order could save

`interception_cas` (025) declares its `program_id` key NO ACTION and registers
that same column in `purge_cascade_edges` with the rationale "Purging a program
destroys its CA record". Those cannot both be true. Nothing reaches the table, so
a Program that has ever minted a CA cannot be purged at all:

```
23503: update or delete on table "programs" violates foreign key constraint
"interception_cas_program_id_fkey" on table "interception_cas"
```

016's rewrite loop cannot see this. It strips a cascade that no register row
accounts for; a register row that no cascade accounts for is the same lie told the
other way round, and it hid there for six migrations because no test in the file
had ever written a CA row. `ProgramPurgeTest` writes two.

### What keeps it

`check_purge_travel()`, four arms, registered as this ticket's own standing check
rather than as arms bolted onto 016's or 017's -- 026's reason, which 75 also
took. Arm (a) is the register claiming an edge no key travels. Arm (b) is 016's
rewrite loop restated as a standing question rather than a thing that ran once in
2025 and has been on the corpus's honour since. Both read one sentence in
opposite directions, so both use the same three actions for "travels" -- CASCADE,
SET NULL, SET DEFAULT -- since RESTRICT is not a weak cascade but the refusal to
travel, and a register row over a RESTRICT key would be the CA's lie with one
more letter in it.

Arm (c) is the generation rule, and it is deliberately stricter than the failure:
it fails a pair that is merely lucky, because 031 exists precisely because a
restore reorders keys and "lucky" and "green" read the same until the day they do
not. Two exclusions, both because something else answers them. A pair that also
carries a cascade is 017's check (d), which asserts the cascade fires first and is
how every entity detail table is purged. A self-referencing key answers itself,
since all of one table's rows go in the delete that queues its own check -- and
rather than leave that as a claim, the test writes the row: a retired CA
superseded by a current one, which is the only self-referencing NO ACTION key in
the corpus.

Arm (d) is the CA's defect asked of every table rather than of that one, and it
is a fourth arm rather than a widening of (c) because (c) structurally cannot see
it: (c) compares two generations and `programs` is not program-scoped, so a key
straight into the purge root is invisible to it. What it names is also worse than
an ordering and does not depend on one -- NO ACTION into `programs` from a table
no cascade reaches refuses the delete in every catalogue order there is.

Four arms, four negative controls, one per arm and each written so the arm it
names is the only one it trips. That last part is not enforced: the gate asserts
the check goes red, not why, so a control that went red for a neighbour's reason
would pass while covering nothing -- which is exactly the trap here, since three
of the four arms fire on the register and the catalogue disagreeing and a careless
break makes them disagree twice. Arm (c)'s control is the defect itself put back,
one dropped key, plus the register row that key answers for.

### The test purges on purpose

Every fixture in `test_database.py` ends by dropping its Program, which has meant
that for the whole life of the corpus the purge was covered by a teardown -- so a
failure was an error in whichever case ran next, not an assertion. `ProgramPurgeTest`
inherits `ReportFixture` for its rows, which is the deepest Program the suite
builds -- 52 program-scoped tables with rows in them, including all four the rule
was broken for -- mints the CA nothing else mints, and then makes the delete the
assertion, rolled back so the fixture's own teardown still executes it
independently afterwards. What it asserts against is every program-scoped table in
the catalogue, read out of `pg_class`, not the five that are known to have been
wrong.

Criterion 2 is a third test rather than a hope: inside the same rolled-back
transaction it drops and re-adds every cascade key on those five tables, which
makes each the newest constraint in the database and therefore the last of its
parent's RI triggers to fire -- the state a `pg_restore` leaves at random -- and
purges again. Measured both ways: with the three keys this migration adds dropped,
that same rebuild fails with `finding_effects_witness_observation_id_program_id_fkey`,
and with the CA key put back to NO ACTION it fails on the CA.
