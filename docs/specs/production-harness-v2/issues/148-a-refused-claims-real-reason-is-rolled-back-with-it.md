# 148 — A refused claim's real reason is rolled back with it

**What to build:** The part of `promote_proposal`'s pass 3 that keeps an edge's
own refusal when the claim it belongs to is refused, instead of replacing it
with a sentence that names the wrong cause.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] **The measurement is in the ticket.** `rk2hunt7`, proposal `PR1`,
      2026-08-22. Seven refusals; three of them describe one event and two of
      those three are wrong.

      ```
      1|hypotheses[1]|no_support|no evidence edge in this result supports it
      2|evidence[2]  |no_subject|the hypothesis it names was not promoted
      3|evidence[3]  |no_subject|the hypothesis it names was not promoted
      ```

      What the payload actually held:

      ```
      idx|hyp  |obs       |pol     |role
      2  |h_ver|obs_php   |supports|baseline
      3  |h_ver|obs_drupal|supports|variant
      ```

      Both Observations were promoted -- they are `O1`..`O6`. Both edges name
      `h_ver`, both say `supports`, both carry a counting role. On the face of
      the record the claim had two supporting edges and was refused for having
      none, and the edges were refused for naming a claim that was refused. The
      three sentences are circular and none of them is the cause.

      The cause is `enforce_evidential_kind()`:

      ```
      technology_identified | is_evidential = f
      ```

      so both INSERTs raised, both were caught into `v_faults`, `v_supported`
      stayed false, `RK033` was raised, and the block rolled back -- taking
      `v_faults` with it, because `v_drops := v_drops || v_faults` runs only on
      the success path. The post-loop handler then wrote `no_subject` over every
      edge naming the refused `ref`.

      The file says so itself, at
      `20260814T070000Z__a_proposal_becomes_a_canonical_hypothesis.sql:879`:

      ```
      -- Its edges' refusals survive with it. Had the block rolled back,
      -- they would have been reported against the Hypothesis instead.
      ```

      That is the intended behaviour, and the measurement is what it costs: a
      hunter reading its own drops cannot learn that
      `technology_identified` may only be cited with `role=context`, which is the
      one sentence that would stop it repeating the mistake.

- [ ] **The refusal names the cause.** Whether by collecting the edge faults
      outside the block that rolls back, by re-deriving the evidential kinds
      before the insert, or by carrying `SQLERRM` into the `no_support` citation
      -- the record must say `technology_identified is not evidential` somewhere
      a run can read.

- [ ] **The cascade stops claiming to be a cause.** `the hypothesis it names was
      not promoted` is true and useless. If it stays, it should say which
      refusal it is downstream of.

- [ ] **Checked by something that would go red.** A promotion test staging a
      claim supported only by a non-evidential Observation, asserting the drops
      name the kind.

## Why

Found by reading a live result, not the code. The harness refused a well-formed
Hypothesis for a correct reason and then described the refusal three times
without once naming it. Every drop this Program files is a message to the next
run, and this one teaches it nothing.

Small, contained to one function, and worth more than its size: ticket 139 and
ticket 144 both turned on the same insight, that what the runtime tells a model
is what the model does next.
