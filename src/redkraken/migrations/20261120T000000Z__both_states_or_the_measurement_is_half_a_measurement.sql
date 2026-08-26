-- ---------------------------------------------------------------------------
-- 20261120T000000Z__both_states_or_the_measurement_is_half_a_measurement.sql
--                                                                  (ticket 191)
--
-- Every lane that touches a target works the engagement twice: once as nobody,
-- and once as each account this Program has actually provisioned.
--
-- 20261119T000000Z closed half of ticket 190. It gave the hunt frontier a
-- branch that fans a claim out across the provisioned Identities, and gated
-- that branch on the subject carrying `authenticated_endpoint`. Two things were
-- wrong with stopping there, and both are measurements rather than opinions.
--
-- The gate is circular. `authenticated_endpoint` is derived from
-- `endpoints.auth_required IS TRUE`, which is what the recon lane recorded --
-- and the recon lane has only ever walked as nobody:
--
--     kind    | identity | slot_name  | count
--     recon   | IDN3     | _anonymous | 108
--     hunt    | IDN3     | _anonymous | 41
--     perform | IDN3     | _anonymous | 1
--
-- So the fact that decides whether an account is worth spending can only ever
-- be written by a walk that never had one. A surface visible only after
-- sign-in is not recorded, so no claim is made about it, so no Identity is
-- ever fanned out to it. The gate is removed rather than widened: the
-- scheduler already ranks and the lane quota already caps, and a pending Task
-- costs nothing until one of them chooses it.
--
-- The loop leaks at the far end. Ticket 131's note that
-- `derive_hypothesis_hunts` is "the only caller in the corpus that writes one"
-- is still true of every other derivation, and `select_task_identity` fills a
-- NULL with the anonymous Identity. So a hunt that finds something while
-- signed in authors a Test, and `derive_test_performances` opens a `perform`
-- Task that spends that Test signed out. The Test measures a different target
-- state than the claim was made about, comes back negative, and the finding
-- evaporates with nothing recording why. That is repaired in
-- `select_task_identity`, which is the one hook every INSERT into `tasks`
-- passes through -- so the repair is in the place all of them route through
-- rather than in each of them.
--
-- WHAT THIS FILE CHANGES, and the one thing it does not.
--
--   1. `rk2_hunting_identities` is the set both fan-outs read: the anonymous
--      Identity, and every non-anonymous one that is neither invalidated nor
--      unprovisioned. Provisioned means a sealed `identity_slots` row -- the
--      door has nothing to inject without one, and `resolve_egress_identity`
--      refuses a named slot with no live Lease, so a Task pointed at a
--      configured-but-unprovisioned Identity is work that cannot run.
--   2. The hunt frontier fans out over that set, unconditionally, for a claim
--      that named nobody. A claim that named its own Identities still gets
--      exactly those.
--   3. `open_configured_recon` fans out the same way, so the first walk of a
--      root happens once per state. `open_task` gains a fifth argument to say
--      which; the four-argument form is kept and passes NULL, which is the
--      anonymous default every existing caller already relied on.
--   4. `recon` clamps to Identity Leases, because a lane that acts as an
--      account has to hold it: `claim_task` takes the Lease only for a clamped
--      role, and both the door and `rk2_replay_plan` refuse a named slot
--      without one. `task_identities` is backfilled for its existing Tasks in
--      the same transaction, since `claim_task` raises on a clamped Task that
--      names nothing to hold.
--
-- WHAT IT LEAVES OPEN, deliberately and in writing. The far end of the loop is
-- still anonymous. A hunt that finds something while signed in authors a Test,
-- and `derive_test_performances` opens a `perform` Task that spends it signed
-- out -- so an authenticated claim is settled against a target state it was
-- never made about. The repair is one line in `select_task_identity`, and it
-- cannot land here: `performer` runs as a `renderer`, and 0019 forbids a
-- renderer to clamp on the grounds that it "holds no session and drives no
-- identity". That sentence was written about the `reporter`, which renders a
-- document and sends nothing. The `performer` was made a renderer afterwards
-- and drives the replay Lane, which sends real requests to a real target --
-- and `rk2_replay_plan` refuses a named slot with no live Lease, which is a
-- Lease no unclamped role ever takes. Lifting a schema check is not something
-- to fold into a file about derivation, so ticket 192 holds it.
--
-- WHAT IT DOES NOT CHANGE. No authority. A Task selecting a non-anonymous
-- Identity still reaches `net_borrowed_identity`, is still graded
-- `approval_required` asking `credential_needed`, and still parks for a person
-- before one request leaves. This file decides which questions get asked, and
-- an operator still answers every one that spends an account.
--
-- ONE CONSTRAINT THIS FILE INHERITS AND DOES NOT LIFT.
-- `identity_leases_exclusive_idx` is UNIQUE on `identity_entity_id WHERE
-- released_at IS NULL`, with no exemption for the anonymous Identity. Two
-- clamped lanes wanting the same Identity at the same moment serialise, and
-- with three clamped roles that now includes two anonymous lanes. Today the
-- driver claims one Task per `rk run`, so the practical concurrency is one and
-- the index never binds. It would bind the moment a lane quota profile put two
-- clamped lanes in flight together. Ticket 192 holds that question; it is
-- named here so that raising a slot count is not the way anybody discovers it.
--
-- Depends on 20261012T000000Z and 20261119T000000Z (the frontier),
-- 20261101T000000Z (the Task column, its projection and the clamp),
-- 0003 (`identities`), and the `identity_slots` definition in force. A new
-- file rather than an edit to any of them: a recorded migration whose file has
-- changed is schema drift and `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------

SELECT set_actor('runtime', 'ticket 191 both-states derivation');


-- ===========================================================================
-- 1. The set both fan-outs read
-- ===========================================================================

CREATE OR REPLACE FUNCTION rk2_hunting_identities(p_program uuid)
RETURNS SETOF uuid
LANGUAGE sql STABLE AS $fn$
    SELECT rk2_anonymous_identity_id(p_program)
    UNION
    SELECT i.entity_id
      FROM identities i
      JOIN identity_slots s
        ON s.identity_entity_id = i.entity_id
       AND s.program_id = i.program_id
     WHERE i.program_id = p_program
       AND i.class <> 'anonymous'
       AND i.invalidated_at IS NULL;
$fn$;

COMMENT ON FUNCTION rk2_hunting_identities(uuid) IS
    'Every state this Program can work a target in: the anonymous Identity, '
    'and each non-anonymous one that is provisioned -- a sealed identity_slots '
    'row -- and not invalidated. Ticket 191. Unprovisioned is excluded rather '
    'than included and refused later: the door has nothing to inject for a slot '
    'with no sealed row, so such a Task is work that cannot run.';


-- ===========================================================================
-- 2. The hunt frontier, ungated
-- ===========================================================================

CREATE OR REPLACE FUNCTION rk2_hypothesis_hunt_frontier(p_program_id uuid)
RETURNS TABLE(hypothesis_id uuid, subject_entity_id uuid,
              identity_entity_id uuid, created_at timestamptz)
LANGUAGE sql STABLE AS $fn$
    SELECT h.id, h.subject_entity_id, x.identity_entity_id, h.created_at
      FROM hypotheses h
      JOIN entities e ON e.id = h.subject_entity_id AND e.program_id = h.program_id
      CROSS JOIN LATERAL (
          -- One row per Identity the claim named. `DISTINCT` because a claim
          -- naming one Identity twice is one Task.
          SELECT DISTINCT named.id AS identity_entity_id
            FROM (SELECT unnest(ARRAY[h.identity_a_entity_id,
                                      h.identity_b_entity_id]) AS id) named
           WHERE named.id IS NOT NULL

          UNION

          -- Ticket 191: and every state this Program can work, for a claim
          -- that named nobody. This is where the anonymous row now comes
          -- from -- `rk2_hunting_identities` includes it -- so a Program with
          -- no provisioned account derives exactly what it derived before.
          SELECT k.id
            FROM rk2_hunting_identities(h.program_id) k(id)
           WHERE h.identity_a_entity_id IS NULL
             AND h.identity_b_entity_id IS NULL
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
    'have. One row per Identity a claim names; and for a claim that names '
    'none, one row per state in rk2_hunting_identities -- anonymous and each '
    'provisioned account. Ticket 191 removed the earlier gate on '
    '`authenticated_endpoint`: that fact is written by the recon lane, which '
    'until this file had only ever walked as nobody.';


-- ===========================================================================
-- 3. The first walk of a root, once per state
-- ===========================================================================

-- `open_task` gains the Identity as a fifth argument. The body is
-- 20260901's, with two changes and no others: the dedup check reads the
-- Identity as well, and the INSERT writes it.
--
-- Widening the check is a correction and not a new rule. `tasks_live_dedup_idx`
-- has carried `selected_identity_entity_id` since 20261101T000000Z, so the
-- index has always permitted one Task per (subject, Identity) while the check
-- above it refused the second one -- with a message naming the first, which is
-- why nobody noticed the two disagreed. The check now says what the index says.
CREATE OR REPLACE FUNCTION open_task(p_program uuid, p_kind text, p_subject uuid,
                                     p_reason text, p_identity uuid)
RETURNS uuid
LANGUAGE plpgsql AS $fn$
DECLARE
    subject entities%ROWTYPE;
    actor   text;
    prior   text;
    cause   uuid;
    opened  uuid;
    refusal text;
BEGIN
    IF p_reason IS NULL OR btrim(p_reason) = '' THEN
        RAISE EXCEPTION 'a Task is opened with the sentence that licensed it'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    actor := nullif(current_setting('app.actor_kind', true), '');
    IF actor IS NULL THEN
        RAISE EXCEPTION
            'open_task must run inside a session that has declared its actor '
            '(app.actor_kind unset)'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    SELECT * INTO subject FROM entities e
     WHERE e.id = p_subject AND e.program_id = p_program;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'subject % is not an Entity of program %', p_subject, p_program
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    IF subject.scope_class <> 'target' THEN
        RAISE EXCEPTION
            'subject % is %, not a target of the live scope: %',
            subject.label, subject.scope_class, subject.scope_reason
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    SELECT k.label INTO refusal FROM tasks k
     WHERE k.program_id = p_program AND k.kind = p_kind
       AND k.subject_entity_id = p_subject
       AND k.hypothesis_id IS NULL AND k.finding_id IS NULL
       AND k.selected_identity_entity_id
           IS NOT DISTINCT FROM coalesce(p_identity,
                                         rk2_anonymous_identity_id(p_program))
       AND k.status IN ('pending', 'claimed', 'running', 'parked');
    IF FOUND THEN
        RAISE EXCEPTION '% already carries a live % Task against %',
            refusal, p_kind, subject.label
            USING ERRCODE = 'unique_violation';
    END IF;

    INSERT INTO events (program_id, type, actor_kind, payload)
    VALUES (p_program, 'task.opened', actor,
            jsonb_build_object('kind', p_kind,
                               'subject', subject.label,
                               'subject_entity_id', p_subject,
                               'scope_version', subject.scope_version_at,
                               'reason', p_reason))
    RETURNING id INTO cause;

    prior := coalesce(current_setting('app.caused_by_event_id', true), '');
    PERFORM set_config('app.caused_by_event_id', cause::text, true);
    INSERT INTO tasks (program_id, kind, subject_entity_id,
                       selected_identity_entity_id)
    VALUES (p_program, p_kind, p_subject, p_identity)
    RETURNING id INTO opened;
    PERFORM set_config('app.caused_by_event_id', prior, true);

    SELECT ready_for(k) INTO refusal FROM tasks k WHERE k.id = opened;
    IF refusal IS NOT NULL THEN
        RAISE EXCEPTION 'a % Task against % would not be ready: %',
            p_kind, subject.label, refusal
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    RETURN opened;
END $fn$;

COMMENT ON FUNCTION open_task(uuid, text, uuid, text, uuid) IS
    'Open one Task against one subject in one state. A NULL Identity is the '
    'anonymous one, which `select_task_identity` fills in. Ticket 191.';

-- The four-argument form every existing caller uses, kept and delegating. NULL
-- and not the anonymous id spelled out here: which Identity "no Identity" means
-- is `select_task_identity`'s answer and there should go on being one place
-- that gives it.
CREATE OR REPLACE FUNCTION open_task(p_program uuid, p_kind text, p_subject uuid,
                                     p_reason text)
RETURNS uuid
LANGUAGE sql AS $fn$
    SELECT open_task(p_program, p_kind, p_subject, p_reason, NULL::uuid);
$fn$;


CREATE OR REPLACE FUNCTION open_configured_recon(p_program uuid)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    recorded bigint;
    opened   bigint := 0;
    row_     record;
BEGIN
    recorded := record_configured_subjects(p_program);

    -- `metadata ->> 'source'` and not `origin`: `program._project_identities`
    -- writes Entities that are `configured` too, and an identity slot is not
    -- somewhere to send a recon Agent. The one thing this walks is what section
    -- 2 recorded.
    --
    -- Ticket 191: one row per (subject, state) rather than per subject. The
    -- Task predicate gains the Identity for the same reason the frontier's did
    -- -- a root walked as nobody has not been walked while signed in -- and
    -- keeps the widening to any status, which is what makes a second `rk run`
    -- open nothing.
    FOR row_ IN
        SELECT e.id, e.label, k.id AS identity_entity_id
          FROM entities e
          CROSS JOIN rk2_hunting_identities(p_program) k(id)
         WHERE e.program_id = p_program
           AND e.metadata ->> 'source' = 'program_scope'
           AND e.scope_class = 'target'
           AND NOT EXISTS (SELECT 1 FROM tasks t
                            WHERE t.program_id = p_program
                              AND t.kind = 'recon'
                              AND t.subject_entity_id = e.id
                              AND t.hypothesis_id IS NULL
                              AND t.finding_id IS NULL
                              AND t.selected_identity_entity_id
                                  IS NOT DISTINCT FROM k.id)
         ORDER BY e.label, k.id
    LOOP
        PERFORM open_task(p_program, 'recon', row_.id,
                          'the Program''s configured scope admits this subject '
                          'and nothing has mapped it in this state yet',
                          row_.identity_entity_id);
        opened := opened + 1;
    END LOOP;

    RETURN jsonb_build_object('subjects_recorded', recorded, 'tasks_opened', opened);
END $fn$;


-- ===========================================================================
-- 5. A lane that acts as an account holds it
-- ===========================================================================

-- `claim_task` takes the Lease only for a clamped role, and
-- `resolve_egress_identity` refuses a named slot with no live Lease. So a
-- recon or perform Task selecting a real Identity is unreachable until these
-- two roles clamp -- and would fail at the door rather than quietly sending
-- the request as nobody, which is the one thing worse than not sending it.
UPDATE roles SET clamp_to_identity_leases = true
 WHERE role = 'recon';

-- `claim_task` raises on a clamped Task that names nothing to hold, and the
-- projection skipped these Tasks precisely because their roles were not
-- clamped a moment ago. A Task whose run is holding a Lease is left alone: it
-- took what it took, and 20260908T010000Z refuses the projection under a hold.
DO $$
DECLARE r tasks%ROWTYPE; n integer := 0;
BEGIN
    FOR r IN
        SELECT t.* FROM tasks t
          JOIN role_task_kinds m ON m.kind = t.kind
         WHERE m.role = 'recon'
           AND NOT EXISTS (SELECT 1 FROM task_identities ti WHERE ti.task_id = t.id)
           AND NOT EXISTS (SELECT 1 FROM agent_runs ar
                             JOIN identity_leases l ON l.holder_agent_run_id = ar.id
                            WHERE ar.task_id = t.id AND l.released_at IS NULL)
         ORDER BY t.id
    LOOP
        PERFORM rk2_project_task_identities(r);
        n := n + 1;
    END LOOP;
    RAISE NOTICE 'ticket 191: projected task_identities for % Task(s)', n;
END $$;


-- ===========================================================================
-- 6. The guard
-- ===========================================================================

-- Four statements, and each of them is a way this file could be wrong rather
-- than a restatement of what it just wrote.
DO $$
DECLARE n integer; v_program uuid; v_states integer;
BEGIN
    -- (i) A Program with no provisioned account derives exactly what it
    --     derived before: one state, and it is the anonymous one.
    SELECT count(*) INTO n
      FROM programs p
     WHERE NOT EXISTS (SELECT 1 FROM identity_slots s WHERE s.program_id = p.id)
       AND (SELECT count(*) FROM rk2_hunting_identities(p.id)) <> 1;
    IF n > 0 THEN
        RAISE EXCEPTION
            'a Program with nothing provisioned no longer works exactly one state (% of them)', n;
    END IF;

    -- (ii) Every provisioned Program works the anonymous state as well as its
    --      accounts. Losing the anonymous half would make every finding a
    --      comparison with nothing to compare against.
    SELECT count(*) INTO n
      FROM programs p
     WHERE rk2_anonymous_identity_id(p.id) IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM rk2_hunting_identities(p.id) k(id)
                        WHERE k.id = rk2_anonymous_identity_id(p.id));
    IF n > 0 THEN
        RAISE EXCEPTION 'the anonymous state left % Program(s)', n;
    END IF;

    -- (iii) Nothing unprovisioned is offered. A Task pointed at a slot the door
    --       cannot inject is work that cannot run, and deriving it would fill
    --       the queue with refusals.
    SELECT count(*) INTO n
      FROM identities i
      JOIN rk2_hunting_identities(i.program_id) k(id) ON k.id = i.entity_id
     WHERE i.class <> 'anonymous'
       AND NOT EXISTS (SELECT 1 FROM identity_slots s
                        WHERE s.identity_entity_id = i.entity_id
                          AND s.program_id = i.program_id);
    IF n > 0 THEN
        RAISE EXCEPTION 'the derivation offers % unprovisioned Identity(ies)', n;
    END IF;

    -- (iv) No clamped Task is left naming nothing to hold, which is the state
    --      `claim_task` raises on and the one this file could have created.
    SELECT count(*) INTO n
      FROM tasks t
      JOIN role_task_kinds m ON m.kind = t.kind
      JOIN roles r ON r.role = m.role AND r.clamp_to_identity_leases
     WHERE t.status IN ('pending', 'claimed', 'running', 'parked')
       AND NOT EXISTS (SELECT 1 FROM task_identities ti WHERE ti.task_id = t.id);
    IF n > 0 THEN
        RAISE EXCEPTION
            '% live clamped Task(s) name no Identity to hold', n;
    END IF;
END $$;
