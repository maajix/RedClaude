-- ---------------------------------------------------------------------------
-- Seven classes the rewrite gave an emitter                          (ticket 101)
--
-- Ticket 114 mapped thirty-three Property classes onto the Surface deltas that
-- put them back in question, and left six out with its reason stated at
-- `20260927T010000Z__the_retest_lane_has_an_input_and_a_reader.sql:38-48`:
-- two are `unmakeable` under `transport_makeability`, and four "no Playbook
-- emits". That file also says who would change that -- "101 owns the emitters"
-- -- and this is 101 doing it.
--
-- The rewrite gave three of those four an emitter, and migration
-- `20261215T000000Z__four_readings_the_vocabulary_could_not_spell.sql` added
-- four classes the rewrite emits three of. Six emitted classes therefore have
-- no mapping row, and `rk2_negative_relevant_deltas` inner-joins that table, so
-- each one is a refutation no Surface change can ever reopen -- silently,
-- because an empty join reads exactly like a Surface that never moved.
--
-- One row per section that genuinely settles the class, and never a cross
-- product: 022's argument, quoted at that file's line 59, is that mapping every
-- section to every class makes every delta invalidate every refutation, which
-- is the same as having no mapping at all with more rows to read.
--
-- `transport.certificate_trust` is not here, and not for want of an emitter.
-- `0025_transport_claims.sql:211` declares it `probe_only`: every certificate
-- field an intercepted agent sees belongs to the run CA, so the class rests on
-- a measurement receipt the Finding may not cite. That is ticket 116's subject,
-- and a Playbook emitting a class no Finding can be built on is exactly the
-- unreachable prose this ticket's second criterion refuses.
--
-- `injection.unclaimed_reference` IS here. It arrived from ticket 100 with no
-- emitter; section 3 of `external-resources` is the reading it was spelled for
-- and now declares it, which is the other half of "101 owns the emitters".
-- ---------------------------------------------------------------------------

INSERT INTO surface_delta_property_classes (kind, property_class_id, note)
SELECT k.kind, m.property_class_id, m.note
  FROM (VALUES
    -- A recovery flow is a sequence of routes, and which account it is about
    -- travels as a parameter. Both are how a caller enters somebody else's.
    ('endpoint',  'authentication.recovery_flow',
     'a route that appeared may be a step of a reset a caller can enter for an account that is not theirs'),
    ('parameter', 'authentication.recovery_flow',
     'the parameter that names the account is what a recovery step decides on'),

    -- Which fields a write accepts is settled per route, and a parameter is
    -- the field. The claim is about a property the caller was not offered.
    ('endpoint',  'authorization.object_property_write',
     'what a write accepts is settled per route, so a route that appeared or changed may accept a property its own form never offered'),
    ('parameter', 'authorization.object_property_write',
     'a parameter that appeared is a property a caller can now try to set'),

    -- A reference the target publishes lives in the bytes a route serves, and
    -- which third party it points at is settled by the stack that emits it.
    -- Not `parameter`: the candidate list comes from the target's own served
    -- artefacts and never from an input this reading chooses.
    ('endpoint',  'injection.unclaimed_reference',
     'a route that appeared serves bytes that may carry a reference to a provider slot nobody holds'),
    ('technology', 'injection.unclaimed_reference',
     'which third parties a page references is settled by the framework and the build that emits it, so a version that moved may have added or retired one'),

    -- Two readers of one document disagreeing is a property of the readers.
    -- The value they disagree about arrives as a parameter.
    ('technology', 'injection.parser_differential',
     'which library reads the document decides how it reads it, so a version that moved is a second reader that may now disagree with the first'),
    ('parameter', 'injection.parser_differential',
     'the value two readers disagree about is what a parameter carries'),

    -- 022 mapped `rate_limiting.per_identity` to `endpoint` alone with the
    -- note "a new route is a new thing to repeat". Per-origin is the same
    -- question asked without an Identity, so it takes the same single row.
    ('endpoint',  'rate_limiting.per_origin',
     'a new route is a new thing to repeat from one origin'),

    -- Cost is per route, and what drives the cost is the parameter that states
    -- how much work to do.
    ('endpoint',  'rate_limiting.resource_cost',
     'a route that appeared may be one whose single call costs more than the caller is charged for'),
    ('parameter', 'rate_limiting.resource_cost',
     'the parameter that states a count, a depth or a range is what turns one request into expensive work'),

    -- Cookie parsing is a property of whatever assembles and reads the header,
    -- which is the server and its framework, not any one route.
    ('technology', 'session_handling.cookie_parsing',
     'which server and framework read the cookie header decide how it is split and which duplicate wins, so a version that moved is a different reading of the same header')
  ) AS m(prefix, property_class_id, note)
  JOIN surface_projection_sections s ON s.delta_prefix = m.prefix
  JOIN surface_delta_kinds k ON k.section = s.section AND k.change IN ('added','changed');


-- ===========================================================================
-- What this migration claims, asserted
-- ===========================================================================

DO $$
DECLARE
    n_unmapped integer;
    unmapped   text;
BEGIN
    -- Ticket 114's criterion 1, re-asserted after the rewrite moved the
    -- emitters underneath it: every class a Playbook declares as an output has
    -- a row. This is the assertion 20260927 already carries, and it passed
    -- there because the corpus that made it false is registered later in the
    -- corpus than the file that states it.
    SELECT count(*), string_agg(p.id, ', ' ORDER BY p.id)
      INTO n_unmapped, unmapped
      FROM property_classes p
     WHERE EXISTS (SELECT 1 FROM playbook_outputs o WHERE o.property_class = p.id)
       AND NOT EXISTS (SELECT 1 FROM surface_delta_property_classes m
                        WHERE m.property_class_id = p.id);
    IF n_unmapped > 0 THEN
        RAISE EXCEPTION 'ticket 101: % emitted Property class(es) no delta reaches: %',
            n_unmapped, unmapped;
    END IF;

    -- And 022's decision, which this file adds rows through the same join as:
    -- a route that is gone tests nothing.
    IF EXISTS (SELECT 1 FROM surface_delta_property_classes m
                JOIN surface_delta_kinds k ON k.kind = m.kind
               WHERE k.change = 'removed') THEN
        RAISE EXCEPTION 'ticket 101: a removal was mapped to a Property class';
    END IF;
END $$;
