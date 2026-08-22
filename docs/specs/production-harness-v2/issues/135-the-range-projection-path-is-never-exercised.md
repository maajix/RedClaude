# 135 — The range projection path is never exercised

**What to build:** The two tests ticket 117's criterion 5 named and its
implementation did not reach, because the file that holds them was owned by
another agent at the time.

**Blocked by:** 117 — The CIDR arm of scope evaluation has no writer.

**Status:** ready-for-agent

- [ ] The projection is exercised through the statement that changed. Ticket
      117's criterion 5 asks that "a configuration with a CIDR target compiles,
      projects, and an Entity inside the range comes out `target`". The
      compiling half is covered by `tests/test_scope.py:241-341`. The projecting
      half is asserted in the migration by a hand-written `INSERT INTO
      program_scope_rules`, which bypasses `program.py:910-925` -- the
      `jsonb_to_recordset` column list that gained `net cidr` and is the only
      writer a real Program uses. A test must drive that path.
- [ ] The three-way matrix gains a range row. Ticket 117's own correction says
      ranges "must land in the Python evaluator and in the diagnostic's grammar
      ... or the three-way matrix starts disagreeing". The matrix fixture at
      `tests/test_database.py:3872` gained no `cidr` row, so SQL-side and
      Python-side agreement on a range is currently unverified in both
      directions.
- [ ] Both tests fail before the fix they protect and pass after, and the ticket
      records which assertion caught what.

## Why

Found by the spec axis of the code review on `0759b7b`. Ticket 117 is otherwise
paid; this is the part of its criterion 5 that a file-ownership boundary kept
out of that commit, cut into its own ticket rather than left as a ticked box
over an untested path.
