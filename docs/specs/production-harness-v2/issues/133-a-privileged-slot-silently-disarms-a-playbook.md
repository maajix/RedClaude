# 133 — A privileged slot silently disarms a Playbook

**What to build:** A decision, and then a writer for it, about what a Program
with one `user` slot and one `privileged` slot is entitled to be offered, now
that ticket 112 has made the distinction sayable.

**Blocked by:** 112 — No Identity is ever privileged, and a surface fact is
built on one. The hazard does not exist until an operator can write `class`.

**Status:** needs-triage

- [ ] The arithmetic is stated. `multiple_test_identities` counts
      `i.class = 'user' ... >= 2` (`0032_playbooks.sql:150-153`, re-issued
      unchanged as late as
      `20260904T000000Z__three_http_integrity_and_parsing_topics_...sql`). Before
      ticket 112 every configured slot projected as `user`, so a two-slot
      Program always held the fact. After it, an operator who correctly labels
      one of two slots `privileged` drops the count to one and the fact goes.
- [ ] The blast radius is measured rather than guessed. `multiple_test_identities`
      is a required target for a list of Playbooks that includes api, graphql,
      grpc, logging and api-authorization; the exact list is a query against
      `playbook_targets`, and this ticket carries its output rather than this
      sentence.
- [ ] The decision is written into this ticket before the code is. Three shapes:
      a privileged slot also counts toward the two, because it is still an
      account a differential can be taken between; the fact is restated as
      "two or more distinct accounts, of any class"; or the count stands and the
      Playbooks that need two peer accounts are correct to go quiet, in which
      case the operator has to be told, because a Playbook that silently stops
      being offered is the failure mode the 112 migration header argues against
      in its own terms.
- [ ] Whatever is decided, an operator can see it. The present behaviour is
      invisible: nothing reports which Playbooks a Program's identity
      configuration has just made unreachable.

## Why

Found by the standards axis of the code review on `0759b7b`: *"Reclassifying one
of two slots drops the count to 1 -- the exact 'silently unselectable Playbook'
trap the 112 migration header argues against, reintroduced next door."*
