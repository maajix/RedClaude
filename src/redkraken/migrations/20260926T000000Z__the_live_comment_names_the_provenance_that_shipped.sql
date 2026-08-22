-- ---------------------------------------------------------------------------
-- 20260926T000000Z__the_live_comment_names_the_provenance_that_shipped.sql
--                                                                  (ticket 115)
--
-- 018 wrote one sentence of schema documentation onto
-- `observation_kinds.allowed_provenance` and ended it by sending the reader to
-- a rejection: "see the out_of_band_interaction note in migration 018". That
-- note refused `out_of_band_interaction` because its provenance set would have
-- been empty -- an inbound arrival crosses no proxy, so there is no Receipt,
-- and analyses no stored bytes, so there is no Tool run -- and said what would
-- lift the refusal: "a third `provenance_kind` ('oob_receipt') written by a
-- runtime-controlled listener".
--
-- The third provenance kind shipped four months later under a different name.
-- `20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:337-341`
-- dropped and re-added `observation_kinds_allowed_provenance_closed` to admit
-- `callback`, `:348-350` inserted `callback_interaction` with an
-- `allowed_provenance` of `{callback}`, and the collector that writes it is
-- `record_callback_interaction`, which resolves a correlator the runtime minted
-- and files the arrival against the subject it was minted for. The kind is
-- live, and `playbooks/webhooks` requires it for a supported claim. So the
-- condition 018 named has been met, by a listener the harness controls, and the
-- comment still sends a reader to the refusal.
--
-- WHY A LIVE COMMENT IS WORTH A MIGRATION AND A `--` COMMENT IS NOT.
--
-- The note inside 018 is left exactly where it is, and not because it is right.
-- A recorded migration whose file has changed is schema drift, and `rk db
-- migrate` refuses the whole corpus for it, so the correction has to arrive as
-- a new file whichever comment it is about. What makes the two different is who
-- reads them. The `--` comment is dated by the file it sits in: a reader who
-- reaches it has already been told it is 018 talking, and the corpus practice
-- for that case is to name the superseding ticket in the superseding file,
-- which `20260812T040000Z` did. A `COMMENT ON` has no date on it at all. It is
-- what `\d+ observation_kinds` prints today, so it presents as current schema
-- documentation, and a reader following it arrives at a rejection that was
-- overturned before this schema ever ran against a target.
--
-- The house standard for the repair is already set. `20260922T060000Z:100-104`
-- re-issued `COMMENT ON COLUMN fixture_addresses.protocol` in the file that
-- widened the constraint under it, and said why: "The original is a `--`
-- comment inside a recorded migration file, which cannot be edited, so the rule
-- now says why it is two rather than why it was one." This file does the same
-- thing one migration late, which is the instance ticket 130's G8 rule -- a
-- migration that moves a constraint, a default or a closed set on a column must
-- re-issue that column's `COMMENT ON` in the same file -- exists to make
-- impossible rather than to have to report.
--
-- Depends on 0018 (the column, the closed set and the comment being replaced)
-- and 20260812T040000Z (the third provenance kind, the constraint that admits
-- it and the kind that carries it). Nothing else changes: no constraint moves,
-- no row is written, and the vocabulary is the one those two files agreed on.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The comment says what the schema under it actually admits
-- ===========================================================================

-- The rule 018 stated is kept, because it is still the rule and it is the
-- reason the kind was refused. What is replaced is the pointer: the sentence
-- now carries its own example and names the provenance that lifted it, so a
-- reader of `\d+ observation_kinds` is told the outcome rather than sent to the
-- argument. `record_callback_interaction` is named because a provenance kind is
-- only as real as the collector that writes it, and that name is what a reader
-- greps for next.
COMMENT ON COLUMN observation_kinds.allowed_provenance IS
  'Which provenance_kind values may back an observation of this kind. A kind with no admissible provenance record does not belong in this vocabulary: 018 refused out_of_band_interaction on exactly that ground, because an inbound arrival crosses no proxy and analyses no stored bytes, so it could have named neither of the two records that existed then. 20260812T040000Z built the third record and the refusal is spent. It is callback, written by record_callback_interaction for an arrival on a channel this Program declared, and callback_interaction is admitted on {callback} alone so that a Receipt cannot inherit the weight of an out-of-band confirmation. The listener 018 predicted arrived as a declared callback channel rather than as the oob_receipt it named.';


-- ===========================================================================
-- 2. The migration refuses to finish if the sentence is not true
-- ===========================================================================

-- A comment is documentation, so the only thing that can make this file wrong
-- is the schema disagreeing with what it now says. Each clause of the new
-- sentence is asked of the catalogue rather than assumed: the standing rule
-- about empty provenance sets, the third kind the sentence claims shipped, the
-- collector it names, and the absence of the one this column has spent four
-- months pointing at.
DO $$
DECLARE
    v_comment text;
    v_admitted text[];
BEGIN
    SELECT col_description('observation_kinds'::regclass, a.attnum) INTO v_comment
      FROM pg_attribute a
     WHERE a.attrelid = 'observation_kinds'::regclass
       AND a.attname = 'allowed_provenance';

    IF v_comment IS NULL OR v_comment LIKE '%see the out_of_band_interaction note%' THEN
        RAISE EXCEPTION 'the column comment still sends a reader to the rejection 20260812T040000Z overturned'
          USING ERRCODE = '23514';
    END IF;

    -- The rule the first sentence states, asked of every row rather than of the
    -- one that prompted the ticket. A kind admitted with an empty provenance
    -- set would be the thing 018 refused, arrived by another door.
    IF EXISTS (SELECT 1 FROM observation_kinds WHERE cardinality(allowed_provenance) = 0) THEN
        RAISE EXCEPTION 'an observation kind admits no provenance record at all'
          USING DETAIL = 'the sentence this column carries is the rule, and a row breaks it',
                ERRCODE = '23514';
    END IF;

    -- The third record, in the two places it has to exist for the comment to be
    -- true: the closed set on `observations.provenance_kind`, and the kind that
    -- was inserted the moment that set widened.
    SELECT allowed_provenance INTO v_admitted
      FROM observation_kinds WHERE id = 'callback_interaction';
    IF v_admitted IS DISTINCT FROM ARRAY['callback']::text[] THEN
        RAISE EXCEPTION 'callback_interaction is not admitted on {callback} alone: %',
                        coalesce(v_admitted::text, 'the kind does not exist')
          USING ERRCODE = '23514';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'observations'::regclass
           AND conname = 'observations_provenance_kind_check'
           AND pg_get_constraintdef(oid) LIKE '%''callback''%') THEN
        RAISE EXCEPTION 'observations may not cite a callback, so the kind above can never be written'
          USING ERRCODE = '23514';
    END IF;

    -- The collector, because a provenance kind nothing writes is the empty set
    -- the first sentence refuses, one layer up.
    IF to_regprocedure('record_callback_interaction(text,jsonb,jsonb)') IS NULL THEN
        RAISE EXCEPTION 'the comment names a collector this schema does not hold'
          USING ERRCODE = '23514';
    END IF;

    -- And the name the old sentence pointed at, which was always a forecast.
    -- If some later file ever does ship it, this comment is the one that has to
    -- be re-issued again, and the failure here is where that is found out.
    IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'observations'::regclass
           AND conname = 'observations_provenance_kind_check'
           AND pg_get_constraintdef(oid) LIKE '%oob_receipt%') THEN
        RAISE EXCEPTION 'oob_receipt shipped after all, and this column comment now understates the vocabulary'
          USING ERRCODE = '23514';
    END IF;
END $$;
