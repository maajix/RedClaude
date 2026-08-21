# 125 — A redaction miss and a report blocker cannot be recorded

**What to build:** Writers for the two tables that record why evidence or a
report must be held back: `redaction_failure` and `program_known_issues`.

**Blocked by:** nothing.

**Status:** needs-triage

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
