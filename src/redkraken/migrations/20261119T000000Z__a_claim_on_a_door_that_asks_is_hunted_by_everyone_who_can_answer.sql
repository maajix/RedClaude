-- ---------------------------------------------------------------------------
-- 20261119T000000Z__a_claim_on_a_door_that_asks_is_hunted_by_everyone_who_can_answer.sql
--                                                                  (ticket 190)
--
-- The hop between a provisioned Identity and a request that carries one.
--
-- What was measured. Database `rk2here`, 2026-08-25. Both configured
-- Identities were signed in against the live target, harvested and sealed:
--
--     IDN1 | here-primary   | sealed | 5027 bytes
--     IDN2 | here-secondary | sealed | 5035 bytes
--
-- and 239 Receipts later, every single one of them read `(anonymous)`. Every
-- one of 37 hunt Tasks had selected `_anonymous`, because every one of 37
-- claims named no Identity at all:
--
--     hypotheses | names_a | names_b
--     37         | 0       | 0
--
-- Ticket 131 built the whole mechanism and left one end open. It made the Task
-- carry the choice, made `task_identities` the projection of that choice, and
-- made this function open one Task per Identity a claim names. What it did not
-- do -- and said so -- was give anything a way to name one. `identity_a`
-- appears nowhere in the Python runtime: `submit_mission_result` has no field
-- that could carry it and no other caller fills it in. So the LATERAL below
-- has only ever taken its second branch, the one that means "nobody named
-- anybody, hunt as nobody", and the eleven Playbooks written around the
-- difference between two Identities were unreachable by construction.
--
-- THE DECISION, of the three shapes ticket 190 laid out: the runtime derives
-- it, and no new agent surface is added.
--
-- A claim whose subject the recon lane recorded as `authenticated_endpoint`
-- is a claim about a door that asks. Such a claim is hunted once by everyone
-- who can answer -- every non-anonymous Identity this Program has actually
-- provisioned -- and once, as before, by nobody. That last row is not dropped
-- and is the point: an authenticated finding is a comparison, and the
-- anonymous half is one of the two things being compared.
--
-- Why `authenticated_endpoint` and not every subject. Because an Identity is
-- spent, not free. It carries a real account against a real third party, it
-- costs an operator a decision, and on a door that never asks it would answer
-- exactly what the anonymous half already answered. The fact is derived by
-- `subject_facts` from `endpoints.auth_required IS TRUE`, which is the recon
-- lane's own recorded observation and not this file's guess.
--
-- Why provisioned and not merely configured. `resolve_egress_identity` refuses
-- a named slot with no live Lease, and the door has nothing to inject for a
-- slot with no sealed row. A Task pointed at a configured-but-unprovisioned
-- Identity could not reach the target at all, so the join to `identity_slots`
-- is what keeps this from deriving work that cannot run. Note that
-- `subject_facts.multiple_test_identities` asks a weaker question -- two
-- configured Identities, provisioned or not -- so it is deliberately not the
-- predicate here.
--
-- What this widens: nothing. A Task selecting a non-anonymous Identity still
-- reaches `net_borrowed_identity`, is still graded `approval_required` asking
-- `credential_needed`, and still parks for a person before one request leaves.
-- Ticket 190 is explicit that whatever closes this gap leaves an operator a
-- decision to answer rather than routing around one. This file adds Tasks; it
-- does not add authority, and the first authenticated request still stops the
-- hunt until somebody says yes.
--
-- Depends on 20261012T000000Z (this function), 20261101T000000Z (the Task
-- column and its projection), 0003 (`identities`) and the `identity_slots` and
-- `subject_facts` definitions in force. A new file rather than an edit to any
-- of them: a recorded migration whose file has changed is schema drift and
-- `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION rk2_hypothesis_hunt_frontier(p_program_id uuid)
RETURNS TABLE(hypothesis_id uuid, subject_entity_id uuid,
              identity_entity_id uuid, created_at timestamptz)
LANGUAGE sql STABLE AS $fn$
    SELECT h.id, h.subject_entity_id, x.identity_entity_id, h.created_at
      FROM hypotheses h
      JOIN entities e ON e.id = h.subject_entity_id AND e.program_id = h.program_id
      CROSS JOIN LATERAL (
          -- One row per Identity the claim names, or one anonymous row when it
          -- names none. `DISTINCT` because a claim naming nobody unnests two
          -- NULLs and a claim naming one Identity twice is one Task.
          SELECT DISTINCT
                 coalesce(named.id, rk2_anonymous_identity_id(h.program_id))
                     AS identity_entity_id
            FROM (SELECT unnest(ARRAY[h.identity_a_entity_id,
                                      h.identity_b_entity_id]) AS id) named
           WHERE named.id IS NOT NULL
              OR (h.identity_a_entity_id IS NULL AND h.identity_b_entity_id IS NULL)

          UNION

          -- Ticket 190: and everyone who can answer a door that asks. Only
          -- where the claim named nobody, so a claim that did name its
          -- Identities keeps naming exactly them -- this branch supplies a
          -- selection nobody made and never overrides one somebody did.
          -- `UNION` and not `UNION ALL`: the anonymous row is already produced
          -- above and an Identity reached twice is still one Task.
          SELECT i.entity_id
            FROM identities i
            JOIN identity_slots s
              ON s.identity_entity_id = i.entity_id
             AND s.program_id = i.program_id
           WHERE h.identity_a_entity_id IS NULL
             AND h.identity_b_entity_id IS NULL
             AND i.program_id = h.program_id
             AND i.class <> 'anonymous'
             AND i.invalidated_at IS NULL
             AND EXISTS (SELECT 1 FROM subject_facts f
                          WHERE f.program_id = h.program_id
                            AND f.subject_entity_id = h.subject_entity_id
                            AND f.fact = 'authenticated_endpoint')
      ) x
     WHERE h.program_id = p_program_id
       AND h.status = 'testable'
       AND h.superseded_by IS NULL
       AND e.in_scope
       AND NOT EXISTS (SELECT 1 FROM tasks k
                        WHERE k.program_id = h.program_id
                          AND k.kind = 'hunt'
                          AND k.hypothesis_id = h.id
                          AND k.selected_identity_entity_id
                              IS NOT DISTINCT FROM x.identity_entity_id);
$fn$;

COMMENT ON FUNCTION rk2_hypothesis_hunt_frontier(uuid) IS
    'The (claim, Identity) pairs this Program owes a hunt Task and does not '
    'have. One row per Identity a claim names; one anonymous row when it names '
    'none; and, ticket 190, one row per provisioned non-anonymous Identity when '
    'the claim names none and its subject carries the fact '
    '`authenticated_endpoint`. Provisioned means a sealed identity_slots row: '
    'a Task pointed at an Identity the door cannot inject could not reach the '
    'target at all.';


-- The guard. Two statements, and each of them is a way this file could be
-- wrong rather than a restatement of what it just wrote.
DO $$
DECLARE n_anonymous integer; n_named integer; v_program uuid;
BEGIN
    -- (i) Every Program that has claims still owes an anonymous row for each
    --     one that named nobody. This branch is the one every existing hunt
    --     depends on, and a UNION that swallowed it would be silent.
    SELECT count(*) INTO n_anonymous
      FROM hypotheses h
      JOIN entities e ON e.id = h.subject_entity_id
     WHERE h.status = 'testable' AND h.superseded_by IS NULL AND e.in_scope
       AND h.identity_a_entity_id IS NULL AND h.identity_b_entity_id IS NULL
       AND NOT EXISTS (
             SELECT 1 FROM rk2_hypothesis_hunt_frontier(h.program_id) fr
              WHERE fr.hypothesis_id = h.id
                AND fr.identity_entity_id = rk2_anonymous_identity_id(h.program_id))
       AND NOT EXISTS (
             SELECT 1 FROM tasks k
              WHERE k.program_id = h.program_id AND k.kind = 'hunt'
                AND k.hypothesis_id = h.id
                AND k.selected_identity_entity_id
                    = rk2_anonymous_identity_id(h.program_id));
    IF n_anonymous > 0 THEN
        RAISE EXCEPTION
            'the frontier stopped owing an anonymous hunt to % claim(s)', n_anonymous;
    END IF;

    -- (ii) And a claim that named its own Identities is untouched: the count of
    --      rows it produces is the count of distinct Identities it named, with
    --      nothing added.
    SELECT count(*) INTO n_named
      FROM hypotheses h
     WHERE h.status = 'testable' AND h.superseded_by IS NULL
       AND (h.identity_a_entity_id IS NOT NULL OR h.identity_b_entity_id IS NOT NULL)
       AND (SELECT count(*) FROM rk2_hypothesis_hunt_frontier(h.program_id) fr
             WHERE fr.hypothesis_id = h.id)
           > (SELECT count(DISTINCT id) FROM unnest(
                  ARRAY[h.identity_a_entity_id, h.identity_b_entity_id]) id
               WHERE id IS NOT NULL);
    IF n_named > 0 THEN
        RAISE EXCEPTION
            'the frontier added an Identity to % claim(s) that named their own', n_named;
    END IF;
END $$;
