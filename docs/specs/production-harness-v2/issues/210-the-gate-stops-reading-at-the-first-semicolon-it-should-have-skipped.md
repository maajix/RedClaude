# 210 — The gate stops reading at the first semicolon it should have skipped

**What to build:** `statement()` in `tools/check_wiring.py` ends a seeded
statement at the first `;` it finds in the raw file, so a semicolon inside a
comment or a string literal hides every row after it from the gate. The file
already builds the mask that answers this correctly; the reader has to use it.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

Found while landing ticket 100: a new `property_classes` row whose description
contained a semicolon made the three rows written after it invisible to gate W9,
and the gate passed. The description was reworded there; the reader was left for
this ticket.

Measured across `src/redkraken/migrations/*.sql`, comparing each statement the
gate reads against the same span ended at the first semicolon of the file's own
mask:

```
statements read via statement():        112
truncated early:                          1
seeded rows the gate never sees:          5
```

The one is `0018_vocabularies.sql:216`, the `observation_kinds` seed. It is cut
at line 238, by the semicolon in its own section comment:

```sql
 -- non-evidential: surface facts. Real observations, provenance and all; they
 -- populate entities and inform the scheduler, and they settle nothing.
```

The five rows below that comment -- `endpoint_discovered`,
`parameter_discovered`, `technology_identified`, `identity_established`,
`artifact_captured` -- are exactly the five non-evidential kinds, and they are
the only ones the rule that reads this map cares about.

## Why it fails open

`tools/check_wiring.py:1697`:

```python
if catalogue.evidential.get(kind, True) or role == "context":
    continue
```

A kind the reader never saw is assumed evidential, so the rule "a Playbook
expects a non-evidential kind at a settling role" cannot fire for any of the
five kinds it exists to catch. No shipped Playbook names one today, so this is
a hole and not a live miss -- but it is a hole in the direction a gate must
never fail in, and it has been open since the reader was written.

## The mechanism

`tools/check_wiring.py:544`:

```python
def statement(sql: str, start: int) -> str:
    stop = sql.find(";", start)
    return sql[start:] if stop < 0 else sql[start:stop]
```

The docstring says the statement is taken off the original rather than the mask
on purpose, and that half is right: a seeding statement's content lives in its
string literals, and the mask blanks them. What does not follow is finding the
*end* there. `masked()` blanks comments, quoted runs and dollar-quoted bodies to
spaces of the same length, so a position in the mask is a position in the file
(`check_wiring.py:410`). The end belongs in the mask; the content belongs in the
original.

Every one of the twelve call sites already has `code` in scope.

## Acceptance criteria

- [x] `statement()` finds the end of a statement in the mask and slices the
      original, so a semicolon inside a comment, a string literal or a
      dollar-quoted body no longer ends it. All twelve call sites pass the mask
      they already hold.
- [x] A test in `tests/test_wiring.py` covers the three shapes directly against
      `statement()`: a semicolon inside a `--` comment, one inside a `'literal'`,
      and one inside a `$$ body $$`. Each asserts the rows after it are read.
- [x] A test asserts `evidential` reads all sixteen observation kinds out of the
      shipped corpus, with the five non-evidential ones present and `False`.
      This is the shipped-corpus check that would have failed before the fix.
- [x] `catalogue.evidential.get(kind, True)` at `check_wiring.py:1697` keeps its
      default, or the reason it is safe once the reader is honest is written
      down beside it. The default is what turned a truncated read into a pass.
- [x] `check_wiring` still ends rc=0 on the corpus as it stands, and its W9
      summary line is compared against the pre-fix one in the resolution
      comment: if any count moves, the movement is a finding this gate owed and
      is either fixed or given a register row.
- [x] The other three gates end rc=0 and `tests.test_wiring` is green.

## Notes

The fix is a reader, not a vocabulary, so no migration and no database are
needed: `tests.test_wiring` and the four gates are the whole acceptance surface.

Nothing here changes what the corpus seeds. If the honest read turns up gaps the
gate should have reported all along, they are the point of the ticket, not scope
creep -- record them, and split anything that needs a migration into its own
ticket rather than widening this one.

## Comments

**2026-08-28 -- The mask already knew. The reader now asks it.**

`statement()` takes the mask as well as the file. The end of the statement is
found in the mask, where a semicolon inside a comment, a literal or a
dollar-quoted body is a space; the content is still sliced out of the original,
which is the half of the old docstring that was right. All twelve call sites
already held `code` and now pass it.

Red first, against the tree as it stood:

```
TypeError: statement() takes 2 positional arguments but 3 were given
AssertionError: 16 != 11
```

The second is the one worth keeping: the gate read eleven observation kinds out
of a corpus that seeds sixteen, and every one it saw was evidential, because
the five it lost are the five non-evidential ones.

Two tests in `tests/test_wiring.WiringReadingTest`:

- `test_a_semicolon_the_mask_already_knows_about_does_not_end_a_statement` asks
  all three shapes in one statement, and also asserts the statement stops before
  the `INSERT` that follows it -- reading two as one would turn a later
  migration's correction into a second opinion.
- `test_every_observation_kind_the_corpus_seeds_reaches_the_reading` is the
  shipped-corpus check: 16 kinds, 11 evidential, and the five non-evidential
  ones named and `False`.

**The report did not move.** Every count in `check_wiring`'s summary is
character-for-character what it was before the fix, `W9 vocabulary 13 owed
property classes 61 emitted 50 unmakeable 2` included, and the register is still
56 rows. That is the honest outcome and not a disappointment: only one statement
in the corpus was being truncated, W9's other readings never depended on it, and
no shipped Playbook names a non-evidential kind at a settling role. The hole was
real and it was empty.

`catalogue.evidential.get(kind, True)` keeps its default, with the reason
written beside it: what it now covers is a name that is not an observation kind
at all, which the database refuses on its own, so the gate reports the one
problem a body really has instead of two. Before this fix the same default was
answering for five kinds a truncated read had hidden, which is what made the
rule dead rather than lenient.

Measured: `tests.test_wiring` **26 tests, OK**. All four gates rc=0.
`git diff --check` clean. No migration, no database.
