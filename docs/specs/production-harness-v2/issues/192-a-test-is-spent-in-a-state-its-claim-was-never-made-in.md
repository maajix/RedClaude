# 192 — A Test is spent in a state its claim was never made in

**What to build:** The far end of the loop, and the schema check standing in front of it.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** Ticket 191 made the recon and hunt
      lanes work a target in every provisioned state. The lane that settles
      what they find did not move. `derive_test_performances` inserts a
      `perform` Task naming the test, the claim and the subject, and never the
      Identity:

      ```sql
      INSERT INTO tasks (program_id, kind, test_id, hypothesis_id,
                         subject_entity_id)
      SELECT p, 'perform', w.test_id, w.hypothesis_id, w.subject_entity_id
      ```

      `select_task_identity` fills the NULL with the anonymous Identity. So a
      hunt that finds something while signed in authors a Test, and the Test is
      replayed signed out against a target state the claim was never made
      about. It comes back negative, the claim is refuted, and nothing records
      that the two runs were looking at different things. That is worse than
      not testing it: it writes down a wrong answer.

      The same is true of every other derivation — `derive_chain_unlocks`,
      `derive_finding_claims`, `open_impact_task`, `open_validation_session`.
      Ticket 131's note that `derive_hypothesis_hunts` is "the only caller in
      the corpus that writes one" is still true of all of them.

- [x] **The repair, and why it is one line in one place.**
      `select_task_identity` is the BEFORE INSERT trigger every INSERT into
      `tasks` passes through, so the inheritance belongs there rather than in
      each derivation. Inheritance only where there is exactly one answer: a
      `perform` Task spends one Test, a Test was authored by one run, and that
      run held one Identity, so `tests.created_by_run_id -> agent_runs.task_id
      -> tasks.selected_identity_entity_id` has a single value at the end of
      it. A `conclude` Task or a chain unlock derived from a claim reached by
      two Identities has two, and must not guess.

- [x] **The schema check in front of it.** `performer` runs as a `renderer`,
      and 0019 carries

      ```sql
      -- a renderer holds no session and drives no identity
      CHECK (runs_as <> 'renderer' OR NOT clamp_to_identity_leases)
      ```

      so the performer cannot clamp, so `claim_task` never takes it a Lease,
      so `rk2_replay_plan` refuses any named slot it is given: `Identity lease
      refused`. Inheriting the Identity without lifting this would turn a
      silent wrong answer into a loud refusal, which is better but is not the
      fix.

      Dropped in 20261124T000000Z. What `renderer` actually means is still
      checked, by the two constraints that file does not touch:
      `roles_renderer_runs_no_model` and `roles_renderer_loads_nothing`, both
      as true of the performer as of the reporter. Driving an Identity is not
      in that family — it is a property of the lane's work,
      `clamp_to_identity_leases` is the column for it, and the roster is where
      it is decided. A check that restates a roster decision adds nothing, and
      this one contradicted it.

      The sentence was written about the `reporter`, which was the only
      renderer 0019 shipped: it renders a document and sends nothing. The
      `performer` was made a renderer afterwards and drives the replay Lane,
      which sends real requests to a real target through the door. The check
      generalised a property of one row into a rule about a category, and the
      category acquired a member the rule was never true of.

- [x] **What the fix has to decide.** Whether `renderer` stops being one
      category — a `reporter` that sends nothing and a `performer` that sends
      through the replay Lane are two things sharing a word — or whether the
      check narrows to name the reporter. The first is the honest shape and the
      larger diff; the second is one line and leaves the word still wrong.

      Neither. `renderer` is one category and its two surviving checks say what
      it is: no model, no skills. The rule that was wrong was the third one,
      and it was removed rather than narrowed — narrowing it would have written
      a role name into a schema constraint, which is the same mistake with a
      shorter blast radius.

- [x] **And one constraint it inherits.** `identity_leases_exclusive_idx` is
      UNIQUE on `identity_entity_id WHERE released_at IS NULL`, with no
      exemption for the anonymous Identity. Today the driver claims one Task per
      `rk run` so the practical concurrency is one and the index never binds. A
      lane quota profile putting two clamped lanes in flight together would
      make the second claim fail, and with `recon` clamped as of ticket 191
      that now includes two anonymous lanes. Whoever raises a slot count should
      find this written down rather than discover it.

      Still true, and now with three clamped roles instead of two.

- [x] **Measured after.** The migration ran against `rk2here` in a rolled-back
      transaction first: all three guards passed and one existing `perform`
      Task was projected into `task_identities`. Its Test was authored by an
      anonymous run, so the inheritance gives it what it already held — which
      is what guard (ii) checks.

## Why

Ticket 191 opened the signed-in state for the lanes that explore. This is the
lane that decides whether what they found is true. Leaving it anonymous does
not merely fail to settle authenticated claims — it settles them wrongly, and a
harness whose whole argument is that a Receipt is evidence cannot have a step
that measures the wrong thing and records the result as a measurement.
