# 207 — The Rules of Engagement say logged in, and the door asks anyway

**What to build:** A Program whose configuration declares `credential_use` acts
as the accounts its operator provisioned, without being asked once per host.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

`rk2here`, 2026-08-26, sixteen laps of the driver loop after ticket 206 let the
campaign work past an open question. The first thirteen:

```
rk2here-01  T776 perform -> done    accepted True
rk2here-02  T602 hunt    -> parked  accepted False
rk2here-03  T603 hunt    -> parked  accepted False
rk2here-04  T151 recon   -> parked  accepted False
rk2here-05  T152 recon   -> parked  accepted False
rk2here-06  T153 recon   -> parked  accepted False
rk2here-07  T154 recon   -> parked  accepted False
rk2here-08  T105 recon   -> done    accepted True
```

Six of thirteen laps did no work. Each stopped on
`call_risk_rules:net_borrowed_identity`, and each spent one of its Task's three
attempts doing it. The sitting ended on lap 16 with nothing workable left.

## What the configuration already said

`program-here.toml`, line 40, with the operator's own comment above it:

```toml
# credential_use is true because two accounts of our own are in play. The
credential_use = true
```

That control is a Rule of Engagement. `config._rules_of_engagement` loads it,
`scope.compile_policy` compiles it, and `program.py` writes it to
`program_scope_versions.credential_use` on every revision. It is the operator
saying, in the one document this harness treats as authority, that this
campaign works its target logged in.

Nothing read it. `program.py` reported it in a controls table and no gate
consulted it, so the harness asked per host for permission it had been given
once in writing.

## The mechanism

`net_borrowed_identity` (`0026_human_control.sql:266`) names the digest fact
`identity_slot` and escalates any value outside `{""}`. The slot is filled for
every request made as somebody, so the rule fires for every host --
and `equivalence_key` hashes the whole digest, host included, so one approval
covers one host. The Program has 231 host entities.

## What was changed

A third projection fact, `unapproved_identity_slot`, stamped by
`current_request_digest` beside the two it already stamps: the slot this
request will act as where the Program declared no credential use, and the empty
string where it declared it. `net_borrowed_identity` reads that fact instead of
`identity_slot`.

A Program that declared nothing is bit-for-bit unaffected: for one of those the
two facts are the same string.

## What is not widened

- `net_unsafe_method` still escalates any method outside GET/HEAD/OPTIONS. A
  state-changing request made as an account holder is still a question -- and
  it is a question this change makes *reachable*, because `assess_call_risk`
  names the first rule to reach the deciding class and the credential rule got
  there first alphabetically.
- `net_host_out_of_scope` is `forbidden` and no control lowers it. Being logged
  in has never let a request leave for a host the configuration does not name.
- The slot still has to resolve to an Identity of this Program holding a live
  Lease, and the secret still comes from the vault through
  `resolve_egress_identity`.
- `identity_slot` stays in the digest, in the equivalence key and on the
  Receipt. Every request still says which account made it.

## What it invalidates

`equivalence_key` hashes the whole digest, so a new fact in it is a new key for
every request. Every live grant stops matching and every open question re-gates
under the rule as it now reads; `revalidate_decision` answers `policy_changed`,
which is `supersede_decision`'s case. That is the correct ending for both: a
grant is an answer about a classification, and the classification moved.

- [x] A Program declaring `credential_use = true` makes an authenticated GET without asking.
- [x] A Program declaring nothing is asked exactly as before.
- [x] A state-changing request as an account holder is still asked about, by the method rule.
- [x] Every rule still names a fact the digest carries.
