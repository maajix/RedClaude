-- ===========================================================================
-- Production harness 14 -- an interaction that arrived somewhere we said we
-- would listen
-- ===========================================================================
-- A callback is the one Observation the harness does not fetch. Everything
-- else in the epistemic pipeline is a request this installation made and a
-- Receipt the door wrote for it; an out-of-band interaction is a request
-- somebody else made, arriving at a name we published, and the only thing
-- tying it to a Program is a correlator that travelled out in a payload and
-- came back in a query. That difference is what this file is about: without a
-- correlator, an inbound record is a stranger's traffic, and promoting it into
-- evidence would let anyone on the internet confirm a Hypothesis by sending a
-- packet.
--
-- Four rules, and each of them is a table or a trigger rather than a caller's
-- `IF`:
--
--   * A channel is declared or it does not exist. `program_callback_channels`
--     is the scope version's own projection of `[[callback]]`, written by the
--     same compilation that writes the rules -- so "the channels this Program
--     declared" is a join, not a re-read of the operator's file, and a channel
--     that was withdrawn stops admitting arrivals the moment a new version goes
--     live.
--
--   * The correlator is minted by the runtime and stored as a digest.
--     `callback_correlators` holds `correlator_sha256` and nothing that could
--     reproduce the correlator, exactly as `tool_runs` holds the egress
--     capability. A correlator is not a capability: holding one authorises no
--     read, no write and no egress, which is why an arrival is allowed to
--     contain it and a Receipt's artifact list is not.
--
--   * The arrival resolves the correlator or it is not written at all. The
--     `ENABLE ALWAYS` trigger on `callback_interactions` re-asks every question
--     the writer asks, so an ungated INSERT by the owner is refused for the same
--     reasons an ungated call would have been. Missing, cleared, fabricated and
--     cross-Program correlators all fail the same join; an expired one fails the
--     clock, which the trigger reads for itself rather than believing the
--     `received_at` the row states; and a name that does not carry the
--     correlator it claims fails the digest, which is the arm that decides whose
--     canary fired rather than merely that one did.
--
--   * The Observation names the arrival. `observations` gains a third
--     provenance record, because a callback is neither a Receipt nor a Tool
--     run and forcing it to claim one of those would put a fact about inbound
--     traffic under a record of an outbound request.
--
-- What this file deliberately does NOT build:
--
--   * A listener. Nothing here opens a socket or speaks DNS. The runtime hands
--     the bytes it received to `record_callback_interaction`, and the acceptance
--     path is synthetic in the test suite for the same reason the proxy's target
--     is: what is under test is the admission decision, not somebody else's
--     resolver.
--
--   * Any agent surface. Neither table is on the agent read surface, so no
--     session can enumerate live correlators or read the names they arrived at.
--     The agent-visible half is the Observation and the stored bytes it cites --
--     which is the honest limit of this design: an out-of-band canary travels
--     inside the payload it was embedded in, so an agent that reads the arrival
--     bytes may read the correlator that produced them. It buys nothing, since
--     writing an arrival is a privilege no session holds, and a correlator
--     expires.
--
--   * Any discovery of callback infrastructure. `decide_callback` is already
--     `egress_support` and never `target`, and nothing here resolves, probes or
--     enumerates a channel host. An interaction beneath a declared endpoint is
--     admitted; the endpoint's neighbours, its parent domain and every host
--     nobody declared are refused by the same predicate that admits it.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. The channels a scope version declares
-- ---------------------------------------------------------------------------
-- Compiled output, projected beside `program_scope_rules` and
-- `program_required_headers` and immutable with the version that owns it. An
-- http channel also compiles to an `egress_support` request rule -- that is
-- ticket 08's business and is what stops the harness treating its own listener
-- as a target. This table answers the other question: which names may an
-- arrival have come in on, and under which channel.
--
-- `host` is stored exactly as the compiler normalised it, and a wildcard is
-- unrepresentable here as well as unwritable there: a channel already admits
-- everything beneath its endpoint, so `*.oob.example.net` would be a second
-- spelling of one rule, and the two spellings disagree about the endpoint
-- itself.

CREATE TABLE program_callback_channels (
    program_id uuid    NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    version    integer NOT NULL,
    ord        integer NOT NULL CHECK (ord >= 1),
    name       text    NOT NULL CHECK (name ~ '^[a-z0-9][a-z0-9-]{0,62}$'),
    kind       text    NOT NULL CHECK (kind IN ('dns','http')),
    host       text    NOT NULL CHECK (host = lower(host) AND host <> ''
                                       AND position('*' IN host) = 0),
    PRIMARY KEY (program_id, version, ord),
    UNIQUE (program_id, version, name),
    -- One endpoint, one channel. Two channels on one host would make "which
    -- channel admitted this arrival" a question about row order.
    UNIQUE (program_id, version, host),
    FOREIGN KEY (program_id, version)
        REFERENCES program_scope_versions (program_id, version)
);

COMMENT ON TABLE program_callback_channels IS
  'The out-of-band channels a Program declared, per scope version. An arrival is admitted by a row here or it is not written. Immutable with the version, and off the agent read surface.';

COMMENT ON COLUMN program_callback_channels.host IS
  'The channel endpoint. An arrival at this name, or at any name beneath it, is admitted; its parent, its siblings and every undeclared host are not.';

CREATE TRIGGER callback_channels_immutable
    BEFORE UPDATE OR DELETE ON program_callback_channels
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();
-- 021's lesson, and the reason every append-only table in this corpus repeats
-- it: `session_replication_role = replica` skips ORIGIN triggers, and a restore
-- is exactly when a compiled projection would be rewritten.
ALTER TABLE program_callback_channels
    ENABLE ALWAYS TRIGGER callback_channels_immutable;

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('program_callback_channels', 'program_id', 'program-scoped: the purge root');

-- Exempt in the same words as its two siblings: compiled output, not a
-- decision. `program.configured` records the revision these rows are derived
-- from, and the scope version's digest says which compilation produced them.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('program_callback_channels', 'reference',
     'the callback channels of a scope version; immutable with it and compiled from the revision that does emit', '14');


-- ---------------------------------------------------------------------------
-- 2. The correlator
-- ---------------------------------------------------------------------------
-- One row per correlator the runtime minted, holding the digest of a label it
-- did not keep. What the row binds is the whole of what an arrival may later
-- claim: one Program, one subject entity, and at most one of the Tool run or
-- Test run the correlator was minted for.
--
-- `subject_entity_id` is not optional, and it is the reason a correlator is
-- minted per test rather than per Program: an Observation has a subject, so a
-- correlator with none would produce a fact about nothing. The Tool run and
-- Test run columns are the narrower bindings on top of it -- an arrival is
-- attributable to the run that caused it when there was one, and to the Program
-- alone when an operator is driving.
--
-- `expires_at` is required. A canary with no lifetime is a name that confirms
-- Hypotheses forever, including long after the payload that carried it was
-- forgotten by everyone but the target.

CREATE TABLE callback_correlators (
    id                uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id        uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    scope_version     integer NOT NULL,
    channel_name      text NOT NULL,
    -- SHA-256 of the correlator, hex, lower case. The plaintext is returned once
    -- to the process that asked for it and stored nowhere.
    correlator_sha256 text NOT NULL CHECK (correlator_sha256 ~ '^[0-9a-f]{64}$'),
    -- NO ACTION on all three, which is 016's purge rule: `program_id` is the
    -- one edge to the root, and a second cascade path is a second way for a
    -- narrow delete to half-succeed. 017's rule 3 is the composite shape: a
    -- citation between two program-scoped rows carries the program, so a
    -- correlator cannot name another Program's entity or Tool run.
    subject_entity_id uuid NOT NULL,
    tool_run_id       uuid,
    test_run_id       uuid,
    issued_at         timestamptz NOT NULL DEFAULT now(),
    expires_at        timestamptz NOT NULL,
    cleared_at        timestamptz,
    -- Per Program, not global (017 rule 4). Two Programs minting the same 128
    -- bits is not a thing that happens, and a global key would make it an
    -- error in whichever Program went second rather than a coincidence.
    UNIQUE (program_id, correlator_sha256),
    -- What `callback_interactions` cites, in the shape rule 3 wants.
    CONSTRAINT callback_correlators_id_program_key UNIQUE (id, program_id),
    -- The channel as of the version it was minted under, so a correlator names
    -- a declaration that existed rather than a name that might be reused later.
    FOREIGN KEY (program_id, scope_version, channel_name)
        REFERENCES program_callback_channels (program_id, version, name),
    FOREIGN KEY (subject_entity_id, program_id) REFERENCES entities (id, program_id),
    FOREIGN KEY (tool_run_id, program_id) REFERENCES tool_runs (id, program_id),
    -- `test_runs` carries a derived `program_id` (017), so this key has the
    -- same shape as the other two.
    FOREIGN KEY (test_run_id, program_id) REFERENCES test_runs (id, program_id),
    -- One narrower binding at most. A correlator that named both would be
    -- attributable to two runs, and an arrival is caused by one thing.
    CHECK (tool_run_id IS NULL OR test_run_id IS NULL),
    CHECK (expires_at > issued_at)
);

CREATE INDEX callback_correlators_live_idx
    ON callback_correlators (program_id, expires_at) WHERE cleared_at IS NULL;

COMMENT ON TABLE callback_correlators IS
  'Correlators the runtime minted for declared channels, stored as digests. Holding a correlator authorises nothing: it is what makes an arrival attributable, not what makes it admissible.';

COMMENT ON COLUMN callback_correlators.correlator_sha256 IS
  'The digest of the correlator. The plaintext is returned once, travels in a payload, and is in no table, event or agent-visible view.';


-- ---------------------------------------------------------------------------
-- 3. The arrival, and the Observation it becomes
-- ---------------------------------------------------------------------------
-- The exact bytes go to the content-addressed store like every other piece of
-- evidence; this row is what they are, where they came in and which correlator
-- claimed them. `observed_host` is the name as received, because a record that
-- redacted the name would be a claim about an arrival nobody could check.

CREATE TABLE callback_interactions (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label         text NOT NULL DEFAULT '',
    correlator_id uuid NOT NULL,
    channel_name  text NOT NULL,
    -- 'dns' or 'http', and it must be the kind of the channel that admitted it:
    -- an HTTP request to a name we only ever published as a DNS canary is not
    -- the interaction the channel was declared for.
    arrival_kind  text NOT NULL CHECK (arrival_kind IN ('dns','http')),
    observed_host text NOT NULL CHECK (observed_host = lower(observed_host)),
    peer_class    text NOT NULL DEFAULT 'unknown'
                       CHECK (peer_class IN ('unknown','resolver','client')),
    received_at   timestamptz NOT NULL DEFAULT now(),
    body_sha256   text NOT NULL REFERENCES artifacts(sha256),
    byte_size     bigint NOT NULL CHECK (byte_size >= 0),
    UNIQUE (program_id, label),
    -- What the Observation cites.
    CONSTRAINT callback_interactions_id_program_key UNIQUE (id, program_id),
    FOREIGN KEY (correlator_id, program_id)
        REFERENCES callback_correlators (id, program_id)
);

CREATE INDEX callback_interactions_correlator_idx
    ON callback_interactions (correlator_id, received_at DESC);

COMMENT ON TABLE callback_interactions IS
  'One inbound out-of-band interaction, admitted by a live correlator on a declared channel. Off the agent read surface: what an agent may cite is the Observation and the stored bytes.';

INSERT INTO label_prefixes (kind, prefix) VALUES ('callback_interactions', 'CB');

CREATE TRIGGER callback_interactions_assign_label
    BEFORE INSERT ON callback_interactions
    FOR EACH ROW EXECUTE FUNCTION assign_label();

CREATE TRIGGER callback_interactions_immutable
    BEFORE UPDATE OR DELETE ON callback_interactions
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();
ALTER TABLE callback_interactions
    ENABLE ALWAYS TRIGGER callback_interactions_immutable;

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('callback_correlators', 'program_id', 'program-scoped: the purge root'),
    ('callback_interactions', 'program_id', 'program-scoped: the purge root');

INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('callback.observed', 'row', 'callback_interactions',
     'an out-of-band interaction arrived on a declared channel and resolved a live correlator');

INSERT INTO event_table_config
    (table_name, created_type, updated_type, ignored_columns, redacted_columns) VALUES
    -- `observed_host` is redacted rather than logged: the name an arrival came
    -- in on carries the correlator, and the event log is the most widely read
    -- surface in the installation. The label, the channel and the digest of the
    -- bytes are what an auditor needs, and they are all still here.
    ('callback_interactions', 'callback.observed', NULL, '{}', '{observed_host}');

-- The correlator table emits nothing. Its rows are minting and expiry, and an
-- event per correlator is an oracle for when a live canary exists and when it
-- stopped being live -- which is the one thing about a correlator worth
-- knowing without holding it. `callback.observed` records the half that is a
-- fact about the target rather than about our own bookkeeping.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('callback_correlators', 'bookkeeping',
     'correlators the runtime minted for itself; an event per correlator would log when a live canary exists without saying anything about a target', '14');

SELECT attach_event_triggers();


-- ---------------------------------------------------------------------------
-- 4. A third provenance record
-- ---------------------------------------------------------------------------
-- 006 forced an Observation to name a Receipt or a Tool run, and 018 forced it
-- to name the one its kind can be produced by. A callback is neither: no
-- request of ours produced it, and no tool of ours ran. Filing it under either
-- would attach a fact about inbound traffic to a record of an outbound request
-- -- and `receipt_id` is the column ticket 09's fence, ticket 25's transport
-- guard and ticket 42's rendering all read.
--
-- The constraints are discovered rather than named: 0007 wrote both of them
-- inline, so their names are PostgreSQL's and a migration that guessed wrong
-- would fail on a database restored from a dump taken by a different server.

-- NO ACTION, like the two provenance columns beside it: 016 stripped the
-- cascade off `receipt_id` and `tool_run_id` so a narrow delete of the record
-- an Observation cites cannot silently take the Observation with it. Composite,
-- like them too: 017's rule 3 rewrote both to carry the program, and the same
-- shape here is what makes an Observation citing another Program's arrival a
-- foreign key violation rather than a thing a trigger has to notice.
ALTER TABLE observations
    ADD COLUMN callback_interaction_id uuid,
    ADD CONSTRAINT observations_callback_interaction_id_fkey
        FOREIGN KEY (callback_interaction_id, program_id)
        REFERENCES callback_interactions (id, program_id);

COMMENT ON COLUMN observations.callback_interaction_id IS
  'The arrival this Observation is derived from. The third provenance record: an inbound interaction nobody here requested.';

DO $mig$
DECLARE c text;
BEGIN
    FOR c IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'observations'::regclass
           AND contype = 'c'
           AND pg_get_constraintdef(oid) LIKE '%provenance_kind%'
    LOOP
        EXECUTE format('ALTER TABLE observations DROP CONSTRAINT %I', c);
    END LOOP;
END $mig$;

ALTER TABLE observations
    ADD CONSTRAINT observations_provenance_kind_check
        CHECK (provenance_kind IN ('receipt','tool_run','callback')),
    -- Exactly one record, and never none. The third arm is the new one; the
    -- first two are 0007's, restated with the new column excluded so a Receipt
    -- observation cannot also claim an arrival.
    ADD CONSTRAINT observations_provenance_record_check
        CHECK ((provenance_kind = 'receipt'
                AND receipt_id IS NOT NULL AND tool_run_id IS NULL
                AND callback_interaction_id IS NULL)
            OR (provenance_kind = 'tool_run'
                AND tool_run_id IS NOT NULL AND receipt_id IS NULL
                AND callback_interaction_id IS NULL)
            OR (provenance_kind = 'callback'
                AND callback_interaction_id IS NOT NULL AND receipt_id IS NULL
                AND tool_run_id IS NULL));

ALTER TABLE observation_kinds
    DROP CONSTRAINT observation_kinds_allowed_provenance_closed;
ALTER TABLE observation_kinds
    ADD CONSTRAINT observation_kinds_allowed_provenance_closed
        CHECK (array_to_string(allowed_provenance, ',')
               IN ('receipt', 'tool_run', 'receipt,tool_run', 'callback'));

-- Evidential, and deliberately its own kind rather than a `state_change` with
-- an unusual provenance: what a callback settles is that the target reached
-- somewhere it was told to, which is a different claim from a side effect seen
-- on a later request. `{callback}` alone, so an agent cannot file a Receipt
-- under it and inherit the weight of an out-of-band confirmation.
INSERT INTO observation_kinds (id, name, is_evidential, allowed_provenance, description) VALUES
    ('callback_interaction', 'Callback interaction', true, '{callback}',
     'an out-of-band interaction arrived on a channel this Program declared, carrying a correlator the runtime minted for one subject');


-- ---------------------------------------------------------------------------
-- 5. Resolving a correlator
-- ---------------------------------------------------------------------------
-- The shape of `resolve_egress_capability`, and for the same reason: the
-- resolver is the door every honest caller comes through, and the trigger below
-- is the invariant. A rule that lived only here is a rule an owner-level INSERT
-- walks around.
--
-- `rk2_program()` is in the predicate rather than a program argument, so a
-- session bound to one Program cannot resolve another's correlator however it
-- was obtained. That is the whole of the cross-Program answer: not a comparison
-- the caller makes, but a row the caller cannot see.

CREATE FUNCTION resolve_callback_correlator(p_correlator text)
RETURNS TABLE (
    correlator_id          uuid,
    program_id        uuid,
    channel_name      text,
    channel_kind      text,
    channel_host      text,
    subject_entity_id uuid,
    tool_run_id       uuid,
    test_run_id       uuid,
    expires_at        timestamptz
)
LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
    SELECT t.id, t.program_id, t.channel_name, c.kind, c.host,
           t.subject_entity_id, t.tool_run_id, t.test_run_id, t.expires_at
      FROM callback_correlators t
      JOIN programs p
        ON p.id = t.program_id AND p.closed_at IS NULL
      JOIN program_callback_channels c
        ON c.program_id = t.program_id
       AND c.version = p.scope_version
       AND c.name = t.channel_name
     WHERE p_correlator IS NOT NULL
       AND t.program_id = rk2_program()
       AND t.correlator_sha256 = encode(digest(p_correlator, 'sha256'), 'hex')
       AND t.cleared_at IS NULL
       AND t.expires_at > clock_timestamp();
$fn$;

COMMENT ON FUNCTION resolve_callback_correlator(text) IS
  'Resolves a correlator only while its Program is open, its channel is still declared by the live scope version, and the correlator is neither cleared nor expired. Bound to the session Program, so another Program''s correlator resolves to nothing.';

-- Whether a name arrived on a channel. The channel endpoint counts and every
-- label beneath it counts, because that is how a canary is addressed -- the
-- correlator is the label. Nothing above the endpoint counts, which is what
-- keeps a Program's declaration of `oob.example.net` from admitting
-- `example.net` or `other.example.net`.
-- A literal suffix compare rather than a LIKE, because `LIKE` would read `_`
-- and `%` in a declared host as pattern syntax. `normalize_host` admits neither
-- today, but a fence whose reach depends on another module's regex is a fence
-- that widens the day that regex does. This is `endswith('.' || host)`, spelled
-- the way SQL spells it.
CREATE FUNCTION callback_host_admitted(p_host text, p_channel_host text)
RETURNS boolean
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT p_host IS NOT NULL AND p_channel_host IS NOT NULL
       AND (p_host = p_channel_host
            OR right(p_host, length(p_channel_host) + 1) = '.' || p_channel_host);
$fn$;

COMMENT ON FUNCTION callback_host_admitted(text, text) IS
  'Whether an observed name is the channel endpoint or a label beneath it. Mirrors scope.Channel.admits.';

-- And which label is the correlator, which is a different question: every live
-- correlator of a Program is admitted by the same channel, so a name beneath
-- one says that some canary was queried and not which. The label immediately
-- beneath the endpoint, not the whole prefix -- a resolver that queried
-- `www.<correlator>.<endpoint>` reported one arrival on one canary, and the
-- extra label is the target's business. NULL for the endpoint itself, which
-- carries no correlator at all, and NULL for a name this channel does not
-- admit, so neither can be compared into an accidental match. Mirrors
-- `callback._correlator`.
CREATE FUNCTION callback_correlator_label(p_host text, p_channel_host text)
RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT CASE
             WHEN NOT callback_host_admitted(p_host, p_channel_host) THEN NULL
             WHEN p_host = p_channel_host THEN NULL
             ELSE nullif(
                    split_part(
                      left(p_host, length(p_host) - length(p_channel_host) - 1),
                      '.', -1),
                    '')
           END;
$fn$;

COMMENT ON FUNCTION callback_correlator_label(text, text) IS
  'The label an arrival carries beneath a channel endpoint, which is the correlator it claims. Null for the endpoint itself and for any name the channel does not admit.';


-- ---------------------------------------------------------------------------
-- 6. The invariant: an arrival nobody can attribute is unwritable
-- ---------------------------------------------------------------------------
-- ENABLE ALWAYS, and it re-asks every question the writer asks, because the
-- writer is a convenience and this is the guarantee. A restore, a fixture
-- loaded by the database owner and a future caller that forgot the writer all
-- meet the same refusal.

CREATE FUNCTION enforce_callback_attribution() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE t record;
BEGIN
    SELECT tk.program_id, tk.channel_name, tk.issued_at, tk.expires_at,
           tk.cleared_at, tk.correlator_sha256, c.kind, c.host
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
    IF NOT callback_host_admitted(NEW.observed_host, t.host) THEN
        RAISE EXCEPTION 'callback interaction arrived at %, which channel % does not admit',
            NEW.observed_host, t.channel_name
            USING ERRCODE = '23514';
    END IF;
    -- The arm that decides whose canary fired. Every live correlator of this
    -- Program is admitted by the same channel, so the arm above says only that
    -- some canary was queried; without this one an arrival at subject B's name
    -- could be filed under subject A's correlator, and the Observation would be
    -- a true fact about the wrong entity. The digest is all this table holds,
    -- and comparing it to the label the name carries is exactly what it is for.
    IF encode(digest(callback_correlator_label(NEW.observed_host, t.host), 'sha256'), 'hex')
       IS DISTINCT FROM t.correlator_sha256 THEN
        RAISE EXCEPTION 'callback interaction arrived at %, which does not carry the correlator it claims',
            NEW.observed_host USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER callback_interactions_attribution
    BEFORE INSERT ON callback_interactions
    FOR EACH ROW EXECUTE FUNCTION enforce_callback_attribution();
ALTER TABLE callback_interactions
    ENABLE ALWAYS TRIGGER callback_interactions_attribution;

-- And the Observation's half, which the composite foreign key above already
-- says. It is repeated as an ALWAYS trigger for the one case the key cannot
-- cover: `session_replication_role = replica` skips referential integrity
-- triggers as well as ORIGIN ones, so during a restore the key is not checked
-- and this is. Same reason 021 gave for every immutability trigger in the
-- corpus, applied to the constraint that decides whose evidence this is.
CREATE FUNCTION enforce_callback_observation_program() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE p uuid;
BEGIN
    IF NEW.provenance_kind <> 'callback' THEN
        RETURN NEW;
    END IF;
    SELECT ci.program_id INTO p
      FROM callback_interactions ci WHERE ci.id = NEW.callback_interaction_id;
    IF p IS DISTINCT FROM NEW.program_id THEN
        RAISE EXCEPTION
            'observation cites a callback interaction belonging to another Program'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER observations_callback_program_guard
    BEFORE INSERT ON observations
    FOR EACH ROW EXECUTE FUNCTION enforce_callback_observation_program();
ALTER TABLE observations
    ENABLE ALWAYS TRIGGER observations_callback_program_guard;


-- ---------------------------------------------------------------------------
-- 7. Minting, clearing, and the one call that accepts an arrival
-- ---------------------------------------------------------------------------
-- Minting is a function rather than an INSERT because the caller must not be
-- able to state the digest of a correlator it did not generate:
-- `mint_callback_correlator` takes the plaintext, digests it here, and returns
-- the row identifier. The plaintext is a `text` argument and therefore reaches
-- the server -- which is why the function is `SECURITY DEFINER` with a fixed
-- search path, writes no log line, and stores only the digest.

CREATE FUNCTION mint_callback_correlator(
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
    v_program uuid := rk2_program();
    v_version integer;
    v_id      uuid;
BEGIN
    IF v_program IS NULL OR p_correlator IS NULL OR p_channel IS NULL
       OR p_subject IS NULL OR p_lifetime IS NULL OR p_lifetime <= interval '0' THEN
        RAISE EXCEPTION 'callback correlator refused' USING ERRCODE = '23514';
    END IF;
    -- One DNS label, lower case, because that is the only shape a correlator can
    -- arrive in: an observed name is stored lowercased, and the admission
    -- trigger compares the digest of the label it carries. A correlator that
    -- could never match the name it travels in is one whose arrivals would all
    -- be refused, which is a canary that quietly does not work.
    IF p_correlator !~ '^[a-z0-9][a-z0-9-]{0,62}$' THEN
        RAISE EXCEPTION 'a correlator is one lower-case DNS label'
            USING ERRCODE = '23514';
    END IF;
    -- The live version, not any version: a channel withdrawn by the operator's
    -- last revision is a channel no new correlator may be minted for.
    SELECT p.scope_version INTO v_version
      FROM programs p WHERE p.id = v_program AND p.closed_at IS NULL;
    IF NOT FOUND OR NOT EXISTS (
        SELECT 1 FROM program_callback_channels c
         WHERE c.program_id = v_program AND c.version = v_version
           AND c.name = p_channel
    ) THEN
        RAISE EXCEPTION 'channel % is not declared by the live scope policy', p_channel
            USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM entities e
                    WHERE e.id = p_subject AND e.program_id = v_program) THEN
        RAISE EXCEPTION 'the subject of a correlator must be an entity of this Program'
            USING ERRCODE = '23514';
    END IF;

    PERFORM set_actor('runtime');
    INSERT INTO callback_correlators
        (program_id, scope_version, channel_name, correlator_sha256, subject_entity_id,
         tool_run_id, test_run_id, expires_at)
    VALUES (v_program, v_version, p_channel,
            encode(digest(p_correlator, 'sha256'), 'hex'), p_subject,
            p_tool_run, p_test_run, clock_timestamp() + p_lifetime)
    RETURNING id INTO v_id;
    RETURN v_id;
END $fn$;

COMMENT ON FUNCTION mint_callback_correlator(text, text, uuid, interval, uuid, uuid) IS
  'Records a correlator for a channel the live scope policy declares, storing its digest and never its plaintext. Refuses an undeclared channel, a foreign subject and an unbounded lifetime.';

-- Clearing is the operator's and the runtime's way of ending a canary early --
-- when the test that carried it is over, or when the payload turns out to have
-- gone somewhere it should not have. It is a function because
-- `callback_correlators` takes no UPDATE from any role: a correlator whose
-- expiry could be moved is a correlator with no expiry.
CREATE FUNCTION clear_callback_correlator(p_correlator_id uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE v_cleared boolean;
BEGIN
    PERFORM set_actor('runtime');
    UPDATE callback_correlators
       SET cleared_at = clock_timestamp()
     WHERE id = p_correlator_id
       AND program_id = rk2_program()
       AND cleared_at IS NULL
    RETURNING true INTO v_cleared;
    RETURN coalesce(v_cleared, false);
END $fn$;

COMMENT ON FUNCTION clear_callback_correlator(uuid) IS
  'Ends a correlator early. Idempotent: clearing an already cleared or unknown correlator answers false and changes nothing.';

-- One call, one transaction: the bytes, the arrival and the Observation, or
-- none of them. Two calls would allow an arrival naming bytes nobody stored,
-- and an arrival with no Observation is evidence that exists and cannot be
-- cited.
CREATE FUNCTION record_callback_interaction(
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
    v_kind        text;
    v_peer        text;
    v_sha         text;
    v_size        bigint;
    v_type        text;
    v_interaction uuid;
    v_label       text;
    v_reference   text;
    v_observation uuid;
    v_obs_label   text;
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

    v_host := lower(nullif(p_arrival ->> 'host', ''));
    v_kind := nullif(p_arrival ->> 'arrival_kind', '');
    v_peer := coalesce(nullif(p_arrival ->> 'peer_class', ''), 'unknown');
    v_sha  := nullif(p_artifact ->> 'sha256', '');
    v_type := nullif(p_artifact ->> 'content_type', '');
    v_size := (p_artifact ->> 'byte_size')::bigint;

    IF v_host IS NULL OR v_kind IS NULL OR v_sha IS NULL OR v_size IS NULL THEN
        RAISE EXCEPTION 'a callback interaction states a host, a kind and the bytes it received'
            USING ERRCODE = '23514';
    END IF;
    IF v_sha !~ '^[0-9a-f]{64}$' OR v_size < 0 THEN
        RAISE EXCEPTION 'callback interaction names bytes with no hash or no byte count'
            USING ERRCODE = '23514';
    END IF;
    -- The name and the correlator arrive as two arguments, and nothing but this
    -- makes them one claim: resolving a live correlator says a canary of this
    -- Program fired, and the name says which. Asked here as well as in the
    -- trigger, so the convenience and the guarantee refuse the same rows.
    IF callback_correlator_label(v_host, t.channel_host) IS DISTINCT FROM p_correlator THEN
        RAISE EXCEPTION 'callback interaction arrived at %, which does not carry the correlator it claims',
            v_host USING ERRCODE = '23514';
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
         peer_class, body_sha256, byte_size)
    VALUES (t.program_id, t.correlator_id, t.channel_name, v_kind, v_host,
            v_peer, v_sha, v_size)
    RETURNING id, label INTO v_interaction, v_label;

    -- The summary names the channel and the bytes and not the host. The host
    -- carries the correlator, and this string is the one part of the record an
    -- agent reads.
    INSERT INTO observations
        (program_id, subject_entity_id, kind, summary, provenance_kind,
         callback_interaction_id, observed_at, metadata)
    VALUES (t.program_id, t.subject_entity_id, 'callback_interaction',
            'an out-of-band ' || v_kind || ' interaction arrived on channel '
              || t.channel_name || ' carrying this subject''s correlator, '
              || v_size || ' byte(s) stored as ' || coalesce(v_reference, v_sha),
            'callback', v_interaction, clock_timestamp(),
            jsonb_build_object('interaction', v_label,
                               'channel', t.channel_name,
                               'arrival_kind', v_kind,
                               'byte_size', v_size))
    RETURNING id, label INTO v_observation, v_obs_label;

    RETURN jsonb_build_object(
        'interaction_id', v_interaction, 'interaction', v_label,
        'observation_id', v_observation, 'observation', v_obs_label,
        'artifact', v_reference, 'sha256', v_sha,
        'channel', t.channel_name, 'correlator_id', t.correlator_id);
END $fn$;

COMMENT ON FUNCTION record_callback_interaction(text, jsonb, jsonb) IS
  'Accepts one inbound interaction: resolves the correlator, registers the exact bytes, writes the arrival and promotes it into an immutable Observation, in one transaction or not at all.';


-- ---------------------------------------------------------------------------
-- 8. Who may do any of it
-- ---------------------------------------------------------------------------
-- The runtime alone. The proxy is the outbound door and has no business
-- writing inbound records; `rk2_state` is the connection the model reads
-- through and holds nothing here at all -- not the verbs, and not the tables,
-- which is what keeps live correlators and the names they arrived at off the
-- agent surface. Nothing is added to `state_read_surface`, so the absence is
-- the grant.

REVOKE ALL ON FUNCTION resolve_callback_correlator(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION mint_callback_correlator(text, text, uuid, interval, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION clear_callback_correlator(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION record_callback_interaction(text, jsonb, jsonb) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION mint_callback_correlator(text, text, uuid, interval, uuid, uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION clear_callback_correlator(uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION record_callback_interaction(text, jsonb, jsonb) TO rk2_runtime;

-- 0029's default privileges hand the owner's new tables to `rk2_runtime` with
-- every DML verb, and ticket 13 found what that is worth: a role that can
-- UPDATE a correlator can move its expiry past the moment it should have died,
-- and one that can DELETE an arrival can unmake the evidence it produced. Both
-- go.
--
-- SELECT and INSERT stay, because 029's `readwrite_on_every_managed_table`
-- asserts the runtime keeps them everywhere and narrowing that generally is
-- ticket 66's. Neither is a way in here. A hand-written correlator row is
-- bounded by the FK -- it can only name a channel some version of this
-- Program's policy declared -- and a hand-written arrival meets
-- `callback_interactions_attribution`, which re-asks every question the writer
-- asks: whether that channel is still declared by the version live now, whether
-- the correlator is live by the clock rather than by the row's own
-- `received_at`, and whether the name it came in at carries that correlator at
-- all. What the runtime can do without a verb is mint itself a correlator it
-- could have asked for anyway.
REVOKE UPDATE, DELETE ON TABLE callback_correlators, callback_interactions
    FROM rk2_runtime;
REVOKE ALL ON TABLE callback_correlators, callback_interactions, program_callback_channels
    FROM rk2_proxy, rk2_state, rk2_human;


-- ---------------------------------------------------------------------------
-- 9. The standing check
-- ---------------------------------------------------------------------------

CREATE FUNCTION check_callback_admission()
RETURNS TABLE(problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) The verbs are the runtime's alone.
    SELECT 'callback_verbs_misplaced',
           p.grantee || ' can execute ' || p.verb
      FROM (
        SELECT g.grantee, f.verb
          FROM (VALUES ('record_callback_interaction(text,jsonb,jsonb)'),
                       ('mint_callback_correlator(text,text,uuid,interval,uuid,uuid)'),
                       ('clear_callback_correlator(uuid)'),
                       ('resolve_callback_correlator(text)')) AS f(verb),
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
    -- (c) The correlator and the name it arrived at are not on the agent read
    --     surface, and a row added there is what would put them on it.
    SELECT 'callback_on_agent_surface', s.table_name || '.' || s.column_name
      FROM state_read_surface s
     WHERE s.table_name IN ('callback_correlators', 'callback_interactions')
    UNION ALL
    -- (d) The invariants, still ALWAYS. `tgenabled` is 'A' for ENABLE ALWAYS
    --     and 'O' for an ordinary trigger a restore would skip.
    SELECT 'callback_guard_not_always', tg.tgname
      FROM pg_trigger tg
     WHERE tg.tgname IN ('callback_interactions_attribution',
                         'callback_interactions_immutable',
                         'observations_callback_program_guard',
                         'callback_channels_immutable')
       AND tg.tgenabled <> 'A'
    UNION ALL
    SELECT 'callback_guard_missing', want.tgname
      FROM (VALUES ('callback_interactions_attribution'),
                   ('callback_interactions_immutable'),
                   ('observations_callback_program_guard'),
                   ('callback_channels_immutable')) AS want(tgname)
     WHERE NOT EXISTS (SELECT 1 FROM pg_trigger tg WHERE tg.tgname = want.tgname)
    UNION ALL
    -- (e) And the rows themselves: an arrival whose correlator belongs to
    --     another Program, or that came in at a name no channel of its Program
    --     has ever admitted. Against every version rather than the live one,
    --     because an arrival was admitted by the policy that was live when it
    --     arrived, and a check nobody can clear stops being a signal.
    SELECT 'callback_interaction_unattributed', ci.label
      FROM callback_interactions ci
      LEFT JOIN callback_correlators t
        ON t.id = ci.correlator_id AND t.program_id = ci.program_id
     WHERE t.id IS NULL
    UNION ALL
    SELECT 'callback_interaction_undeclared_host', ci.label
      FROM callback_interactions ci
     WHERE NOT EXISTS (
        SELECT 1 FROM program_callback_channels c
         WHERE c.program_id = ci.program_id
           AND c.name = ci.channel_name
           AND c.kind = ci.arrival_kind
           AND callback_host_admitted(ci.observed_host, c.host))
    UNION ALL
    -- and an arrival filed under a correlator the name it came in at does not
    -- carry. The two above ask whether some canary of this Program fired; this
    -- asks which, against the version the correlator was minted under, because
    -- that is the declaration it was addressed beneath.
    SELECT 'callback_interaction_mislabelled', ci.label
      FROM callback_interactions ci
      JOIN callback_correlators t
        ON t.id = ci.correlator_id AND t.program_id = ci.program_id
      JOIN program_callback_channels c
        ON c.program_id = t.program_id AND c.version = t.scope_version
       AND c.name = t.channel_name
     WHERE encode(digest(callback_correlator_label(ci.observed_host, c.host),
                         'sha256'), 'hex')
           IS DISTINCT FROM t.correlator_sha256
    UNION ALL
    SELECT 'callback_observation_foreign', o.label
      FROM observations o
      JOIN callback_interactions ci ON ci.id = o.callback_interaction_id
     WHERE o.provenance_kind = 'callback' AND ci.program_id <> o.program_id;
$fn$;

REVOKE ALL ON FUNCTION check_callback_admission() FROM PUBLIC;

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('callback_admission', 'SELECT * FROM check_callback_admission()', '14',
     'accepting an out-of-band interaction is the runtime''s verb alone, a correlator is nobody''s to rewrite, neither it nor the name it arrived at is on the agent surface, and every stored arrival still resolves a correlator of its own Program on a channel that Program declared, at a name carrying that correlator');

COMMENT ON FUNCTION check_callback_admission() IS
  'Callback admission, asserted from both ends: who may accept an interaction, and whether any stored arrival lacks the correlator, the declared channel or the matching name that would make it evidence about its subject.';
