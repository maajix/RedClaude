-- ===========================================================================
-- Production harness 83 -- a Program opens the first Task of its own scope
-- ===========================================================================
-- Ticket 82 made the Agent boundary satisfiable, and the first thing an
-- operator met on the other side of it was an empty slate: `rk run` reached the
-- scheduler, found no Task ready, and stopped. `execution.Slice._pass` is right
-- to stop -- an empty slate ends the pass before the orchestrator session is
-- opened, so nothing is started and nothing is spent -- but the queue it was
-- reading had no way of ever holding anything. Every production
-- `INSERT INTO tasks` in this schema is downstream of a Finding or a
-- Hypothesis, and a Program that has just been opened has neither. Nor can a
-- model propose its way out: `promote_proposal` promotes Observations, Surface
-- and Hypotheses and not Tasks, and there is no model running while the slate
-- is empty.
--
-- Three things, and the middle one is the verb.
--
--   The subject. `ready_for` refuses a recon Task with no subject, and the
--   Surface of a freshly opened Program holds only the identity slots
--   `program._project_identities` wrote. `record_configured_subjects` projects
--   the live scope version's own exact target rules into `entities` as
--   Applications with `origin = 'configured'`, which is what 021 says that
--   origin means: "the operator's configuration". It reads the compiled rules
--   rather than the configuration document, so the subject a Task is opened
--   against is addressed in the same terms the scope evaluator will judge it
--   by.
--
--   The verb. `open_task` takes a Task kind and a subject and nothing else. It
--   refuses a subject that is not this Program's, one the live scope does not
--   admit as a target, a live Task that would duplicate it, and -- last, after
--   the row exists -- a Task `ready_for` would not let the scheduler act on.
--   That last one is why there is no list of per-kind preconditions here: the
--   one predicate the scheduler asks is the one this asks, so a kind whose
--   input a fresh Program does not have is refused by the same sentence that
--   would have left it pending forever.
--
--   The account. `task.opened` is an occurrence event carrying who opened the
--   Task, against what, and why, and it is written before the row so that the
--   `task.created` row event names it as its cause. A Task derived from a
--   Finding is attributable through the Finding; this is the same attribution
--   for the one Task that has nothing behind it but the configuration.
--
-- `open_configured_recon` is the caller, and `program._open_program` is where
-- it is called from: opening a Program is when the configuration is read, and
-- a seeding that ran every scheduler pass would be the runtime re-deciding the
-- Surface on a timer.
--
-- Narrows ADR 0002, and says so rather than doing it quietly. That ADR has the
-- causal context arriving "through SET LOCAL session settings that the
-- runtime's connection helper sets before any write", and until this file
-- `app.caused_by_event_id` was read in SQL and written only out there. Section
-- 3 writes it. What the ADR is protecting is attribution -- "the single place
-- an actor can be misattributed" -- and the actor is untouched here: `open_task`
-- reads `app.actor_kind` from the session the helper set and refuses outright
-- when it is unset, exactly as the ADR's second consequence requires. What it
-- sets is the cause, to an event it wrote itself one statement earlier, and it
-- puts the caller's own back before it returns. The alternative was for
-- `program.py` to write the `task.opened` event and set the cause around a
-- `tasks` insert of its own, which would move a row insert out of the one verb
-- and back to a call site -- the thing the ADR exists to stop. Worth reopening
-- if a second function ever needs this, because two of them is a convention
-- again and the ADR's argument would then apply in full.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. What the account is written as
-- ---------------------------------------------------------------------------
-- An occurrence event rather than a column on `tasks`. The reason a Task was
-- opened is a sentence about the moment it was opened, not a property of the
-- Task, and a column would have to be maintained by every later writer of that
-- row. `caused_by_event_id` already exists to join the two, and the emitter
-- already reads `app.caused_by_event_id`, so this needs no new machinery on the
-- reading side.

INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('task.opened', 'occurrence', NULL,
     'the runtime opened a Task against a subject: which kind, which subject, and the sentence that licensed it');


-- ---------------------------------------------------------------------------
-- 2. The Surface a configuration already declares
-- ---------------------------------------------------------------------------
-- An inclusion in a Program configuration is an address: a protocol, a host, a
-- port and a path prefix. That is an Application, and an Application is the one
-- kind of subject a Task can actually be dispatched against -- `execution`
-- resolves the target URL from `applications.base_url`, or from an Endpoint's
-- template under one, and a Task whose subject is neither is refused at the
-- target step for carrying no address to send a request to. So the projection
-- is one Application per target rule of the live scope version.
--
-- Spelled the way the promotion path spells one, and keyed the way it keys one,
-- because the recon Agent this opens a Task for will propose the Application it
-- was sent to map. `promote_proposal` writes
-- `rk2_dedup_key('application', ARRAY[base_url])`, so that proposal converges on
-- this row instead of standing up a second Application for the same address.
--
-- The rule's own protocol, port and path are carried because they are the
-- Application. `https://host/api/` and `https://host/admin/` are two base URLs,
-- and 020 already treats them as two subjects; a rule naming two protocols
-- compiles to two rows and is therefore two Applications, which is what listing
-- both asked for. `applications.kind` is left NULL -- web, api, spa, graphql or
-- websocket is a judgement about what answered, and nothing has asked yet.
--
-- Wildcards are not projected. `*.example.com` names a set of hosts and no
-- address, and there is nothing in this build that enumerates one, so a subject
-- recorded for it would be a subject with no verb: a Task against it would
-- reach the target step and stop. A Program whose scope is only wildcards
-- therefore opens nothing and says so in the count it reports, which is a
-- readable answer rather than a Task that fails once a child has been paid for.
-- CIDR rules are not projected either, and for a plainer reason:
-- `scope.parse_pattern` compiles `exact` and `wildcard` and nothing else, so
-- `pattern_kind = 'cidr'` is a shape the column admits and the compiler has
-- never produced. Both are filtered by name rather than left to fall through,
-- so the day either becomes projectable this is a missing subject and not a
-- silently malformed Entity.
--
-- Nothing is deleted when a rule is withdrawn. That is 021's rule and it still
-- holds here: the Entity stays and the next projection marks it denied, which
-- is how a subject that was in scope and no longer is stays readable.

-- The canonical spelling of a base URL: the scheme's own port is left off and
-- so is a root path, so `https://h:443/` and `https://h` are one string rather
-- than two rows for one address. 020's application arm builds the same string
-- inline to key a promoted Application on it, and this is the spelling that has
-- to agree with it -- named here so that a third writer has one to call instead
-- of a fourth to invent.
--
-- Agreeing means agreeing on all four parts, and two of them are not the
-- columns as `program_scope_rules` stores them.
--
--   The path goes through `rk2_clean_path`, which is what 020 reaches it
--   through: `rk2_parse_base_url` cleans before it returns, and cleaning drops
--   one trailing slash. `scope.path_variants` keeps that slash -- `/api/` is
--   stored as written -- so passing the column through verbatim would key the
--   configured Application on `.../api/` while the Agent proposing the very URL
--   it was handed keyed on `.../api`, which is the duplicate row this whole
--   section exists to prevent. A path `rk2_clean_path` refuses has no canonical
--   spelling at all, and the NULL that comes back is section 2's signal to skip
--   the rule rather than record a subject the promotion path could never
--   converge on.
--
--   An IPv6 host is bracketed. `scope.normalize_host` unbrackets one before it
--   stores it, so the column holds `2001:db8::1`; unbracketed in a URL that is
--   an authority with three colons in it, which `rk2_parse_base_url` refuses by
--   name and `execution` could never dial.
--
-- Not PARALLEL SAFE: `rk2_clean_path` is not marked, and a promise made here
-- about a function that has not made it is a promise about somebody else's
-- code.
CREATE FUNCTION rk2_base_url(p_scheme text, p_host text, p_port integer,
                             p_path text) RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT CASE WHEN c.path IS NULL THEN NULL ELSE
           p_scheme || '://'
        || CASE WHEN position(':' IN p_host) > 0
                THEN '[' || p_host || ']' ELSE p_host END
        || CASE WHEN coalesce(p_port, d.n) = d.n THEN '' ELSE ':' || p_port::text END
        || CASE WHEN c.path = '/' THEN '' ELSE c.path END END
      FROM (SELECT CASE WHEN p_scheme = 'https' THEN 443 ELSE 80 END) AS d(n),
           LATERAL rk2_clean_path(coalesce(p_path, '/')) c
$fn$;

COMMENT ON FUNCTION rk2_base_url(text, text, integer, text) IS
    'The canonical spelling of an Application''s base URL, the one '
    'rk2_parse_base_url would parse back to the same four parts: default port '
    'and root path omitted, one trailing slash dropped, an IPv6 host '
    'bracketed. NULL when the path is not a route this schema stores.';

CREATE FUNCTION record_configured_subjects(p_program uuid) RETURNS bigint
LANGUAGE plpgsql AS $fn$
DECLARE
    ver integer;
    n   bigint := 0;
BEGIN
    SELECT p.scope_version INTO ver FROM programs p WHERE p.id = p_program;
    IF ver IS NULL THEN
        RAISE EXCEPTION 'program % has no live scope version', p_program
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    -- One row per base URL: the URL is built from the other three columns and
    -- what it drops -- a port the scheme implies, one trailing slash -- is
    -- dropped by the promotion path too, so two rules with the same URL are the
    -- same host, port and path as well. A rule whose path has no canonical
    -- spelling gets no URL and is skipped, on the same ground as a wildcard:
    -- there is no address to send anything to.
    --
    -- The scope columns keep the rule's own prefix rather than the cleaned one.
    -- They answer a different question -- whether this Entity is under the rule
    -- -- and `scope_path_under` reads a prefix as a subtree, so an Entity at
    -- `/api` under a rule prefixed `/api/` would not be in scope at all.
    WITH subject AS (
        SELECT DISTINCT
               rk2_base_url(r.protocol, r.match_key, r.port, r.path_prefix) AS base_url,
               r.match_key                  AS host,
               r.port                       AS port,
               coalesce(r.path_prefix, '/') AS path
          FROM program_scope_rules r
         WHERE r.program_id = p_program
           AND r.version = ver
           AND r.effect = 'target'
           AND r.pattern_kind = 'exact'
           AND rk2_base_url(r.protocol, r.match_key, r.port, r.path_prefix) IS NOT NULL
    ), made AS (
        INSERT INTO entities (program_id, type, dedup_key, origin, metadata,
                              scope_selector_kind, scope_selector, scope_port,
                              scope_path_raw, scope_path_norm)
        SELECT p_program, 'application',
               rk2_dedup_key('application', ARRAY[s.base_url]),
               'configured',
               jsonb_build_object('source', 'program_scope', 'scope_version', ver),
               'host', s.host, s.port, s.path, s.path
          FROM subject s
        ON CONFLICT (program_id, type, dedup_key) DO NOTHING
        RETURNING id, dedup_key
    ), detailed AS (
        INSERT INTO applications (entity_id, base_url)
        SELECT m.id, s.base_url
          FROM made m
          JOIN subject s ON rk2_dedup_key('application', ARRAY[s.base_url]) = m.dedup_key
        RETURNING 1 AS one
    )
    SELECT count(*) INTO n FROM detailed;

    -- Always, not only when something was written: the rules may have moved
    -- under Entities this call did not create, and the projection is what
    -- decides whether they are still targets.
    PERFORM refresh_scope_projection(p_program);
    RETURN n;
END $fn$;

COMMENT ON FUNCTION record_configured_subjects(uuid) IS
    'Project the live scope version''s exact target rules into Surface as '
    'configured Applications, keyed on the base URL in the same spelling '
    'promote_proposal uses, so a proposal of the same address converges on the '
    'row instead of doubling it. Idempotent; deletes nothing, because a '
    'withdrawn rule leaves an Entity the next projection marks denied.';


-- ---------------------------------------------------------------------------
-- 3. The verb
-- ---------------------------------------------------------------------------
-- A kind and a subject. Not a row: nothing here lets a caller set a status, a
-- priority, an estimate or a lease, so a Task opened through this is a pending
-- Task the scheduler ranks like any other. Ticket 59's fourth criterion asks
-- for exactly that on anything a model could reach, and section 5 makes sure a
-- model cannot reach this one at all.
--
-- The readiness check is asked after the insert rather than before it because
-- `ready_for` takes a `tasks` row, and building one by hand to ask in advance
-- would mean this file keeping its own copy of the row shape -- which is the
-- copy that goes stale the day a kind gains a precondition.
--
-- Asking after is safe because every refusal here is the same refusal: the
-- exception aborts the caller's transaction, so the row this function inserted
-- a moment ago is undone along with everything else the caller had written.
-- That is the loud failure and not a skip -- one un-ready subject takes the
-- whole `rk run` open down with it -- and it is the right shape for the one
-- caller there is. `open_configured_recon` opens `recon` Tasks against subjects
-- section 3 has already established are targets, and `ready_for` refuses a
-- recon Task on exactly two grounds: no subject, and a subject not in scope.
-- Neither can be true here, so a refusal reaching this line means the two
-- predicates have stopped agreeing about what a target is, which is not a
-- subject to skip past.

CREATE FUNCTION open_task(p_program uuid, p_kind text, p_subject uuid,
                          p_reason text) RETURNS uuid
LANGUAGE plpgsql AS $fn$
DECLARE
    subject entities%ROWTYPE;
    actor   text;
    prior   text;
    cause   uuid;
    opened  uuid;
    refusal text;
BEGIN
    IF p_reason IS NULL OR btrim(p_reason) = '' THEN
        RAISE EXCEPTION 'a Task is opened with the sentence that licensed it'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    -- Read, never defaulted. The `task.opened` event is the whole of criterion
    -- 3, and an actor this function supplied would be the answer to "who opened
    -- it" invented by the thing being asked. `refresh_scope_projection` refuses
    -- the same session for the same reason.
    actor := nullif(current_setting('app.actor_kind', true), '');
    IF actor IS NULL THEN
        RAISE EXCEPTION
            'open_task must run inside a session that has declared its actor '
            '(app.actor_kind unset)'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    SELECT * INTO subject FROM entities e
     WHERE e.id = p_subject AND e.program_id = p_program;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'subject % is not an Entity of program %', p_subject, p_program
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    -- `target`, not merely `in_scope`. An `egress_support` Entity is in scope
    -- so that the harness may reach its own callback listener, and opening a
    -- recon Task against that would point a child at the harness.
    IF subject.scope_class <> 'target' THEN
        RAISE EXCEPTION
            'subject % is %, not a target of the live scope: %',
            subject.label, subject.scope_class, subject.scope_reason
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    -- The live dedup index would refuse this as a unique violation. Asked here
    -- so the refusal names the Task that already exists, which is what a caller
    -- deciding whether to skip a subject needs to read.
    SELECT k.label INTO refusal FROM tasks k
     WHERE k.program_id = p_program AND k.kind = p_kind
       AND k.subject_entity_id = p_subject
       AND k.hypothesis_id IS NULL AND k.finding_id IS NULL
       AND k.status IN ('pending', 'claimed', 'running', 'parked');
    IF FOUND THEN
        RAISE EXCEPTION '% already carries a live % Task against %',
            refusal, p_kind, subject.label
            USING ERRCODE = 'unique_violation';
    END IF;

    INSERT INTO events (program_id, type, actor_kind, payload)
    VALUES (p_program, 'task.opened', actor,
            jsonb_build_object('kind', p_kind,
                               'subject', subject.label,
                               'subject_entity_id', p_subject,
                               'scope_version', subject.scope_version_at,
                               'reason', p_reason))
    RETURNING id INTO cause;

    -- The row event the insert emits names this one as its cause, so a reader
    -- who found the Task can reach the sentence without knowing to look for it.
    -- Put back rather than cleared: a caller already writing under a cause of
    -- its own -- `open_configured_recon` in a loop is the obvious one -- would
    -- otherwise have it dropped by the first Task it opened.
    prior := coalesce(current_setting('app.caused_by_event_id', true), '');
    PERFORM set_config('app.caused_by_event_id', cause::text, true);
    INSERT INTO tasks (program_id, kind, subject_entity_id)
    VALUES (p_program, p_kind, p_subject)
    RETURNING id INTO opened;
    PERFORM set_config('app.caused_by_event_id', prior, true);

    SELECT ready_for(k) INTO refusal FROM tasks k WHERE k.id = opened;
    IF refusal IS NOT NULL THEN
        RAISE EXCEPTION 'a % Task against % would not be ready: %',
            p_kind, subject.label, refusal
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    RETURN opened;
END $fn$;

COMMENT ON FUNCTION open_task(uuid, text, uuid, text) IS
    'Open one pending Task of one kind against one subject the live scope '
    'admits as a target, and record the sentence that licensed it as a '
    'task.opened event the row event names as its cause. Refuses a foreign '
    'subject, a subject that is not a target, a duplicate of a live Task, and '
    'a Task ready_for would never let the scheduler act on.';


-- ---------------------------------------------------------------------------
-- 4. What a fresh Program opens
-- ---------------------------------------------------------------------------
-- `recon`, because it is the one kind whose input is the configuration and
-- nothing else -- `MISSIONS['recon']` in `execution.py` tells such a child to
-- "Map what this target exposes", and a configured target is the whole of what
-- it needs. The other three kinds each want state a fresh Program has not
-- produced yet, and section 3's readiness check would refuse them by name.
--
-- Guarded on a recon Task in ANY status, not merely a live one. 41's
-- `derive_chain_unlocks` gives the reason and it is the same reason here: "A
-- Task that ran and finished is an answer; deriving it again next pass because
-- the answer was disappointing is a loop with a database behind it." So a
-- second `rk run` against an unchanged configuration opens nothing, and a
-- configuration that adds a host opens one Task for the host it added.

CREATE FUNCTION open_configured_recon(p_program uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    recorded bigint;
    opened   bigint := 0;
    row_     record;
BEGIN
    recorded := record_configured_subjects(p_program);

    -- `metadata ->> 'source'` and not `origin`: `program._project_identities`
    -- writes Entities that are `configured` too, and an identity slot is not
    -- somewhere to send a recon Agent. The one thing this walks is what section
    -- 2 recorded.
    --
    -- The Task predicate is section 3's own, minus the status filter: the same
    -- three columns identify the Task, and widening it to any status is what
    -- makes a second `rk run` open nothing.
    FOR row_ IN
        SELECT e.id, e.label
          FROM entities e
         WHERE e.program_id = p_program
           AND e.metadata ->> 'source' = 'program_scope'
           AND e.scope_class = 'target'
           AND NOT EXISTS (SELECT 1 FROM tasks k
                            WHERE k.program_id = p_program
                              AND k.kind = 'recon'
                              AND k.subject_entity_id = e.id
                              AND k.hypothesis_id IS NULL
                              AND k.finding_id IS NULL)
         ORDER BY e.label
    LOOP
        PERFORM open_task(p_program, 'recon', row_.id,
                          'the Program''s configured scope admits this subject '
                          'and nothing has mapped it yet');
        opened := opened + 1;
    END LOOP;

    RETURN jsonb_build_object('subjects_recorded', recorded, 'tasks_opened', opened);
END $fn$;

COMMENT ON FUNCTION open_configured_recon(uuid) IS
    'Project the configured scope into Surface and open one recon Task per '
    'configured target nothing has ever reconned. Called when a Program is '
    'opened, so a campaign with no history still has something to rank.';


-- ---------------------------------------------------------------------------
-- 5. None of this is reachable from a model
-- ---------------------------------------------------------------------------
-- 029's default privileges hand every new function to `rk2_runtime`, and
-- Postgres hands every new function to PUBLIC. The revoke is the load-bearing
-- half: `rk2_state` is the role an MCP tool call arrives on, and a model that
-- could call `open_task` would be a model minting its own work -- which is the
-- whole of what the Slate exists to prevent.
--
-- `rk2_base_url` is not revoked, for the same reason `rk2_dedup_key` is not: it
-- reads nothing and writes nothing, so what it hands a caller is the argument
-- they already had, spelled the way this schema spells it.

REVOKE ALL ON FUNCTION record_configured_subjects(uuid) FROM PUBLIC, rk2_state, rk2_proxy;
REVOKE ALL ON FUNCTION open_task(uuid, text, uuid, text) FROM PUBLIC, rk2_state, rk2_proxy;
REVOKE ALL ON FUNCTION open_configured_recon(uuid) FROM PUBLIC, rk2_state, rk2_proxy;
GRANT EXECUTE ON FUNCTION record_configured_subjects(uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION open_task(uuid, text, uuid, text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION open_configured_recon(uuid) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 6. Criterion 3, asked of the log rather than of the code that writes it
-- ---------------------------------------------------------------------------
-- A `task.opened` event says why a Task was opened, and it is only an account
-- of a Task if some Task names it. `open_task` writes the pair in one
-- transaction, so a `task.opened` with no `task.created` citing it means either
-- that a caller wrote the occurrence event by hand or that the causal link was
-- lost between them -- both of which leave a Task whose reason nobody can reach
-- from the Task, which is the failure this event exists to end.
--
-- Not registered Program-scoped. This is a property of the log, and the one
-- Program-scoped check is `program_configuration`, which decides whether a
-- configuration may be adopted; a Program is not unsound because an event of
-- some other Program's lost its Task.

CREATE FUNCTION check_opened_tasks()
RETURNS TABLE(problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    SELECT 'opened_task_without_a_task',
           'a task.opened event for a ' || coalesce(o.payload ->> 'kind', '?')
               || ' Task against ' || coalesce(o.payload ->> 'subject', '?')
               || ' is cited by no task.created event'
      FROM events o
     WHERE o.type = 'task.opened'
       AND NOT EXISTS (SELECT 1 FROM events c
                        WHERE c.program_id = o.program_id
                          AND c.type = 'task.created'
                          AND c.caused_by_event_id = o.id)
$fn$;

COMMENT ON FUNCTION check_opened_tasks() IS
    'Ticket 83. Every account of why a Task was opened is reachable from the '
    'Task it accounts for: a task.opened event with no task.created event '
    'citing it as its cause is a reason nobody can find.';

REVOKE ALL ON FUNCTION check_opened_tasks() FROM PUBLIC, rk2_state, rk2_proxy;
GRANT EXECUTE ON FUNCTION check_opened_tasks() TO rk2_runtime, rk2_human;

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('opened_tasks',
     'SELECT * FROM check_opened_tasks()',
     '83',
     'every task.opened event is cited as the cause of a task.created event, so the sentence that licensed a Task is reachable from the Task');
