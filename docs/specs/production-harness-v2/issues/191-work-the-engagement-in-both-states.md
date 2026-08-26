# 191 — Work the engagement in both states

**What to build:** Every lane that touches a target does it twice: as nobody, and as each provisioned account.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** Database `rk2here`, 2026-08-25,
      after ticket 190 named the gap and 20261119T000000Z closed half of it.
      Every Task of every kind still selected the anonymous Identity:

      ```
      kind    | identity | slot_name  | count
      recon   | IDN3     | _anonymous | 108
      hunt    | IDN3     | _anonymous | 41
      perform | IDN3     | _anonymous | 1
      ```

      and the half that had been closed could not fire, because it was gated on
      the subject carrying `authenticated_endpoint` — a fact `subject_facts`
      derives from `endpoints.auth_required IS TRUE`, which is written by the
      recon lane, which had only ever walked as nobody. The gate asked a
      question only a signed-in walk could answer and then refused to sign in.

- [x] **One set, read by both fan-outs.** `rk2_hunting_identities(program)`:
      the anonymous Identity, plus every non-anonymous one that is provisioned
      and not invalidated. Provisioned means a sealed `identity_slots` row —
      the door has nothing to inject without one and `resolve_egress_identity`
      refuses a named slot with no live Lease, so an unprovisioned Identity
      would only ever derive work that cannot run.

- [x] **The hunt frontier fans out, ungated.** A claim that named nobody now
      owes one Task per state. A claim that named its own Identities still gets
      exactly those. A Program with nothing provisioned derives exactly what it
      derived before, which is guard (i).

- [x] **The first walk of a root fans out the same way.**
      `open_configured_recon` opens one recon Task per (subject, state).
      `open_task` gains a fifth argument to say which; the four-argument form
      is kept and passes NULL. Its dedup check was widened to read the Identity
      as well — `tasks_live_dedup_idx` has carried
      `selected_identity_entity_id` since 20261101T000000Z, so the index has
      always permitted the second Task while the check above it refused it,
      with a message naming the first, which is why nobody noticed they
      disagreed.

- [x] **A lane that acts as an account holds it.** `recon` clamps to Identity
      Leases. `claim_task` takes the Lease only for a clamped role, and both
      the door and `rk2_replay_plan` refuse a named slot without one.
      `task_identities` is backfilled for the 108 existing recon Tasks in the
      same transaction, because `claim_task` raises on a clamped Task that
      names nothing to hold.

- [x] **Measured after.** `rk2here`, immediately after the migration:

      ```
      states offered      IDN3 _anonymous | IDN1 here-primary | IDN2 here-secondary
      hunt frontier owes  here-primary 41 | here-secondary 41
      recon fan-out owes  here-primary 108 | here-secondary 108
      recon clamp         t
      task_identities     recon 108 | hunt 41
      ```

- [x] **And the roster says the same thing the schema does.** The clamp was
      turned on by an `UPDATE`, and `test_roster` read only the `INSERT` rows,
      so `roster.ROLES["recon"].clamp_to_identity_leases` stayed `False` while
      the database said `True` and nothing noticed. `roster.py` now states it,
      and the test reads later clamp updates as well as later rows — which is
      the hole, not the drift: the assertion exists so that a roster edit the
      migration does not follow fails here.

- [ ] **The far end of the loop is still anonymous.** Deferred to ticket 192,
      and stated in the migration rather than left to be discovered.

## Why

An engagement provisioned two real accounts, spent a sign-in against a live
third party to harvest their sessions, sealed both, and hunted 239 requests as
nobody. The signed-in state is where the interesting surface is: what a door
serves after it stops asking is not what it serves while it is asking, and a
harness that only ever measures the second one is measuring the front page.

Both states, not the second one instead of the first. An authenticated finding
is a comparison, and the anonymous half is one of the two things being
compared — which is why `rk2_hunting_identities` includes the anonymous
Identity rather than sitting beside it.

## What this does not change

No authority. A Task selecting a non-anonymous Identity still reaches
`net_borrowed_identity`, is still graded `approval_required` asking
`credential_needed`, and still parks for a person before one request leaves.
This ticket decides which questions get asked. An operator still answers every
one that spends an account.
