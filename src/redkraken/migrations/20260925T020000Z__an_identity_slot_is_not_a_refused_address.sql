-- ---------------------------------------------------------------------------
-- 20260925T020000Z__an_identity_slot_is_not_a_refused_address.sql
--                                                                  (ticket 118)
--
-- 021 gives `entities.scope_class` a default of `denied` and a trigger that
-- refuses an INSERT asserting anything else: an Entity is born denied and the
-- projection is the only thing that may move it. That is the right default for
-- an address and the wrong resting place for a slot, because the same file has
-- a fourth class for a row that has no address at all.
-- `scope_class_of_entity` answers `not_addressable` on its first arm for every
-- selector-less Entity, and an Identity slot is one: nothing may be sent to it,
-- and nobody refused it either.
--
-- Two writers create an Identity Entity with a raw INSERT and only one of them
-- leaves it there. `rk2_anonymous_identity` inserts the Program's `_anonymous`
-- slot the first time a clamped Task needs to act as it, returns, and nothing
-- behind it ever projects, so the row keeps the default until some later
-- configuration change happens to reproject the Program for its own reasons.
-- `program._project_identities` inserts the configured slots with the same four
-- columns and does not project either, and the transaction it runs in does:
-- every answer that keeps a Program open reaches `open_configured_recon` two
-- statements later, and `record_configured_subjects` ends with an unconditional
-- `refresh_scope_projection` for a reason of its own. So the Python is already
-- right and this file is the whole of the repair.
--
-- WHAT IT COSTS IS NOT A COLUMN, IT IS A CHAIN.
--
-- 20260818T000000Z's `rk2_chain_unsoundness` asks whether the subject of any
-- step of a composed chain is `denied`, and it reads that word rather than the
-- `in_scope` boolean on purpose. Its own prose says why: the fourth class is
-- for "an entity that has no address at all -- an identity slot, a technology
-- fingerprint", and reading the boolean "would make every chain composed on one
-- permanently unsound for a reason that is not about scope at all". An Identity
-- Entity nobody projected is sitting in the one class that check does refuse,
-- so the distinction 021 drew is undone at exactly the place the chain leaned
-- on it: a kill chain whose pivot ran as the anonymous Identity reports itself
-- unsound, and the operator is told a subject left scope when none did.
--
-- THE PROJECTION IS ASKED FOR, NOT ASSUMED.
--
-- `refresh_scope_projection` raises when the Program has no live scope version,
-- and `rk2_anonymous_identity` is reached from a trigger on `tasks` rather than
-- from a call somebody wrote. A Program that never compiled a policy can still
-- have a hunt Task inserted into it -- the integrity gate's own negative
-- control for the identity clamp does exactly that -- and turning that INSERT
-- into an exception would be this ticket refusing work it has no opinion about.
-- So the projection runs when there is a version to project against and is
-- skipped when there is not, which is the guard 20260813T090000Z and
-- 20260814T070000Z already write for the same reason at the end of their own
-- walks. Nothing is lost by skipping: `set_scope_version` reprojects every
-- Entity of the Program the first time one exists, so the row is correct before
-- anything can be sent under that version.
--
-- Nothing about the write guard changes. `refresh_scope_projection` still
-- refuses outside a runtime session, and the caller this file adds is already
-- in one: the `entities` INSERT above it emits an Event, so a session that
-- could reach the new statement has already declared its actor.
--
-- Depends on 0021 (the four classes, the projection and its guard),
-- 20260813T090000Z (`add_entity` as it stands, with its origin) and
-- 20260908T010000Z (the function replaced below). A new file rather than an
-- edit to any of them: a recorded migration whose file has changed is schema
-- drift and `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The anonymous Identity is classed when it is created
-- ===========================================================================

-- 20260908T010000Z's body with one statement added at the end. Replaced rather
-- than dropped and recreated: the signature is the same one, and the grant and
-- the comment on it are the ones that file wrote.
CREATE OR REPLACE FUNCTION rk2_anonymous_identity(p_program uuid) RETURNS uuid
LANGUAGE plpgsql AS $fn$
DECLARE v_entity uuid;
BEGIN
    SELECT e.id INTO v_entity
      FROM entities e
     WHERE e.program_id = p_program AND e.type = 'identity'
       AND e.dedup_key = 'anonymous-identity';
    IF FOUND THEN RETURN v_entity; END IF;

    INSERT INTO entities (program_id, type, dedup_key, metadata)
    VALUES (p_program, 'identity', 'anonymous-identity',
            jsonb_build_object('source', 'identity_clamp', 'ticket', '72'))
    RETURNING id INTO v_entity;

    INSERT INTO identities (entity_id, slot_name, class)
    VALUES (v_entity, '_anonymous', 'anonymous');

    -- After both rows and not between them, because the projection is about
    -- the Entity and the Entity is not finished until the slot it stands for
    -- exists. Only on the branch that created one: the early return above
    -- found a row some earlier Task already projected, and re-projecting a
    -- Program to discover that nothing moved is work every clamped Task in the
    -- run would repeat.
    IF EXISTS (SELECT 1 FROM programs p
                WHERE p.id = p_program AND p.scope_version IS NOT NULL) THEN
        PERFORM refresh_scope_projection(p_program);
    END IF;

    RETURN v_entity;
END $fn$;

COMMENT ON FUNCTION rk2_anonymous_identity(uuid) IS
    'The Program''s anonymous Identity, created the first time a clamped Task '
    'needs to act as it. An unauthenticated hunt still occupies one upstream '
    'slot and one cookie jar, so it is leased like any other Identity rather '
    'than being the absence of one. Projected as it is created, so that a slot '
    'with no address rests in not_addressable rather than in the class an '
    'operator''s refusal writes.';


-- ===========================================================================
-- 2. The rows that were written before it did
-- ===========================================================================

-- Every Program already holding an Entity that has no address and is filed
-- under a refusal. A fix to the writer leaves those rows exactly as they are,
-- and they are the ones a chain composed today would be judged against.
--
-- Selected on the absence of a selector rather than on the type, because that
-- is the question `scope_class_of_entity` asks: an Identity Entity may carry a
-- selector -- a slot recorded against the host it was found on -- and one that
-- does is a scope question with an answer this file has no business moving. It
-- is `denied` because a rule says so.
--
-- Per Program and not per row, because the projection has no other shape. A
-- Program reached for its Identity slot has its technology fingerprints
-- corrected on the way past, which is the same defect with the same cause, and
-- an Entity whose class has not moved is not written to at all.
DO $$
DECLARE v_program uuid;
BEGIN
    -- The projection refuses a session with no actor, and a migration has none
    -- of its own. `runtime` because that is what a projection is: 20260908 and
    -- 20260811T150000Z declare the same thing for the same reason.
    PERFORM set_actor('runtime', 'ticket 118 identity projection backfill');

    FOR v_program IN
        SELECT DISTINCT e.program_id
          FROM entities e
          JOIN programs p ON p.id = e.program_id
         WHERE e.scope_selector_kind IS NULL
           AND e.scope_class = 'denied'
           AND p.scope_version IS NOT NULL
         ORDER BY 1
    LOOP
        PERFORM refresh_scope_projection(v_program);
    END LOOP;
END $$;

-- The repair, asserted rather than assumed, in the terms the check that reads
-- this column uses. A row left here would be a Program whose projection ran and
-- did not move it, which would mean the classifier and this file disagree about
-- what an address is.
DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n
      FROM entities e JOIN programs p ON p.id = e.program_id
     WHERE e.scope_selector_kind IS NULL
       AND e.scope_class = 'denied'
       AND p.scope_version IS NOT NULL;
    IF n > 0 THEN
        RAISE EXCEPTION
            '% Entity(ies) with no address are still classed denied', n
          USING DETAIL = 'refresh_scope_projection did not move a row '
                         'scope_class_of_entity calls not_addressable',
                ERRCODE = '23514';
    END IF;
END $$;


-- ===========================================================================
-- 3. `add_entity` stops naming a caller it does not have
-- ===========================================================================

-- The comment 20260813T090000Z wrote says the origin "defaults to the
-- operator's configuration because that is the only caller this function has
-- ever had". There is no such caller: `grep -rn add_entity src/redkraken/*.py`
-- returns nothing. Six statements insert into `entities` without it, and five
-- are inside SQL that states its own scope selector and projects at the end of
-- its own walk; the sixth is `program._project_identities`, which states none
-- because a slot has none and is projected by the transaction it runs in.
--
-- The reason for the default survives the correction and is worth keeping,
-- because it is the honest one: the four origins are `configured`, `imported`,
-- `observed` and `proposed`, and a row nobody named a provenance for is one the
-- Program was configured to look for. This ticket does not route the six
-- through here -- what each of them writes is what a projection is computed
-- from, and section 1 is the one that had no projection behind it -- so what is
-- left to fix is the sentence.
COMMENT ON FUNCTION add_entity(uuid, text, text, text, text, integer, text, text) IS
    'Insert denied, then project. The origin says who caused the row; it '
    'defaults to the operator''s configuration because a row nobody recorded a '
    'provenance for is one the Program was configured to go looking for. No '
    'caller in src/ reaches this function: every writer of entities states its '
    'own scope selector and projects for itself.';
