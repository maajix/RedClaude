# 210 — The gate stops reading at the first semicolon it should have skipped

**What to build:** `statement()` in `tools/check_wiring.py` ends a seeded
statement at the first `;` it finds in the raw file, so a semicolon inside a
comment or a string literal hides every row after it from the gate. The file
already builds the mask that answers this correctly; the reader has to use it.

**Blocked by:** nothing.

**Status:** ready-for-agent

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

- [ ] `statement()` finds the end of a statement in the mask and slices the
      original, so a semicolon inside a comment, a string literal or a
      dollar-quoted body no longer ends it. All twelve call sites pass the mask
      they already hold.
- [ ] A test in `tests/test_wiring.py` covers the three shapes directly against
      `statement()`: a semicolon inside a `--` comment, one inside a `'literal'`,
      and one inside a `$$ body $$`. Each asserts the rows after it are read.
- [ ] A test asserts `evidential` reads all sixteen observation kinds out of the
      shipped corpus, with the five non-evidential ones present and `False`.
      This is the shipped-corpus check that would have failed before the fix.
- [ ] `catalogue.evidential.get(kind, True)` at `check_wiring.py:1697` keeps its
      default, or the reason it is safe once the reader is honest is written
      down beside it. The default is what turned a truncated read into a pass.
- [ ] `check_wiring` still ends rc=0 on the corpus as it stands, and its W9
      summary line is compared against the pre-fix one in the resolution
      comment: if any count moves, the movement is a finding this gate owed and
      is either fixed or given a register row.
- [ ] The other three gates end rc=0 and `tests.test_wiring` is green.

## Notes

The fix is a reader, not a vocabulary, so no migration and no database are
needed: `tests.test_wiring` and the four gates are the whole acceptance surface.

Nothing here changes what the corpus seeds. If the honest read turns up gaps the
gate should have reported all along, they are the point of the ticket, not scope
creep -- record them, and split anything that needs a migration into its own
ticket rather than widening this one.
