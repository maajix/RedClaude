# 100 — Extend the vocabulary the corpus is missing

**What to build:** One migration adding the property-class leaves and surface
facts the shipped vocabulary genuinely cannot express, each arriving with the
fixture that grades it.

**Blocked by:** nothing on the capability side, and it must land **after** the
capability work rather than before it: a class with no emitter is what
`authentication.recovery_flow` already is, and adding six more would multiply
that failure rather than fix it.

**Status:** ready-for-agent

- [ ] The counts this ticket works from are the migrated ones, not the ones an
      earlier reading reported. The shipped vocabulary is **57 property
      classes**, **16 observation kinds of which 11 are evidential** and **55
      surface facts**, read back out of a database with every migration applied
      and all fifty Playbooks loaded. An earlier reading counted from
      `0018_vocabularies.sql` and `0032_playbooks.sql` alone and reported 47, 14
      and 33; nine later migrations extend all three, because every Playbook
      batch since has added the vocabulary it needed. Counting the
      `INSERT INTO property_classes` blocks across all eight migrations that
      hold one gives 57.
- [ ] Each class the research calls absent has been checked against the
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
- [ ] What is genuinely absent is added, and the list is short:
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
- [ ] Every class added arrives with the fixture that grades it, in the same
      migration. This is the rule the ticket exists to enforce and not a
      nicety: a class no fixture declares gives `playbook_fixture_binding` an
      empty in-pair side, and `playbook_test_verdict` then stops at `untested`
      however many runs are spent -- which is exactly the hole ticket 88 was
      opened to close for one Playbook.
- [ ] Nothing degrades quietly, and the ticket relies on that rather than on a
      test. The catalogue is loaded by migration into `playbooks` plus five
      child tables with foreign keys, so an unknown class, trigger, kind or
      skill fails at INSERT rather than being ignored -- the safe direction, and
      the reason a vocabulary migration carries no runtime risk.
- [ ] No new observation kind is added for out-of-band work.
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
