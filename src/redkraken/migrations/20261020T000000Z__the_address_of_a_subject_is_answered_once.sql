-- ---------------------------------------------------------------------------
-- the_address_of_a_subject_is_answered_once.sql   (ticket 157)
--
-- "Where does a request for this Entity go" was answered in two places. 143
-- put `rk2_subject_addressable` in `ready_for`, testing `applications` and
-- `endpoints`; `execution.STARTED` resolves the URL itself, in an inline CASE
-- over the same two tables. Two copies of one rule, one in SQL and one in a
-- Python string, either of which can be changed without the other. A predicate
-- that says yes where the dispatch says NULL sends a Task to be retired; a
-- predicate that says no where the dispatch could have resolved one freezes
-- work that was runnable.
--
-- `rk2hunt16` on 22 August froze the second kind. Claim H1 was promoted against
-- DOM1, the domain `www.yekta-it.de`, and `https://www.yekta-it.de` was in
-- `applications` the whole time. `ready_for` answered `hunt.no_address` and the
-- hunt Task never left `pending`.
--
-- So the question gets one answer. `rk2_subject_url` is the dispatch slice's
-- CASE, moved here and given the two arms the CASE could not have: a Domain and
-- a Host resolve to the Application the Program holds on that name.
-- `rk2_subject_addressable` becomes "that answer is not NULL", which is what it
-- always meant, and `execution.STARTED` calls the function instead of carrying
-- its own copy.
-- ---------------------------------------------------------------------------

-- ===========================================================================
-- 1. The one answer
-- ===========================================================================

-- Written out so that both name arms above ask it identically, and because
-- "the Application on this name" is a sentence the schema will want again.
CREATE FUNCTION rk2_application_on(p_program uuid, p_name text) RETURNS text
LANGUAGE sql STABLE AS $fn$
    SELECT a.base_url
      FROM applications a
      JOIN entities ae ON ae.id = a.entity_id
      JOIN LATERAL rk2_parse_base_url(a.base_url) u ON true
     WHERE ae.program_id = p_program
       AND p_name IS NOT NULL
       AND u.host = p_name
     ORDER BY (u.scheme = 'https') DESC, u.port, a.base_url
     LIMIT 1
$fn$;

COMMENT ON FUNCTION rk2_application_on(uuid, text) IS
    'The one Application this Program holds on that host name, or NULL. The order '
    'is the tie-break rk2_subject_url documents and is part of the contract: two '
    'callers must not resolve one name to two listeners.';

-- The four arms, in the order that decides them. An Endpoint before an
-- Application because an Endpoint has one and the path is the point of it; a
-- name last, because a name is not a place until the Program holds something
-- served there.
--
-- The name arms take the Application whose base URL is ON that name, asked
-- through `rk2_parse_base_url` rather than by pattern: `base_url LIKE
-- '%www.yekta-it.de%'` also matches `https://not-www.yekta-it.de`, and a scope
-- decision made on a substring is not a scope decision.
--
-- One name can carry more than one Application. 20260813 settled that this is
-- correct -- "one listener speaks one scheme, so http and https on the same
-- port are two subjects and not one seen twice" -- so the pick has to be
-- stated rather than left to the planner, and it is: https first, then the
-- lower port, then the base URL ascending. Every call gets the same answer,
-- and it is the more defended of the two listeners, which is the one a claim
-- about a vhost is nearly always about.
--
-- A wildcard Domain resolves to nothing on purpose. `*.example.net` names a
-- set of hosts and this build enumerates none of them; the Application it
-- would join to is an Application on some other name that happens to share an
-- apex. `FirstTaskTest` holds the case as the wildcard Domain standing
-- beside its configured Application.
CREATE FUNCTION rk2_subject_url(p_entity uuid) RETURNS text
LANGUAGE sql STABLE AS $fn$
    SELECT CASE
        WHEN ep.entity_id IS NOT NULL THEN
            rtrim(pa.base_url, '/')
            || CASE WHEN left(ep.path_template, 1) = '/' THEN ep.path_template
                    ELSE '/' || ep.path_template END
        WHEN ap.entity_id IS NOT NULL THEN ap.base_url
        WHEN dm.entity_id IS NOT NULL AND NOT dm.wildcard THEN
            rk2_application_on(e.program_id, dm.fqdn)
        WHEN ho.entity_id IS NOT NULL THEN
            rk2_application_on(e.program_id, ho.hostname)
    END
      FROM entities e
      LEFT JOIN endpoints    ep ON ep.entity_id = e.id
      LEFT JOIN applications pa ON pa.entity_id = ep.application_id
      LEFT JOIN applications ap ON ap.entity_id = e.id
      LEFT JOIN domains      dm ON dm.entity_id = e.id
      LEFT JOIN hosts        ho ON ho.entity_id = e.id
     WHERE e.id = p_entity
$fn$;

COMMENT ON FUNCTION rk2_subject_url(uuid) IS
    'Where a request for this Entity goes, or NULL for one nothing can be aimed '
    'at. An Endpoint resolves to its Application and path, an Application to its '
    'base URL, and a Domain or Host to the Application this Program holds on that '
    'name -- https first, then the lower port, then the base URL ascending. Read '
    'by ready_for through rk2_subject_addressable and by execution.STARTED, which '
    'is the point: one question, one answer.';

REVOKE ALL ON FUNCTION rk2_subject_url(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_application_on(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_subject_url(uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_application_on(uuid, text) TO rk2_runtime;


-- ===========================================================================
-- 2. The predicate, in terms of it
-- ===========================================================================

-- What it always meant. `ready_for` is not touched at all: its two `no_address`
-- arms already ask this function and now get a better answer from it.
--
-- NULL in, NULL out is kept. "Is this subject addressable" has no answer about
-- a Task that names no subject, and `recon.no_subject` is the sentence for
-- that one.
CREATE OR REPLACE FUNCTION rk2_subject_addressable(p_entity uuid) RETURNS boolean
LANGUAGE sql STABLE AS $fn$
    SELECT CASE WHEN p_entity IS NULL THEN NULL
                ELSE rk2_subject_url(p_entity) IS NOT NULL END
$fn$;

COMMENT ON FUNCTION rk2_subject_addressable(uuid) IS
    'Whether rk2_subject_url can resolve a target URL from this Entity. NULL for '
    'no Entity at all. Defined in terms of the resolution rather than beside it, '
    'so a predicate that says yes and a dispatch that finds nothing cannot both '
    'be right.';


-- ===========================================================================
-- 3. The surface
-- ===========================================================================

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
  ('rk2_subject_url(uuid)', '157',
   'where a request for this Entity goes; read by execution.STARTED and by rk2_subject_addressable'),
  ('rk2_application_on(uuid, text)', '157',
   'the one Application this Program holds on a host name; read by rk2_subject_url and by nothing else');
