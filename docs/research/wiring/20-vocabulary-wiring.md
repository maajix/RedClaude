# 20 — The vocabulary: every declared value nothing produces or nothing consumes

Sweep axis: the vocabulary tables. Read-only audit. Every claim carries a
`file:line` or the SQL that produced it. Lists are exhaustive, not illustrative.

Every row is graded one of two ways:

- **harmless** — the value is unused, and nothing in the corpus or the schema
  promises it will work. Deleting it would change no behaviour.
- **promised** — something the harness ships (playbook prose, a skill pack, a
  view branch, a generated column) tells a reader or a model this value is
  live, and it is not. This is the defect class the sweep exists to find.

## 0. The reading, and a caveat about the database that was handed to me

The database at `127.0.0.1:55433/rk2probe` **is stale**. It has 135 of the 139
migration files applied:

```sql
SELECT count(*) FROM rk2_meta.schema_migrations;   -- 135
```
```
$ ls src/redkraken/migrations/*.sql | wc -l          # 139
```

Missing, in order: `20260922T040000Z__a_route_template_names_its_own_method`,
`20260922T050000Z__a_bad_wait_fails_more_missions_than_a_bad_selector`,
`20260922T060000Z__a_fixture_may_own_its_own_handshake`,
`20260923T000000Z__the_runtime_takes_its_own_transport_measurement`.

The two that matter to this axis are the last two, and they change the answer
to section 2. I therefore cloned the probe and applied the four missing files
in the runner's own frame (`SET LOCAL ROLE rk2_owner`, `set_actor('runtime', …)`,
matching `migrate._apply`, `src/redkraken/migrate.py:660-688`). All four applied
clean. **Every query below was run against that database, `rk2vocab`**, which
is the full 139-migration corpus.

The vocabulary delta between the two databases is exactly one fixture:

```sql
-- run against both, diffed
SELECT id FROM fixtures;                       -- rk2vocab adds tls-configuration-pair
SELECT fixture_id, property_class FROM fixture_classes;
                                               -- rk2vocab adds (tls-configuration-pair, transport.tls_configuration)
SELECT id FROM property_classes;               -- identical, 57
SELECT id FROM observation_kinds;              -- identical, 16
SELECT id FROM surface_facts;                  -- identical, 55
SELECT property_class, makeability FROM transport_makeability;  -- identical
```

Corpus size confirmed on `rk2vocab`: 57 property classes, 16 observation kinds,
55 surface facts, 50 playbooks, 55 fixtures, 50 `playbook_outputs`, 139
`playbook_triggers`, 150 `playbook_evidence`, 55 `fixture_classes`.

Note the shape this imposes: **`playbook_outputs` has exactly 50 rows for 50
playbooks.** Every playbook declares exactly one output class. There is no
many-to-one anywhere, so "classes covered by the corpus" is capped at 50 of 57
by construction.

---

## 1. Property classes nobody emits

```sql
SELECT pc.id
  FROM property_classes pc
 WHERE NOT EXISTS (SELECT 1 FROM playbook_outputs po
                    WHERE po.property_class = pc.id)
 ORDER BY pc.id;
```

Seven rows. "Prose" is `grep -rn '<class>' src/redkraken/playbooks/ src/redkraken/skills/`.

| value | declared where | produced by | consumed by | verdict |
|---|---|---|---|---|
| `authentication.recovery_flow` | `src/redkraken/migrations/0018_vocabularies.sql:105` | **nothing** — no `playbook_outputs` row | `fixture_classes` (`recovery-flow-pair`), `property_class_vulnerability_classes` → `weak_credential_recovery` (`0034_reports.sql:149`) | **promised.** `src/redkraken/playbooks/authentication/playbook.md:101` tells the reader "the enrolment and recovery paths are their own class, `authentication.recovery_flow`"; `references/http-attacks-password-reset.md:8` says "Reset is a real class"; `references/type-juggling.md:55` routes to it. Three files send work to a class no playbook can claim. A fixture exists to grade it and nothing can be graded. |
| `information_disclosure.identifier_oracle` | `0018_vocabularies.sql:127` | **nothing** | `fixture_classes` (`identifier-oracle-pair`), `surface_delta_property_classes` (2 kinds), `property_class_vulnerability_classes` → `sensitive_data_exposure` (`0034_reports.sql:162`) | **promised, worst case.** Five corpus files name it: `playbooks/api-authorization/references/idor.md:52`, `playbooks/api-authorization/references/uuids.md:52`, `playbooks/authentication/references/sign-up-login-register.md:29`, `playbooks/race-conditions/references/race-conditions-and-timing-attacks.md:21`, and `skills/analyse-source/references/sinks-go.md:86` — where it is a **top-level `##` sink heading**, i.e. the analyst skill teaches the model to identify sinks for a class no playbook will ever open a hypothesis in. |
| `rate_limiting.per_origin` | `0018_vocabularies.sql:146` | **nothing** | `fixture_classes` (`per-origin-limit-pair`), vuln map → `resource_exhaustion` | **promised.** `playbooks/api/playbook.md:82` names it as the class the `api` playbook cannot claim, implying a sibling that can. There is none. |
| `rate_limiting.resource_cost` | `0018_vocabularies.sql:148` | **nothing** | `fixture_classes` (`resource-cost-pair`), vuln map → `resource_exhaustion` | **promised.** Three files: `playbooks/graphql/playbook.md:82` ("…is `rate_limiting.resource_cost`, and this Playbook may not claim it"), `playbooks/graphql/references/api-graphql.md:37`, `playbooks/api/references/rate-limit-bypass.md:36` ("Note the class: this is `rate_limiting.resource_cost`, not `per_identity`"). Three explicit hand-offs to nobody. |
| `transport.certificate_trust` | `0018_vocabularies.sql:167` | **nothing** | `transport_makeability` = `probe_only` (`0025_transport_claims.sql:211`), vuln map → `certificate_validation`. **No fixture.** | **promised.** `playbooks/http-desync/playbook.md:110` names it as "a different leaf with its own" handling. It became technically makeable on 2026-09-23 when `record_transport_measurement` shipped (`src/redkraken/proxy.py:1037`, migration `20260923T000000Z`), and no playbook, no fixture and no evidence declaration followed. This is a capability wired at the bottom and nowhere else. |
| `transport.request_framing` | `0025_transport_claims.sql:170` | **nothing** | `transport_makeability` = `unmakeable` with mechanism (`0025_transport_claims.sql:222`). No fixture, no vuln map. | **harmless by design.** `0025` declares it structurally unmakeable behind the interception proxy, and a trigger refuses a claim in it at INSERT. Five corpus files name it (`playbooks/api-authorization/references/idor.md:61`, `playbooks/routing/references/status-code-bypass.md:50`, `playbooks/routing/references/http-attacks-verb-tampering.md:43`, `playbooks/http-desync/references/http-attacks-request-smuggling-and-http-desync.md:25`, `playbooks/http-desync/references/http-attacks-http-2-downgrading.md:27`) and **each names it together with `unmakeable`** — the corpus tells the truth about it, which is what makes it harmless rather than promised. |
| `transport.datagram_transport` | `0025_transport_claims.sql:172` | **nothing** | `transport_makeability` = `unmakeable` (`0025_transport_claims.sql:229`). No fixture, no vuln map, **zero corpus mentions**. | **harmless.** Declared unmakeable, named nowhere. The only genuinely inert row in the table. |

### 1b. The reverse consumption gap on the same table: retest triggers

`rk2_negative_relevant_deltas()` (`src/redkraken/migrations/20260814T080000Z__a_refutation_is_kept_and_made_due.sql:569-592`) is what puts a recorded refutation back in the queue when the surface moves. It **inner-joins** `surface_delta_property_classes`:

```sql
JOIN surface_delta_property_classes pc
  ON pc.kind = d.kind AND pc.property_class_id = n.property_class
```

```sql
SELECT count(*) FROM property_classes pc
 WHERE NOT EXISTS (SELECT 1 FROM surface_delta_property_classes s
                    WHERE s.property_class_id = pc.id);           -- 39
```

Thirty-nine of fifty-seven classes have no row. A refutation recorded in any of
them is **never** made due again, whatever changes on the target. The mapping
was seeded on 2026-08-13 (`20260813T140000Z__the_surface_gets_a_fingerprint.sql:328-390`),
covering the 18 classes that existed with playbooks then; the 43 playbook
classes that arrived from 2026-08-26 onward never extended it.

The 39: `authentication.factor_enforcement`, `authentication.federation_trust`,
`authentication.recovery_flow`, `authorization.channel_subscription`,
`authorization.edge_rule`, `authorization.parallel_route`,
`authorization.state_transition`, `business_logic.quantity_or_price`,
`business_logic.replay`, `business_logic.workflow_order`,
`information_disclosure.artifact_exposure`, `information_disclosure.cached_response`,
`information_disclosure.client_storage`, `information_disclosure.credential_material`,
`information_disclosure.dependency_manifest`, `information_disclosure.excess_field`,
`information_disclosure.log_record`, `information_disclosure.undeclared_field`,
`information_disclosure.workload_metadata`, `injection.client_channel`,
`injection.client_path`, `injection.foreign_resource`, `injection.formula`,
`injection.model_instruction`, `injection.object_graph`,
`injection.parameter_precedence`, `injection.query_field`,
`injection.query_operator`, `injection.stored_file`, `injection.url_authority`,
`rate_limiting.per_origin`, `rate_limiting.resource_cost`,
`session_handling.cross_origin_read`, `session_handling.fixation`,
`session_handling.lifetime`, `transport.certificate_trust`,
`transport.datagram_transport`, `transport.request_framing`,
`transport.tls_configuration`.

**Verdict: promised** for the 36 of these that a playbook emits — the harness
ships a retest lane, the playbook produces claims, and the two are not
connected. Harmless for `transport.datagram_transport` and
`transport.request_framing` (unmakeable) and neutral for
`rate_limiting.per_origin` / `.resource_cost` / `authentication.recovery_flow`
(nothing emits them anyway; already counted in section 1).

### 1c. A second consumer gap on the same table, which is *not* a defect

```sql
SELECT count(*) FROM property_classes pc
 WHERE NOT EXISTS (SELECT 1 FROM property_class_vulnerability_classes v
                    WHERE v.property_class_id = pc.id);           -- 24
```

Twenty-four classes have no CWE/vulnerability-class mapping. **Harmless, and
explicitly so:** `0034_reports.sql:130-134` — "It is advisory — it drives
`finding_class_divergence`, which is a review signal, not a constraint. …a leaf
with no row here asks no question." Recorded here so a future sweep does not
re-flag it.

---

## 2. Property classes emitted but ungradeable

The binding is `playbook_fixture_binding(uuid)` (`20260914T000000Z__a_fixture_is_reached_by_address_not_by_name.sql:360-372`, superseding `20260824T000000Z…:405-415`); it is total over `fixtures` and marks a fixture `in` when the fixture declares a class the playbook outputs.

```sql
SELECT p.path,
       count(*) FILTER (WHERE b.side = 'in')  AS in_pair,
       count(*) FILTER (WHERE b.side = 'out') AS out_pair
  FROM playbooks p, LATERAL playbook_fixture_binding(p.id) b
 GROUP BY p.path ORDER BY in_pair;
```

| value | declared where | produced by | consumed by | verdict |
|---|---|---|---|---|
| *(none — on the full 139-migration corpus)* | — | — | — | Minimum `in_pair` across all 50 playbooks is **1**. Every emitted class has at least one fixture declaring it. |
| `transport.tls_configuration` **on the stale `rk2probe`** | `0018_vocabularies.sql:165` | `playbooks/http-desync/playbook.md:4` (`bb:outputs`) | zero `fixture_classes` rows → `in_pair = 0` → `playbook_test_verdict` stuck at `untested` → `playbooks_stable_is_promoted` unreachable | **Was promised; fixed 2026-09-22.** `20260922T060000Z__a_fixture_may_own_its_own_handshake.sql:1-48` is the fix and names the defect in its own words: "`playbook_fixture_binding` yielded an empty in-pair side and `playbook_test_verdict` stopped at `untested` for it on every run". It shipped `tls-configuration-pair` served over HTTPS via a second fixture entry point `tls(variant, context)`. **This is the one instance of this defect class that the harness has actually closed, and it took the schema-level `fixture_addresses.protocol` CHECK to move with it.** It is listed here because it is invisible on the database that was handed to me. |

### 2b. The other side of the same join: fixtures that can never grade anybody

```sql
SELECT fc.fixture_id, fc.property_class
  FROM fixture_classes fc
 WHERE NOT EXISTS (SELECT 1 FROM playbook_outputs po
                    WHERE po.property_class = fc.property_class);
```

| value | declared where | produced by | consumed by | verdict |
|---|---|---|---|---|
| `identifier-oracle-pair` → `information_disclosure.identifier_oracle` | `20260826T000000Z…sql` / `fixture_classes` | the fixture corpus | **no playbook** — always `out` for all 50 | **promised.** A graded pair was built, shipped, hashed twice (`source_sha256`, `ground_truth_sha256`) and can only ever serve as an out-of-class negative. |
| `per-origin-limit-pair` → `rate_limiting.per_origin` | same | same | **no playbook** | **promised**, same reason. |
| `recovery-flow-pair` → `authentication.recovery_flow` | same | same | **no playbook** | **promised**, same reason. |
| `resource-cost-pair` → `rate_limiting.resource_cost` | same | same | **no playbook** | **promised**, same reason. |

Four of 55 fixtures — 7% of the graded-target corpus — exist to grade classes
nobody emits. They are the mirror image of section 1: the fixture author
believed a playbook would follow, and none did.

---

## 3. Observation kinds nothing writes and nothing cites

Two separate questions, and the answers are sharply different.

**Written by machine code.** Grepping every observation-kind id as a Python
string literal across `src/redkraken/*.py` returns **zero hits for all sixteen**.
Observations are written by SQL functions only:

- `promote_proposal()` — `20260814T070000Z__a_proposal_becomes_a_canonical_hypothesis.sql:1631` (and its superseded twins `20260813T090000Z…:1273`, `20260812T070000Z…:273`). `kind` is `v_element ->> 'kind'`, i.e. **whatever the model typed**, FK-checked against `observation_kinds` and nothing more.
- Replay lane — `20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1063-1078` and `20260815T000000Z__a_test_runs_through_the_replay_lane.sql:1790-1806`. Hardcoded two-way choice: `response_differential` if a `status_differs`/`body_differs` assertion names the action, else `response_invariant`.
- Callback arrival — `20260910T000000Z__an_arrival_resolves_to_one_interaction.sql:262-274` (and `20260912T000000Z…:746`, `20260812T040000Z…:759`). Hardcodes `'callback_interaction'`.

So **exactly three** of sixteen kinds are written by code the harness controls.
The other thirteen exist only if a model types the string.

**Cited by `bb:evidence`.**
```sql
SELECT ok.id, ok.is_evidential, array_to_string(ok.allowed_provenance,','),
       (SELECT count(DISTINCT pe.playbook_id) FROM playbook_evidence pe
         WHERE pe.observation_kind = ok.id)
  FROM observation_kinds ok ORDER BY ok.is_evidential DESC, ok.id;
```

| value | declared where | produced by | consumed by (playbooks citing it) | verdict |
|---|---|---|---|---|
| `response_invariant` | `0018_vocabularies.sql:221` | replay lane, hardcoded | 40 | written **and** cited |
| `response_differential` | `0018_vocabularies.sql:219` | replay lane, hardcoded | 21 | written **and** cited |
| `callback_interaction` | `20260812T040000Z…:349` | `resolve_callback_arrival`, hardcoded | 1 (`webhooks`) | written **and** cited |
| `credential_effect` | `0018_vocabularies.sql:231` | model string only | 17 | **cited, not written by code.** Named in 18 corpus files. |
| `content_match` | `0018_vocabularies.sql:233` | model string only | 9 | cited, not written by code. 9 corpus files. |
| `state_change` | `0018_vocabularies.sql:229` | model string only | 6 | cited, not written by code. 7 corpus files. |
| `header_policy_observed` | `0018_vocabularies.sql:235` | model string only | 3 | cited, not written by code. 3 corpus files. |
| `reflected_input` | `0018_vocabularies.sql:225` | model string only | 3 | cited, not written by code. 4 corpus files. |
| `error_detail` | `0018_vocabularies.sql:227` | model string only | 2 | cited, not written by code. 22 corpus files. |
| `timing_differential` | `0018_vocabularies.sql:223` | model string only | 1 | cited, not written by code. 3 corpus files. |
| `transport_parameters_observed` | `0025_transport_claims.sql:250` | model string only; its **provenance** is now machine-written (`record_transport_measurement`, `src/redkraken/proxy.py:1037`, `20260923T000000Z…`) | 1 (`http-desync`, all three rows — `20260904T000000Z…:444-446`) | **cited; provenance wired 2026-09-23, observation still not.** Gated hardest of any kind: `0025_transport_claims.sql:304` and `:373` require a `transport_citable` receipt and a field-by-field match of `metadata.transport` against the receipt's `wire_*` columns. |
| `artifact_captured` | `0018_vocabularies.sql:248` | model string only | **0** | **neither written nor cited. Harmless** — `is_evidential = false`, and `enforce_evidential_kind()` (`0018_vocabularies.sql:448-470`) refuses it in `hypothesis_evidence` for any role but `context`. Zero corpus files name it. |
| `endpoint_discovered` | `0018_vocabularies.sql:240` | model string only | **0** | neither. **Harmless**, same reason. Zero corpus files. |
| `identity_established` | `0018_vocabularies.sql:246` | model string only | **0** | neither. **Harmless**, same reason. Zero corpus files. |
| `parameter_discovered` | `0018_vocabularies.sql:242` | model string only | **0** | neither. **Harmless**, same reason. Zero corpus files. |
| `technology_identified` | `0018_vocabularies.sql:244` | model string only | **0** | neither. **Harmless** as evidence, but 5 corpus files name it, so it *is* reachable as a `context` citation. |

Three-way roll-up: **3 written-and-cited**, **8 cited-but-written-only-by-a-model-string**,
**5 neither** (and all five neither are exactly the five `is_evidential = false`
rows, which is a coherent design rather than rot).

### 3b. The load-bearing finding on this axis: the enum is built and never served

`0018_vocabularies.sql:515-557` builds three functions whose entire stated
purpose is to hand these vocabularies to the model:

```
-- Both layers read from these tables. `mcp_enum()` is what the MCP server calls
-- at startup to build the schema, so the enum cannot drift from the FK.
CREATE FUNCTION mcp_enum(p_vocabulary text) RETURNS jsonb ...
CREATE FUNCTION mcp_enum_described(p_vocabulary text) RETURNS jsonb ...
```
plus `mcp_transport_makeability()` (`0025_transport_claims.sql`, granted the same way).

```
$ grep -rn "mcp_enum\|mcp_transport_makeability" src/redkraken/*.py tests/ tools/ | wc -l
0
```

All three are `GRANT EXECUTE … TO rk2_runtime` and **have zero callers anywhere
outside the migration that created them.** The tool that would use them,
`mcp__rk2__submit_mission_result`, declares its element lists as
`Argument("array", free_text=True)` with no enum at all —
`src/redkraken/roster.py:670-684`, with the comment at `:659-669` stating the
element lists "stay open because a proposal is raw model output".

**Verdict: promised.** The schema comment says the MCP server calls this at
startup. It does not. This is the mechanism that would have prevented every
other row in this report, built in migration 018 and never connected.

---

## 4. Surface facts nothing produces or nothing consumes

**The producer side is already gated.** `check_playbook_integrity()` has a HARD
rule `fact_not_computed` that fails any `surface_facts` row not appearing in
`pg_get_viewdef('subject_facts')` (`0032_playbooks.sql:577-579`, current text
in `20260823T000000Z…:658-660`).

```sql
SELECT f.id FROM surface_facts f
 WHERE position((''''||f.id||'''') IN pg_get_viewdef('subject_facts'::regclass)) = 0;
-- 0 rows
SELECT * FROM check_playbook_integrity();
-- 0 rows
```

All 55 facts have a branch in `subject_facts` (live definition last replaced by
`20260903T000000Z__five_platform_and_supply_chain_topics…sql:76-224`).

### 4a. Triggers no playbook lists — produced, not consumed

```sql
SELECT sf.id, sf.scope FROM surface_facts sf
 WHERE NOT EXISTS (SELECT 1 FROM playbook_triggers pt WHERE pt.fact = sf.id);
```

| value | declared where | produced by | consumed by | verdict |
|---|---|---|---|---|
| `redirect_target` (endpoint) | `0032_playbooks.sql:66` | `subject_facts` branch on `relationships.type = 'redirects_to'` (src side), `20260903T000000Z…:119` | **no playbook** | **promised.** `src/redkraken/playbooks/ssrf-url-routing/references/open-redirection.md:30` states outright: "`routing` asks it, with a `redirect_target` trigger and a browser to observe with." `routing`'s actual triggers are `flow_step` + `state_changing_method` (`src/redkraken/playbooks/routing/playbook.md:5`) and its output is `business_logic.workflow_order`. The hand-off is to a playbook that does not implement it. |
| `numeric_identifier` (endpoint) | `0032_playbooks.sql:61` | branch on `parameters.value_class = 'integer_id'`, `20260903T000000Z…:103` | **no playbook** | **harmless.** `object-ownership` triggers on the broader `object_identifier` (`uuid`/`integer_id`/`opaque_id`) instead. Subsumed, not orphaned. |
| `tech_graphql` (application) | `0032_playbooks.sql:76` | branch on `lower(technologies.name)='graphql'` via a `runs` relationship, `20260903T000000Z…:146` | **no playbook** | **harmless.** The `graphql` playbook triggers on `graphql_surface` (`applications.kind='graphql'`) instead. Redundant path to the same subject. |
| `tech_soap` (application) | `0032_playbooks.sql:75` | branch on `lower(technologies.name)='soap'`, `20260903T000000Z…:145` | **no playbook** | **harmless.** No SOAP playbook exists; `structured-injection` covers XML bodies via `xml_request`. Unused and nothing promises otherwise. |
| `anonymous_identity_available` (program) | `0032_playbooks.sql:80` | branch on `identities.class = 'anonymous'`, `20260903T000000Z…:221`. **Is** produced — `rk2_anonymous_identity()` writes that class (`20260908T010000Z__a_clamped_run_holds_the_identity_it_acts_as.sql:182-183`) and so does `promote_proposal` (`20260814T070000Z…:1427-1428`). | **no playbook** | **harmless.** Genuinely computable, genuinely unwanted. |
| `privileged_identity_available` (program) | `0032_playbooks.sql:79` | branch on `identities.class = 'privileged'`, `20260903T000000Z…:217`. **Never true — see 4b.** | **no playbook** | **harmless only because nothing consumes it.** Dead on both sides simultaneously; the single worst-wired row in `surface_facts`. |

### 4b. Facts whose producing predicate no writer can satisfy

This is the direction the existing `fact_not_computed` gate does **not** cover:
the fact has a branch in the view, but the column value that branch tests for
is never written.

`identities.class` is closed to four values
(`0003_entities.sql:105` — `anonymous`, `user`, `privileged`, `service`).
Every writer in the tree:

| writer | class it writes |
|---|---|
| `src/redkraken/program.py:1044-1046` (program configuration) | `'user'`, hardcoded |
| `promote_proposal`, `20260814T070000Z…:1427-1428` | `'anonymous'`, hardcoded |
| `promote_proposal` (superseded), `20260813T090000Z…:1069-1070` | `'anonymous'`, hardcoded |
| `rk2_anonymous_identity`, `20260908T010000Z…:182-183` | `'anonymous'`, hardcoded |

There is no `UPDATE identities SET class` anywhere
(`grep -rn "identities SET" src/` → only `secret_ref` and `invalidated_at`,
`src/redkraken/program.py:1054`, `:1076`).

| value | declared where | produced by | consumed by | verdict |
|---|---|---|---|---|
| `privileged_identity_available` | `0032_playbooks.sql:79` | **nothing can set `class='privileged'`** | nothing | **harmless today, a trap tomorrow.** The predicate is unsatisfiable. The first playbook that adds this trigger will be silently unselectable forever, and no gate will say so. |
| `identities.class = 'privileged'` (the enum value itself) | `0003_entities.sql:105` | no writer | one `subject_facts` branch | **promised.** The class vocabulary advertises a privileged-identity concept the runtime cannot instantiate. |
| `identities.class = 'service'` (the enum value itself) | `0003_entities.sql:105` | no writer | **nothing reads it either** | **harmless.** Fully inert. |
| `multiple_test_identities` | `0032_playbooks.sql` | satisfiable — `program.py:1044` writes `'user'` | **7 playbooks**: `api`, `api-authorization`, `browser-realtime`, `graphql`, `grpc`, `logging`, `object-ownership` | correctly wired |

**`parameters.value_class` is the larger hole.** Nine of the 55 facts are
computed from it (`20260903T000000Z…:85-113`), and it is:

- `text` with **no CHECK constraint** — verified: `SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='parameters'::regclass;` lists only `entity_type`, `location`, keys and FKs.
- written by `promote_proposal` as `left(nullif(btrim(v_element ->> 'value_class'),''),200)` — `20260814T070000Z…:1410-1418`. Raw model text, truncated, otherwise unexamined.
- **absent from every Python module, every playbook and every skill in the tree.** `grep -rn "value_class\|integer_id\|opaque_id" src/ docs/` outside `src/redkraken/migrations/` returns only `docs/prototype/` and two `docs/specs/` issue files.

The nine literal spellings the view tests for — `uuid`, `integer_id`,
`opaque_id`, `url`, `file`, `email`, `number`, `path`, `serialized` — exist
**only inside the body of the `subject_facts` view**. A model writing
`"value_class": "integer"` or `"uuid_v4"` produces a valid row that matches no
branch, and nothing anywhere refuses it or reports it.

| value | declared where | produced by | consumed by | verdict |
|---|---|---|---|---|
| `object_identifier` | `0032_playbooks.sql:59` | `value_class ∈ (uuid, integer_id, opaque_id)` — unconstrained model text | `object-ownership` | **promised.** |
| `url_valued_parameter` | `0032_playbooks.sql` | `value_class = 'url'` | `external-resources`, `ssrf-url-routing`, `webhooks` | **promised.** |
| `path_valued_parameter` | `20260902T000000Z…` | `value_class = 'path'` | `file-resolution`, `file-upload` | **promised.** |
| `quantity_valued_parameter` | `20260828T000000Z…` | `value_class = 'number'` | `exceptional-conditions`, `payment-workflows` | **promised.** |
| `file_parameter` | `0032_playbooks.sql` | `value_class = 'file'` | `command-directory-injection`, `file-upload` | **promised.** |
| `email_valued_parameter` | `0032_playbooks.sql` | `value_class = 'email'` | `authentication` | **promised.** |
| `serialized_object_parameter` | `20260902T000000Z…` | `value_class = 'serialized'` | `deserialization` | **promised.** |
| `numeric_identifier` | `0032_playbooks.sql:61` | `value_class = 'integer_id'` | — | harmless (4a) |
| `reflected_parameter` | `0032_playbooks.sql:62` | `parameters.reflected IS TRUE`, a boolean the model sets (`20260814T070000Z…:1414-1415`) | `agentic-ai`, `browser-script`, `spreadsheet-injection`, `ssti` | **promised** — same shape, but a boolean has no spelling to get wrong, so the risk is omission rather than drift. |

Fifteen playbooks — `object-ownership`, `external-resources`,
`ssrf-url-routing`, `webhooks`, `file-resolution`, `file-upload`,
`exceptional-conditions`, `payment-workflows`, `command-directory-injection`,
`authentication`, `deserialization`, `browser-script`, `ssti`,
`spreadsheet-injection`, `agentic-ai` — are selectable only if a model
free-types one of nine undocumented magic strings (`SELECT count(DISTINCT p.path)
FROM playbooks p JOIN playbook_triggers pt ON pt.playbook_id = p.id WHERE pt.fact
IN (…the nine value_class/reflected facts…)` → 15).

**`technologies.name` is the same shape at larger scale.** Seventeen `tech_*`
facts are computed from a 68-row inline `VALUES` list matching
`lower(technologies.name)` exactly (`20260903T000000Z…:136-200`).
`technologies.name` has no constraint and is written from
`v_element ->> 'name'` (`20260814T070000Z…:1420-1425`). `nginx` matches;
`nginx/1.24.0`, `NGINX`, `Nginx (Ubuntu)` do not. **Promised**, for the 18
playbooks that trigger on a `tech_*` fact (`SELECT count(DISTINCT p.path) … WHERE
pt.fact LIKE 'tech\_%'` → 18).

### 4c. Facts that are correctly wired end to end

For completeness: the 49 facts with at least one playbook trigger, and their
producing column, are `endpoints.auth_required` (3 facts),
`endpoints.method` (2), `endpoints.request_content_type` (4),
`parameters.location` (5), `applications.kind` (5),
`relationships.type='redirects_to'|'embeds'|'runs'|'member_of'` (20),
`parameters` self-join (1), plus the value_class/reflected/identity groups
above. The single writer for all of them is `promote_proposal()`
(`20260814T070000Z…:1370-1440`), called from `src/redkraken/execution.py:381`
(`PROMOTE = "SELECT promote_proposal($1::uuid)"`). **There is no other producer
of typed surface in the harness.** Recon does not write surface; the model
does, and the runtime grounds it.

---

## 5. The reverse direction — vocabulary-shaped identifiers that exist in no table

Method: extract every backticked token from `src/redkraken/playbooks/**` and
`src/redkraken/skills/**` (1650 distinct), then diff against
`property_classes`, `surface_facts`, `observation_kinds`,
`property_class_families`, every table name, every column name and every
`public` function name in the live database.

- 150 tokens have `family.leaf` shape; 94 are not property classes; after
  removing `table.column` forms, **all but one** are third-party code
  identifiers (`document.cookie`, `yaml.safe_load`, `xp_cmdshell`, …).
- 123 tokens are snake_case; 92 are not in the schema; **all 92** resolve to
  language-level sink names, closed CHECK values that do exist
  (`approval_required`, `mutates_object`, `probe_only`, `stable_session`), or
  real browser-action / skill-script argument names (`assert_text`,
  `capture_dom`, `wait_for`, `document_loaded`, `http_status` — all verified
  present in `browser_actions`).

| value | declared where (prose) | produced by | consumed by | verdict |
|---|---|---|---|---|
| `client_side.navigation` | `src/redkraken/playbooks/ssrf-url-routing/playbook.md:128` ("the class is `client_side.navigation` and the Playbook is `routing`") and `src/redkraken/playbooks/ssrf-url-routing/references/open-redirection.md:30` ("the class is `client_side.navigation`. `routing` asks it…") | **nothing** — there is no `client_side` family and no such class. `SELECT id FROM property_class_families;` returns 8 rows, none of them `client_side`. | nothing | **promised, and the worst single row in this report.** It is a *triple* miss in one sentence: (a) the class does not exist; (b) the trigger it names, `redirect_target`, is listed by no playbook (§4a); (c) the playbook it delegates to, `routing`, emits `business_logic.workflow_order` and triggers on `flow_step` + `state_changing_method`. Two corpus files route open-redirect work into a hole with three separate bottoms. |
| *(everything else)* | — | — | — | No other backticked token in the playbook or skill corpus has vocabulary shape and no table row. |

Cross-check in the other direction — a playbook naming a real surface fact that
is not among its own declared triggers:

```
for each playbooks/*/: grep backticked tokens in playbook.md + references/*.md
                       ∩ surface_facts.id, minus that playbook's own triggers
→ ssrf-url-routing :: mentions `redirect_target` :: not one of its triggers
```

One hit, and it is the same defect. Also checked and clean: sink-pack `##`
headings in `src/redkraken/skills/analyse-source/references/sinks-*.md` (16
distinct classes, **all 16 are real** — but one of them,
`information_disclosure.identifier_oracle`, is emitted by nobody; see §1).

---

## 6. Stale declarations — comments or rows contradicted by a later migration

| value | declared where | produced by | consumed by | verdict |
|---|---|---|---|---|
| The `out_of_band_interaction` rejection note | `src/redkraken/migrations/0018_vocabularies.sql:251-268` — "REJECTED, and the rejection is the point. … It goes back in when the collector that generates its provenance exists: a third `provenance_kind` ('oob_receipt') written by a runtime-controlled listener." | superseded by `20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:336-351`, which widened `observation_kinds_allowed_provenance_closed` to admit `'callback'` and inserted `callback_interaction` | the kind is live, cited by `webhooks`, and written by `resolve_callback_arrival` | **stale.** The provenance kind that shipped is `callback`, not `oob_receipt`. The known instance, confirmed. |
| The **live** column comment repeating it | `COMMENT ON COLUMN observation_kinds.allowed_provenance`, set at `0018_vocabularies.sql:269-270`, never re-issued. Verified against the running database: `SELECT col_description('observation_kinds'::regclass, 4);` still returns "…see the out_of_band_interaction note in migration 018." | — | anyone reading `\d+ observation_kinds` | **stale, and worse than the file comment** — a `--` comment inside a recorded migration is at least dated; a live `COMMENT ON` presents as current schema documentation. `20260812T040000Z` moved the constraint and did not move the comment. |
| "Leaving it unbound is the honest answer … `http-desync` is graded `out` on all fifty fixtures" | `20260904T000000Z__three_http_integrity_and_parsing_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql:507-522` — argues at length that `transport.tls_configuration` **cannot** have a fixture because "none of which exists on a loopback fixture serving plain HTTP, which is what every fixture in this catalogue is" | superseded by `20260922T060000Z__a_fixture_may_own_its_own_handshake.sql:14-33`, which added the `tls(variant, context)` entry point, made `evaluation.served` wrap the socket, and relaxed `fixture_addresses_protocol_check` to `('http','https')` | — | **stale.** Both the premise ("every fixture … plain HTTP") and the count ("all fifty fixtures", now 55) are false. Same file, `:526`, "the other forty-nine Playbooks" is still correct at 50 playbooks. |
| "no Python writer sets `purpose` at all — 021 gives it a default of `target_traffic` and nothing moves it. … Ticket 93 owns that lane." | `20260922T060000Z__a_fixture_may_own_its_own_handshake.sql:36-45` | superseded eight hours later by `20260923T000000Z__the_runtime_takes_its_own_transport_measurement.sql`, which created `record_transport_measurement()` (it sets `v_receipt.purpose := 'transport_measurement'`) and wired it at `src/redkraken/proxy.py:1037` | `receipts.transport_citable` (generated), `enforce_transport_observation` | **stale.** Self-labelled as a forecast, but a reader of `20260922T060000Z` alone concludes the transport lane is dead, and it is not. |
| `fixture_addresses.protocol` — "a fixture is served by `evaluation.served` over plain HTTP; a second spelling here would be a claim about a listener nothing starts" | `20260914T000000Z__a_fixture_is_reached_by_address_not_by_name.sql` (ticket 78) | superseded by `20260922T060000Z…:88-104` | — | **stale in the file, correctly repaired in the schema.** `20260922T060000Z` explicitly re-issued `COMMENT ON COLUMN fixture_addresses.protocol` with the new reason and says why ("The original is a `--` comment inside a recorded migration file, which cannot be edited"). **This is the pattern the other three rows should have followed** and is worth citing as the house standard. |
| "Nothing writes one yet" — about `relationships.type = 'same_as'` | `20260813T090000Z__a_recon_run_becomes_typed_surface.sql:190` | still true: `same_as` is agent-writable through `promote_proposal` but no code path emits it; it feeds no `subject_facts` branch | nothing | **not stale — accurate.** Listed to close the question. |
| `0025_transport_claims.sql` in full | built `receipts.transport_citable`, `transport_measurement` purpose, `transport_parameters_observed` and `enforce_transport_observation` (migration 25 of 139, applied before any timestamped file) | **had no writer at all** until `20260923T000000Z`, the last file in the corpus | — | **not a stale comment, but the archetype of the defect this sweep is for.** `20260923T000000Z…:1-11` says it plainly: "no writer has ever set that purpose … one side of the argument 025 records has been in the schema since 025 and the other side has never been made." |

No other migration comment in the corpus makes a claim about the vocabulary
that a later migration contradicts. The scan was: `grep -rniE '^--.*(nothing
(writes|sets|emits|produces|reads|cites)|no writer|nobody (writes|sets|emits)|not
yet exist|does not exist yet|goes back in when|when the .* exists|REJECTED|is
deferred|no fixture|cannot be graded|never citable|no Python writer)'
src/redkraken/migrations/*.sql`, plus every live `COMMENT ON` in the database
(280 rows) filtered on the same phrases.

---

## What a gate would have to assert

The natural home is `check_playbook_integrity()`
(`20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql:653-775`,
already invoked as a hard gate by that migration's own tail at `:834` and by
`tests/test_database.py:37354`). It already carries the right idea for one axis
— `fact_not_computed` refuses a registered trigger atom nothing computes — and
explicitly declines the reverse: *"a trigger atom no playbook uses is fine"*.
That exemption is where four of the six defect classes below live.

Each check below is stated as the query, the severity it should carry, and why
that severity.

**G1 — `class_not_emitted`. ERROR unless allowlisted.**
```sql
SELECT 'error', 'class_not_emitted', pc.id
  FROM property_classes pc
 WHERE NOT EXISTS (SELECT 1 FROM playbook_outputs po WHERE po.property_class = pc.id)
   AND NOT EXISTS (SELECT 1 FROM transport_makeability t
                    WHERE t.property_class = pc.id AND t.makeability = 'unmakeable');
```
Today: 5 errors (`authentication.recovery_flow`,
`information_disclosure.identifier_oracle`, `rate_limiting.per_origin`,
`rate_limiting.resource_cost`, `transport.certificate_trust`). The
`unmakeable` carve-out is the existing, honest way to say "declared and
deliberately unreachable" — a class that wants to be unemitted should have to
say so in `transport_makeability` (or a generalised `class_unreachable` table)
rather than by silence. That converts §1's five promised rows into either a
playbook or an explicit declaration.

**G2 — `class_named_in_prose_but_unemitted`. ERROR. The worst case, so it gets its own name.**
Requires a corpus-side scan, so it belongs in `tests/test_database.py` beside
the catalogue test rather than in SQL:
```python
declared  = {row.id for row in db("SELECT id FROM property_classes")}
emitted   = {row.property_class for row in db("SELECT property_class FROM playbook_outputs")}
for path in Path("src/redkraken").rglob("*.md"):        # playbooks/ and skills/
    for token in re.findall(r"`([a-z_]+\.[a-z_]+)`", path.read_text()):
        if token in declared and token not in emitted:
            fail(f"{path}: names {token}, which no playbook emits")
        if re.fullmatch(r"[a-z_]+\.[a-z_]+", token) and token not in declared \
           and token.split(".")[0] in families:
            fail(f"{path}: names {token}, which is not a property class")
```
Today: 12 failures across §1 (four classes × their prose sites) plus the two
`client_side.navigation` sites from §5. Note the second clause has to be
family-gated or it drowns in `yaml.safe_load`; gating on
`property_class_families.id` is exact and cheap. **`client_side.navigation`
would have been caught the day it was written.**

**G3 — `class_ungradeable`. ERROR.**
```sql
SELECT 'error', 'class_ungradeable', p.path || ' -> ' || po.property_class
  FROM playbooks p JOIN playbook_outputs po ON po.playbook_id = p.id
 WHERE NOT EXISTS (SELECT 1 FROM fixture_classes fc
                    WHERE fc.property_class = po.property_class);
```
Equivalently `SELECT p.path FROM playbooks p WHERE NOT EXISTS (SELECT 1 FROM
playbook_fixture_binding(p.id) b WHERE b.side = 'in')`. Today: 0. On the
database that was handed to me: 1 (`http-desync`). This is the check that would
have caught §2 at the moment `20260904T000000Z` applied rather than eighteen
migrations later, and note that the migration's own comment argued *at length*
that the state was fine — a prose defence is exactly what a gate is immune to.

**G4 — `fixture_grades_nobody`. WARNING, not ERROR.**
```sql
SELECT 'warning', 'fixture_grades_nobody', fc.fixture_id || ' -> ' || fc.property_class
  FROM fixture_classes fc
 WHERE NOT EXISTS (SELECT 1 FROM playbook_outputs po WHERE po.property_class = fc.property_class);
```
Today: 4 (§2b). Warning rather than error because a fixture ahead of its
playbook is a defensible order of work; four of them sitting for months is not,
and a warning that never clears is the signal.

**G5 — `evidence_kind_unsatisfiable`. ERROR.**
`playbook_evidence` has an FK to `observation_kinds` and a `role` CHECK, and
**no check that the kind is evidential** (verified: `\d playbook_evidence` lists
no such constraint and no trigger). But `enforce_evidential_kind()`
(`0018_vocabularies.sql:448-470`) refuses a non-evidential kind in
`hypothesis_evidence` for any role but `context`. So a playbook can today
declare a `supported`-status requirement that is unsatisfiable at runtime:
```sql
SELECT 'error', 'evidence_kind_unsatisfiable', p.path || ' -> ' || e.observation_kind
  FROM playbook_evidence e
  JOIN playbooks p ON p.id = e.playbook_id
  JOIN observation_kinds ok ON ok.id = e.observation_kind
 WHERE NOT ok.is_evidential AND e.role <> 'context';
```
Today: 0 — but only by luck, and this is the check that keeps §3's five
non-evidential kinds harmless instead of becoming a promise. Cheapest of the
six and should be a table CHECK rather than a report, since nothing legitimate
writes such a row.

**G6 — `fact_predicate_unsatisfiable`. ERROR. The hardest and the most valuable.**
The existing `fact_not_computed` proves the view *mentions* the fact. Nothing
proves the view's predicate can ever be true. Two concrete forms:

*G6a — closed-enum branches.* For each `subject_facts` branch that tests a
column with a CHECK-closed domain, assert some writer produces that value.
Mechanically: extract the literals the view compares `identities.class`,
`applications.kind`, `relationships.type` and `endpoints.method` against, and
intersect with the literals the writers insert.
```sql
-- the shipped form of the identities case, which is the one that fails today
SELECT 'error', 'fact_predicate_unsatisfiable', 'privileged_identity_available'
 WHERE NOT EXISTS (
   SELECT 1 FROM pg_proc p
    WHERE p.prosrc LIKE '%INSERT INTO identities%'
      AND p.prosrc LIKE '%''privileged''%')
   AND NOT EXISTS (SELECT 1 FROM identities WHERE class = 'privileged');
```
A cleaner and more durable version is a declared table —
`fact_producers(fact, writer, note)` — with a check that every
`surface_facts` row has at least one row in it and every named writer still
exists (`to_regprocedure`, or a `grep` in the Python case). That form also
documents §4c, which is currently knowledge held nowhere.

*G6b — open-text branches.* `parameters.value_class` and `technologies.name`
are `text` with no constraint, and the view's nine and sixty-eight literal
spellings are the real vocabulary. Two assertions, both worth having:
```sql
-- (i) the vocabulary must be closed at the column, not inside a view body
ALTER TABLE parameters ADD CONSTRAINT parameters_value_class_check
  CHECK (value_class IS NULL OR value_class IN
    ('uuid','integer_id','opaque_id','url','file','email','number','path','serialized'));
```
```python
# (ii) and it must be reachable by the party that writes it
served = mcp_enum('parameter_value_class')          # or the tool schema's enum
assert served, "value_class vocabulary is not served to any writer"
```
Today (i) fails against no data (the column is empty on a fresh database) and
would immediately start refusing the drift it exists to refuse; (ii) fails
outright, because `mcp_enum()` has no caller at all.

**G7 — `enum_declared_but_never_served`. ERROR, and the one that generalises.**
```python
# tests/test_database.py, beside the catalogue test
for fn in ("mcp_enum", "mcp_enum_described", "mcp_transport_makeability"):
    callers = subprocess.run(["grep","-rl",fn,"src/redkraken","tests","tools"],...)
    callers = [c for c in callers if "/migrations/" not in c]
    assert callers, f"{fn} is granted to rk2_runtime and called by nothing"
```
Today: 3 failures. Stated generally: **a function granted `EXECUTE` to
`rk2_runtime` and referenced only by the migration that created it is a
capability with no consumer.** That query is one line of SQL against
`pg_proc.proacl` plus one grep, it needs no vocabulary knowledge at all, and it
is the check that would have caught §3b — which is itself the check that would
have caught most of the rest of this document.

**G8 — `stale_declaration`. WARNING, and partly social.**
The mechanical part is enforceable: a migration that changes a constraint,
default or closed set on a column **must** re-issue `COMMENT ON` for that
column in the same file. `20260922T060000Z…:100-104` already does this
voluntarily and says why. As a test:
```python
for migration in changed_files:
    for column in columns_whose_constraints_this_file_alters(migration.sql):
        assert f"COMMENT ON COLUMN {column}" in migration.sql, \
            f"{migration.identity} moved {column}'s rule and left its comment"
```
Today this would have flagged `20260812T040000Z` (moved
`observation_kinds_allowed_provenance_closed`, left the column comment pointing
at a rejection that no longer holds) — the known instance, caught
mechanically. It does not catch stale `--` prose inside a migration body, and
nothing can; the mitigation for that is the one this corpus already practises,
which is to name the superseding ticket in the superseding file.

---

### Roll-up

| section | count | promised | harmless |
|---|---|---|---|
| 1. classes nobody emits | 7 | 5 | 2 |
| 1b. classes with no retest trigger | 39 | 36 | 3 |
| 2. emitted but ungradeable | 0 (1 on the stale DB, fixed) | — | — |
| 2b. fixtures that grade nobody | 4 | 4 | 0 |
| 3. observation kinds neither written nor cited | 5 | 0 | 5 |
| 3. kinds written only by a model string | 8 | — | — |
| 3b. vocabulary-serving functions with no caller | 3 | 3 | 0 |
| 4a. facts no playbook triggers on | 6 | 1 | 5 |
| 4b. facts whose predicate no writer satisfies | 1 unsatisfiable + 9 value_class/reflected-gated (15 playbooks) + 17 `tech_*`-gated (18 playbooks) | 26 | 1 |
| 5. vocabulary-shaped identifiers in no table | 1 | 1 | 0 |
| 6. stale declarations | 5 | — | — |
