-- ---------------------------------------------------------------------------
-- 20260911T000000Z__a_canary_ends_by_verb.sql                         (PH2-70)
--
-- `clear_callback_correlator` has been the way to end a canary early since 014,
-- and there has never been a verb that calls it. Using it meant opening the
-- runtime connection by hand and remembering `set_config('rk2.program_id', ...)`
-- first, because the function filters on `rk2_program()` and answers `false`
-- without it rather than raising. MEASURED on 2026-08-12: the first call
-- returned `false` for a correlator that existed, for exactly that reason.
--
-- The reason to end a canary early is usually that a payload went somewhere it
-- should not have, which is the worst moment to be composing SQL. So this file
-- makes the function answer something an operator can act on -- whether it
-- changed anything, whether this Program has the correlator at all, the channel
-- it was minted on and how many arrivals it had already admitted -- and
-- `rk callback clear` carries it.
--
-- The answer is `jsonb` rather than `boolean`, which is why the function is
-- dropped and recreated: a return type is not something CREATE OR REPLACE may
-- change. Nothing in the tree read the boolean; the only caller that existed is
-- a test that discards it, and `false` survives as `cleared: false`.
--
-- What does not change: the correlator is ended by row id, never by its
-- plaintext, and `callback_correlators` still takes no UPDATE from any role.
-- An operator who can name a correlator id can end that canary and learn what
-- it caught; one who names another Program's gets the answer they would get for
-- a correlator that does not exist, because the two must not be tellable apart.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. The verb
-- ---------------------------------------------------------------------------

DROP FUNCTION clear_callback_correlator(uuid);

CREATE FUNCTION clear_callback_correlator(p_correlator_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_channel  text;
    v_arrivals bigint;
    v_cleared  boolean;
BEGIN
    PERFORM set_actor('runtime');

    -- One statement, so the count and the clearing read one snapshot: an
    -- arrival landing between two statements would be a report saying this
    -- canary was ended having admitted a number that was already stale.
    --
    -- `scoped` is the predicate, written once and used by both halves. A
    -- correlator of another Program matches nothing there, so the outer SELECT
    -- returns no row and every value stays NULL -- which is what an id nobody
    -- minted leaves too. An operator must not be able to use this verb to learn
    -- that somebody else's canary exists.
    WITH scoped AS (
        SELECT t.id, t.channel_name
          FROM callback_correlators t
         WHERE t.id = p_correlator_id
           AND t.program_id = rk2_program()
    ), ended AS (
        UPDATE callback_correlators c
           SET cleared_at = clock_timestamp()
          FROM scoped s
         WHERE c.id = s.id
           AND c.cleared_at IS NULL
        RETURNING c.id
    )
    SELECT s.channel_name,
           EXISTS (SELECT 1 FROM ended),
           (SELECT count(*) FROM callback_interactions ci WHERE ci.correlator_id = s.id)
      INTO v_channel, v_cleared, v_arrivals
      FROM scoped s;

    -- `cleared` is what this call did; `known` is what it found. They differ on
    -- the second clear of the same canary, which is the case the operator most
    -- needs told apart from having named the wrong id.
    RETURN jsonb_build_object(
        'cleared', coalesce(v_cleared, false),
        'known', v_channel IS NOT NULL,
        'channel', v_channel,
        'interactions', coalesce(v_arrivals, 0));
END $fn$;

COMMENT ON FUNCTION clear_callback_correlator(uuid) IS
  'Ends a correlator early and says what it ended: whether this call cleared it, whether this Program has it at all, the channel it was minted on and how many arrivals it already admitted. Idempotent: clearing an already cleared correlator answers cleared false and changes nothing, and one this Program does not have is answered as unknown rather than refused.';

REVOKE ALL ON FUNCTION clear_callback_correlator(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION clear_callback_correlator(uuid) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 2. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer; d text;
BEGIN
    -- Dropping a function drops its grants with it, so both directions have to
    -- be re-asked. `check_callback_admission` is the negative one: the four
    -- callback verbs are the runtime's and no keyholder may execute them.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_callback_admission();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-70 refuses to finish: % callback problem(s): %', n, d;
    END IF;

    -- And `check_runtime_privileges` is the positive one, which is the half a
    -- DROP breaks. `runtime_verb_surface` has carried a row for this verb since
    -- 66, so arm 5 -- a declared verb the runtime cannot execute -- is what a
    -- forgotten GRANT above would come back as. Without this the file would
    -- finish green having left the runtime unable to call its own verb.
    SELECT count(*), string_agg(problem || ' on ' || object || ': ' || detail, '; ')
      INTO n, d FROM check_runtime_privileges();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-70 leaves the runtime surface wrong (% problems): %', n, d;
    END IF;
END $$;
