-- ===========================================================================
-- Production harness 31 -- a browser mission runs behind the door
-- ===========================================================================
-- A browser is the one tool in this harness that fetches things nobody asked
-- for. A page pulls its own scripts, its own images and its own XHRs, and it
-- does it from a process that reads DNS, opens sockets and remembers cookies.
-- Every one of those is a second egress path if it is not closed, and closing
-- them in the browser's own configuration is closing them where the page can
-- argue. So the shape here is the shape ticket 30 arrived at, one turn harder:
-- what the browser may be asked to do is a closed registry, the plan is
-- returned by the database rather than composed by a caller, and the network
-- the browser gets is a per-run adapter whose only peer is the door.
--
-- Six things, one per criterion:
--
--   1. Every request goes through the proxy and earns a Receipt.
--      `authorize_egress_request` is re-created here with a browser arm: the
--      Identity slot is enforced for the browser exactly as it is for
--      `net_request`, and the method is checked against the set this mission
--      derived from its own plan -- a set that cannot contain PUT, PATCH or
--      DELETE, because no action in the registry can cause one. A step records
--      how many requests the browser started, and `check_browser_runs` holds
--      that count against the Receipts the door wrote.
--   2. No path out except that one. The registry has no action that names a
--      host other than through a scope-checked URL, and every navigate URL in
--      a plan is classified against the Program's current scope before the row
--      exists. The namespace half is `isolation.py`'s: one internal network,
--      one peer, DNS to a blackhole.
--   3. The Identity is the proxy's business. `tool_runs.args ->> 'identity_slot'`
--      is what `resolve_egress_identity` already reads, and the browser writes
--      it there and nowhere else. Nothing in the container is given a cookie,
--      a header or a key; the door injects, and a probe that read
--      `document.cookie` would be a probe this file's own check refuses.
--   4. What the run saw becomes Artifacts. DOM, screenshot, console and probe
--      output land in `tool_run_artifacts` -- the same table an offline tool
--      run writes, because "what a Tool run produced" is one fact and two
--      tables holding it would be two answers -- attributed to the step that
--      produced them and, through the run, to the Receipts the door wrote.
--   5. The digest is over declared outcome keys and nothing else. Each action
--      names the keys its outcome may have; `record_browser_step` refuses an
--      outcome with any other key, and refuses a value that is not a small
--      integer, a boolean or a lowercase word. A timestamp, a nonce, a uuid
--      and a hash cannot be spelled in that vocabulary, so their exclusion is
--      structural rather than a filter somebody has to remember to apply.
--   6. The twins are a test, and this file is what makes the test mean
--      something: the same plan yields the same `plan_sha256` against both
--      fixtures and a different `result_digest`, because the probe's verdict
--      is the only thing that moved.


-- ---------------------------------------------------------------------------
-- 1. What a step's argument may be
-- ---------------------------------------------------------------------------
-- A second kind vocabulary rather than more rows in 30's, and the reason is an
-- invariant that points the other way. An offline tool's argument becomes a
-- token in an argv, so no kind there may admit `/` -- that is what makes path
-- escape impossible instead of checked. A browser's argument is a URL and a
-- CSS selector, and both need `/`. One table would have to give up one of the
-- two invariants, and the one it would give up is 30's.

-- One word shape, used by four things: an action's name, the keys of its
-- outcome, a probe's name and a probe's verdicts. All four end up in a digest
-- line, so all four have to be spellings a reader can tell apart from each
-- other and from a separator.
CREATE FUNCTION rk2_lowercase_words(p_words text[]) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT coalesce(bool_and(w ~ '^[a-z][a-z0-9_]{0,31}$'), true)
      FROM unnest(p_words) AS w;
$fn$;

COMMENT ON FUNCTION rk2_lowercase_words(text[]) IS
    'Whether every element of an array is a lowercase word of at most 32 '
    'characters. A predicate over its own argument, so it stays executable by '
    'PUBLIC: a CHECK constraint that some role could not evaluate would be a '
    'constraint that turns into an error at insert time rather than a rule.';

CREATE TABLE browser_argument_kinds (
    value_kind  text PRIMARY KEY,
    pattern     text NOT NULL,
    -- Separate from the pattern rather than spelled inside it, because a
    -- Postgres bound stops at 255 and the honest bound on a URL does not. A
    -- pattern that said `{0,512}` would be a pattern the server refuses to
    -- compile, and a pattern that said `*` and nothing else would be no bound.
    max_length  integer NOT NULL CHECK (max_length BETWEEN 1 AND 2048),
    description text NOT NULL
);

COMMENT ON TABLE browser_argument_kinds IS
    'What a value in a browser step may look like, by kind. Every kind is '
    'anchored and bounded, and no value of any kind ever becomes JavaScript: '
    'the driver hands these to the page as CDP call arguments, so a selector '
    'is a selector and a typed string is a typed string wherever it came from.';

COMMENT ON COLUMN browser_argument_kinds.pattern IS
    'The floor an action''s own row may narrow and may not widen: '
    '`open_browser_run` applies this first and the action''s own pattern after.';

COMMENT ON COLUMN browser_argument_kinds.max_length IS
    'What the shape does not say. Bounded at lengths a plan can carry and a '
    'Receipt can describe, because an argument nobody can read back is an '
    'argument nobody can check.';

INSERT INTO browser_argument_kinds (value_kind, pattern, max_length, description) VALUES
    -- No fragment, because a fragment never leaves the browser and a URL that
    -- carries one is a URL whose Receipt would not match it. No square
    -- brackets, so no IPv6 literal: the scope compiler classifies hosts, and a
    -- bracketed literal is a host spelling it does not produce.
    ('url',
     '^https?://[A-Za-z0-9][A-Za-z0-9.-]{0,252}(:[0-9]{1,5})?(/[A-Za-z0-9._~%!$&()*+,;=:@/-]*)?(\?[A-Za-z0-9._~%!$&()*+,;=:@/?-]*)?$',
     1024,
     'an absolute http or https URL, without a fragment and without an address literal'),
    -- `]` leads the set so it is a member rather than the end of it and `-`
    -- trails it, the same spelling 30 uses. `<`, `{`, `}`, `;` and `\` are out:
    -- none of them appears in a selector, and each of them appears in some
    -- other language a selector might be pasted into.
    ('selector',
     '^[]A-Za-z0-9 ."''#=_>~+*:,()/^$|[-]+$', 256,
     'a CSS selector, passed to the page as an argument and never as source text'),
    ('text',    '^[^[:cntrl:]]+$', 512,
     'a literal to type into a field or to look for in the rendered text'),
    ('integer', '^[0-9]{1,5}$', 5,
     'a count or a duration in milliseconds, and never a negative one'),
    ('probe',   '^[a-z][a-z0-9_]{0,31}$', 32,
     'the name of a registered probe; the JavaScript and the payload come from its row');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('browser_argument_kinds',
     'the vocabulary a browser action schema is written in; a per-program copy '
     'would let one Program mean something wider by `url` than the door does');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('browser_argument_kinds', 'reference',
     'the browser argument vocabulary, changed only by migration', '31');

GRANT SELECT ON browser_argument_kinds TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 2. What a browser may be asked to do
-- ---------------------------------------------------------------------------
-- Criterion 1's other half, and criterion 5's whole. Nine actions, and the
-- method set a mission may use is derived from which of them its plan contains
-- rather than declared beside it: `submits` is the column that decides, so a
-- plan that only reads cannot ask for POST and no plan of any shape can ask
-- for PUT, PATCH or DELETE. A browser has no way to emit those without script
-- the page itself wrote, and a page that wants one gets a refusal at the door
-- -- which is the answer an operator should be given rather than a permission
-- the plan quietly granted itself.

CREATE TABLE browser_actions (
    action       text PRIMARY KEY CHECK (action ~ '^[a-z][a-z0-9_]{0,31}$'),
    -- Whether performing this action can cause the browser to send a request
    -- the mission did not name a URL for. `navigate` does by construction;
    -- `click` does because a link and a form submit are both a click.
    reaches_network boolean NOT NULL,
    -- Whether performing it can cause a form submission, which is the only way
    -- an action in this registry produces a method outside the safe set.
    submits      boolean NOT NULL,
    -- The keys the outcome of this action may have, and the only thing the
    -- run's digest is computed over. An action with none of them would be a
    -- step the digest cannot see, which is criterion 5 with a hole in it.
    outcome_keys text[] NOT NULL
        CHECK (cardinality(outcome_keys) BETWEEN 1 AND 8
               AND rk2_lowercase_words(outcome_keys)),
    description  text NOT NULL
);

COMMENT ON TABLE browser_actions IS
    'Everything a browser mission may be asked to do, and what an answer to it '
    'looks like. Changed only by migration: an action the runtime could add is '
    'an action the plan could invent, and the plan is written by a model.';

COMMENT ON COLUMN browser_actions.submits IS
    'The whole of how a mission acquires POST. `open_browser_run` derives the '
    'method set from the actions its plan contains, so a read-only plan is a '
    'read-only capability and no plan is ever a state-changing one beyond a '
    'form submission.';

COMMENT ON COLUMN browser_actions.outcome_keys IS
    'The canonical outcome, by name. `record_browser_step` refuses an outcome '
    'with any other key and refuses a value outside the small vocabulary in '
    '`rk2_browser_outcome_word`, so a timestamp, a nonce, a generated '
    'identifier or a screenshot hash cannot reach the digest -- not because '
    'something strips them, but because there is nowhere to put them.';

INSERT INTO browser_actions
    (action, reaches_network, submits, outcome_keys, description) VALUES
    ('navigate',      true,  false, '{http_status,scope_class,document_loaded}',
     'load one URL the plan names, which the scope compiler has already classified'),
    ('wait_for',      false, false, '{matched}',
     'wait, bounded, until a selector matches something in the document'),
    ('fill',          false, false, '{matched}',
     'type a literal the plan supplies into the field a selector names'),
    ('inject',        false, false, '{matched}',
     'type a registered probe''s own payload into the field a selector names'),
    ('click',         true,  true,  '{matched}',
     'click what a selector names, which may follow a link or submit a form'),
    ('assert_text',   false, false, '{matched}',
     'the rendered text of the document contains the literal the plan names'),
    ('assert_absent', false, false, '{matched}',
     'the rendered text of the document does not contain it'),
    ('probe',         false, false, '{verdict}',
     'run a registered probe and record the verdict it returns, from its own declared set'),
    ('capture_dom',   false, false, '{captured}',
     'store the serialised document as an Artifact'),
    ('screenshot',    false, false, '{captured}',
     'store a PNG of the viewport as an Artifact');

CREATE TABLE browser_action_arguments (
    action      text NOT NULL REFERENCES browser_actions(action),
    name        text NOT NULL CHECK (name ~ '^[a-z][a-z0-9_]{0,31}$'),
    value_kind  text NOT NULL REFERENCES browser_argument_kinds(value_kind),
    required    boolean NOT NULL DEFAULT false,
    pattern     text,
    description text NOT NULL,
    PRIMARY KEY (action, name)
);

COMMENT ON TABLE browser_action_arguments IS
    'The argument schema of one action, one row per parameter. An argument an '
    'action does not declare is refused by name, because a verb that ignored '
    'what it did not recognise would run a shorter mission than the one it was '
    'asked for and report success.';

COMMENT ON COLUMN browser_action_arguments.pattern IS
    'Narrower than the kind, never wider: `open_browser_run` applies both, and '
    'the kind is applied first.';

INSERT INTO browser_action_arguments
    (action, name, value_kind, required, pattern, description) VALUES
    ('navigate',      'url',        'url',      true,  NULL,
     'the URL to load, classified against the Program''s scope before the run opens'),
    ('wait_for',      'selector',   'selector', true,  NULL,
     'what has to appear'),
    ('wait_for',      'timeout_ms', 'integer',  false, NULL,
     'how long to wait, bounded above by the step timeout in browser_ceilings'),
    ('fill',          'selector',   'selector', true,  NULL,
     'the field to type into'),
    ('fill',          'value',      'text',     true,  NULL,
     'what to type'),
    ('inject',        'selector',   'selector', true,  NULL,
     'the field to type into'),
    ('inject',        'probe',      'probe',    true,  NULL,
     'whose payload is typed; the same probe''s JavaScript is what later reads the result'),
    ('click',         'selector',   'selector', true,  NULL,
     'what to click'),
    ('assert_text',   'text',       'text',     true,  NULL,
     'the literal that must be present in the rendered text'),
    ('assert_absent', 'text',       'text',     true,  NULL,
     'the literal that must not be'),
    ('probe',         'probe',      'probe',    true,  NULL,
     'the registered probe to run');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('browser_actions',
     'what a browser may be asked to do at all; a per-program registry would '
     'make the set of possible actions something a Program''s configuration could widen'),
    ('browser_action_arguments',
     'the argument schema of a global registry');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('browser_actions', 'reference',
     'the browser action registry, changed only by migration', '31'),
    ('browser_action_arguments', 'reference',
     'the argument schema of the browser action registry', '31');

GRANT SELECT ON browser_actions, browser_action_arguments TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 3. The probes, which are the only JavaScript in this system
-- ---------------------------------------------------------------------------
-- A model-authored expression evaluated in the page would make every other
-- control here decorative: it could read `document.cookie`, it could fetch
-- whatever it liked from the page's own origin, and it could return whatever
-- verdict it wanted the run to record. So there is no path by which a plan
-- supplies JavaScript. A `probe` step names a row, the row holds the source,
-- and `open_browser_run` returns that source to the driver.
--
-- A probe owns both halves of its question. The payload it plants and the check
-- it runs are written together, by the owner, in the same row -- because a
-- probe that looked for a marker the plan chose would be a probe whose verdict
-- the plan could arrange.

CREATE TABLE browser_probes (
    probe       text PRIMARY KEY CHECK (probe ~ '^[a-z][a-z0-9_]{0,31}$'),
    -- What an `inject` step types on this probe's behalf, or NULL for a probe
    -- that plants nothing and only observes.
    payload     text CHECK (payload IS NULL OR length(payload) BETWEEN 1 AND 512),
    javascript  text NOT NULL CHECK (length(javascript) BETWEEN 1 AND 4096),
    -- Every answer the probe may give. The verdict a step records is checked
    -- against this, so a probe that returned something else is a broken probe
    -- rather than a new finding.
    verdicts    text[] NOT NULL
        CHECK (cardinality(verdicts) BETWEEN 2 AND 8
               AND rk2_lowercase_words(verdicts)),
    description text NOT NULL
);

COMMENT ON TABLE browser_probes IS
    'The closed set of expressions this harness will evaluate in a page. '
    'Owner-written, changed only by migration, and the only JavaScript any '
    'browser mission runs: a plan names a probe and never supplies one.';

COMMENT ON COLUMN browser_probes.payload IS
    'The string an `inject` step plants for this probe. Owned by the probe '
    'rather than by the plan, so the thing looked for and the thing planted '
    'are one decision and a verdict cannot be arranged by choosing the marker.';

COMMENT ON COLUMN browser_probes.javascript IS
    'Evaluated with `returnByValue`, and expected to return a JSON string whose '
    '`verdict` is one of this row''s verdicts. The whole string is stored as '
    'the step''s probe Artifact, so the verdict has its own evidence beside it.';

INSERT INTO browser_probes (probe, payload, javascript, verdicts, description) VALUES
    ('markup_injection',
     '<rk-probe id="rk-probe-marker"></rk-probe>',
     $js$(function () {
  var node = document.getElementById('rk-probe-marker');
  var body = document.body ? document.body.textContent : '';
  var raw  = document.documentElement ? document.documentElement.outerHTML : '';
  var seen = body.indexOf('rk-probe-marker') !== -1
             || raw.indexOf('rk-probe-marker') !== -1;
  return JSON.stringify({
    verdict: node ? 'reflected' : (seen ? 'escaped' : 'absent'),
    node_count: document.getElementsByTagName('rk-probe').length,
    marker_in_text: body.indexOf('rk-probe-marker') !== -1
  });
})()$js$,
     '{reflected,escaped,absent}',
     'did the payload come back as markup the parser built an element from, as text, or not at all');

-- One probe, for 30's reason: a registry seeded with entries nobody has run is
-- a registry of guesses. `rk-probe` is a custom element with no script, no
-- attribute a browser acts on and no content, so planting it changes what the
-- document IS without changing what it DOES -- which is what makes the same
-- payload safe to send at a real target and decisive against a fixture.

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('browser_probes',
     'the only JavaScript this harness evaluates; a per-program copy would be a '
     'per-program way to write some');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('browser_probes', 'reference',
     'the probe registry, changed only by migration', '31');

GRANT SELECT ON browser_probes TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 4. What a browser runs under
-- ---------------------------------------------------------------------------
-- One row, and the primary key says so. These are not per-mission numbers,
-- because a caller that could choose its own timeout could choose one longer
-- than the capability that authorises it, and a caller that could choose its
-- own memory could choose enough to matter on the host. A second profile is a
-- schema change, which is the same bar as a second action.

CREATE TABLE browser_ceilings (
    id                 integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    -- Deliberately under the five minutes `authorize_tool_run` gives a
    -- capability. A mission that outlived its own capability would spend its
    -- last minutes making requests the door refuses, and would report that as
    -- the target's behaviour.
    timeout_seconds    integer NOT NULL CHECK (timeout_seconds BETWEEN 5 AND 240),
    step_timeout_ms    integer NOT NULL CHECK (step_timeout_ms BETWEEN 100 AND 30000),
    max_steps          integer NOT NULL CHECK (max_steps BETWEEN 1 AND 64),
    memory_mb          integer NOT NULL CHECK (memory_mb BETWEEN 256 AND 4096),
    cpu_quota          numeric NOT NULL CHECK (cpu_quota > 0 AND cpu_quota <= 4),
    pids_limit         integer NOT NULL CHECK (pids_limit BETWEEN 32 AND 1024),
    max_artifact_bytes integer NOT NULL CHECK (max_artifact_bytes BETWEEN 1024 AND 16777216),
    -- Fixed, so two runs of one plan render the same document at the same size.
    -- The screenshot's bytes are outside the digest either way; a viewport a
    -- caller could vary would move what the DOM says as well.
    viewport_width     integer NOT NULL CHECK (viewport_width BETWEEN 320 AND 1920),
    viewport_height    integer NOT NULL CHECK (viewport_height BETWEEN 240 AND 1200)
);

COMMENT ON TABLE browser_ceilings IS
    'The one set of limits every browser mission runs under. One row by primary '
    'key, unreadable by the agent connection, and changed only by migration.';

INSERT INTO browser_ceilings
    (timeout_seconds, step_timeout_ms, max_steps, memory_mb, cpu_quota,
     pids_limit, max_artifact_bytes, viewport_width, viewport_height)
VALUES (180, 10000, 32, 1024, 2.0, 512, 8388608, 1280, 800);

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('browser_ceilings',
     'what a browser is allowed to consume; a per-program copy would let a '
     'Program raise its own ceiling');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('browser_ceilings', 'reference',
     'the browser resource ceilings, changed only by migration', '31');

GRANT SELECT ON browser_ceilings TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 5. The mission, the plan and what came of it
-- ---------------------------------------------------------------------------
-- `browser_runs` is an extension of the Tool run rather than a second run: the
-- status, the times and the label are already on `tool_runs` and a copy here
-- would be a second answer the day one of them moved. What this row holds is
-- the three facts the Tool run cannot: which plan ran, what the outcomes
-- digest to, and what to tell an operator if it ended badly.

CREATE TABLE browser_runs (
    tool_run_id   uuid PRIMARY KEY,
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    plan_sha256   text NOT NULL CHECK (plan_sha256 ~ '^[0-9a-f]{64}$'),
    result_digest text CHECK (result_digest ~ '^[0-9a-f]{64}$'),
    detail        text,
    UNIQUE (tool_run_id, program_id),
    FOREIGN KEY (tool_run_id, program_id) REFERENCES tool_runs (id, program_id)
);

COMMENT ON TABLE browser_runs IS
    'One browser mission, as the extension of the Tool run that performed it. '
    'The plan digest identifies what was asked; the result digest identifies '
    'what happened, over declared outcome keys alone.';

COMMENT ON COLUMN browser_runs.plan_sha256 IS
    'Over the identity slot and every step''s action and arguments in canonical '
    'order. Two runs of one mission share it whatever they found, which is what '
    'makes a differing result digest evidence about the target rather than '
    'evidence that somebody edited the plan.';

COMMENT ON COLUMN browser_runs.result_digest IS
    'Criterion 5. `browser_run_digest` over the declared outcome keys of every '
    'recorded step, and nothing else. Written once, at close, from the rows -- '
    'never supplied by the runtime, because a digest a caller can name is a '
    'digest a caller can make agree.';

CREATE TABLE browser_steps (
    tool_run_id uuid NOT NULL,
    ordinal     integer NOT NULL CHECK (ordinal BETWEEN 1 AND 64),
    program_id  uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    action      text NOT NULL REFERENCES browser_actions(action),
    arguments   jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (tool_run_id, ordinal),
    UNIQUE (tool_run_id, ordinal, program_id),
    FOREIGN KEY (tool_run_id, program_id) REFERENCES browser_runs (tool_run_id, program_id)
);

COMMENT ON TABLE browser_steps IS
    'The plan, one row per step, written by `open_browser_run` before anything '
    'starts. `arguments` is what the plan asked for, already validated against '
    'the action''s schema -- the driver is handed the resolved step and never '
    'reads this table.';

CREATE TABLE browser_step_results (
    tool_run_id      uuid NOT NULL,
    ordinal          integer NOT NULL,
    program_id       uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    outcome          jsonb NOT NULL,
    -- How many http or https requests the browser started while this step ran,
    -- counting each redirect hop. Outside `outcome` on purpose: it is the
    -- number `check_browser_runs` holds against the Receipts, and it is not
    -- stable enough between two runs of one plan to belong in a digest.
    network_requests integer NOT NULL DEFAULT 0 CHECK (network_requests BETWEEN 0 AND 4096),
    recorded_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tool_run_id, ordinal),
    UNIQUE (tool_run_id, ordinal, program_id),
    FOREIGN KEY (tool_run_id, ordinal, program_id)
        REFERENCES browser_steps (tool_run_id, ordinal, program_id)
);

COMMENT ON TABLE browser_step_results IS
    'What one step answered. Exactly one row per step, and its keys are exactly '
    'the action''s declared outcome keys -- so the run''s digest is a function '
    'of these rows and of the registry, and of nothing that varies between two '
    'runs of one plan.';

CREATE INDEX browser_step_results_run_idx ON browser_step_results (tool_run_id);

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('browser_runs',         'program_id', 'program-scoped: the purge root'),
    ('browser_steps',        'program_id', 'program-scoped: the purge root'),
    ('browser_step_results', 'program_id', 'program-scoped: the purge root');

-- No event type of its own, and 0022's reason: a browser mission IS a Tool run,
-- and `tool_runs` already emits `tool_run.proposed` when one opens and
-- `tool_run.settled` when it closes. A second pair of events over the same two
-- moments would be the log saying twice what happened once, and the day the two
-- disagreed there would be no way to tell which was the mission.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('browser_runs', 'covered',
     'the extension of a Tool run, written with it; the opening and the closing '
     'are tool_run.proposed and tool_run.settled', '31'),
    ('browser_steps', 'bookkeeping',
     'the compiled plan of a mission, written in the transaction that opens it '
     'and never afterwards; check_browser_runs holds it against its digest', '31'),
    ('browser_step_results', 'bookkeeping',
     'the outcomes of a mission, written in the transaction that closes it and '
     'never afterwards; check_browser_runs holds them against its digest', '31');

SELECT attach_event_triggers();

-- The plan and its outcomes are settled once. A step whose arguments could be
-- edited afterwards would be a mission whose `plan_sha256` describes something
-- else, and an outcome that could be edited would be a digest that agrees with
-- whatever was last written.
CREATE TRIGGER browser_steps_immutable
    BEFORE UPDATE OR DELETE ON browser_steps
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

CREATE TRIGGER browser_step_results_immutable
    BEFORE UPDATE OR DELETE ON browser_step_results
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

-- What the model may read: the mission it asked for and what came of it. The
-- registries stay where sections 1 to 4 left them -- an agent that could read
-- `browser_probes` would know which marker to look for, and one that could read
-- `browser_ceilings` would know exactly how long a mission may take.
INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('browser_runs',         'tool_run_id',      'ph2-31'),
    ('browser_runs',         'plan_sha256',      'ph2-31'),
    ('browser_runs',         'result_digest',    'ph2-31'),
    ('browser_runs',         'detail',           'ph2-31'),
    ('browser_steps',        'tool_run_id',      'ph2-31'),
    ('browser_steps',        'ordinal',          'ph2-31'),
    ('browser_steps',        'action',           'ph2-31'),
    ('browser_steps',        'arguments',        'ph2-31'),
    ('browser_step_results', 'tool_run_id',      'ph2-31'),
    ('browser_step_results', 'ordinal',          'ph2-31'),
    ('browser_step_results', 'outcome',          'ph2-31'),
    ('browser_step_results', 'network_requests', 'ph2-31'),
    ('browser_step_results', 'recorded_at',      'ph2-31');

GRANT SELECT, INSERT ON browser_runs TO rk2_runtime;
GRANT UPDATE (result_digest, detail) ON browser_runs TO rk2_runtime;
GRANT SELECT, INSERT ON browser_steps, browser_step_results TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 6. One table for what a Tool run produced
-- ---------------------------------------------------------------------------
-- Criterion 4. `tool_run_artifacts` is 30's table and it stays 30's table: a
-- browser's DOM and an offline tool's stdout are the same fact -- bytes a Tool
-- run produced, content-addressed, held by this Program -- and a second table
-- would be a second place an operator has to look and a second guard somebody
-- has to keep in step.
--
-- Two columns of vocabulary and one new column, and one repair on the way past.

ALTER TABLE tool_run_artifacts
    -- Which step produced them, for the browser streams that have one.
    -- `console` does not: a page logs whenever it likes, and attributing a
    -- message to whichever step happened to be running would be a guess
    -- recorded as a fact.
    ADD COLUMN browser_step_ordinal integer;

ALTER TABLE tool_run_artifacts DROP CONSTRAINT tool_run_artifacts_stream_check;
ALTER TABLE tool_run_artifacts ADD CONSTRAINT tool_run_artifacts_stream_check
    CHECK (stream IN ('stdout','stderr','output',
                      'dom','screenshot','console','probe'));

ALTER TABLE tool_run_artifacts DROP CONSTRAINT tool_run_artifacts_named_output_ck;
ALTER TABLE tool_run_artifacts ADD CONSTRAINT tool_run_artifacts_named_output_ck
    CHECK ((stream IN ('output','probe')) = (output_name IS NOT NULL));

ALTER TABLE tool_run_artifacts ADD CONSTRAINT tool_run_artifacts_browser_step_ck
    CHECK ((stream IN ('dom','screenshot','probe')) = (browser_step_ordinal IS NOT NULL));

ALTER TABLE tool_run_artifacts
    ADD FOREIGN KEY (tool_run_id, browser_step_ordinal, program_id)
        REFERENCES browser_steps (tool_run_id, ordinal, program_id);

-- The repair. 30's key was `(tool_run_id, stream, output_name)`, and
-- `output_name` is NULL for the two streams, so two `stdout` rows for one run
-- were distinct by the rule that NULLs never equal each other. Adding the
-- ordinal without saying otherwise would have made that worse rather than
-- better; saying it fixes both at once.
ALTER TABLE tool_run_artifacts
    DROP CONSTRAINT tool_run_artifacts_tool_run_id_stream_output_name_key;
ALTER TABLE tool_run_artifacts
    ADD CONSTRAINT tool_run_artifacts_stream_key
        UNIQUE NULLS NOT DISTINCT (tool_run_id, stream, output_name, browser_step_ordinal);

COMMENT ON COLUMN tool_run_artifacts.stream IS
    'Which stream of the producing run these bytes are. `stdout`, `stderr` and '
    'a declared `output` belong to an offline tool run; `dom`, `screenshot` and '
    '`probe` belong to one step of a browser mission and `console` to the '
    'mission as a whole. There is no `cookies`, and there is no `storage`: '
    'criterion 3 says the Agent is never shown a credential, and the way to '
    'mean that is to have nowhere to put one.';

COMMENT ON COLUMN tool_run_artifacts.browser_step_ordinal IS
    'The step of the browser mission that produced these bytes, and NULL for '
    'everything else. It is what links a stored DOM to the navigation that '
    'fetched it, and through the run to the Receipts the door wrote for it.';

INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('tool_run_artifacts', 'browser_step_ordinal', 'ph2-31');

-- 30's guard is about a process: it demands `offline_tool IS NOT NULL` and
-- checks a declared output against `offline_tool_outputs`. Re-created with the
-- two kinds of run as two arms, because a link row still has to prove the same
-- four things and only the last of them differs.
CREATE OR REPLACE FUNCTION tool_run_artifact_is_this_runs_output() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    v_run     tool_runs%ROWTYPE;
    v_browser boolean;
    v_size    bigint;
BEGIN
    SELECT * INTO v_run FROM tool_runs
     WHERE id = NEW.tool_run_id AND program_id = NEW.program_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tool run % is not a Tool run of this Program',
            NEW.tool_run_id USING ERRCODE = '23503';
    END IF;
    v_browser := EXISTS (SELECT 1 FROM browser_runs b WHERE b.tool_run_id = v_run.id);
    IF v_run.offline_tool IS NULL AND NOT v_browser THEN
        RAISE EXCEPTION 'tool run % is neither an offline Tool run nor a browser mission',
            v_run.label USING ERRCODE = '23503';
    END IF;
    -- The stream has to belong to the kind of run that is claiming it. Without
    -- this a browser mission could file a `stdout` and an offline tool could
    -- file a `dom`, and the reader of either would be reading a label that
    -- describes nothing that happened.
    IF v_browser <> (NEW.stream IN ('dom','screenshot','console','probe')) THEN
        RAISE EXCEPTION 'the % stream does not belong to this kind of run', NEW.stream
            USING ERRCODE = '23514';
    END IF;

    -- Output is recorded while the run is open, and the close is what makes it
    -- final. A row arriving after the close would be output attributed to a run
    -- that had already reported what it produced.
    IF v_run.status <> 'running' THEN
        RAISE EXCEPTION 'tool run % has already been closed as %',
            v_run.label, v_run.status USING ERRCODE = '23514';
    END IF;

    -- The Artifact has to be one this Program holds. Reachability is the
    -- reference, never the hash: ticket 06's whole argument is that storage
    -- deduplicates across Programs and access does not, so a hash another
    -- Program stored resolves here to nothing.
    IF NOT EXISTS (SELECT 1 FROM artifact_references r
                    WHERE r.program_id = NEW.program_id AND r.sha256 = NEW.sha256) THEN
        RAISE EXCEPTION 'artifact % is not held by this Program', NEW.sha256
            USING ERRCODE = '42704',
                  HINT = 'store the bytes and reference them before recording them as output';
    END IF;

    SELECT byte_size INTO v_size FROM artifacts WHERE sha256 = NEW.sha256;
    IF NEW.produced_bytes < v_size THEN
        RAISE EXCEPTION 'a stream of % byte(s) cannot have stored % byte(s)',
            NEW.produced_bytes, v_size USING ERRCODE = '23514';
    END IF;
    IF NEW.truncated <> (NEW.produced_bytes > v_size) THEN
        RAISE EXCEPTION 'the truncation flag disagrees with the stored size'
            USING ERRCODE = '23514',
                  HINT = 'truncated is produced_bytes > the stored artifact size, and nothing else';
    END IF;

    IF NEW.stream = 'output'
       AND NOT EXISTS (SELECT 1 FROM offline_tool_outputs o
                        WHERE o.tool = v_run.offline_tool AND o.name = NEW.output_name) THEN
        RAISE EXCEPTION '% declares no output named %', v_run.offline_tool, NEW.output_name
            USING ERRCODE = '42704';
    END IF;
    -- A probe Artifact is named by the probe that produced it, and the step it
    -- is attributed to has to be that probe's step. Otherwise the evidence
    -- beside a verdict could be evidence from somewhere else in the mission.
    IF NEW.stream = 'probe'
       AND NOT EXISTS (SELECT 1 FROM browser_steps s
                        WHERE s.tool_run_id = NEW.tool_run_id
                          AND s.ordinal = NEW.browser_step_ordinal
                          AND s.action = 'probe'
                          AND s.arguments ->> 'probe' = NEW.output_name) THEN
        RAISE EXCEPTION 'step % of this mission does not run the probe %',
            NEW.browser_step_ordinal, NEW.output_name USING ERRCODE = '42704';
    END IF;
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION tool_run_artifact_is_this_runs_output() IS
    'What a link row must be able to prove: the run is this Program''s and is '
    'still open, the stream belongs to the kind of run claiming it, the '
    'Artifact is one this Program holds, the sizes agree with what was stored, '
    'a named output is one the tool declares, and a probe Artifact belongs to '
    'the step that ran that probe.';


-- ---------------------------------------------------------------------------
-- 7. Opening a mission is validating the plan
-- ---------------------------------------------------------------------------
-- 30's argument, one turn harder. Everything that decides whether this mission
-- may happen is asked before any row exists; the rows are written before
-- anything starts; and what comes back is the resolved plan the driver is to
-- perform -- each step already carrying the probe source and payload it needs,
-- so the driver never looks anything up and there is no second place where a
-- name could resolve to different bytes.

CREATE FUNCTION rk2_browser_ceilings() RETURNS browser_ceilings
LANGUAGE sql STABLE AS $fn$ SELECT * FROM browser_ceilings WHERE id = 1 $fn$;

COMMENT ON FUNCTION rk2_browser_ceilings() IS
    'The one row of section 4. A function rather than a query at each call site '
    'so the singleton is asserted in one place and the runtime is handed limits '
    'rather than trusted to read them.';

-- The outcome vocabulary, and the whole of criterion 5's exclusion. A value is
-- a boolean, a small integer, or a lowercase word. A timestamp is none of
-- those; a uuid is none of those; a nonce and a content hash are none of those.
CREATE FUNCTION rk2_browser_outcome_word(p_value jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT CASE jsonb_typeof(p_value)
             WHEN 'boolean' THEN true
             WHEN 'number'  THEN p_value::text ~ '^[0-9]{1,5}$'
             WHEN 'string'  THEN (p_value #>> '{}') ~ '^[a-z][a-z0-9_]{0,31}$'
             ELSE false
           END;
$fn$;

COMMENT ON FUNCTION rk2_browser_outcome_word(jsonb) IS
    'Whether one outcome value is sayable in the canonical vocabulary: a '
    'boolean, an integer below 100000, or a lowercase word of at most 32 '
    'characters. Criterion 5 excludes timestamps, nonces, generated identifiers '
    'and screenshot bytes, and none of them can be written in this.';

-- The one name a browser mission's Tool run goes by. A function rather than
-- three string literals: `open_browser_run` writes it, and `authorize_egress_request`
-- reads it twice to decide what a request off this capability may be, so a
-- typo in any one of them would be a mission whose requests are judged by the
-- rules for something else.
CREATE FUNCTION rk2_browser_tool() RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$ SELECT 'mcp__rk2__browse'::text; $fn$;

COMMENT ON FUNCTION rk2_browser_tool() IS
    'The `tool_runs.tool` value a browser mission is opened under, in one '
    'place. Ticket 31.';

-- One line of either digest. Both this file's digests are a step's ordinal, its
-- action and a set of named values in key order, and they differ only in which
-- values: the plan digests the arguments a step was given and the result digests
-- the outcome it reported. Written once so they cannot drift -- a change to the
-- separators or the ordering in one and not the other would leave two digests
-- that look comparable and are not.
CREATE FUNCTION rk2_browser_digest_line(
        p_ordinal integer, p_action text, p_values jsonb, p_keys text[])
RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT p_ordinal || ' ' || p_action || ' ' ||
           coalesce((SELECT string_agg(k || '=' || (p_values ->> k), ',' ORDER BY k)
                       FROM unnest(p_keys) AS k), '');
$fn$;

COMMENT ON FUNCTION rk2_browser_digest_line(integer, text, jsonb, text[]) IS
    'One line of a browser mission''s digest: the ordinal, the action, and the '
    'named values in key order. The plan digest passes a step''s arguments and '
    'their own keys; the result digest passes the outcome and the action''s '
    'declared outcome keys. A key with no value contributes nothing to the '
    'line, the way string_agg skips a NULL, so an optional argument that was '
    'not given reads the same as one that does not exist.';

CREATE FUNCTION open_browser_run(
        p_agent_run_id  uuid,
        p_steps         jsonb,
        p_identity_slot text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p          uuid := rk2_program_required();
    v_run      agent_runs%ROWTYPE;
    v_ceil     browser_ceilings%ROWTYPE := rk2_browser_ceilings();
    v_step     jsonb;
    v_action   browser_actions%ROWTYPE;
    v_arg      browser_action_arguments%ROWTYPE;
    v_kind     browser_argument_kinds%ROWTYPE;
    v_probe    browser_probes%ROWTYPE;
    v_name     text;
    v_value    text;
    v_ordinal  integer := 0;
    v_methods  text[] := ARRAY['GET','HEAD','OPTIONS'];
    v_lines    text[] := '{}';
    v_plan     jsonb := '[]'::jsonb;
    v_args     jsonb;
    v_class    text;
    v_url      text[];
    v_id       uuid;
    v_label    text;
BEGIN
    IF jsonb_typeof(p_steps) <> 'array' THEN
        RAISE EXCEPTION 'the plan of a browser mission is an array of steps'
            USING ERRCODE = '22023';
    END IF;
    IF jsonb_array_length(p_steps) = 0
       OR jsonb_array_length(p_steps) > v_ceil.max_steps THEN
        RAISE EXCEPTION 'a browser mission has between 1 and % steps', v_ceil.max_steps
            USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_run FROM agent_runs
     WHERE id = p_agent_run_id AND program_id = p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent run % is not a run of this Program', p_agent_run_id
            USING ERRCODE = '23503';
    END IF;
    IF v_run.finished_at IS NOT NULL THEN
        RAISE EXCEPTION 'agent run % has already ended', v_run.label
            USING ERRCODE = '23514';
    END IF;

    -- The Halt. Unlike an offline tool run this mission will also pass the risk
    -- gate, because it makes requests -- `authorize_tool_run` is what mints its
    -- capability. The Halt is asked here as well because starting a browser is
    -- new work whatever the gate would have said, and because refusing it now
    -- means no container starts rather than one that starts and is refused.
    IF EXISTS (SELECT 1 FROM program_halts h
                WHERE h.program_id = p AND h.status = 'halted') THEN
        RAISE EXCEPTION 'the Program is Halted and may not start new work'
            USING ERRCODE = '42501',
                  HINT = 'rk resume lifts the Halt';
    END IF;

    -- The Identity is named here and resolved by the door. The lease is checked
    -- now so a mission with a slot it does not hold is refused before a browser
    -- exists, and checked again on every request by `resolve_egress_identity`,
    -- which is the one that counts: a lease that expires mid-mission stops the
    -- next request rather than being remembered as valid from the start.
    IF p_identity_slot IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM identities i
              JOIN identity_leases l
                ON l.identity_entity_id = i.entity_id
               AND l.program_id = i.program_id
               AND l.holder_agent_run_id = v_run.id
               AND l.released_at IS NULL
               AND l.expires_at > clock_timestamp()
             WHERE i.program_id = p
               AND i.slot_name = p_identity_slot
               AND i.invalidated_at IS NULL) THEN
            RAISE EXCEPTION 'Identity lease refused' USING ERRCODE = '23514';
        END IF;
    END IF;

    v_lines := array_append(v_lines, 'identity=' || coalesce(p_identity_slot, '-'));

    FOR v_step IN SELECT * FROM jsonb_array_elements(p_steps) LOOP
        v_ordinal := v_ordinal + 1;
        -- Cleared per step rather than left to the argument loop below to
        -- overwrite: a step that names no probe must not inherit the last one
        -- that did, and the resolution at the end of this loop reads it.
        v_probe := NULL;
        IF jsonb_typeof(v_step) <> 'object' THEN
            RAISE EXCEPTION 'step % is not an object', v_ordinal USING ERRCODE = '22023';
        END IF;

        SELECT * INTO v_action FROM browser_actions
         WHERE action = v_step ->> 'action';
        IF NOT FOUND THEN
            RAISE EXCEPTION 'step % names no action this browser performs: %',
                v_ordinal, coalesce(v_step ->> 'action', '<none>')
                USING ERRCODE = '42704';
        END IF;

        v_args := coalesce(v_step -> 'arguments', '{}'::jsonb);
        IF jsonb_typeof(v_args) <> 'object' THEN
            RAISE EXCEPTION 'the arguments of step % are an object', v_ordinal
                USING ERRCODE = '22023';
        END IF;

        -- Extra arguments first, and by name, so the refusal says which one.
        FOR v_name IN SELECT jsonb_object_keys(v_args) LOOP
            IF NOT EXISTS (SELECT 1 FROM browser_action_arguments a
                            WHERE a.action = v_action.action AND a.name = v_name) THEN
                RAISE EXCEPTION '% takes no argument named %', v_action.action, v_name
                    USING ERRCODE = '22023';
            END IF;
        END LOOP;

        FOR v_arg IN
            SELECT * FROM browser_action_arguments
             WHERE action = v_action.action ORDER BY name
        LOOP
            v_value := v_args ->> v_arg.name;
            IF v_value IS NULL THEN
                IF v_arg.required THEN
                    RAISE EXCEPTION 'step % (%) requires the argument %',
                        v_ordinal, v_action.action, v_arg.name USING ERRCODE = '22023';
                END IF;
                CONTINUE;
            END IF;
            IF jsonb_typeof(v_args -> v_arg.name) <> 'string' THEN
                -- Every value is handed to the page as a string, so every value
                -- is a string here. A number would be accepted by `->>` and
                -- would make the plan digest depend on how jsonb renders it.
                RAISE EXCEPTION 'the argument % of step % is given as text',
                    v_arg.name, v_ordinal USING ERRCODE = '22023';
            END IF;

            SELECT * INTO v_kind FROM browser_argument_kinds
             WHERE value_kind = v_arg.value_kind;
            IF length(v_value) > v_kind.max_length THEN
                RAISE EXCEPTION 'the argument % of step % is longer than a % may be',
                    v_arg.name, v_ordinal, v_arg.value_kind USING ERRCODE = '22023';
            END IF;
            IF v_value !~ v_kind.pattern THEN
                RAISE EXCEPTION 'the argument % of step % is not a well formed %',
                    v_arg.name, v_ordinal, v_arg.value_kind USING ERRCODE = '22023';
            END IF;
            IF v_arg.pattern IS NOT NULL AND v_value !~ v_arg.pattern THEN
                RAISE EXCEPTION 'the argument % of step % does not match what % accepts there',
                    v_arg.name, v_ordinal, v_action.action USING ERRCODE = '22023';
            END IF;

            IF v_arg.value_kind = 'probe' THEN
                SELECT * INTO v_probe FROM browser_probes WHERE probe = v_value;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'no probe named %', v_value USING ERRCODE = '42704';
                END IF;
                IF v_arg.name = 'probe' AND v_action.action = 'inject'
                   AND v_probe.payload IS NULL THEN
                    RAISE EXCEPTION 'the probe % plants nothing and cannot be injected', v_value
                        USING ERRCODE = '22023';
                END IF;
            END IF;

            IF v_arg.value_kind = 'url' THEN
                -- Criterion 2, before anything exists. The scope compiler owns
                -- the answer; a URL it does not classify as ours is a URL this
                -- mission will not be given a chance to try.
                v_url := regexp_match(v_value,
                    '^(https?)://([^/:?#]+)(?::([0-9]+))?([^?#]*)');
                SELECT s.scope_class INTO v_class
                  FROM programs pr
                  CROSS JOIN LATERAL scope_class_of(
                        pr.id, pr.scope_version, lower(v_url[2]),
                        coalesce(v_url[3]::integer,
                                 CASE lower(v_url[1]) WHEN 'https' THEN 443 ELSE 80 END),
                        coalesce(nullif(v_url[4], ''), '/'),
                        coalesce(nullif(v_url[4], ''), '/'),
                        lower(v_url[1]), 'request') s
                 WHERE pr.id = p;
                IF coalesce(v_class, 'denied') NOT IN ('target', 'egress_support') THEN
                    RAISE EXCEPTION 'step % navigates outside the current scope', v_ordinal
                        USING ERRCODE = '42501',
                              HINT = 'the door would refuse it; the mission is refused instead';
                END IF;
            END IF;
        END LOOP;

        IF v_action.submits AND NOT ('POST' = ANY (v_methods)) THEN
            v_methods := array_append(v_methods, 'POST');
        END IF;

        v_lines := array_append(v_lines,
            rk2_browser_digest_line(v_ordinal, v_action.action, v_args,
                                    ARRAY(SELECT jsonb_object_keys(v_args))));

        -- The resolved step, which is what the driver performs. A `probe` or an
        -- `inject` carries the registry's own source and payload, so the driver
        -- has nothing to look up and no name of its own to resolve. Read off
        -- `v_probe`, which the argument loop above already fetched and which the
        -- same loop refused if it named nothing: asking again here would be a
        -- second read of one row that could answer differently.
        v_plan := v_plan || jsonb_build_object(
            'ordinal', v_ordinal,
            'action', v_action.action,
            'arguments', v_args,
            'outcome_keys', to_jsonb(v_action.outcome_keys),
            'javascript', CASE WHEN v_action.action = 'probe'
                               THEN v_probe.javascript END,
            'payload', CASE WHEN v_action.action = 'inject'
                            THEN v_probe.payload END,
            'verdicts', CASE WHEN v_action.action = 'probe'
                             THEN to_jsonb(v_probe.verdicts) END);
    END LOOP;

    -- The rows, and nothing has started. `args` is what was asked for and is
    -- also what the door reads: `identity_slot` is where `resolve_egress_identity`
    -- looks, and `methods` is what the re-created `authorize_egress_request`
    -- below holds every request against.
    INSERT INTO tool_runs
        (program_id, agent_run_id, task_id, tool, args, status, transport)
    VALUES
        (p, v_run.id, v_run.task_id, rk2_browser_tool(),
         jsonb_build_object('identity_slot', p_identity_slot,
                            'methods', to_jsonb(v_methods),
                            'steps', jsonb_array_length(p_steps)),
         'running', 'runtime')
    RETURNING id, label INTO v_id, v_label;

    INSERT INTO browser_runs (tool_run_id, program_id, plan_sha256)
    VALUES (v_id, p,
            encode(digest(array_to_string(v_lines, E'\n'), 'sha256'), 'hex'));

    -- The plan, last, because it is the one thing here that could not be
    -- written earlier: a step belongs to a run, the run belongs to a Tool run,
    -- and neither existed until the whole plan had been accepted. `v_plan`
    -- carries the validated arguments, so this writes what was checked rather
    -- than re-reading what was asked.
    INSERT INTO browser_steps (tool_run_id, ordinal, program_id, action, arguments)
    SELECT v_id, (s ->> 'ordinal')::integer, p, s ->> 'action', s -> 'arguments'
      FROM jsonb_array_elements(v_plan) AS s;

    RETURN jsonb_build_object(
        'tool_run_id', v_id,
        'tool_run', v_label,
        'plan_sha256', (SELECT b.plan_sha256 FROM browser_runs b WHERE b.tool_run_id = v_id),
        'identity_slot', p_identity_slot,
        'methods', to_jsonb(v_methods),
        'timeout_seconds', v_ceil.timeout_seconds,
        'step_timeout_ms', v_ceil.step_timeout_ms,
        'memory_mb', v_ceil.memory_mb,
        'cpu_quota', v_ceil.cpu_quota,
        'pids_limit', v_ceil.pids_limit,
        'max_artifact_bytes', v_ceil.max_artifact_bytes,
        'viewport_width', v_ceil.viewport_width,
        'viewport_height', v_ceil.viewport_height,
        'steps', v_plan);
END $fn$;

COMMENT ON FUNCTION open_browser_run(uuid, jsonb, text) IS
    'Validate one browser mission against the registry, record its plan before '
    'anything starts, and return the resolved plan and the ceilings the runtime '
    'is to run it under. Every refusal is a raise: an unknown action, an '
    'argument it does not declare, a required one missing, a value outside its '
    'kind, an unregistered probe, an Identity slot this run does not hold, a '
    'navigation outside the current scope, and a plan longer than the ceiling.';

CREATE FUNCTION record_browser_step(
        p_tool_run_id uuid,
        p_ordinal     integer,
        p_outcome     jsonb,
        p_requests    integer DEFAULT 0)
RETURNS void
LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    v_run    tool_runs%ROWTYPE;
    v_step   browser_steps%ROWTYPE;
    v_action browser_actions%ROWTYPE;
    v_key    text;
BEGIN
    SELECT tr.* INTO v_run FROM tool_runs tr
      JOIN browser_runs b ON b.tool_run_id = tr.id
     WHERE tr.id = p_tool_run_id AND tr.program_id = p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tool run % is not a browser mission of this Program',
            p_tool_run_id USING ERRCODE = '23503';
    END IF;
    IF v_run.status <> 'running' THEN
        RAISE EXCEPTION 'browser mission % was already closed as %',
            v_run.label, v_run.status USING ERRCODE = '23514';
    END IF;

    SELECT * INTO v_step FROM browser_steps
     WHERE tool_run_id = p_tool_run_id AND ordinal = p_ordinal;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'this mission has no step %', p_ordinal USING ERRCODE = '23503';
    END IF;
    SELECT * INTO v_action FROM browser_actions WHERE action = v_step.action;

    IF jsonb_typeof(p_outcome) <> 'object' THEN
        RAISE EXCEPTION 'the outcome of a step is an object' USING ERRCODE = '22023';
    END IF;

    -- Exactly the declared keys, both directions. A missing key would leave a
    -- hole in the digest that reads as an answer; an extra one would be a value
    -- the digest ignores, which is a fact recorded where nobody will check it.
    FOR v_key IN SELECT jsonb_object_keys(p_outcome) LOOP
        IF NOT (v_key = ANY (v_action.outcome_keys)) THEN
            RAISE EXCEPTION '% has no outcome named %', v_step.action, v_key
                USING ERRCODE = '22023';
        END IF;
    END LOOP;
    FOREACH v_key IN ARRAY v_action.outcome_keys LOOP
        IF NOT (p_outcome ? v_key) THEN
            RAISE EXCEPTION '% must report %', v_step.action, v_key
                USING ERRCODE = '22023';
        END IF;
        IF NOT rk2_browser_outcome_word(p_outcome -> v_key) THEN
            RAISE EXCEPTION 'the outcome % is not a canonical value', v_key
                USING ERRCODE = '22023',
                      HINT = 'an outcome is a boolean, an integer below 100000, or a lowercase word';
        END IF;
    END LOOP;

    -- A verdict is one of the probe's own. A step that answered something else
    -- is a broken probe, and recording it would put a word in the digest that
    -- the registry cannot account for.
    IF v_step.action = 'probe'
       AND NOT EXISTS (SELECT 1 FROM browser_probes b
                        WHERE b.probe = v_step.arguments ->> 'probe'
                          AND (p_outcome ->> 'verdict') = ANY (b.verdicts)) THEN
        RAISE EXCEPTION 'the probe % does not return the verdict %',
            v_step.arguments ->> 'probe', coalesce(p_outcome ->> 'verdict', '<none>')
            USING ERRCODE = '22023';
    END IF;

    INSERT INTO browser_step_results
        (tool_run_id, ordinal, program_id, outcome, network_requests)
    VALUES (p_tool_run_id, p_ordinal, p, p_outcome, coalesce(p_requests, 0));
END $fn$;

COMMENT ON FUNCTION record_browser_step(uuid, integer, jsonb, integer) IS
    'Record what one step answered, exactly once, in exactly the keys its '
    'action declares and exactly the vocabulary the digest is defined over. '
    'A probe''s verdict is checked against the probe''s own set.';

CREATE FUNCTION browser_run_digest(p_tool_run_id uuid) RETURNS text
LANGUAGE sql STABLE AS $fn$
    SELECT encode(digest(string_agg(l.line, E'\n' ORDER BY l.ordinal), 'sha256'), 'hex')
      FROM (SELECT r.ordinal,
                   rk2_browser_digest_line(r.ordinal, s.action, r.outcome,
                                           a.outcome_keys) AS line
              FROM browser_step_results r
              JOIN browser_steps s
                ON s.tool_run_id = r.tool_run_id AND s.ordinal = r.ordinal
              JOIN browser_actions a ON a.action = s.action
             WHERE r.tool_run_id = p_tool_run_id) l;
$fn$;

COMMENT ON FUNCTION browser_run_digest(uuid) IS
    'Criterion 5. The ordinal, the action and the declared outcome keys in key '
    'order, one line per recorded step, hashed. Nothing else is in it: not the '
    'times, not the identifiers, not the request counts and not one byte of a '
    'screenshot. Two runs of one plan that saw the same thing agree; two that '
    'saw different things do not.';

CREATE FUNCTION close_browser_run(
        p_tool_run_id uuid,
        p_status      text,
        p_detail      text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    v_run    tool_runs%ROWTYPE;
    v_steps  bigint;
    v_done   bigint;
    v_kept   bigint;
    v_digest text;
BEGIN
    IF p_status NOT IN ('success','error') THEN
        RAISE EXCEPTION 'a browser mission closes as success or error, not %', p_status
            USING ERRCODE = '22023';
    END IF;

    SELECT tr.* INTO v_run FROM tool_runs tr
      JOIN browser_runs b ON b.tool_run_id = tr.id
     WHERE tr.id = p_tool_run_id AND tr.program_id = p FOR UPDATE OF tr;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tool run % is not a browser mission of this Program',
            p_tool_run_id USING ERRCODE = '23503';
    END IF;
    IF v_run.status <> 'running' THEN
        RAISE EXCEPTION 'browser mission % was already closed as %',
            v_run.label, v_run.status USING ERRCODE = '23514';
    END IF;

    SELECT count(*) INTO v_steps FROM browser_steps WHERE tool_run_id = v_run.id;
    SELECT count(*) INTO v_done  FROM browser_step_results WHERE tool_run_id = v_run.id;
    SELECT count(*) INTO v_kept  FROM tool_run_artifacts WHERE tool_run_id = v_run.id;

    IF p_status = 'success' AND v_done < v_steps THEN
        -- A mission that succeeded without performing its plan is a mission
        -- whose digest describes a shorter plan than the one that was asked
        -- for, and the two would compare equal to nothing.
        RAISE EXCEPTION 'browser mission % recorded % of its % step(s)',
            v_run.label, v_done, v_steps USING ERRCODE = '23514';
    END IF;
    IF p_status = 'success' AND v_kept = 0 THEN
        RAISE EXCEPTION 'browser mission % stored none of what it saw', v_run.label
            USING ERRCODE = '23514',
                  HINT = 'store the console log and any captured DOM before closing a mission as success';
    END IF;

    v_digest := browser_run_digest(v_run.id);

    UPDATE browser_runs
       SET result_digest = v_digest, detail = left(p_detail, 500)
     WHERE tool_run_id = v_run.id;

    -- The credential dies with the mission because `guard_tool_run_authorization`
    -- clears it on any row that stops running, which is why this statement says
    -- nothing about it: a token left live on a finished run would be bearer
    -- material for a container that is already gone, and the one place that
    -- rule is written is the one place it can be enforced from.
    UPDATE tool_runs
       SET status = p_status, finished_at = now()
     WHERE id = v_run.id;

    RETURN jsonb_build_object(
        'tool_run', v_run.label, 'status', p_status,
        'steps', v_steps, 'recorded', v_done,
        'artifacts', v_kept, 'result_digest', v_digest);
END $fn$;

COMMENT ON FUNCTION close_browser_run(uuid, text, text) IS
    'Close one browser mission, once, and digest what it answered. A success '
    'has to have performed its whole plan and kept something; a failure closes '
    'as error with the detail, because what a reader needs from those is that '
    'the mission ended and why.';

REVOKE ALL ON FUNCTION rk2_browser_ceilings(),
                       open_browser_run(uuid, jsonb, text),
                       record_browser_step(uuid, integer, jsonb, integer),
                       browser_run_digest(uuid),
                       close_browser_run(uuid, text, text)
    FROM PUBLIC, rk2_state, rk2_proxy, rk2_human;
GRANT EXECUTE ON FUNCTION rk2_browser_ceilings(),
                          open_browser_run(uuid, jsonb, text),
                          record_browser_step(uuid, integer, jsonb, integer),
                          browser_run_digest(uuid),
                          close_browser_run(uuid, text, text)
    TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 8. The door learns what a browser is
-- ---------------------------------------------------------------------------
-- Criteria 1 and 3, at the only place they can be enforced: the function the
-- proxy calls before it sends anything. Two arms change and the rest is
-- verbatim from `20260810T214500Z`.
--
-- The Identity arm gains the browser tool. Without that a browser mission would
-- carry a slot in its `args`, `resolve_egress_identity` would resolve it, and
-- nothing would check that the request the proxy is about to make is the one
-- that slot was resolved for -- which is the difference between selecting an
-- Identity and being able to borrow one.
--
-- The method arm splits. `net_request` keeps its rule: the safe methods are
-- exempt because subresources and redirects share one capability and arrive as
-- GET whatever was declared. A browser has no declared single method to be
-- exempt from -- it has the set its plan derived -- so every method is matched
-- against that set, GET included. A mission whose plan cannot submit a form
-- therefore holds a capability that cannot POST, which is what makes the
-- derivation worth doing.

CREATE OR REPLACE FUNCTION authorize_egress_request(
    p_capability text,
    p_method     text,
    p_protocol   text,
    p_host       text,
    p_port       integer,
    p_path_raw   text,
    p_path_norm  text,
    p_identity   text DEFAULT ''
) RETURNS TABLE (
    program_id uuid,
    tool_run_id uuid,
    scope_version integer,
    scope_class text
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_auth    record;
    v_version integer;
    v_class   text;
    v_tool    text;
    v_args    jsonb;
    v_method  text;
BEGIN
    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    SELECT tr.tool, tr.args INTO v_tool, v_args
      FROM tool_runs tr WHERE tr.id = v_auth.tool_run_id;
    v_method := upper(coalesce(p_method, 'GET'));

    -- The canonical form, asserted rather than assumed. Each of these is a
    -- spelling the compiler's own canonicaliser cannot emit, so a request
    -- carrying one did not come through it.
    IF p_protocol IS NULL OR p_protocol NOT IN ('http', 'https') THEN
        RAISE EXCEPTION 'egress request states no known protocol'
            USING ERRCODE = '23514';
    END IF;
    IF p_host IS NULL OR scope_normalize_host(p_host) IS DISTINCT FROM p_host THEN
        RAISE EXCEPTION 'egress request states a host that is not in canonical form'
            USING ERRCODE = '23514';
    END IF;
    IF p_port IS NULL OR p_port < 1 OR p_port > 65535 THEN
        RAISE EXCEPTION 'egress request states no port in 1-65535'
            USING ERRCODE = '23514';
    END IF;
    IF p_path_raw IS NULL OR NOT starts_with(p_path_raw, '/')
       OR p_path_norm IS NULL OR NOT starts_with(p_path_norm, '/') THEN
        RAISE EXCEPTION 'egress request states a path that is not absolute'
            USING ERRCODE = '23514';
    END IF;
    -- A normalised path with a dot segment left in it is not normalised, and
    -- passing the raw spelling twice is exactly how 039 authorised
    -- `/public/../admin` under a rule that covers `/public`.
    IF p_path_norm ~ '(^|/)\.\.?(/|$)' THEN
        RAISE EXCEPTION 'egress request states a normalised path that still traverses'
            USING ERRCODE = '23514';
    END IF;

    -- Decided against the CURRENT policy and the request that actually arrived,
    -- not against the arguments that minted the capability. Subresources and
    -- redirects deliberately share one capability (§7); each still earns its own
    -- verdict, which is what makes sharing safe.
    SELECT p.scope_version INTO v_version
      FROM programs p WHERE p.id = v_auth.program_id;
    SELECT s.scope_class INTO v_class
      FROM scope_class_of(v_auth.program_id, v_version,
                          p_host, p_port, p_path_raw, p_path_norm,
                          p_protocol, 'request') s;
    IF coalesce(v_class, 'denied') NOT IN ('target', 'egress_support') THEN
        RAISE EXCEPTION 'egress request is outside current scope'
            USING ERRCODE = '23514';
    END IF;
    IF v_method <> 'CONNECT'
       AND v_tool IN ('mcp__rk2__net_request', rk2_browser_tool())
       AND coalesce(p_identity, '') IS DISTINCT FROM
           coalesce(v_args ->> 'identity_slot', '') THEN
        RAISE EXCEPTION 'egress identity does not match authorized tool run'
            USING ERRCODE = '23514';
    END IF;
    IF v_tool = rk2_browser_tool() THEN
        -- CONNECT is exempt for ticket 10's reason: no tunnel is opened at all,
        -- so there is no request for a declared method to describe.
        IF v_method <> 'CONNECT'
           AND NOT (v_method = ANY (ARRAY(SELECT jsonb_array_elements_text(
                        coalesce(v_args -> 'methods', '[]'::jsonb))))) THEN
            RAISE EXCEPTION 'egress method is not one this browser mission derived'
                USING ERRCODE = '23514';
        END IF;
    -- The method the Tool run declared binds every request that could change
    -- something, and only those. §7 has subresources and redirects sharing one
    -- capability, and both arrive as GET whatever the declared method was: a
    -- page authorized as a POST pulls its scripts with GETs, and a 303 turns the
    -- POST itself into one. Refusing those would make the sharing unusable while
    -- protecting nothing, because a safe method is the one thing a caller who
    -- already holds the capability gains nothing by substituting. Anything
    -- outside the safe set is matched exactly.
    ELSIF v_method NOT IN ('GET', 'HEAD', 'OPTIONS', 'CONNECT')
       AND upper(coalesce(v_args ->> 'method', 'GET')) IS DISTINCT FROM v_method THEN
        RAISE EXCEPTION 'egress method does not match authorized tool run'
            USING ERRCODE = '23514';
    END IF;

    RETURN QUERY SELECT v_auth.program_id, v_auth.tool_run_id,
                        v_version, v_class;
END $fn$;

COMMENT ON FUNCTION
    authorize_egress_request(text,text,text,text,integer,text,text,text) IS
  'Resolves a live capability and re-decides the request the proxy is about to send against the current compiled policy, in the canonical spellings the proxy will use. Refuses any spelling the canonicaliser could not have produced, any Identity that is not the one the Tool run selected, and -- for a browser mission -- any method outside the set its own plan derived.';


-- ---------------------------------------------------------------------------
-- 9. What can go wrong, as rows
-- ---------------------------------------------------------------------------
CREATE FUNCTION check_browser_runs()
RETURNS TABLE (problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- criterion 1: the browser started requests the door did not write a
    -- Receipt for. Only this direction is a fault: more Receipts than counted
    -- requests is a preflight or a retry the driver did not see, and more
    -- requests than Receipts is bytes that left another way.
    SELECT 'requests_without_receipts'::text,
           tr.label || ': ' || sum(r.network_requests) || ' request(s), ' ||
           (SELECT count(*) FROM receipts x WHERE x.tool_run_id = tr.id) || ' receipt(s)'
      FROM browser_runs b
      JOIN tool_runs tr ON tr.id = b.tool_run_id
      JOIN browser_step_results r ON r.tool_run_id = b.tool_run_id
     GROUP BY tr.id, tr.label
    HAVING sum(r.network_requests) >
           (SELECT count(*) FROM receipts x WHERE x.tool_run_id = tr.id)
UNION ALL
    -- criterion 1, from the other side: a mission that loaded a document and
    -- has no Receipt at all reached the network without the door.
    SELECT 'loaded_document_without_a_receipt', tr.label
      FROM browser_runs b
      JOIN tool_runs tr ON tr.id = b.tool_run_id
      JOIN browser_steps s ON s.tool_run_id = b.tool_run_id AND s.action = 'navigate'
      JOIN browser_step_results r
        ON r.tool_run_id = s.tool_run_id AND r.ordinal = s.ordinal
     WHERE r.outcome ->> 'document_loaded' = 'true'
       AND NOT EXISTS (SELECT 1 FROM receipts x WHERE x.tool_run_id = tr.id)
UNION ALL
    -- criterion 3: a probe that could read a credential out of the page and put
    -- it in an agent-visible Artifact. The registry is owner-written, which is
    -- what makes this a check on the owner rather than on a model.
    SELECT 'probe_reads_stored_credentials', b.probe
      FROM browser_probes b
     WHERE b.javascript ~* '(document\s*\.\s*cookie|localStorage|sessionStorage|indexedDB)'
UNION ALL
    -- criterion 5: an action whose outcome the digest cannot see.
    SELECT 'action_outside_the_digest', a.action
      FROM browser_actions a
     WHERE cardinality(a.outcome_keys) = 0
UNION ALL
    -- criterion 5: a recorded outcome whose keys are not the action's. The verb
    -- refuses it; this finds the row that got there another way.
    SELECT 'outcome_keys_disagree_with_the_action',
           r.tool_run_id::text || ' step ' || r.ordinal
      FROM browser_step_results r
      JOIN browser_steps s
        ON s.tool_run_id = r.tool_run_id AND s.ordinal = r.ordinal
      JOIN browser_actions a ON a.action = s.action
     WHERE (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(r.outcome) k)
           IS DISTINCT FROM (SELECT array_agg(k ORDER BY k) FROM unnest(a.outcome_keys) k)
UNION ALL
    -- criterion 5: a value outside the canonical vocabulary is a timestamp, a
    -- nonce or an identifier reaching the digest.
    SELECT 'outcome_value_outside_the_vocabulary',
           r.tool_run_id::text || ' step ' || r.ordinal || ' ' || e.key
      FROM browser_step_results r
      CROSS JOIN LATERAL jsonb_each(r.outcome) AS e(key, value)
     WHERE NOT rk2_browser_outcome_word(e.value)
UNION ALL
    -- criterion 5: a verdict the probe does not admit.
    SELECT 'verdict_outside_its_probe',
           r.tool_run_id::text || ' step ' || r.ordinal
      FROM browser_step_results r
      JOIN browser_steps s
        ON s.tool_run_id = r.tool_run_id AND s.ordinal = r.ordinal
      JOIN browser_probes b ON b.probe = s.arguments ->> 'probe'
     WHERE s.action = 'probe'
       AND NOT ((r.outcome ->> 'verdict') = ANY (b.verdicts))
UNION ALL
    -- criterion 5: the digest on the row disagrees with the rows it is over.
    -- The one arm that would catch a digest somebody wrote rather than computed.
    SELECT 'digest_disagrees_with_its_steps', tr.label
      FROM browser_runs b
      JOIN tool_runs tr ON tr.id = b.tool_run_id
     WHERE b.result_digest IS NOT NULL
       AND b.result_digest IS DISTINCT FROM browser_run_digest(b.tool_run_id)
UNION ALL
    -- a mission that ended without one. `close_browser_run` writes it; a run
    -- closed another way is a run whose outcomes nothing summarises.
    SELECT 'closed_mission_without_a_digest', tr.label
      FROM browser_runs b
      JOIN tool_runs tr ON tr.id = b.tool_run_id
     WHERE tr.status = 'success' AND b.result_digest IS NULL
UNION ALL
    -- a step of a plan nobody performed and nobody closed.
    SELECT 'mission_open_past_its_timeout', tr.label
      FROM browser_runs b
      JOIN tool_runs tr ON tr.id = b.tool_run_id
      CROSS JOIN rk2_browser_ceilings() c
     WHERE tr.status = 'running'
       AND tr.started_at < now() - make_interval(secs => c.timeout_seconds * 2)
UNION ALL
    -- the ceilings are one row and one row only.
    SELECT 'ceilings_not_singleton', count(*)::text
      FROM browser_ceilings
    HAVING count(*) <> 1
UNION ALL
    -- the registry is the runtime's and the agent connection may not read it. A
    -- model that can read `browser_probes` knows which marker the verdict turns
    -- on, and one that can read `browser_ceilings` knows exactly how long it has.
    SELECT 'registry_reachable_by_agent', table_name || '.' || privilege_type
      FROM information_schema.table_privileges
     WHERE grantee = 'rk2_state'
       AND table_name IN ('browser_actions','browser_action_arguments',
                          'browser_argument_kinds','browser_probes',
                          'browser_ceilings')
UNION ALL
    -- and no verb over it is reachable from a connection a model can influence.
    -- `authorize_egress_request` is deliberately absent: it is the door's own
    -- function and `rk2_proxy` must hold it.
    SELECT 'browser_verb_reachable', p.proname || ' by ' || r.rolname
      FROM pg_proc p
      CROSS JOIN (VALUES ('rk2_state'),('rk2_proxy')) AS r(rolname)
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('rk2_browser_ceilings','open_browser_run',
                         'record_browser_step','close_browser_run',
                         'browser_run_digest')
       AND has_function_privilege(r.rolname, p.oid, 'EXECUTE')
$fn$;

COMMENT ON FUNCTION check_browser_runs() IS
    'What a browser mission can get wrong: requests the door wrote no Receipt '
    'for, a document loaded with no Receipt at all, a probe that reads stored '
    'credentials, an action or an outcome the digest cannot account for, a '
    'verdict a probe does not admit, a digest that disagrees with its own '
    'steps, a mission closed without one or never closed at all, ceilings that '
    'are not one row, and the registry or its verbs reachable from a connection '
    'a model can influence.';

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('browser_runs', 'SELECT * FROM check_browser_runs()', '31',
     'every browser mission is registered, scoped, receipted, digested and closed');


-- ---------------------------------------------------------------------------
-- 10. The invariants this file must not have broken
-- ---------------------------------------------------------------------------
SELECT enforce_always_triggers();
SELECT apply_state_rls();
SELECT apply_state_grants();
SELECT enforce_fk_fire_order();

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_browser_runs();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-31 refuses to finish: % browser violation(s): %', n, d;
    END IF;

    -- 30's control still has to pass: this file re-created its trigger and
    -- widened its table, and a repair that broke the thing it repaired would
    -- show up here first.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_offline_tools();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-31 breaks ph2-30 (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-31 breaks program isolation (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || object || ' ' || detail, '; ')
      INTO n, d FROM check_rls_coverage();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-31 leaves a scoped table unguarded (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || object || ' ' || detail, '; ')
      INTO n, d FROM check_state_grants();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-31 changes the agent read surface (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_event_coverage();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-31 leaves a table unaccounted for in the log (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || object || ' ' || detail, '; ')
      INTO n, d FROM check_purge_reachability();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-31 makes a Program unpurgeable (% problems): %', n, d;
    END IF;
END $$;
