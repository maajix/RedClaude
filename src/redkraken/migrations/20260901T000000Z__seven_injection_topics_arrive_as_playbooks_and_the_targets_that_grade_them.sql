-- ---------------------------------------------------------------------------
-- 20260901T000000Z__seven_injection_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql
--                                                                   (ticket 53)
--
-- Ticket 53 migrates the v1 server-side injection packs into authored v2
-- Playbooks and gives each of them a positive fixture. Twenty-seven v1 pages
-- collapse into seven readings, because v1 organised this material by dialect
-- and by escalation -- eleven pages of SQL alone, one per database and one per
-- payoff -- and a reading is not a dialect. What separates one reading here from
-- the next is which interpreter the caller's bytes reach, which is the same cut
-- 018 made when it named the injection family.
--
-- Four things happen.
--
--   1. Five surface facts -- `tech_sql`, `tech_document_store`, `tech_orm`,
--      `tech_template`, `xml_request` -- and the branches of `subject_facts`
--      that compute them. Spelled out literally for 049's reason: the
--      `fact_not_computed` rule reads the view's own definition text, and a name
--      assembled by concatenation is invisible to it.
--
--      The first four are one fact each over a family of fingerprints, for the
--      reason `tech_cdn` is: a reading that asks whether a value reached a query
--      language does not care whether the answer was MySQL or Oracle, and a
--      reading that did care would be a reading about a dialect. `xml_request`
--      joins `json_request`, `form_request` and `multipart_request` as the
--      fourth body shape, which is the one v1's XXE and XPath pages were about.
--
--   2. Three new Property classes. Four of these seven topics land on leaves 018
--      already named -- `injection.query_language`, `injection.command`,
--      `injection.template`, `injection.document_parser` -- because 018 split
--      injection by the server-side interpreter and these are exactly the
--      interpreters it had in mind. The other three are interpreters it did not
--      name: an operator rather than a value, a field name rather than a filter,
--      and a spreadsheet on somebody else's machine.
--
--   3. The seven Playbooks, as rows. Every one is `draft` for 049's reason:
--      `playbooks_stable_is_promoted` and 036's promotion guard make `stable`
--      unreachable until the evaluator has run the exact text against the
--      fixture catalogue, and no evaluation has happened yet.
--
--   4. The seven fixtures, as rows.
--
-- A new file rather than an edit to 052: a recorded migration whose file has
-- changed is schema drift and `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. Five facts, and the branches that compute them
-- ===========================================================================

-- `tech_sql`, `tech_document_store`, `tech_orm` and `tech_template` are each one
-- fact over a family of fingerprints, for the reason 052 gives at `tech_cdn`. A
-- recon pass records that Postgres or Oracle answered; what the readings here
-- need to know is that a query language is behind the route at all. The four
-- families are separate facts rather than one `tech_datastore` because they are
-- what tells four of this ticket's Playbooks apart: the same endpoint shape in
-- front of a relational database, a document store, an ORM and a template engine
-- is four different questions with four different refutations.
--
-- `xml_request` is the body shape 003's other three branches left out. A route
-- that takes XML is the route where a document parser exists to be reached, and
-- 052's corpus had no way to say so.
INSERT INTO surface_facts (id, scope, description) VALUES
 ('tech_sql','application','a relational database was identified behind the application'),
 ('tech_document_store','application','a document store or key-value database was identified behind the application'),
 ('tech_orm','application','an object-relational mapper or a framework that ships one was identified'),
 ('tech_template','application','a server-side template engine was identified'),
 ('xml_request','endpoint','the endpoint accepts an XML request body')
ON CONFLICT (id) DO NOTHING;

-- The view, restated whole because `CREATE OR REPLACE VIEW` has no way to add a
-- branch to a UNION without restating the rest. One body-shape branch is new and
-- four names join the technology block; every other branch is 052's, verbatim,
-- with the column list unchanged so the replacement is legal.
CREATE OR REPLACE VIEW subject_facts AS
WITH ep AS (
    SELECT e.id AS entity_id, e.program_id, ep.application_id, ep.method,
           ep.auth_required, ep.request_content_type
      FROM entities e JOIN endpoints ep ON ep.entity_id = e.id
     WHERE e.in_scope
)
-- endpoint shape
SELECT program_id, entity_id AS subject_entity_id, 'authenticated_endpoint'::text AS fact
  FROM ep WHERE auth_required IS TRUE
UNION ALL SELECT program_id, entity_id, 'unauthenticated_endpoint' FROM ep WHERE auth_required IS FALSE
UNION ALL SELECT program_id, entity_id, 'unknown_auth_endpoint'    FROM ep WHERE auth_required IS NULL
UNION ALL SELECT program_id, entity_id, 'state_changing_method'    FROM ep WHERE method IN ('POST','PUT','PATCH','DELETE')
UNION ALL SELECT program_id, entity_id, 'read_method'              FROM ep WHERE method IN ('GET','HEAD')
UNION ALL SELECT program_id, entity_id, 'json_request'             FROM ep WHERE request_content_type LIKE '%json%'
UNION ALL SELECT program_id, entity_id, 'form_request'             FROM ep WHERE request_content_type LIKE '%form-urlencoded%'
UNION ALL SELECT program_id, entity_id, 'multipart_request'        FROM ep WHERE request_content_type LIKE '%multipart%'
-- The new body shape, beside the three 003 had. `%xml%` catches `text/xml`,
-- `application/xml` and the `+xml` suffix types -- SOAP, Atom, SVG -- which is
-- the whole set of bodies a document parser is reached through.
UNION ALL SELECT program_id, entity_id, 'xml_request'              FROM ep WHERE request_content_type LIKE '%xml%'
-- parameters
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id,
       CASE p.location WHEN 'path' THEN 'path_parameter' WHEN 'query' THEN 'query_parameter'
                       WHEN 'body' THEN 'body_parameter' WHEN 'header' THEN 'header_parameter'
                       ELSE 'cookie_parameter' END
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'object_identifier'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id
 WHERE p.value_class IN ('uuid','integer_id','opaque_id')
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'numeric_identifier'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'integer_id'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'reflected_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.reflected IS TRUE
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'url_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'url'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'file_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'file'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'email_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'email'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'quantity_valued_parameter'
  FROM ep JOIN parameters p ON p.endpoint_id = ep.entity_id WHERE p.value_class = 'number'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'redirect_target'
  FROM ep JOIN relationships r ON r.src_entity_id = ep.entity_id AND r.type = 'redirects_to'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'flow_step'
  FROM ep JOIN relationships r ON r.dst_entity_id = ep.entity_id AND r.type = 'redirects_to'
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, 'embedded_document'
  FROM ep JOIN relationships r ON r.dst_entity_id = ep.entity_id AND r.type = 'embeds'
-- application shape
UNION ALL SELECT ep.program_id, ep.entity_id,
       CASE a.kind WHEN 'graphql' THEN 'graphql_surface' WHEN 'spa' THEN 'spa_surface'
                   WHEN 'api' THEN 'api_surface' WHEN 'web' THEN 'web_surface'
                   ELSE 'websocket_surface' END
  FROM ep JOIN applications a ON a.entity_id = ep.application_id
 WHERE a.kind IN ('graphql','spa','api','web','websocket')
-- Spelled out rather than 'tech_' || lower(t.name), for the reason 049, 050, 051
-- and 052 give at this same branch. Twenty-four names map onto four new facts
-- because a query language is one fact however it was fingerprinted, and the
-- readings that key on it do not care which vendor answered. `activerecord` and
-- `rails` both appear because a recon pass may name either the framework or the
-- mapper inside it, and the fact is the same either way.
UNION ALL SELECT DISTINCT ep.program_id, ep.entity_id, known.fact
  FROM ep JOIN relationships r ON r.src_entity_id = ep.application_id AND r.type = 'runs'
          JOIN technologies t ON t.entity_id = r.dst_entity_id
          JOIN (VALUES ('jwt',           'tech_jwt'),
                       ('oauth',         'tech_oauth'),
                       ('saml',          'tech_saml'),
                       ('soap',          'tech_soap'),
                       ('graphql',       'tech_graphql'),
                       ('grpc',          'tech_grpc'),
                       ('llm',           'tech_llm'),
                       ('webauthn',      'tech_webauthn'),
                       ('cdn',           'tech_cdn'),
                       ('cloudflare',    'tech_cdn'),
                       ('cloudfront',    'tech_cdn'),
                       ('fastly',        'tech_cdn'),
                       ('akamai',        'tech_cdn'),
                       ('varnish',       'tech_cdn'),
                       ('postgresql',    'tech_sql'),
                       ('mysql',         'tech_sql'),
                       ('mariadb',       'tech_sql'),
                       ('mssql',         'tech_sql'),
                       ('oracle',        'tech_sql'),
                       ('sqlite',        'tech_sql'),
                       ('mongodb',       'tech_document_store'),
                       ('couchdb',       'tech_document_store'),
                       ('elasticsearch', 'tech_document_store'),
                       ('redis',         'tech_document_store'),
                       ('dynamodb',      'tech_document_store'),
                       ('django',        'tech_orm'),
                       ('rails',         'tech_orm'),
                       ('prisma',        'tech_orm'),
                       ('sequelize',     'tech_orm'),
                       ('hibernate',     'tech_orm'),
                       ('activerecord',  'tech_orm'),
                       ('jinja',         'tech_template'),
                       ('twig',          'tech_template'),
                       ('freemarker',    'tech_template'),
                       ('velocity',      'tech_template'),
                       ('handlebars',    'tech_template'),
                       ('erb',           'tech_template'),
                       ('smarty',        'tech_template')) AS known(name, fact)
            ON known.name = lower(t.name)
-- program shape
UNION ALL SELECT ep.program_id, ep.entity_id, 'multiple_test_identities'
  FROM ep WHERE (SELECT count(*) FROM entities ie JOIN identities i ON i.entity_id = ie.id
                  WHERE ie.program_id = ep.program_id AND i.class = 'user'
                    AND i.invalidated_at IS NULL) >= 2
UNION ALL SELECT ep.program_id, ep.entity_id, 'privileged_identity_available'
  FROM ep WHERE EXISTS (SELECT 1 FROM entities ie JOIN identities i ON i.entity_id = ie.id
                         WHERE ie.program_id = ep.program_id AND i.class = 'privileged'
                           AND i.invalidated_at IS NULL)
UNION ALL SELECT ep.program_id, ep.entity_id, 'anonymous_identity_available'
  FROM ep WHERE EXISTS (SELECT 1 FROM entities ie JOIN identities i ON i.entity_id = ie.id
                         WHERE ie.program_id = ep.program_id AND i.class = 'anonymous'
                           AND i.invalidated_at IS NULL)
UNION ALL SELECT ep.program_id, ep.entity_id, 'tenant_boundary'
  FROM ep WHERE (SELECT count(DISTINCT r.dst_entity_id)
                   FROM entities ie JOIN identities i ON i.entity_id = ie.id
                   JOIN relationships r ON r.src_entity_id = ie.id AND r.type = 'member_of'
                  WHERE ie.program_id = ep.program_id) >= 2;


-- ===========================================================================
-- 2. Three Property classes
-- ===========================================================================

-- 018 split injection by the interpreter, "because the interpreter is the test".
-- Four of this ticket's seven land on leaves it already named. These three are
-- interpreters it did not, and each is a separate leaf for 018's stated reason --
-- the test is different in each.
--
--   `query_operator` the caller's bytes become part of the query's grammar
--                    without ever being a string. There is no quote to escape
--                    and no syntax error to provoke, so the whole of the
--                    `query_language` reading -- send a quote, watch it break --
--                    is inapplicable, and what is sent instead is a structure.
--
--   `query_field`    the caller names a stored field. The generated query is
--                    always syntactically valid, so nothing ever errors, and the
--                    signal is a change in which rows or columns came back
--                    rather than a change in whether the route worked.
--
--   `formula`        the interpreter is not on the target at all. It is the
--                    spreadsheet application on the machine of whoever opens the
--                    exported file, which is why the evidence lives in an
--                    Artifact rather than in a response.
INSERT INTO property_classes (id, family_id, name, description) VALUES
 ('injection.query_operator','injection','Query operator injection',
  'input reaches a query as an operator or a type the query language acts on, rather than as a value it compares'),
 ('injection.query_field','injection','Query field injection',
  'input decides which stored field or relation the generated query filters, orders or returns'),
 ('injection.formula','injection','Formula injection',
  'input is written into an exported document cell that a spreadsheet application will evaluate as a formula')
ON CONFLICT (id) DO NOTHING;


-- ===========================================================================
-- 3. Seven Playbooks, as rows
-- ===========================================================================

-- `version` is the digest of the projection -- what the model is handed --
-- beside `source_sha256`, which is the document.
--
-- Five are `constrained` and two are `approval_required`, and the split is not
-- about how loud the payload is. `command-directory-injection` executes a
-- process on somebody else's host even when it does nothing but wait, and
-- `spreadsheet-injection` is the one Playbook in this ticket that is not
-- `read_only`: it has to store a contact, an order line, a display name -- the
-- record has to exist before it can be exported -- so it is `mutates_object`,
-- and 032's `RISK_FLOOR` puts that no lower than `constrained` while the
-- document's own step 1 asks for the grant anyway. Everything else here reads.
--
-- Five are `stable_session` and two are `none`. The split is whether the reading
-- compares two responses that must have come from the same caller: `ssti` and
-- `structured-injection` are answered by what one response holds -- a value
-- evaluated, or a parser that reported where it stopped -- and their controls
-- compare requests sent back to back rather than a state one request left for
-- the next, so neither needs a session to persist across the comparison.
INSERT INTO playbooks (path, source_sha256, version, category, status, stale_after,
                       risk, effects, baseline, specificity, provenance) VALUES
 ('playbooks/command-directory-injection/playbook.md',
  'af58877c97ed3e1842ced481a162356067a44a6d8f32008a8d817f8169cfb2ec',
  'd1c024ea398a0780f5128d2598d5d878b6d0421df4d2f11734d0f4de3e84241a',
  'injection', 'draft', '2027-03-15T00:00:00Z',
  'approval_required', 'read_only', 'stable_session', 3,
  'Written for ticket 53 as the v2 replacement for v1''s command-directory-injection pack against the command leaf of the ticket 18 vocabulary; the pack''s five pages are attached as maintainer references, two of them (ldap-injections, xxe) describe classes graded by sql-injection and structured-injection respectively, and every escalation step in the other three is refused by step 7.'),
 ('playbooks/nosql-injection/playbook.md',
  '6171374c0df59b95db1a17782187e548a9e93549d61774bcbdc0ad7da98e1595',
  '00428b4cd4a3ceda3480ae53d36a64d0baeb8488210e3b3a6b4a36a9edad28a4',
  'injection', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 53 as the v2 replacement for v1''s nosql-injection page against a new query-operator leaf added by ticket 53; the v1 text is rewritten rather than attached, because its whole method was a payload list and the reading here is a structure sent beside an inert twin.'),
 ('playbooks/orm/playbook.md',
  '22e4c1c97771896e398e470c2630c5f5701f2f079db044fa654fe7f4d9d367c8',
  'd812c363aa4b0f8809f031aa6be600342467a34f41e8495654349b34b129b71f',
  'injection', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 53 as the v2 replacement for v1''s orm page against a new query-field leaf added by ticket 53; the v1 text is rewritten rather than attached, because it was organised by mapper and the property here is the same whichever mapper generated the query.'),
 ('playbooks/spreadsheet-injection/playbook.md',
  '0a689151c71b8ed83d28ac193301e5b2330d98182c4a4ad30d8316148bf24d52',
  '78bb0b7acbf4834d318969890b326061bad09e6cd3b23cdeacb784b683951f71',
  'injection', 'draft', '2027-03-15T00:00:00Z',
  'approval_required', 'mutates_object', 'stable_session', 3,
  'Written for ticket 53 as the v2 replacement for v1''s spreadsheet-injection page against a new formula leaf added by ticket 53; the v1 text is rewritten rather than attached, because every payload it listed executes on a reader''s machine and step 6 refuses all of them.'),
 ('playbooks/sql-injection/playbook.md',
  '1333ae44cb1879858411cfa2ab91c11e4658e377a62f935de93b2c45571fdd8a',
  'ee0fe91bf389118456460f0aad36dee05401e9ce8c2b989268ec857915fa5087',
  'injection', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'stable_session', 3,
  'Written for ticket 53 as the v2 replacement for v1''s eleven-page sqli pack against the query-language leaf of the ticket 18 vocabulary; all eleven pages are attached as maintainer references, and the extraction, stacked-query and host-reach material in them is refused by step 7 rather than summarised.'),
 ('playbooks/ssti/playbook.md',
  '83fb53e72e6e487dcb4896d57dff3f63e5e91a16d5287c61218614364070d886',
  '34287999bf49934bdce0f1b8d037aab2835a2235b66da25715ba2fc51c1cd0c8',
  'injection', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'none', 3,
  'Written for ticket 53 as the v2 replacement for v1''s ssti page against the template leaf of the ticket 18 vocabulary; the v1 text is attached as a maintainer reference and step 6''s refusal of sandbox escape is where this Playbook and that page part company.'),
 ('playbooks/structured-injection/playbook.md',
  '1e0d37e032c17942725d60a5125cc916fd13a614fcbbb9ba511f3cd140d0dddd',
  'ddca14d5bc80f6fcf1e3e09c3f93b85619c27e4b84244a2952f285b4e096e776',
  'injection', 'draft', '2027-03-15T00:00:00Z',
  'constrained', 'read_only', 'none', 3,
  'Written for ticket 53 as the v2 replacement for v1''s xpath-injections and smtp-header-injection pages against the document-parser leaf of the ticket 18 vocabulary; both v1 texts are attached as maintainer references, and entity resolution and sending mail are refused by step 6.')
ON CONFLICT (path) DO UPDATE SET
    source_sha256 = excluded.source_sha256,
    version       = excluded.version,
    category      = excluded.category,
    status        = excluded.status,
    stale_after   = excluded.stale_after,
    risk          = excluded.risk,
    effects       = excluded.effects,
    baseline      = excluded.baseline,
    specificity   = excluded.specificity,
    provenance    = excluded.provenance;

-- `specificity` above is the count of `all` rows here, and
-- `specificity_disagrees` is the database recomputing it. No Playbook in this
-- ticket declares an `any` arm, for 050's reason, and all seven carry exactly
-- three facts.
--
-- Four of the seven are told apart by the technology fact section 1 added, and
-- nothing else would do it: `sql-injection` and `orm` want the same
-- authenticated read with a query parameter, and `nosql-injection` wants the
-- same JSON body a dozen other routes have. What is behind the route is the
-- question, so what is behind the route is the trigger. The remaining three are
-- separated by the body shape instead -- a file part, an XML body, a form post --
-- because their interpreters are reached through the body rather than named by a
-- fingerprint.
INSERT INTO playbook_triggers (playbook_id, mode, fact)
SELECT p.id, v.mode, v.fact
  FROM playbooks p, (VALUES
        ('playbooks/command-directory-injection/playbook.md', 'all', 'file_parameter'),
        ('playbooks/command-directory-injection/playbook.md', 'all', 'multipart_request'),
        ('playbooks/command-directory-injection/playbook.md', 'all', 'state_changing_method'),
        ('playbooks/nosql-injection/playbook.md',             'all', 'json_request'),
        ('playbooks/nosql-injection/playbook.md',             'all', 'state_changing_method'),
        ('playbooks/nosql-injection/playbook.md',             'all', 'tech_document_store'),
        ('playbooks/orm/playbook.md',                         'all', 'authenticated_endpoint'),
        ('playbooks/orm/playbook.md',                         'all', 'query_parameter'),
        ('playbooks/orm/playbook.md',                         'all', 'tech_orm'),
        ('playbooks/spreadsheet-injection/playbook.md',       'all', 'form_request'),
        ('playbooks/spreadsheet-injection/playbook.md',       'all', 'reflected_parameter'),
        ('playbooks/spreadsheet-injection/playbook.md',       'all', 'state_changing_method'),
        ('playbooks/sql-injection/playbook.md',               'all', 'authenticated_endpoint'),
        ('playbooks/sql-injection/playbook.md',               'all', 'query_parameter'),
        ('playbooks/sql-injection/playbook.md',               'all', 'tech_sql'),
        ('playbooks/ssti/playbook.md',                        'all', 'authenticated_endpoint'),
        ('playbooks/ssti/playbook.md',                        'all', 'reflected_parameter'),
        ('playbooks/ssti/playbook.md',                        'all', 'tech_template'),
        ('playbooks/structured-injection/playbook.md',        'all', 'body_parameter'),
        ('playbooks/structured-injection/playbook.md',        'all', 'state_changing_method'),
        ('playbooks/structured-injection/playbook.md',        'all', 'xml_request'))
        AS v(path, mode, fact)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, mode, fact) DO NOTHING;

-- One class each, for 051's reason: `playbook_fixture_binding` is total over
-- `fixtures`, so two Playbooks sharing a class would each be graded `in` on the
-- other's target and neither result would say which document was right.
--
-- This is the ticket that empties 018's injection family of the server-side
-- leaves it named and nobody had claimed. `injection.query_language`,
-- `injection.command`, `injection.template` and `injection.document_parser` were
-- all written in 018 and all unclaimed until now, because every Playbook before
-- this one was about a browser, an identity or an authorisation decision.
INSERT INTO playbook_outputs (playbook_id, property_class)
SELECT p.id, v.property_class
  FROM playbooks p, (VALUES
        ('playbooks/command-directory-injection/playbook.md', 'injection.command'),
        ('playbooks/nosql-injection/playbook.md',             'injection.query_operator'),
        ('playbooks/orm/playbook.md',                         'injection.query_field'),
        ('playbooks/spreadsheet-injection/playbook.md',       'injection.formula'),
        ('playbooks/sql-injection/playbook.md',               'injection.query_language'),
        ('playbooks/ssti/playbook.md',                        'injection.template'),
        ('playbooks/structured-injection/playbook.md',        'injection.document_parser'))
        AS v(path, property_class)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, property_class) DO NOTHING;

-- `skill_sha256_at_promotion` stays NULL on every row, for 050's reason.
--
-- All seven carry `compare-responses` and `use-identity`, which is the first
-- ticket where one Skill set covers the whole set. It is what these readings
-- are: every one of them sends two requests that differ in one thing and reports
-- what changed, under a leased Identity so that the two requests came from the
-- same caller. Two carry `handle-untrusted-content` beside them, and both for the
-- same reason -- `structured-injection` reads a parser's own error text and
-- `spreadsheet-injection` reads a file the target produced, so in both the
-- material being read is the target's output rather than the reading's own.
INSERT INTO playbook_skills (playbook_id, skill_name)
SELECT p.id, v.skill_name
  FROM playbooks p, (VALUES
        ('playbooks/command-directory-injection/playbook.md', 'compare-responses'),
        ('playbooks/command-directory-injection/playbook.md', 'use-identity'),
        ('playbooks/nosql-injection/playbook.md',             'compare-responses'),
        ('playbooks/nosql-injection/playbook.md',             'use-identity'),
        ('playbooks/orm/playbook.md',                         'compare-responses'),
        ('playbooks/orm/playbook.md',                         'use-identity'),
        ('playbooks/spreadsheet-injection/playbook.md',       'compare-responses'),
        ('playbooks/spreadsheet-injection/playbook.md',       'handle-untrusted-content'),
        ('playbooks/spreadsheet-injection/playbook.md',       'use-identity'),
        ('playbooks/sql-injection/playbook.md',               'compare-responses'),
        ('playbooks/sql-injection/playbook.md',               'use-identity'),
        ('playbooks/ssti/playbook.md',                        'compare-responses'),
        ('playbooks/ssti/playbook.md',                        'use-identity'),
        ('playbooks/structured-injection/playbook.md',        'compare-responses'),
        ('playbooks/structured-injection/playbook.md',        'handle-untrusted-content'),
        ('playbooks/structured-injection/playbook.md',        'use-identity'))
        AS v(path, skill_name)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, skill_name) DO NOTHING;

-- Three rows each: what refutes, what the control has to show, and what the
-- claim itself rests on.
--
-- Six of the seven refute with a `response_invariant` on the variant leg, and
-- that is the shape of this whole ticket: the payload went in, the route
-- answered exactly as it answers without it, and nothing parsed anything. It is
-- the strongest answer available here, and it is why every one of these
-- documents sends an inert twin rather than a payload alone.
--
-- The supported kinds are five, because these readings are answered in five
-- different places.
--
--   `response_differential`  `sql-injection`, `nosql-injection`, `orm`. All
--                            three are answered by which rows came back, which
--                            is a difference between two bodies.
--   `reflected_input`        `ssti`. The claim is that a value was evaluated
--                            rather than copied, so what is cited is what came
--                            back where the value was put.
--   `timing_differential`    `command-directory-injection`. The channel a
--                            converter usually leaves open is duration, and the
--                            claim is a separation between two sampled sets.
--   `error_detail`           `structured-injection`. A parser that reports where
--                            it stopped is the finding: the offset moved with
--                            the payload, which says the caller's bytes were
--                            parsed as document rather than held as text.
--   `content_match`          `spreadsheet-injection`, and it is the one kind
--                            here whose only allowed provenance is a tool run.
--                            That is the honest source: the evidence is a cell
--                            inside a downloaded export, and what says the cell
--                            is there is a run over the Artifact rather than a
--                            response body.
INSERT INTO playbook_evidence
        (playbook_id, to_status, role, observation_kind, polarity, min_count)
SELECT p.id, v.to_status, v.role, v.kind, v.polarity, v.min_count
  FROM playbooks p, (VALUES
        ('playbooks/command-directory-injection/playbook.md', 'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/command-directory-injection/playbook.md', 'supported', 'control', 'response_invariant',    'supports', 1),
        ('playbooks/command-directory-injection/playbook.md', 'supported', 'variant', 'timing_differential',   'supports', 1),
        ('playbooks/nosql-injection/playbook.md',             'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/nosql-injection/playbook.md',             'supported', 'control', 'response_invariant',    'supports', 1),
        ('playbooks/nosql-injection/playbook.md',             'supported', 'variant', 'response_differential', 'supports', 1),
        ('playbooks/orm/playbook.md',                         'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/orm/playbook.md',                         'supported', 'control', 'response_invariant',    'supports', 1),
        ('playbooks/orm/playbook.md',                         'supported', 'variant', 'response_differential', 'supports', 1),
        ('playbooks/spreadsheet-injection/playbook.md',       'refuted',   'variant', 'content_match',         'refutes',  1),
        ('playbooks/spreadsheet-injection/playbook.md',       'supported', 'control', 'content_match',         'supports', 1),
        ('playbooks/spreadsheet-injection/playbook.md',       'supported', 'variant', 'content_match',         'supports', 1),
        ('playbooks/sql-injection/playbook.md',               'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/sql-injection/playbook.md',               'supported', 'control', 'response_invariant',    'supports', 1),
        ('playbooks/sql-injection/playbook.md',               'supported', 'variant', 'response_differential', 'supports', 1),
        ('playbooks/ssti/playbook.md',                        'refuted',   'variant', 'reflected_input',       'refutes',  1),
        ('playbooks/ssti/playbook.md',                        'supported', 'control', 'reflected_input',       'supports', 1),
        ('playbooks/ssti/playbook.md',                        'supported', 'variant', 'reflected_input',       'supports', 1),
        ('playbooks/structured-injection/playbook.md',        'refuted',   'variant', 'response_invariant',    'refutes',  1),
        ('playbooks/structured-injection/playbook.md',        'supported', 'control', 'response_invariant',    'supports', 1),
        ('playbooks/structured-injection/playbook.md',        'supported', 'variant', 'error_detail',          'supports', 1))
        AS v(path, to_status, role, kind, polarity, min_count)
 WHERE p.path = v.path
ON CONFLICT (playbook_id, to_status, role, observation_kind) DO NOTHING;

-- The material the model never gets. Twenty files behind four Playbooks;
-- `nosql-injection`, `orm` and `spreadsheet-injection` have nothing attached
-- because their v1 pages were rewritten rather than absorbed, and a reference to
-- a page whose method this Playbook rejects would be a reference that argues with
-- the document holding it. Recorded so a maintainer can find them and hashed so a
-- maintainer can tell whether they moved.
--
-- Two of the five under `command-directory-injection` describe classes this
-- Playbook does not grade: `ldap-injections.md` is `injection.query_language` and
-- `xxe.md` is `injection.document_parser`. They are attached here because that is
-- where v1's pack put them and the disposition ledger records where each v1 page
-- went, not where its subject is graded. Each note says so in its own text, and
-- step 6 of the Playbook names the right document for both.
INSERT INTO playbook_references (playbook_id, name, path, sha256)
SELECT p.id, v.name, v.path, v.sha256
  FROM playbooks p, (VALUES
        ('playbooks/command-directory-injection/playbook.md', 'command-injection-filter-bypass.md',
         'playbooks/command-directory-injection/references/command-injection-filter-bypass.md',
         '24cd62262101c8c27ea45a577c1cef335c014a95b81016c3ce152003eb4ba315'),
        ('playbooks/command-directory-injection/playbook.md', 'ldap-injections.md',
         'playbooks/command-directory-injection/references/ldap-injections.md',
         '36eff3c63ecf0b85f5b1e57195238ce316c351ce76269b05568cd62ab7372fcd'),
        ('playbooks/command-directory-injection/playbook.md', 'os-command-injection.md',
         'playbooks/command-directory-injection/references/os-command-injection.md',
         '0a453e39dabe9c5fffab479a252c344fde6fa3b2f9494bae2ebf84300ad2f2d3'),
        ('playbooks/command-directory-injection/playbook.md', 'shells.md',
         'playbooks/command-directory-injection/references/shells.md',
         '3286a9b8f65d8f4249a569837c5a22d823e120f45a82c501cfd9b9cefb60ea2a'),
        ('playbooks/command-directory-injection/playbook.md', 'xxe.md',
         'playbooks/command-directory-injection/references/xxe.md',
         'c754a378bb56c0138c5092f7aae5f9beeca40bfb7370083cebe8601c9250bfc9'),
        ('playbooks/sql-injection/playbook.md', 'sqli-advanced-sqli-techniques.md',
         'playbooks/sql-injection/references/sqli-advanced-sqli-techniques.md',
         'b8c61cbbb63828115e44bb19c246f1987f6ef5205e0579d02436fc7e20fbb8fa'),
        ('playbooks/sql-injection/playbook.md', 'sqli-advanced-sqlmap.md',
         'playbooks/sql-injection/references/sqli-advanced-sqlmap.md',
         'a9bb8b032d69cf438472aa044d3d837146f9f3eeceafafb08b2de4fea23af7f1'),
        ('playbooks/sql-injection/playbook.md', 'sqli-blind-sql-injection.md',
         'playbooks/sql-injection/references/sqli-blind-sql-injection.md',
         '2da2d58f9f4e828a785b0f8c302ed2c287b45361656f6a9a74ec1333382af6c6'),
        ('playbooks/sql-injection/playbook.md', 'sqli-custom-tampering.md',
         'playbooks/sql-injection/references/sqli-custom-tampering.md',
         '1b79d0e925f21cbd4820f98cb6fcd33c6ab1c3e08ae43c0bc24b32d94014a256'),
        ('playbooks/sql-injection/playbook.md', 'sqli-identifying-vulnerabilities.md',
         'playbooks/sql-injection/references/sqli-identifying-vulnerabilities.md',
         '04847bb9cd1c45ad1984005530b75751297115e044c9e0f7f5f2671cdda8a284'),
        ('playbooks/sql-injection/playbook.md', 'sqli-intro-to-mssql-sql-server.md',
         'playbooks/sql-injection/references/sqli-intro-to-mssql-sql-server.md',
         '2f8f3f0abe892f79d7f482ea02bb9967638b2f76a52615ddf89b97e2697c9903'),
        ('playbooks/sql-injection/playbook.md', 'sqli-leaking-netntlm-hashes.md',
         'playbooks/sql-injection/references/sqli-leaking-netntlm-hashes.md',
         '98a5c2584d114f79a5e67ad8a2ff82394298dfc7f621e2331ca38aa2fb1d774c'),
        ('playbooks/sql-injection/playbook.md', 'sqli-out-of-band-dns.md',
         'playbooks/sql-injection/references/sqli-out-of-band-dns.md',
         '2dc8a4d18d63a9182dc49574ae020ad04013048d08c418bb723c9a51d276dae9'),
        ('playbooks/sql-injection/playbook.md', 'sqli-postgresql-specific-techniques.md',
         'playbooks/sql-injection/references/sqli-postgresql-specific-techniques.md',
         '5f9a350fd9f128e0edb96358c8d09babd6680dfdcfb86bf0761b48366e8116e3'),
        ('playbooks/sql-injection/playbook.md', 'sqli-remote-code-execution.md',
         'playbooks/sql-injection/references/sqli-remote-code-execution.md',
         'f1d891214a4903ebc5e3382a79837248df3c250f15b421d95eed0a09439d59ff'),
        ('playbooks/sql-injection/playbook.md', 'sqli-time-based-sqli.md',
         'playbooks/sql-injection/references/sqli-time-based-sqli.md',
         '95a78684e4588cbfaaee4f5c61fbf8799c15c941184ab9b622270f39d71a92f5'),
        ('playbooks/sql-injection/playbook.md', 'sqli.md',
         'playbooks/sql-injection/references/sqli.md',
         '0166afe459556b4e16c79b0fc65af54e714b5b3baf61a2e8d0d261bcc5008bd6'),
        ('playbooks/ssti/playbook.md', 'ssti.md',
         'playbooks/ssti/references/ssti.md',
         'a2a6763d3a81a71899dccf9a6bd1c60e13b709245b1b363459edbb62047fd141'),
        ('playbooks/structured-injection/playbook.md', 'smtp-header-injection.md',
         'playbooks/structured-injection/references/smtp-header-injection.md',
         'ca62f8075acdb4066ac09cb7ffeba5cd123144255d560e73927e664b59df8412'),
        ('playbooks/structured-injection/playbook.md', 'xpath-injections.md',
         'playbooks/structured-injection/references/xpath-injections.md',
         '6a8035468173aec5c05533a45226b0a9f9e6f61bc47553016488af460ef0350c'))
        AS v(playbook_path, name, path, sha256)
 WHERE p.path = v.playbook_path
ON CONFLICT (playbook_id, name) DO NOTHING;


-- ===========================================================================
-- 4. Seven targets, as rows
-- ===========================================================================

-- One positive per topic, each written from the class description rather than
-- from the Playbook's steps. `playbook_fixture_binding()` is total over this
-- table, so every one of these is also an out-of-class negative for the other
-- thirty-four Playbooks -- which is why nothing here declares a class it does not
-- hold, and why each ground truth spends most of its length saying which
-- neighbouring class is deliberately absent and what in the source keeps it out.
--
-- Every one carries two precision controls beside its secure twin, which is new
-- in this ticket and is what criterion 5 asks for. The first is a noisy endpoint
-- whose body changes on every request, so a reading that never established what
-- "the same response" looks like has a route it can be wrong about. The second is
-- a decoy that reflects the payload and interprets nothing, so a reading that
-- treats a reflection as an interpreter has a route it can be wrong about. Seven
-- of these Playbooks are about differencing two responses, and those are the two
-- ways differencing goes wrong.
--
-- `formula-pair` is the one graded on something no response body carries. Both
-- halves store the same bytes and acknowledge them identically; the difference is
-- one call in the export writer, which is why the evidence is a match inside a
-- downloaded Artifact.
INSERT INTO fixtures (id, kind, path, source_sha256, ground_truth_sha256) VALUES
 ('command-pair', 'own_pair',
  'fixtures/command-pair/fixture.md',
  '5f051d52f90b87da826c6064f338ac912e016498eb488c70ef4e26d962cb31b0',
  '3acbe8b1a130ef8f7e246ebd7db027531908463593913c47de3d96afa5553e3d'),
 ('document-parser-pair', 'own_pair',
  'fixtures/document-parser-pair/fixture.md',
  '2304cde5a893aacef8e555b501c40ce3ba16a1651c6ac488bc44e2d604396c27',
  '1841aba6bc4e86fa6f6c20f4ca02122024826725a291c29c9f12cdecfef934cb'),
 ('formula-pair', 'own_pair',
  'fixtures/formula-pair/fixture.md',
  'bac85f7474eaba5b5d95a7ea7744ada58a8e21c25236ed307a4953772304cdea',
  'bfe32e4b1f3ff51e43e608eeb83710c03590f9e8ab8a5cb4349ab222f9dd18b8'),
 ('query-field-pair', 'own_pair',
  'fixtures/query-field-pair/fixture.md',
  'b7e504e5e6af0efddc700c6f66f09e50fdd41242bcaefbd3a95ca039028f6fbc',
  '30a8fdfc73eadfab04c251d42fb223c28231b171e243d80dd8938e652256e527'),
 ('query-language-pair', 'own_pair',
  'fixtures/query-language-pair/fixture.md',
  'b7ecf766b9ffb62f5141b855b831812d5aefa19f28545ec306d28eb155802a51',
  '6d3097e41c18f1294533fdffd623903275dadb4558e7eab12a2738d77a219535'),
 ('query-operator-pair', 'own_pair',
  'fixtures/query-operator-pair/fixture.md',
  '16c89c43d695838ac1b124b244ed76ebef523355d907d1e569ab754d884a6620',
  '51184eb0db99fa27e3b2584fd3acf275bc1fd26835d0d3f4e57d1ac3e1bf369c'),
 ('template-pair', 'own_pair',
  'fixtures/template-pair/fixture.md',
  'bd1545d027100f733cbc6f43bc995b8b7bca5727d075f948b0dc1b0a640dd8b9',
  '21d2f067b74d1b27e45f3bdf872770219f197a65f6fbf6dfe76991a8a9ede8b5')
ON CONFLICT (id) DO UPDATE SET
    kind                = excluded.kind,
    path                = excluded.path,
    source_sha256       = excluded.source_sha256,
    ground_truth_sha256 = excluded.ground_truth_sha256;

-- One class each, for 050's reason.
INSERT INTO fixture_classes (fixture_id, property_class) VALUES
 ('command-pair',         'injection.command'),
 ('document-parser-pair', 'injection.document_parser'),
 ('formula-pair',         'injection.formula'),
 ('query-field-pair',     'injection.query_field'),
 ('query-language-pair',  'injection.query_language'),
 ('query-operator-pair',  'injection.query_operator'),
 ('template-pair',        'injection.template')
ON CONFLICT (fixture_id, property_class) DO NOTHING;
