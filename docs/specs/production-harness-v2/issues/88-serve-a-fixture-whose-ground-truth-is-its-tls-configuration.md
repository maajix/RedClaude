# 88 — Serve a fixture whose ground truth is its TLS configuration

**What to build:** An own-pair fixture declaring `transport.tls_configuration`,
and the half of the evaluation harness that can serve one. `playbooks/http-desync`
declares that class as its only output and no fixture in the corpus declares it,
so `playbook_fixture_binding` yields nothing on its in-pair side and
`playbook_test_verdict` stops at `untested` for that Playbook no matter how many
runs ticket 84's campaign files.

**Blocked by:** nothing. Ticket 84 grades what the binding yields; this is what
the binding does not yield.

**Status:** resolved

- [x] A fixture pair whose two variants differ in the TLS configuration they
      negotiate, not in the bytes they return, and whose `bb:classes` is
      `["transport.tls_configuration"]`.
- [x] `evaluation.served` can serve that pair over TLS. Today it is a bare
      `ThreadingHTTPServer((host, 0), handler(variant))` -- every fixture in the
      corpus is graded over cleartext, which is the one thing this class cannot
      be graded over.
- [x] The measurement reaches the fixture on the lane whose receipt is
      admissible for the question. The Playbook's whole subject is that an
      ordinary reading through the interception proxy describes the proxy's own
      door; a fixture graded through that door grades the door. **Deferred:**
      none of this landed, and `**Deferred:**` rather than the tracker's usual
      `**Partial:**` says so -- what the other criteria built is the fixture and
      the listener, and neither of those is a lane.
      `receipts.transport_citable` is generated over
      `purpose = 'transport_measurement'`, and no Python writer sets `purpose`
      at all, so every receipt in this harness carries 021's default of
      `target_traffic` and every reading of this fixture still goes through the
      door. Ticket 93 builds that writer and decides the trust anchor a fixture
      measurement verifies against. **Closed by ticket 93:** the writer is
      `record_transport_measurement`, the anchor is the evaluator's per-run
      authority for the Program it was minted for, and both halves of this pair
      are now measured on that lane and told apart by their Receipts.
- [x] `playbook_fixture_binding` gives `playbooks/http-desync` a non-empty
      in-pair side, and `playbook_test_verdict` reaches a clause past
      `untested` for it.
- [x] The corpus statements that count the catalogue are updated together --
      the enumerated corpus in `tests/test_database.py`, the binding totals
      ticket 84's `rk playbook cost` states, and `UNGRADED`.
- [x] `PlaybookCatalogueTest.UNGRADED` and the test that names this ticket are
      rewritten as the statement of what is now gradable, or deleted with the
      reason.

## Why

Found by ticket 64's final review and recorded as
`one-playbook-has-no-fixture-to-be-graded-against` in
`baseline/final-review.tsv`: "Story 178/187: one shipped Playbook can never be
graded." Story 178 asks every
in-scope Playbook to be graded against fixtures it did not pick; 187 asks a
verdict to follow from what was filed. For forty-nine of the fifty Playbooks
ticket 84's campaign will produce one. For `playbooks/http-desync` it cannot,
and no number of runs changes that: `0036_playbook_tests.sql:366` returns
`untested` when `n_in_pair = 0`, and the in-pair side is derived from
`fixture_classes` against `playbook_outputs`, so a class no fixture declares has
no in-pair side to be run against.

The gap is not an oversight in the Playbook. `transport.tls_configuration` is
what that Playbook is for, and 056 shipped it knowing the corpus could not grade
it: the class is settled by a measurement taken on a lane the proxy does not
intercept, against a target serving two TLS configurations, and every fixture in
this corpus is an `app.py` handler behind cleartext HTTP.

## What ticket 64 found out about the shape

* `evaluation.served` builds one `ThreadingHTTPServer` per variant and takes the
  address from the socket. TLS is a wrap of that socket plus a certificate the
  reading will see -- `tls.py` already mints them for the proxy, so the material
  exists; what does not exist is a fixture that declares it needs one.
* The two variants have to differ in the handshake, which means the difference
  is in the `SSLContext` rather than in `handler(variant)`. That is a shape the
  fixture format does not currently have a place for.
* Adding a fixture is a migration, not a file: the corpus is inserted by
  `INSERT INTO fixtures` across five migrations, and `tests/test_database.py`
  enumerates the whole corpus in `ORDER BY fixture_id` order.
* Doing it during ticket 84's campaign would move the binding underneath it.
  84's stated cost -- 50 Playbooks against 54 bound fixtures, 16200 runs -- is
  computed from the binding; a 55th fixture restates the campaign.

## Comments

Ticket 64 recorded the finding rather than fixing it. The risk it leaves is
bounded and stated in three places: the Playbook ships `draft`, a `draft`
Playbook is never promoted, and `check_playbook_tests` reports
`draft_playbook_untestable` against it on every run
(`0036_playbook_tests.sql:545`). Nothing untested is presented as tested. What
is missing is coverage, and this ticket owns it.

## What was built

`src/redkraken/fixtures/tls-configuration-pair/` is the fifty-fifth fixture and
the first with two entry points. `app.py` defines `handler(variant)` like every
other fixture in the corpus, and both halves return the same bytes from it: the
same shell on `/app`, the same bundle on `/static/console.js`, the same public
status document, the same counting route, and the same
`Strict-Transport-Security: max-age=63072000; includeSubDomains; preload` on
every response. Then it defines `tls(variant, context)`, and that is where the
halves differ: `vulnerable` terminates at TLS 1.2 with
`ECDHE-ECDSA-AES128-GCM-SHA256`, `secure` terminates at TLS 1.3 and refuses
everything under it, and both offer `http/1.1` and only `http/1.1` over ALPN.

The second entry point is the class's own division rather than an invention.
025 records `transport.tls_configuration` as `probe_only` over `tls_version`,
`cipher` and `alpn`, and not one of the three is a thing a request handler can
write. A corpus of handlers behind cleartext can never hold a positive for it,
which is why fifty-four fixtures and fifty Playbooks left this one Playbook
`untested`.

`evaluation.served` wraps the listening socket when a fixture defines `tls` and
leaves it alone when it does not, so the scheme is a property of the fixture
rather than a mode the evaluator is put into. `Served` gained a required
`scheme` field for that -- required rather than defaulted, because a default of
`"http"` would let a fixture be served over TLS and scoped as cleartext, and the
scope document `configuration()` writes is what the door checks a dial against.
`tests/test_fixture.py:ServingOverTls` holds the rest of the corpus at `http`.

The certificate is the evaluator's. `tls.authority()` mints a fresh one per call
into a temporary directory that dies with the context manager, and `tls` is
handed a context to configure rather than asked to build one -- who the target
*is* changes every run and is nobody's business but the evaluator's, and what it
*negotiates* is the fixture's whole subject.

The one schema rule that moved is `fixture_addresses.protocol`, from
`CHECK (protocol = 'http')` to `IN ('http','https')`, with `open_fixture_address`
replaced for the one clause that refuses a scheme. 078 wrote it as one spelling
with the reason in a comment -- "a second spelling here would be a claim about a
listener nothing starts" -- and that reason was true until this migration
shipped the listener. It is still a closed set, because a fixture address is
what the door dials and a third scheme would be a claim about a listener that
still does not exist.

## What criterion 3 leaves, and why it is a ticket rather than a hole

`receipts.transport_citable` is a generated column over
`purpose = 'transport_measurement' AND intercepted = false AND decision =
'allowed'` and the three wire verification columns. `grep purpose
src/redkraken/proxy.py` finds prose and no writer: `0021_scope_policy.sql:155`
gives the column a default of `target_traffic` and nothing in `src/` moves it,
so the measurement purpose 025 built citability on has never been used by
anything. That is a lane, and building it is more work than this ticket's
subject and is now ticket 93.

What that leaves here is a fixture that is reached, read and graded, and a
receipt that is honestly non-citable. `proxy.connect` already tolerates a target
it cannot verify -- strict attempt, keep its words, dial again with verification
off, record `chain_verified = false` and `hostname_verified = false` -- so the
self-signed fixture is reachable through the door and its receipt is recorded as
the unverified one it is. No fake evidence is produced anywhere: the citability
column refuses, which is exactly what 025 built it to do.

Ticket 93 also carries the question this ticket could not answer on its own. 025
says a measurement verifies "against the SYSTEM trust store rather than the run
CA", which is right for a live target and settles nothing for a fixture whose
authority is minted per run and handed to nobody. Either that per-run authority
is a trust anchor for the measurement of the Program it was minted for and for
no other, or a fixture measurement is recorded unverified on purpose. 93 says
which.

## What a graded run of `http-desync` now returns, and why it is not a pass

Written down because criterion 4 asks for a clause past `untested` and does not
ask which one, and the answer matters to whoever spends ticket 84's runs.

Through the door the two halves are indistinguishable: they serve the same bytes
under the same advertisement, and the field they differ in is one an Agent
cannot observe from an intercepted exchange. So a graded campaign walks past
clauses 1, 2 and 3 of `playbook_test_verdict` and stops at clause 4 with `fail`
-- `median discriminating finding < 1 on tls-configuration-pair`,
`0036_playbook_tests.sql:404`.

That is a real move rather than a cosmetic one. Before this ticket the Playbook
was `untested` for want of a fixture; after it, it is gradeable and grades
`fail` for want of the lane ticket 93 owns. Both block promotion and neither
presents anything untested as tested, so nothing ships that did not ship before.
What changes is where the missing piece is recorded: it was a hole in the corpus
and it is now a named lane with a ticket. A note on ticket 84 says the same
thing where the spend is decided.

## What this ticket also changed

`tools/check_baseline.py` refuses a fixture that imports a module it could dial
out with, and `ssl` was on the refused side. It is on the listener side now,
with the reason in the comment: `ssl` cannot open a connection -- it wraps a
socket something else already has -- and a fixture whose ground truth is its TLS
configuration has to name `ssl.TLSVersion` to state what it terminates at. Every
module that actually dials is still refused, so a fixture holding this one and
nothing else can serve a handshake and reach nobody.

`evaluation._repeat` now translates `tls.Unusable` into a Ledger refusal naming
the fixture. `tls.authority` is the same call `proxy`, `browser` and `doctor`
each already translate into a refusal of their own vocabulary, and `served` was
the one call site that let it escape -- so a machine with no `openssl` would
have answered `rk playbook evaluate` with a traceback from three frames inside a
context manager rather than with the one sentence that says what is missing.

`UNGRADED` was deleted rather than rewritten. Criterion 6 allows either. It was
a constant naming the one Playbook that said `draft_playbook_untestable`
differently from the other forty-nine, and after this ticket it says it the same
way, so keeping the constant would mean keeping a name for an empty set. The
reason is in the test's own comment, where the constant used to be read.

`baseline/final-review.tsv` was not in the criteria and was edited anyway. Its
`one-playbook-has-no-fixture-to-be-graded-against` row cited
`PlaybookCatalogueTest.UNGRADED` in its remediation cell, which this ticket
deleted, and `tests/test_review.py` requires a `fixed` row to cite a run this
repository has. The row is now `fixed`, citing
`PlaybookEvaluationTest.test_the_only_standing_problem_is_a_draft_nobody_has_evaluated`,
and its remediation cell says what landed and what went to ticket 93.

`baseline/technique-intake.tsv`'s `tls-parameter-floor` row keeps its outcome
and loses a sentence that stopped being true. The outcome is still
`ungradeable:harness_owned`, and it has to be: `tools/check_intake` refuses a row
claiming a *fixture* for a class the schema records as `probe_only`. What the
rationale used to say is that a corpus fixture is served over the transport the
harness chose, and after this ticket the transport is the fixture's. It now says
the true version -- the reading is still the harness's, because an agent reads
through the interception proxy -- and names ticket 93 as the lane that changes
it. The retrieval, the date and the digest are untouched; only the sentence
about this repository moved.

The fixture's `Server` header is `nginx/1.27.2` rather than an invented product
name. `bb:facts` declares `tech_edge_proxy`, that fact is computed from the
technology tokens 055 maps, and `playbooks/http-desync` names it in
`bb:triggers_all`. Nothing validates `bb:facts` against what a fixture serves --
`edge-rule-pair` declares the same fact and sends no `Server` header at all --
so this is a fixture choosing to be findable rather than a rule being followed.
