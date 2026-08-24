# 176 — An evaluation points every Program at a route its fixture does not serve

**What to build:** the Program an evaluation opens names the route the fixture
card declares, so the recon Task a fresh Program opens has somewhere to go.
Until now every graded Program was pointed at `/`, which no fixture in the
corpus answers.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The configured scope is the whole of the seeding.**
      `record_configured_subjects` (`20260831T000000Z`) writes one `application`
      Entity per exact target rule of the live scope version, keyed on
      `rk2_base_url(protocol, host, port, path_prefix)`, and
      `open_configured_recon` opens one recon Task per Entity it finds. There is
      no other path: `program._project_identities` writes identity Entities and
      nothing else, and every Surface row past that point is something a child
      proposed. So `scope.include.paths` decides what a fresh Program is
      pointed at.
- [x] **`evaluation.configuration` wrote `paths = ["/"]` and nothing else.**
      One rule, one Application, one recon Task, against the origin's root.
- [x] **No fixture in the corpus serves its root.** All five High-Yield pairs
      answer `404` at `/`, and each declares the one route it does serve:

          artifact-exposure-pair    /static/app.js.map
          object-ownership-pair     /notes/2
          markup-pair               /search
          cookie-scope-pair         /account
          quantity-or-price-pair    /cart/items

      `artifact-exposure-pair/app.py` serves `/static/app.js` and
      `/static/app.js.map` and answers `404` for everything else;
      `object-ownership-pair/app.py` serves `/notes/<id>` for a known id and
      answers `404` for everything else. Neither ships an index, so nothing
      links to the route either.
- [x] **`bb:subject` was declared and never used.** `fixture.py` parses it
      against `SUBJECT` and `fixture.Fixture` carries it; the only reader in the
      package is a description line in `evaluation.py`. Ticket 46 lists the key
      among what a card declares and names no consumer.
- [x] **Measured.** Canary attempt three, `attack-surface` against
      `artifact-exposure-pair`, door route, database `rk2grade3` on 2026-08-24.
      Every one of the six Programs held exactly one configured Entity, an
      `application` at `scope_path_raw = /`. What the six spent their passes on:

          vulnerable   200 x1 on /static/app.js, 404 x25, 501 x3
          secure       200 x1 on /static/app.js, 404 x29

      No vulnerable Program ever requested `/static/app.js.map`. The secure half
      did, and 404 is the right answer there. Not one vulnerable Program
      proposed `information_disclosure.artifact_exposure`; the only two
      hypotheses of that class in the whole database sit on a secure Program and
      stopped at `testable`. What the vulnerable halves asserted instead was
      `transport.header_policy` and `information_disclosure.workload_metadata`,
      and `attack-surface` declares one class, so both counted `out_of_scope`.
      Filed: `claims 2, out_of_scope 1, discriminating_tp 0` on repeat 0 and
      `claims 0` on repeat 1.
- [x] **What it would have cost.** `playbook_test_verdict` fails a Playbook
      whose median discriminating finding is below 1. Every one of the 55
      fixtures would have filed `discriminating_tp = 0` for the same reason, so
      all 1650 runs would have measured whether a child guesses an unlinked
      path. That is the third instrument fault the canary has caught, after
      tickets 166 and 175.
- [x] **The fix.** `evaluation.configuration` writes the root and the card's
      route, de-duplicated, into the one `[[scope.include]]` rule. Authority
      does not move: `/` already admits the whole origin and `bb:subject` is a
      path under it, so the second rule adds a recon subject and no reach.
      `tests/test_fixture.py` holds the list and the root-only case.

## Why

A fixture card states the route under test because the fixture is one route.
That is deliberate and it is written down: `artifact-exposure-pair` says "one
artifact, one comparison, one claim", and the whole corpus is built the same
way. A harness that reads the class, the facts and the identities off the card
and then throws away the route is asking every Playbook to rediscover, by
guessing, the one thing the card already said.

It also makes the measurement dishonest in a specific direction. A Playbook is
being graded on its method -- `attack-surface` step 2 is "propose candidates
from the surface, not from a list" -- and a Program whose surface is a single
404 has no surface to propose from. The grade that comes out is a grade of luck.

## Notes

The database `rk2grade3` is kept, not dropped.

This changes what every fixture measures, so the canary starts again from an
empty surface in a new database, and the digests are frozen again first.
