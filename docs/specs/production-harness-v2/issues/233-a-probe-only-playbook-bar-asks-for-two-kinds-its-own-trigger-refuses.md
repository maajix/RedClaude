# 233 — A probe-only Playbook bar asks for two kinds its own trigger refuses

**What to build:** One decision, applied to `http-desync`: either its
`bb:evidence` bar names `transport_parameters_observed` for the roles it gates
`supported` on, or `transport.tls_configuration` comes off its `bb:outputs` so
the bar is only ever read against an `agent_ok` class. Today it declares both
and asks for neither's admissible kind, so one half of the Playbook can never
reach `supported`.

**Blocked by:** nothing.

**Status:** resolved

**Touches:** `src/redkraken/playbooks/http-desync/playbook.md`,
`src/redkraken/migrations/` (one new file, to re-freeze the digest of a document
whose bytes move), `tools/check_wiring.py` (one `OWED` entry), `docs/okf/`,
`tests/test_database.py` (the test criterion 4 asks for; added by review cycle 1,
which found the line omitted it). Review cycle 1 also touched
`src/redkraken/playbooks/http-desync/references/`, for the reason recorded under
`## Review findings`.

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
      `probe_only`, `transport.header_policy` is `agent_ok` (`:217`),
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
`transport.header_policy` `agent_ok` (`:217`),
`transport.request_framing` `unmakeable` (`:222`) and
`transport.datagram_transport` `unmakeable` (`:229`).

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
  (`20260918T000000Z__an_edit_retires_the_evidence_that_blessed_it.sql:57`,
  reading it at `:87`); `playbook_promotion_evidence`
  (`20260824T000000Z__a_playbook_earns_stable_against_fixtures_it_did_not_pick.sql:302`,
  reading it at `:308` beside `s.outcome = 'produced'`);
  `check_playbook_integrity`
  (`20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql:653`),
  whose `output_outside_category` arm at `:700` joins it against
  `property_classes`; `record_playbook_test_run`
  (`20260914T000000Z__a_fixture_is_reached_by_address_not_by_name.sql:405`
  and `:515`); and `settle_playbook_selections`
  (`20260925T010000Z__a_finished_run_says_what_its_playbook_produced.sql:147`
  and `:155`).

  Three of these were first cited at bodies that no longer run. Migrations apply
  in filename order (`src/redkraken/migrate.py:206`), so the last
  `CREATE OR REPLACE` wins: `playbook_candidates`, `playbook_promotion_evidence`
  and `check_playbook_integrity` are the bodies cited above, not the
  `20260823T000000Z…:278`, `0035_corpus_promotion.sql:70` and
  `0035_corpus_promotion.sql:229` this block first named. The functions are
  real readers either way; the citations were superseded, and are corrected
  here by review cycle 1.

  `playbook_fixture_binding` is the reader the ticket's decision block did not
  price -- see `## Build findings` below. `settle_playbook_selections` is the
  second, and review cycle 1 is where it was found. It settles a
  `playbook_selections` row `produced` or `exhausted` by asking whether a
  Hypothesis of a class the Playbook declares exists on the subject, so after
  the removal a `http-desync` run that minted only a
  `transport.tls_configuration` claim settles `exhausted` where it settled
  `produced`. Both directions of that are what option B asked for and neither
  is a regression: `playbook_promotion_evidence` (`:308`, `s.outcome =
  'produced'`) stops crediting this Playbook for a TLS claim it no longer
  makes, and `playbooks_by_metadata` (`0032_playbooks.sql:420`,
  `s.outcome = 'exhausted'`) stops re-offering it on a subject where it
  produced none of its declared class. The `agent_ok` half is untouched: a run
  that mints the `transport.header_policy` claim the Playbook is now written
  for still settles `produced`.

  **Reads skipped, counted rather than implied.** At least thirteen further
  SQL reads of `playbook_outputs` exist (`0032_playbooks.sql:402`, `:612`,
  `20260823…:700`, `20260824…:308`, `:449`, `:559`, `20260918…:87`,
  `20260925…:147`, `:155`, `20260927…:471`, `20261004…:234`, `:276`,
  `20261220…:107`). They are the same six functions read at their second and
  third call sites plus the promotion and integrity arms; none is a distinct
  far end, which is why the list above names functions rather than lines.
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
  (`tools/check_wiring.py:345`) -- **READ BY**
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

**Name drift, checked, and corrected by review cycle 1.**
`grep -rn '^bb:outputs:' src/redkraken/playbooks/*/playbook.md` piped through
`grep -c tls_configuration` prints `0` -- no Playbook declares the class in any
spelling.

At the build commit the 51 remaining mentions in `src`, `tools` and `tests`
were bucketed into the register, the class vocabulary
(`roster.PROPERTY_CLASSES` at `roster.py:349-411`, where the class still
exists), ticket 88's fixture row, the W9 `OWED` row, prose in nine migration
headers, and this ticket's own tests. That accounts for about 36 of the 51. The
count was right and the enumeration was not; the fifteen it missed are the six
`analyse-source` sink packs carrying a `## transport.tls_configuration`
heading, three mentions in this Playbook's own `references/`,
`src/redkraken/evaluation.py:366`,
`src/redkraken/fixtures/tls-configuration-pair/app.py:10` and `:83`,
`playbook.md:12` (the `bb:provenance` sentence), and `tests/test_fixture.py:543`.
The "nine migration headers" bucket also included `20261219T000000Z…:783`,
which is a `playbook_outputs` INSERT row rather than prose.

Re-measured after this review's own repair, the count is **53**, and the two it
gained are the correction sentences added to the two reference pages below. The
bare `tls_configuration` spelling adds five more, so "in any spelling" is 58
where the build commit read 56.

Three of the fifteen were stale rather than merely unlisted, and are corrected
in the review commit:
`src/redkraken/playbooks/http-desync/references/http-attacks-request-smuggling-and-http-desync.md`
and `.../http-attacks-http-2-downgrading.md` still said in the present tense
that `transport.tls_configuration` is what this Playbook asks. They are
maintainer material and reach no model -- `read_corpus`
(`tools/check_wiring.py:1247`) globs only `*/playbook.md` and `*/SKILL.md`, and
the generated bundle stub `docs/okf/references/http-desync--http-attacks-http-2-downgrading.md:16`
says so outright -- which is why nothing caught them, and why correcting them
changes no digest and no bundle. Criterion 2's "that sentence is corrected in
the same edit" was met for `bb:provenance` and missed for these two.

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
  the class that fixture becomes `side = 'out'` for all 51 Playbooks and
  grades nobody. The ticket's decision block priced the lost claim and did not
  name this.** -- required -- NOW. Discharged three ways rather than by a
  sentence: the migration header states the cost, the migration asserts that
  `http-desync` still binds exactly one `in`-side own pair, and
  `TransportBarTest.test_the_fixture_the_removed_class_declared_now_grades_nobody`
  asserts both halves of it. That test was genuinely red before the change --
  it is in the three-failure run recorded under `## Resolution` -- so the cost
  is checked, not described.

Why it is a cost and not a regression, measured rather than argued:
`playbook_fixture_binding` is TOTAL, so `http-desync` keeps a binding of 59
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
a corpus that carries the shape at this file's place in apply order fails at
apply time rather than at the next test run. That block runs once, at that
place: a later migration reintroducing the shape applies afterwards and is
never seen by it. The standing form of the invariant is W7
`guard_satisfiability` -- "no guard requires a row another guard refuses" --
which `tools/check_wiring.py:303` carries as `owed:116`; this ticket does not
close it and does not claim to. Review cycle 1 corrected this sentence, which
first read "a future corpus migration that reintroduces the shape fails at
apply time".

Six further tests carry the ends the invariant cannot: that both `probe_only`
classes are now emitted by nobody, that the bar empties for the `agent_ok` half
with both edges landing and one selection pinning the chain, that a
`probe_only` claim still cannot carry either kind the bar asks for, that
`hypothesis_transition_refusal` on the emitted class names only the base rule
(`transition testing -> supported requires a tool receipt`) with no Playbook
conjunct in front of it, and what the removal costs in fixture rows. Review
cycle 1 corrected two overstatements here: the `agent_ok` half does **not**
reach `supported` -- nothing asserts that, and the base rule still refuses the
transition for want of a test-linked receipt -- and the gate never named this
Playbook for the emitted class in the first place, because
`playbook_evidence_unmet` (`0032_playbooks.sql:509-526`) does not read
`playbook_outputs` and `transport_evidence_guard` returns at `0025:370` for any
class that is not `probe_only`. The test that carries that end was renamed to
`test_the_gate_the_runtime_is_handed_names_only_the_base_rule` in the same
edit.

**Red:** `AssertionError: Lists differ: [] != [('playbooks/http-desync/playbook.md', 'tr[162 chars]al')]` / `First extra element 0: ('playbooks/http-desync/playbook.md', 'transport.tls_configuration', 'control', 'response_invariant')`
**Mutated:** `'probe_only'` -> `'agent_ok'` in the seam test's `WHERE` clause -> `AssertionError: Lists differ: [] != [('playbooks/browser-framing/playbook.md', 'transport.header_policy', 'control', 'header_policy_observed'), ... 4 rows]`
**Forward references left standing:** 233 -> 237

One thing was missing from the ticket, and it is the `## Build findings` entry
above: criterion 5 asks what the choice costs, and the fixture strand is a cost
the decision block did not name.

**Wrong in the ticket, named.** The build session recorded "nothing in the
ticket turned out wrong". Review cycle 1 found three things that were, all of
them citations rather than reasoning, and all corrected in the review commit:

- Criterion 1 is present-tense and its own commit falsified one of its
  citations. "`http-desync` declares `transport.tls_configuration` in
  `bb:outputs` (`playbook.md:4`)" was true at `d0556465` and is false at HEAD:
  `:4` now reads `bb:outputs: ["transport.header_policy"]`. `:13` still holds
  the bar as the criterion describes. The criterion is read as the pre-state it
  was written against.
- Three of the five register line numbers under `## What was measured` were one
  line early (`:216`, `:221`, `:228` for `:217`, `:222`, `:229`), and the
  `:216` cite had shipped into a test docstring.
- Three `playbook_outputs` far ends under `## Seam check` cited function bodies
  that no longer run, because migrations apply in filename order and a later
  `CREATE OR REPLACE` wins.

None of the three changes what the ticket decided; each would have sent the
next reader to the wrong line.

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

   That paste is the build run and is kept as it stands.
   `test_the_gate_the_runtime_is_handed_no_longer_names_the_playbook` in it no
   longer exists: review cycle 1 renamed it to
   `test_the_gate_the_runtime_is_handed_names_only_the_base_rule`, for the
   reason under `## Review findings`. The cycle 1 re-run below carries the
   current names.

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
   by `TestLoader().loadTestsFromName`, and an estimated fifty minutes at the
   batch's measured 2.0 s/test -- "over thirty minutes" was an estimate, not a
   measurement, and is conservative. That omission is not a lowering:
   `docs/agents/testing.md` tier 3 fires on a migration that changes the schema
   broadly, and `20270112T000000Z__…sql` carries no DDL at all -- one `DELETE`,
   one `UPDATE`, three `RAISE` assertions. What was run is every database class
   that reads the Playbook catalogue, the fixture binding, the transport
   register or the evidence guard, plus `CleanCreationTest`, which applies the
   whole corpus including the new migration from empty.

   What that justification first priced was only "one corpus row and one
   re-frozen Playbook", and it was silent on the other half of the diff: 310
   added lines of `tests/test_database.py`. The class-subset batch cannot cover
   those for **ordering**, because it put `TransportBarTest` last while a full
   module run sorts it 84th of 91, ahead of `UnreadyTaskTest`,
   `ValidationCommandTest`, `WaveMeasurementTest` and `WriteDisciplineTest`.
   Review cycle 1 added those four classes to the batch; the re-run is below.

   `git diff --numstat d0556465...HEAD`, all seven lines rather than the four
   this item first quoted -- the three it dropped included the 138-line
   migration, this ticket's only new production file:

   ```
   4	5	docs/okf/playbooks/http-desync.md
   411	6	docs/specs/production-harness-v2/issues/233-...md
   70	0	docs/specs/production-harness-v2/issues/237-...md
   138	0	src/redkraken/migrations/20270112T000000Z__a_probe_only_class_comes_off_the_bar_it_cannot_meet.sql
   11	8	src/redkraken/playbooks/http-desync/playbook.md
   310	0	tests/test_database.py
   18	0	tools/check_wiring.py
   ```

   Nothing deleted in any test file, no `.skip` added, no assertion removed.
   This item first asserted that from an **un-anchored** `git diff`, whose
   result it characterised rather than quoted; anchored, it prints seven lines,
   not one, and one of them is a `-`-side line matching `.*assert`. Review
   cycle 1 replaced it with the scoped command and its verbatim output:

   ```
   git diff d0556465...HEAD -- tests/ tools/ src/ | grep -E '^\+.*skip|^-.*assert'
   +-- What is lost, stated rather than skipped. The Playbook stops claiming the TLS

   git diff d0556465...HEAD -- tests/ | grep -c '^-[^-]'
   0
   ```

   One hit, and it is the migration header's prose. Zero deleted lines under
   `tests/`. No `.skip`, `skipTest`, `skipIf`, `xfail`, `type: ignore`, `noqa`
   or `pragma: no cover` is added anywhere in the diff.
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

   The file list is exact; the sentence "the diff is what the ticket asked for"
   was broader than the list. Criterion 2 asked for one sentence of
   `bb:provenance` to be corrected, and the whole `bb:provenance` was rewritten:
   "unmakeable behind the interception proxy" became "unmakeable", "refused by
   the last section" became "refused by section 4", "under D3" was dropped, and
   "merged technique ledger, which holds one executable reading, two blocked
   ones and two refusals for this slug" became "merged ledger". The rewrite is
   terser, not wrong, and it rides into the agent-facing `## Provenance` of
   `docs/okf/playbooks/http-desync.md`. Review cycle 1 records it here rather
   than restoring the clauses, because the Playbook's bytes are frozen by
   digest and restoring them would cost a second re-freeze migration for
   wording.
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
`check_playbook_integrity()` returns no row. `docs/specs/production-harness-v2/spec.md`
has **no** `## Load` section at all -- the same absence as its missing
`## Verify command` -- so there is no figure for this path to be measured
against. This line first read "the spec's `Load` section names no figure",
which reads as though the section exists and is silent.

**Judgement, Rule 3b.** No double was injected. `TransportBarTest` opens a real
Program through `program.run`, claims real Hypotheses through the real verbs,
inserts a real `playbook_selections` row past `freeze_playbook_selection`, and
reads the refusal out of `hypothesis_transition_refusal`. The only thing it
does not use is a live door, and it does not need one: the bar is read from the
catalogue, not from a response.

What "no double" does not mean, named by review cycle 1: `TransportBarTest.stage`
writes the Task and the `playbook_selections` row by hand rather than earning
them, and its own docstring says why -- after this ticket
`playbooks_by_metadata` filters on `playbook_outputs` and this Playbook no
longer names the `probe_only` class, so the runtime cannot reach the
`probe_only` arrangement at all while the trigger that would refuse it is still
there. That is the reading Rule 3b asks for: the arrangement is staged because
production can no longer produce it, not to dodge a real path. Cycle 1 also
added the selection count both precedents carry, so an empty unmet set cannot
be read as "the bar is met" when it means "no Playbook reached the read".

**Review cycle 1 re-run, 2026-09-03.** The cycle's NOW repairs changed the
migration's bytes, so its checksum moved and every database that had applied it
drifts; the answer the corpus README gives is to migrate from empty, which is
what `CleanCreationTest` does. They also renamed one test, added one assertion
to another, and corrected two maintainer reference pages. The machine lines,
re-run on `rk2-test-pg` (`127.0.0.1:55433`) against fresh databases:

```
RK_TEST_DATABASE=rk2_r233c1 uv run python -m unittest -v \
  tests.test_database.CleanCreationTest tests.test_database.TransportBarTest
  ... (9 CleanCreationTest lines, all ok)
  test_a_probe_only_claim_cannot_carry_either_kind_its_bar_asks_for ... ok
  test_no_playbook_declares_a_probe_only_class_its_own_bar_cannot_support ... ok
  test_the_bar_is_met_for_the_class_this_playbook_emits ... ok
  test_the_bar_stays_unmet_for_a_probe_only_claim_and_the_gate_says_so ... ok
  test_the_fixture_the_removed_class_declared_now_grades_nobody ... ok
  test_the_gate_the_runtime_is_handed_names_only_the_base_rule ... ok
  test_the_probe_only_classes_are_declared_by_no_playbook_at_all ... ok
  Ran 16 tests in 27.465s
  OK

RK_TEST_DATABASE=rk2_r233b uv run python -m unittest -q \
  <the seven classes item 4 names> \
  tests.test_database.UnreadyTaskTest \
  tests.test_database.ValidationCommandTest \
  tests.test_database.WaveMeasurementTest \
  tests.test_database.WriteDisciplineTest
  Ran 199 tests in 368.090s
  OK

NO_COLOR=1 uv run python -m unittest -q tests.test_playbook tests.test_okf tests.test_fixture
  Ran 150 tests in 42.481s
  OK
NO_COLOR=1 uv run python -m unittest -q tests.test_wiring tests.test_coverage
  Ran 70 tests in 42.867s
  OK

PYTHONPATH=$PWD python3 -s tools/check_audit.py              rc=0
PYTHONPATH=$PWD python3 -s tools/check_wiring.py             rc=0
  W9 vocabulary                3 owed   property classes 61  emitted 57  unmakeable 2
  register                    42 rows   tickets 6  findings 42  distinct 42
PYTHONPATH=$PWD python3 -s tools/check_baseline.py           rc=0
  baseline ok: classifications=10 regressions=7 adapters=11 artifacts=223 frozen
PYTHONPATH=$PWD/src:$PWD python3 -s tools/check_coverage.py  rc=0
  catalogue               51   skills 6  references 86
```

199 against the build run's 162: the four trailing classes the ordering
argument named are 37 further tests and about 18 further seconds, which is what
that surface cost to close. Every gate figure is identical to the build run's,
including `references 86` -- the two corrected reference pages change no count
and no digest, which is the measurement behind calling them maintainer material.

`grep -c '^- \[ \]'` prints `0` and `grep -c '^- \[x\]'` prints `5`: this
cycle added no acceptance criterion, so the ticket's criteria count is
unchanged and `cut-slices` Rule 4 is not touched. `grep -c '^## Resolution'`
prints `1`, `grep -c '^## Bar'` prints `1`, `grep -c '^## Handoff'` prints `0`.
The forward-reference grep still prints 8 lines outside this file, all of them
history or prose heads, exactly as item 3 recorded.

**What this cycle did not settle.** The build session's `Red:` line is not
reproducible from a read -- only the session that watched it knows -- so it
stands on that session's word, as the standing bar says it must. The `Mutated:`
line was reproduced independently: flipping `'probe_only'` to `'agent_ok'` in
the seam query returns four rows, the first
`('playbooks/browser-framing/playbook.md', 'transport.header_policy',
'control', 'header_policy_observed')`, and the unmutated query returns none.

## Review findings, 2026-09-03 — cycle 1

- [seam] **`settle_playbook_selections`
  (`20260925T010000Z__a_finished_run_says_what_its_playbook_produced.sql:147`
  and `:155`) is an on-path reader of `playbook_outputs` that the `## Seam
  check` block never names. It settles a `playbook_selections` row `produced`
  or `exhausted` by asking whether a Hypothesis of a class the Playbook
  declares exists on the subject, so after the removal a `http-desync` run that
  minted only a `transport.tls_configuration` claim settles `exhausted` where
  it settled `produced`. The far-end list is one reader short, and the reader
  it is short of is the one whose behaviour changed.** — required — NOW. `settle_playbook_selections` added to the `playbook_outputs` far-end list under `## Seam check`, with the `produced`/`exhausted` flip and both downstream readers priced (`playbook_promotion_evidence` at `s.outcome = 'produced'`, `playbooks_by_metadata` at `0032_playbooks.sql:420`). Neither direction is a regression -- both are what option B asked for -- but neither was written down.
- [craft] **`TransportBarTest.test_the_gate_the_runtime_is_handed_no_longer_names_the_playbook`
  is named for a change this ticket did not make. `playbook_evidence_unmet`
  (`0032_playbooks.sql:509-526`) never reads `playbook_outputs` at all — it
  joins `playbook_selections`, `tasks`, `playbooks`, `playbook_evidence`,
  `hypothesis_evidence` and `observations` — and `transport_evidence_guard`
  (`0025_transport_claims.sql:369`) returns `NEW` early for any class that is
  not `probe_only`. So for the `transport.header_policy` claim both bar edges
  inserted and `unmet` was empty before this ticket exactly as after; deleting
  the `transport.tls_configuration` output row cannot reach either function.
  `## Resolution` repeats the claim as "`hypothesis_transition_refusal` no
  longer names this Playbook for the class it emits".** — required — NOW. Test renamed to `test_the_gate_the_runtime_is_handed_names_only_the_base_rule` and its comment now records why the old name was wrong. The `## Resolution` sentence is corrected in the same edit.
- [ticket] **`## Resolution` overstates what the tests assert. "that the
  `agent_ok` half reaches `supported` with both bar edges landing" is asserted
  by nothing:
  `test_the_bar_is_met_for_the_class_this_playbook_emits` asserts only
  `refused == {}` and `unmet == []`, and
  `test_the_gate_the_runtime_is_handed_no_longer_names_the_playbook` pins the
  return of `hypothesis_transition_refusal` as `transition testing -> supported
  requires a tool receipt` — the transition is still refused, by the base rule.
  Criterion 4 asks for the transition "either landing or refusing by name", and
  is met; the Resolution is what is wrong. Converged with the [craft] finding
  above, from the other end.** — required — NOW. `## Resolution` reworded: the bar empties for the `agent_ok` half and what still refuses the transition is the base rule, named. Corrected together with the [craft] finding above, which is the same defect read from the test side.
- [seam] **Three of the five `playbook_outputs` far ends cite function bodies
  that never run. Migrations apply in filename order (`src/redkraken/migrate.py:206`),
  so the live `playbook_candidates` is
  `20260918T000000Z__an_edit_retires_the_evidence_that_blessed_it.sql:57`
  (reading at `:87`), not `20260823T000000Z…:278`; the live
  `playbook_promotion_evidence` is `20260824T000000Z…:302` (reading at `:308`),
  not `0035_corpus_promotion.sql:70`; and the live `check_playbook_integrity`
  is `20260823T000000Z…:653` (`output_outside_category` arm at `:700`), not
  `0035_corpus_promotion.sql:229`. The functions are real readers; the cited
  source is superseded.** — required — NOW. All three re-cited to the last `CREATE OR REPLACE`, with the apply-order reason (`src/redkraken/migrate.py:206`) written into the block so the next reader can check it.
- [ticket] **The `Name drift, checked` enumeration is false, and the drift it
  misses is inside this Playbook's own shipped references. The count of 51 is
  right, but only about 36 fall in the named buckets. Fifteen do not, and three
  of them are files this Playbook's `bb:references` attaches:
  `src/redkraken/playbooks/http-desync/references/http-attacks-request-smuggling-and-http-desync.md:53`
  still reads "That is `transport.tls_configuration` … and it is what the
  Playbook under this name now asks", and
  `.../http-attacks-http-2-downgrading.md:37` and `:54` still describe a
  supported `transport.tls_configuration` as the reading worth writing up.
  Criterion 2 says "Whichever way this ticket goes, that sentence is corrected
  in the same edit"; the frontmatter sentence was corrected and the reference
  pages handed to the model performing the Playbook were not.** — required — NOW. Both reference pages corrected in the review commit, and the enumeration replaced with one that accounts for all 51 at the build commit. The pages are maintainer material -- `read_corpus` globs only `*/playbook.md` and `*/SKILL.md`, and the generated bundle stub says nothing there reaches a model -- so the correction changes no digest and no bundle. Re-measured after the repair the count is 53; the two it gained are the correction sentences themselves.
- [craft] **The migration's corpus-wide `DO $$` block
  (`20270112T000000Z__a_probe_only_class_comes_off_the_bar_it_cannot_meet.sql:123-137`)
  cannot do what `## Resolution` says it does. The block runs once, at this
  file's position in apply order, so a later corpus migration that reintroduces
  the shape applies afterwards and is never seen — the claim that it "fails at
  apply time rather than at the next test run" holds only for this file's own
  state. The repo has a documented home for a standing corpus invariant
  (`src/redkraken/migrations/README.md`, "Adding a migration"; a
  `standing_checks` row run by `rk db verify`), and
  `tools/check_wiring.py::guard_gaps` (`:1621`) still reports
  `guard_satisfiability` unregistered at `1 owed`.** — required — NOW. `## Resolution` reworded to what a one-shot `DO` block can claim, and the same scope note added to the migration beside the assertion. The standing form of the invariant is W7 `guard_satisfiability`, which `tools/check_wiring.py:303` already carries as `owed:116`; this ticket does not close it and no longer implies it does.
- [bar] **`## Bar` item 4's skip/assert grep is un-anchored and its result is
  characterised rather than quoted, which the standing bar forbids. Anchored to
  `d0556465...HEAD` it prints six lines, not one — including
  `-- [ ] **A test asserts the whole path rather than the trigger.**`, a
  `-`-side line matching `.*assert`, which is the shape the check exists to
  catch. The conclusion it supports is nonetheless true:
  `git diff d0556465...HEAD -- tests/` deletes no line, and no `.skip`,
  `skipTest`, `skipIf`, `xfail`, `type: ignore`, `noqa` or `pragma: no cover`
  is added anywhere in the diff.** — required — NOW. Item 4 re-pasted with the command anchored to `d0556465...HEAD` and scoped to `tests/ tools/ src/`, its output quoted verbatim (one hit, the migration header's prose), plus `git diff d0556465...HEAD -- tests/ | grep -c '^-[^-]'` printing `0`.
- [ticket] **The same `## Bar` item 4 grep does not reproduce: against
  `d0556465...HEAD` it prints 7 lines by this reader's count, not one. The
  substantive claim is independently proven in the same item by
  `git diff --numstat`, whose four figures re-run exactly. Converged with the
  [bar] finding above.** — nit — NOW. Same edit as the [bar] finding above.
- [seam] **`src/redkraken/playbooks/http-desync/references/http-attacks-http-2-downgrading.md:37`,
  `:54` and `http-attacks-request-smuggling-and-http-desync.md:53` still assert
  in the present tense that `transport.tls_configuration` is what this Playbook
  asks, and nothing will catch it: `read_corpus`
  (`tools/check_wiring.py:1247`) globs only `*/playbook.md` and `*/SKILL.md`,
  and no runtime reader consumes references. Converged with the [ticket]
  finding above.** — nit — NOW. Same edit as the [ticket] finding above; the seam block now records the correction and why nothing caught it.
- [seam] **The `playbook_outputs` reader list reads as exhaustive but records
  no skipped count, which `seam-check` step 2 requires when a pass stops early.
  At least nine further SQL reads exist (`0032_playbooks.sql:402`, `:612`,
  `20260823…:700`, `20260824…:308`, `:449`, `:559`, `20260918…:87`,
  `20260925…:147`, `:155`, `20260927…:471`, `20261004…:234`, `:276`,
  `20261220…:107`).** — nit — NOW. The list now names functions rather than lines and states the thirteen further read sites, with the reason none is a distinct far end.
- [seam] **The `Name drift, checked` count of 51 is exact but its enumeration
  covers about 40. Unlisted: the six `analyse-source` sink packs carrying a
  `## transport.tls_configuration` heading, three mentions in `http-desync`'s
  own references, `src/redkraken/evaluation.py:366`, and the Playbook's own
  `bb:provenance` line. The "nine migration headers" bucket includes
  `20261219T000000Z…:783`, which is a `playbook_outputs` INSERT row, not prose.
  Converged with the [ticket] finding above.** — nit — NOW. Same edit as the [ticket] finding above.
- [seam] **`OWED_GAPS["W9 transport.tls_configuration"] = "owed:237"` is cited
  at `tools/check_wiring.py:199`; `:199` is the dict's opening line and the row
  is at `:345`.** — nit — NOW. Cite corrected to `:345`.
- [ticket] **The same `tools/check_wiring.py:199` citation: `:199` is
  `OWED_GAPS: dict[str, str] = {`, the row is at `:345`. The seam itself holds
  — `register_errors` is at `:2037` as claimed and the gate re-runs rc=0 with
  `W9 vocabulary 3 owed`. Converged with the [seam] finding above.** — nit — NOW. Same edit as the [seam] finding above.
- [ticket] **Three of the five register line numbers in `## What was measured`
  are one line early: `transport.header_policy` `agent_ok` is at
  `0025_transport_claims.sql:217` not `:216`, `transport.request_framing` at
  `:222` not `:221`, `transport.datagram_transport` at `:229` not `:228`.
  `:204`, `:211` and the `:203-233` range are correct. The `:216` cite also
  shipped into
  `TransportBarTest.test_the_bar_is_met_for_the_class_this_playbook_emits`'s
  docstring.** — nit — NOW. `:217`, `:222`, `:229` in `## What was measured`, in criterion 3, and in the test docstring that carried the `:216` cite.
- [ticket] **Two counts in `## Build findings` are wrong. The binding is 59
  fixtures, not 60 — the catalogue seeds 59 rows, 59 directories ship, and this
  ticket's own pasted live run says `59 fixture(s) in the binding have no run at
  this text`. And the catalogue holds 51 Playbooks, not "all fifty"
  (`check_wiring` W12 `playbooks 51`, `check_coverage` `catalogue 51`); the same
  "all fifty" is in the migration header at
  `20270112T000000Z__a_probe_only_class_comes_off_the_bar_it_cannot_meet.sql:41`.
  Neither number changes the argument.** — nit — NOW. 59 and 51 in `## Build findings`, and `all fifty` corrected to `all 51` in the migration header.
- [ticket] **`Touches:` names four paths and omits `tests/test_database.py`,
  although criterion 4 requires a test. The other three excess paths are asked
  for: this ticket's own file, and ticket 237's file, which the decision block
  commissions. `## Bar` item 5 accounts for all seven.** — nit — NOW. `tests/test_database.py` added to `Touches:`, together with the `references/` path this review's own repair touched.
- [ticket] **Criterion 1 is present-tense and its own commit falsified one of
  its citations: "`http-desync` declares `transport.tls_configuration` in
  `bb:outputs` (`playbook.md:4`)" — `:4` now reads
  `bb:outputs: ["transport.header_policy"]`. `## Resolution` says "Nothing in
  the ticket turned out wrong" and carries no `Wrong in the ticket, named`
  block, which is the form ticket 166's own review cycle required for this
  exact shape.** — nit — NOW. A `**Wrong in the ticket, named.**` block added under `## Resolution`, carrying this and the two other citation defects cycle 1 found, and reading criterion 1 as the pre-state it was written against.
- [ticket] **`tools/check_wiring.py:326-327` still owes
  `W9 transport.certificate_trust` and `W9 http-desync transport.certificate_trust`
  to ticket 116, while `## The decision` argues in writing that 116 leaves
  `transport_evidence_guard` alone and so cannot close the class. The argument
  that moved the new row to 237 applies verbatim to the neighbour. Outside
  `Touches:`.** — nit — DECLINED. Pre-existing, outside this ticket's `Touches:`, and re-owning it is a decision for whoever closes 116 or builds 237 -- the two `transport.certificate_trust` rows have to move together with whatever 116 concludes about `transport_evidence_guard`, and moving them now on this ticket's reasoning alone would put a second ticket's registry entry in a third ticket's commit. Recorded here so the next review finds the decision rather than the finding.
- [ticket] **The migration at
  `20270112T000000Z__a_probe_only_class_comes_off_the_bar_it_cannot_meet.sql:37`
  cites `playbook_fixture_binding` as `0036:117`; the function is at
  `0036_playbook_tests.sql:122`. The same wrong cite is in
  `test_the_fixture_the_removed_class_declared_now_grades_nobody`'s docstring.
  `## Build findings` has it right.** — nit — NOW. `:122` in the migration header and in the test docstring.
- [bar] **`## Bar` item 4 quotes four of seven `git diff --numstat` lines with
  no elision marker, and the three dropped ones include the 138-line migration,
  this ticket's only new production file.** — nit — NOW. All seven lines pasted, with the three that were dropped named.
- [bar] **The omitted full `tests/test_database.py` run is not a quiet lowering
  — `docs/agents/testing.md` tier 3 fires on a migration that changes the
  schema broadly, and this migration contains no DDL at all — but the
  justification prices only "one corpus row and one re-frozen Playbook" and is
  silent on the 310 added lines of `tests/test_database.py`. The class-subset
  run cannot cover those for ordering: the batch put `TransportBarTest` last,
  while a full module run sorts it 84th of 91, ahead of `UnreadyTaskTest`,
  `ValidationCommandTest`, `WaveMeasurementTest` and `WriteDisciplineTest`.
  Residual risk is low — `tearDownClass` purges under `SET LOCAL app.purging`
  and takes no artifact delete — and adding those four classes closes it for
  about 40s.** — nit — NOW. `UnreadyTaskTest`, `ValidationCommandTest`, `WaveMeasurementTest` and `WriteDisciplineTest` added to the batch and re-run; item 4 now prices the 310 added test lines as well as the corpus row, and replaces the unmeasured "over thirty minutes" with the measured 2.0 s/test extrapolation.
- [bar] **"The spec's `Load` section names no figure for this path" reads as
  though the section exists and is silent. `docs/specs/production-harness-v2/spec.md`
  has no `## Load` section at all, the same absence as its missing
  `## Verify command`.** — nit — NOW. Corrected to say the section is absent, not silent.
- [bar] **"Judgement, Rule 3b. No double was injected" asserts everything is
  real, but `TransportBarTest.stage`'s own docstring records that the Task and
  the `playbook_selections` row are "written rather than earned", because after
  this ticket `playbooks_by_metadata` filters on `playbook_outputs` and the
  runtime can no longer reach the arrangement. That is the reading Rule 3b asks
  for, and it is not named in the judgement.** — nit — NOW. The judgement now names the hand-written Task and selection and why production can no longer reach the `probe_only` arrangement, which is the reading Rule 3b asks for.
- [bar] **The `bb:provenance` rewrite went past the correction criterion 2
  asked for: "unmakeable behind the interception proxy" became "unmakeable",
  "refused by the last section" became "refused by section 4", "under D3" was
  dropped, and "merged technique ledger, which holds one executable reading,
  two blocked ones and two refusals for this slug" became "merged ledger".
  These ride into the agent-facing `## Provenance` of
  `docs/okf/playbooks/http-desync.md`. `## Bar` item 5's file list is exact;
  its sentence "the diff is what the ticket asked for" is broader than the
  list.** — nit — NOW. Item 5 now records that the whole `bb:provenance` sentence was rewritten, which clauses went, and why cycle 1 records it rather than restoring them -- the Playbook's bytes are frozen by digest and a restore costs a second re-freeze migration for wording.
- [craft] **The migration's in-side own-pair assertion (`:92-102`) is the first
  half of `test_the_fixture_the_removed_class_declared_now_grades_nobody`
  restated in SQL, for the same reason and against the same rows.** — nit — NOW. A comment added beside the assertion saying it is deliberately the same reading as the test, so a corpus applied without the test suite still refuses the shape.
- [craft] **`test_no_playbook_declares_a_probe_only_class_its_own_bar_cannot_support`
  is vacuous while its sibling holds.
  `test_the_probe_only_classes_are_declared_by_no_playbook_at_all` asserts that
  no `playbook_outputs` row names either `probe_only` class, so the seam test's
  `JOIN transport_makeability … WHERE makeability = 'probe_only'` has no rows
  before the polarity filter is reached; it cannot go red unless the sibling
  goes red first. The seam test is the durable one and the sibling is the
  snapshot that dies when 237 lands, which the docstrings do not say.** — nit — NOW. The docstring now says which of the pair is durable and which dies when 237 lands, and that the sibling is the one to delete.
- [craft] **`TransportBarTest.stage` (`:39383-39399`) is the third verbatim copy
  of the `tasks` + `playbook_selections` arrangement
  (`HypothesisPromotionTest.put_the_claim_under_a_playbook_bar` at `:14047`,
  `ask_the_preview_about_the_playbook_bar` at `:31026`), and the first to drop
  the guard both precedents carry with a written reason — each counts the
  selections that reached a Task, because an empty unmet set would otherwise
  mean "no Playbook" rather than "the bar is met".
  `test_the_bar_is_met_for_the_class_this_playbook_emits` asserts exactly that
  empty set with nothing pinning the chain.** — nit — NOW. The selection count both precedents carry is added to `stage` and asserted in `test_the_bar_is_met_for_the_class_this_playbook_emits`, so an empty unmet set cannot read as "the bar is met" when it means "no Playbook reached the read".

Review cycle 1 of 3 — undecided: none
