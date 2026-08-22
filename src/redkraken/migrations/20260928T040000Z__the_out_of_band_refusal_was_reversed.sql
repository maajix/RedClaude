-- ---------------------------------------------------------------------------
-- 20260928T040000Z__the_out_of_band_refusal_was_reversed.sql
--                                                                   (ticket 98)
--
-- Migration 018 refused to put an out-of-band observation kind in the
-- vocabulary, and said why at length: "it cannot be in the vocabulary, because
-- its `allowed_provenance` would be empty: the interaction is INBOUND. It never
-- crosses the scope proxy, so there is no receipt; it is not analysis of a
-- stored artifact, so there is no tool run." It then named the condition under
-- which the refusal lapses -- "it goes back in when the collector that
-- generates its provenance exists: a third `provenance_kind` written by a
-- runtime-controlled listener" -- and pointed the column comment at itself, so
-- that a reader who asks what `allowed_provenance` means is sent to the
-- refusal.
--
-- Every part of that condition was met by ticket 14, two years of tickets
-- later. The third `provenance_kind` is `'callback'`. The collector is
-- `record_callback_interaction`, beneath a listener whose channel the scope
-- policy declares. And the kind went in: `callback_interaction`, evidential,
-- backed by `{callback}` alone. So 018's note is not a decision any more, it is
-- a decision that was reversed, and it is still the text the column comment
-- sends a reader to.
--
-- WHY A COMMENT AND NOTHING ELSE.
--
-- Because nothing is wrong. The vocabulary is right, the provenance is right,
-- the trigger beneath both is right; the only defect is that the most detailed
-- paragraph in the corpus on this subject argues for the opposite of what the
-- corpus does, and a reader who finds it first is being told the capability
-- does not exist. A migration cannot edit 018's `--` lines and should not want
-- to: what applied, applied. What it can do is move the pointer, so the comment
-- a reader actually meets says where the argument ended rather than where it
-- started.


-- ===========================================================================
-- 1. The pointer, moved
-- ===========================================================================

COMMENT ON COLUMN observation_kinds.allowed_provenance IS
    'Which provenance_kind values may back an observation of this kind. A kind '
    'with no admissible provenance record does not belong in this vocabulary. '
    'Migration 018 states that rule at length by refusing an out-of-band kind '
    'for having no admissible provenance -- that refusal is SPENT and is kept '
    'only as the reasoning: ticket 14 built the collector 018 named as its own '
    'condition, added the third provenance_kind ''callback'', and admitted '
    'callback_interaction backed by {callback}. Read 018''s note as the '
    'argument, not as the state of this vocabulary.';

-- And the same sentence where the kind itself is, because the two readers are
-- different people: one is asking what the column means and the other is
-- asking what this row is. 018's note claims this row cannot exist.
COMMENT ON TABLE observation_kinds IS
    'The closed vocabulary of what an Observation can be, with the provenance '
    'records admissible for each. Extended once since 018 declared it: ticket '
    '14 added callback_interaction, whose only admissible provenance is the '
    'inbound arrival 018 argued could have none, and ticket 98 made both the '
    'minting of a correlator and the citing of an arrival reachable from a '
    'Playbook step rather than only from an operator''s terminal.';


-- ===========================================================================
-- 2. What this migration claims, asserted
-- ===========================================================================

-- A comment-only file still has one claim, and it is the claim the comments
-- make: that 018's condition was met. If any part of it stopped being true --
-- the kind withdrawn, the provenance word removed, the backing narrowed -- then
-- these comments would be as wrong as the note they supersede, and the honest
-- moment to find that out is the moment the schema is built.
DO $$
DECLARE v_allowed text[];
BEGIN
    SELECT allowed_provenance INTO v_allowed
      FROM observation_kinds WHERE id = 'callback_interaction';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ticket 98: callback_interaction is not in the vocabulary, '
                        'so migration 018''s refusal is not spent after all';
    END IF;
    IF v_allowed IS DISTINCT FROM ARRAY['callback'] THEN
        RAISE EXCEPTION 'ticket 98: callback_interaction is backed by %, not by the '
                        'inbound arrival 018 said it could never have', v_allowed
          USING ERRCODE = '23514';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'observations'::regclass
           AND conname = 'observations_provenance_kind_check'
           AND pg_get_constraintdef(oid) LIKE '%callback%'
    ) THEN
        RAISE EXCEPTION 'ticket 98: an Observation may no longer have callback provenance';
    END IF;
END $$;
