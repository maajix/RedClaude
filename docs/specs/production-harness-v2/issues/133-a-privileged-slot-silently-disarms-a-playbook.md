# 133 — A privileged slot silently disarms a Playbook

**What to build:** A decision, and then a writer for it, about what a Program
with one `user` slot and one `privileged` slot is entitled to be offered, now
that ticket 112 has made the distinction sayable.

**Blocked by:** 112 — No Identity is ever privileged, and a surface fact is
built on one. The hazard does not exist until an operator can write `class`.

**Status:** resolved

- [x] The arithmetic is stated. `multiple_test_identities` counts
      `i.class = 'user' ... >= 2` (`0032_playbooks.sql:150-153`, re-issued
      unchanged as late as
      `20260904T000000Z__three_http_integrity_and_parsing_topics_...sql`). Before
      ticket 112 every configured slot projected as `user`, so a two-slot
      Program always held the fact. After it, an operator who correctly labels
      one of two slots `privileged` drops the count to one and the fact goes.
- [x] The blast radius is measured rather than guessed. `multiple_test_identities`
      is a required target for a list of Playbooks that includes api, graphql,
      grpc, logging and api-authorization; the exact list is a query against
      `playbook_targets`, and this ticket carries its output rather than this
      sentence.
- [x] The decision is written into this ticket before the code is. Three shapes:
      a privileged slot also counts toward the two, because it is still an
      account a differential can be taken between; the fact is restated as
      "two or more distinct accounts, of any class"; or the count stands and the
      Playbooks that need two peer accounts are correct to go quiet, in which
      case the operator has to be told, because a Playbook that silently stops
      being offered is the failure mode the 112 migration header argues against
      in its own terms.
- [x] Whatever is decided, an operator can see it. The present behaviour is
      invisible: nothing reports which Playbooks a Program's identity
      configuration has just made unreachable.

## The blast radius, as measured

Seven Playbooks require `multiple_test_identities` in `triggers_all`, measured
against both the corpus (`src/redkraken/playbooks/*/playbook.md`) and a live
`playbook_targets`:

    playbooks/api/playbook.md
    playbooks/api-authorization/playbook.md
    playbooks/browser-realtime/playbook.md
    playbooks/graphql/playbook.md
    playbooks/grpc/playbook.md
    playbooks/logging/playbook.md
    playbooks/object-ownership/playbook.md

## The decision

**The second shape: two or more distinct accounts, of any class but
`anonymous`.** Written as `count(DISTINCT i.entity_id) WHERE i.class <>
'anonymous' AND i.invalidated_at IS NULL >= 2`.

The first shape -- add `privileged` to the list -- selects the same rows today
and is a list to keep in step with a CHECK constraint forever. The third -- the
count stands and the seven Playbooks are right to go quiet -- is refused by what
those Playbooks ask for: `object-ownership` wants a second account to read the
first one's objects with, and an admin account is a second account. A user/admin
pair is the sharper differential, not a missing precondition.

`anonymous` stays out, and it is the one class the branch is really about. An
unauthenticated caller is not an account; the difference between an account and
nobody is `anonymous_identity_available`, which already exists. Since ticket 131
every Program mints an anonymous Identity for its first Task, so counting it
would hand this fact to every Program that configured a single slot.

## What an operator sees

`program_identity_gaps(uuid)`: the identity-shaped facts a Program does not
carry, one typed reason each, and the Playbooks each fact gates.

    fact                           reason
    multiple_test_identities       no_account_configured | one_account_configured
    privileged_identity_available  no_privileged_identity
    anonymous_identity_available   no_anonymous_identity
    tenant_boundary                no_tenant_membership | one_tenant_only

Called from `program._report_identity_gaps`, so `rk program open` says it at the
moment the identity document is read -- which is the moment an operator labels a
slot `privileged` and moves seven Playbooks out of reach. Gaps that gate no
Playbook are left out: `tenant_boundary` gates none in the corpus today, and
naming it would be telling an operator to configure something nothing asks for.

An invalidated Identity is not counted and is not a reason of its own: a
withdrawn credential is a slot to re-provision, which is the same instruction as
configuring one.

## Why

Found by the standards axis of the code review on `0759b7b`: *"Reclassifying one
of two slots drops the count to 1 -- the exact 'silently unselectable Playbook'
trap the 112 migration header argues against, reintroduced next door."*
