-- ---------------------------------------------------------------------------
-- 20260818T000000Z__a_chain_is_composed_and_stays_sound.sql  (40)
-- ---------------------------------------------------------------------------
--
--   039 refused to let a hunter write "so". It replaced the word with a stamp:
--   one capability, obtained once, from one member Finding, under one Identity,
--   witnessed by one run. This ticket is what those stamps are for. A chain is
--   the composition, and the only thing it may compose over is stamps.
--
--   The shape, and why it is this shape:
--
--    * Nothing about the graph is proposed. An agent may say which stamps it
--      thinks belong together and in what order, and that is the whole of what
--      it may say. Where the edges go is a question the stamps already answer:
--      one step provides a capability the next one requires, or it does not.
--      The runtime derives the edges, stores its own order, and keeps the
--      agent's claim beside the answer rather than inside it.
--
--    * A chain is sound or it is not, and the answer is never stored. A stored
--      verdict is a cached answer that goes stale exactly when it matters --
--      the day a member is withdrawn is the day the cache still says yes. So
--      there is no verdict column anywhere in this migration, which is also the
--      shortest possible proof that no agent can write one.
--
--    * What the harness starts with is a fact about the Program, not a claim in
--      the proposal. If a chain could declare its own starting capabilities,
--      every chain would declare all of them and every chain would be sound.
--      The Program reaches its target because it is a target, and it holds a
--      session if and only if an operator provisioned an Identity. Everything
--      else has to be obtained by a step, which is what a chain is for.
--
--    * Idempotence is a hash again, and it is a hash of hashes: a chain's
--      digest is over its members' digests, and a stamp's digest is already
--      over everything that stamp rests on. So a chain's identity covers the
--      whole tree beneath it, and two agents proposing the same stamps in
--      different orders build one chain rather than two.

-- ===========================================================================
-- 1. What the harness starts with
-- ===========================================================================
--
-- Criterion 3 wants unsatisfied requirements refused, and that rule is only
-- meaningful once something says what does not need satisfying. Two words, and
-- both of them are read off the Program rather than taken from the caller:
--
--   `anonymous_reach` -- always. A Program is a target somebody asked to be
--   tested; being able to send it a request is the premise of the whole
--   corpus, not an achievement to be stamped.
--
--   `authenticated_session` -- exactly when an operator provisioned an Identity
--   that is not the anonymous one and has not been invalidated. A program that
--   hands out test accounts hands out sessions, and a chain whose first step
--   needs one it was given is a real chain. `identity_slots` and not
--   `identities`: 012 declares an Identity in the configuration and seals the
--   material separately, and a slot nobody provisioned is a session nothing can
--   be sent as.
--
-- Nothing else is free. `privileged_role`, `credential_material` and the rest
-- are what a step is for, and a Program that started with them would make the
-- chain that obtained them unnecessary.

CREATE FUNCTION rk2_chain_entry(p_program uuid) RETURNS text[]
LANGUAGE sql STABLE AS $fn$
    SELECT ARRAY['anonymous_reach']::text[]
        || CASE WHEN EXISTS (SELECT 1
                               FROM identities i
                               JOIN identity_slots s
                                 ON s.identity_entity_id = i.entity_id
                              WHERE i.program_id = p_program
                                AND i.class <> 'anonymous'
                                AND i.invalidated_at IS NULL)
                THEN ARRAY['authenticated_session']::text[]
                ELSE ARRAY[]::text[] END
$fn$;

COMMENT ON FUNCTION rk2_chain_entry(uuid) IS
  'Ticket 40: the capabilities a chain of this Program may assume rather than obtain -- reaching the surface, always, and holding a session exactly when an operator provisioned a live non-anonymous Identity. Derived and never declared: a chain that could name its own starting capabilities would name all of them.';


-- ===========================================================================
-- 2. The graph, derived
-- ===========================================================================
--
-- Criterion 2. An edge is not a thing anybody writes down; it is a thing two
-- stamps either have between them or do not. One provides a capability, the
-- other requires it, and both are columns 039 put on the stamp precisely so
-- this join would be a join.
--
-- Everything in this section takes the same two arguments -- the Program and a
-- set of stamps -- so that the graph a chain is checked as is the same graph it
-- is stored as. The alternative is a validator that reasons about one graph and
-- a builder that writes another, and those two agree until the day they do not.

CREATE FUNCTION rk2_chain_edges(p_program uuid, p_members uuid[])
RETURNS TABLE (from_stamp uuid, to_stamp uuid, capability text)
LANGUAGE sql STABLE AS $fn$
    SELECT u.id, d.id, u.provides
      FROM pivot_stamps u
      JOIN pivot_stamps d
        ON d.program_id = u.program_id
       AND d.id = ANY (p_members)
       AND d.id <> u.id
       AND u.provides = ANY (d.requires)
     WHERE u.program_id = p_program AND u.id = ANY (p_members)
$fn$;

COMMENT ON FUNCTION rk2_chain_edges(uuid, uuid[]) IS
  'Ticket 40 criterion 2: the edges a set of pivot stamps has between them, which is every pair where one provides what the other requires. Derived on every read rather than remembered, so the graph a chain is checked as and the graph it is stored as are one query.';

-- How deep into the chain a step sits: the longest way to reach it from a step
-- nothing points at. Depth rather than an ordinal, because a branch has two
-- steps in the same place and an ordinal would have to invent an order between
-- them. Only ever asked of a graph that has already been found acyclic -- the
-- `CYCLE` clause is here so this cannot loop forever if it is asked anyway,
-- not because a looping graph has a depth.
CREATE FUNCTION rk2_chain_depths(p_program uuid, p_members uuid[])
RETURNS TABLE (of_stamp uuid, at_depth integer)
LANGUAGE sql STABLE AS $fn$
    WITH RECURSIVE edge AS (
        SELECT e.from_stamp, e.to_stamp FROM rk2_chain_edges(p_program, p_members) e
    ), walk AS (
        SELECT s.id AS stamp_id, 0 AS depth
          FROM pivot_stamps s
         WHERE s.id = ANY (p_members) AND s.program_id = p_program
           AND NOT EXISTS (SELECT 1 FROM edge e WHERE e.to_stamp = s.id)
         UNION ALL
        SELECT e.to_stamp, w.depth + 1
          FROM walk w JOIN edge e ON e.from_stamp = w.stamp_id
    ) CYCLE stamp_id SET looped USING trail
    SELECT w.stamp_id, max(w.depth)::integer
      FROM walk w WHERE NOT w.looped GROUP BY w.stamp_id
$fn$;

COMMENT ON FUNCTION rk2_chain_depths(uuid, uuid[]) IS
  'Ticket 40: how deep into a chain each pivot stamp sits, counted as the longest way to reach it from a step nothing points at. Depth rather than an ordinal, because a branch puts two steps in the same place and an ordinal would invent an order between them.';

-- A step that is its own ancestor. This is the circular argument the ticket is
-- really about -- "the session gets us the token, and the token gets us the
-- session" is two stamps that satisfy each other and prove nothing -- and it
-- has to be asked before requirements are, because a cycle satisfies its own
-- requirements by construction.
CREATE FUNCTION rk2_chain_cycle(p_program uuid, p_members uuid[]) RETURNS uuid
LANGUAGE sql STABLE AS $fn$
    WITH RECURSIVE edge AS (
        SELECT e.from_stamp, e.to_stamp FROM rk2_chain_edges(p_program, p_members) e
    ), walk AS (
        SELECT e.from_stamp AS root, e.to_stamp AS at FROM edge e
         UNION ALL
        SELECT w.root, e.to_stamp
          FROM walk w JOIN edge e ON e.from_stamp = w.at
    ) CYCLE at SET looped USING trail
    SELECT w.root FROM walk w WHERE w.root = w.at ORDER BY w.root LIMIT 1
$fn$;

COMMENT ON FUNCTION rk2_chain_cycle(uuid, uuid[]) IS
  'Ticket 40 criterion 3: a pivot stamp that is its own ancestor, or NULL. The circular argument this ticket is about -- the session gets us the token and the token gets us the session -- which has to be asked before requirements, because a cycle satisfies its own by construction.';

-- Which steps hang together, walked with the edges read in both directions. A
-- branch is one root reaching two steps and a merge is two roots reaching one,
-- and both are chains; what is not a chain is two chains, which is what a
-- member no undirected walk reaches means.
CREATE FUNCTION rk2_chain_reached(p_program uuid, p_members uuid[]) RETURNS uuid[]
LANGUAGE sql STABLE AS $fn$
    WITH RECURSIVE either_way AS (
        SELECT e.from_stamp AS here, e.to_stamp AS there
          FROM rk2_chain_edges(p_program, p_members) e
         UNION ALL
        SELECT e.to_stamp, e.from_stamp
          FROM rk2_chain_edges(p_program, p_members) e
    ), reached AS (
        SELECT (SELECT s.id FROM pivot_stamps s
                 WHERE s.id = ANY (p_members) AND s.program_id = p_program
                 ORDER BY s.id LIMIT 1) AS id
         UNION
        SELECT b.there FROM reached r JOIN either_way b ON b.here = r.id
    )
    SELECT coalesce(array_agg(r.id), '{}'::uuid[]) FROM reached r WHERE r.id IS NOT NULL
$fn$;

COMMENT ON FUNCTION rk2_chain_reached(uuid, uuid[]) IS
  'Ticket 40 criterion 3: which of a proposal''s pivot stamps hang together, walked with the edges read in both directions from the lowest-keyed member. A branch and a merge are both chains; a member no undirected walk reaches means this proposal is two chains.';


-- ===========================================================================
-- 3. Integrity, asked before anything is written
-- ===========================================================================
--
-- Criterion 3's six rejections and criterion 6's empty graph, in one function
-- returning the first reason or NULL. One function and not one per rule, for
-- 039's reason: the alternative is a refusal worded in the builder and a second
-- copy worded in the check, and the two answer differently on the day one of
-- them is edited.
--
-- The order is not decorative. A cycle is asked before requirements, because a
-- cycle satisfies its own; the stamps are resolved before anything else,
-- because every later rule reads columns off them; and the empty graph is asked
-- first of all, because every rule below it is vacuously satisfied by nothing.

CREATE FUNCTION rk2_chain_problem(p_program uuid, p_members uuid[]) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_entry  text[];
    v_label  text;
    v_detail text;
    v_need   text;
    v_id     uuid;
    v_n      integer;
BEGIN
    -- Criterion 6's empty graph, and the reason it is a refusal rather than an
    -- answer: every rule below this one is a NOT EXISTS, and a NOT EXISTS over
    -- nothing is true. A chain of no members would pass integrity, pass
    -- soundness, and render as a claim that the harness proved something.
    IF p_members IS NULL OR cardinality(p_members) = 0 THEN
        RETURN 'a chain of no steps is not an empty chain, it is not a chain, '
               || 'and an empty graph is not a negative result';
    END IF;
    IF array_position(p_members, NULL) IS NOT NULL THEN
        RETURN 'the proposal names nothing in one of its places';
    END IF;

    -- A bound, for 035's reason: a claim nobody can read is not a claim. Eight
    -- capabilities is the most a single stamp may require, and sixteen steps is
    -- past the point where a reader is still following the argument.
    IF cardinality(p_members) > 16 THEN
        RETURN 'a chain of ' || cardinality(p_members) || ' steps is a story';
    END IF;

    -- Missing and cross-Program at once. `rk2_program_required` fences the
    -- caller and this predicate fences the read, so a stamp of another Program
    -- is simply not a stamp of this one -- the same sentence, because from
    -- here they are the same absence.
    SELECT m INTO v_id FROM unnest(p_members) AS named(m)
     WHERE NOT EXISTS (SELECT 1 FROM pivot_stamps s
                        WHERE s.id = named.m AND s.program_id = p_program)
     ORDER BY m LIMIT 1;
    IF v_id IS NOT NULL THEN
        RETURN 'no pivot stamp of this Program is recorded under ' || v_id;
    END IF;

    SELECT s.label INTO v_label
      FROM unnest(p_members) AS named(m) JOIN pivot_stamps s ON s.id = named.m
     GROUP BY s.label HAVING count(*) > 1
     ORDER BY s.label LIMIT 1;
    IF v_label IS NOT NULL THEN
        RETURN 'step ' || v_label || ' is named twice, and a step is one step';
    END IF;

    -- A chain of one is a stamp. There is a verb for reading one of those and
    -- it is not this one; what makes a chain a chain is that something in it
    -- was reached through something else in it.
    IF cardinality(p_members) < 2 THEN
        RETURN 'one stamp is a stamp, and a chain composes at least two';
    END IF;

    -- Vocabulary mismatch. Every stamp records the capability vocabulary it was
    -- issued under, and two stamps issued under two vocabularies may be using
    -- one word for two things -- which is the exact failure the vocabulary
    -- digest was put on the stamp to catch. Not "the current vocabulary":
    -- a chain of old stamps that agree with each other still composes, and 039
    -- deliberately does not go red when the vocabulary moves.
    SELECT count(DISTINCT s.vocabulary_sha256) INTO v_n
      FROM pivot_stamps s
     WHERE s.id = ANY (p_members) AND s.program_id = p_program;
    IF v_n > 1 THEN
        RETURN 'the steps were stamped under ' || v_n
               || ' capability vocabularies, and a chain composes words that mean one thing';
    END IF;

    -- Criterion 2's "backed by current pivot stamps". A stamp is a record of
    -- what was seen, and it stays true about that moment forever; whether the
    -- pivot would still be issued today is a different question, and 039 wrote
    -- the whole of it as one sentence. Asked here so that a chain cannot be
    -- built out of ground that has already moved, and asked again at every read
    -- so that ground moving afterwards is caught too.
    SELECT s.label, r.reason INTO v_label, v_detail
      FROM pivot_stamps s
      CROSS JOIN LATERAL (SELECT rk2_pivot_refusal(p_program, s.tool_run_id) AS reason) r
     WHERE s.id = ANY (p_members) AND s.program_id = p_program
       AND r.reason IS NOT NULL
     ORDER BY s.label LIMIT 1;
    IF v_label IS NOT NULL THEN
        RETURN 'step ' || v_label || ' no longer stands: ' || v_detail;
    END IF;

    v_id := rk2_chain_cycle(p_program, p_members);
    IF v_id IS NOT NULL THEN
        RETURN 'step ' || (SELECT label FROM pivot_stamps WHERE id = v_id)
               || ' is its own ancestor, and a chain that assumes what it '
               || 'concludes concludes nothing';
    END IF;

    -- Unsatisfied requirements. A step's `requires` is a list of capabilities
    -- the run needed to have before it could do what it did, and each of them
    -- was either brought by an earlier step or was there from the start. There
    -- is no third source: "we would have had it" is the word 039 removed.
    v_entry := rk2_chain_entry(p_program);
    SELECT s.label, need INTO v_label, v_need
      FROM pivot_stamps s
      CROSS JOIN LATERAL unnest(s.requires) AS wanted(need)
     WHERE s.id = ANY (p_members) AND s.program_id = p_program
       AND NOT (need = ANY (v_entry))
       AND NOT EXISTS (SELECT 1 FROM pivot_stamps u
                        WHERE u.id = ANY (p_members) AND u.program_id = p_program
                          AND u.provides = need)
     ORDER BY s.label, need LIMIT 1;
    IF v_label IS NOT NULL THEN
        RETURN 'step ' || v_label || ' requires ' || v_need
               || ', and no step provides it and the Program does not start with it';
    END IF;

    SELECT s.label INTO v_label
      FROM pivot_stamps s
     WHERE s.id = ANY (p_members) AND s.program_id = p_program
       AND NOT (s.id = ANY (rk2_chain_reached(p_program, p_members)))
     ORDER BY s.label LIMIT 1;
    IF v_label IS NOT NULL THEN
        RETURN 'step ' || v_label
               || ' is joined to nothing else here, so this is two chains';
    END IF;

    -- Ambiguous Identity flow. A step reached from two steps that ran as
    -- different Identities cannot say which session the capability arrived in,
    -- and the difference matters: a capability obtained as one account is not a
    -- capability the other account has. Fan-out is not this -- one Identity
    -- reaching two places is a branch, which criterion 6 asks to work -- and
    -- neither is a step running as somebody new, which is what most pivots are
    -- for. It is two parents disagreeing, and nothing in the graph choosing.
    SELECT d.label INTO v_label
      FROM rk2_chain_edges(p_program, p_members) e
      JOIN pivot_stamps u ON u.id = e.from_stamp
      JOIN pivot_stamps d ON d.id = e.to_stamp
     GROUP BY d.label
    HAVING count(DISTINCT u.identity_entity_id) > 1
     ORDER BY d.label LIMIT 1;
    IF v_label IS NOT NULL THEN
        RETURN 'step ' || v_label
               || ' is reached from steps that ran as different Identities, '
               || 'and the chain does not say which one carried it';
    END IF;

    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_chain_problem(uuid, uuid[]) IS
  'Ticket 40 criterion 3 and criterion 6''s empty graph as one list: the first reason this set of pivot stamps is not a chain, or NULL. Ordered so that each rule is asked of a graph the rules before it have already made sense of -- the empty graph first, because everything below it is vacuously true of nothing.';


-- ===========================================================================
-- 4. The chain
-- ===========================================================================

INSERT INTO label_prefixes (kind, prefix) VALUES ('chains', 'KC');

CREATE TABLE chains (
    id         uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label      text NOT NULL DEFAULT '',
    -- At least one, because a chain that starts from nothing could not have
    -- taken its first step. No ceiling here: the real bound is "fewer than the
    -- whole vocabulary", which is a count a CHECK may not read, so it is next
    -- to the other rule about `entry` that has to be a trigger for the same
    -- reason. A number copied from `pivot_stamps.requires` would be a bound
    -- whose rationale does not transfer.
    entry      text[] NOT NULL CHECK (cardinality(entry) >= 1),
    vocabulary_sha256 char(64) NOT NULL CHECK (vocabulary_sha256 ~ '^[0-9a-f]{64}$'),
    source     jsonb NOT NULL,
    source_sha256 char(64) NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    built_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, program_id),
    UNIQUE (program_id, label),
    -- One chain per body of evidence, so building the same chain twice has
    -- nowhere to put a second row.
    UNIQUE (program_id, source_sha256),
    CHECK (source_sha256 = equivalence_key(source)),
    -- 039's rule, restated: a column the digest does not defend is the only
    -- kind of column worth moving. `members` has no column here because the
    -- membership is the `chain_steps` rows, and those carry their own keys.
    CHECK (source -> 'entry' = to_jsonb(entry)
           AND source ->> 'vocabulary' = vocabulary_sha256)
);

COMMENT ON TABLE chains IS
  'Ticket 40: one composition of pivot stamps, identified by the digest of its members'' digests. It carries no verdict, deliberately: whether the chain is sound is asked at every read, because a stored answer is right until the day it matters.';

COMMENT ON COLUMN chains.entry IS
  'The capabilities this Program offered without a step when the chain was built. Recorded rather than recomputed at read time so that a Program which stops offering one makes its chains explicitly unsound instead of quietly reinterpreting them.';

COMMENT ON COLUMN chains.source IS
  'What `source_sha256` is the digest of: the members'' own digests in one order, the entry capabilities and the vocabulary. A hash of hashes -- a stamp''s digest already covers everything it rests on -- so a chain''s identity covers the whole tree beneath it, and the order the members were proposed in is not part of it.';

CREATE TRIGGER chains_assign_label BEFORE INSERT ON chains
    FOR EACH ROW EXECUTE FUNCTION assign_label();

CREATE TRIGGER chains_immutable BEFORE UPDATE OR DELETE ON chains
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

-- `entry` is two words out of a vocabulary a CHECK may not read: a CHECK may
-- only call IMMUTABLE functions and reading a table is not immutable. The same
-- rule at the same moment through the other mechanism this schema has for it,
-- which is what 039 did with `apply_pivot_claim`. Canonical order as well as
-- membership, because the array is inside the digest and two orders of one set
-- would be two chains. And the ceiling the CHECK could not state: a chain that
-- starts from the whole vocabulary needs no step to obtain anything, so every
-- requirement is satisfied for free and the composition proves nothing --
-- which is the file header's argument about a chain naming its own entry set,
-- enforced rather than only argued.
CREATE FUNCTION enforce_chain_entry() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE v_word text;
BEGIN
    SELECT word INTO v_word FROM unnest(NEW.entry) AS assumed(word)
     WHERE NOT EXISTS (SELECT 1 FROM capabilities c WHERE c.capability = assumed.word);
    IF v_word IS NOT NULL THEN
        RAISE EXCEPTION 'a chain cannot start from %, which is not a capability', v_word;
    END IF;
    IF NEW.entry <> ARRAY(SELECT DISTINCT word FROM unnest(NEW.entry) AS assumed(word)
                           ORDER BY word) THEN
        RAISE EXCEPTION 'the entry capabilities are inside the digest and are not in order';
    END IF;
    IF cardinality(NEW.entry) >= (SELECT count(*) FROM capabilities) THEN
        RAISE EXCEPTION 'a chain that starts from every capability obtains none of them';
    END IF;
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION enforce_chain_entry() IS
  'Ticket 40: the three rules about a chain''s entry capabilities that a CHECK constraint may not state, because all three read the capability vocabulary and a CHECK may only call IMMUTABLE functions. Every word is a capability, the array is in canonical order because it is inside the digest, and the set is smaller than the vocabulary because a chain that assumes everything obtains nothing.';

CREATE TRIGGER chains_entry_is_vocabulary BEFORE INSERT ON chains
    FOR EACH ROW EXECUTE FUNCTION enforce_chain_entry();

-- The membership. One row per stamp, and nothing of the stamp copied onto it:
-- a stamp is immutable and carries every column a reader could want, so a copy
-- here would be a second place for the same fact to live.
CREATE TABLE chain_steps (
    id         uuid PRIMARY KEY DEFAULT uuidv7(),
    chain_id   uuid NOT NULL,
    program_id uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    stamp_id   uuid NOT NULL,
    depth      integer NOT NULL CHECK (depth >= 0),
    UNIQUE (id, program_id),
    -- The target of both edge keys below, which is what makes an edge between
    -- two steps of different chains a foreign-key violation rather than a rule.
    -- One stamp appears in a chain once: `program_id` is functionally dependent
    -- on `chain_id` through the key below it, so this is the two-column
    -- uniqueness as well.
    UNIQUE (chain_id, stamp_id, program_id),
    FOREIGN KEY (chain_id, program_id) REFERENCES chains (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (stamp_id, program_id) REFERENCES pivot_stamps (id, program_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE chain_steps IS
  'Ticket 40: which pivot stamps a chain is composed of, and how deep into it each one sits. Depth rather than an ordinal, because a branch puts two steps in the same place and an ordinal would have to invent an order between them.';

CREATE TRIGGER chain_steps_immutable BEFORE UPDATE OR DELETE ON chain_steps
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

-- The edges, which are what criterion 1 says no agent may write. Derived by
-- `rk2_chain_edges` and stored so a reader can join rather than recompute; the
-- standing check asks whether the stored rows still say what the stamps say.
CREATE TABLE chain_edges (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    chain_id      uuid NOT NULL,
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    from_stamp_id uuid NOT NULL,
    to_stamp_id   uuid NOT NULL,
    capability    text NOT NULL REFERENCES capabilities(capability),
    UNIQUE (id, program_id),
    UNIQUE (chain_id, from_stamp_id, to_stamp_id, capability),
    CHECK (from_stamp_id <> to_stamp_id),
    -- The stamp first and the chain second, though the key is over all three:
    -- 016 registers a cascading edge by the *first* column of its constraint,
    -- and two keys both beginning `chain_id` would be one registration
    -- covering both ends. Named this way each end declares itself.
    FOREIGN KEY (from_stamp_id, chain_id, program_id)
        REFERENCES chain_steps (stamp_id, chain_id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (to_stamp_id, chain_id, program_id)
        REFERENCES chain_steps (stamp_id, chain_id, program_id) ON DELETE CASCADE
);

COMMENT ON TABLE chain_edges IS
  'Ticket 40 criterion 2: one row per capability that passes from one step of a chain to another, derived from the stamps'' own `provides` and `requires`. Both ends are keyed to `chain_steps`, so an edge into a stamp that is not a member of the same chain is a foreign-key violation.';

CREATE INDEX chain_edges_to_idx ON chain_edges (chain_id, to_stamp_id);

CREATE TRIGGER chain_edges_immutable BEFORE UPDATE OR DELETE ON chain_edges
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

-- Every attempt, kept, on 036's and 039's pattern. This one carries more than
-- the outcome: it carries what the agent proposed, which is the only place that
-- claim survives. The chain is what the stamps say, so a proposal that named
-- the members in the wrong order or claimed a flow that is not there builds the
-- same chain as one that got it right -- and the difference between the two is
-- worth reading, because it is how well the model understood its own evidence.
CREATE TABLE chain_proposals (
    id           uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id   uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    agent_run_id uuid,
    members      uuid[] NOT NULL,
    flow         jsonb,
    outcome      text NOT NULL CHECK (outcome IN ('built', 'repeated', 'refused')),
    refusal      text,
    chain_id     uuid,
    at           timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (agent_run_id, program_id) REFERENCES agent_runs (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (chain_id, program_id) REFERENCES chains (id, program_id)
        ON DELETE CASCADE,
    CHECK ((outcome = 'refused') = (refusal IS NOT NULL)),
    CHECK ((outcome = 'refused') = (chain_id IS NULL))
);

COMMENT ON TABLE chain_proposals IS
  'Ticket 40 criterion 1: one row per attempt to build a chain, carrying the member order and capability flow the agent proposed and the chain or the sentence the runtime answered with. Beside the chains and reachable from none of them: the edge runs the other way.';

COMMENT ON COLUMN chain_proposals.members IS
  'The stamps the proposal named, in the order it named them, and not a foreign key -- a proposal naming a stamp that does not exist or belongs to another Program is one of the things the refusal is for, and a key here would refuse the record of the refusal.';

COMMENT ON COLUMN chain_proposals.flow IS
  'What the agent said the capabilities do between its members. Recorded and never read: where a capability goes is a question the stamps answer, and this column exists so that a wrong answer leaves a trace rather than disappearing into a correct chain.';

CREATE INDEX chain_proposals_program_idx ON chain_proposals (program_id, at DESC);

CREATE TRIGGER chain_proposals_immutable BEFORE UPDATE OR DELETE ON chain_proposals
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();


-- ===========================================================================
-- 5. Building one
-- ===========================================================================
--
-- Criterion 1, as a signature. What comes in is a set of stamps and a story
-- about them; what goes out is a graph the caller had no say in. The story is
-- written to `chain_proposals` and read by nothing.

CREATE FUNCTION build_kill_chain(p_members uuid[],
                                 p_flow jsonb DEFAULT NULL,
                                 p_agent_run_id uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    v_members uuid[] := coalesce(p_members, '{}'::uuid[]);
    v_refusal text;
    v_entry   text[];
    v_source  jsonb;
    v_sha     text;
    v_chain   chains%ROWTYPE;
    v_repeat  boolean := false;
BEGIN
    v_refusal := rk2_chain_problem(p, v_members);
    IF v_refusal IS NOT NULL THEN
        PERFORM set_actor('runtime');
        INSERT INTO chain_proposals (program_id, agent_run_id, members, flow,
                                     outcome, refusal)
        VALUES (p, p_agent_run_id, v_members, p_flow, 'refused', v_refusal);
        RETURN jsonb_build_object('chain', NULL, 'refusal', v_refusal);
    END IF;

    v_entry  := rk2_chain_entry(p);
    -- The members go in as their own digests and in digest order, so the
    -- identity of a chain is the identity of its evidence and not of the
    -- sentence somebody wrote about it. Two agents proposing these stamps in
    -- two orders build one chain.
    v_source := jsonb_build_object(
        'members', (SELECT jsonb_agg(s.source_sha256 ORDER BY s.source_sha256)
                      FROM pivot_stamps s
                     WHERE s.id = ANY (v_members) AND s.program_id = p),
        'entry', to_jsonb(v_entry),
        'vocabulary', rk2_capability_vocabulary_sha256());
    v_sha := equivalence_key(v_source);

    SELECT * INTO v_chain FROM chains WHERE program_id = p AND source_sha256 = v_sha;
    v_repeat := FOUND;

    IF NOT v_repeat THEN
        PERFORM set_actor('runtime');
        INSERT INTO chains (program_id, entry, vocabulary_sha256, source, source_sha256)
        VALUES (p, v_entry, v_source ->> 'vocabulary', v_source, v_sha)
        RETURNING * INTO v_chain;

        INSERT INTO chain_steps (chain_id, program_id, stamp_id, depth)
        SELECT v_chain.id, p, d.of_stamp, d.at_depth
          FROM rk2_chain_depths(p, v_members) d;

        INSERT INTO chain_edges (chain_id, program_id, from_stamp_id, to_stamp_id,
                                 capability)
        SELECT v_chain.id, p, e.from_stamp, e.to_stamp, e.capability
          FROM rk2_chain_edges(p, v_members) e;
    END IF;

    PERFORM set_actor('runtime');
    INSERT INTO chain_proposals (program_id, agent_run_id, members, flow,
                                 outcome, chain_id)
    VALUES (p, p_agent_run_id, v_members, p_flow,
            CASE WHEN v_repeat THEN 'repeated' ELSE 'built' END, v_chain.id);

    RETURN jsonb_build_object(
        'chain', v_chain.label, 'refusal', NULL, 'built', NOT v_repeat,
        'entry', to_jsonb(v_chain.entry),
        'steps', (SELECT count(*) FROM chain_steps WHERE chain_id = v_chain.id),
        'edges', (SELECT count(*) FROM chain_edges WHERE chain_id = v_chain.id),
        'source_sha256', v_chain.source_sha256);
END $fn$;

COMMENT ON FUNCTION build_kill_chain(uuid[], jsonb, uuid) IS
  'Ticket 40 criteria 1 to 3: compose a set of pivot stamps into a chain, or record why they are not one. The caller proposes members and a flow; the runtime derives the edges from the stamps and stores its own. Idempotent by the digest of the members'' digests.';


-- ===========================================================================
-- 6. Staying sound
-- ===========================================================================
--
-- Criteria 4 and 5. Building a chain answered "is this a chain"; this answers
-- "is it still one", and the two are different questions because everything
-- underneath a chain can move after it is built.
--
-- Most of the list is 039's sentence, asked once per step: whether a pivot
-- would still be issued today is already the whole of member validation, Test
-- runs, Artifacts, Receipts and grants, and wording it a second time here would
-- be two rules pretending to be one. What is added is what a chain has and a
-- stamp does not -- the scope it is read in, the Identities it leans on, the
-- capabilities it assumed at the start, and the review gates on its members.

CREATE FUNCTION rk2_chain_unsoundness(p_program uuid, p_chain uuid) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_chain  chains%ROWTYPE;
    v_label  text;
    v_detail text;
    v_need   text;
    v_n      integer;
BEGIN
    SELECT * INTO v_chain FROM chains WHERE id = p_chain AND program_id = p_program;
    IF NOT FOUND THEN
        RETURN 'no chain of this Program is recorded under that id';
    END IF;

    -- (a) Criterion 5, and most of criterion 4. A member withdrawn, a run
    --     re-read as refuting, an Artifact retired, a Receipt gone, a grant
    --     expired: every one of them is a reason 039 already words, and every
    --     one of them makes the step it is about stop being a demonstration.
    SELECT s.label, r.reason INTO v_label, v_detail
      FROM chain_steps cs
      JOIN pivot_stamps s ON s.id = cs.stamp_id
      CROSS JOIN LATERAL (SELECT rk2_pivot_refusal(p_program, s.tool_run_id) AS reason) r
     WHERE cs.chain_id = p_chain AND r.reason IS NOT NULL
     ORDER BY cs.depth, s.label LIMIT 1;
    IF v_label IS NOT NULL THEN
        RETURN 'step ' || v_label || ' no longer stands: ' || v_detail;
    END IF;

    -- (b) The start. A chain assumed the Program offered something without a
    --     step; if it no longer does, the first step is standing on nothing.
    --     This is where an invalidated Identity is felt at the head of the
    --     chain -- 012 invalidates an Identity the configuration stopped
    --     declaring, and `authenticated_session` stops being free the moment
    --     the last live one goes.
    SELECT assumed.word INTO v_need
      FROM unnest(v_chain.entry) AS assumed(word)
     WHERE NOT (assumed.word = ANY (rk2_chain_entry(p_program)))
     ORDER BY assumed.word LIMIT 1;
    IF v_need IS NOT NULL THEN
        RETURN 'the chain starts from ' || v_need
               || ' and this Program no longer offers it without a step';
    END IF;

    -- (c) Invalidations, in the middle of the chain rather than at its head.
    --     A step went out as one Identity; if that Identity has been
    --     invalidated the capability it carried cannot be shown again.
    --
    --     Before the scope version and not after it, which is the one place in
    --     this list where the order is a decision rather than a reading order.
    --     012 invalidates an Identity when the configuration stops declaring
    --     it, and a configuration the operator changed is a configuration whose
    --     policy is recorded again -- so *every* withdrawn Identity arrives
    --     with a moved scope version behind it. Asked the other way round, this
    --     sentence would be unreachable and an operator who took a session away
    --     would be told the document moved.
    SELECT s.label, i.slot_name INTO v_label, v_detail
      FROM chain_steps cs
      JOIN pivot_stamps s ON s.id = cs.stamp_id
      JOIN identities i ON i.entity_id = s.identity_entity_id
     WHERE cs.chain_id = p_chain AND i.invalidated_at IS NOT NULL
     ORDER BY cs.depth, s.label LIMIT 1;
    IF v_label IS NOT NULL THEN
        RETURN 'step ' || v_label || ' went out as identity ' || v_detail
               || ', which has been invalidated';
    END IF;

    -- (d) Scope, which a stamp records and a Program moves. A capability
    --     obtained under one scope document is not a capability obtained under
    --     the next one: the operator changed what may be touched, and a claim
    --     made before that change has not been re-made after it.
    SELECT pr.scope_version INTO v_n FROM programs pr WHERE pr.id = p_program;
    IF v_n IS NOT NULL THEN
        SELECT s.label, s.scope_version::text INTO v_label, v_detail
          FROM chain_steps cs JOIN pivot_stamps s ON s.id = cs.stamp_id
         WHERE cs.chain_id = p_chain AND s.scope_version <> v_n
         ORDER BY cs.depth, s.label LIMIT 1;
        IF v_label IS NOT NULL THEN
            RETURN 'step ' || v_label || ' was obtained under scope version '
                   || v_detail || ' and this Program is now at version ' || v_n;
        END IF;
    END IF;

    -- (e) Scope again, at the other end: the subject itself. 021 projects the
    --     class rather than deleting the entity, and a step against a subject
    --     the policy now denies is a step nobody may re-run.
    --
    --     `denied` and not `NOT in_scope`, which are different questions. 021
    --     has a fourth class for an entity that has no address at all -- an
    --     identity slot, a technology fingerprint -- and its own comment says
    --     why: those are not a scope question, and they are out of scope only
    --     in the sense that nothing may be sent *to* them. A Finding about a
    --     technology has a subject like that, and reading the boolean would
    --     make every chain composed on one permanently unsound for a reason
    --     that is not about scope at all.
    SELECT s.label INTO v_label
      FROM chain_steps cs
      JOIN pivot_stamps s ON s.id = cs.stamp_id
      JOIN entities e ON e.id = s.subject_entity_id
     WHERE cs.chain_id = p_chain AND e.scope_class = 'denied'
     ORDER BY cs.depth, s.label LIMIT 1;
    IF v_label IS NOT NULL THEN
        RETURN 'the subject of step ' || v_label || ' is no longer in scope';
    END IF;

    -- (f) Review gates. 034 and 038 registered the codes that hold a Finding
    --     unrenderable, and a chain is at most as reportable as its weakest
    --     member. Named one by one rather than as "every hard code except", and
    --     that direction is the decision here: an inclusion list makes a new
    --     blocker code inert until somebody says it bears on a chain, and an
    --     exclusion list makes every code anyone adds later a reason to call
    --     chains built years ago unsound. Only two of the eight are asked.
    --
    --     `known_issue` and `duplicate` are the gates where somebody decided
    --     this Finding may not be carried -- the Program said in writing it
    --     does not want the class, or it is the same signature as one already
    --     validated or reported. A chain composed on either is a chain that
    --     cannot be put in front of the Program, whatever its pivots prove.
    --
    --     The other six are not, and the reasons differ.
    --
    --     `not_validated` is the one worth spelling out, because it is *not*
    --     arm (a) restated and the two deliberately disagree. 039 admits a
    --     member that is `validated` or `reported` -- a Finding somebody wrote
    --     up is not a Finding somebody withdrew -- while `report_blockers`
    --     holds anything other than `validated`, because 034 is about
    --     rendering that Finding's own report and one already reported must
    --     not be sent twice. Both are right about their own question. Reading
    --     034's answer here would make a chain go unsound the moment its
    --     strongest member was submitted, which is the moment the chain is
    --     most worth having.
    --
    --     `no_effect`, `no_chain` and `unwitnessed_effect` are about the v1
    --     report rows, which is 042's work: a gate no Finding in this corpus
    --     can pass yet reports nothing about the one in front of it.
    --     `cvss_stale` and `severity_unstated` are about the severity band --
    --     how bad it is, and on whose word -- and a chain's soundness is the
    --     question of whether the transitions hold, which is not a question
    --     about the number beside them. Those two still stop the *report*: 034
    --     reads the blockers itself, so a member with an unstated severity is
    --     unrenderable there and sound here, which is the honest pair of
    --     answers rather than one answer twice.
    SELECT f.label, b.code || ': ' || b.detail INTO v_label, v_detail
      FROM chain_steps cs
      JOIN pivot_stamps s ON s.id = cs.stamp_id
      JOIN findings f ON f.id = s.finding_id
      CROSS JOIN LATERAL report_blockers(f.id) b
     WHERE cs.chain_id = p_chain AND b.severity = 'hard'
       AND b.code IN ('known_issue', 'duplicate')
     ORDER BY cs.depth, f.label, b.code LIMIT 1;
    IF v_label IS NOT NULL THEN
        RETURN 'member ' || v_label || ' is held by a review gate -- ' || v_detail;
    END IF;

    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_chain_unsoundness(uuid, uuid) IS
  'Ticket 40 criteria 4 and 5: the first reason this chain is not reportable now, or NULL. Every step is asked 039''s own question -- would this pivot still be issued today -- and the chain is asked the four a chain has of its own: the capabilities it started from, the scope it was read in, the Identities it leaned on and the review gates on its members.';


-- ===========================================================================
-- 7. The reportable read
-- ===========================================================================
--
-- Criterion 5's "unrenderable". An unsound chain answers with the reason and
-- nothing else -- no steps, no edges, nothing a renderer could put in front of
-- a human -- and every row it was built from stays exactly where it was. The
-- history of a chain that stopped being true is the most useful history there
-- is: it is the record of what the harness believed and what changed.

CREATE FUNCTION read_kill_chain(p_chain uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    v_chain chains%ROWTYPE;
    v_why   text;
BEGIN
    SELECT * INTO v_chain FROM chains WHERE id = p_chain AND program_id = p;
    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'chain', NULL, 'sound', false,
            'unsound', 'no chain of this Program is recorded under that id');
    END IF;

    v_why := rk2_chain_unsoundness(p, p_chain);
    IF v_why IS NOT NULL THEN
        RETURN jsonb_build_object('chain', v_chain.label, 'sound', false,
                                  'unsound', v_why, 'steps', NULL, 'edges', NULL);
    END IF;

    RETURN jsonb_build_object(
        'chain', v_chain.label, 'sound', true, 'unsound', NULL,
        'entry', to_jsonb(v_chain.entry),
        'steps', (SELECT jsonb_agg(jsonb_build_object(
                             'stamp', s.label, 'depth', cs.depth,
                             'member', f.label, 'subject', e.label,
                             'identity', i.slot_name, 'provides', s.provides,
                             'requires', to_jsonb(s.requires),
                             'conditions', s.conditions)
                         ORDER BY cs.depth, s.label)
                    FROM chain_steps cs
                    JOIN pivot_stamps s ON s.id = cs.stamp_id
                    JOIN findings f ON f.id = s.finding_id
                    JOIN entities e ON e.id = s.subject_entity_id
                    JOIN identities i ON i.entity_id = s.identity_entity_id
                   WHERE cs.chain_id = p_chain),
        'edges', (SELECT jsonb_agg(jsonb_build_object(
                             'from', u.label, 'to', d.label,
                             'capability', ce.capability)
                         ORDER BY u.label, d.label, ce.capability)
                    FROM chain_edges ce
                    JOIN pivot_stamps u ON u.id = ce.from_stamp_id
                    JOIN pivot_stamps d ON d.id = ce.to_stamp_id
                   WHERE ce.chain_id = p_chain));
END $fn$;

COMMENT ON FUNCTION read_kill_chain(uuid) IS
  'Ticket 40 criteria 4 and 5: a chain as something a reader may act on, or the sentence saying why it is not one any more. An unsound chain answers with the reason and no steps and no edges, and keeps every row it was built from.';


-- ===========================================================================
-- 8. Wiring: events, purge, isolation, grants
-- ===========================================================================

INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('chain.built', 'row', 'chains',
     'the runtime composed pivot stamps into a chain and derived the edges between them');

INSERT INTO event_table_config (table_name, created_type) VALUES
    ('chains', 'chain.built');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('chain_steps', 'derived',
     'the membership of a chain, recomputable from the chain''s own source digest and the stamps it names; the chain it belongs to emits', '40'),
    ('chain_edges', 'derived',
     'the edges between a chain''s steps, recomputable from those steps'' provides and requires; the chain they belong to emits', '40'),
    ('chain_proposals', 'audit',
     'the append-only record of what was proposed and what was answered; only the built outcome has an Event of its own, and a refused or repeated attempt writes no canonical row for one to be about', '40');

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('chains', 'program_id',
     'program-scoped: the purge root'),
    ('chain_steps', 'program_id',
     'program-scoped: the purge root'),
    ('chain_steps', 'chain_id',
     'ON DELETE CASCADE to chains: a step of a chain that is gone'),
    ('chain_steps', 'stamp_id',
     'ON DELETE CASCADE to pivot_stamps: a step whose demonstration is gone'),
    ('chain_edges', 'program_id',
     'program-scoped: the purge root'),
    ('chain_edges', 'from_stamp_id',
     'ON DELETE CASCADE to chain_steps: the step the capability came from'),
    ('chain_edges', 'to_stamp_id',
     'ON DELETE CASCADE to chain_steps: the step the capability went to'),
    ('chain_proposals', 'program_id',
     'program-scoped: the purge root'),
    ('chain_proposals', 'agent_run_id',
     'ON DELETE CASCADE to agent_runs: the run that proposed'),
    ('chain_proposals', 'chain_id',
     'ON DELETE CASCADE to chains: the chain the proposal reached');

SELECT attach_event_triggers();
SELECT attach_actor_kind_guards();

GRANT SELECT, INSERT ON chains, chain_steps, chain_edges, chain_proposals
    TO rk2_runtime;
GRANT SELECT ON chains, chain_steps, chain_edges, chain_proposals TO rk2_human;

-- 029's default privileges hand every new table the four verbs to `rk2_runtime`,
-- so an append-only table has to say so. The trigger already refuses the
-- statement; this stops it being attempted, which is the difference between
-- "the row did not change" and "the role cannot change rows".
REVOKE UPDATE, DELETE ON TABLE chains, chain_steps, chain_edges, chain_proposals
    FROM rk2_runtime;
REVOKE ALL ON TABLE chains, chain_steps, chain_edges, chain_proposals
    FROM rk2_proxy, rk2_state;

REVOKE ALL ON FUNCTION rk2_chain_entry(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_chain_edges(uuid, uuid[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_chain_depths(uuid, uuid[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_chain_cycle(uuid, uuid[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_chain_reached(uuid, uuid[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_chain_problem(uuid, uuid[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_chain_unsoundness(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION build_kill_chain(uuid[], jsonb, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION read_kill_chain(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION enforce_chain_entry() FROM PUBLIC;

GRANT EXECUTE ON FUNCTION rk2_chain_entry(uuid) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION rk2_chain_edges(uuid, uuid[]) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION rk2_chain_depths(uuid, uuid[]) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_chain_cycle(uuid, uuid[]) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_chain_reached(uuid, uuid[]) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_chain_problem(uuid, uuid[]) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION rk2_chain_unsoundness(uuid, uuid) TO rk2_runtime, rk2_human;
-- The verb is the runtime's and the read is everyone's who may see a Program.
-- An operator reading a chain it cannot build is the whole point of criterion 1.
GRANT EXECUTE ON FUNCTION build_kill_chain(uuid[], jsonb, uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION read_kill_chain(uuid) TO rk2_runtime, rk2_human;

SELECT apply_state_rls();
SELECT apply_state_grants();
SELECT enforce_always_triggers();


-- ===========================================================================
-- 9. The standing check
-- ===========================================================================
--
-- What is true of the corpus rather than of one read. `rk2_chain_unsoundness`
-- asks whether a chain is still true of the world; this asks whether the stored
-- graph still says what the stamps under it say, which is a question about this
-- migration rather than about the target.
--
-- Four of the seven arms name a rule `rk2_chain_problem` also names -- fewer
-- than two steps, two vocabularies, an unsupplied requirement, a cycle -- and
-- section 3 said in as many words that a rule worded twice is two rules on the
-- day one is edited. The difference is what they are asked *of*. The builder
-- reads a proposal and derives a graph from stamps; these read the rows that
-- were written, and a row is not a proposal. Nothing this migration exposes can
-- put a stored graph out of step with its stamps -- the four tables take
-- INSERT and nothing else -- so every one of these arms is about rows that
-- arrived some other way: a restore, a partial purge, a hand-written repair, a
-- later migration. That is the whole job of a standing check, and it is why
-- these cannot be delegated to `rk2_chain_problem` even where the sentence
-- would read the same: that function would re-derive the edges from the stamps
-- and answer about the graph that *should* be there, which is exactly the
-- graph these arms are not asking about.

CREATE FUNCTION check_kill_chains()
RETURNS TABLE (problem text, detail text) LANGUAGE sql STABLE AS $fn$
    WITH RECURSIVE walk AS (
        SELECT e.chain_id, e.from_stamp_id AS root, e.to_stamp_id AS at
          FROM chain_edges e
         UNION ALL
        SELECT w.chain_id, w.root, e.to_stamp_id
          FROM walk w
          JOIN chain_edges e ON e.chain_id = w.chain_id AND e.from_stamp_id = w.at
    ) CYCLE at SET looped USING trail
    -- (a) a chain whose digest no longer covers what it says
    SELECT 'chain_digest_disagrees_with_its_source'::text, c.label
      FROM chains c WHERE c.source_sha256 <> equivalence_key(c.source)
UNION ALL
    -- (b) criterion 6's empty graph, asked of the corpus. A chain of fewer than
    --     two steps is the row a vacuous soundness answer would be about, and
    --     the one shape of this table that would make every rule below it true.
    SELECT 'chain_composes_fewer_than_two_steps', c.label
      FROM chains c
     WHERE (SELECT count(*) FROM chain_steps cs WHERE cs.chain_id = c.id) < 2
UNION ALL
    -- (c) criterion 2: a stored edge the stamps do not agree with. The edges are
    --     derived once and read many times, so this is the question of whether
    --     what was derived is still what would be derived.
    SELECT 'chain_edge_is_not_what_the_stamps_say', c.label || ' ' || e.capability
      FROM chain_edges e
      JOIN chains c ON c.id = e.chain_id
      JOIN pivot_stamps u ON u.id = e.from_stamp_id
      JOIN pivot_stamps d ON d.id = e.to_stamp_id
     WHERE u.provides <> e.capability OR NOT (e.capability = ANY (d.requires))
UNION ALL
    -- (d) criterion 3's vocabulary mismatch, as a corpus fact
    SELECT 'chain_composes_two_vocabularies', c.label
      FROM chains c JOIN chain_steps cs ON cs.chain_id = c.id
      JOIN pivot_stamps s ON s.id = cs.stamp_id
     GROUP BY c.label
    HAVING count(DISTINCT s.vocabulary_sha256) > 1
UNION ALL
    -- (e) criterion 1: a chain no `chain.built` Event attributes to the runtime.
    --     026's guard makes an actor authentic at the moment of writing; this
    --     asks after the fact, so a chain whose Event says something else and a
    --     chain with no Event are one answer.
    SELECT 'chain_was_not_built_by_the_runtime', c.label
      FROM chains c
     WHERE NOT EXISTS (SELECT 1 FROM events ev
                        WHERE ev.subject_id = c.id
                          AND ev.type = 'chain.built'
                          AND ev.actor_kind = 'runtime')
UNION ALL
    -- (f) criterion 3: a step requiring a capability nothing in its own chain
    --     brings it and the chain did not start with. The stored counterpart of
    --     the rule the builder refuses on, asked of the rows rather than of the
    --     proposal, because a chain whose requirements stopped being covered is
    --     a chain that composes over a gap.
    SELECT 'chain_step_requires_what_nothing_supplies',
           c.label || ' ' || s.label || ' ' || wanted.need
      FROM chain_steps cs
      JOIN chains c ON c.id = cs.chain_id
      JOIN pivot_stamps s ON s.id = cs.stamp_id
      CROSS JOIN LATERAL unnest(s.requires) AS wanted(need)
     WHERE NOT (wanted.need = ANY (c.entry))
       AND NOT EXISTS (SELECT 1 FROM chain_edges e
                        WHERE e.chain_id = cs.chain_id
                          AND e.to_stamp_id = cs.stamp_id
                          AND e.capability = wanted.need)
UNION ALL
    -- (g) criterion 3's cycle, asked of the stored edges. The builder refuses
    --     one and nothing edits an edge afterwards, so a cycle here is a row
    --     that did not come through the verb.
    SELECT DISTINCT 'chain_contains_a_cycle', c.label
      FROM walk w JOIN chains c ON c.id = w.chain_id
     WHERE w.root = w.at
$fn$;

COMMENT ON FUNCTION check_kill_chains() IS
  'Ticket 40. Everything about a chain that is true of the corpus rather than of one read: every chain digests to what it says, composes at least two steps under one vocabulary, was built by the runtime, has edges the stamps still agree with, has no step requiring what nothing supplies, and contains no cycle.';

REVOKE ALL ON FUNCTION check_kill_chains() FROM PUBLIC, rk2_state, rk2_proxy;
GRANT EXECUTE ON FUNCTION check_kill_chains() TO rk2_runtime, rk2_human;

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('check_kill_chains',
     'SELECT * FROM check_kill_chains()',
     '40',
     'A chain is composed and stays sound: every chain digests to its own source, composes at least two steps under one capability vocabulary, was built by the runtime, carries edges the stamps still agree with, leaves no step requiring what nothing in the chain supplies, and contains no cycle.');


-- ===========================================================================
-- 10. What this migration asserts about itself
-- ===========================================================================

DO $$
DECLARE n integer; v text;
BEGIN
    -- Criterion 1, as the shortest proof there is: no table this migration
    -- writes has a column an agent could put a verdict in.
    SELECT count(*) INTO n FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name IN ('chains', 'chain_steps', 'chain_edges')
       AND column_name IN ('sound', 'unsound', 'verdict', 'reportable', 'status');
    IF n > 0 THEN
        RAISE EXCEPTION 'a chain stores % verdict columns, and a stored verdict goes stale', n;
    END IF;

    -- And the other half of criterion 1: an executing role reaches none of the
    -- canonical tables. `rk2_state` is the whole write surface of a model.
    SELECT string_agg(g.role || ' holds ' || g.privilege || ' on ' || g.tab, ', ')
      INTO v
      FROM (VALUES ('rk2_state'), ('rk2_proxy')) AS r(role),
           (VALUES ('chains'), ('chain_steps'), ('chain_edges')) AS t(tab),
           (VALUES ('INSERT'), ('UPDATE'), ('DELETE')) AS p(privilege)
      CROSS JOIN LATERAL (SELECT r.role, p.privilege, t.tab) g
     WHERE has_table_privilege(r.role, t.tab, p.privilege);
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'an agent can write a canonical chain row: %', v;
    END IF;

    -- Criterion 3's entry rule is derived rather than declared, which is only
    -- true while nothing lets a caller name one. `build_kill_chain` takes
    -- members, a flow and a run, and if a fourth argument ever arrives this
    -- assertion is the place to think about what it means.
    SELECT count(*) INTO n FROM pg_proc
     WHERE proname = 'build_kill_chain' AND pronargs = 3;
    IF n <> 1 THEN
        RAISE EXCEPTION 'build_kill_chain takes arguments this ticket did not give it';
    END IF;
    SELECT prosrc INTO v FROM pg_proc WHERE proname = 'build_kill_chain';
    IF v NOT LIKE '%rk2_chain_entry(p)%' THEN
        RAISE EXCEPTION 'the builder does not read the entry capabilities off the Program';
    END IF;

    -- Criterion 4 is 039's sentence asked again rather than worded again. Two
    -- copies of "the grant is no longer live" would be two rules on the day one
    -- of them was edited.
    SELECT prosrc INTO v FROM pg_proc WHERE proname = 'rk2_chain_unsoundness';
    IF v NOT LIKE '%rk2_pivot_refusal%' THEN
        RAISE EXCEPTION 'a chain rechecks its steps with a second copy of 039''s list';
    END IF;

    -- Nothing edits a chain, and nothing below the owner may try.
    SELECT string_agg(t.tab, ', ') INTO v
      FROM (VALUES ('chains'), ('chain_steps'), ('chain_edges'),
                   ('chain_proposals')) AS t(tab)
     WHERE NOT EXISTS (SELECT 1 FROM pg_trigger
                        WHERE tgrelid = t.tab::regclass
                          AND tgname = t.tab || '_immutable');
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'a chain can be rewritten after it was built: %', v;
    END IF;

    -- An edge whose ends are not both steps of its own chain is the shape a
    -- disconnected member would be smuggled in as, and it is a key rather than
    -- a rule. Two of them, one per end.
    SELECT count(*) INTO n FROM pg_constraint
     WHERE conrelid = 'chain_edges'::regclass AND contype = 'f'
       AND confrelid = 'chain_steps'::regclass;
    IF n <> 2 THEN
        RAISE EXCEPTION 'an edge of a chain can name a stamp that is not a step of it';
    END IF;
END $$;
