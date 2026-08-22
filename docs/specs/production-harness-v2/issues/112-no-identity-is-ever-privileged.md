# 112 — No Identity is ever privileged, and a surface fact is built on one

**What to build:** A decision about `identities.class`: either a writer for
`privileged`, or the removal of the class and the fact computed from it.

**Blocked by:** nothing.

**Status:** ready-for-agent

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

## The decision, taken 2026-08-22

**The class comes from configuration: one optional `class` key on the `identity`
entry, closed to `user` and `privileged`, defaulting to `user`. `service` is
retired from the enum. `privileged` stays, and `privileged_identity_available`
stays, because with that key it is computable.**

The fact that settles which half of the ticket's either/or is right is a CHECK,
not a missing function. `0003_entities.sql:111` says `CHECK (class = 'anonymous'
OR secret_ref IS NOT NULL)`. So any row that is ever `privileged` must also carry
a `secret_ref`, and **the only writer of `secret_ref` in this tree is
`_project_identities`** (`src/redkraken/program.py:1044` and `:1054`), which takes
it from `configuration.document["identity"]` at `:1015-1017`. The set of rows that
could ever be privileged is therefore exactly the set configuration creates, and
"a writer for `privileged`" can only mean "configuration says so".

**A runtime writer is not merely unbuilt; the grants forbid it.** The state
role's SELECT on `identities` is a column grant that deliberately omits
`secret_ref` -- `0020_state_access.sql:217-221`, with the comment "`identities`
minus one column. Not a view, not a redaction: a grant, checked by the executor
on every query." `_project_identities`' own docstring says the same thing from
the other side (`program.py:1005-1011`): "The configuration document is the
operator's declaration of which stable labels exist. `secret_ref` retains only
the control-side `slot://` reference, and the state role's column grant excludes
it." A runtime path that promoted an Identity to `privileged` would have to
produce a `secret_ref` for a row through a connection that cannot read the column
and has no write privilege on the table at all.

**And privilege is not observable in the first place.** Whether a credential is an
administrator's is a fact about how the operator provisioned the account, not a
property of any response the harness can fetch. A Playbook that inferred it from
"this session sees an admin panel" would be writing a guess into a closed
vocabulary that other Playbooks' triggers read as ground truth. The configuration
document is where facts the runtime cannot discover already live -- the
`rules_of_engagement` block is the precedent, typed controls where an absent
control is a denial (`src/redkraken/config.py:44-56`), and `identity` already
carries exactly one such fact per entry today (`IDENTITY_KEYS = ("name",
"slot_ref")` at `config.py:83`, validated by `_identity` at `:571-587`).

**Rejected: removing `privileged` and the surface fact.** Removal would say the
harness will never model a privilege boundary, and the corpus is one Playbook
away from needing it. Forty-seven Playbook bodies were read: eight list
`multiple_test_identities`, which is `count(class = 'user') >= 2`
(`20260904T000000Z...:214-216`) and is satisfiable from configuration today, so
horizontal tests between peers already work. `multiple_test_identities` cannot
express a vertical test -- peer-versus-peer and peer-versus-admin are different
experiments -- and `privileged_identity_available` is the only vocabulary in the
tree for the second. Removing it costs the same migration edit as adding the
writer and buys less.

**Rejected: `service`.** No writer, no reader, no `subject_facts` branch, and the
word already means something else two tables away -- `entities.type = 'service'`
is a port on a host (`0003_entities.sql:10`, `:48`), which is what every other use
of the string in this tree means (`0015_epistemic_corrections.sql:45`,
`20260813T090000Z...:164`). A fourth Identity class spelled like an Entity type is
a collision the vocabulary should not keep.

The shape of the change: one key in `config.IDENTITY_KEYS` and its check in
`config._identity`; the literal at `program.py:1044` replaced by the entry's
value; the `UPDATE` at `program.py:1054` extended to carry a class change, since
today a re-projection updates only `secret_ref` and `invalidated_at`, so an
operator who reclassified a slot would see nothing happen; and one migration
replacing the CHECK at `0003_entities.sql:105` with a three-value domain.
Defaulting the key to `user` keeps every existing configuration document meaning
exactly what it means now.

## What was measured

`grep -rn "identities SET" src/` finds two statements, both in `program.py`
(`:1054`, `:1076`), and neither touches `class` -- the ticket's claim, verified.
Every `INSERT INTO identities` in the tree: `program.py:1044` (`'user'`),
`rk2_anonymous_identity` (`'anonymous'`), `promote_proposal` (`'anonymous'`).
Forty-seven Playbook bodies under `src/redkraken/playbooks/`: **zero** list
`privileged_identity_available` as a trigger; eight list
`multiple_test_identities`; one lists `tenant_boundary`.

## Correction: the live `rk2_anonymous_identity` is a later file

The ticket cites `rk2_anonymous_identity` at
`20260908T010000Z__a_clamped_run_holds_the_identity_it_acts_as.sql:182`. That
definition has been superseded. The live body is
`20260925T020000Z__an_identity_slot_is_not_a_refused_address.sql:73-90`, a
`CREATE OR REPLACE` of the same signature with one statement added, and its
`INSERT INTO identities (entity_id, slot_name, class)` is at `:89-90`. The class
it writes is still `'anonymous'`, so the ticket's conclusion is unaffected, but
anyone editing the function must edit the later file.

## Correction: "no Playbook lists it as a trigger" is true here and does not
generalise

The ticket's third criterion treats "no Playbook lists this fact" as the reason
the defect is harmless today. That is right for
`privileged_identity_available`, and the neighbouring row shows why it is a thin
rescue rather than a general one: `tenant_boundary` is listed as a trigger by
`src/redkraken/playbooks/workload-identities/playbook.md:5`, and its branch
(`20260904T000000Z...:224-228`) counts distinct `member_of` destinations from
Identity Entities. `grep -rn "member_of" src/` finds no writer for that
relationship type outside the migrations that declare it
(`0004_relationships.sql:15`, `20260813T090000Z...:218`); the only route that
could produce one is a Playbook proposing the edge through
`submit_mission_result`, and every Identity a proposal can mint is `'anonymous'`.
Separately, `identities.tenant_entity_id` has no writer anywhere -- `grep -rn
"tenant_entity_id" src/ tools/` returns the column definition and one GRANT
(`0020_state_access.sql:219`) and nothing else -- and no reader either, since
`tenant_boundary` computes from `member_of` instead. Neither of those is this
ticket's to fix; both belong in whatever ticket owns the G6a gate, and this ticket
should not be closed on the claim that `identities` has one such row.
