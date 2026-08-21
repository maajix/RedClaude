# 88 — Serve a fixture whose ground truth is its TLS configuration

**What to build:** An own-pair fixture declaring `transport.tls_configuration`,
and the half of the evaluation harness that can serve one. `playbooks/http-desync`
declares that class as its only output and no fixture in the corpus declares it,
so `playbook_fixture_binding` yields nothing on its in-pair side and
`playbook_test_verdict` stops at `untested` for that Playbook no matter how many
runs ticket 84's campaign files.

**Blocked by:** nothing. Ticket 84 grades what the binding yields; this is what
the binding does not yield.

**Status:** ready-for-agent

- [ ] A fixture pair whose two variants differ in the TLS configuration they
      negotiate, not in the bytes they return, and whose `bb:classes` is
      `["transport.tls_configuration"]`.
- [ ] `evaluation.served` can serve that pair over TLS. Today it is a bare
      `ThreadingHTTPServer((host, 0), handler(variant))` -- every fixture in the
      corpus is graded over cleartext, which is the one thing this class cannot
      be graded over.
- [ ] The measurement reaches the fixture on the lane whose receipt is
      admissible for the question. The Playbook's whole subject is that an
      ordinary reading through the interception proxy describes the proxy's own
      door; a fixture graded through that door grades the door.
- [ ] `playbook_fixture_binding` gives `playbooks/http-desync` a non-empty
      in-pair side, and `playbook_test_verdict` reaches a clause past
      `untested` for it.
- [ ] The corpus statements that count the catalogue are updated together --
      the enumerated corpus in `tests/test_database.py`, the binding totals
      ticket 84's `rk playbook cost` states, and `UNGRADED`.
- [ ] `PlaybookCatalogueTest.UNGRADED` and the test that names this ticket are
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
