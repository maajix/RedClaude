# 190 — Two sealed accounts nothing ever acts as

**What to build:** A path from a provisioned Identity to a request that carries it.

**Blocked by:** nothing.

**Status:** open

- [ ] **The measurement is in the ticket.** Database `rk2here`, 2026-08-25.
      Both configured Identities are provisioned and sealed:

      ```
      label|slot_name     |sealed|byte_size
      IDN1 |here-primary  |t     |5027
      IDN2 |here-secondary|t     |5035
      IDN3 |_anonymous    |f     |
      ```

      `here-login.py` read the credentials out of 1Password over `op://`,
      performed the sign-in against `account.here.com` and handed the harvested
      jar to `rk identity provision`. That half works and has worked since
      18:45.

      Nothing has ever acted as either of them:

      ```
      -- receipts by identity
      (anonymous)|239

      -- what every Task selected
      IDN3|_anonymous|hunt|pending|37

      -- what every claim named
      hypotheses|names_a|names_b
      37        |0      |0
      ```

      One Lease has ever been taken, by `AR75`, on `_anonymous`.

- [ ] **The chain, and where it is open.** Ticket 131 made the Task the thing
      that carries the choice, and made the anonymous Identity the written-down
      default. `rk2_project_task_identities` projects
      `tasks.selected_identity_entity_id` into `task_identities`, and
      `derive_hypothesis_hunts` opens one hunt Task per (claim, Identity). The
      Identity on a claim comes from `rk2_promote_hypotheses`, out of the
      candidate document:

      ```sql
      INSERT INTO hypotheses
          (program_id, subject_entity_id, identity_a_entity_id,
           identity_b_entity_id, property_class, statement, rationale)
      VALUES (p, (v_candidate ->> 'subject')::uuid,
              (v_candidate ->> 'identity_a')::uuid,
              (v_candidate ->> 'identity_b')::uuid, ...)
      ```

      `identity_a` appears nowhere in `src/redkraken/_launch.py` and nowhere in
      the rest of the Python runtime. The child's `submit_mission_result` has no
      field that could carry it and the runtime never fills one in. So every
      candidate arrives with two NULLs, every claim is anonymous, every hunt
      Task selects `_anonymous`, and the two sealed sessions are unreachable by
      construction rather than by configuration. There is no operator command
      that repoints a Task either: `selected_identity_entity_id` is written by
      the trigger and read by one query in `execution.py`.

- [ ] **The second gate, which is not a defect.** Ticket 131 states that a Task
      selecting a non-anonymous Identity "still reaches
      `net_borrowed_identity`, is still graded `approval_required` asking
      `credential_needed`, and still parks for a person before a single request
      leaves". That is deliberate and stays. Whatever fills the first gap has to
      leave an operator a decision to answer, not route around one.

## Why

An engagement provisioned two real accounts, spent a sign-in against a live
third party to harvest their sessions, sealed both, and then hunted 239 requests
as nobody. Eleven Playbooks are written around the difference between two
Identities and none of them can be reached.

This is the same shape as ticket 189: every part is built, tested and correct,
and the one hop nobody wrote is the one that would let the parts touch. Ticket
131 said the question "can now be asked at all". Nothing asks it.

## What this does not decide

Which shape closes it. At least three are open, and they are not equivalent:

  1. The child names an Identity on a claim, through a new
     `submit_mission_result` field the roster admits for `web_hunter` alone.
  2. The runtime derives it: a claim whose subject carries an
     `authenticated_endpoint` fact opens one hunt Task per provisioned
     Identity, with no model involvement.
  3. The operator binds it in the configuration: `[[identity]]` gains a scope
     predicate and the derivation reads it.

(2) needs no new agent surface and produces the identity differential the
Playbooks want; (1) is the only one that lets a model say *why* an account
matters. They are not exclusive.
