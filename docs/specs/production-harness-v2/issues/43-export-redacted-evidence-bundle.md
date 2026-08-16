# 43 — Export a redacted evidence bundle

**What to build:** Package one rendered Finding or chain with independently verifiable, redacted evidence that remains usable outside the running database without exporting credentials.

**Blocked by:** 07 — Encrypt credential-bearing wire Artifacts; 42 — Render Findings and chains deterministically.

**Status:** resolved

- [x] The bundle contains the deterministic report, replay specification, assertion outcomes, Receipt metadata, redacted Agent-view Artifacts and content hashes.
- [x] Encrypted wire credentials, capabilities, cookies, secret headers, runtime keys and unrelated Program material are excluded by default.
- [x] A standalone verifier checks manifest completeness and every included hash without database access.
- [x] Export rechecks current Finding or chain soundness and refuses stale, invalidated or review-gated material.
- [x] Repeated export from identical canonical rows is deterministic apart from explicitly excluded packaging metadata.
- [x] Synthetic credential markers remain absent from the unpacked bundle and secret scanning passes.

## How each is met

1. **What a bundle carries is a table, not a branch in the packer.**
   `evidence_bundle_files` registers one row per subject per file, and
   `rk2_evidence_required_files()` names the six every subject owes: `report.md`,
   `source.json`, `spec.json`, `receipts.json`, `artifacts.json`, `verify.py`.
   `_written` writes the documents and asks the registry which of the optional
   ones this subject carries, so giving a bundle a file is adding a row rather
   than editing a condition -- and an export that owes a file it did not write
   refuses instead of shipping an incomplete bundle. `check_evidence_export`
   asks the other direction: that every renderable subject carries every
   required file, and that no file is registered for a subject nothing renders.

   The replay specification is on both sides and was not at first. A Finding has
   one -- `finding_evidence_specifications` reads it through
   `validated_by_test_run_id` -- and a chain has one per step, which
   `chain_evidence_specifications` reads through each stamp's `test_run_id`.
   Without the second, a chain bundle carried 042's `specification sha256` line
   against each transition and shipped none of the documents those digests
   identify: a recipient could read the number and hold it against nothing. Both
   come from the database rather than one from there and one out of the report
   source, so `spec.json` is one document read one way.

   `assertions.json` is the one file only a Finding has, because a chain has no
   single validating run to have answered anything.

   The hashes are the manifest's: every file, its length and its SHA-256,
   including each packed artifact. `artifacts.json` names, per artifact, the
   Agent-view digest it was made from, the digest of what the bundle actually
   carries after redaction, both lengths, the redactions applied and every
   `receipt:direction` that cites it.

2. **Exclusion is what the queries select, not what a filter strips.**
   `evidence_artifacts` has `visibility = 'agent_visible' AND NOT encrypted AND
   purged_at IS NULL` in its `WHERE`, so a sealed wire artifact is not something
   the packer declines to write -- it is something no read returns. Every
   function in the file is bound by `rk2_program_required()`, so another
   Program's rows are outside the query rather than filtered out of a result.
   `evidence_receipts` carries `query_sha256` and never a query string, which is
   009's decision rather than a new one. No column this module reads holds a
   capability, a cookie, a header value or key material.

   What was left behind is stated. `evidence_exclusions` has five arms over one
   CTE -- sealed wire artifacts, Identity material, query strings, a sealed
   Agent view, a purged artifact -- each a code, a sentence and a count, and only
   non-zero rows come out. A reader cannot tell material that was excluded from
   material that was never there, and the two Agent-view arms are the ones
   `evidence_artifacts` would otherwise withhold silently: 042's report cites
   such an artifact by hash, and without those lines a reader comparing the
   document against `artifacts.json` finds a hash the index does not carry and
   no sentence anywhere saying why.

   `test_a_bundle_states_no_exclusion_it_had_nothing_to_exclude_for` is the
   other side of the same rule: the Finding's exchanges ran anonymously, so its
   bundle has no `identity_material` line at all, and every line it does have
   counts more than zero.

3. **The verifier ships inside what it verifies and imports nothing.**
   `verifier.py` imports `hashlib`, `json`, `re`, `sys`, `Mapping` and `Path`,
   and `IndependenceTest` asserts that whole list rather than a rule about it.
   `evidence.py` copies the file into every bundle as `verify.py`, and section 2
   makes it a file every bundle owes, so a bundle cannot ship without the thing
   that checks it. `rk evidence verify` calls the same function on the same
   directory, which is what makes the operator's check and the recipient's check
   one check.

   It answers five questions: every file the manifest names is here and is the
   bytes the manifest says; every file that is here is named by the manifest;
   the manifest still says what it said when it was written; the bundle's two
   indexes agree about the artifacts they both describe; and nothing a redaction
   rule was written to remove survives in any packed file. The fourth exists
   because the same export writes `artifacts.json` and the manifest, which is
   exactly why a recipient should not be made to assume they agree.

   `test_the_copy_in_the_bundle_runs_under_a_python_that_has_no_package` runs
   the shipped copy from outside this repository with no `PYTHONPATH`, and holds
   its answer against what `rk evidence verify` said about the same bundle.

4. **Soundness is 042's question, asked again at export time.** The export reads
   through `read_finding_report`/`read_chain_report` and renders through 042's
   renderer, so `report_blockers` and `rk2_chain_unsoundness` decide -- an
   invalidated, duplicate, known-issue or review-gated subject raises `Refused`
   before a byte is written, and `test_a_finding_nothing_has_been_composed_onto_is_refused`
   asserts the destination does not exist afterwards.

   `evidence_stale_rendering` is the half 042 had no reason to ask. A Finding
   whose rows moved after somebody approved a rendering of it would export a
   fresh document under a label an approval was given for a different one, and
   every hash in the bundle would be internally consistent. The refusal names
   the digest on both sides. A chain has no rendering row and a Finding nobody
   has filed a rendering for is not stale; neither is refused, because there is
   nothing there to have gone out of date.

5. **Every read is ordered and the wall clock is outside the digest.** Each
   function orders by a column that means something -- receipt arrival then
   label, artifact by hash, specification by test label -- and `_artifacts` keys
   packed bytes by the Agent-view hash, so two exchanges carrying identical
   bodies are one file rather than two names a reader has to compare. The only
   clock in the module is `_now()`, and it writes into `packaging`, which
   `manifest_digest` excludes along with the digest itself.
   `test_a_second_export_of_unchanged_rows_is_the_same_bundle` compares every
   file of two exports byte for byte, and
   `test_the_two_manifests_differ_only_in_when_they_were_packed` compares the two
   manifests key by key.

6. **A redaction rule carries two witnesses, and both are checked from both
   engines.** `redaction_rules` gains `probe` and `counter_probe`, both NOT NULL
   and non-empty. A rule that matches nothing is a redaction that fails open,
   which 024 already said in writing is worse than none; a rule that matches
   everything fails closed, which sounds safe and is not -- the scan runs over
   the whole bundle, so a pattern that claims a timestamp refuses every export
   until somebody turns the rule off. `check_evidence_export` arms 1 and 2 ask
   PostgreSQL that each pattern matches its probe and declines its counter-probe;
   `test_database` asks `re` the same two questions, which is the engine that
   actually redacts and so the only one whose answer reaches a bundle.

   Three of the six patterns changed to pass their counter-probes. `\b` is a
   backspace character in a POSIX ARE and a word boundary in Python, so `phone`,
   `card` and `national_id` are anchored with `(?<![0-9A-Za-z])` and
   `(?![0-9A-Za-z])` instead. The counter-probes are the exact false positives
   that had bitten: an ISO timestamp read as a telephone number, a SHA-256 hex
   digest read as a card number.

   `redact` matches every rule against the original text and splices once.
   Overlaps go to the earliest start, then the longest match, then the lowest
   rule identifier, which is a total order -- so the same bytes redact the same
   way whichever order the rules arrive in. latin-1 throughout, the one codec
   that round-trips every byte.

   What stands in place of a match names the rule and the length and nothing
   else. It deliberately does not carry a digest of what was removed: a
   telephone number, a national identifier or a card number has few enough
   possible values to walk through offline, so publishing SHA-256 of one is
   publishing it. The range stays answerable to somebody holding the full
   artifact, since the manifest names that artifact's own digest and each mark
   carries its offset and length -- which needs the artifact, and that is the
   difference.

   Finally, `_verified` runs the shipped verifier over the finished directory
   before the command reports success, and **deletes the tree when it refuses**.
   The refusal this exists to catch is `redaction_incomplete`, which says a
   packed file still carries what a rule was written to take out; leaving that on
   disk under a directory named as a bundle produces exactly the thing the export
   refused to produce, with only an exit status between it and an operator who
   attaches it.

## What this ticket also changed

- **`reporting.projected` is shared between the renderer and the packer.**
  Identifying which row a label names and reading its projection onto one form
  is the same pair of reads with the same pair of refusals, and 043 was the
  second reader. A bundle whose `source.json` came from a different projection
  than its `report.md` would be one where every hash agrees and the document is
  about something else.
- **The manifest carries one version of the packing and not two.** It had
  `schema` and `version` holding the same string. The verifier travels inside
  the bundle it verifies, so what packed a bundle and what reads one are one
  release and cannot differ; the second key was a difference a recipient would
  go looking for and not find. `renderer` stays, because 042 renders through a
  projection this module does not control.
- **`evidence_bundle_files` is a global reference table the runtime cannot edit.**
  `program_global_tables` and `event_table_exempt` both name it, `UPDATE` and
  `DELETE` are revoked from `rk2_runtime`, and `rk2_state` and `rk2_proxy` have
  no access at all. `INSERT` is retained for 20260819T000000Z's reason:
  `readwrite_on_every_managed_table` asserts the runtime keeps SELECT and INSERT
  on every managed table. The retained verb is not a way in -- the CHECKs admit
  two subjects and one filename shape, so an INSERT can only add a file the
  exporter does not write, and `_written` refuses when the registry owes a file
  the export did not produce.
- **`probe` and `counter_probe` join the Agent state read surface.** Both are
  synthetic strings that say nothing about a target, and withholding them would
  make the read surface disagree with the table for no reason.

## What is not covered

- **A bundle is a directory and not an archive.** Nothing here tars, zips or
  signs. A recipient runs `python3 verify.py <directory>`; how the directory
  reaches them is the operator's business, and a container format would be a
  second thing to verify.
- **The verifier decides nothing about the claim.** It answers whether the
  evidence in front of a triager is the evidence this harness produced. Whether
  the argument built on it is sound is what a triager is for.
- **The redaction rules are the six 034 wrote.** This ticket gave each of them
  two witnesses and fixed three patterns that could not pass the second; it did
  not add a rule. What is redacted is another person's contact details,
  authorization material and identifiers -- not every string that might be
  sensitive in some deployment.
- **A chain bundle names its members and does not contain them.** Every
  transition carries the member's label, and the four report sections that are
  facts about one validated Finding stay in that Finding's own bundle, for the
  reason 042 already gave.
- **Nothing is submitted anywhere.** The bundle is written to a directory an
  operator names. There is no platform client, no attachment upload and no
  disclosure workflow in this ticket.
