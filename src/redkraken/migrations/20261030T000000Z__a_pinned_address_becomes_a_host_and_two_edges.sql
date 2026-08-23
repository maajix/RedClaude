-- ===========================================================================
-- Production harness 159 -- recon writes no Host and no edge between a name
--                           and what serves it
-- ===========================================================================
-- `rk2hunt16` on 22 August, the first end-to-end run in this tree:
--
--     hosts          0
--     relationships  DOM1 -same_as-> DOM2 ;  APP2 -runs-> TEC1..TEC4
--
-- `195.201.160.13` is in that database, in `receipts.pinned_ips`, and nowhere
-- else. So the surface says this Program knows two names and four technologies
-- and cannot say that either name is served anywhere.
--
-- Neither missing fact is unknown and neither is a claim a child has to make.
-- The door has to pin what it dialled, so `src/redkraken/proxy.py:pinned_ips`
-- writes the address on every egress; `applications.base_url` parses to a host
-- name through `rk2_parse_base_url`; and that name is the name the Receipt
-- requested. Both edges are joins over rows this harness wrote itself.
--
-- Four decisions this file makes.
--
-- **The writer is the runtime, not a proposal.** A child asked to propose the
-- address it was answered with would be a child asked to repeat the Receipt,
-- and `incompatible_provenance` (145) is already the cost of that pattern. So
-- the origin is `observed` -- 013's word for "the runtime saw it", which has
-- been in `rk2_origins()` since it was written and has had no writer until now.
--
-- **Only an allowed Receipt.** A blocked Receipt can carry a pinned address
-- too: the door records what it *would* have dialled. That is a resolution and
-- not a reach, and criterion 1 asks for "an address this Program actually
-- reached".
--
-- **The scope projection is not bypassed.** The Host is inserted denied like
-- every other Entity and classified by `refresh_scope_projection`. An address
-- that answered for an in-scope name is not itself necessarily in the scope
-- document, and the honest record of that is a Host row whose scope class says
-- `denied` -- not an absent row, and not a row this file classified itself.
--
-- **The subdomain edge is display, not vocabulary.** Criterion 4 asks the
-- question and this is the answer: `domains.apex` already carries the fact,
-- `relationship_directions` has no `domain -> domain` type but `same_as`, and
-- `same_as` means the two rows are one subject, which a subdomain and its apex
-- are not. Adding a type would put a second copy of `apex` in a table that can
-- disagree with it. The relation stays derived and the console draws it, which
-- is what `~/engagements/*/graph.py` already does, labelled `subdomain of` and
-- joined on `d.apex = d2.fqdn`. Nothing here writes it, and nothing here writes
-- it as `same_as`.

-- ---------------------------------------------------------------------------
-- 1. The verb
-- ---------------------------------------------------------------------------
-- One receipt or all of them. The single-receipt form is what a test and a
-- future per-exchange caller want; the whole-Program form is what the promotion
-- step calls, because a lap's Receipts and a lap's Applications land in the same
-- transaction and either can be the half that was missing. Both are the same
-- walk with one predicate different, so there is one function.
--
-- Idempotent by construction. The Entity converges on `(program_id, type,
-- dedup_key)` and the Relationship on `(src, dst, type)`, both of which are
-- existing unique keys; a second Receipt for the same name touches
-- `last_seen_at` and writes nothing else. Provenance is the one place a second
-- Receipt legitimately adds a row -- it is a record of which evidence showed
-- what -- and re-reading one Receipt does not, which is why those three inserts
-- are guarded by their own evidence rather than by `ON CONFLICT`: the unique key
-- there includes two nullable columns, and NULLs do not conflict.

CREATE FUNCTION record_receipt_topology(p_receipt uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p          uuid := rk2_program_required();
    r          record;
    v_name     text;
    v_domain   uuid;
    v_address  text;
    v_host     uuid;
    v_app      uuid;
    v_edge     uuid;
    v_hosts    integer := 0;
    v_resolves integer := 0;
    v_serves   integer := 0;
    v_wrote    boolean := false;
BEGIN
    FOR r IN
        SELECT rc.id, rc.host, rc.pinned_ips
          FROM receipts rc
         WHERE rc.program_id = p
           AND rc.decision = 'allowed'
           AND rc.host IS NOT NULL
           AND coalesce(btrim(rc.pinned_ips), '') <> ''
           AND (p_receipt IS NULL OR rc.id = p_receipt)
         ORDER BY rc.ts_arrival, rc.id
    LOOP
        v_name := scope_normalize_host(r.host);
        CONTINUE WHEN v_name IS NULL;

        -- The name as a subject, if this Program has promoted it. A Receipt
        -- naming a Domain nobody promoted still yields the Host: the address is
        -- a fact about the reach either way, and criterion 2's edge is the part
        -- that needs both ends.
        SELECT d.entity_id INTO v_domain
          FROM domains d JOIN entities e ON e.id = d.entity_id
         WHERE e.program_id = p AND d.fqdn = v_name
         LIMIT 1;

        FOREACH v_address IN ARRAY string_to_array(r.pinned_ips, ',') LOOP
            v_address := scope_normalize_host(v_address);
            -- An address and not a name. `scope_normalize_host` accepts both,
            -- and `hosts.address` is `inet`: a hostname arriving here would be
            -- a door that recorded something other than what it dialled.
            CONTINUE WHEN v_address IS NULL
                       OR v_address !~ '^([0-9]{1,3}(\.[0-9]{1,3}){3}|[0-9a-f:]+)$';

            PERFORM set_actor('runtime');
            INSERT INTO entities
                (program_id, type, dedup_key, origin,
                 scope_selector_kind, scope_selector)
            VALUES (p, 'host', rk2_dedup_key('host', ARRAY[v_address]),
                    'observed', 'host', v_address)
            ON CONFLICT (program_id, type, dedup_key)
                DO UPDATE SET last_seen_at = now()
            RETURNING id, (xmax = 0) INTO v_host, v_wrote;
            IF v_wrote THEN
                v_hosts := v_hosts + 1;
            END IF;

            INSERT INTO hosts (entity_id, address)
            VALUES (v_host, v_address::inet)
            ON CONFLICT (entity_id) DO UPDATE
               SET address = coalesce(hosts.address, EXCLUDED.address);

            INSERT INTO entity_provenance
                (program_id, entity_id, origin, element_path, receipt_id)
            SELECT p, v_host, 'observed', 'receipts.pinned_ips', r.id
             WHERE NOT EXISTS (SELECT 1 FROM entity_provenance ep
                                WHERE ep.entity_id = v_host
                                  AND ep.origin = 'observed'
                                  AND ep.receipt_id = r.id);

            -- Criterion 2: the name answered with this address.
            IF v_domain IS NOT NULL AND v_domain <> v_host THEN
                INSERT INTO relationships
                    (program_id, src_entity_id, dst_entity_id, type, origin)
                VALUES (p, v_domain, v_host, 'resolves_to', 'observed')
                ON CONFLICT (src_entity_id, dst_entity_id, type)
                    DO UPDATE SET last_seen_at = now()
                RETURNING id, (xmax = 0) INTO v_edge, v_wrote;
                IF v_wrote THEN
                    v_resolves := v_resolves + 1;
                END IF;

                INSERT INTO relationship_provenance
                    (program_id, relationship_id, origin, element_path, receipt_id)
                SELECT p, v_edge, 'observed', 'receipts.pinned_ips', r.id
                 WHERE NOT EXISTS (SELECT 1 FROM relationship_provenance rp
                                    WHERE rp.relationship_id = v_edge
                                      AND rp.origin = 'observed'
                                      AND rp.receipt_id = r.id);
            END IF;

            -- Criterion 3: what that address serves. Every Application whose
            -- base URL parses to this name, because one address can serve
            -- several and the schema has no reason to pick one.
            FOR v_app IN
                SELECT a.entity_id
                  FROM applications a
                  JOIN entities e ON e.id = a.entity_id
                 CROSS JOIN LATERAL rk2_parse_base_url(a.base_url) u
                 WHERE e.program_id = p AND u.host = v_name
                 ORDER BY a.entity_id
            LOOP
                CONTINUE WHEN v_app = v_host;
                INSERT INTO relationships
                    (program_id, src_entity_id, dst_entity_id, type, origin)
                VALUES (p, v_host, v_app, 'serves', 'observed')
                ON CONFLICT (src_entity_id, dst_entity_id, type)
                    DO UPDATE SET last_seen_at = now()
                RETURNING id, (xmax = 0) INTO v_edge, v_wrote;
                IF v_wrote THEN
                    v_serves := v_serves + 1;
                END IF;

                INSERT INTO relationship_provenance
                    (program_id, relationship_id, origin, element_path, receipt_id)
                SELECT p, v_edge, 'observed', 'receipts.pinned_ips', r.id
                 WHERE NOT EXISTS (SELECT 1 FROM relationship_provenance rp
                                    WHERE rp.relationship_id = v_edge
                                      AND rp.origin = 'observed'
                                      AND rp.receipt_id = r.id);
            END LOOP;
        END LOOP;
    END LOOP;

    -- One projection for the whole walk, and only when there is something to
    -- project. Every Host above was inserted denied; this is what turns the
    -- scope document's answer into the stored class, and re-running it at the
    -- same version writes nothing.
    IF v_hosts > 0 THEN
        PERFORM refresh_scope_projection(p);
    END IF;

    RETURN jsonb_build_object('hosts', v_hosts,
                              'resolves_to', v_resolves,
                              'serves', v_serves);
END $fn$;

COMMENT ON FUNCTION record_receipt_topology(uuid) IS
  'Ticket 159: the two facts a recon lap already holds and never recorded -- the address a name answered with, and the Application that address serves. Reads allowed Receipts and writes Host Entities, `resolves_to` and `serves` edges under the `observed` origin, because every one of them is a row this harness wrote itself. Idempotent: a second Receipt for the same name touches last_seen_at and adds provenance, and nothing else.';

REVOKE ALL ON FUNCTION record_receipt_topology(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION record_receipt_topology(uuid) TO rk2_runtime;

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('record_receipt_topology(uuid)',
     '159',
     'reads receipts.pinned_ips back into surface as Host Entities and the resolves_to and serves edges; the runtime''s, because a child proposing it would be a child repeating the Receipt');

-- ---------------------------------------------------------------------------
-- 2. The standing check
-- ---------------------------------------------------------------------------

CREATE FUNCTION check_receipt_topology() RETURNS TABLE (problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) an observed Host says what address it is. The type's own CHECK admits
    -- a hostname instead; this walk never writes one, and a row that had one
    -- would be a Host from somewhere else wearing this origin.
    SELECT 'observed_host_has_no_address', e.label
      FROM entities e
      JOIN hosts h ON h.entity_id = e.id
     WHERE e.type = 'host' AND e.origin = 'observed' AND h.address IS NULL
    UNION ALL
    -- (b) and names the Receipt it was read out of. `observed` means the
    -- runtime saw it; a row with no evidence is a row nothing saw.
    SELECT 'observed_host_cites_no_receipt', e.label
      FROM entities e
     WHERE e.type = 'host' AND e.origin = 'observed'
       AND NOT EXISTS (SELECT 1 FROM entity_provenance ep
                        WHERE ep.entity_id = e.id AND ep.origin = 'observed'
                          AND ep.receipt_id IS NOT NULL)
    UNION ALL
    -- (c) the same of the edges, which is the half that would rot silently: an
    -- edge whose evidence was purged is an edge nobody can check.
    SELECT 'observed_edge_cites_no_receipt', s.label || ' -' || r.type || '-> ' || d.label
      FROM relationships r
      JOIN entities s ON s.id = r.src_entity_id
      JOIN entities d ON d.id = r.dst_entity_id
     WHERE r.origin = 'observed' AND r.type IN ('resolves_to', 'serves')
       AND NOT EXISTS (SELECT 1 FROM relationship_provenance rp
                        WHERE rp.relationship_id = r.id AND rp.origin = 'observed'
                          AND rp.receipt_id IS NOT NULL)
    UNION ALL
    -- (d) criterion 4, as a rule rather than as a paragraph: the subdomain
    -- relation stays derived, and nothing writes it as `same_as` between a name
    -- and its own apex.
    SELECT 'subdomain_written_as_same_as', s.label || ' -same_as-> ' || d.label
      FROM relationships r
      JOIN entities s ON s.id = r.src_entity_id
      JOIN entities d ON d.id = r.dst_entity_id
      JOIN domains ds ON ds.entity_id = s.id
      JOIN domains dd ON dd.entity_id = d.id
     WHERE r.type = 'same_as' AND ds.fqdn <> dd.fqdn AND ds.apex = dd.fqdn;
$fn$;

COMMENT ON FUNCTION check_receipt_topology() IS
  'Ticket 159: every Host and every edge this runtime read out of a Receipt says which Receipt, an observed Host carries the address it was read from, and no subdomain has been recorded as `same_as` its own apex.';

REVOKE ALL ON FUNCTION check_receipt_topology() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION check_receipt_topology() TO rk2_runtime, rk2_human;

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('check_receipt_topology()',
     '159',
     'the standing check that surface read out of a Receipt names the Receipt, and that the subdomain relation stayed derived');

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('receipt_topology',
     'SELECT * FROM check_receipt_topology()',
     '159',
     'A name, the address it answered with and the Application that address serves: every observed Host carries an address and a Receipt, every observed resolves_to and serves edge carries a Receipt, and no subdomain is recorded as `same_as` its apex.');

SELECT apply_state_rls();
SELECT apply_state_grants();
SELECT enforce_always_triggers();
