-- ---------------------------------------------------------------------------
-- 20260912T000000Z__an_out_of_band_host_is_bound_not_declared.sql      (PH2-69)
--
-- Two limits of the interactsh channels the 2026-08-12 live run used, and one
-- table that removes both.
--
-- A canary cannot carry a payload: an XXE against a target that resolves
-- external entities needs a DTD the target can fetch, and interactsh answers a
-- fixed body. So the exploit file lived on a hand-rolled server behind a
-- tunnel, outside the harness and outside the record -- and the fetch of that
-- file, which is exactly the inbound request an out-of-band channel exists to
-- see, produced no Observation.
--
-- Running that file host ourselves needs two things this schema did not have.
--
-- FIRST, a correlator that is not a DNS label. MEASURED on 2026-08-12 against a
-- live quick tunnel: one hostname, no wildcard, path and query forwarded
-- verbatim including `/<32 hex>/x.dtd?q=1`. A host that cannot vary its labels
-- carries no correlator under `callback_correlator_label`, so every arrival
-- would be refused -- correctly, and uselessly. What the tunnel does give is
-- the path. A channel therefore states a `placement`: `label`, which is what
-- every channel does today and the only thing a `dns` channel may do, or
-- `path`, where the correlator is the first segment and the rest is the
-- payload's business.
--
-- SECOND, an endpoint that is not in the policy. `program_callback_channels`
-- is immutable with its scope version, which is right: a declaration should not
-- drift. But a quick tunnel's name lasts as long as the process, so it is a
-- fact about today rather than a declaration -- and putting it in the compiled
-- policy would change `policy_sha256` every morning and make the Program's
-- identity depend on Cloudflare's word list. So a channel states a `provider`
-- instead of a host, and the name it was given lives in `callback_channel_
-- bindings`, appended when a tunnel starts and released when it stops.
--
-- The join between the two is `callback_correlators.binding_id`. A correlator
-- minted against yesterday's name is dead on its own terms this morning: it
-- cites a binding that is released, so the resolver does not return it and the
-- attribution trigger refuses an arrival claiming it. Nothing has to remember
-- to clean anything up, which is the property the ticket is about -- an
-- operator who pauses overnight and restarts in the morning gets a new name and
-- no correlator that outlives the old one.
--
-- What does not change: the correlator is still a digest, the plaintext is
-- still stored nowhere, the four callback verbs are still the runtime's alone,
-- and a channel still admits an arrival or the arrival is not written.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. The channel says where its correlator sits and who gives it a name
-- ---------------------------------------------------------------------------
-- Both columns default to what every existing row means, so the projection of a
-- policy compiled before this file is the same rows it was: a channel that
-- named a host declared it itself, and a canary addressed by label is what
-- `callback_correlator_label` has always read.
--
-- `host` becomes nullable and the two are tied: a `static` channel has a host
-- and a dynamic one has none. Storing the tunnel's name here instead would be
-- the drift this file exists to avoid, and leaving the column filled with a
-- stale name would be worse -- a declaration that says one thing while the
-- admission path reads another.

ALTER TABLE program_callback_channels
    ADD COLUMN placement text NOT NULL DEFAULT 'label'
        CHECK (placement IN ('label','path')),
    ADD COLUMN provider  text NOT NULL DEFAULT 'static'
        CHECK (provider IN ('static','cloudflare-quick')),
    ALTER COLUMN host DROP NOT NULL,
    ADD CONSTRAINT program_callback_channels_endpoint_is_declared_or_bound
        CHECK ((provider = 'static') = (host IS NOT NULL)),
    -- A DNS query has no path and a quick tunnel is an HTTPS name, so both of
    -- the new spellings are HTTP's. A `dns` channel keeps exactly the shape it
    -- had, which is the shape the DNS listener can address.
    ADD CONSTRAINT program_callback_channels_dns_is_a_declared_label
        CHECK (kind = 'http' OR (placement = 'label' AND provider = 'static'));

COMMENT ON COLUMN program_callback_channels.placement IS
  'Where an arrival carries its correlator: `label`, the label beneath the endpoint, or `path`, the first path segment. One question, asked by whichever function this names.';

COMMENT ON COLUMN program_callback_channels.provider IS
  'Who gives this channel its name. `static` is the declared host; anything else is bound at run time and recorded in callback_channel_bindings, because a name that changes daily is not a declaration.';

COMMENT ON COLUMN program_callback_channels.host IS
  'The declared channel endpoint, for a static channel. An arrival at this name, or at any name beneath it, is admitted; its parent, its siblings and every undeclared host are not. Null for a channel whose provider binds a name at run time.';


-- ---------------------------------------------------------------------------
-- 2. The binding: the name a provider handed us today
-- ---------------------------------------------------------------------------
-- Appended when a tunnel starts, released when it stops, and never rewritten
-- otherwise -- the same rule `callback_correlators` follows and for the same
-- reason: a binding whose endpoint could be edited is a binding that cannot say
-- which name an arrival came in at.
--
-- `evidence_sha256` is the tunnel's own startup output, stored like any other
-- evidence. It is the only record of where the name came from, and a hostname
-- with nothing behind it is a claim rather than a measurement.
--
-- `tunnel_pid` is not in the ticket's column list and is here because its
-- lifecycle rule needs it: "on start, a binding whose tunnel process is gone is
-- released before anything else happens". A pid is a fact about one machine,
-- which is the machine that ran the tunnel and wrote this row; nothing else
-- reads it.

CREATE TABLE callback_channel_bindings (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    scope_version integer NOT NULL,
    channel_name  text NOT NULL,
    -- Never 'static': a declared host is a declaration and needs no binding,
    -- and a row here for one would be a second answer to "what is this
    -- channel's endpoint".
    provider      text NOT NULL CHECK (provider IN ('cloudflare-quick')),
    endpoint_host text NOT NULL CHECK (endpoint_host = lower(endpoint_host)
                                       AND endpoint_host <> ''
                                       AND position('*' IN endpoint_host) = 0),
    tunnel_pid    integer CHECK (tunnel_pid IS NULL OR tunnel_pid > 0),
    bound_at      timestamptz NOT NULL DEFAULT now(),
    released_at   timestamptz,
    evidence_sha256 text NOT NULL REFERENCES artifacts(sha256),
    -- What `callback_correlators` cites, in 017 rule 3's shape.
    CONSTRAINT callback_channel_bindings_id_program_key UNIQUE (id, program_id),
    -- The channel as of the version the binding was made under, so a binding
    -- names a declaration that existed rather than a name that might be
    -- declared later.
    FOREIGN KEY (program_id, scope_version, channel_name)
        REFERENCES program_callback_channels (program_id, version, name),
    CHECK (released_at IS NULL OR released_at >= bound_at)
);

-- One live name per channel. Two would make "which endpoint is this channel's"
-- a question about row order, and a correlator minted in between would be
-- addressed at whichever the writer happened to read.
CREATE UNIQUE INDEX callback_channel_bindings_live_idx
    ON callback_channel_bindings (program_id, channel_name)
 WHERE released_at IS NULL;

COMMENT ON TABLE callback_channel_bindings IS
  'The endpoint a dynamic channel is answering on right now, and every endpoint it has answered on. Appended by `bind_callback_channel` and ended by `release_callback_binding`; nothing else writes it, and a released row is the record of a name that is gone.';

COMMENT ON COLUMN callback_channel_bindings.evidence_sha256 IS
  'The provider''s own startup output, stored. Where the name came from, so a hostname in this table is a measurement rather than a claim.';

-- The release is an UPDATE and everything else about the row is not, so the
-- guard is narrower than `reject_mutation_unless_purging` and says so. DELETE
-- goes to the same purge rule every program-scoped table follows.
CREATE FUNCTION enforce_callback_binding_release() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF coalesce(current_setting('app.purging', true), 'off') = 'on' THEN
            RETURN OLD;
        END IF;
        RAISE EXCEPTION 'callback_channel_bindings rows are immutable'
            USING ERRCODE = '23514';
    END IF;
    IF OLD.released_at IS NOT NULL THEN
        RAISE EXCEPTION 'this binding was already released at %', OLD.released_at
            USING ERRCODE = '23514';
    END IF;
    IF NEW.released_at IS NULL THEN
        RAISE EXCEPTION 'the only change a binding takes is being released'
            USING ERRCODE = '23514';
    END IF;
    -- Every other column restated, because "only released_at changed" is the
    -- whole of what this trigger permits and a column added later must be
    -- refused until somebody decides otherwise.
    IF (NEW.id, NEW.program_id, NEW.scope_version, NEW.channel_name, NEW.provider,
        NEW.endpoint_host, NEW.tunnel_pid, NEW.bound_at, NEW.evidence_sha256)
       IS DISTINCT FROM
       (OLD.id, OLD.program_id, OLD.scope_version, OLD.channel_name, OLD.provider,
        OLD.endpoint_host, OLD.tunnel_pid, OLD.bound_at, OLD.evidence_sha256) THEN
        RAISE EXCEPTION 'a binding may be released and not otherwise rewritten'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER callback_bindings_append_only
    BEFORE UPDATE OR DELETE ON callback_channel_bindings
    FOR EACH ROW EXECUTE FUNCTION enforce_callback_binding_release();
-- 021's lesson: `session_replication_role = replica` skips ORIGIN triggers, and
-- a restore is exactly when a binding would be rewritten.
ALTER TABLE callback_channel_bindings
    ENABLE ALWAYS TRIGGER callback_bindings_append_only;

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('callback_channel_bindings', 'program_id', 'program-scoped: the purge root');

-- This one emits, where its two neighbours do not. `program_callback_channels`
-- is compiled output and `callback_correlators` would be an oracle for when a
-- live canary exists; a binding is neither. It is the harness publishing a name
-- to the internet and later taking it down, which is the operational fact an
-- auditor reading the log most needs, and the endpoint carries no correlator.
INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('callback.bound', 'row', 'callback_channel_bindings',
     'an out-of-band channel was given a public endpoint by its provider'),
    ('callback.released', 'row', 'callback_channel_bindings',
     'an out-of-band endpoint was released, and every correlator minted against it died with it');

INSERT INTO event_table_config
    (table_name, created_type, updated_type, ignored_columns, redacted_columns) VALUES
    ('callback_channel_bindings', 'callback.bound', 'callback.released', '{}', '{}');

SELECT attach_event_triggers();


-- ---------------------------------------------------------------------------
-- 3. The correlator names the binding it was minted against
-- ---------------------------------------------------------------------------
-- Nullable in the schema and required by the writer and the trigger, because
-- "required" here means "required when this channel's provider is dynamic" and
-- a CHECK cannot reach the channel row to ask. Section 5 asks it in both
-- places, and section 8 asks it of every row that exists.

ALTER TABLE callback_correlators
    ADD COLUMN binding_id uuid,
    ADD CONSTRAINT callback_correlators_binding_fkey
        FOREIGN KEY (binding_id, program_id)
        REFERENCES callback_channel_bindings (id, program_id);

COMMENT ON COLUMN callback_correlators.binding_id IS
  'The endpoint this correlator was addressed at, for a channel whose name is bound rather than declared. Releasing that binding is what makes yesterday''s canary dead this morning without anything having to sweep it up.';


-- ---------------------------------------------------------------------------
-- 4. What an arrival carries, and which half of it is the correlator
-- ---------------------------------------------------------------------------
-- The request target as it arrived, undecoded. Undecoded because the segment is
-- compared against a digest: `%63orr` and `corr` are the same path to a decoder
-- and two different claims to this table, and the one that must not be
-- attributable is the one somebody had to encode to write.
--
-- Null for a channel whose correlator is a label -- a DNS query has no path,
-- and an HTTP arrival on a label channel carries its correlator in the name.

ALTER TABLE callback_interactions
    ADD COLUMN observed_path text
        CHECK (observed_path IS NULL OR left(observed_path, 1) = '/');

COMMENT ON COLUMN callback_interactions.observed_path IS
  'The request target exactly as it arrived, for a channel whose correlator is a path segment. Undecoded, because the segment is compared against a digest and a decoder would make two spellings one claim.';

-- It carries the correlator, so it is redacted for the reason `observed_host`
-- is: the event log is the most widely read surface in the installation.
UPDATE event_table_config
   SET redacted_columns = '{observed_host,observed_path}'
 WHERE table_name = 'callback_interactions';

-- The mirror of `callback_correlator_label`, with the same three answers: the
-- segment, NULL for a request that names none, and NULL for anything it must
-- not match. The shape gate is `mint_callback_correlator`'s own regex, so the
-- only thing this can return is something that could have been minted -- which
-- is what makes a percent-encoded segment, an empty one and a query string all
-- answer the same "no correlator here" rather than reaching the digest compare
-- with something clever in it.
CREATE FUNCTION callback_correlator_from_path(p_path text)
RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    -- The query is cut before the segment is read, the same cut the publisher
    -- and the accepter make: `/<correlator>?x=1` is a request for that canary,
    -- and a correlator read with the query still on it would match nothing that
    -- was ever minted.
    SELECT CASE
             WHEN p_path IS NULL OR left(p_path, 1) <> '/' THEN NULL
             WHEN split_part(split_part(p_path, '?', 1), '/', 2)
                  ~ '^[a-z0-9][a-z0-9-]{0,62}$'
                  THEN split_part(split_part(p_path, '?', 1), '/', 2)
             ELSE NULL
           END;
$fn$;

COMMENT ON FUNCTION callback_correlator_from_path(text) IS
  'The first path segment of a request, which is the correlator it claims, for a channel whose placement is `path`. The query is cut first. Null for a request naming none and for any segment that is not the shape a correlator is minted in. Mirrors callback_correlator_label.';

-- One question, asked where the placement is known. Both halves are pure
-- functions of the arrival and the endpoint, so the writer and the trigger can
-- ask it without agreeing about anything else.
CREATE FUNCTION callback_correlator_claimed(
    p_placement text, p_host text, p_path text, p_endpoint text
) RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT CASE
             WHEN NOT callback_host_admitted(p_host, p_endpoint) THEN NULL
             WHEN p_placement = 'path' THEN callback_correlator_from_path(p_path)
             ELSE callback_correlator_label(p_host, p_endpoint)
           END;
$fn$;

COMMENT ON FUNCTION callback_correlator_claimed(text, text, text, text) IS
  'The correlator an arrival claims, read from whichever place the channel''s placement names. Null when the endpoint does not admit the name at all, so a path segment cannot stand in for arriving somewhere we declared.';



-- ---------------------------------------------------------------------------
-- 5. The resolver, the writer and the invariant, all asking the binding
-- ---------------------------------------------------------------------------
-- The resolver answers two more things -- where this channel's correlator sits
-- and which binding this correlator was minted against -- which is a return
-- type, so it is dropped and recreated. Nothing else in the corpus selects from
-- it: `record_callback_interaction` is the one caller and it reads by name.
--
-- Dropping a function drops its grants. This one was granted to `rk2_runtime`
-- by 029's default privileges and recorded by 66's seed, so the grant is
-- re-asked below and `check_runtime_privileges()` at the end of this file is
-- what says the pair still agree.

DROP FUNCTION resolve_callback_correlator(text);

CREATE FUNCTION resolve_callback_correlator(p_correlator text)
RETURNS TABLE (
    correlator_id     uuid,
    program_id        uuid,
    channel_name      text,
    channel_kind      text,
    channel_host      text,
    channel_placement text,
    binding_id        uuid,
    subject_entity_id uuid,
    tool_run_id       uuid,
    test_run_id       uuid,
    expires_at        timestamptz
)
LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
    SELECT t.id, t.program_id, t.channel_name, c.kind,
           coalesce(c.host, b.endpoint_host), c.placement, t.binding_id,
           t.subject_entity_id, t.tool_run_id, t.test_run_id, t.expires_at
      FROM callback_correlators t
      JOIN programs p
        ON p.id = t.program_id AND p.closed_at IS NULL
      JOIN program_callback_channels c
        ON c.program_id = t.program_id
       AND c.version = p.scope_version
       AND c.name = t.channel_name
      -- The correlator's own binding, and only while it is live. This is the
      -- whole of "yesterday's canary is dead this morning": nothing swept it
      -- up, the name it was addressed at stopped existing and the join that
      -- would have returned it finds nothing.
      LEFT JOIN callback_channel_bindings b
        ON b.id = t.binding_id AND b.released_at IS NULL
     WHERE p_correlator IS NOT NULL
       AND t.program_id = rk2_program()
       AND t.correlator_sha256 = encode(digest(p_correlator, 'sha256'), 'hex')
       AND t.cleared_at IS NULL
       AND t.expires_at > clock_timestamp()
       AND (c.provider = 'static') = (t.binding_id IS NULL)
       AND (c.provider = 'static' OR b.id IS NOT NULL);
$fn$;

COMMENT ON FUNCTION resolve_callback_correlator(text) IS
  'Resolves a correlator only while its Program is open, its channel is still declared by the live scope version, the endpoint it was minted against is still bound, and the correlator is neither cleared nor expired. Bound to the session Program, so another Program''s correlator resolves to nothing.';

REVOKE ALL ON FUNCTION resolve_callback_correlator(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION resolve_callback_correlator(text) TO rk2_runtime;


-- The invariant. Every question it asked it still asks; what changes is that
-- the endpoint is read rather than declared, and the correlator is read from
-- wherever the placement says.
CREATE OR REPLACE FUNCTION enforce_callback_attribution() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    t          record;
    v_endpoint text;
BEGIN
    SELECT tk.program_id, tk.channel_name, tk.issued_at, tk.expires_at,
           tk.cleared_at, tk.correlator_sha256, tk.binding_id,
           c.kind, c.host, c.placement, c.provider
      INTO t
      FROM callback_correlators tk
      JOIN programs p
        ON p.id = tk.program_id AND p.closed_at IS NULL
      JOIN program_callback_channels c
        ON c.program_id = tk.program_id
       AND c.version = p.scope_version
       AND c.name = tk.channel_name
     WHERE tk.id = NEW.correlator_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'callback interaction names no live correlator on a declared channel'
            USING ERRCODE = '23514';
    END IF;
    IF t.program_id <> NEW.program_id THEN
        RAISE EXCEPTION 'callback correlator belongs to another Program'
            USING ERRCODE = '23514';
    END IF;
    -- Against the clock rather than against `NEW.received_at`. That column is
    -- the caller's -- it defaults to `now()` and nothing stops an INSERT stating
    -- another value -- so an expiry arm that read it would be an arm the row it
    -- guards could answer by backdating itself. `resolve_callback_correlator`
    -- reads `clock_timestamp()` for the same reason; this is the same rule where
    -- the writer is not involved.
    IF t.cleared_at IS NOT NULL OR t.expires_at <= now() THEN
        RAISE EXCEPTION 'callback correlator was not live when the interaction arrived'
            USING ERRCODE = '23514';
    END IF;
    -- And the window the row claims has to be one the correlator was listening
    -- in: before it was minted, after it expired, or in the future are all
    -- claims about a canary that was not there.
    IF NEW.received_at < t.issued_at
       OR NEW.received_at >= t.expires_at
       OR NEW.received_at > now() THEN
        RAISE EXCEPTION 'callback interaction claims to have arrived at %, outside its correlator''s lifetime',
            NEW.received_at USING ERRCODE = '23514';
    END IF;
    IF NEW.channel_name <> t.channel_name OR NEW.arrival_kind <> t.kind THEN
        RAISE EXCEPTION 'callback interaction claims channel % (%), correlator names % (%)',
            NEW.channel_name, NEW.arrival_kind, t.channel_name, t.kind
            USING ERRCODE = '23514';
    END IF;

    -- Where the channel is answering. For a declared host that is the
    -- declaration; for a bound one it is the correlator's own binding, still
    -- live, which is the arm that refuses an arrival at this morning's name
    -- claiming last night's canary.
    IF t.provider = 'static' THEN
        IF t.binding_id IS NOT NULL THEN
            RAISE EXCEPTION 'callback correlator names a binding on a channel that declares its own host'
                USING ERRCODE = '23514';
        END IF;
        v_endpoint := t.host;
    ELSE
        IF t.binding_id IS NULL THEN
            RAISE EXCEPTION 'callback correlator on channel % names no binding, and that channel''s endpoint is bound rather than declared',
                t.channel_name USING ERRCODE = '23514';
        END IF;
        SELECT b.endpoint_host INTO v_endpoint
          FROM callback_channel_bindings b
         WHERE b.id = t.binding_id AND b.program_id = t.program_id
           AND b.released_at IS NULL;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'callback correlator was minted against an endpoint that is no longer bound'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NOT callback_host_admitted(NEW.observed_host, v_endpoint) THEN
        RAISE EXCEPTION 'callback interaction arrived at %, which channel % does not admit',
            NEW.observed_host, t.channel_name
            USING ERRCODE = '23514';
    END IF;
    -- A path channel is addressed by path, so an arrival that recorded none
    -- carries no correlator at all -- and one on a label channel that recorded
    -- a path is a row whose extra column nothing would ever read.
    IF (t.placement = 'path') <> (NEW.observed_path IS NOT NULL) THEN
        RAISE EXCEPTION 'callback interaction on channel % carries % path, and its correlator sits in the %',
            t.channel_name,
            CASE WHEN NEW.observed_path IS NULL THEN 'no' ELSE 'a' END,
            t.placement USING ERRCODE = '23514';
    END IF;
    -- The arm that decides whose canary fired. Every live correlator of this
    -- Program is admitted by the same channel, so the arm above says only that
    -- some canary was queried; without this one an arrival at subject B's name
    -- could be filed under subject A's correlator, and the Observation would be
    -- a true fact about the wrong entity. The digest is all this table holds,
    -- and comparing it to what the arrival carries is exactly what it is for.
    IF encode(digest(callback_correlator_claimed(t.placement, NEW.observed_host,
                                                 NEW.observed_path, v_endpoint),
                     'sha256'), 'hex')
       IS DISTINCT FROM t.correlator_sha256 THEN
        RAISE EXCEPTION 'callback interaction arrived at %, which does not carry the correlator it claims',
            coalesce(NEW.observed_path, NEW.observed_host) USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;


-- Minting, which now records the endpoint the canary is addressed at. A dynamic
-- channel with nothing bound mints nothing: a correlator whose address is
-- unknown is a canary embedded in a payload that nobody can be reached at.
CREATE OR REPLACE FUNCTION mint_callback_correlator(
    p_channel    text,
    p_correlator text,
    p_subject    uuid,
    p_lifetime   interval,
    p_tool_run   uuid DEFAULT NULL,
    p_test_run   uuid DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_program  uuid := rk2_program();
    v_version  integer;
    v_provider text;
    v_binding  uuid;
    v_id       uuid;
BEGIN
    IF v_program IS NULL OR p_correlator IS NULL OR p_channel IS NULL
       OR p_subject IS NULL OR p_lifetime IS NULL OR p_lifetime <= interval '0' THEN
        RAISE EXCEPTION 'callback correlator refused' USING ERRCODE = '23514';
    END IF;
    -- One DNS label, lower case, because that is the only shape a correlator can
    -- arrive in: an observed name is stored lowercased, and the admission
    -- trigger compares the digest of the label it carries. A correlator that
    -- could never match the name it travels in is one whose arrivals would all
    -- be refused, which is a canary that quietly does not work. The same shape
    -- serves a path segment, which `callback_correlator_from_path` gates on.
    IF p_correlator !~ '^[a-z0-9][a-z0-9-]{0,62}$' THEN
        RAISE EXCEPTION 'a correlator is one lower-case DNS label'
            USING ERRCODE = '23514';
    END IF;
    -- The live version, not any version: a channel withdrawn by the operator's
    -- last revision is a channel no new correlator may be minted for.
    SELECT p.scope_version INTO v_version
      FROM programs p WHERE p.id = v_program AND p.closed_at IS NULL;
    IF FOUND THEN
        SELECT c.provider INTO v_provider
          FROM program_callback_channels c
         WHERE c.program_id = v_program AND c.version = v_version
           AND c.name = p_channel;
    END IF;
    IF v_provider IS NULL THEN
        RAISE EXCEPTION 'channel % is not declared by the live scope policy', p_channel
            USING ERRCODE = '23514';
    END IF;
    IF v_provider <> 'static' THEN
        SELECT b.id INTO v_binding
          FROM callback_channel_bindings b
         WHERE b.program_id = v_program AND b.channel_name = p_channel
           AND b.released_at IS NULL;
        IF v_binding IS NULL THEN
            RAISE EXCEPTION 'channel % has no live binding, so there is no name to embed', p_channel
                USING ERRCODE = '23514';
        END IF;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM entities e
                    WHERE e.id = p_subject AND e.program_id = v_program) THEN
        RAISE EXCEPTION 'the subject of a correlator must be an entity of this Program'
            USING ERRCODE = '23514';
    END IF;

    PERFORM set_actor('runtime');
    INSERT INTO callback_correlators
        (program_id, scope_version, channel_name, correlator_sha256, subject_entity_id,
         tool_run_id, test_run_id, expires_at, binding_id)
    VALUES (v_program, v_version, p_channel,
            encode(digest(p_correlator, 'sha256'), 'hex'), p_subject,
            p_tool_run, p_test_run, clock_timestamp() + p_lifetime, v_binding)
    RETURNING id INTO v_id;
    RETURN v_id;
END $fn$;

COMMENT ON FUNCTION mint_callback_correlator(text, text, uuid, interval, uuid, uuid) IS
  'Records a correlator for a channel the live scope policy declares, storing its digest and never its plaintext, against the endpoint that channel is answering on. Refuses an undeclared channel, a foreign subject, an unbounded lifetime and a dynamic channel with no live binding.';


-- The writer. Everything 67 built is untouched -- the stated moment, the
-- arrival key, the duplicate answer -- and what is added is the path: taken as
-- it arrived, required exactly when the channel's correlator lives in it, and
-- compared through the same function the trigger compares through.
CREATE OR REPLACE FUNCTION record_callback_interaction(
    p_correlator    text,
    p_arrival  jsonb,
    p_artifact jsonb
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    t             record;
    v_host        text;
    v_path        text;
    v_kind        text;
    v_peer        text;
    v_stated      text;
    v_received    timestamptz;
    v_sha         text;
    v_size        bigint;
    v_type        text;
    v_interaction uuid;
    v_label       text;
    v_reference   text;
    v_observation uuid;
    v_obs_label   text;
    v_duplicate   boolean;
    v_problem     text;
BEGIN
    IF p_correlator IS NULL
       OR coalesce(jsonb_typeof(p_arrival), 'null') <> 'object'
       OR coalesce(jsonb_typeof(p_artifact), 'null') <> 'object' THEN
        RAISE EXCEPTION 'callback interaction refused' USING ERRCODE = '23514';
    END IF;

    SELECT * INTO t FROM resolve_callback_correlator(p_correlator) r;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'callback correlator refused' USING ERRCODE = '23514';
    END IF;

    v_host   := lower(nullif(p_arrival ->> 'host', ''));
    -- Not lowercased and not decoded: a path is case-sensitive and the segment
    -- is compared against a digest.
    v_path   := nullif(p_arrival ->> 'path', '');
    v_kind   := nullif(p_arrival ->> 'arrival_kind', '');
    v_peer   := coalesce(nullif(p_arrival ->> 'peer_class', ''), 'unknown');
    v_stated := nullif(p_arrival ->> 'received_at', '');
    v_sha    := nullif(p_artifact ->> 'sha256', '');
    v_type   := nullif(p_artifact ->> 'content_type', '');
    v_size   := (p_artifact ->> 'byte_size')::bigint;

    IF v_host IS NULL OR v_kind IS NULL OR v_sha IS NULL OR v_size IS NULL THEN
        RAISE EXCEPTION 'a callback interaction states a host, a kind and the bytes it received'
            USING ERRCODE = '23514';
    END IF;
    IF v_sha !~ '^[0-9a-f]{64}$' OR v_size < 0 THEN
        RAISE EXCEPTION 'callback interaction names bytes with no hash or no byte count'
            USING ERRCODE = '23514';
    END IF;
    IF (t.channel_placement = 'path') <> (v_path IS NOT NULL) THEN
        RAISE EXCEPTION 'channel % carries its correlator in the %, and this arrival states % path',
            t.channel_name, t.channel_placement,
            CASE WHEN v_path IS NULL THEN 'no' ELSE 'a' END
            USING ERRCODE = '23514';
    END IF;
    -- The listener's moment when there is one, and the acceptance moment when
    -- there is not. A caller with no timestamp is not refused: an operator
    -- holding a recording whose format carries no clock still has an arrival,
    -- and filing it under the acceptance moment is what this function did for
    -- every row that exists. What it costs them is the deduplication -- two
    -- accepts of that recording are two moments and therefore two arrivals.
    --
    -- `now()` and not `clock_timestamp()`, which is what the column's DEFAULT
    -- was and what `enforce_callback_attribution` requires: that trigger refuses
    -- a row whose moment is after `now()`, the moment this transaction began,
    -- and `clock_timestamp()` is by definition after it. MEASURED: stating it
    -- here answers `callback interaction claims to have arrived at ..., outside
    -- its correlator's lifetime` for an arrival that is being accepted right now.
    IF v_stated IS NULL THEN
        v_received := now();
    ELSE
        BEGIN
            v_received := v_stated::timestamptz;
        EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN
            RAISE EXCEPTION 'callback interaction states a received_at that is not a moment: %',
                v_stated USING ERRCODE = '23514';
        END;
    END IF;
    -- The name, the path and the correlator arrive as separate arguments, and
    -- nothing but this makes them one claim: resolving a live correlator says a
    -- canary of this Program fired, and the arrival says which. Asked here as
    -- well as in the trigger, so the convenience and the guarantee refuse the
    -- same rows.
    IF callback_correlator_claimed(t.channel_placement, v_host, v_path, t.channel_host)
       IS DISTINCT FROM p_correlator THEN
        RAISE EXCEPTION 'callback interaction arrived at %, which does not carry the correlator it claims',
            coalesce(v_path, v_host) USING ERRCODE = '23514';
    END IF;

    PERFORM set_actor('runtime');
    INSERT INTO artifacts (sha256, byte_size, content_type, visibility, encrypted)
    VALUES (v_sha, v_size, v_type, 'agent_visible', false)
    ON CONFLICT (sha256) DO NOTHING;

    -- The same disagreement check `record_proxy_exchange` makes, for the same
    -- reason: the store is one namespace keyed by the hash of the plaintext, so
    -- these bytes may already be registered by another Program's identical
    -- ones. What must not pass is a hash registered with a different length or
    -- under a visibility this Observation may not cite.
    SELECT CASE
             WHEN a.sha256 IS NULL THEN 'not registered'
             WHEN a.byte_size <> v_size THEN 'registered as ' || a.byte_size || ' byte(s)'
             WHEN a.visibility <> 'agent_visible' OR a.encrypted
                  THEN 'registered as ' || a.visibility
             WHEN a.purged_at IS NOT NULL THEN 'purged'
           END
      INTO v_problem
      FROM (SELECT 1) one
      LEFT JOIN artifacts a ON a.sha256 = v_sha;
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION 'callback interaction names bytes it did not store: % (%)',
            v_sha, v_problem USING ERRCODE = '23514';
    END IF;

    INSERT INTO artifact_references (program_id, sha256, kind)
    VALUES (t.program_id, v_sha, 'runtime')
    ON CONFLICT (program_id, sha256, kind) DO NOTHING;
    SELECT ar.label INTO v_reference
      FROM artifact_references ar
     WHERE ar.program_id = t.program_id AND ar.sha256 = v_sha AND ar.kind = 'runtime';

    INSERT INTO callback_interactions
        (program_id, correlator_id, channel_name, arrival_kind, observed_host,
         observed_path, peer_class, received_at, body_sha256, byte_size)
    VALUES (t.program_id, t.correlator_id, t.channel_name, v_kind, v_host,
            v_path, v_peer, v_received, v_sha, v_size)
    ON CONFLICT ON CONSTRAINT callback_interactions_arrival_key DO NOTHING
    RETURNING id, label INTO v_interaction, v_label;

    v_duplicate := v_interaction IS NULL;

    IF v_duplicate THEN
        -- The arrival is already recorded. Answering with the rows it resolved
        -- to rather than raising is what makes `rk callback accept` safe to
        -- re-run: the operator asked for this arrival to be on the record, and
        -- it is. `duplicate` is how they tell that from having recorded a
        -- second one.
        --
        -- These six columns are the constraint's, restated because DO NOTHING
        -- yields no row and DO UPDATE would touch one the immutability trigger
        -- refuses. Whoever edits `callback_interactions_arrival_key` edits this
        -- WHERE with it: they are one identity written twice, and only the
        -- constraint is enforced. `observed_path` is deliberately not among
        -- them -- it travels in the bytes of the request that produced it, so
        -- two arrivals differing only in path already differ in `body_sha256`.
        SELECT ci.id, ci.label INTO v_interaction, v_label
          FROM callback_interactions ci
         WHERE ci.program_id    = t.program_id
           AND ci.correlator_id = t.correlator_id
           AND ci.arrival_kind  = v_kind
           AND ci.observed_host = v_host
           AND ci.body_sha256   = v_sha
           AND ci.received_at   = v_received;

        -- The row this insert lost to can be one this transaction cannot see:
        -- under a snapshot older than the transaction that wrote it -- anything
        -- above READ COMMITTED -- the conflict is real and the row is invisible,
        -- and the SELECT above finds nothing. That is a lost race rather than a
        -- broken record, and the answer is to accept the file again, so it is
        -- reported under the class a caller retries rather than as a record that
        -- contradicts itself.
        IF v_interaction IS NULL THEN
            RAISE EXCEPTION 'this arrival is being recorded by another transaction that has not committed'
                USING ERRCODE = '40001';
        END IF;

        BEGIN
            SELECT o.id, o.label INTO STRICT v_observation, v_obs_label
              FROM observations o
             WHERE o.program_id = t.program_id
               AND o.callback_interaction_id = v_interaction;
        EXCEPTION
            WHEN no_data_found THEN
                RAISE EXCEPTION 'the arrival % is recorded with no Observation to cite', v_label
                    USING ERRCODE = '23514';
            WHEN too_many_rows THEN
                RAISE EXCEPTION 'the arrival % is cited by more than one Observation', v_label
                    USING ERRCODE = '23514';
        END;
    ELSE
        -- The summary names the channel and the bytes and neither the host nor
        -- the path. Both carry the correlator, and this string is the one part
        -- of the record an agent reads.
        INSERT INTO observations
            (program_id, subject_entity_id, kind, summary, provenance_kind,
             callback_interaction_id, observed_at, metadata)
        VALUES (t.program_id, t.subject_entity_id, 'callback_interaction',
                'an out-of-band ' || v_kind || ' interaction arrived on channel '
                  || t.channel_name || ' carrying this subject''s correlator, '
                  || v_size || ' byte(s) stored as ' || coalesce(v_reference, v_sha),
                'callback', v_interaction, v_received,
                jsonb_build_object('interaction', v_label,
                                   'channel', t.channel_name,
                                   'arrival_kind', v_kind,
                                   'byte_size', v_size))
        RETURNING id, label INTO v_observation, v_obs_label;
    END IF;

    -- One answer for both paths, because they are the same answer: these are
    -- the rows this arrival resolves to. `duplicate` says whether this call is
    -- what put them there.
    RETURN jsonb_build_object(
        'interaction_id', v_interaction, 'interaction', v_label,
        'observation_id', v_observation, 'observation', v_obs_label,
        'artifact', v_reference, 'sha256', v_sha,
        'channel', t.channel_name, 'correlator_id', t.correlator_id,
        'received_at', v_received, 'duplicate', v_duplicate);
END $fn$;


-- ---------------------------------------------------------------------------
-- 6. Binding a name, releasing it, and asking which one is live
-- ---------------------------------------------------------------------------
-- Functions rather than INSERTs for the reason minting is one: the caller must
-- not be able to state a binding this Program did not make, and the table takes
-- no UPDATE from any role, so releasing has to be a verb.

CREATE FUNCTION bind_callback_channel(
    p_channel  text,
    p_provider text,
    p_endpoint text,
    p_pid      integer,
    p_evidence jsonb
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_program  uuid := rk2_program();
    v_version  integer;
    v_declared text;
    v_sha      text;
    v_size     bigint;
    v_type     text;
    v_problem  text;
    v_id       uuid;
    v_at       timestamptz;
BEGIN
    IF v_program IS NULL OR p_channel IS NULL OR p_provider IS NULL
       OR p_endpoint IS NULL
       OR coalesce(jsonb_typeof(p_evidence), 'null') <> 'object' THEN
        RAISE EXCEPTION 'callback binding refused' USING ERRCODE = '23514';
    END IF;

    SELECT p.scope_version INTO v_version
      FROM programs p WHERE p.id = v_program AND p.closed_at IS NULL;
    IF FOUND THEN
        SELECT c.provider INTO v_declared
          FROM program_callback_channels c
         WHERE c.program_id = v_program AND c.version = v_version
           AND c.name = p_channel;
    END IF;
    IF v_declared IS NULL THEN
        RAISE EXCEPTION 'channel % is not declared by the live scope policy', p_channel
            USING ERRCODE = '23514';
    END IF;
    -- The provider is the caller's claim about what handed it this name, and
    -- the declaration is the operator's about what may. A disagreement is a
    -- binding made by something the configuration did not ask for.
    IF v_declared <> p_provider THEN
        RAISE EXCEPTION 'channel % declares provider %, and this binding was made by %',
            p_channel, v_declared, p_provider USING ERRCODE = '23514';
    END IF;

    v_sha  := nullif(p_evidence ->> 'sha256', '');
    v_type := nullif(p_evidence ->> 'content_type', '');
    v_size := (p_evidence ->> 'byte_size')::bigint;
    IF v_sha IS NULL OR v_size IS NULL OR v_sha !~ '^[0-9a-f]{64}$' OR v_size < 0 THEN
        RAISE EXCEPTION 'a binding states the provider output it read the name out of'
            USING ERRCODE = '23514';
    END IF;

    PERFORM set_actor('runtime');
    INSERT INTO artifacts (sha256, byte_size, content_type, visibility, encrypted)
    VALUES (v_sha, v_size, v_type, 'agent_visible', false)
    ON CONFLICT (sha256) DO NOTHING;

    SELECT CASE
             WHEN a.sha256 IS NULL THEN 'not registered'
             WHEN a.byte_size <> v_size THEN 'registered as ' || a.byte_size || ' byte(s)'
             WHEN a.visibility <> 'agent_visible' OR a.encrypted
                  THEN 'registered as ' || a.visibility
             WHEN a.purged_at IS NOT NULL THEN 'purged'
           END
      INTO v_problem
      FROM (SELECT 1) one
      LEFT JOIN artifacts a ON a.sha256 = v_sha;
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION 'a binding names output it did not store: % (%)', v_sha, v_problem
            USING ERRCODE = '23514';
    END IF;

    INSERT INTO artifact_references (program_id, sha256, kind)
    VALUES (v_program, v_sha, 'runtime')
    ON CONFLICT (program_id, sha256, kind) DO NOTHING;

    -- The partial unique index is what refuses a second live binding, and it
    -- is caught rather than pre-checked: two starts racing is exactly the case
    -- a read followed by a write would let through.
    BEGIN
        INSERT INTO callback_channel_bindings
            (program_id, scope_version, channel_name, provider, endpoint_host,
             tunnel_pid, evidence_sha256)
        VALUES (v_program, v_version, p_channel, p_provider, lower(p_endpoint),
                p_pid, v_sha)
        RETURNING id, bound_at INTO v_id, v_at;
    EXCEPTION WHEN unique_violation THEN
        RAISE EXCEPTION 'channel % already has a live binding; release it before binding another',
            p_channel USING ERRCODE = '23505';
    END;

    RETURN jsonb_build_object(
        'binding_id', v_id, 'channel', p_channel, 'provider', p_provider,
        'endpoint', lower(p_endpoint), 'bound_at', v_at, 'tunnel_pid', p_pid);
END $fn$;

COMMENT ON FUNCTION bind_callback_channel(text, text, text, integer, jsonb) IS
  'Records the endpoint a dynamic channel is answering on, with the provider output it was read from. Refuses an undeclared channel, a provider the declaration did not name, and a channel that already has a live binding.';


CREATE FUNCTION release_callback_binding(p_binding uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_channel     text;
    v_endpoint    text;
    v_correlators bigint;
    v_released    boolean;
BEGIN
    PERFORM set_actor('runtime');

    -- One statement, so the count and the release read one snapshot: a
    -- correlator minted between two statements would be one this answer says
    -- nothing about and the release has already killed. `scoped` is the
    -- predicate, written once and used by both halves; a binding of another
    -- Program matches nothing there, so every value stays NULL -- which is what
    -- an id nobody minted leaves too.
    WITH scoped AS (
        SELECT b.id, b.channel_name, b.endpoint_host
          FROM callback_channel_bindings b
         WHERE b.id = p_binding
           AND b.program_id = rk2_program()
    ), ended AS (
        UPDATE callback_channel_bindings b
           SET released_at = clock_timestamp()
          FROM scoped s
         WHERE b.id = s.id
           AND b.released_at IS NULL
        RETURNING b.id
    )
    SELECT s.channel_name, s.endpoint_host,
           EXISTS (SELECT 1 FROM ended),
           (SELECT count(*) FROM callback_correlators t
             WHERE t.binding_id = s.id
               AND t.cleared_at IS NULL
               AND t.expires_at > clock_timestamp())
      INTO v_channel, v_endpoint, v_released, v_correlators
      FROM scoped s;

    -- `released` is what this call did; `known` is what it found. The count is
    -- correlators that were still live and are now unreachable -- the ones an
    -- operator would otherwise go looking for.
    RETURN jsonb_build_object(
        'released', coalesce(v_released, false),
        'known', v_channel IS NOT NULL,
        'channel', v_channel,
        'endpoint', v_endpoint,
        'correlators', coalesce(v_correlators, 0));
END $fn$;

COMMENT ON FUNCTION release_callback_binding(uuid) IS
  'Ends one binding and says what it ended: whether this call released it, whether this Program has it at all, the channel and endpoint it named, and how many live correlators died with it. Idempotent, and a binding of another Program is answered as one that never existed.';


CREATE FUNCTION callback_channel_binding(p_channel text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_program uuid := rk2_program();
    v_version integer;
    c         record;
    b         record;
BEGIN
    SELECT p.scope_version INTO v_version
      FROM programs p WHERE p.id = v_program AND p.closed_at IS NULL;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('declared', false, 'bound', false);
    END IF;
    SELECT ch.kind, ch.host, ch.placement, ch.provider INTO c
      FROM program_callback_channels ch
     WHERE ch.program_id = v_program AND ch.version = v_version
       AND ch.name = p_channel;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('declared', false, 'bound', false);
    END IF;

    -- A static channel is answered in the same shape, with its declaration as
    -- the endpoint and no binding. One caller, one answer: `rk oob status` and
    -- `rk callback provision` both need "where is this channel answering", and
    -- a second function for the declared case would be two places for that
    -- question to be answered differently.
    IF c.provider = 'static' THEN
        RETURN jsonb_build_object(
            'declared', true, 'bound', true, 'channel', p_channel,
            'kind', c.kind, 'placement', c.placement, 'provider', c.provider,
            'endpoint', c.host, 'binding_id', NULL, 'correlators', 0);
    END IF;

    SELECT bb.id, bb.endpoint_host, bb.bound_at, bb.tunnel_pid, bb.evidence_sha256 INTO b
      FROM callback_channel_bindings bb
     WHERE bb.program_id = v_program AND bb.channel_name = p_channel
       AND bb.released_at IS NULL;
    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'declared', true, 'bound', false, 'channel', p_channel,
            'kind', c.kind, 'placement', c.placement, 'provider', c.provider);
    END IF;

    RETURN jsonb_build_object(
        'declared', true, 'bound', true, 'channel', p_channel,
        'kind', c.kind, 'placement', c.placement, 'provider', c.provider,
        'endpoint', b.endpoint_host, 'binding_id', b.id, 'bound_at', b.bound_at,
        'tunnel_pid', b.tunnel_pid, 'evidence_sha256', b.evidence_sha256,
        'correlators', (SELECT count(*) FROM callback_correlators t
                         WHERE t.binding_id = b.id
                           AND t.cleared_at IS NULL
                           AND t.expires_at > clock_timestamp()));
END $fn$;

COMMENT ON FUNCTION callback_channel_binding(text) IS
  'Where one channel of this Program is answering right now, and how many live correlators hang off it. The only supported way to learn a bound name: it is not in the configuration, and an unbound dynamic channel answers bound false rather than a stale one.';


-- ---------------------------------------------------------------------------
-- 7. What the runtime holds
-- ---------------------------------------------------------------------------
-- Since 66 a function born in this schema is open to PUBLIC and a table is not
-- granted to anybody, so the three verbs have to be closed and then declared,
-- and the table has to be named on the surface to be readable at all. The
-- registries are the grant: `apply_runtime_grants()` below is what performs it.

REVOKE ALL ON FUNCTION bind_callback_channel(text, text, text, integer, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION release_callback_binding(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION callback_channel_binding(text) FROM PUBLIC;

-- `apply_runtime_grants()` performs the table half of the surface and only that
-- half, so a verb is granted by hand and the registry row is what holds it
-- there: without the row `check_runtime_privileges` arm 1 fails the grant, and
-- without the grant arm 5 fails the row.
GRANT EXECUTE ON FUNCTION bind_callback_channel(text, text, text, integer, jsonb) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION release_callback_binding(uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION callback_channel_binding(text) TO rk2_runtime;

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('bind_callback_channel(text, text, text, integer, jsonb)', '69',
     'records the endpoint a dynamic channel is answering on, against the provider output it was read from'),
    ('release_callback_binding(uuid)', '69',
     'ends one binding, which is what makes every correlator minted against it dead'),
    ('callback_channel_binding(text)', '69',
     'where one channel of this Program is answering now; the only supported way to learn a bound name');

-- SELECT and nothing else. The rows are written by the definer above, which is
-- what checks that the channel is declared, that the provider is the declared
-- one and that nothing else is already live -- three checks a direct INSERT
-- would be a way around.
INSERT INTO runtime_table_surface (table_name, privilege, added_by) VALUES
    ('callback_channel_bindings', 'SELECT', '69');

REVOKE ALL ON TABLE callback_channel_bindings FROM rk2_proxy, rk2_state, rk2_human;

SELECT apply_state_rls();
SELECT apply_runtime_grants();


-- ---------------------------------------------------------------------------
-- 8. The standing check, asking the binding where it used to ask the column
-- ---------------------------------------------------------------------------
-- Two of ticket 14's arms read `program_callback_channels.host` as the name a
-- channel answers at. For a bound channel that column is NULL, so left alone
-- both arms would fail every arrival on a quick tunnel. They now read the
-- endpoint from wherever that channel's name came from, and three arms are
-- added for the ways a binding can be wrong.

CREATE OR REPLACE FUNCTION check_callback_admission()
RETURNS TABLE(problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- Every name any channel of any Program has ever answered at: the declared
    -- host of a static channel, and the endpoint of each binding a dynamic one
    -- has had. Released bindings included, because an arrival was admitted at
    -- the name that was live when it arrived, and a check nobody can clear
    -- stops being a signal.
    WITH channel_endpoints AS (
        SELECT c.program_id, c.name, c.kind, c.placement, c.host AS endpoint
          FROM program_callback_channels c
         WHERE c.provider = 'static'
        UNION ALL
        SELECT b.program_id, b.channel_name, c.kind, c.placement, b.endpoint_host
          FROM callback_channel_bindings b
          JOIN program_callback_channels c
            ON c.program_id = b.program_id AND c.version = b.scope_version
           AND c.name = b.channel_name
    )
    -- (a) The verbs are the runtime's alone.
    SELECT 'callback_verbs_misplaced',
           p.grantee || ' can execute ' || p.verb
      FROM (
        SELECT g.grantee, f.verb
          FROM (VALUES ('record_callback_interaction(text,jsonb,jsonb)'),
                       ('mint_callback_correlator(text,text,uuid,interval,uuid,uuid)'),
                       ('clear_callback_correlator(uuid)'),
                       ('resolve_callback_correlator(text)'),
                       ('bind_callback_channel(text,text,text,integer,jsonb)'),
                       ('release_callback_binding(uuid)'),
                       ('callback_channel_binding(text)')) AS f(verb),
               (VALUES ('rk2_state'), ('rk2_proxy'), ('rk2_human')) AS g(grantee)
         WHERE has_function_privilege(g.grantee, f.verb, 'EXECUTE')
      ) p
    UNION ALL
    SELECT 'callback_writer_unreachable',
           'rk2_runtime cannot execute record_callback_interaction'
     WHERE NOT has_function_privilege(
               'rk2_runtime', 'record_callback_interaction(text,jsonb,jsonb)', 'EXECUTE')
    UNION ALL
    -- (b) A correlator nobody may rewrite, and an arrival nobody may unmake.
    SELECT 'callback_tables_writable',
           p.grantee || ' holds ' || p.privilege_type || ' on ' || p.table_name
      FROM (
        SELECT g.grantee, t.table_name, g.privilege_type
          FROM (VALUES ('callback_correlators'), ('callback_interactions')) AS t(table_name),
               (VALUES ('rk2_runtime', 'UPDATE'), ('rk2_runtime', 'DELETE'),
                       ('rk2_proxy', 'INSERT'), ('rk2_proxy', 'UPDATE'),
                       ('rk2_proxy', 'DELETE'), ('rk2_proxy', 'SELECT'),
                       ('rk2_state', 'INSERT'), ('rk2_state', 'UPDATE'),
                       ('rk2_state', 'DELETE'), ('rk2_state', 'SELECT'),
                       ('rk2_human', 'UPDATE'), ('rk2_human', 'DELETE'))
                 AS g(grantee, privilege_type)
         WHERE has_table_privilege(g.grantee, t.table_name, g.privilege_type)
      ) p
    UNION ALL
    -- A binding is stated by the verb or not at all, so the runtime reads this
    -- one and writes none of it: the checks the definer makes -- declared
    -- channel, declared provider, nothing already live -- are exactly what a
    -- direct INSERT would be a way around.
    SELECT 'callback_bindings_writable',
           g.grantee || ' holds ' || g.privilege_type || ' on callback_channel_bindings'
      FROM (VALUES ('rk2_runtime', 'INSERT'), ('rk2_runtime', 'UPDATE'),
                   ('rk2_runtime', 'DELETE'), ('rk2_proxy', 'SELECT'),
                   ('rk2_state', 'SELECT'), ('rk2_human', 'INSERT'),
                   ('rk2_human', 'UPDATE'), ('rk2_human', 'DELETE'))
             AS g(grantee, privilege_type)
     WHERE has_table_privilege(g.grantee, 'callback_channel_bindings', g.privilege_type)
    UNION ALL
    -- (c) The correlator, the name it arrived at, and the endpoint it was
    --     minted against are not on the agent read surface, and a row added
    --     there is what would put them on it.
    SELECT 'callback_on_agent_surface', s.table_name || '.' || s.column_name
      FROM state_read_surface s
     WHERE s.table_name IN ('callback_correlators', 'callback_interactions',
                            'callback_channel_bindings')
    UNION ALL
    -- (d) The invariants, still ALWAYS. `tgenabled` is 'A' for ENABLE ALWAYS
    --     and 'O' for an ordinary trigger a restore would skip.
    SELECT 'callback_guard_not_always', tg.tgname
      FROM pg_trigger tg
     WHERE tg.tgname IN ('callback_interactions_attribution',
                         'callback_interactions_immutable',
                         'observations_callback_program_guard',
                         'callback_channels_immutable',
                         'callback_bindings_append_only')
       AND tg.tgenabled <> 'A'
    UNION ALL
    SELECT 'callback_guard_missing', want.tgname
      FROM (VALUES ('callback_interactions_attribution'),
                   ('callback_interactions_immutable'),
                   ('observations_callback_program_guard'),
                   ('callback_channels_immutable'),
                   ('callback_bindings_append_only')) AS want(tgname)
     WHERE NOT EXISTS (SELECT 1 FROM pg_trigger tg WHERE tg.tgname = want.tgname)
    UNION ALL
    -- (e) And the rows themselves: an arrival whose correlator belongs to
    --     another Program, or that came in at a name no channel of its Program
    --     has ever answered at.
    SELECT 'callback_interaction_unattributed', ci.label
      FROM callback_interactions ci
      LEFT JOIN callback_correlators t
        ON t.id = ci.correlator_id AND t.program_id = ci.program_id
     WHERE t.id IS NULL
    UNION ALL
    SELECT 'callback_interaction_undeclared_host', ci.label
      FROM callback_interactions ci
     WHERE NOT EXISTS (
        SELECT 1 FROM channel_endpoints e
         WHERE e.program_id = ci.program_id
           AND e.name = ci.channel_name
           AND e.kind = ci.arrival_kind
           AND callback_host_admitted(ci.observed_host, e.endpoint))
    UNION ALL
    -- and an arrival filed under a correlator the name it came in at does not
    -- carry. The two above ask whether some canary of this Program fired; this
    -- asks which, against the version the correlator was minted under and the
    -- endpoint it was minted against, because that pair is the declaration it
    -- was addressed beneath. A claim that cannot be read at all is null, and
    -- null is distinct from every digest, so an unreadable arrival is caught
    -- here rather than passing for want of a comparison.
    SELECT 'callback_interaction_mislabelled', ci.label
      FROM callback_interactions ci
      JOIN callback_correlators t
        ON t.id = ci.correlator_id AND t.program_id = ci.program_id
      JOIN program_callback_channels c
        ON c.program_id = t.program_id AND c.version = t.scope_version
       AND c.name = t.channel_name
      LEFT JOIN callback_channel_bindings b ON b.id = t.binding_id
     WHERE encode(digest(callback_correlator_claimed(
                             c.placement, ci.observed_host, ci.observed_path,
                             coalesce(c.host, b.endpoint_host)),
                         'sha256'), 'hex')
           IS DISTINCT FROM t.correlator_sha256
    UNION ALL
    -- An arrival that carries a path on a channel that puts its correlator in
    -- the label, or one that carries none on a channel that puts it in the
    -- path. The digest above would pass the first of those, because a label
    -- placement never looks at the path.
    SELECT 'callback_interaction_path_disagrees', ci.label
      FROM callback_interactions ci
      JOIN callback_correlators t
        ON t.id = ci.correlator_id AND t.program_id = ci.program_id
      JOIN program_callback_channels c
        ON c.program_id = t.program_id AND c.version = t.scope_version
       AND c.name = t.channel_name
     WHERE (c.placement = 'path') <> (ci.observed_path IS NOT NULL)
    UNION ALL
    -- (f) And the binding itself. A correlator carries one exactly when its
    --     channel has a provider to bind: minted without one it names an
    --     endpoint nobody can say, and minted with one on a declared host it
    --     claims a name the operator did not write down.
    SELECT 'callback_correlator_binding_disagrees',
           t.id::text || ' on ' || t.channel_name
      FROM callback_correlators t
      JOIN program_callback_channels c
        ON c.program_id = t.program_id AND c.version = t.scope_version
       AND c.name = t.channel_name
     WHERE (c.provider = 'static') = (t.binding_id IS NOT NULL)
    UNION ALL
    SELECT 'callback_binding_on_static_channel',
           b.channel_name || ' at ' || b.endpoint_host
      FROM callback_channel_bindings b
      JOIN program_callback_channels c
        ON c.program_id = b.program_id AND c.version = b.scope_version
       AND c.name = b.channel_name
     WHERE c.provider = 'static'
    UNION ALL
    SELECT 'callback_observation_foreign', o.label
      FROM observations o
      JOIN callback_interactions ci ON ci.id = o.callback_interaction_id
     WHERE o.provenance_kind = 'callback' AND ci.program_id <> o.program_id;
$fn$;

COMMENT ON FUNCTION check_callback_admission() IS
  'Callback admission, asserted from both ends: who may accept an interaction or bind a name, a correlator and a binding nobody may rewrite, neither on the agent surface, and every stored arrival still resolving a correlator of its own Program at a name that Program was answering at, in the place its channel puts it.';

UPDATE standing_checks
   SET note = 'accepting an out-of-band interaction is the runtime''s verb alone and so is binding the name one arrives at, a correlator and a binding are nobody''s to rewrite, none of the three is on the agent surface, and every stored arrival still resolves a correlator of its own Program at a name that Program was answering at, in the place its channel declares'
 WHERE name = 'callback_admission';


-- ---------------------------------------------------------------------------
-- 9. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_callback_admission();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-69 refuses to finish: % callback problem(s): %', n, d;
    END IF;

    -- `resolve_callback_correlator` was dropped and recreated, and a DROP takes
    -- the grant with it. Arm 5 -- a declared verb the runtime cannot execute --
    -- is what a forgotten GRANT comes back as, and arm 1 is what the three new
    -- rows would come back as had section 7 declared a verb it did not close.
    SELECT count(*), string_agg(problem || ' on ' || object || ': ' || detail, '; ')
      INTO n, d FROM check_runtime_privileges();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-69 leaves the runtime surface wrong (% problems): %', n, d;
    END IF;

    -- A new program-scoped table is three separate ways to leak: a citation
    -- that crosses Programs without carrying one, a policy nobody wrote, and a
    -- purge that stops short of it.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-69 breaks Program isolation (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ' on ' || object || ': ' || detail, '; ')
      INTO n, d FROM check_rls_coverage();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-69 leaves a table unpoliced (% problems): %', n, d;
    END IF;

    -- Event coverage is deliberately not asked here: `enforce_always_triggers`
    -- is a finalizer, so mid-run every trigger this file just attached is still
    -- ordinary and the answer would be about the run rather than the file.
    SELECT count(*), string_agg(problem || ' on ' || subject || ': ' || detail, '; ')
      INTO n, d FROM check_purge_travel();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-69 leaves rows a purge cannot reach (% problems): %', n, d;
    END IF;
END $$;
