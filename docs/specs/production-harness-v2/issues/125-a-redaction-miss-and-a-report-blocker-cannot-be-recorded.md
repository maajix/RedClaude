# 125 — A redaction miss and a report blocker cannot be recorded

**What to build:** Writers for the two tables that record why evidence or a
report must be held back: `redaction_failure` and `program_known_issues`.

**Blocked by:** nothing.

**Status:** ready-for-agent

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
- [ ] A program's do-not-report list can be populated.
      `program_known_issues` (`0034_reports.sql:351-359`) is read by
      `report_blockers` and has no writer. Its own comment (`:348-350`) says
      what it is for: "Bounty programs publish one, and a report that ignores it
      costs reputation rather than earning a bounty. It is a hard blocker, not a
      warning." Five of its columns are on the agent's read surface and all five
      are always NULL.
- [ ] The writer for the known-issue list is the one the corpus already names.
      `0034_reports.sql:1073` registers the table as `'reference'` with the
      rationale "the program's published do-not-send list, entered by the
      operator through the control surface", and no control surface enters one.
      `source` is constrained to
      `('program_policy','operator','prior_submission')`, which names three
      origins: the program's published policy, a human, and the harness's own
      history of what it has already submitted. The first two are the
      configuration document `program.py` compiles; the third is a runtime
      write after a report goes out.
- [ ] Whichever writers are added, the blocker is asserted end to end: a Finding
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
