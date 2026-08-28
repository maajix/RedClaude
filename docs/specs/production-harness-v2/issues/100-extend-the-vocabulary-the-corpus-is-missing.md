# 100 — Extend the vocabulary the corpus is missing

**What to build:** One migration adding the property-class leaves and surface
facts the shipped vocabulary genuinely cannot express, each arriving with the
fixture that grades it.

**Blocked by:** nothing on the capability side, and it must land **after** the
capability work rather than before it: a class with no emitter is what
`authentication.recovery_flow` already is, and adding six more would multiply
that failure rather than fix it.

**Status:** resolved

- [x] The counts this ticket works from are the migrated ones, not the ones an
      earlier reading reported. The shipped vocabulary is **57 property
      classes**, **16 observation kinds of which 11 are evidential** and **55
      surface facts**, read back out of a database with every migration applied
      and all fifty Playbooks loaded. An earlier reading counted from
      `0018_vocabularies.sql` and `0032_playbooks.sql` alone and reported 47, 14
      and 33; nine later migrations extend all three, because every Playbook
      batch since has added the vocabulary it needed. Counting the
      `INSERT INTO property_classes` blocks across all eight migrations that
      hold one gives 57.
- [x] Each class the research calls absent has been checked against the
      migrated vocabulary before it is added, and the ones that turn out to
      exist are recorded as existing rather than added twice. Two of the four
      that `00-todo-and-harness-gaps.md` section B names do exist:
      * `authentication.recovery_flow` is at `0018_vocabularies.sql:105-106`
        ("the reset, recover or enrolment path grants what the primary path
        would refuse"), and `recovery-flow-pair` is already bound to it
        (`20260915T000000Z__four_disclosed_techniques_arrive_as_fixtures.sql:92`).
        The class is not missing and neither is its fixture. What is missing is
        an emitter: the string appears in
        `playbooks/authentication/playbook.md:101` and in two of its reference
        pages, and in no `bb:outputs` anywhere. That is ticket 101's work, not
        this one's.
      * `authorization.tenant_isolation` is at `0018_vocabularies.sql:91-92`
        ("the boundary crossed is an organisation or realm, not a single
        object") **and is emitted** --
        `playbooks/workload-identities/playbook.md:4` declares it, and
        `tenant-isolation-pair` grades it
        (`20260827T000000Z…:473`). The claim that there is no class for tenant
        isolation over HTTP does not check out and is not repeated.
      A third, cache deception, is covered by
      `information_disclosure.cached_response`
      (`20260829T000000Z…:239-240`), emitted by `playbooks/web-cache`.
- [x] What is genuinely absent is added, and the list is short:
      * **a takeability leaf for a dangling resource.** The string `takeab`
        appears nowhere in `src/redkraken/`. It serves 07 #1 (dangling DNS on an
        in-scope hostname, read to the provider fingerprint), 07 #5 (abandoned
        storage the application still fetches from) and the read half of 07 #12.
        The reading is a finding; claiming the resource is refused, and the leaf
        must be worded so that it cannot be read as permission to claim one.
      * **an object-property write leaf.** Mass assignment / BOPLA on the write
        side has no home in the 57: `authorization.object_ownership`
        (`0018_vocabularies.sql:87-88`) is about the object named by the
        request, `information_disclosure.excess_field`
        (`0018_vocabularies.sql:131-132`) is the read half, and
        `injection.object_graph`
        (`20260902T000000Z…:270-271`) is about which *type* a route
        reconstructs. The gap is recorded in
        `docs/research/playbook-state-of-the-art/04-authorization-business-logic.md:541`.
      * **a cookie-parser-differential leaf** under `session_handling`, for
        02 #4. `session_handling.cookie_scope`
        (`0018_vocabularies.sql:156`) is the nearest and is about scope, not
        parsing.
      * **a general parser-differential leaf**, for 05 #8.
      * **a SCIM / provisioning surface fact** for 03 #10, and **a pipeline or
        workload subject** for 03 #15 and 07 #11, which the research merges into
        one ask.
- [x] Every class added arrives with the fixture that grades it, in the same
      migration. This is the rule the ticket exists to enforce and not a
      nicety: a class no fixture declares gives `playbook_fixture_binding` an
      empty in-pair side, and `playbook_test_verdict` then stops at `untested`
      however many runs are spent -- which is exactly the hole ticket 88 was
      opened to close for one Playbook.
- [x] Nothing degrades quietly, and the ticket relies on that rather than on a
      test. The catalogue is loaded by migration into `playbooks` plus five
      child tables with foreign keys, so an unknown class, trigger, kind or
      skill fails at INSERT rather than being ignored -- the safe direction, and
      the reason a vocabulary migration carries no runtime risk.
- [x] No new observation kind is added for out-of-band work.
      `callback_interaction` exists, is evidential and is backed by `{callback}`
      alone, and the stale refusal that says otherwise is ticket 98's to
      supersede.

## Why

Capability L in
`docs/research/playbook-state-of-the-art/09-capability-matrix.md` -- 8 of the
131 techniques (02 #4; 03 #1, #10, #15; 05 #8; 07 #1, #5, #11), and the smallest
item in the ranked list: one migration, no runtime risk, and the explicit
instruction that it must land after the capability work.

The count correction is from the same file's opening section and from
`00-todo-and-harness-gaps.md` section C0, which says why: read the vocabulary
from a migrated database rather than from the first migration that declares it,
because every Playbook batch since has extended it. That correction is what
turns most of the "missing class" list into a list of classes that are present
and unused -- which is a corpus problem, not a schema one, and belongs to
ticket 101.

## Comments

**2026-08-28 -- Four classes, two facts, four fixtures, and one gate that reads
less than it looks like it does.**

The counts were read back out of a database with every migration applied and all
fifty Playbooks loaded, and they are the ones this ticket claimed: **57 property
classes, 16 observation kinds of which 11 are evidential, 55 surface facts**,
beside 55 fixtures and 50 Playbooks. The three "missing" classes were checked
before anything was added and are recorded as existing rather than added twice:
`authentication.recovery_flow` (0018, graded by `recovery-flow-pair`, emitter
owed to 101), `authorization.tenant_isolation` (0018, declared by
`playbooks/workload-identities` and graded by `tenant-isolation-pair`) and
`information_disclosure.cached_response` (20260829, emitted by
`playbooks/web-cache`).

Migration `20261215T000000Z__four_readings_the_vocabulary_could_not_spell` adds:

| class | fixture |
| --- | --- |
| `injection.unclaimed_reference` | `unclaimed-reference-pair` |
| `authorization.object_property_write` | `object-property-write-pair` |
| `session_handling.cookie_parsing` | `cookie-parsing-pair` |
| `injection.parser_differential` | `parser-differential-pair` |

and the two surface facts `scim_surface` and `pipeline_surface`. No observation
kind was added.

Three things the work found that the ticket did not predict.

1. **A surface fact needs a branch, not just a row.**
   `check_playbook_integrity()`'s `fact_not_computed` rule refused the corpus
   with `(error,fact_not_computed,scim_surface)` and the same for
   `pipeline_surface`. The rule is textual -- it reads
   `pg_get_viewdef('subject_facts')` looking for the atom's own name, which is
   why 049 through 055 spell every name out instead of assembling it -- so the
   view is restated whole with four rows added to the same `VALUES` map the
   `tech_` atoms use, and the fact descriptions were reworded to say what the
   branch actually computes.
2. **`tools/check_wiring.py` read one of the four new classes and not the other
   three.** `statement()` at `check_wiring.py:544` finds the end of a seeding
   statement with `sql.find(";", start)`, with no regard for quoting, and the
   first class description contained a semicolon -- so the statement was cut
   after row one and three classes were invisible to gate W9. The description
   was rewritten without the semicolon. **The reader itself is not fixed here.**
   Measured against the mask that same file already builds, one seeded statement
   in the corpus is being cut short today: `0018_vocabularies.sql:216`'s
   `observation_kinds` seed ends, as far as the gate is concerned, at the
   semicolon inside the `-- non-evidential: surface facts. Real observations,
   provenance and all; they` comment on line 238, so the five non-evidential
   kinds never reach it. `check_wiring.py:1697` then defaults an unseen kind to
   evidential, which is the direction that fails open. No shipped Playbook trips
   that rule today, so this is a hole and not a miss. It is its own ticket, and
   it is recorded here rather than fixed inside a vocabulary ticket.
3. **The four new classes are emitterless, deliberately, and W9 says so out
   loud.** They are registered `owed:101` beside the five that were already
   there. Shipping a class and a Playbook written against it in one step is a
   Playbook nothing graded, which is the failure this ticket exists to avoid.

Two facts with no fixture presenting them is the residue, and it is stated in
the migration header rather than skipped: a trigger no evaluation exercises is
the same unused-vocabulary shape as an emitterless class, smaller because a fact
cannot be a verdict, and inherited by ticket 101 on purpose.

Measured:

- `CleanCreationTest + ApplicationSubjectFactsTest + PlaybookCorpusSelectionTest
  + PlaybookEvaluationTest`: **82 tests, OK**, 299s.
- `tests.test_fixture + tests.test_playbook + tests.test_skill +
  tests.test_roster`: **309 tests, OK**.
- The four gates end rc=0. `check_wiring` reports **W9 property classes 61,
  emitted 50, unmakeable 2, 13 owed** and a register of 56 rows.
  `git diff --check` is clean.
- A scratch database provisioned and migrated from empty with the engagement's
  own role passwords: `rk db verify` gives **97 assertions, 0 violations**,
  `check_playbook_integrity()` returns **no errors**, and the vocabulary reads
  back **61 classes, 57 surface facts, 59 fixtures**. The scratch database was
  dropped; no Hunt database was migrated.
