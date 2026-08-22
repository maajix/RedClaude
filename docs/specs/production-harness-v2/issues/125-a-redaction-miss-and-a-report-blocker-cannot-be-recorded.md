# 125 — A redaction miss and a report blocker cannot be recorded

**What to build:** Writers for the two tables that record why evidence or a
report must be held back: `redaction_failure` and `program_known_issues`.

**Blocked by:** nothing.

**Status:** resolved

- [ ] A redaction that fails is recorded. `redaction_failure`
      (`0024_secret_keying.sql:143-154`) carries the rule that tripped, the
      encoding path it tripped on, an offset, a length and a keyed fingerprint,
      and its own comment (`:140-142`) states the design: "A redaction that
      fails open is worse than none, so the projection is withheld and the
      failure is a row here, not a log line." It has no writer, no reader and no
      FK pointing at it. `src/redkraken/evidence.py` reads `redaction_rules` and
      `evidence_bundle_files` and records no failure.
- [ ] The thing that would write the row is identified, because it does not
      exist either. `redaction_failure.rule_id` is "which verifier tripped" and
      `encoding_path` is "'raw', 'urldecode', 'base64>urldecode', ..."
      (`0024_secret_keying.sql:147-148`), so the row is the output of a
      verification pass that re-scans the redacted bytes through each encoding
      looking for what should have gone. `evidence.redact`
      (`src/redkraken/evidence.py:103-152`) applies the rules once against the
      original text and returns what it replaced; it cannot fail, and there is
      no second pass to fail. The missing piece is the verifier, and the table
      is only its output.
- [ ] The withholding half is settled with the recording half. The comment
      promises two things -- the projection is withheld, and the failure is a
      row -- and today the harness does neither.
- [x] A program's do-not-report list can be populated.
      `program_known_issues` (`0034_reports.sql:351-359`) is read by
      `report_blockers` and has no writer. Its own comment (`:348-350`) says
      what it is for: "Bounty programs publish one, and a report that ignores it
      costs reputation rather than earning a bounty. It is a hard blocker, not a
      warning." Five of its columns are on the agent's read surface and all five
      are always NULL.
- [x] The writer for the known-issue list is the one the corpus already names.
      `0034_reports.sql:1073` registers the table as `'reference'` with the
      rationale "the program's published do-not-send list, entered by the
      operator through the control surface", and no control surface enters one.
      `source` is constrained to
      `('program_policy','operator','prior_submission')`, which names three
      origins: the program's published policy, a human, and the harness's own
      history of what it has already submitted. The first two are the
      configuration document `program.py` compiles; the third is a runtime
      write after a report goes out.
- [x] Whichever writers are added, the blocker is asserted end to end: a Finding
      whose class and entity match a known issue is refused by `report_blockers`
      rather than merely annotated.

## Why

`docs/research/wiring/23-database-wiring.md` section 3.1 lists both among the
fourteen tables with no `INSERT` anywhere and grades each load-bearing:
`redaction_failure` "if a redaction miss is meant to be auditable",
`program_known_issues` as "a report blocker that can never block".

Together they are the two places the harness was supposed to be able to say "do
not send this out". Both are on the path between a Finding and a human, both are
declared with the reasoning written into the migration, and neither can hold
anything back today.

`needs-triage` because each needs its writer chosen by somebody who knows where
the operator's configuration ends and the runtime begins, and because the
redaction half may be hiding a second, larger question about what the harness
does when a redaction rule trips.

## The decision, taken 2026-08-22

**The two halves get opposite answers. `program_known_issues` gets a writer, and
it is the configuration document, on the pattern `identity`, `required_header`
and `callback` already set. `redaction_failure` is retired: the design it
presumes was overruled at the point of implementation, and no honest
implementation can write the row.**

### `program_known_issues` is a configuration table

The corpus already named the writer and then did not build it. `0034_reports.sql:1073`
registers the table as `'reference'` with the rationale "the program's published
do-not-send list, entered by the operator through the control surface", and the
`source` CHECK (`0034:356`) names three origins of which two are the operator's:
`program_policy` is the published list transcribed, `operator` is the operator's
own addition, and `prior_submission` is the harness's record of what it has
already sent.

The shape to copy is next door. `config.TOP_LEVEL` (`src/redkraken/config.py:31-40`)
holds eight keys, three of which -- `identity`, `required_header`, `callback` --
are lists of typed entries validated by a per-entry reader and projected into
state by a `_project_*` function in `program.py` that inserts what is new,
updates what changed and invalidates what the document stopped naming
(`_project_identities`, `src/redkraken/program.py:998-1085`). A known-issue entry
is `class_id`, an optional `entity_like`, a `source` and a `note`; the offline
validator checks shape, and `class_id REFERENCES vulnerability_classes(id)`
checks membership at projection time -- the same division of labour the scope
compiler already uses.

**It is worth building rather than dropping because the override for this gate
already ships.** `rk finding clear-gate` (`src/redkraken/cli.py:1378-1392`) exists
to let an operator overrule exactly two of the nine emission blockers, and the
first one it names is `known_issue`: "where the program published a do-not-send
list and whether this instance is what they meant is a reading of their words".
The harness ships the power to lift a gate that can never be raised. And the gate
is a hard one when it is raised -- `report_blockers` returns `'hard',
'known_issue'` joined on `class_id` and `entity_like`
(`0034_reports.sql:815-825`), and `0034:992` refuses on every hard blocker -- so
the ticket's last criterion is already enforced by the function; it needs rows,
not new enforcement.

`prior_submission` is not this ticket's. It is a runtime write that happens after
a report has actually gone out, and nothing in this tree sends one yet.

### `redaction_failure` is retired

The table promises a two-part behaviour (`0024_secret_keying.sql:139-141`): "A
redaction that fails open is worse than none, so the projection is withheld and
the failure is a row here, not a log line." Both parts were reconsidered, in
prose, by the code that does the redaction.

**The withholding was rejected explicitly.** `project_identity_response`
(`src/redkraken/proxy.py:659-697`) opens with "Redaction and not suppression"
and gives the reason: "Withholding it whole would cite nothing and would make an
authenticated exchange -- the one an access control finding is made of -- an
exchange whose answer nobody may read." The compensating control is named in the
same docstring: "the Agent view and the wire view are hashed separately and the
difference is sealed, so an exchange whose redaction was incomplete is one an
auditor can still see whole."

**And the row cannot be written by an honest implementation.** The table's own
columns say what would write it: `rule_id` is "which verifier tripped" and
`encoding_path` is "'raw', 'urldecode', 'base64>urldecode', ..."
(`0024:147-148`) -- a second pass that re-scans the redacted bytes through
encodings. That vocabulary now lives in the scrubber instead: `_renderings`
(`proxy.py`, the function `project_identity_response` calls) expands each injected
secret into eight spellings -- raw, percent-encoded, four base64 variants and two
hex cases -- and every one of them is replaced in the body and dropped from the
headers. So a verifier searching the same eight finds nothing by construction,
and a verifier searching for a ninth would be a better detector than the
scrubber, in which case it belongs *in* the scrubber. **Any detector good enough
to write the row is good enough to prevent it**, which is why the table has no
writer and would not get one.

What the scrubber does not catch it says it does not catch: "a target may
transform a value beyond any spelling `_renderings` knows -- so what this narrows
is the ordinary case rather than closing the class. Anything richer -- a hash, a
truncation, half a value on each side of a template -- is not recoverable by
search and is not pretended to be." That is a stated residual risk with a stated
control, not a missing writer.

The migration that drops the table says all of this, so that the next reader does
not re-add it: the harness redacts and records; it does not verify and withhold;
and the sealed wire view is where an incomplete redaction stays visible.

## What was measured

`grep -rn "redaction_failure" src/ tools/` returns its own `CREATE TABLE` and
nothing else -- no INSERT, no SELECT, no FK. `grep -rn "program_known_issues"`
returns the table, the `report_blockers` join, the `'reference'` registry row and
the read-surface grants -- one reader, no writer. `_renderings` produces eight
distinct spellings per secret and `project_identity_response` applies all of them
to both halves of the message; `project_identity_request` (`proxy.py:700-`) does
the same for the request side, added by ticket 96 when a model could first compose
a body.

## Correction: `evidence.redact` is not the function this ticket is about

The ticket reads `redaction_failure` against `evidence.redact`
(`src/redkraken/evidence.py:103-152`) and concludes the missing piece is a
verifier for it. Those are two different redactions with two different subjects.
`evidence.redact` applies the six `redaction_rules` rows
(`0034_reports.sql:328-341`: email, phone, bearer, jwt, card, national_id) to an
**export bundle**, and its subject is other people's personal data -- "Nothing
about another person" (`evidence.py:18-22`). `redaction_failure` is a 0024 table,
and 0024's subject is the harness's own injected credential material in the
**agent's view of an exchange**; its `encoding_path` vocabulary matches
`_renderings`, not the six PII patterns. The conclusion the ticket draws from
`evidence.redact` -- single pass, cannot fail, no second pass to fail -- is true
of that function and is not the reason this table is empty. The reason is above.

## What was built, 2026-08-22

The decision above, carried out as written. Nothing in it was reopened.

**The do-not-send list has a writer and it is the configuration document.**
`known_issue` is a ninth key in `config.TOP_LEVEL` (`src/redkraken/config.py:35`),
read per entry by `config._known_issue` (`:706`) into the four columns the table
holds: a `class_id` checked for shape and not for membership, an optional
`entity_like`, a `source` closed to `operator` and `program_policy`, and a
required one-line `note`. Two entries agreeing on `class_id` and `entity_like`
are refused as one rule written twice, because that pair is what
`report_blockers` joins on and which of the two notes a refusal quoted would
otherwise be whichever row the join reached first.
`program._project_known_issues` (`src/redkraken/program.py:1106`) projects the
list inside the transaction `_open_program` already runs (`:544`): insert what is
new, update what changed, delete what the document stopped naming. It reads only
rows whose `source` is not `prior_submission`, so the one origin the harness
writes for itself is not the document's to withdraw -- the exclusion is in the
`SELECT` rather than in a filter afterwards, because a row this function never
sees is a row it cannot delete by forgetting to check.

Two things the writer did not need. The gate is untouched: `report_blockers`
has always returned `'hard', 'known_issue'` on the `class_id`/`entity_like` join
and `0034:992` has always refused on every hard blocker, so the last criterion
is enforced by a function that only ever lacked rows. And no privilege moved:
`rk2_runtime` already held SELECT, INSERT, UPDATE and DELETE with four `66-seed`
rows in `runtime_table_surface`, and its row-level policy admits it
unconditionally. Section 4 of the migration asserts both rather than trusting
that they are still there.

**`redaction_failure` is retired** by
`20261006T000000Z__a_do_not_send_list_is_written_and_a_redaction_verifier_is_not.sql`,
which carries the argument so that the next audit does not re-add the table: the
withholding half was rejected in prose by `project_identity_response`, and any
detector good enough to write the row is good enough to prevent it, so it
belongs in `_renderings` instead. The same file updates the register sentence
that sent a reader looking for a control surface nobody built, and takes the
dropped table's seven register rows with it -- one `event_table_exempt`, one
`purge_cascade_edges`, one `program_global_tables` and four
`runtime_table_surface` -- with each count asserted, because a name that matched
nothing would delete nothing and let the file declare itself finished.

## What was measured, 2026-08-22

Measured twice, because three other agents were writing the same worktree: once
there, and once in a `git archive HEAD` tree carrying only this ticket's files.
Both readings are given where they differ.

| Command | Answer |
|---|---|
| `uv run python -m unittest tests.test_config tests.test_program -q` | `Ran 96 tests in 0.646s` / `OK` (isolated: `Ran 96 tests in 0.537s` / `OK`) |
| `uv run python -m unittest tests.test_config tests.test_program tests.test_doctor tests.test_scope tests.test_build -q` | `Ran 217 tests in 3.330s` / `OK` |
| `uv run python -m unittest tests.test_evidence -q` | `Ran 50 tests in 0.011s` / `OK` |
| `uv run python -m unittest tests.test_proxy -q` | `Ran 124 tests in 46.224s` / `FAILED (failures=1)`, the known client-certificate failure |
| `uv run python -m unittest tests.test_cli -q` | `Ran 145 tests in 48.647s` / `FAILED (failures=1)`, the known `ContainmentTest` failure |
| `flock /tmp/rk2-db.lock ... tests.test_database.CleanCreationTest RuntimePrivilegeSurfaceTest ProgramRunTest FindingReportTest -q` | `Ran 57 tests in 85.061s` / `OK` (isolated, without `ProgramRunTest`: `Ran 43 tests in 29.622s` / `OK`) |
| `PYTHONPATH=$PWD python3 -s tools/check_audit.py` | rc=0 |
| `PYTHONPATH=$PWD python3 -s tools/check_wiring.py` | rc=1, register rows only, below |
| `PYTHONPATH=$PWD python3 -s tools/check_baseline.py` | rc=0 |
| `PYTHONPATH=$PWD/src:$PWD python3 -s tools/check_coverage.py` | rc=0 |

`CleanCreationTest` is the class that proves the corpus applies from empty, which
is what a new migration most often breaks; `FindingReportTest` is where the
`known_issue` gate is already asserted end to end against rows inserted by hand
(`tests/test_database.py:37352`, `:37733`); `RuntimePrivilegeSurfaceTest` is
where the registers the drop empties are held to the catalogue.

## What was not paid, and why

**Criteria one, two and three stay unticked, and they are refused rather than
deferred.** They ask for a writer for `redaction_failure` and for the second
pass that would feed it. The decision above is that no honest implementation can
write the row: the vocabulary those columns describe now lives in the scrubber,
a verifier searching the same eight spellings finds nothing by construction, and
one searching for a ninth belongs in the scrubber instead. So they name no
ticket that owes them -- the table is gone and the argument is in the migration,
which is where the next reader meets it.

**Three `owed:125` rows in `tools/check_wiring.py` are left standing**, because
that file was held by another agent. Two of them are now stale and one has lost
its subject:

- `"W6 program_known_issues"` and `"W6 redaction_failure"` both name gaps this
  ticket closed -- the first has a Python writer, the second has no table -- so
  the register answers `this tree has no such gap; remove the row`. Both rows
  should be deleted.
- `"W3 find_in_database"` is still a gap and is now recorded against a resolved
  ticket. It was put here on the ground that this ticket "builds the redaction
  verifier, whose output is what a sweep would feed"; there is no verifier and
  will not be one. The function itself is unaffected and still uncalled: it is a
  synthetic-marker sweep for incident response
  (`20260810T173000Z__sealed_wire_artifacts.sql:178-218`), and the nearest open
  ticket whose work would call it is 65, whose evidence-bundle criterion is that
  the bundle "contains no synthetic credentials or unredacted wire secrets". The
  row needs re-pointing at whichever ticket takes that; it is not this one.

**Four database-level assertions are in the migration rather than in a test,**
because `tests/test_database.py` was held by another agent for the whole of this
work. Section 4 of the migration asserts, inside the transaction that applies
it: that `redaction_failure` leaves no relation and no row in any of the six
registers; that `rk2_runtime` holds all four privileges on
`program_known_issues` in the catalogue *and* in `runtime_table_surface`, which
is what `apply_runtime_grants()` reads; that the row-level policy
`program_known_issues_rk2_runtime` exists, since a grant without a policy is a
writer whose rows are silently discarded; and that `report_blockers` still joins
on both `class_id` and `entity_like`.

What a test should assert once that file is free is the projection's own end to
end, which no assertion in a migration can reach without manufacturing a
Program, an Entity and a Finding and leaving them behind: that `rk run` against
a configuration carrying one `[[known_issue]]` entry leaves exactly that row;
that a second run with the entry reworded updates it in place rather than
replacing it; that a third run with the entry removed leaves none, while a row
whose `source` is `prior_submission` survives all three; and that a Finding of
the named class on a matching entity is then refused with the operator's note as
the refusal's detail.
