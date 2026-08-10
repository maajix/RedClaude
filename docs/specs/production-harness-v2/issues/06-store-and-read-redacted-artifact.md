# 06 — Store and read a redacted Artifact

**What to build:** Persist one non-secret runtime Artifact by content hash and let the owning Program retrieve bounded ranges without widening global deduplication into cross-Program access.

**Blocked by:** 05 — Prove Program isolation and bounded reads.

**Status:** resolved

- [x] Storing identical plaintext twice produces one content-addressed Artifact and distinct Program-scoped references where appropriate.
- [x] The recorded identifier is the SHA-256 of exact plaintext bytes and is verified again on read.
- [x] Agent-visible reads require a reference reachable from the current Program and support bounded ranges with omission metadata.
- [x] A bare hash from another Program cannot reveal existence or content.
- [x] Artifact creation and reference creation are audited without embedding Artifact bytes in Events.
- [x] Corruption, missing backing data and hash mismatch fail closed and make dependent integrity checks unsound.

## Comments

Implemented on branch `implementation/startup-assertion` in commit `c5837b8` on
2026-08-10.

`src/redkraken/artifact.py` is the operation and `rk artifact put|get|audit` is
the adapter over it; `src/redkraken/store.py` is the half of an Artifact the
database cannot see, and
`20260810T151500Z__program_scoped_artifacts.sql` is what makes a Program able to
hold one.

`artifacts` existed from 0005 and had exactly one writer: the receipt function
0040 wrote, which records four hashes per intercepted call with `byte_size = 0`
and no bytes behind them. Its policy matched — 020 scoped the table by
reachability through a view called `artifact_refs`, because the table is a
`program_global_table` and has no `program_id` to key on — and the two relations
that view reads from are receipt tables. So an Artifact could become visible to a
Program only by being the request or response body of an intercepted call.
Nothing could store one deliberately, and nothing could hold one for any other
reason.

`artifact_references` is the missing row: a Program, a label, a hash, and why
the Program holds it. It is the whole of criterion 1. The store deduplicates on
`sha256` and the reference does not, so identical plaintext from two Programs is
one file, one `artifacts` row and two references — both labelled `AF1`, because
labels are per Program and colliding short labels are the ordinary case rather
than the awkward one. Within one Program the reference is the claim, and a claim
made twice is one claim: `(program_id, sha256, kind)` is unique, and a repeated
`put` reports `stored: false, referenced: false` rather than inventing a second
label nobody would see again.

`artifact_refs` gained a third arm over the new table and `artifacts_due_for_purge`
gained a second `NOT EXISTS`, so the reachability policy and the purge
refcount both extend rather than fork.

### What is asserted, and by what

`tests/test_artifact.py` is 29 offline tests over four pure seams. `digest` is
held against `hashlib` rather than against itself. `window` is the bounded read,
and its tests are about the subtraction: what was omitted before the range, what
after, and that the three numbers always add up to the artifact — including an
offset past the end, which is an empty answer with the whole artifact omitted
before it rather than an error. `Store` is tested at the two ways it can be
wrong. `ArgumentTest` asserts criterion 4 where it can be asserted rather than
described: the read verb takes a label, no verb takes a hash, and the SQL those
verbs send contains no such parameter.

`tests/test_cli.py::ArtifactCommandTest` is 7 tests over the adapter: the store
named alongside the connection strings when none is set, both connection strings
named for a read, `--sha256` rejected as an unrecognized argument, neither URL
echoed back, and a refused configuration that reaches no database and creates no
store directory.

`tests/test_integrity.py::StoreVerificationTest` is 7 tests over the gate's new
question, and the load-bearing one is that a store nobody named leaves the report
byte-for-byte as it was — no key, no statement sent.

`tests/test_database.py::ArtifactStoreTest` is 19 live tests and the third class
in that module that commits. Criterion 4 is the interesting one: it counts rows
visible to each Program across `artifacts`, `artifact_references` and
`v_artifacts` for a hash only the first Program ever stored, and gets `[1, 1, 1]`
against `[0, 0, 0]`. The read for that label from the second Program is
indistinguishable from a label nobody holds — same shape, same exit code — for
the reason ticket 05 established: it is the same query, and the difference is a
row RLS did not return.

Run on 2026-08-10 against `pgvector/pgvector:pg18` — PostgreSQL 18.4 with
pgvector 0.8.6, the pairing tickets 03, 04 and 05 were verified on. The whole
suite with the server present is 373 tests, green, no skips, in 161s; without one
it is 290 with 11 skipped. `tools/check_baseline.py` reports `classifications=10
regressions=7 artifacts=223`, unchanged. There is still no typechecker configured
in this repository — no `[tool.mypy]` or `[tool.pyright]` in `pyproject.toml`,
and neither is installed — so what ran in its place is `python3 -m compileall -q
src tests`, clean.

`check_artifact_reachability()` has four negative controls in `CONTROLS`: a
reference left dangling by a purge, a reference to an artifact whose visibility
is `secret`, the foreign key to `artifacts` re-created as `ON DELETE CASCADE`,
and `artifact_refs` taken off `security_invoker`.

### Decisions worth naming

**Criterion 6's second clause is the gate's, not the command's.** `rk artifact
audit` walks one Program's references and reads every one of them, which answers
"fail closed". It does not answer "make dependent integrity checks unsound",
because nothing calls it: a corrupt store would have passed `rk db verify`
silently, and every later check that trusts a recorded hash would have been
trusting nothing. So `integrity.verify` takes an optional store root and holds
every recorded reference against the bytes filed under it, and `rk db verify
--artifacts` is how an operator asks. It is not counted in `checks` — that number
is how many registered checkers ran, and this is not one of them — but it fails
the gate exactly as they do. `test_a_store_the_gate_cannot_verify_fails_the_gate`
is the control: the same connection, the same corpus, passing blind and failing
when given the store.

**`store.py` is a separate module for one reason.** `integrity` cannot import
`artifact`, because `artifact` imports `program` and `program` imports
`integrity`. The split is not merely a way around the cycle, though: everything
in `store.py` is over bytes, a path and a hash, which is what makes the gate able
to ask without knowing anything about commands, and what makes the same code
testable without a server.

**The bytes go down before the row, and are never taken back up.** A committed
row naming a file that was never written is the one skew `audit` cannot repair.
The other direction — bytes filed under their own hash with no row naming them —
is unreachable by any reader and is adopted by the next `put` of the same
plaintext. An earlier draft deleted them on the way out of a failed transaction;
that is a race, because another process may already have committed a reference
to exactly those bytes. Review caught it and it is gone.

**Whole-plaintext verification on every read, including bounded ones.** Hashing
the slice would verify the answer against itself, and a corrupt artifact would
read clean in every window that misses the damage. A range that fails leaves
`content` null: a partial answer here would be an answer nothing downstream could
be trusted about afterwards.

**`v_artifacts` lost its `ref_count`.** 020's version counted references across
the whole installation, so an agent could watch the number move and learn that
some other Program had stored the same bytes. The view now joins through
`artifact_references` and answers only with what this Program holds.

**Criterion 5 is met by `artifact.referenced` on the reference table.** Every
path that creates an `artifacts` row also creates a receipt or a reference, and
both of those are audited, so no artifact comes into existence unobserved.
`artifacts` itself stays exempt, and the exemption's `reason` now says why in the
form 0027 asks for: the table is program-global, so an event about a row of it
has no Program to belong to. The payload carries the hash and no bytes; the
length is the one join away it has always been. 0027 still lists `artifacts` as
`'undecided'` against ticket 07, which is an inconsistency in that registry
rather than in this one.

**`kind` has three values and only one is written today.** `runtime` is what
`rk artifact put` records; `tool_output` and `source` exist because they are the
third component of the uniqueness rule, and the same file arriving as a tool's
output and again as fetched source is two claims about one artifact rather than
one claim with a lost distinction. Tickets 30 and 32 are the writers.

### Raised by review and deliberately not built here

- **The glossary is not updated.** `CONTEXT.md` defines **Artifact** and lists
  `_Avoid_: Blob`; it says nothing about a reference, a label or a store root.
  No implementation ticket in this branch has edited that file, and
  `docs/agents/domain.md` says the glossary is maintained by `/domain-modeling`.
  The public name `blob_path` that review flagged is gone — it is `store.path_for`
  — and the new prose says "bytes" where it would have said "blob", but the
  glossary entry itself belongs to whoever runs that skill next.
- **The agent still reaches the store through SQL.** `rk artifact get` binds a
  session and reads `v_artifacts`; the model-facing surface that turns this into
  a tool call, with the harness process holding the session, is ticket 19. What
  ticket 06 owes it is that no argument on this path names a Program or a hash,
  and none does.
- **Encryption is ticket 07.** Everything stored here is `agent_visible`
  plaintext. `check_artifact_reachability()` already refuses a reference to an
  artifact whose visibility is `secret`, so the day sealed artifacts arrive they
  cannot be reached by this path by accident.
- **`v_artifacts` is now read; the other five 020 views still are not.** Ticket
  05 left the question of whether they survive open. This one answers it for the
  artifact view and leaves the rest to ticket 19.
