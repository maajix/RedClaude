# 46 — Evaluate and promote one Playbook

**What to build:** Run one Playbook against independently authored positive and adversarial fixtures and permit stable promotion only when this exact text is grounded, reproducible and precise.

**Blocked by:** 35 — Execute a structured Test through the replay Lane; 45 — Select one Playbook by Property class.

**Status:** resolved

**Deviation on criterion 6:** the door is not on the path. The evaluator goes through
the production Program opener, configuration reader, scope compiler, work callable and
counting functions, but its fixtures listen on loopback and the door refuses to dial a
loopback address -- at compile time in `scope.address_refusal` and again at dial time in
`authorize_identity_egress_address`. That refusal is what keeps a Program configuration
from pointing the harness at the machine it runs on, so it was not relaxed for a test.
A machine with no Agent boundary therefore evaluates end to end and files honest zeroes,
and the route by which a real Agent reaches a fixture through the door is ticket 78.

- [x] Fixture ground truth and class binding are independent of the Playbook author and include at least one relevant positive and one meaningful out-of-class negative.
- [x] Each repeat records Playbook hash, fixture hash, selected Skills, grounded canonical claims, true positives, false positives and ungrounded claims.
- [x] Promotion requires the configured repeated positive result, zero disqualifying ungrounded/off-class claims and runtime provenance for this exact text.
- [x] A Playbook that always fires, under-declares outputs, lacks a control or is selected only because of its own fixture data fails.
- [x] Editing, expiry or a later failing verdict demotes the Playbook from stable without deleting historical test runs.
- [ ] The end-to-end evaluator uses the production Agent, proxy, Test and promotion seams against synthetic fixtures. **Partial:** every seam but the proxy, per the deviation above. Ticket 78 closes it.

## Comments

Implemented on 2026-08-16.

### The corpus

`src/redkraken/fixture.py` compiles `src/redkraken/fixtures/` the way `playbook.py`
compiles cards: a `fixture.md` declaring `bb:kind`, `bb:classes`, `bb:subject`,
`bb:facts`, `bb:identities` and `bb:provenance`, and an `app.py` that is digested and
never imported by the compiler. Two fixtures ship -- `object-ownership-pair` as the
positive and `error-detail-pair` as the out-of-class negative, which contains a real
defect of a family no authorization Playbook declares. A fixture may not name the
Playbooks it tests; that key is refused, which is what makes criterion 1's independence
a rule rather than a convention.

### The rule

`20260824T000000Z__a_playbook_earns_stable_against_fixtures_it_did_not_pick.sql` adds
the fixture catalogue, `fixture_classes`, `evaluation_programs`, the false-positive and
ground-truth columns on `playbook_test_runs`, `playbook_test_run_skills`, the R5
refusals that hold a filed run to the corpus it claims, the evidence exclusion for
evaluation Programs, the repeat minimum and false-positive clauses in
`playbook_test_verdict`, `demote_playbooks()`, `playbook_demotions` and nine arms of
`check_playbook_tests`.

### Criterion 4 says "fails"; two of its four cases are `untested`

The criterion names four ways to fail. Two of them are a `fail` verdict: a Playbook that
always fires makes a claim on the secure half and is refused by clause B, and one
selected only because of its own fixture data cannot promote at all, because
`playbook_promotion_evidence` no longer counts an evaluation Program. The other two --
"under-declares outputs" and "lacks a control" -- come out `untested`, and that is
deliberate.

A Playbook that under-declares fires outside its own `bb:outputs`. That claim can be
true: the fixture may genuinely contain the class. Scoring it against the Playbook would
punish a correct finding for a gap in a document somebody else owns, so it is reported
as `fixture_groundtruth_gap` against the fixture and the Playbook's `in`-side credit
simply does not accrue -- clause 4 then takes the median discriminating finding under 1.
"Lacks a control" is stronger: with no secure twin there is no `NOT admitted` conjunct
to evaluate, `discriminating_tp` is 0 by construction, and clause 1 answers `untested`
because `n_in_pair = 0`. Both land where 036 put them: "an unevaluable predicate never
produces a pass". Neither state can promote, which is what the criterion is protecting;
what differs is that the harness says "this was not measured" instead of claiming a
measurement it did not take.

Proved by `test_a_playbook_that_claims_a_class_the_ground_truth_does_not_contain_fails`,
`test_repeats_that_find_nothing_pull_the_median_under_one` and
`test_a_target_with_no_control_earns_no_discriminating_finding`.

### What was built beyond the six criteria, and why

`playbook_demotions` is not in criterion 5, which asks only that a demotion happen
"without deleting historical test runs". A demotion with no record is a Playbook that
was stable last week and is a draft today with nothing to say why, and the three causes
the criterion lists are exactly three different answers. The table is append-only under
`reject_mutation_unless_purging`, like every other ledger here.

Three arms of `check_playbook_tests` are new -- `stable_playbook_expired`,
`test_run_for_superseded_fixture` and `test_run_froze_no_skills` -- and one of 036's is
gone. The repo's convention is that a rule the schema enforces gets a standing check
that reports the states already in the database when it lands; each new arm reports a
state one of this migration's own refusals makes unreachable going forward.

`kind = 'third_party'` and the `bb:coverage` key implement 0036's existing contract
rather than a new one: `fixtures.kind` has been `CHECK (kind IN ('own_pair',
'third_party'))` since that migration, with two constraints requiring
`upstream_list_size` and `converted` on one branch and forbidding them on the other. A
compiler that could only write `own_pair` would leave half of a shipped schema
unwritable. No third-party fixture ships.

### Where the proof is

- `tests/test_fixture.py` -- the compiler's refusals, the two digests, and the
  database-free half of the evaluator: what listens is what was digested, and the
  document written for it is one `config.load` and `scope.compile_policy` accept.
- `tests/test_database.py::PlaybookEvaluationTest` -- the rule: the binding, the frozen
  texts and where they come from, the verdict clauses, the evidence exclusion with its
  negative control, the sensitivity clause with its own, and the three demotion causes.
- `tests/test_database.py::PlaybookEvaluationCommandTest` -- the command, end to end:
  twelve Programs opened, each marked before its work ran, each probed through the port
  in its own compiled scope while the fixture was listening, six repeats filed at the
  texts that were served, `untested` after one fixture and `fail` after both, and no
  promotion evidence from any of it.
- `tests/test_cli.py::PlaybookCommandTest` -- the command line: three inputs, no
  configuration file, and a fixture outside the corpus refused before a connection is
  opened.
