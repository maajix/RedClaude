# 112 — No Identity is ever privileged, and a surface fact is built on one

**What to build:** A decision about `identities.class`: either a writer for
`privileged`, or the removal of the class and the fact computed from it.

**Blocked by:** nothing.

**Status:** needs-triage

- [ ] The enum and its writers are named exactly. `identities.class` is closed
      to four values at `0003_entities.sql:105` -- `anonymous`, `user`,
      `privileged`, `service`. Every writer in the tree:
      `src/redkraken/program.py:1044` writes the literal `'user'`;
      `promote_proposal`
      (`20260814T070000Z__a_proposal_becomes_a_canonical_hypothesis.sql:1427`),
      its superseded twin
      (`20260813T090000Z__a_recon_run_becomes_typed_surface.sql:1069`) and
      `rk2_anonymous_identity`
      (`20260908T010000Z__a_clamped_run_holds_the_identity_it_acts_as.sql:182`)
      all write the literal `'anonymous'`. There is no `UPDATE identities SET
      class` anywhere: `grep -rn "identities SET" src/` finds only `secret_ref`
      and `invalidated_at`, at `program.py:1054` and `:1076`.
- [ ] The consequence is a surface fact whose predicate no writer can satisfy.
      `privileged_identity_available` is registered at `0032_playbooks.sql:79`
      ("a privileged identity is controlled") and has a `subject_facts` branch
      in every one of the nine migrations that rebuilt the view, most recently
      `20260904T000000Z...:216`. The branch tests `identities.class =
      'privileged'`. It can never be true.
- [ ] It is harmless today only because no Playbook lists it as a trigger, and
      the ticket says why that is a trap rather than a rescue: the first
      Playbook that adds this trigger is silently unselectable forever, and the
      existing `fact_not_computed` gate will not say so, because it proves the
      view mentions the fact and not that the predicate can hold.
- [ ] `identities.class = 'service'` is decided in the same breath. It has no
      writer and no reader -- not even a `subject_facts` branch -- so it is
      fully inert, and inert is a state a closed vocabulary should have to
      declare rather than reach by silence.
- [ ] Ticket 97 is named as the owner of the adjacent question and is not
      duplicated. What an identity slot is, and how a run says which one it
      spent, is 97's; what classes an Identity may be, and which of them
      anything can produce, is this one's.
- [ ] `anonymous_identity_available` (`0032_playbooks.sql:80`) is checked in
      passing and recorded as fine: `rk2_anonymous_identity` and
      `promote_proposal` both write that class, so it is genuinely computable
      and genuinely listed by no Playbook. That is a different state from this
      ticket's and is left alone.

## Why

`docs/research/wiring/20-vocabulary-wiring.md` section 4b, which calls
`privileged_identity_available` "the single worst-wired row in `surface_facts`"
and grades the class vocabulary itself **promised**: "The class vocabulary
advertises a privileged-identity concept the runtime cannot instantiate."

Its gate G6a is the mechanical form -- for each `subject_facts` branch testing a
column with a CHECK-closed domain, assert some writer produces that value -- and
`identities` is the case that fails today.
