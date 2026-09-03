# 233 — A probe-only Playbook bar asks for two kinds its own trigger refuses

**What to build:** One decision, applied to `http-desync`: either its
`bb:evidence` bar names `transport_parameters_observed` for the roles it gates
`supported` on, or `transport.tls_configuration` comes off its `bb:outputs` so
the bar is only ever read against an `agent_ok` class. Today it declares both
and asks for neither's admissible kind, so one half of the Playbook can never
reach `supported`.

**Blocked by:** nothing.

**Status:** claimed

**Touches:** `src/redkraken/playbooks/http-desync/playbook.md`,
`src/redkraken/migrations/` (one new file, to re-freeze the digest of a document
whose bytes move), `tools/check_wiring.py` (one `OWED` entry), `docs/okf/`.

**PRODUCES:** changed contract -- `http-desync`'s `bb:outputs` no longer names a
`probe_only` class, so its `bb:evidence` bar is only ever read against an
`agent_ok` claim and can be met.

**CONSUMED BY:** `playbook_evidence_unmet(uuid, text)` and
`enforce_playbook_evidence`, which read the bar at every `supported`
transition; `transport_evidence_guard`, which is what refuses the bar today;
`tools/check_coverage.py`, which compares `playbooks.source_sha256` against the
document on disk; `tools/check_wiring.py::vocabulary_gaps` (W9), which will
report the class as emitted by nobody.

**CONSUMES:** `transport_makeability`
(`src/redkraken/migrations/0025_transport_claims.sql:203-233`), which is the
register that decides;
`src/redkraken/playbooks/http-desync/playbook.md`, whose frontmatter is the
bar.

- [x] **The unreachable state is what the criterion is stated against.**
      `transport_evidence_guard()`
      (`src/redkraken/migrations/0025_transport_claims.sql:361-394`, and
      `ENABLE ALWAYS`, so it fires for replication and restore too) returns
      early unless the row is `polarity = 'supports'` and the claim's
      `property_class` is `probe_only` in `transport_makeability`. For such a
      claim it raises unless the cited Observation is
      `transport_parameters_observed`. `http-desync` declares
      `transport.tls_configuration` in `bb:outputs`
      (`src/redkraken/playbooks/http-desync/playbook.md:4`), which is
      `probe_only` (`0025_transport_claims.sql:204`), and its bar (`:13`) asks
      `response_invariant` for `control` and `response_differential` for
      `variant`, both `supports`. Neither edge can be **inserted** for such a
      claim, by any writer, so `playbook_evidence_unmet` can never empty and
      `enforce_playbook_evidence` raises on every `supported` transition.
- [x] **The regression is named and dated.** `http-desync`'s own
      `bb:provenance` (`:12`) records that ticket 101's rewrite moved its
      evidence rows "off `transport_parameters_observed`, which the ledger
      established has no agent-reachable writer by any path". That reasoning is
      right about the *writer* and wrong about this class: for a `probe_only`
      class it is the only kind the guard admits, so the rewrite moved the bar
      from the one admissible kind onto two inadmissible ones. Whichever way
      this ticket goes, that sentence is corrected in the same edit.
- [x] **The other four classes are checked, not assumed.**
      `transport_makeability` (`0025_transport_claims.sql:203-233`) seeds five
      rows: `transport.tls_configuration` and `transport.certificate_trust` are
      `probe_only`, `transport.header_policy` is `agent_ok`,
      `transport.request_framing` and `transport.datagram_transport` are
      `unmakeable`. Every Playbook whose `bb:outputs` names a `probe_only`
      class is read the same way, and the count is stated. `http-desync` is the
      case this ticket was opened on, not necessarily the only one.
- [x] **A test asserts the whole path rather than the trigger.** A claim on
      `transport.tls_configuration` under this Playbook, the bar read through
      `playbook_evidence_unmet`, and the `supported` transition either landing
      or refusing by name. The previous shape of this bug — one rule that is
      individually reasonable and a corpus row that is individually reasonable,
      collectively unsatisfiable — is caught by neither end alone, which is why
      ticket 166's reachability sweep missed it.
- [x] **What the choice costs is written down, either way.** Naming
      `transport_parameters_observed` keeps the Playbook gradeable but ties its
      bar to a Receipt only the runtime's own measurement can produce, so no
      agent-filed edge helps. Dropping `transport.tls_configuration` from
      `bb:outputs` keeps the bar agent-reachable but stops the Playbook
      claiming the TLS leaf it was written for. Ticket 166 took the analogous
      decision for five Playbooks on 2026-08-24 and recorded the loss; this one
      does the same rather than choosing silently.

## What was measured, 2026-09-02

Every fact the criteria state, re-measured on this tree rather than carried
from the review that filed the ticket.

**The guard.** `transport_evidence_guard()` is at
`src/redkraken/migrations/0025_transport_claims.sql:361`, its trigger at `:392`,
and `ALTER TABLE hypothesis_evidence ENABLE ALWAYS TRIGGER
transport_evidence_guard` at `:395`. The two early returns are `:370`
(`IF NOT FOUND OR m.makeability <> 'probe_only' THEN RETURN NEW`) and the
polarity test above it; the refusal is `:373-375`
(`IF o.kind <> 'transport_parameters_observed' THEN ... 'transport evidence
refused: % needs a transport_parameters_observed '`). So for a claim whose
Property class is `probe_only`, every `supports`-polarity edge must cite a
`transport_parameters_observed` Observation, and a `refutes` edge is untouched.

**The register.** `transport_makeability` seeds five rows at `:203-233`:
`transport.tls_configuration` `probe_only` (`:204`),
`transport.certificate_trust` `probe_only` (`:211`),
`transport.header_policy` `agent_ok` (`:216`),
`transport.request_framing` `unmakeable` (`:221`) and
`transport.datagram_transport` `unmakeable` (`:228`).

**The bar.** `src/redkraken/playbooks/http-desync/playbook.md:4` declares
`bb:outputs: ["transport.header_policy", "transport.tls_configuration"]` and
`:13` declares three evidence rows: `refuted`/`variant`/`response_differential`/
`refutes`, `supported`/`control`/`response_invariant`/`supports`, and
`supported`/`variant`/`response_differential`/`supports`. Both `supported` rows
carry `polarity: supports`, and neither names
`transport_parameters_observed` -- so on a `transport.tls_configuration` claim
both are refused at insert and `playbook_evidence_unmet` can never empty.

**The count criterion 3 asks for is one.** Read off the compiled corpus rather
than off the corpus directory:

```
NO_COLOR=1 uv run python -c "from redkraken import playbook; ..."
  playbooks naming a probe_only or unmakeable transport class: 1
  http-desync ['transport.header_policy', 'transport.tls_configuration']
```

`transport.certificate_trust`, `transport.request_framing` and
`transport.datagram_transport` are named by no Playbook's `bb:outputs` at all,
which is why W9 already carries `transport.certificate_trust` as
`owed:116` (`tools/check_wiring.py:326-327`). So `http-desync` is not merely the
case the ticket was opened on: it is the whole of it.

**The bar cannot be made per-class.** An evidence row is
`{to_status, role, kind, polarity, min_count}` and carries no property class, so
one bar is read against every class the Playbook emits. That is the fact that
decides this ticket, and it is why the two options are not symmetric.

## The decision, taken 2026-09-02

**`transport.tls_configuration` comes off `bb:outputs`.** Not the other option,
and the reason is the measurement above: the bar is Playbook-wide. Naming
`transport_parameters_observed` for the two `supported` roles would make the bar
ask for a measurement Receipt on the `transport.header_policy` claim too --
`transport_parameters_observed` needs a measurement receipt
(`0025_transport_claims.sql:304-308`) and this Playbook's reading is an ordinary
agent-lane response differential. So option A repairs the half that cannot work
by breaking the half that does. Option B leaves one working half.

**What it costs, stated rather than skipped.** The Playbook stops claiming the
TLS leaf it was written for. That is a smaller loss than it reads as, because
`0025_transport_claims.sql:204` is the register saying why the claim was never
sound: *the agent terminates TLS against the interception proxy*, version and
cipher matched the origin by coincidence and ALPN did not. A
`transport.tls_configuration` Finding filed off this Playbook's reading would
have described the proxy. What is being removed is a claim that could not have
been true, not a capability.

**What it owes.** After this, no Playbook emits
`transport.tls_configuration`, so W9 reports the same gap it already reports for
`transport.certificate_trust`. It is **not** owed to ticket 116: 116 widens
`reject_non_agent_evidence` and `reject_non_agent_citation` so a `probe_only`
claim may reach a Finding, and leaves `transport_evidence_guard` alone -- so
after 116 the class still needs a `transport_parameters_observed` Observation
and still has no Playbook step that files one. The owed rule is filed as
**ticket 237** -- a Playbook step that files a `transport_parameters_observed`
Observation off the runtime's own unintercepted measurement -- and W9's `OWED`
registry points the new gap there, beside the `transport.certificate_trust` gap
it already carries.

## Why

Ticket 166 was opened on the claim that Playbook evidence bars gate `supported`
on Observation kinds no verb can write, and closed on 2026-09-02 having
established the opposite for the writer question: an evidence edge filed with
the proposal that mints a claim, while the claim is still `proposed`, is counted
by `playbook_evidence_unmet` at the `supported` transition, so every kind a
proposal can mint is reachable and only the writer differs.

That sweep asked which *writer* could produce a kind. It did not ask which kinds
a claim's own `property_class` admits, and there is a second `BEFORE INSERT`
trigger on `hypothesis_evidence` that decides exactly that. So one bar in the
corpus is still unreachable, and the reason is neither provenance nor the
replay's kind derivation — it is a per-property-class rule that predates both.
166's review pass found it; 166 could not take it, because taking it would have
been its ninth acceptance criterion against a ceiling of six.

This blocks ticket 84. 84 grades every in-scope Playbook at the text it ships
and requires precision and recall to come from door runs. A graded campaign
against `http-desync`'s `transport.tls_configuration` half would return `fail`
and measure this trigger rather than the Playbook — which is precisely what
ticket 166's 2026-08-24 comment recorded happening to five other Playbooks, at a
cost of 330 million budget units, before those five were narrowed.

## Notes

Not ticket 116's problem. 116 widens `reject_non_agent_evidence` and
`reject_non_agent_citation` so the Observation a `probe_only` claim rests on may
also be cited by the Finding that rests on it. It leaves
`transport_evidence_guard` alone, so after 116 a `probe_only` claim still needs
a `transport_parameters_observed` Observation and this Playbook's bar still asks
for two other kinds. The two tickets are adjacent and neither closes the other.

Not ticket 145's problem either, for the same reason 166 gave: every kind named
here is in the vocabulary with an `allowed_provenance` some writer could
satisfy. What is wrong is that the claim's Property class forbids the kind, not
that the kind forbids the provenance.

## Seam check, 2026-09-03

`PRODUCES:` a changed contract. `http-desync` declares one Property class where
it declared two, so its `bb:evidence` bar is only ever read against an
`agent_ok` claim and can be met.

`WROTE`, each far end opened in source:

- `bb:outputs` at `src/redkraken/playbooks/http-desync/playbook.md:4` --
  **READ BY** `redkraken.playbook::_playbook` (`playbook.py:399`), reading
  `fields["bb:outputs"]` at `:428`; `redkraken.okf::_playbook_concept`
  (`okf.py:164`), reading `one.property_classes` at `:201`; and
  `tools/check_wiring.py::vocabulary_gaps` (`:1667`), reading
  `body.front.get("bb:outputs", [])`. Three readers, all on the path: the
  compiler, the bundle writer and the W9 gate. W9's prose arm does not fire on
  the class name this ticket left in `bb:provenance`, because `CLASS_TOKEN`
  matches backticked names only and that sentence carries none.
- the `playbook_outputs` row the migration deleted -- **READ BY**
  `playbook_fixture_binding` (`0036_playbook_tests.sql:122`), which joins it
  against `fixture_classes` to decide `in` or `out`; `playbook_candidates`
  (`20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql:278`);
  `playbook_promotion_evidence` (`0035_corpus_promotion.sql:70`);
  `check_playbook_integrity` (`0035_corpus_promotion.sql:229`), whose
  `output_outside_category` arm joins it against `property_classes`; and
  `record_playbook_test_run`
  (`20260914T000000Z__a_fixture_is_reached_by_address_not_by_name.sql:405`
  and `:515`). The first of those is the reader the ticket's decision block did
  not price -- see `## Build findings` below.
- `playbooks.source_sha256` -- **READ BY**
  `tools/check_coverage.py::catalogue_errors` (`:245-257`), reading
  `coverage.registered.get(one.path)` against `one.sha256` and reporting
  `registered at <12 chars> and ships <12 chars>` on a mismatch.
- `playbooks.version` -- **READ BY** `freeze_playbook_selection`
  (`20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql:448-451`),
  which stamps it onto a `playbook_selections` row and raises when a row
  arrives carrying a different one. `TransportBarTest.stage` inserts that row
  by hand for both halves, so this reader ran against the re-frozen digest
  rather than being asserted about.
- `playbooks.provenance` -- **READ BY** `redkraken.okf::_playbook_concept`
  (`okf.py:254`), which is the bundle's `## Provenance` section, and by
  **the `NOT NULL` and `CHECK (provenance <> '')` constraints** at
  `20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql:63`
  and `:583`. No SQL function selects the column; the bundle and those two
  constraints are the whole of its readership, and the second is why an empty
  provenance is not a silent option.
- `OWED_GAPS["W9 transport.tls_configuration"] = "owed:237"`
  (`tools/check_wiring.py:199`) -- **READ BY**
  `tools/check_wiring.py::register_errors` (`:2037`), in both directions: a gap
  with no row prints `unregistered: ...`, and a row with no gap is a defect of
  its own. That second direction is why this row could not have been added
  before the class stopped being emitted, and it is what makes the row a debt
  rather than a comment.
- `docs/okf/playbooks/http-desync.md` -- **READ BY**
  `tests.test_okf.FreezeTest::test_the_committed_bundle_is_current`, comparing
  `okf.build(ROOT)` against the committed tree file by file.

`READ`, mirrored:

- `transport_makeability` -- **WRITTEN BY** the seed at
  `0025_transport_claims.sql:203-233`, five rows, untouched here.
- `transport_evidence_guard` -- **WRITTEN BY**
  `0025_transport_claims.sql:361`, its trigger at `:392` and `ENABLE ALWAYS` at
  `:395`. Untouched: it is the rule the corpus row was wrong about, not the
  thing that was wrong.
- this Playbook's `playbook_evidence` rows -- **WRITTEN BY** ticket 101's
  corpus mirror,
  `20261219T000000Z__the_corpus_is_rewritten_and_refrozen.sql`. Left exactly as
  they stand: the bar is correct for the class that remains, which is the whole
  of option B.

No `NOBODY`. One forward reference, recorded rather than redeemed: the W9 gap
this ticket opens is owed to ticket 237, which is `open` and whose `Blocked by`
line names 233 and 116.

**Name drift, checked.** `grep -rn '^bb:outputs:' src/redkraken/playbooks/*/playbook.md`
piped through `grep -c tls_configuration` prints `0` -- no Playbook declares the
class in any spelling. The 51 remaining mentions in `src`, `tools` and `tests`
are the register, the class vocabulary
(`roster.PROPERTY_CLASSES` at `roster.py:349-411`, where the class still
exists), ticket 88's fixture row, the W9 `OWED` row, prose in nine migration
headers, and this ticket's own tests.

**Unit and type drift.** Nothing numeric crossed. The one typed value is a
64-hex digest, and both digest columns carry
`CHECK (... ~ '^[0-9a-f]{64}$')`, which the `UPDATE` satisfied.

**The live run, and the case it reached.** There is no `live-inputs.md` in this
effort, so there was no block to replay; ticket 236's bar recorded the same
absence two days ago. The run was against a real cluster --
`rk2-test-pg` on `127.0.0.1:55433`, `RK_TEST_DATABASE=rk2_t233live`, the whole
corpus applied from empty by `rk db migrate` -- and it read the five far ends
that matter, not a green exit:

```
emits transport.tls_configuration: []
emits transport.header_policy:   ['playbooks/browser-framing/playbook.md', 'playbooks/http-desync/playbook.md']
desync verdict: [('untested', '59 fixture(s) in the binding have no run at this text')]
desync in-side own pairs: ['header-policy-pair']
tls-pair in for: []
frozen digest: [('e80023c5beab', 'aa8147bb07ad')]
integrity: []
```

The third line is the one worth reading twice: the verdict is `untested` for the
ordinary reason every un-run Playbook is, **not** the "no own-pair fixture
declares a class this playbook declares as an output" clause. That is the
difference between this removal costing a fixture and this removal breaking
ticket 88's grading, and it is why the fourth line is asserted in the migration
as well as here.

- [seam] clean -- nothing raised

## Build findings, 2026-09-03

- [build] **The removal strands ticket 88's `tls-configuration-pair` fixture.
  `playbook_fixture_binding` (`0036_playbook_tests.sql:122`) is derived from
  `playbook_outputs` against `fixture_classes`, so with no Playbook declaring
  the class that fixture becomes `side = 'out'` for all fifty Playbooks and
  grades nobody. The ticket's decision block priced the lost claim and did not
  name this.** -- required -- NOW. Discharged three ways rather than by a
  sentence: the migration header states the cost, the migration asserts that
  `http-desync` still binds exactly one `in`-side own pair, and
  `TransportBarTest.test_the_fixture_the_removed_class_declared_now_grades_nobody`
  asserts both halves of it. That test was genuinely red before the change --
  it is in the three-failure run recorded under `## Resolution` -- so the cost
  is checked, not described.

Why it is a cost and not a regression, measured rather than argued:
`playbook_fixture_binding` is TOTAL, so `http-desync` keeps a binding of 60
fixtures either way, and `header-policy-pair` keeps it holding one `in`-side
own pair. `playbook_test_verdict`
(`20260824T000000Z__a_playbook_earns_stable_against_fixtures_it_did_not_pick.sql:621`)
therefore never reaches the clause that refuses a Playbook with no own-pair
fixture -- the live read above is that clause not firing. What is lost is one
fixture's usefulness, and the ticket that can restore it is 237: a Playbook step
that emits the class puts the fixture back `in` with no schema change at all.

## Resolution, 2026-09-03

`http-desync` declares one Property class, `transport.header_policy`, and its
`bb:evidence` bar is now only ever read against an `agent_ok` claim. The seam is
`bb:outputs` against `transport_evidence_guard`: an evidence row carries no
Property class, so one bar is read against every class a Playbook names, and a
Playbook that names a `probe_only` class has a bar that
`transport_evidence_guard` refuses at insert. The corpus-wide invariant is
asserted by
`TransportBarTest.test_no_playbook_declares_a_probe_only_class_its_own_bar_cannot_support`,
which joins `playbook_outputs` against `transport_makeability` and
`playbook_evidence` and requires the result to be empty; the same invariant is
asserted a second time inside
`20270112T000000Z__a_probe_only_class_comes_off_the_bar_it_cannot_meet.sql`, so
a future corpus migration that reintroduces the shape fails at apply time
rather than at the next test run. Six further tests carry the ends the
invariant cannot: that both `probe_only` classes are now emitted by nobody, that
the `agent_ok` half reaches `supported` with both bar edges landing, that a
`probe_only` claim still cannot carry either kind the bar asks for, that
`hypothesis_transition_refusal` no longer names this Playbook for the class it
emits, and what the removal costs in fixture rows.

**Red:** `AssertionError: Lists differ: [] != [('playbooks/http-desync/playbook.md', 'tr[162 chars]al')]` / `First extra element 0: ('playbooks/http-desync/playbook.md', 'transport.tls_configuration', 'control', 'response_invariant')`
**Mutated:** `'probe_only'` -> `'agent_ok'` in the seam test's `WHERE` clause -> `AssertionError: Lists differ: [] != [('playbooks/browser-framing/playbook.md', 'transport.header_policy', 'control', 'header_policy_observed'), ... 4 rows]`
**Forward references left standing:** 233 -> 237

Nothing in the ticket turned out wrong. One thing was missing from it, and it
is the `## Build findings` entry above: criterion 5 asks what the choice costs,
and the fixture strand is a cost the decision block did not name.

## Bar, 2026-09-03

1. **Every acceptance criterion is ticked.** `grep -c '^- \[ \]' <ticket>`
   prints `0`; `grep -c '^- \[x\]' <ticket>` prints `5`.
2. **The seam test passes, read by name.** This effort's spec carries no
   `## Verify command`, so the tests are named in full, with
   `CleanCreationTest` in the invocation as `docs/agents/testing.md` requires.

   ```
   NO_COLOR=1 RK_TEST_SUPERUSER_URL="postgres://postgres:...@127.0.0.1:55433/postgres" \
   RK_TEST_DATABASE=rk2_t233bar uv run python -m unittest -v \
     tests.test_database.CleanCreationTest tests.test_database.TransportBarTest
     ... (9 CleanCreationTest lines, all ok)
     test_a_probe_only_claim_cannot_carry_either_kind_its_bar_asks_for ... ok
     test_no_playbook_declares_a_probe_only_class_its_own_bar_cannot_support ... ok
     test_the_bar_is_met_for_the_class_this_playbook_emits ... ok
     test_the_bar_stays_unmet_for_a_probe_only_claim_and_the_gate_says_so ... ok
     test_the_fixture_the_removed_class_declared_now_grades_nobody ... ok
     test_the_gate_the_runtime_is_handed_no_longer_names_the_playbook ... ok
     test_the_probe_only_classes_are_declared_by_no_playbook_at_all ... ok
     Ran 16 tests in 27.561s
     OK
   ```

   The named test for criterion 4 is
   `test_no_playbook_declares_a_probe_only_class_its_own_bar_cannot_support`,
   and for the `## Build findings` entry it is
   `test_the_fixture_the_removed_class_declared_now_grades_nobody`.
3. **Forward references redeemed.**
   `grep -rn 'ticket 233\|Ticket 233' docs/specs/production-harness-v2/`, this
   ticket excluded, prints 8 lines.
   `166-...md:447`, `:481` and `:514` are inside `## Resolution, 2026-09-02`;
   `166-...md:762` is inside `## Review findings, 2026-09-02 -- cycle 1`;
   `235-...md:444` and `:478` are inside `## Bar, 2026-09-02`. All six are
   history by this line's own rule. The remaining two are prose heads and
   neither is a debt: `166-...md:11` is that ticket's `**What to build:**`
   block naming its successor, and `237-...md:50` is that ticket's `## Why`.
   No `CONSUMED BY`, `CONSUMES` or `deferred to` on any of the eight, and
   nothing was owed to this ticket. 237's `**Blocked by:**` line names `233`
   by number, which is a frontier edge rather than a seam debt -- and it is
   what kept 237 from being built first.
4. **Existing tests still pass, none skipped, deleted or weakened.**

   ```
   NO_COLOR=1 uv run python -m unittest -q \
     tests.test_playbook tests.test_okf tests.test_fixture
     Ran 150 tests in 42.493s
     OK
   NO_COLOR=1 uv run python -m unittest -q tests.test_wiring tests.test_coverage
     Ran 70 tests in 43.058s
     OK
   RK_TEST_DATABASE=rk2_t233 uv run python -m unittest -q \
     tests.test_database.CleanCreationTest \
     tests.test_database.PlaybookSelectionTest \
     tests.test_database.PlaybookCorpusSelectionTest \
     tests.test_database.PlaybookEvaluationTest \
     tests.test_database.PlaybookEvaluationCommandTest \
     tests.test_database.HypothesisHuntTest \
     tests.test_database.TransportBarTest
     Ran 162 tests in 349.831s
     OK
   ```

   The four gates, each as a program:

   ```
   PYTHONPATH=$PWD python3 -s tools/check_audit.py           rc=0
   PYTHONPATH=$PWD python3 -s tools/check_wiring.py          rc=0
     W9 vocabulary                3 owed   property classes 61  emitted 57  unmakeable 2
     register                    42 rows   tickets 6  findings 42  distinct 42
   PYTHONPATH=$PWD python3 -s tools/check_baseline.py        rc=0
     baseline ok: classifications=10 regressions=7 adapters=11 artifacts=223 frozen
   PYTHONPATH=$PWD/src:$PWD python3 -s tools/check_coverage.py  rc=0
     catalogue               51   skills 6  references 86
   ```

   `W9 ... 3 owed` is 2 owed plus this ticket's new row, and `emitted 57` is 58
   minus this class. The full `tests/test_database.py` was not run: 1587 tests
   by `TestLoader().loadTestsFromName` and over thirty minutes, against a change that deletes one corpus row and
   re-freezes one Playbook. What was run is every database class that reads the
   Playbook catalogue, the fixture binding, the transport register or the
   evidence guard, plus `CleanCreationTest`, which applies the whole corpus
   including the new migration from empty.

   `git diff --numstat`: `tests/test_database.py` 310 added and 0 deleted,
   `tools/check_wiring.py` 18 added and 0 deleted,
   `src/redkraken/playbooks/http-desync/playbook.md` 11 added and 8 deleted,
   `docs/okf/playbooks/http-desync.md` 4 added and 5 deleted. Nothing deleted
   in any test file, no `.skip` added, no assertion removed --
   `git diff | grep -E '^\+.*skip|^-.*assert'` prints one line and it is this
   ticket's own prose, "stated rather than skipped".
5. **The diff is what the ticket asked for.**
   `git status --short --untracked-files=all` holds seven paths and this commit
   names all seven: the four `Touches` files
   (`src/redkraken/playbooks/http-desync/playbook.md`, the new migration
   `src/redkraken/migrations/20270112T000000Z__a_probe_only_class_comes_off_the_bar_it_cannot_meet.sql`,
   `tools/check_wiring.py`, `docs/okf/playbooks/http-desync.md`), this ticket's
   test file `tests/test_database.py`, this ticket's own file, and ticket 237's
   file, which is the owner of the gap criterion 5 records and was cut by this
   session under `hold-the-line`'s TICKET verdict. No build artifacts, no
   concurrent ticket's work: the tree was clean at `d0556465` before this
   session's first edit.
6. **The blocks.** `grep -c '^## Resolution' <ticket>` prints `1`,
   `grep -c '^## Bar' <ticket>` prints `1`, `grep -c '^## Handoff' <ticket>`
   prints `0`.

**Judgement, red and mutated.** Both watched in this session. The red was
watched twice: once before any code existed, giving the `Red:` line above, and
once again with the new migration moved aside after the frontmatter change had
landed, which produced three failures and is what proves the fixture-cost test
discriminates as well as the seam test. The mutation flipped the reader's
`'probe_only'` literal to `'agent_ok'` and returned four rows; it was reverted
in the same minute.

**Judgement, no unexplained NOBODY.** Seven written values, seven far ends, all
of them code or a constraint that was made to fire. The one debt is the W9 gap,
recorded as ticket 237 with its status read off the file rather than assumed.

**Judgement, the live run reached this ticket's case.** The far-end read is
pasted under `## Seam check` above, against a database built from empty on
`rk2-test-pg`. It reached the case rather than the happy path: the two
`probe_only` classes are emitted by nobody, the removed class binds no fixture,
the digest in the catalogue is the digest the document now hashes to, and
`check_playbook_integrity()` returns no row. The spec's `Load` section names no
figure for this path.

**Judgement, Rule 3b.** No double was injected. `TransportBarTest` opens a real
Program through `program.run`, claims real Hypotheses through the real verbs,
inserts a real `playbook_selections` row past `freeze_playbook_selection`, and
reads the refusal out of `hypothesis_transition_refusal`. The only thing it
does not use is a live door, and it does not need one: the bar is read from the
catalogue, not from a response.
