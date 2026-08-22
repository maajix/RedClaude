-- ---------------------------------------------------------------------------
-- 20260926T010000Z__the_value_class_vocabulary_is_closed_at_the_column.sql
--                                                                  (ticket 111)
--
-- 0003 declares `parameters.value_class` as `text` and stops there. Nine
-- branches of `subject_facts` test that column against nine literal spellings
-- -- `uuid`, `integer_id`, `opaque_id`, `url`, `file`, `email`, `number`,
-- `path` and `serialized` -- and those spellings exist nowhere else. They are
-- not a table, they are not a constraint and they are not in any Python module,
-- Playbook or Skill in the tree; they are punctuation inside the body of a view.
-- The only writer is `promote_proposal`, which takes what the model typed:
-- `left(nullif(btrim(v_element ->> 'value_class'), ''), 200)`. So a model that
-- answers `"value_class": "integer"` writes a valid row that satisfies no
-- branch, computes no fact, and is reported by nothing.
--
-- What that silence costs is eleven Playbooks. `object-ownership`,
-- `external-resources`, `ssrf-url-routing`, `webhooks`, `file-resolution`,
-- `file-upload`, `exceptional-conditions`, `payment-workflows`,
-- `command-directory-injection`, `authentication` and `deserialization` are
-- selectable only when the spelling lands on one of the nine. Four more --
-- `agentic-ai`, `browser-script`, `ssti` and `spreadsheet-injection` -- trigger
-- on `parameters.reflected`, which is the same shape one column over and is
-- deliberately left alone: it is a boolean, so the risk there is a model
-- omitting it rather than misspelling it, and there is nothing to close.
--
-- THE SET IS CLOSED WHERE THE COLUMN IS, NOT WHERE THE READER IS.
--
-- A vocabulary written into a view body is enforced against nothing. The view
-- is a reader, it runs long after the row was written, and its way of rejecting
-- a spelling it does not know is to compute nothing and say nothing -- which
-- reads, downstream, exactly like a parameter that carries no interesting kind
-- of value. 018 already made this argument for the vocabularies it seeded, and
-- built both layers for it: an enum in the tool schema so the model is refused
-- before any code runs, and a foreign key so anything arriving by another route
-- is refused too. This column has had neither since 0003.
--
-- WHAT THE REFUSAL COSTS THE ONLY WRITER, WHICH IS LESS THAN IT LOOKS.
--
-- `promote_proposal` walks a proposal element by element inside a block whose
-- `EXCEPTION` arm catches `check_violation` and files a `proposal_drops` row
-- with reason `refused_by_invariant` and the server's own message. A model that
-- misspells a value class therefore loses that one element and is told so in
-- the drop, and the endpoint, the parameters beside it and every other element
-- of the same proposal are promoted as before. The refusal is a line in the
-- answer rather than a failed submission, which is what makes closing the
-- column affordable without touching the writer at all.
--
-- NULL is admitted, and that is not a loophole. The writer leaves the column
-- null whenever the model said nothing, and `unclassified` is a different claim
-- from `classified as something the surface has no reading for`: the first
-- computes no fact and asserts nothing, and the second computes no fact while
-- looking like an answer. Every branch in the view already tests for equality,
-- so a null row was invisible to all nine before this file and still is.
--
-- THE HALF THIS FILE DOES NOT BUY, AND WHO OWES IT.
--
-- The vocabulary still reaches the party that writes it nowhere.
-- `submit_mission_result` declares its element lists as free text, `mcp_enum`
-- has no caller at all, and no Playbook or Skill spells out the nine. Until
-- ticket 110 puts the closed set in front of the model, this constraint teaches
-- the nine by refusing rather than by telling, which is the weaker half of the
-- pair 018 describes and is the reason 111 was written blocked on 110. What
-- lands here is the half that holds whatever the tool schema says, including
-- against a fixture, a repair script or a future tool that forgot.
--
-- TECHNOLOGIES.NAME IS THE SAME SHAPE AND IS DECIDED THE OTHER WAY.
--
-- Nineteen `tech_*` facts are computed by matching `lower(technologies.name)`
-- against a sixty-nine-row list inline in the same view, and that column has no
-- constraint either. It does not get one. The set of technologies in the world
-- is open, the list is a set of readings this corpus happens to have Playbooks
-- for rather than a classification of anything, and a CHECK there would refuse a
-- true observation of a component nobody listed -- which is a worse answer than
-- recording it and computing no fact from it. The nine value classes are the
-- opposite case: a closed classification with one reader, where a tenth
-- spelling is never a discovery.
--
-- So `technologies.name` is a declared open set, and what that costs is written
-- on the column rather than left for somebody to rediscover: the reading
-- lowercases, so `NGINX` matches `nginx`, and a name that arrives carrying its
-- version or its packager -- `nginx/1.24.0`, `Nginx (Ubuntu)` -- matches
-- nothing and computes no fact for the eighteen Playbooks that trigger on one.
-- `technologies.version` is the column the writer already fills from a separate
-- field, which is where the rest of that string belongs.
--
-- Depends on 0003 (the column), 20260904T000000Z (the view as it now stands,
-- and the nine branches this closes over) and 20260814T070000Z (the writer and
-- its refusal arm). A new file rather than an edit to any of them: a recorded
-- migration whose file has changed is schema drift and `rk db migrate` refuses
-- the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. What is already recorded, before anything is closed over it
-- ===========================================================================

-- The column is empty on a fresh database, and on any database that has run a
-- hunt it holds whatever a model typed. A row outside the nine cannot be
-- repaired from here: the value is a claim somebody's model made about a
-- parameter, clearing it would rewrite a recorded observation and move the
-- surface fingerprint that hashes it, and guessing which of the nine was meant
-- is the model's job rather than a migration's. So this refuses with a sentence
-- naming what it found instead of leaving PostgreSQL to refuse the `ALTER`
-- below with a message about one row and no instruction.
DO $$
DECLARE n integer; spellings text;
BEGIN
    SELECT count(*), string_agg(DISTINCT quote_literal(value_class), ', ' ORDER BY quote_literal(value_class))
      INTO n, spellings
      FROM parameters
     WHERE value_class IS NOT NULL
       AND value_class NOT IN ('uuid','integer_id','opaque_id','url','file',
                               'email','number','path','serialized');
    IF n > 0 THEN
        RAISE EXCEPTION
            '% parameter(s) carry a value_class outside the nine: %', n, spellings
          USING DETAIL = 'each of these computes no surface fact today; correct '
                         'them to one of uuid, integer_id, opaque_id, url, file, '
                         'email, number, path, serialized, or clear them, and '
                         'apply this migration again',
                ERRCODE = '23514';
    END IF;
END $$;


-- ===========================================================================
-- 2. The closed set, on the column rather than in the view
-- ===========================================================================

-- Nullable and closed, in that order: the first arm is what the writer produces
-- when the model classified nothing, and the second is the vocabulary the nine
-- branches read. Spelled out rather than made a foreign key to a new reference
-- table: 018's tables carry a description because a model picks from them and
-- needs the leaf's meaning, and nothing picks from this one yet -- ticket 110
-- decides what the model is shown and can lift these nine into a table if that
-- is what serving them turns out to need.
ALTER TABLE parameters
    ADD CONSTRAINT parameters_value_class_check
    CHECK (value_class IS NULL
           OR value_class IN ('uuid','integer_id','opaque_id','url','file',
                              'email','number','path','serialized'));

-- The rule where a reader of the live schema meets it, which is the thing a
-- `--` comment in a migration file is not. The nine are named here because a
-- reader who has just been refused by the constraint above needs them, and
-- because the alternative is reading them out of a view body.
COMMENT ON COLUMN parameters.value_class IS
 'What kind of value this parameter carries, closed to nine spellings: uuid, integer_id and opaque_id for the three shapes of an object identifier, then url, file, email, number, path and serialized. The set is closed here rather than in the body of subject_facts because that view is the only reader and its way of refusing a tenth spelling is to compute nothing and report nothing. NULL is admitted and means the model did not classify the parameter, which is a different claim from classifying it as something no branch reads. The writer is promote_proposal, which takes raw model text: an element outside the nine is dropped as refused_by_invariant and the rest of the proposal is promoted.';


-- ===========================================================================
-- 3. The technology name beside it, decided open and said so
-- ===========================================================================

-- No constraint, on purpose, and the purpose is on the column so that the next
-- reader does not have to decide it again.
COMMENT ON COLUMN technologies.name IS
 'The component as it was fingerprinted. Deliberately an open set: subject_facts matches lower(name) against a sixty-nine-row list to compute nineteen tech_* facts, but that list is the readings this corpus has Playbooks for rather than a classification of anything, and a CHECK here would refuse a true observation of a component nobody listed. What the open set costs is the miss: the reading lowercases, so NGINX matches nginx, and a name carrying its version or its packager -- nginx/1.24.0, Nginx (Ubuntu) -- matches nothing and computes no fact for the eighteen Playbooks that trigger on one. The version belongs in technologies.version, which the writer fills from its own field.';


-- ===========================================================================
-- 4. The migration refuses to finish if the two sets have come apart
-- ===========================================================================

-- The property is not "a constraint exists". It is that the set the column
-- admits and the set the view computes from are the same set, and that the
-- expression really does refuse a spelling outside it. Both sides are read back
-- out of the catalogue rather than restated here, so this block would fail if
-- the `ALTER` above were edited to a tenth spelling, and would fail again the
-- day a branch is added to `subject_facts` without widening the column.
DO $$
DECLARE
    v_admitted text[];
    v_computed text[];
    v_expression text;
    v_spelling text;
    v_holds boolean;
BEGIN
    SELECT array_agg(DISTINCT m[1] ORDER BY m[1]) INTO v_admitted
      FROM pg_constraint c,
           LATERAL regexp_matches(pg_get_constraintdef(c.oid), '''([a-z_]+)''::text', 'g') m
     WHERE c.conrelid = 'parameters'::regclass
       AND c.conname = 'parameters_value_class_check';

    WITH body AS (SELECT pg_get_viewdef('subject_facts'::regclass, true) AS text),
         lines AS (SELECT unnest(string_to_array(body.text, chr(10))) AS line FROM body)
    SELECT array_agg(DISTINCT m[1] ORDER BY m[1]) INTO v_computed
      FROM lines, LATERAL regexp_matches(lines.line, '''([a-z_]+)''::text', 'g') m
     WHERE lines.line LIKE '%value_class%';

    IF v_admitted IS NULL THEN
        RAISE EXCEPTION 'parameters.value_class carries no closed set'
          USING ERRCODE = '23514';
    END IF;
    IF v_admitted IS DISTINCT FROM v_computed THEN
        RAISE EXCEPTION
            'the column admits % and subject_facts computes from %',
            v_admitted::text, coalesce(v_computed::text, 'nothing')
          USING DETAIL = 'a spelling on one side and not the other is either a '
                         'value no Playbook can be selected for or a branch no '
                         'row can ever satisfy',
                ERRCODE = '23514';
    END IF;

    -- The expression itself, evaluated rather than read. `pg_get_constraintdef`
    -- renders what the server stored, so substituting the column for a literal
    -- asks the live rule the question a writer would ask it.
    SELECT regexp_replace(pg_get_constraintdef(c.oid), '^CHECK ', '') INTO v_expression
      FROM pg_constraint c
     WHERE c.conrelid = 'parameters'::regclass
       AND c.conname = 'parameters_value_class_check';

    FOREACH v_spelling IN ARRAY v_computed LOOP
        EXECUTE 'SELECT ' || replace(v_expression, 'value_class',
                                     quote_literal(v_spelling) || '::text')
           INTO v_holds;
        IF NOT v_holds THEN
            RAISE EXCEPTION 'the column refuses %, which subject_facts computes a fact from',
                            quote_literal(v_spelling)
              USING ERRCODE = '23514';
        END IF;
    END LOOP;

    -- Three spellings a model could plausibly type, none of which computes
    -- anything: the ticket's own example, a near miss on the first of the nine,
    -- and the same word in the wrong case. A closed set that admitted these
    -- would be documentation rather than a rule.
    FOREACH v_spelling IN ARRAY ARRAY['integer', 'uuid_v4', 'UUID'] LOOP
        EXECUTE 'SELECT ' || replace(v_expression, 'value_class',
                                     quote_literal(v_spelling) || '::text')
           INTO v_holds;
        IF v_holds THEN
            RAISE EXCEPTION 'the column admits %, which computes no surface fact',
                            quote_literal(v_spelling)
              USING ERRCODE = '23514';
        END IF;
    END LOOP;

    -- And the answer the writer produces when the model classified nothing.
    EXECUTE 'SELECT ' || replace(v_expression, 'value_class', 'NULL::text') INTO v_holds;
    IF v_holds IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'an unclassified parameter is refused, which would refuse the writer''s ordinary case'
          USING ERRCODE = '23514';
    END IF;
END $$;
