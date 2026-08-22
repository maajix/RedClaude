-- ===========================================================================
-- Production harness 142 -- a suggested Task becomes a Task or becomes a drop
-- ===========================================================================
-- `submit_mission_result` has declared `suggested_tasks` since the Contract was
-- written, `proposals.payload` has carried what a model put in it ever since,
-- and no SQL and no Python has ever read one. Not promoted, not dropped, not
-- counted: before this file the two declarations in `roster.py` were the only
-- mentions of the name in the tree. Six live hunts ended the same way -- two
-- recon Tasks, then `nothing_to_execute` on every pass after -- while the recon
-- Agent proposed between two and five follow-up Tasks in every single run,
-- naming Drupal paths, a contact form and a truncated body worth re-fetching.
-- Every one of them was discarded in silence, which is the one thing 0020 says
-- promotion may not do: "a silent drop is indistinguishable from a thing the
-- agent never proposed, and ticket 16 cannot grade what left no row."
--
-- The loop this closes has one other producer and it cannot start.
-- `derive_chain_unlocks` needs a sound chain, a Finding and a pivot stamp; a
-- Finding needs a supported Hypothesis, which needs a Test, which needs a hunt
-- Task, which `ready_for` will only allow against a testable Hypothesis.
-- Nothing in that sequence is reachable from a fresh recon run, so once the
-- configured recon Tasks 83 seeds are spent the queue is empty for good.
--
--
-- What 83 decided, and why this does not contradict it
-- ---------------------------------------------------------------------------
-- 83's preamble says, in the sentence this file has to answer:
--
--     "Nor can a model propose its way out: `promote_proposal` promotes
--     Observations, Surface and Hypotheses and not Tasks, and there is no model
--     running while the slate is empty."
--
-- That is a reading of the schema as it stood, offered as the reason the
-- empty-slate problem at Program open needed a verb the runtime calls from the
-- configuration rather than something a model could reach. It is not the
-- decision. The decision is 83's section 5, and it is one sentence long: "a
-- model that could call `open_task` would be a model minting its own work --
-- which is the whole of what the Slate exists to prevent." `open_task` is
-- revoked from `rk2_state`, which is the role an MCP tool call arrives on, and
-- this file does not touch that revoke.
--
-- A suggested Task is not a model minting work, on the same grounds that a
-- proposed Observation is not a model writing canon. The element arrives as
-- staging data on a payload the child cannot promote; the child is gone by the
-- time anything reads it -- `execution._promote` runs after the Agent run has
-- ended; and the runtime, on the `rk2_runtime` connection, decides. It decides
-- with the same gauntlet every other promoted element goes through: the subject
-- is resolved out of the proposal's own ref map or this Program's labels, and
-- then `open_task` asks the four questions it already asks -- is this Entity
-- this Program's, is it a target of the live scope, is there a live Task like
-- it already, and would `ready_for` let the scheduler act on the row. What the
-- model contributed is a subject and a sentence. Everything that decides
-- whether a Task exists is a row the runtime wrote.
--
-- 83 also predicted the shape of the answer without meaning to. Its section 4
-- opens `recon` Tasks and nothing else, "because it is the one kind whose input
-- is the configuration and nothing else". A suggestion carries a subject and a
-- sentence, and `recon` is the one kind whose whole input that is. Section 2
-- below is that same restriction stated against a different input, and it is
-- also -- see hazard 1 -- what keeps an undispatchable kind out of the queue.
--
-- The one place the two do pull against each other is growth, and it is real.
-- Every other element list promotes something inert: an Entity, a Relationship,
-- an Observation, a Hypothesis all sit there until something else reads them. A
-- Task is work. It spends a Lease, a request budget and a token budget, and it
-- ends in another proposal carrying more suggestions. Promotion without a
-- ceiling would be a model minting its own work with three extra steps, which
-- is exactly what 83 refuses. The ceiling in section 2 is therefore not a
-- safeguard bolted onto the feature; it is the half of the feature that makes
-- the rest of it consistent with 83.
--
--
-- Hazard 1: an undispatchable Task refuses the whole pass, not itself
-- ---------------------------------------------------------------------------
-- Measured. An `analyze` Task opened by hand against an Application did not
-- run: the next `rk run` refused the entire pass with `ok: false` and exit 3,
--
--     {"code": "invalid_configuration", "source": "roster",
--      "detail": "a js_analyst run holds no net.request; this slice serves one
--                 target request and T3 needs a role that may make it"}
--
-- because `roster.ROLES['js_analyst']` deliberately holds no
-- `mcp__rk2__http_request` -- "an analyst that fetches is a hunter with the
-- wrong quota" -- and `execution.Slice._run` refuses at the role step before it
-- mints a capability nobody may spend. `reporter` fails one step earlier for a
-- different reason: it is a renderer with no served surface, so this runtime
-- "cannot start it as an isolated child". Both refusals are `ledger.fail`, and
-- `_pass` claims one Task per pass, so one such Task at the top of the ranking
-- is every later pass refused.
--
-- Three ways out were open and this file takes the third.
--
--   Fixing the routing means giving `js_analyst` `net.request`. That reverses a
--   roster decision taken on purpose and written down where it was taken, and
--   it is not a decision a promotion walk has standing to reverse.
--
--   Making the refusal skip the Task rather than the pass is a real defect and
--   is not this file's. It is `execution`'s, it predates this walk, and it
--   would still leave a permanently undispatchable Task in the queue for the
--   ranker to keep offering until its attempts ran out. That is 143, raised
--   beside this one; this file must not be the reason it looks handled.
--
--   Refusing the kind at promotion is 83's own move. Its section 3 asks
--   `ready_for` after the insert so that "a kind whose input a fresh Program
--   does not have is refused by the same sentence that would have left it
--   pending forever". The same argument reaches one step further out: a kind
--   whose role cannot make the one request the dispatch slice serves is a Task
--   that would have wedged every pass, and the honest moment to say so is the
--   moment the suggestion is read, in a row the model's grader can find.
--
-- So section 2 opens `recon` and refuses the other four by name, each with the
-- sentence that refuses it. Two of those sentences quote the roster, and that
-- is the line to revisit the day a role's tool groups change: the refusal of
-- `hunt` and `validate` is structural -- the element has no field that could
-- name a Hypothesis or a Finding, so `open_task` would insert a row `ready_for`
-- refuses -- while the refusal of `analyze` and `report` is a fact about which
-- role the roster gives the kind to.
--
-- There is a second way to be undispatchable and the live payloads are full of
-- it. Of the twenty-four suggestions the six hunts made, eleven named an
-- Application, three named an Endpoint, seven named a Domain and three named
-- nothing that resolves. `execution.STARTED` resolves a target URL from
-- `applications.base_url` or an Endpoint's template under one, and from nothing
-- else, so those seven would each have reached the target step and been refused
-- there -- again `ledger.fail`, again the whole pass. 83 already wrote that fact down in prose ("an
-- Application is the one kind of subject a Task can actually be dispatched
-- against"); section 2 asks it as a predicate, under its own reason, because a
-- model told `no_subject` about a subject that resolved perfectly well would
-- send the same one back.
--
-- Not put in `ready_for`, which is where it belongs and where it cannot go
-- yet. `ready_for` is the scheduler's own predicate and the right long-term
-- home for "this subject carries no address", and moving it there would fix
-- the wedge for every producer at once. It is also read by the ranking, the
-- claim and the idle report, and it is exercised by a large part of a 1359-test
-- module that this change is not able to run. A predicate moved into the
-- scheduler's hot path on an argument rather than on a measurement is not a
-- move worth making blind. 143 owns it.
--
--
-- Hazard 2: the ceiling, and what it is not doing
-- ---------------------------------------------------------------------------
-- Every recon run proposed two to five Tasks and every Task opens a run that
-- proposes more. `open_task` already refuses a live duplicate of one (kind,
-- subject) pair, which stops the same suggestion landing twice and does nothing
-- at all about breadth.
--
-- Total spend is already bounded and it is bounded where it should be. A
-- Program configuration states `[budgets]`, and the live one states
-- `requests = 1200` and `tokens = 2000000` for the whole campaign against
-- `run_requests = 40` and `run_tokens = 250000` for one run -- so a campaign
-- affords something between eight and thirty runs and then `_rotate` closes it.
-- What is unbounded is not the spend, it is the queue: suggestions arrive
-- faster than Tasks drain, and a campaign whose budget goes on a breadth-first
-- sweep of everything anybody mentioned has spent it as surely as one that
-- overran.
--
-- So the ceiling is on queue depth, and the number is one this schema already
-- states: `scheduler_weights.slate_size`, the number of Tasks `offer_slate`
-- puts in front of the picker. A Program already holding that many live Tasks
-- has a full slate; the orchestrator cannot see past it, so a Task added behind
-- it is not work made available, it is work made invisible. Reading the active
-- weights row rather than writing a number here also means the ceiling is
-- already versioned by whoever versions the scheduler, with no new column and
-- no second place to set it.
--
-- Per Program and not per proposal, because a per-proposal cap bounds one
-- result and not the tree: five runs each opening two Tasks is the same
-- explosion at a slower rate. Self-relieving rather than permanent, because a
-- suggestion refused at the ceiling is a good suggestion the queue had no room
-- for, and the model that made it is told exactly that -- so a later run that
-- still thinks the subject matters may say so again into a queue that has
-- drained.
--
--
-- Where the walk lives
-- ---------------------------------------------------------------------------
-- In SQL, beside the other five, as `rk2_promote_tasks` -- the shape
-- `rk2_promote_hypotheses` established for the same reason. Everything the walk
-- needs is already inside `promote_proposal`'s transaction and nowhere else:
-- the ref map that resolves `subject_ref` is a local variable of that function,
-- the `proposal_drops` ordinal is one sequence per proposal that the five walks
-- are already spending, `set_actor` and `set_cause` have already been called
-- where `open_task` requires them, and `open_task` itself is revoked from every
-- role but `rk2_runtime`. A Python walk would have to rebuild the ref map,
-- which is the second resolution of `subject_ref` that could drift from the
-- first, and open a second transaction that could commit without the promotion
-- it belongs to. `execution._promote` gains no logic at all: it reports the
-- Task labels the promotion hands back, which is what stops "nothing was
-- opened" and "nothing was suggested" reading the same way in a run report.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. Three more ways an element can be refused
-- ---------------------------------------------------------------------------
-- None of the twenty-eight reasons the column already admits says any of these
-- things, and each of the three names a different thing for the agent to do
-- next, which is the test 021 and 33 both applied when they widened this
-- vocabulary.
--
--   `unopenable_kind`   the element named a real Task kind that this walk does
--                       not open. Deliberately not `unknown_kind`, which says
--                       the word is outside a closed vocabulary: `analyze` is a
--                       row in `task_kinds` and `enumerate` is not, the two
--                       mistakes are different mistakes, and a model told the
--                       same thing about both learns neither. The `cited`
--                       sentence says which of the four it was and why.
--
--   `no_address`        the subject resolved, is this Program's, and is not an
--                       Application or an Endpoint, so there is no URL to
--                       dispatch a Task against it to. Not `no_subject`, for
--                       the reason 021 kept `no_parent` apart from it: the
--                       subject is fine as a subject and the agent that named a
--                       Domain should name the Application under it, whereas an
--                       agent told `no_subject` sends the same handle back.
--
--   `queue_at_ceiling`  the element was good and the Program's live queue is
--                       already as deep as the slate the picker is offered. The
--                       only refusal here that is about the moment rather than
--                       about the element, and the only one worth making again
--                       later, which is why it is not folded into any of the
--                       others.
--
-- Everything `open_task` itself refuses -- a foreign subject, a subject the
-- live scope does not admit as a target, a live duplicate, a row `ready_for`
-- would never let the scheduler act on -- arrives as `refused_by_invariant`
-- carrying that function's own sentence, which is what the Entity and
-- Relationship walks already do with a raised invariant and is the reason no
-- fourth reason is added for any of them.

ALTER TABLE proposal_drops DROP CONSTRAINT proposal_drops_reason_check;
ALTER TABLE proposal_drops ADD CONSTRAINT proposal_drops_reason_check
    CHECK (reason IN ('no_such_receipt','receipt_other_program',
                      'receipt_proxy_internal','receipt_other_run',
                      'no_such_tool_run','no_such_label',
                      'label_other_program','no_provenance',
                      'no_subject','unknown_kind','incompatible_provenance',
                      'refused_by_invariant',
                      'malformed_field','no_parent','out_of_scope',
                      'invalid_direction','is_containment',
                      'no_such_artifact','artifact_not_source','artifact_changed',
                      'artifact_not_read','no_source_citation',
                      'path_not_in_output',
                      'claims_execution','no_identity','no_support',
                      'claim_past_proposed','polarity_conflict',
                      'unopenable_kind','no_address','queue_at_ceiling'));


-- ---------------------------------------------------------------------------
-- 2. The walk
-- ---------------------------------------------------------------------------
-- One pass, in element order, the way the Entity, Relationship and Observation
-- walks are one pass each: a suggested Task depends on nothing later in its own
-- list, so it has none of the reason `rk2_promote_hypotheses` needs three.
--
-- The ref map arrives as an argument and the drop ordinal arrives and leaves,
-- for that function's reasons: the map is the caller's Entity walk's output,
-- and `proposal_drops.ordinal` is one sequence per proposal that this writes
-- into the middle of.
--
-- The subject is resolved exactly the way an Observation's is -- `subject_ref`
-- against the ref map first, because a Task against an Entity proposed in the
-- same result has no label to name until the Entity walk has run, and
-- `subject_label` otherwise. Same order, same two fields, same `btrim`, so
-- there is one resolution of `subject_ref` in this schema rather than two that
-- could drift.
--
-- The sentence `open_task` requires is the model's, quoted and attributed. It
-- is read from `rationale` or from `note`, because the payloads already staged
-- in live databases spell it both ways and neither is rare: thirteen of those
-- twenty-four elements said `note` and the other eleven said `rationale`, and
-- every one of them said exactly one. A `coalesce` costs less than a drop the
-- model has no way to learn the spelling from. It is prefixed with the proposal's label because
-- `open_task` reads the actor from the session and promotion is `runtime`: a
-- `task.opened` event that said only the model's sentence would attribute the
-- model's idea to the runtime, and 83's third section exists so that a Task's
-- reason is reachable and true.

CREATE FUNCTION rk2_promote_tasks(
    p_proposal    uuid,
    p_entity_refs jsonb,
    p_next        integer
) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p          uuid := rk2_program_required();
    v          proposals%ROWTYPE;
    v_next     integer := p_next;
    v_refused  integer := 0;
    v_element  jsonb;
    v_path     text;
    v_reason   text;
    v_cited    text;
    v_kind     text;
    v_subject  uuid;
    v_sentence text;
    v_ceiling  integer;
    v_live     integer;
    v_task     uuid;
    v_label    text;
    v_opened   text[] := '{}';
BEGIN
    SELECT * INTO v FROM proposals WHERE id = p_proposal AND program_id = p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'proposal % is not a result of this Program', p_proposal
            USING ERRCODE = 'check_violation';
    END IF;

    -- Read once: the slate the picker is offered does not change inside one
    -- promotion, and a weights version activated mid-walk would otherwise
    -- measure the first half of a list against one ceiling and the second half
    -- against another. `coalesce` to zero rather than to "no ceiling": a
    -- database with no active weights row is one whose scheduler can neither
    -- rank nor claim, and queueing work for a picker that is not running is the
    -- opposite of what the number is for.
    SELECT coalesce(w.slate_size, 0) INTO v_ceiling
      FROM scheduler_weights w WHERE w.active;
    v_ceiling := coalesce(v_ceiling, 0);

    FOR v_element, v_path IN
        SELECT e.value, 'suggested_tasks[' || (e.n - 1) || ']'
          FROM (SELECT value, row_number() OVER () AS n
                  FROM jsonb_array_elements(
                          CASE WHEN jsonb_typeof(v.payload -> 'suggested_tasks') = 'array'
                               THEN v.payload -> 'suggested_tasks' ELSE '[]'::jsonb END)
                 WHERE jsonb_typeof(value) = 'object') e
         ORDER BY e.n
    LOOP
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM proposal_drops d
             WHERE d.proposal_id = v.id AND d.element_path = v_path);

        v_reason := NULL; v_cited := NULL; v_subject := NULL;

        v_kind := nullif(btrim(v_element ->> 'kind'), '');

        IF nullif(btrim(v_element ->> 'subject_ref'), '') IS NOT NULL THEN
            v_subject := nullif(p_entity_refs ->> btrim(v_element ->> 'subject_ref'), '')::uuid;
            v_cited := btrim(v_element ->> 'subject_ref');
        ELSE
            SELECT e.id INTO v_subject FROM entities e
             WHERE e.program_id = p AND e.label = btrim(v_element ->> 'subject_label');
            v_cited := nullif(btrim(v_element ->> 'subject_label'), '');
        END IF;

        -- Counted inside the loop, because this walk is one of the things that
        -- changes it: a payload of five suggestions against a queue one short of
        -- the ceiling opens one Task and refuses four, and counting once before
        -- the loop would have opened all five.
        SELECT count(*) INTO v_live FROM tasks k
         WHERE k.program_id = p
           AND k.status IN ('pending', 'claimed', 'running', 'parked');

        IF v_kind IS NULL
           OR NOT EXISTS (SELECT 1 FROM task_kinds tk WHERE tk.kind = v_kind) THEN
            v_reason := 'unknown_kind';
            v_cited := v_kind;

        ELSIF v_kind <> 'recon' THEN
            v_reason := 'unopenable_kind';
            v_cited := v_kind || ': ' || CASE v_kind
                WHEN 'hunt' THEN
                    'a hunt Task is opened against a testable Hypothesis and a '
                    'suggestion has no field that names one'
                WHEN 'validate' THEN
                    'a validate Task is opened against a candidate Finding with '
                    'a test spec and a suggestion has no field that names one'
                WHEN 'analyze' THEN
                    'the roster gives analyze to js_analyst, which holds no '
                    'net.request, and the slice that dispatches a Task serves '
                    'one target request'
                WHEN 'report' THEN
                    'the roster gives report to reporter, which is a renderer '
                    'this runtime cannot start as an isolated child'
                ELSE 'this walk opens recon Tasks' END;

        ELSIF v_subject IS NULL THEN
            v_reason := 'no_subject';

        -- The two typed rows `execution.STARTED` resolves a target URL from,
        -- asked as the question that query asks. An Endpoint's Application is
        -- NOT NULL in 003, so reaching the Endpoint is reaching the address.
        ELSIF NOT EXISTS (SELECT 1 FROM applications a WHERE a.entity_id = v_subject)
          AND NOT EXISTS (SELECT 1 FROM endpoints ep WHERE ep.entity_id = v_subject) THEN
            v_reason := 'no_address';
            SELECT coalesce(v_cited, e.label) || ' is a ' || e.type
                   || ', and only an application or an endpoint carries an '
                   || 'address to send a request to'
              INTO v_cited FROM entities e WHERE e.id = v_subject;

        ELSIF v_live >= v_ceiling THEN
            v_reason := 'queue_at_ceiling';
            v_cited := v_live || ' live Task(s) already, and the active slate '
                    || 'offers ' || v_ceiling;
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, v_reason, left(v_cited, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
            CONTINUE;
        END IF;

        v_sentence := v.label || ' proposed this recon: '
                   || coalesce(nullif(btrim(v_element ->> 'rationale'), ''),
                               nullif(btrim(v_element ->> 'note'), ''),
                               'no reason was given');

        -- The subtransaction the other walks open around their write, widened
        -- by one condition. `open_task` raises `invalid_parameter_value` for
        -- three of its four refusals and `unique_violation` for the fourth, and
        -- the first of those is outside the five conditions the walks above
        -- catch -- so without naming it here a subject the live scope no longer
        -- admits would abort the entire promotion rather than lose one element.
        BEGIN
            v_task := open_task(p, v_kind, v_subject, left(v_sentence, 2000));
            SELECT k.label INTO v_label FROM tasks k WHERE k.id = v_task;
            v_opened := v_opened || v_label;
        EXCEPTION WHEN check_violation OR raise_exception OR not_null_violation
                    OR foreign_key_violation OR unique_violation
                    OR invalid_parameter_value THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, 'refused_by_invariant',
                    left(SQLERRM, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
        END;
    END LOOP;

    RETURN jsonb_build_object(
        'tasks', to_jsonb(v_opened),
        'refused', v_refused,
        'next', v_next);
END $fn$;

REVOKE ALL ON FUNCTION rk2_promote_tasks(uuid, jsonb, integer) FROM PUBLIC, rk2_state, rk2_proxy;
GRANT EXECUTE ON FUNCTION rk2_promote_tasks(uuid, jsonb, integer) TO rk2_runtime;

-- 066's registry, which is what makes the grant above a declaration rather than
-- a fact a reviewer would have to measure. `check_runtime_privileges` refuses a
-- verb the runtime can execute that no row here names.
INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('rk2_promote_tasks(uuid, jsonb, integer)',
     '142',
     'the promotion walk that turns a suggested task into a Task or a drop; called by promote_proposal inside its own transaction and by nothing else');

COMMENT ON FUNCTION rk2_promote_tasks(uuid, jsonb, integer) IS
    'The suggested-Task half of one promotion: each element becomes a recon '
    'Task opened through open_task against a subject the live scope admits, or '
    'a proposal_drops row saying which of the six things refused it. Bounded by '
    'the active slate size, because a Task is work that produces more '
    'suggestions and every other promoted element is inert.';


-- ---------------------------------------------------------------------------
-- 3. Promotion, with six element lists instead of five
-- ---------------------------------------------------------------------------
-- The five walks 021, 022 and 33 wrote are unchanged. What is added is the
-- sixth call, last, and three lines around it.
--
-- Last because the ref map has to be complete: a suggestion naming an Entity
-- proposed in the same result -- which is the common case, and the one the live
-- payloads are full of -- resolves through handles the Entity walk writes. It
-- is also the right place on the other side of the argument: everything the
-- result asserts has landed before any of it is turned into more work, so a
-- Task is opened against a Surface that is already what this run made it.
--
-- An opened Task counts toward `v_canonical`. A `tasks` row is canonical by
-- every test the other five apply -- it is a row in a canonical table that no
-- model may write and that outlives the proposal -- and a result whose only
-- durable effect was a Task the scheduler will now rank is a result that landed.
-- The alternative reading, that a proposal is only promoted if it asserted
-- something, would file such a result as `rejected` and 020's completion trigger
-- reads that status.
--
-- The repeated branch answers with the Tasks too, because that branch's whole
-- promise is that it "reports the same answer rather than a different one".
-- There is no `task_provenance` to read them back from and there does not need
-- to be one: `open_task` writes a `task.opened` event and the `task.created`
-- row event names it as its cause, the row event carries the `agent_run_id`
-- `set_cause` put on the session, and this proposal is that run's one result.
-- So the pair of events is the provenance, which is what 83 built it to be.

CREATE OR REPLACE FUNCTION promote_proposal(p_proposal uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p           uuid := rk2_program_required();
    v           proposals%ROWTYPE;
    v_version   integer;
    v_next      integer;
    v_element   jsonb;
    v_path      text;
    v_receipt   uuid;
    v_tool_run  uuid;
    v_evidence  text;   -- the label the element cited, whatever came of it
    v_subject   uuid;
    v_kind      text;
    v_parent_type text;
    v_scope_class text;
    v_allowed   text[];
    v_provenance text;
    v_reason    text;
    v_cited     text;
    v_label     text;
    v_refs      jsonb := '{}'::jsonb;   -- the proposal's own handles
    v_type      text;
    v_parent    uuid;
    v_parent_key text;
    v_parent_selector_kind text;
    v_parent_selector text;
    v_parent_port integer;
    v_parent_path text;
    v_selector_kind text;
    v_selector  text;
    v_scheme    text;
    v_base_url  text;
    v_port      integer;
    v_path_text text;
    v_dedup     text;
    v_fault     text;
    v_entity    uuid;
    v_created   boolean;
    v_fqdn      text;
    v_apex      text;
    v_wildcard  boolean;
    v_address   text;
    v_hostname  text;
    v_protocol  text;
    v_method    text;
    v_template  text;
    v_location  text;
    v_name      text;
    v_app_kind  text;
    v_identity_class text;
    v_src       uuid;
    v_dst       uuid;
    v_src_type  text;
    v_dst_type  text;
    v_relationship uuid;
    v_src_label text;
    v_dst_label text;
    v_entities  text[] := '{}';
    v_relationships text[] := '{}';
    v_promoted  text[] := '{}';
    v_refused   integer := 0;
    v_wrote_entity boolean := false;   -- whether the scope projection has work
    v_canonical boolean;               -- whether anything at all became canonical
    v_obs_refs  jsonb := '{}'::jsonb;   -- the same handles, for Observations
    v_observation uuid;
    v_hypotheses jsonb;                 -- what the Hypothesis walk made of it
    v_tasks     jsonb;                  -- and what the suggested-Task walk did
BEGIN
    SELECT * INTO v FROM proposals
     WHERE id = p_proposal AND program_id = p FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'proposal % is not a staged result of this Program', p_proposal
            USING ERRCODE = 'check_violation';
    END IF;

    -- Idempotent, and it reports the same answer rather than a different one.
    -- A promotion that ran and a promotion that had already run are the same
    -- state, and the caller retrying after a lost connection needs to be told
    -- what is true rather than what this call did. The two new lists are read
    -- back from the provenance rows, which is what they are for.
    IF v.status <> 'staged' THEN
        RETURN jsonb_build_object(
            'proposal', v.label, 'status', v.status, 'repeated', true,
            'entities', coalesce(
                (SELECT jsonb_agg(DISTINCT e.label) FROM entity_provenance ep
                   JOIN entities e ON e.id = ep.entity_id
                  WHERE ep.proposal_id = v.id), '[]'::jsonb),
            'relationships', coalesce(
                (SELECT jsonb_agg(DISTINCT s.label || ' ' || r.type || ' ' || d.label)
                   FROM relationship_provenance rp
                   JOIN relationships r ON r.id = rp.relationship_id
                   JOIN entities s ON s.id = r.src_entity_id
                   JOIN entities d ON d.id = r.dst_entity_id
                  WHERE rp.proposal_id = v.id), '[]'::jsonb),
            'observations', coalesce(
                (SELECT jsonb_agg(o.label ORDER BY o.label) FROM observations o
                  WHERE o.program_id = p AND o.metadata ->> 'proposal' = v.label),
                '[]'::jsonb),
            'hypotheses', coalesce(
                (SELECT jsonb_agg(DISTINCT h.label) FROM hypothesis_provenance hp
                   JOIN hypotheses h ON h.id = hp.hypothesis_id
                  WHERE hp.proposal_id = v.id), '[]'::jsonb),
            'evidence', (SELECT count(*) FROM hypothesis_evidence he
                          WHERE he.proposal_id = v.id),
            'tasks', coalesce(
                (SELECT jsonb_agg(k.label ORDER BY k.label)
                   FROM events c
                   JOIN events o ON o.program_id = c.program_id
                                AND o.id = c.caused_by_event_id
                                AND o.type = 'task.opened'
                   JOIN tasks k ON k.id = c.subject_id AND k.program_id = c.program_id
                  WHERE c.program_id = p AND c.type = 'task.created'
                    AND c.agent_run_id = v.agent_run_id), '[]'::jsonb),
            'refused', (SELECT count(*) FROM proposal_drops d WHERE d.proposal_id = v.id));
    END IF;

    PERFORM set_actor('runtime', 'promotion');
    PERFORM set_cause(v.agent_run_id, v.task_id);

    SELECT pr.scope_version INTO v_version FROM programs pr WHERE pr.id = p;
    SELECT coalesce(max(ordinal) + 1, 0) INTO v_next
      FROM proposal_drops WHERE proposal_id = v.id;

    -- === Entities ==========================================================
    FOR v_element, v_path IN
        SELECT e.value, 'new_entities[' || (e.n - 1) || ']'
          FROM (SELECT value, row_number() OVER () AS n
                  FROM jsonb_array_elements(
                          CASE WHEN jsonb_typeof(v.payload -> 'new_entities') = 'array'
                               THEN v.payload -> 'new_entities' ELSE '[]'::jsonb END)
                 WHERE jsonb_typeof(value) = 'object') e
         ORDER BY e.n
    LOOP
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM proposal_drops d
             WHERE d.proposal_id = v.id AND d.element_path = v_path);

        v_reason := NULL; v_cited := NULL; v_fault := NULL;
        v_receipt := NULL; v_tool_run := NULL; v_provenance := NULL;
        v_parent := NULL; v_parent_key := NULL;
        v_selector_kind := NULL; v_selector := NULL; v_port := NULL;
        v_path_text := '/'; v_dedup := NULL;
        v_scheme := NULL; v_base_url := NULL;

        v_type := nullif(btrim(v_element ->> 'type'), '');
        SELECT x.receipt_id, x.tool_run_id, x.provenance_kind, x.cited
          INTO v_receipt, v_tool_run, v_provenance, v_evidence
          FROM rk2_element_evidence(p, v_element) x;

        IF v_type IS NULL OR NOT (v_type = ANY (rk2_entity_types())) THEN
            v_reason := 'unknown_kind';
            v_cited := v_type;
        ELSIF v_provenance IS NULL THEN
            -- An Entity is a claim that something is out there, and criterion 1
            -- asks for stable evidence references. A proposed Entity citing
            -- nothing is a guess, and the harness has no way to tell it from a
            -- finding later.
            v_reason := 'no_provenance';
            v_cited := v_evidence;
        END IF;

        -- The containment parent, for the three types that have one.
        IF v_reason IS NULL AND v_type IN ('service','endpoint','parameter') THEN
            v_cited := coalesce(nullif(btrim(v_element ->> 'parent_ref'), ''),
                                nullif(btrim(v_element ->> 'parent_label'), ''));
            IF nullif(btrim(v_element ->> 'parent_ref'), '') IS NOT NULL THEN
                v_parent := nullif(v_refs ->> btrim(v_element ->> 'parent_ref'), '')::uuid;
            ELSIF nullif(btrim(v_element ->> 'parent_label'), '') IS NOT NULL THEN
                SELECT e.id INTO v_parent FROM entities e
                 WHERE e.program_id = p AND e.label = btrim(v_element ->> 'parent_label');
            END IF;
            IF v_parent IS NULL THEN
                v_reason := 'no_parent';
            ELSE
                SELECT e.dedup_key, e.type, e.scope_selector_kind, e.scope_selector,
                       e.scope_port, e.scope_path_raw
                  INTO v_parent_key, v_parent_type, v_parent_selector_kind, v_parent_selector,
                       v_parent_port, v_parent_path
                  FROM entities e WHERE e.id = v_parent;
                IF NOT EXISTS (SELECT 1 FROM entity_containment c
                                WHERE c.child_type = v_type AND c.parent_type = v_parent_type) THEN
                    v_reason := 'no_parent';
                    v_cited := v_cited || ' is a ' || v_parent_type;
                END IF;
            END IF;
        END IF;

        -- The typed fields, per type. Each arm produces a selector for the
        -- scope question and the parts of the dedup key, or a sentence saying
        -- which field it could not accept.
        IF v_reason IS NULL THEN
            IF v_type = 'domain' THEN
                v_fqdn := scope_normalize_host(v_element ->> 'fqdn');
                -- `coalesce`, because an absent key compares NULL rather than
                -- false and `domains.wildcard` is NOT NULL: a Domain proposed
                -- without the flag is a Domain, not a refusal.
                v_wildcard := coalesce((v_element -> 'wildcard') = 'true'::jsonb, false);
                IF v_fqdn IS NULL OR position('.' IN v_fqdn) = 0 OR v_fqdn !~ '[a-z]' THEN
                    v_fault := 'fqdn is absent or is not a dotted domain name';
                ELSE
                    SELECT array_to_string(l[greatest(1, cardinality(l) - 1):cardinality(l)], '.')
                      INTO v_apex FROM (SELECT string_to_array(v_fqdn, '.') AS l) s;
                    v_selector_kind := CASE WHEN v_wildcard THEN 'wildcard_domain' ELSE 'host' END;
                    v_selector := v_fqdn;
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[CASE WHEN v_wildcard THEN '*.' || v_fqdn ELSE v_fqdn END]);
                END IF;

            ELSIF v_type = 'host' THEN
                v_hostname := scope_normalize_host(v_element ->> 'hostname');
                v_address  := scope_normalize_host(v_element ->> 'address');
                IF nullif(btrim(v_element ->> 'address'), '') IS NOT NULL
                   AND (v_address IS NULL OR v_address !~ '^([0-9.]+|[0-9a-f:]+)$') THEN
                    -- Refused rather than dropped. A Host promoted on its
                    -- hostname with the offered address silently discarded is a
                    -- row that answers "what address is this" with nothing,
                    -- while the agent that sent one has been told it landed.
                    v_fault := 'address is not an IP address';
                ELSIF v_hostname IS NULL AND v_address IS NULL THEN
                    v_fault := 'a host needs a hostname or an address, and neither was usable';
                ELSE
                    v_selector_kind := 'host';
                    v_selector := coalesce(v_hostname, v_address);
                    v_dedup := rk2_dedup_key(v_type, ARRAY[v_selector]);
                END IF;

            ELSIF v_type = 'service' THEN
                v_protocol := lower(coalesce(nullif(btrim(v_element ->> 'protocol'), ''), 'tcp'));
                v_port := CASE WHEN v_element ->> 'port' ~ '^[0-9]{1,5}$'
                               THEN (v_element ->> 'port')::integer END;
                IF v_port IS NULL OR v_port NOT BETWEEN 1 AND 65535 THEN
                    v_fault := 'port is absent or is not a number between 1 and 65535';
                ELSIF v_protocol !~ '^[a-z0-9_+-]{1,32}$' THEN
                    v_fault := 'protocol is not a short lowercase token';
                ELSE
                    v_selector_kind := v_parent_selector_kind;
                    v_selector := v_parent_selector;
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[v_parent_key, v_port::text, v_protocol]);
                END IF;

            ELSIF v_type = 'application' THEN
                SELECT u.scheme, u.host, u.port, u.path, u.fault
                  INTO v_scheme, v_selector, v_port, v_path_text, v_fault
                  FROM rk2_parse_base_url(v_element ->> 'base_url') u;
                v_app_kind := nullif(btrim(v_element ->> 'kind'), '');
                IF v_fault IS NULL AND v_app_kind IS NOT NULL
                   AND v_app_kind NOT IN ('web','api','spa','graphql','websocket') THEN
                    v_fault := 'kind is not one of web, api, spa, graphql, websocket';
                END IF;
                IF v_fault IS NULL THEN
                    v_selector_kind := 'host';
                    -- The canonical spelling, built once: the key two proposals
                    -- converge on and the URL the column stores are the same
                    -- string, so they cannot drift apart.
                    v_base_url := v_scheme || '://' || v_selector ||
                        CASE WHEN v_port = CASE WHEN v_scheme = 'https' THEN 443 ELSE 80 END
                             THEN '' ELSE ':' || v_port::text END ||
                        CASE WHEN v_path_text = '/' THEN '' ELSE v_path_text END;
                    v_dedup := rk2_dedup_key(v_type, ARRAY[v_base_url]);
                END IF;

            ELSIF v_type = 'endpoint' THEN
                v_method := upper(coalesce(nullif(btrim(v_element ->> 'method'), ''), ''));
                SELECT c.path, c.fault INTO v_template, v_fault
                  FROM rk2_clean_path(v_element ->> 'path_template') c;
                IF v_method !~ '^[A-Z]{3,10}$' THEN
                    v_fault := 'method is absent or is not an HTTP method token';
                ELSIF v_fault IS NULL THEN
                    -- The route as the fence would see it. An Application at
                    -- `/api` and an Endpoint at `/users` is one request to
                    -- `/api/users`, and the scope question is about that.
                    v_path_text := CASE
                        WHEN v_parent_path = '/' THEN v_template
                        WHEN v_template = v_parent_path
                          OR starts_with(v_template, v_parent_path || '/') THEN v_template
                        ELSE v_parent_path || v_template END;
                    v_selector_kind := v_parent_selector_kind;
                    v_selector := v_parent_selector;
                    v_port := v_parent_port;
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[v_parent_key, v_method, v_template]);
                END IF;

            ELSIF v_type = 'parameter' THEN
                v_name := nullif(btrim(v_element ->> 'name'), '');
                v_location := lower(coalesce(nullif(btrim(v_element ->> 'location'), ''), ''));
                IF v_name IS NULL THEN
                    v_fault := 'name is absent';
                ELSIF v_location NOT IN ('query','body','path','header','cookie') THEN
                    v_fault := 'location is not one of query, body, path, header, cookie';
                ELSE
                    v_selector_kind := v_parent_selector_kind;
                    v_selector := v_parent_selector;
                    v_port := v_parent_port;
                    v_path_text := v_parent_path;
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[v_parent_key, v_location, v_name]);
                END IF;

            ELSIF v_type = 'technology' THEN
                v_name := nullif(btrim(v_element ->> 'name'), '');
                IF v_name IS NULL THEN
                    v_fault := 'name is absent';
                ELSE
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[lower(v_name),
                              coalesce(nullif(btrim(v_element ->> 'version'), ''), '')]);
                END IF;

            ELSE   -- identity
                v_name := nullif(btrim(v_element ->> 'slot_name'), '');
                v_identity_class :=
                    lower(coalesce(nullif(btrim(v_element ->> 'class'), ''), 'anonymous'));
                IF v_name IS NULL THEN
                    v_fault := 'slot_name is absent';
                ELSIF v_identity_class <> 'anonymous' THEN
                    -- 003: a non-anonymous Identity must carry a secret_ref, and
                    -- a secret is the operator's to place. Refused here with a
                    -- sentence rather than left to the CHECK, because "the row
                    -- was refused" and "an agent may not propose credentials"
                    -- are different things to have been told.
                    v_fault := 'an agent may propose only an anonymous identity; '
                            || 'a credentialed one is configured by the operator';
                ELSE
                    v_dedup := rk2_dedup_key(v_type, ARRAY[v_name]);
                END IF;
            END IF;

            IF v_fault IS NOT NULL THEN
                v_reason := 'malformed_field';
                v_cited := left(v_fault, 300);
            END IF;
        END IF;

        -- Scope, before the row exists. `not_addressable` is not a refusal: a
        -- Technology and an Identity have no address, which 021 says is a
        -- different answer from being out of scope.
        IF v_reason IS NULL THEN
            SELECT s.scope_class INTO v_scope_class
              FROM scope_class_of_entity(p, v_version, v_selector_kind, v_selector,
                                         v_port, v_path_text, v_path_text) s;
            IF v_scope_class = 'denied' THEN
                v_reason := 'out_of_scope';
                v_cited := left(coalesce(v_selector, '') ||
                                coalesce(':' || v_port::text, '') ||
                                CASE WHEN v_path_text = '/' THEN '' ELSE v_path_text END, 300);
            END IF;
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, v_reason, v_cited);
            v_next := v_next + 1;
            v_refused := v_refused + 1;
            CONTINUE;
        END IF;

        BEGIN
            -- Converge on the key, and touch nothing else. `last_seen_at` is
            -- the only column a second sighting is evidence about; the scope
            -- columns are the projection's and 021's trigger refuses them here.
            INSERT INTO entities
                (program_id, type, dedup_key, origin, scope_selector_kind,
                 scope_selector, scope_port, scope_path_raw, scope_path_norm)
            VALUES (p, v_type, v_dedup, 'proposed', v_selector_kind,
                    v_selector, v_port, v_path_text, v_path_text)
            ON CONFLICT (program_id, type, dedup_key)
                DO UPDATE SET last_seen_at = now()
            RETURNING id, (xmax = 0), label INTO v_entity, v_created, v_label;

            -- The detail row. Filled where it is empty and never overwritten:
            -- a second proposal that knows less is not a correction.
            IF v_type = 'domain' THEN
                INSERT INTO domains (entity_id, fqdn, apex, wildcard)
                VALUES (v_entity, v_fqdn, v_apex, v_wildcard)
                ON CONFLICT (entity_id) DO NOTHING;
            ELSIF v_type = 'host' THEN
                INSERT INTO hosts (entity_id, hostname, address)
                VALUES (v_entity, v_hostname, v_address::inet)
                ON CONFLICT (entity_id) DO UPDATE
                   SET hostname = coalesce(hosts.hostname, EXCLUDED.hostname),
                       address  = coalesce(hosts.address,  EXCLUDED.address);
            ELSIF v_type = 'service' THEN
                INSERT INTO services (entity_id, host_id, port, protocol, banner)
                VALUES (v_entity, v_parent, v_port, v_protocol,
                        left(nullif(btrim(v_element ->> 'banner'), ''), 500))
                ON CONFLICT (entity_id) DO UPDATE
                   SET banner = coalesce(services.banner, EXCLUDED.banner);
            ELSIF v_type = 'application' THEN
                INSERT INTO applications (entity_id, base_url, kind)
                VALUES (v_entity, v_base_url, v_app_kind)
                ON CONFLICT (entity_id) DO UPDATE
                   SET kind = coalesce(applications.kind, EXCLUDED.kind);
            ELSIF v_type = 'endpoint' THEN
                INSERT INTO endpoints (entity_id, application_id, method, path_template,
                                       auth_required, request_content_type)
                VALUES (v_entity, v_parent, v_method, v_template,
                        CASE WHEN jsonb_typeof(v_element -> 'auth_required') = 'boolean'
                             THEN (v_element -> 'auth_required') = 'true'::jsonb END,
                        left(nullif(btrim(v_element ->> 'request_content_type'), ''), 200))
                ON CONFLICT (entity_id) DO UPDATE
                   SET auth_required = coalesce(endpoints.auth_required, EXCLUDED.auth_required),
                       request_content_type = coalesce(endpoints.request_content_type,
                                                       EXCLUDED.request_content_type);
            ELSIF v_type = 'parameter' THEN
                INSERT INTO parameters (entity_id, endpoint_id, name, location,
                                        value_class, reflected)
                VALUES (v_entity, v_parent, v_name, v_location,
                        left(nullif(btrim(v_element ->> 'value_class'), ''), 200),
                        CASE WHEN jsonb_typeof(v_element -> 'reflected') = 'boolean'
                             THEN (v_element -> 'reflected') = 'true'::jsonb END)
                ON CONFLICT (entity_id) DO UPDATE
                   SET value_class = coalesce(parameters.value_class, EXCLUDED.value_class),
                       reflected   = coalesce(parameters.reflected,   EXCLUDED.reflected);
            ELSIF v_type = 'technology' THEN
                INSERT INTO technologies (entity_id, name, version, cpe)
                VALUES (v_entity, v_name,
                        nullif(btrim(v_element ->> 'version'), ''),
                        left(nullif(btrim(v_element ->> 'cpe'), ''), 200))
                ON CONFLICT (entity_id) DO UPDATE
                   SET cpe = coalesce(technologies.cpe, EXCLUDED.cpe);
            ELSE
                INSERT INTO identities (entity_id, slot_name, class)
                VALUES (v_entity, v_name, 'anonymous')
                ON CONFLICT (entity_id) DO NOTHING;
            END IF;

            INSERT INTO entity_provenance
                (program_id, entity_id, origin, proposal_id, element_path,
                 agent_run_id, receipt_id, tool_run_id)
            VALUES (p, v_entity, 'proposed', v.id, v_path,
                    v.agent_run_id, v_receipt, v_tool_run)
            ON CONFLICT (entity_id, origin, proposal_id, element_path) DO NOTHING;

            v_wrote_entity := true;
            v_entities := v_entities || v_label;
            IF nullif(btrim(v_element ->> 'ref'), '') IS NOT NULL THEN
                v_refs := v_refs || jsonb_build_object(btrim(v_element ->> 'ref'),
                                                       v_entity::text);
            END IF;
        EXCEPTION WHEN check_violation OR raise_exception OR not_null_violation
                    OR foreign_key_violation OR unique_violation THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, 'refused_by_invariant',
                    left(SQLERRM, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
        END;
    END LOOP;

    -- One projection for the whole walk. Every Entity above was inserted denied
    -- and every one of them was scope-checked before it was; this is what turns
    -- the check into the stored class, and re-running it at the same version
    -- writes nothing.
    IF v_wrote_entity AND v_version IS NOT NULL THEN
        PERFORM refresh_scope_projection(p);
    END IF;

    -- === Relationships =====================================================
    FOR v_element, v_path IN
        SELECT e.value, 'relationships[' || (e.n - 1) || ']'
          FROM (SELECT value, row_number() OVER () AS n
                  FROM jsonb_array_elements(
                          CASE WHEN jsonb_typeof(v.payload -> 'relationships') = 'array'
                               THEN v.payload -> 'relationships' ELSE '[]'::jsonb END)
                 WHERE jsonb_typeof(value) = 'object') e
         ORDER BY e.n
    LOOP
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM proposal_drops d
             WHERE d.proposal_id = v.id AND d.element_path = v_path);

        v_reason := NULL; v_cited := NULL;
        v_receipt := NULL; v_tool_run := NULL; v_provenance := NULL;
        v_src := NULL; v_dst := NULL;

        v_type := nullif(btrim(v_element ->> 'type'), '');
        SELECT x.receipt_id, x.tool_run_id, x.provenance_kind, x.cited
          INTO v_receipt, v_tool_run, v_provenance, v_evidence
          FROM rk2_element_evidence(p, v_element) x;

        IF nullif(btrim(v_element ->> 'src_ref'), '') IS NOT NULL THEN
            v_src := nullif(v_refs ->> btrim(v_element ->> 'src_ref'), '')::uuid;
        ELSIF nullif(btrim(v_element ->> 'src_label'), '') IS NOT NULL THEN
            SELECT e.id INTO v_src FROM entities e
             WHERE e.program_id = p AND e.label = btrim(v_element ->> 'src_label');
        END IF;
        IF nullif(btrim(v_element ->> 'dst_ref'), '') IS NOT NULL THEN
            v_dst := nullif(v_refs ->> btrim(v_element ->> 'dst_ref'), '')::uuid;
        ELSIF nullif(btrim(v_element ->> 'dst_label'), '') IS NOT NULL THEN
            SELECT e.id INTO v_dst FROM entities e
             WHERE e.program_id = p AND e.label = btrim(v_element ->> 'dst_label');
        END IF;

        SELECT e.type INTO v_src_type FROM entities e WHERE e.id = v_src;
        SELECT e.type INTO v_dst_type FROM entities e WHERE e.id = v_dst;

        IF v_provenance IS NULL THEN
            v_reason := 'no_provenance';
            v_cited := v_evidence;
        ELSIF v_src IS NULL OR v_dst IS NULL THEN
            v_reason := 'no_subject';
            v_cited := CASE WHEN v_src IS NULL
                            THEN coalesce(nullif(btrim(v_element ->> 'src_ref'), ''),
                                          nullif(btrim(v_element ->> 'src_label'), ''))
                            ELSE coalesce(nullif(btrim(v_element ->> 'dst_ref'), ''),
                                          nullif(btrim(v_element ->> 'dst_label'), '')) END;
        ELSIF NOT EXISTS (SELECT 1 FROM relationship_directions d WHERE d.type = v_type) THEN
            v_reason := 'unknown_kind';
            v_cited := v_type;
        ELSIF EXISTS (SELECT 1 FROM entity_containment c
                       WHERE (c.child_type, c.parent_type) IN
                             ((v_src_type, v_dst_type), (v_dst_type, v_src_type))) THEN
            -- Named apart from `invalid_direction` on purpose: the pair is not
            -- merely undefined, it is already a fact of the schema, and the
            -- agent's mistake is modelling rather than orientation.
            v_reason := 'is_containment';
            v_cited := v_src_type || ' and ' || v_dst_type || ' are containment, not a relationship';
        ELSIF NOT EXISTS (SELECT 1 FROM relationship_directions d
                           WHERE d.type = v_type AND d.src_type = v_src_type
                             AND d.dst_type = v_dst_type) THEN
            v_reason := 'invalid_direction';
            v_cited := v_type || ' does not go from ' || v_src_type || ' to ' || v_dst_type;
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, v_reason, left(v_cited, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
            CONTINUE;
        END IF;

        BEGIN
            INSERT INTO relationships (program_id, src_entity_id, dst_entity_id, type, origin)
            VALUES (p, v_src, v_dst, v_type, 'proposed')
            ON CONFLICT (src_entity_id, dst_entity_id, type)
                DO UPDATE SET last_seen_at = now()
            RETURNING id INTO v_relationship;

            INSERT INTO relationship_provenance
                (program_id, relationship_id, origin, proposal_id, element_path,
                 agent_run_id, receipt_id, tool_run_id)
            VALUES (p, v_relationship, 'proposed', v.id, v_path,
                    v.agent_run_id, v_receipt, v_tool_run)
            ON CONFLICT (relationship_id, origin, proposal_id, element_path) DO NOTHING;

            SELECT e.label INTO v_src_label FROM entities e WHERE e.id = v_src;
            SELECT e.label INTO v_dst_label FROM entities e WHERE e.id = v_dst;
            v_relationships := v_relationships ||
                (v_src_label || ' ' || v_type || ' ' || v_dst_label);
        EXCEPTION WHEN check_violation OR raise_exception OR not_null_violation
                    OR foreign_key_violation OR unique_violation THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, 'refused_by_invariant',
                    left(SQLERRM, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
        END;
    END LOOP;

    -- === Observations ======================================================
    FOR v_element, v_path IN
        SELECT e.value, 'observations[' || (e.n - 1) || ']'
          FROM (SELECT value, row_number() OVER () AS n
                  FROM jsonb_array_elements(
                          CASE WHEN jsonb_typeof(v.payload -> 'observations') = 'array'
                               THEN v.payload -> 'observations' ELSE '[]'::jsonb END)
                 WHERE jsonb_typeof(value) = 'object') e
         ORDER BY e.n
    LOOP
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM proposal_drops d
             WHERE d.proposal_id = v.id AND d.element_path = v_path);

        v_reason := NULL;
        v_receipt := NULL;
        v_tool_run := NULL;
        v_provenance := NULL;
        v_subject := NULL;
        v_cited := NULL;

        SELECT x.receipt_id, x.tool_run_id, x.provenance_kind, x.cited
          INTO v_receipt, v_tool_run, v_provenance, v_evidence
          FROM rk2_element_evidence(p, v_element) x;

        -- `subject_ref` first, because an Observation about an Entity proposed
        -- in the same result has no label to name until the walk above ran.
        IF nullif(btrim(v_element ->> 'subject_ref'), '') IS NOT NULL THEN
            v_subject := nullif(v_refs ->> btrim(v_element ->> 'subject_ref'), '')::uuid;
            v_cited := btrim(v_element ->> 'subject_ref');
        ELSE
            SELECT e.id INTO v_subject FROM entities e
             WHERE e.program_id = p AND e.label = v_element ->> 'subject_label';
            v_cited := v_element ->> 'subject_label';
        END IF;
        v_kind := v_element ->> 'kind';
        SELECT k.allowed_provenance INTO v_allowed
          FROM observation_kinds k WHERE k.id = v_kind;

        IF v_provenance IS NULL THEN
            v_reason := 'no_provenance';
            v_cited := v_evidence;
        ELSIF v_subject IS NULL THEN
            v_reason := 'no_subject';
        ELSIF v_allowed IS NULL THEN
            v_reason := 'unknown_kind';
            v_cited := v_kind;
        ELSIF NOT (v_provenance = ANY (v_allowed)) THEN
            v_reason := 'incompatible_provenance';
            v_cited := v_kind;
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, v_reason, v_cited);
            v_next := v_next + 1;
            v_refused := v_refused + 1;
            CONTINUE;
        END IF;

        BEGIN
            INSERT INTO observations
                (program_id, agent_run_id, subject_entity_id, kind, summary,
                 provenance_kind, receipt_id, tool_run_id, metadata)
            VALUES
                (p, v.agent_run_id, v_subject, v_kind,
                 left(coalesce(v_element ->> 'summary', ''), 2000),
                 v_provenance, v_receipt, v_tool_run,
                 jsonb_build_object('proposal', v.label, 'element', v_path))
            RETURNING label, id INTO v_label, v_observation;
            v_promoted := v_promoted || v_label;

            -- The handle, recorded the way an Entity's is. Without it an
            -- evidence edge could only cite an Observation from an earlier
            -- result, and a hunter that ran a differential and stated what it
            -- means submits both halves in one result.
            IF nullif(btrim(v_element ->> 'ref'), '') IS NOT NULL THEN
                v_obs_refs := v_obs_refs || jsonb_build_object(
                    btrim(v_element ->> 'ref'), v_observation::text);
            END IF;
        EXCEPTION WHEN check_violation OR raise_exception OR not_null_violation
                    OR foreign_key_violation OR unique_violation THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, 'refused_by_invariant',
                    left(SQLERRM, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
        END;
    END LOOP;

    -- The fourth and fifth lists, once the three walks above have produced
    -- every handle they can name. Its own function, and its own three passes:
    -- whether a Hypothesis is supported is a fact about the `evidence` list,
    -- which is read after it, so it cannot be settled one element at a time.
    v_hypotheses := rk2_promote_hypotheses(v.id, v_refs, v_obs_refs, v_next);
    v_next := (v_hypotheses ->> 'next')::integer;
    v_refused := v_refused + (v_hypotheses ->> 'refused')::integer;

    -- The sixth list, last of all, and last for two reasons that point the same
    -- way. It resolves `subject_ref` through the Entity walk's map, which is
    -- only complete once every walk that could add a handle has run; and a Task
    -- is the one element that is work rather than a record, so opening one
    -- against a Surface this result has not finished changing would be
    -- scheduling against a half-written world.
    v_tasks := rk2_promote_tasks(v.id, v_refs, v_next);
    v_next := (v_tasks ->> 'next')::integer;
    v_refused := v_refused + (v_tasks ->> 'refused')::integer;

    -- Promoted if anything at all became canonical. A recon run that found
    -- four Hosts and asserted nothing about them has done its Task, and 020's
    -- completion trigger reads this status.
    v_canonical := cardinality(v_promoted) > 0
              OR cardinality(v_entities) > 0
              OR cardinality(v_relationships) > 0
              OR jsonb_array_length(v_hypotheses -> 'hypotheses') > 0
              OR (v_hypotheses ->> 'evidence')::integer > 0
              OR jsonb_array_length(v_tasks -> 'tasks') > 0;

    UPDATE proposals
       SET status = CASE WHEN v_canonical THEN 'promoted' ELSE 'rejected' END,
           promoted_at = CASE WHEN v_canonical THEN now() END
     WHERE id = v.id;

    RETURN jsonb_build_object(
        'proposal', v.label,
        'status', CASE WHEN v_canonical THEN 'promoted' ELSE 'rejected' END,
        'repeated', false,
        'entities', to_jsonb(v_entities),
        'relationships', to_jsonb(v_relationships),
        'observations', to_jsonb(v_promoted),
        'hypotheses', v_hypotheses -> 'hypotheses',
        'evidence', (v_hypotheses ->> 'evidence')::integer,
        'tasks', v_tasks -> 'tasks',
        'refused', v_refused);
END $fn$;

REVOKE ALL ON FUNCTION promote_proposal(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION promote_proposal(uuid) TO rk2_runtime;

COMMENT ON FUNCTION promote_proposal(uuid) IS
    'Turns one staged agent-run result into canonical Entities, Relationships, '
    'Observations, Hypotheses, evidence edges and recon Tasks, in one '
    'transaction with the Events that record them. Every subject is '
    'canonicalized and scope-checked before anything is written, and every '
    'element it refuses leaves a proposal_drops row saying which reason refused '
    'it. Idempotent: a second call reports what the first one made.';
