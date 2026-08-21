# 23 -- Database wiring: declared structure with no producer or no consumer

One axis of the wiring sweep. The question this file answers is narrow: for every
column, table, function, constraint, trigger and view the schema declares, **is
there a writer and is there a reader** -- and if not, is the absence harmless or
is it the ticket-93 shape (a thing the design turns on that no code path can ever
make true).

## 0. Method, and one thing to know before reading

### 0.1 The probe database is four migrations behind the tree

`rk2probe` on `127.0.0.1:55433` reports 135 applied migrations; the tree carries
139 `.sql` files:

```
psql ... -tAc "select count(*) from rk2_meta.schema_migrations"     -> 135
ls src/redkraken/migrations/*.sql | wc -l                           -> 139
```

Diffing `rk2_meta.schema_migrations.id` against the file names, the four that are
**on disk and not applied** are:

| unapplied migration | what it adds |
|---|---|
| `20260922T040000Z__a_route_template_names_its_own_method` | `UPDATE`s to `skill_dependencies` / `skills` only |
| `20260922T050000Z__a_bad_wait_fails_more_missions_than_a_bad_selector` | `UPDATE`s to `skill_dependencies` / `skills` only |
| `20260922T060000Z__a_fixture_may_own_its_own_handshake` | fixture seed rows, `fixture_addresses_protocol_check`, new `open_fixture_address` |
| `20260923T000000Z__the_runtime_takes_its_own_transport_measurement` | **ticket 93**: `fixture_addresses.trust_anchor`, `record_transport_measurement()`, the widened `receipts_transport_measurement_shape`, and the repaired `reject_proxy_internal_evidence()` |

Everything catalogue-derived below is therefore the schema **as of migration 135**.
Where the fourth file changes a verdict, this is said explicitly. All 50 playbooks
and 54 fixtures are loaded (`select count(*) from playbooks` -> 50, `fixtures` ->
54); every runtime table is empty (`programs` -> 0, `receipts` -> 0), so no verdict
here rests on row counts.

### 0.2 How writer/reader was decided

- Catalogue dumps: `pg_attribute` + `pg_attrdef` (1554 columns over 200 tables),
  `pg_proc` (658 functions, 116 of them extension-owned -> **501 user functions**
  under 617 distinct names), `pg_views` (25), `pg_constraint` (552 CHECK/EXCLUDE,
  plus FKs), `pg_trigger` (187 non-internal), `pg_indexes`, `pg_policy`,
  `information_schema.role_table_grants` / `role_column_grants`, `aclexplode`.
- Writer corpus: every `pg_proc.prosrc` body, all 111 Python files under `src/`
  (with adjacent string-literal concatenation joined first, because every SQL
  statement in `src/` is written as concatenated string literals), and all 139
  migration files. `INSERT INTO t (cols)`, `UPDATE t [alias] SET ...`,
  `ON CONFLICT DO UPDATE SET ...` and `NEW.col :=` inside a trigger function were
  each parsed to a `(table, column)` write.
- A write from a migration file is recorded as **seed**, not as a live writer: a
  `INSERT` that runs once at migration time is not a producer at runtime.
- Dynamic dispatch was resolved by hand where it exists. Two prefixes are called
  through `EXECUTE format('SELECT %I($1)', ...)`: `evidence_profile_*`
  (`src/redkraken/migrations/0015_epistemic_corrections.sql:345`, and again at
  `20260815T000000Z__a_test_runs_through_the_replay_lane.sql:1654`) and
  `lane_signal_*` (`lane_quota_signals_of`). Those are wired and are **not**
  reported as orphans.
- `standing_checks.query` (64 rows) was added to the caller corpus, so a function
  reached only by a registered standing check counts as called.

---

## 1. Columns nothing writes

### 1.1 The shape of the number

| bucket | count |
|---|---|
| columns in `public` base tables | 1554 |
| ... generated (`attgenerated <> ''`) -- see s2 | 4 |
| ... with **no live writer** (no SQL function, no Python, no trigger assignment) | 668 |
| ... of those, an identity/timestamp default that is always right (`uuidv7()`, `now()`, `clock_timestamp()`, `nextval(...)`, `pg_current_xact_id()`, `GENERATED AS IDENTITY`) | 158 |
| ... of those, written only by a migration seed (catalogue/vocabulary tables) | 348 |
| ... of those, on `scheduler_weights`, whose only writer is `version_scheduler_weights`'s copy-forward `INSERT ... SELECT` (no column list, so every column is carried) | 18 |
| **remaining columns that nothing ever writes** | **144** across 46 tables |
| ... of which a CHECK, a generated column, a view, an index, an RLS policy or an FK depends on them | 104 |

The 144 are listed in full below. Verdicts:

- `harmless -- ...` : the column is constant by design, or an operator/enrichment
  field with no consumer.
- `**table has no writer at all**` : the column is unwritten because *nothing
  inserts into its table*; the real finding is in s3.
- `column never written` : nothing writes it and nothing structurally depends on
  it beyond what the "depends on it" cell shows.
- `**load-bearing**` : something downstream reads it, or a rule is built over it,
  and it can only ever be NULL / its default.

### 1.2 The full list

| column | type | NN | default | what depends on it | verdict |
|---|---|---|---|---|---|
| `agent_runs.parent_run_id` | uuid | n | `` | FK `agent_runs_parent_run_id_fkey` | **load-bearing** |
| `agent_sessions.agent_run_id` | uuid | Y | `` | FK `agent_sessions_agent_run_id_fkey`; INDEX `agent_sessions_run_idx` | **table has no writer at all** (see s3) |
| `agent_sessions.program_id` | uuid | Y | `` | FK `agent_sessions_program_id_fkey`, `agent_sessions_agent_run_id_fkey`, `agent_sessions_task_id_fkey`; INDEX `agent_sessions_live_binding_idx`; RLS `agent_sessions_rk2_state` | **table has no writer at all** (see s3) |
| `agent_sessions.sdk_agent_id` | text | Y | `''::text` | INDEX `agent_sessions_live_binding_idx` | **table has no writer at all** (see s3) |
| `agent_sessions.sdk_agent_type` | text | n | `` | -- | **table has no writer at all** (see s3) |
| `agent_sessions.session_id` | text | Y | `` | INDEX `agent_sessions_live_binding_idx` | **table has no writer at all** (see s3) |
| `agent_sessions.task_id` | uuid | n | `` | FK `agent_sessions_task_id_fkey` | **table has no writer at all** (see s3) |
| `agent_sessions.trace_id` | text | n | `` | -- | **table has no writer at all** (see s3) |
| `applications.entity_type` | text | Y | `'application'::text` | CHECK `applications_entity_type_check`; FK `applications_entity_id_entity_type_fkey` | harmless -- subtype discriminator; constant by design, FK to entities(id,type) |
| `artifacts.purged_at` | timestamp with time zone | n | `` | RLS `artifacts_rk2_state` | **load-bearing** |
| `browser_ceilings.id` | integer | Y | `1` | CHECK `browser_ceilings_id_check`; INDEX `browser_ceilings_pkey` | **table has no writer at all** (see s3) |
| `cross_program_exempt_fks.constraint_name` | text | Y | `` | INDEX `cross_program_exempt_fks_pkey` | **table has no writer at all** (see s3) |
| `cross_program_exempt_fks.reason` | text | Y | `` | -- | **table has no writer at all** (see s3) |
| `cross_program_exempt_fks.table_name` | text | Y | `` | INDEX `cross_program_exempt_fks_pkey` | **table has no writer at all** (see s3) |
| `domains.entity_type` | text | Y | `'domain'::text` | CHECK `domains_entity_type_check`; FK `domains_entity_id_entity_type_fkey` | harmless -- subtype discriminator; constant by design, FK to entities(id,type) |
| `endpoints.entity_type` | text | Y | `'endpoint'::text` | CHECK `endpoints_entity_type_check`; FK `endpoints_entity_id_entity_type_fkey` | harmless -- subtype discriminator; constant by design, FK to entities(id,type) |
| `eval_family_coverage.eval_run_id` | uuid | Y | `` | FK `eval_family_coverage_eval_run_id_program_id_fkey`; INDEX `eval_family_coverage_eval_run_id_family_id_key` | **table has no writer at all** (see s3) |
| `eval_family_coverage.family_id` | text | Y | `` | FK `eval_family_coverage_family_id_fkey`; INDEX `eval_family_coverage_eval_run_id_family_id_key` | **table has no writer at all** (see s3) |
| `eval_family_coverage.found` | integer | Y | `0` | CHECK `eval_family_coverage_found_check`, `eval_found_le_entries` | **table has no writer at all** (see s3) |
| `eval_family_coverage.gt_entries` | integer | Y | `0` | CHECK `eval_family_coverage_gt_entries_check`, `eval_found_le_entries` | **table has no writer at all** (see s3) |
| `eval_fn_attribution.bucket` | text | Y | `` | CHECK `eval_bucket_owns`, `eval_fn_attribution_bucket_check`, `eval_suppression_cites_the_row` | **table has no writer at all** (see s3) |
| `eval_fn_attribution.detail` | text | Y | `''::text` | -- | **table has no writer at all** (see s3) |
| `eval_fn_attribution.gt_id` | text | Y | `` | INDEX `eval_fn_attribution_pair_score_id_gt_id_key` | **table has no writer at all** (see s3) |
| `eval_fn_attribution.near_match_id` | uuid | n | `` | CHECK `eval_suppression_cites_the_row`; FK `eval_fn_attribution_near_match_id_program_id_fkey` | **table has no writer at all** (see s3) |
| `eval_fn_attribution.owner` | text | Y | `` | CHECK `eval_bucket_owns`, `eval_fn_attribution_owner_check` | **table has no writer at all** (see s3) |
| `eval_fn_attribution.pair_score_id` | uuid | Y | `` | FK `eval_fn_attribution_pair_score_id_program_id_fkey`; INDEX `eval_fn_attribution_pair_score_id_gt_id_key` | **table has no writer at all** (see s3) |
| `eval_pair_scores.converted_fraction` | numeric | n | `` | CHECK `eval_pair_scores_converted_fraction_check`, `eval_third_party_declares_coverage` | **table has no writer at all** (see s3) |
| `eval_pair_scores.duplicate` | integer | Y | `0` | CHECK `eval_pair_scores_duplicate_check` | **table has no writer at all** (see s3) |
| `eval_pair_scores.eval_run_id` | uuid | Y | `` | FK `eval_pair_scores_eval_run_id_program_id_fkey`; INDEX `eval_pair_scores_eval_run_id_fixture_id_key` | **table has no writer at all** (see s3) |
| `eval_pair_scores.false_positive_rate` | numeric | n | `` | CHECK `eval_pair_scores_false_positive_rate_check`, `eval_third_party_has_no_precision` | **table has no writer at all** (see s3) |
| `eval_pair_scores.fixture_id` | text | Y | `` | INDEX `eval_pair_scores_eval_run_id_fixture_id_key` | **table has no writer at all** (see s3) |
| `eval_pair_scores.fixture_kind` | text | Y | `` | CHECK `eval_own_pair_is_scorable`, `eval_pair_scores_fixture_kind_check`, `eval_third_party_declares_coverage`, `eval_third_party_has_no_precision` | **table has no writer at all** (see s3) |
| `eval_pair_scores.fn_near_miss` | integer | Y | `0` | CHECK `eval_gt_accounting`, `eval_pair_scores_fn_near_miss_check` | **table has no writer at all** (see s3) |
| `eval_pair_scores.fn_not_found` | integer | Y | `0` | CHECK `eval_gt_accounting`, `eval_pair_scores_fn_not_found_check` | **table has no writer at all** (see s3) |
| `eval_pair_scores.fn_suppressed` | integer | Y | `0` | CHECK `eval_gt_accounting`, `eval_pair_scores_fn_suppressed_check` | **table has no writer at all** (see s3) |
| `eval_pair_scores.fn_unproven` | integer | Y | `0` | CHECK `eval_gt_accounting`, `eval_pair_scores_fn_unproven_check` | **table has no writer at all** (see s3) |
| `eval_pair_scores.fp` | integer | Y | `0` | CHECK `eval_pair_scores_fp_check` | **table has no writer at all** (see s3) |
| `eval_pair_scores.gt_declared` | integer | Y | `` | CHECK `eval_pair_scores_gt_declared_check`, `eval_recallable_le_declared` | **table has no writer at all** (see s3) |
| `eval_pair_scores.gt_recallable` | integer | Y | `` | CHECK `eval_gt_accounting`, `eval_pair_scores_gt_recallable_check`, `eval_recallable_le_declared` | **table has no writer at all** (see s3) |
| `eval_pair_scores.pair_clean` | boolean | n | `` | CHECK `eval_own_pair_is_scorable`, `eval_third_party_has_no_precision` | **table has no writer at all** (see s3) |
| `eval_pair_scores.precision_strict` | numeric | n | `` | CHECK `eval_pair_scores_precision_strict_check`, `eval_third_party_has_no_precision` | **table has no writer at all** (see s3) |
| `eval_pair_scores.recall_strict` | numeric | n | `` | CHECK `eval_pair_scores_recall_strict_check` | **table has no writer at all** (see s3) |
| `eval_pair_scores.tool_runs` | integer | Y | `0` | CHECK `eval_pair_scores_tool_runs_check` | **table has no writer at all** (see s3) |
| `eval_pair_scores.tp` | integer | Y | `0` | CHECK `eval_gt_accounting`, `eval_pair_scores_tp_check` | **table has no writer at all** (see s3) |
| `eval_pair_scores.unattributed_real` | integer | Y | `0` | CHECK `eval_pair_scores_unattributed_real_check` | **table has no writer at all** (see s3) |
| `eval_runs.config` | jsonb | Y | `'{}'::jsonb` | -- | **table has no writer at all** (see s3) |
| `eval_runs.finished_at` | timestamp with time zone | n | `` | -- | **table has no writer at all** (see s3) |
| `eval_runs.key_components` | jsonb | Y | `` | -- | **table has no writer at all** (see s3) |
| `eval_runs.program_id` | uuid | Y | `` | FK `eval_runs_program_id_fkey`; INDEX `eval_runs_id_program_id_key`, `eval_runs_program_id_run_key_repeat_index_key`; RLS `eval_runs_rk2_state` | **table has no writer at all** (see s3) |
| `eval_runs.repeat_index` | integer | Y | `0` | CHECK `eval_runs_repeat_index_check`; INDEX `eval_runs_program_id_run_key_repeat_index_key` | **table has no writer at all** (see s3) |
| `eval_runs.run_key` | text | Y | `` | INDEX `eval_runs_program_id_run_key_repeat_index_key` | **table has no writer at all** (see s3) |
| `eval_runs.sut` | text | Y | `` | -- | **table has no writer at all** (see s3) |
| `eval_runs.weights_version` | text | n | `` | -- | **table has no writer at all** (see s3) |
| `events.seq` | bigint | Y | `` | INDEX `events_pkey`, `events_type_idx` | harmless -- GENERATED ALWAYS AS IDENTITY; Postgres writes it |
| `finding_gate_clearances.actor_kind` | text | Y | `'human'::text` | CHECK `finding_gate_clearances_actor_kind_check` | harmless -- constant by design; only a human clears a gate |
| `findings.duplicate_of_finding_id` | uuid | n | `` | FK `findings_duplicate_of_finding_id_fkey`; INDEX `findings_cell_idx` | **load-bearing** |
| `findings.external_ref` | text | n | `` | -- | **load-bearing** |
| `fixtures.converted` | integer | n | `` | CHECK `fixtures_converted_check`, `fixtures_own_pair_declares_no_coverage`, `fixtures_third_party_declares_coverage` | **table has no writer at all** (see s3) |
| `fixtures.upstream_list_size` | integer | n | `` | CHECK `fixtures_own_pair_declares_no_coverage`, `fixtures_third_party_declares_coverage`, `fixtures_upstream_list_size_check` | **table has no writer at all** (see s3) |
| `hosts.asn` | integer | n | `` | -- | harmless -- operator/enrichment field, no consumer |
| `hosts.entity_type` | text | Y | `'host'::text` | CHECK `hosts_entity_type_check`; FK `hosts_entity_id_entity_type_fkey` | harmless -- subtype discriminator; constant by design, FK to entities(id,type) |
| `hypotheses.observed_fingerprint` | text | n | `` | -- | **load-bearing** |
| `hypothesis_embeddings.embedding` | vector(1536) | Y | `` | INDEX `hypothesis_embeddings_hnsw` | **table has no writer at all** (see s3) |
| `hypothesis_embeddings.hypothesis_id` | uuid | Y | `` | FK `hypothesis_embeddings_hypothesis_id_fkey`; INDEX `hypothesis_embeddings_pkey` | **table has no writer at all** (see s3) |
| `hypothesis_embeddings.model` | text | Y | `` | INDEX `hypothesis_embeddings_pkey` | **table has no writer at all** (see s3) |
| `hypothesis_near_matches.candidate_hypothesis_id` | uuid | n | `` | CHECK `hypothesis_near_matches_candidate_matches_action`; FK `hypothesis_near_matches_candidate_fk`; INDEX `hypothesis_near_matches_candidate_idx` | **load-bearing** |
| `hypothesis_near_matches.embedding_model` | text | n | `` | CHECK `hypothesis_near_matches_stage2_cols` | **load-bearing** |
| `hypothesis_near_matches.similarity` | numeric | n | `` | CHECK `hypothesis_near_matches_stage2_cols` | **load-bearing** |
| `hypothesis_retest_triggers.hypothesis_id` | uuid | Y | `` | FK `hypothesis_retest_triggers_hypothesis_id_fkey`; INDEX `hypothesis_retest_triggers_hypothesis_id_kind_watched_entit_key` | **table has no writer at all** (see s3) |
| `hypothesis_retest_triggers.kind` | text | Y | `` | CHECK `hypothesis_retest_triggers_kind_check`; INDEX `hypothesis_retest_triggers_hypothesis_id_kind_watched_entit_key` | **table has no writer at all** (see s3) |
| `hypothesis_retest_triggers.watched_entity_id` | uuid | n | `` | FK `hypothesis_retest_triggers_watched_entity_id_fkey`; INDEX `hypothesis_retest_triggers_hypothesis_id_kind_watched_entit_key` | **table has no writer at all** (see s3) |
| `identities.acquired_at` | timestamp with time zone | n | `` | -- | **load-bearing** |
| `identities.entity_type` | text | Y | `'identity'::text` | CHECK `identities_entity_type_check`; FK `identities_entity_id_entity_type_fkey` | harmless -- subtype discriminator; constant by design, FK to entities(id,type) |
| `identities.tenant_entity_id` | uuid | n | `` | FK `identities_tenant_entity_id_fkey` | **load-bearing** |
| `impact_demonstrations.run_outcome` | text | Y | `'holds'::text` | CHECK `impact_demonstrations_run_outcome_check`; FK `impact_demonstrations_test_run_id_run_outcome_fkey` | harmless -- constant by design; FK pins the cited test run to run_outcome='holds' |
| `interception_cas.label` | text | Y | `` | CHECK `interception_cas_no_key_material`; INDEX `interception_cas_program_id_label_key` | **table has no writer at all** (see s3) |
| `interception_cas.not_after` | timestamp with time zone | Y | `` | CHECK `interception_cas_max_lifetime`, `interception_cas_window` | **table has no writer at all** (see s3) |
| `interception_cas.not_before` | timestamp with time zone | Y | `` | CHECK `interception_cas_max_lifetime`, `interception_cas_window` | **table has no writer at all** (see s3) |
| `interception_cas.program_id` | uuid | Y | `` | FK `interception_cas_program_id_superseded_by_fkey`, `interception_cas_program_id_fkey`; INDEX `interception_cas_program_id_id_key`, `interception_cas_program_id_label_key`, `interception_cas_one_current`; RLS `interception_cas_rk2_state` | **table has no writer at all** (see s3) |
| `interception_cas.retired_at` | timestamp with time zone | n | `` | CHECK `interception_cas_supersede_needs_retire`; INDEX `interception_cas_one_current` | **table has no writer at all** (see s3) |
| `interception_cas.secret_ref` | text | Y | `` | CHECK `interception_cas_no_key_material`, `interception_cas_secret_ref_shape` | **table has no writer at all** (see s3) |
| `interception_cas.spki_sha256` | text | Y | `` | CHECK `interception_cas_no_key_material`, `interception_cas_spki_sha256_check` | **table has no writer at all** (see s3) |
| `interception_cas.subject` | text | Y | `` | CHECK `interception_cas_no_key_material` | **table has no writer at all** (see s3) |
| `interception_cas.superseded_by` | uuid | n | `` | CHECK `interception_cas_supersede_needs_retire`; FK `interception_cas_program_id_superseded_by_fkey` | **table has no writer at all** (see s3) |
| `notification_channels.backoff` | interval | Y | `'00:00:30'::interval` | -- | **table has no writer at all** (see s3) |
| `notification_channels.max_attempts` | smallint | Y | `5` | CHECK `notification_channels_max_attempts_check` | **table has no writer at all** (see s3) |
| `observation_embeddings.embedding` | vector(1536) | Y | `` | INDEX `observation_embeddings_hnsw` | **table has no writer at all** (see s3) |
| `observation_embeddings.model` | text | Y | `` | INDEX `observation_embeddings_pkey` | **table has no writer at all** (see s3) |
| `observation_embeddings.observation_id` | uuid | Y | `` | FK `observation_embeddings_observation_id_fkey`; INDEX `observation_embeddings_pkey` | **table has no writer at all** (see s3) |
| `offline_tools.enabled` | boolean | Y | `true` | -- | harmless -- seeded true; no disable path |
| `parameters.entity_type` | text | Y | `'parameter'::text` | CHECK `parameters_entity_type_check`; FK `parameters_entity_id_entity_type_fkey` | harmless -- subtype discriminator; constant by design, FK to entities(id,type) |
| `playbook_selections.outcome` | text | Y | `'running'::text` | CHECK `playbook_selections_dropped_has_no_outcome`, `playbook_selections_outcome_check` | **load-bearing** |
| `playbook_skills.skill_sha256_at_promotion` | text | n | `` | CHECK `playbook_skills_skill_sha256_at_promotion_check` | **table has no writer at all** (see s3) |
| `playbook_test_policy.id` | integer | Y | `1` | CHECK `playbook_test_policy_id_check`; INDEX `playbook_test_policy_pkey` | **table has no writer at all** (see s3) |
| `program_known_issues.class_id` | text | Y | `` | FK `program_known_issues_class_id_fkey` | **table has no writer at all** (see s3) |
| `program_known_issues.entity_like` | text | n | `` | -- | **table has no writer at all** (see s3) |
| `program_known_issues.note` | text | Y | `` | -- | **table has no writer at all** (see s3) |
| `program_known_issues.program_id` | uuid | Y | `` | FK `program_known_issues_program_id_fkey`; INDEX `program_known_issues_id_program_id_key`; RLS `program_known_issues_rk2_state` | **table has no writer at all** (see s3) |
| `program_known_issues.source` | text | Y | `` | CHECK `program_known_issues_source_check` | **table has no writer at all** (see s3) |
| `program_scope_rules.allow_private_ips` | boolean | Y | `false` | -- | **load-bearing** |
| `program_scope_rules.net` | cidr | n | `` | CHECK `program_scope_rules_check`; INDEX `scope_rules_net_idx` | **load-bearing** |
| `program_scope_rules.tier` | text | n | `` | CHECK `program_scope_rules_check2`; INDEX `scope_rules_key_idx` | **load-bearing** |
| `program_scope_versions.default_tier` | text | n | `` | -- | **load-bearing** |
| `programs.scope_policy` | jsonb | Y | `'{}'::jsonb` | -- | harmless -- superseded by program_scope_versions/rules in 0021; unread |
| `redaction_failure.artifact_sha` | text | n | `` | CHECK `redaction_failure_artifact_sha_check`; FK `redaction_failure_sha_fk` | **table has no writer at all** (see s3) |
| `redaction_failure.encoding_path` | text | Y | `` | -- | **table has no writer at all** (see s3) |
| `redaction_failure.match_len` | integer | Y | `` | -- | **table has no writer at all** (see s3) |
| `redaction_failure.match_offset` | integer | Y | `` | -- | **table has no writer at all** (see s3) |
| `redaction_failure.rule_id` | text | Y | `` | -- | **table has no writer at all** (see s3) |
| `redaction_failure.value_fpr` | bytea | n | `` | CHECK `redaction_failure_value_fpr_check` | **table has no writer at all** (see s3) |
| `relationships.metadata` | jsonb | Y | `'{}'::jsonb` | -- | **load-bearing** |
| `report_queue.program_id` | uuid | Y | `` | FK `report_queue_program_id_fkey`; RLS `report_queue_rk2_state` | **table has no writer at all** (see s3) |
| `report_queue.state` | text | Y | `'queued'::text` | CHECK `report_queue_state_check` | **table has no writer at all** (see s3) |
| `secret_access_log.dek_gen` | integer | n | `` | -- | **load-bearing** |
| `secret_access_log.peer_exe` | text | n | `` | -- | **load-bearing** |
| `secret_access_log.peer_pid` | integer | n | `` | -- | **load-bearing** |
| `secret_access_log.peer_uid` | integer | n | `` | -- | **load-bearing** |
| `secret_access_log.receipt_id` | uuid | n | `` | -- | **load-bearing** |
| `secret_dek.dek_gen` | integer | Y | `` | CHECK `secret_dek_dek_gen_check`; INDEX `secret_dek_pkey` | **table has no writer at all** (see s3) |
| `secret_dek.kek_gen` | integer | Y | `` | FK `secret_dek_kek_gen_fkey` | **table has no writer at all** (see s3) |
| `secret_dek.retired_at` | timestamp with time zone | n | `` | INDEX `secret_dek_current_idx` | **table has no writer at all** (see s3) |
| `secret_dek.scope_id` | uuid | Y | `` | INDEX `secret_dek_pkey`, `secret_dek_current_idx` | **table has no writer at all** (see s3) |
| `secret_dek.scope_kind` | text | Y | `` | CHECK `secret_dek_scope_kind_check`; INDEX `secret_dek_pkey`, `secret_dek_current_idx` | **table has no writer at all** (see s3) |
| `secret_dek.seal_cap` | bigint | Y | `'4294967296'::bigint` | CHECK `secret_dek_check`, `secret_dek_seal_cap_check` | **table has no writer at all** (see s3) |
| `secret_dek.seal_count` | bigint | Y | `0` | CHECK `secret_dek_check`, `secret_dek_seal_count_check` | **table has no writer at all** (see s3) |
| `secret_dek.wrapped` | bytea | Y | `` | CHECK `secret_dek_wrapped_check` | **table has no writer at all** (see s3) |
| `secret_kek.retired_at` | timestamp with time zone | n | `` | CHECK `secret_kek_check`; INDEX `secret_kek_current_idx` | harmless -- rotation not implemented; single generation by design |
| `services.entity_type` | text | Y | `'service'::text` | CHECK `services_entity_type_check`; FK `services_entity_id_entity_type_fkey` | harmless -- subtype discriminator; constant by design, FK to entities(id,type) |
| `tasks.evidence_profile_id` | text | n | `` | FK `tasks_evidence_profile_id_fkey` | **load-bearing** |
| `tasks.expected_information_gain` | numeric | n | `` | -- | **load-bearing** |
| `tasks.potential_impact` | numeric | n | `` | -- | **load-bearing** |
| `tasks.required_skills` | text[] | Y | `'{}'::text[]` | -- | **load-bearing** |
| `tasks.skill_name` | text | n | `` | FK `tasks_skill_name_fkey` | **load-bearing** |
| `tasks.skill_sha256` | text | n | `` | CHECK `tasks_skill_sha256_check` | **load-bearing** |
| `tasks.skill_version` | text | n | `` | CHECK `tasks_skill_version_check` | **load-bearing** |
| `technologies.entity_type` | text | Y | `'technology'::text` | CHECK `technologies_entity_type_check`; FK `technologies_entity_id_entity_type_fkey` | harmless -- subtype discriminator; constant by design, FK to entities(id,type) |
| `tests.supersedes_test_id` | uuid | n | `` | FK `tests_supersedes_test_id_fkey` | **load-bearing** |
| `tool_runs.args_sha256` | text | n | `` | FK `tool_runs_args_sha256_fkey` | **load-bearing** |
| `tool_runs.mcp_server` | text | n | `` | -- | **load-bearing** |
| `tool_runs.result_sha256` | text | n | `` | FK `tool_runs_result_sha256_fkey` | **load-bearing** |
| `tool_runs.sdk_agent_id` | text | n | `` | -- | **load-bearing** |
| `tool_runs.sdk_agent_type` | text | n | `` | -- | **load-bearing** |
| `tool_runs.session_id` | text | n | `` | -- | **load-bearing** |
| `tool_runs.tool_use_id` | text | n | `` | CHECK `tool_runs_hook_identity_ck`; INDEX `tool_runs_tool_use_id_uq` | **load-bearing** |

### 1.3 The load-bearing ones, with the writer that should have set them

**(a) `tasks` -- the skill binding and the two model priors.** The only four
functions that `INSERT INTO tasks` are:

| function | column list |
|---|---|
| `open_task` | `program_id, kind, subject_entity_id` |
| `open_impact_task` | `program_id, kind, subject_entity_id, hypothesis_id, finding_id` |
| `open_validation_session` | `program_id, kind, finding_id, status` |
| `derive_chain_unlocks` | `program_id, kind, hypothesis_id, subject_entity_id` |

`rank_pass` later `UPDATE`s the ranking terms (`direct_value`, `unlock_value`,
`estimated_time`, `safety_cost`, `chain_unlock_value`, `novelty`,
`estimated_cost`, `confidence_of_execution`, `ranked_weights_version`). Nothing,
ever, sets `skill_name` (`0015_epistemic_corrections.sql:148`), `skill_sha256`
(`:149`), `skill_version`
(`20260822T000000Z__a_skill_teaches_what_the_role_may_already_do.sql:318`),
`required_skills` (`0012_scheduler.sql:21`), `evidence_profile_id`
(`0015_epistemic_corrections.sql:178`), `expected_information_gain` or
`potential_impact` (`0006_tasks_and_runs.sql:16-17`).

Consequences, all of them live:

- `tasks_skill_sha256_check` and `tasks_skill_version_check` are decoration --
  the column they constrain is always NULL.
- `tasks_skill_name_fkey -> skills(name)` never resolves, so the six seeded
  `skills` rows are reachable only through `role_skills`, never through a task.
- `tasks_evidence_profile_id_fkey -> evidence_profiles(id)` never resolves. The
  four `evidence_profile_*` functions are dispatched off
  `hypotheses`/`transition_rules.consults_evidence_profile`, not off the task,
  so the *task-side* half of that design has no producer.
- `v_records` publishes `'skill_name'`, `'expected_information_gain'` and
  `'potential_impact'` keys to the agent that are always `null` (s6).
- `state_read_surface` grants `rk2_state` column SELECT on all of
  `skill_name, skill_sha256, required_skills, evidence_profile_id,
  expected_information_gain, potential_impact` -- six always-NULL columns on the
  agent's read surface.

**(b) `tool_runs` -- the whole hook-provenance block is structurally unreachable.**
`0022_hooks_and_receipts.sql:186-217` adds `tool_use_id`, `session_id`,
`sdk_agent_id`, `sdk_agent_type`, `mcp_server`, `args_sha256`, `result_sha256`,
and `transport text NOT NULL DEFAULT 'runtime' CHECK (transport IN ('builtin','mcp','runtime'))`.
`0022` also adds

```
tool_runs_hook_identity_ck  CHECK (((transport = 'runtime') = (tool_use_id IS NULL)))
```

Every writer of `tool_runs` passes the literal `'runtime'`:

| writer | transport value |
|---|---|
| `src/redkraken/execution.py:356` | `'runtime'` |
| `src/redkraken/proxy.py` (`INSERT INTO tool_runs (program_id, agent_run_id, tool, args, status, transport)`) | `'runtime'` |
| `open_browser_run`, `rk2_open_replay`, `open_offline_tool_run` | `'runtime'` |

So `transport IN ('builtin','mcp')` is unreachable, `tool_use_id` is forced NULL
by the check, and `session_id / sdk_agent_id / sdk_agent_type / mcp_server /
args_sha256 / result_sha256` have no writer at all. `tool_runs_tool_use_id_uq`
(the SDK idempotency key) indexes a column that is always NULL; `v_records`
publishes `mcp_server`, `args_sha256`, `result_sha256` as always-`null`; and
`agent_sessions`, the table that would carry `session_id`, has no writer either
(s3).

**(c) `program_scope_rules.net` / `.tier` and `program_scope_versions.default_tier`
-- the CIDR arm of scope evaluation is dead.** Declared at
`0021_scope_policy.sql:91,94,95`; the Python compiler writes the rules at
`src/redkraken/program.py:911` with the column list
`(program_id, version, ord, effect, effect_rank, pattern_kind, pattern_text,
match_key, protocol, port, path_prefix, spec_kind, spec_len)` -- `net`, `tier`
and `allow_private_ips` are absent. And the compiler only ever produces two
pattern kinds: `Pattern(kind="wildcard", ...)` at `src/redkraken/scope.py:579`
and `Pattern(kind="exact", ...)` at `:584`. Therefore:

- `program_scope_rules_check  CHECK ((pattern_kind = 'cidr') = (net IS NOT NULL))`
  and `program_scope_rules_check1 CHECK ((pattern_kind = 'cidr') = (match_key IS NULL))`
  can never be exercised;
- `program_scope_rules_pattern_kind_check`'s `'cidr'` arm is unreachable;
- the GiST index `scope_rules_net_idx ON program_scope_rules USING gist (net inet_ops)`
  (`0021:120`) indexes a column that is always NULL;
- the CIDR matching arm of the classifier, `r.net >>= (...)` at `0021:292`, can
  never match;
- `tier` is never set on a rule and `default_tier` is never set on a version, so
  the tier expression at `0021:333` (`coalesce((SELECT tier FROM tierpick),
  (SELECT sv.default_tier ...))`) always yields NULL, `entities.scope_tier`
  (written by `refresh_scope_projection` from that expression) is always NULL,
  and `v_records` publishes `'scope_tier': null` for every entity.
- `allow_private_ips` (NOT NULL DEFAULT false) has no writer and no reader
  anywhere -- dead.

**(d) `artifacts.purged_at`.** Declared with the lifecycle view
`artifacts_due_for_purge` (`0011_lifecycle.sql:15`). Thirteen SQL functions
mention the column; nothing sets it, and the view that names the collectable
bytes has **zero** readers (s6). Artifacts are never purged, and the RLS policy
`artifacts_rk2_state` and the `state_read_surface` grant on `purged_at` describe a
state no row reaches.

**(e) `playbook_selections.outcome` (and `went_stale_at`).**
`20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql:460` says in
so many words: "`outcome` and `went_stale_at` are what a run updates". Nothing
updates either. `record_playbook_selection` inserts the row at the default
`'running'`; `mark_stale_selections()` -- the only writer of `went_stale_at` --
has no caller (s4). So `playbook_selections_outcome_check`'s `'produced'` and
`'exhausted'` arms are unreachable, `playbook_selections_dropped_has_no_outcome`
is decoration, and the playbook funnel never closes.

**(f) `secret_access_log.receipt_id / peer_pid / peer_uid / peer_exe / dek_gen`.**
The audit row is written (`src/redkraken/artifact.py:273`) without any of the
five columns that would say *who* asked and *which* exchange it was for. The
receipt back-link is the load-bearing one: it is the only edge that would tie a
secret read to the request that used it.

**(g) `hypothesis_near_matches.similarity / embedding_model / candidate_hypothesis_id`.**
`hypothesis_near_matches_stage2_cols` and
`hypothesis_near_matches_candidate_matches_action` are built over three columns
nothing writes -- the embedding-based ("stage 2") half of near-match detection has
no producer, matching the fact that `hypothesis_embeddings` and
`observation_embeddings` have no writer at all (s3).

**(h) Small, still real.** `agent_runs.parent_run_id` (FK declared, no writer, no
reader: the subagent parent edge is never recorded);
`identities.tenant_entity_id` and `identities.acquired_at` (both on the agent read
surface, both always NULL); `relationships.metadata` (NOT NULL DEFAULT `'{}'`, on
the read surface, never populated); `findings.duplicate_of_finding_id`,
`findings.external_ref`, `tests.supersedes_test_id`,
`hypotheses.observed_fingerprint`, `hypotheses.superseded_by` -- all five are
published through `v_records` (`duplicate_of_label`, `external_ref`,
`supersedes_label`, `observed_fingerprint`) and are always null.

### 1.4 Explicitly harmless

- The eight `*.entity_type` discriminators (`applications`, `domains`, `endpoints`,
  `hosts`, `identities`, `parameters`, `services`, `technologies`): constant by
  design, and the constant is what makes the composite FK to `entities(id, type)`
  work. Their `*_entity_type_check` constraints can never fail; that is the point.
- `events.seq`: `GENERATED ALWAYS AS IDENTITY` (`0013_events.sql:99`) -- Postgres
  writes it.
- `programs.scope_policy` (`0002_programs.sql:10`, `jsonb NOT NULL DEFAULT '{}'`):
  superseded by `program_scope_versions` / `program_scope_rules` in `0021`. No
  writer and no reader; a leftover, not a hole.
- `secret_kek.retired_at`: only generation 1 is ever established
  (`ensure_active_secret_kek`); rotation is a documented later phase.
- `impact_demonstrations.run_outcome` (default `'holds'`, CHECK `= 'holds'`) and
  `finding_gate_clearances.actor_kind` (default `'human'`, CHECK `= 'human'`):
  constants that exist to make an FK or a policy expressible.
- `offline_tools.enabled` (seeded `true`, no disable path) and `hosts.asn`
  (enrichment field with no consumer): dead but inert.
- The 348 seed-written columns on the 79 catalogue tables in s3.2.

---

## 2. Generated columns and their inputs

Query:

```sql
select c.relname, a.attname, pg_get_expr(d.adbin, d.adrelid)
  from pg_attribute a
  join pg_class c on c.oid = a.attrelid
  join pg_namespace n on n.oid = c.relnamespace
  join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
 where n.nspname = 'public' and a.attgenerated <> '';
```

Four, and only four.

| generated column | expression depends on | who writes those inputs | anything depends on it | can it ever be true |
|---|---|---|---|---|
| `agent_runs.executes_tasks` | `task_id IS NOT NULL` | `claim_task`, `open_validation_session` set `agent_runs.task_id` | `agent_runs_executes_tasks_fk FOREIGN KEY (role, executes_tasks) REFERENCES roles(role, executes_tasks)` + `roles_role_executes_tasks_key` | **yes** -- 5 of 6 seeded `roles` rows have `executes_tasks = t`; harmless idiom |
| `role_skills.loads_skills` | literal `true` | n/a (constant) | `role_skills_role_loads_fkey FOREIGN KEY (role, loads_skills) REFERENCES roles(role, loads_skills)` + `roles_renderer_loads_nothing` | **yes** by construction. The constant exists so the composite FK refuses a `role_skills` row for a role whose `loads_skills` is false. Harmless. |
| `receipts.transport_divergence` | 7 pairs `agent_* IS DISTINCT FROM wire_*` | `write_allowed_receipt` writes all 14 columns | quoted in `transport_observation_guard`'s refusal message; `check_transport_claims` | **yes** for agent-lane receipts. Note the quirk: on a measurement receipt every `agent_*` is forced NULL, so divergence lists all seven fields. Harmless, but the array is a diagnostic string, not a decision input. |
| `receipts.transport_citable` | `purpose = 'transport_measurement' AND intercepted = false AND decision = 'allowed' AND wire_tls_version IS NOT NULL AND wire_chain_verified IS TRUE AND wire_hostname_verified IS TRUE` | see below | `transport_observation_guard` (the only admissible provenance for a `transport_parameters_observed` observation), `check_transport_claims`, `reject_proxy_internal_evidence` after ticket 93, `v_records`, `state_read_surface` | **NO in the applied schema (135). YES only after the unapplied 4th migration.** |

### 2.1 `receipts.transport_citable` -- the ticket-93 defect, still present in the probe DB

Writers of `receipts` in the schema as applied:

| writer | sets `purpose` | sets `decision` | can produce `transport_citable` |
|---|---|---|---|
| `write_allowed_receipt` | **no** -- the column falls to its default `'target_traffic'::text` | `'allowed'` | no: `purpose <> 'transport_measurement'` |
| `write_blocked_receipt` | yes, but only `'control_plane'` or `'target_traffic'` (`v_purpose := CASE WHEN p_capability IS NULL AND p_receipt ->> 'purpose' = 'control_plane' THEN ... END`) | blocked/denied | no, on both conjuncts |

No third writer exists at migration 135. Ticket 93's writer,
`record_transport_measurement(text, jsonb)`
(`src/redkraken/migrations/20260923T000000Z__...:346`, `GRANT EXECUTE ... TO
rk2_proxy` at `:443`, called from `src/redkraken/proxy.py:1037`), is in the tree
and **not in the probe database**:

```
psql ... -tAc "select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace
               where n.nspname='public' and proname='record_transport_measurement'"   -> 0
```

So the axis-defining defect is *fixed in the tree and unapplied in the probe*. Two
things follow that are worth stating separately, because they are not fixed:

1. `receipts.transport_citable` and `receipts.transport_divergence` are on the
   agent's read surface (`state_read_surface`, `added_by 33-seed`) and in
   `v_records`'s receipt record. Until the fourth migration lands, both are
   published to the model as a constant `false` / a full-divergence array.
2. The contradiction ticket 93 repairs is only repaired for **observations**. The
   same collision still stands one layer up, at `finding_evidence` -- see s5.3.

---

## 3. Tables nothing inserts into

Method: every `INSERT INTO <t>` occurrence in `pg_proc.prosrc`, in `src/**/*.py`
and in `src/redkraken/migrations/*.sql`, bucketed into *live* (function or Python)
and *seed* (migration file only).

| bucket | count |
|---|---|
| base tables in `public` | 200 |
| with a live writer | 107 |
| **seeded by a migration and never written again** | 79 |
| **never inserted into anywhere, including migrations** | **14** |

### 3.1 The 14 with no `INSERT` anywhere

All fourteen are empty in the probe database (`select count(*)` -> 0 for each).

| table | declared | live readers | FKs pointing at it | verdict |
|---|---|---|---|---|
| `agent_sessions` | 0022_hooks_and_receipts.sql:151 | `fn:close_startup_refusal`, `fn:open_impact_replay`, `fn:park_authorized_tool_run`, `fn:resume_program` | 0 |  |
| `cross_program_exempt_fks` | 0017_program_isolation.sql:328 | `fn:check_program_isolation` | 0 |  |
| `eval_family_coverage` | 0033_eval_store.sql:198 | `fn:eval_family_coverage_of` | 0 |  |
| `eval_fn_attribution` | 0033_eval_store.sql:150 | **none** | 0 |  |
| `eval_pair_scores` | 0033_eval_store.sql:60 | `fn:eval_precision`, `fn:eval_recall_by_kind` | 1 |  |
| `eval_runs` | 0033_eval_store.sql:37 | `fn:eval_key_diff`, `fn:eval_precision`, `fn:eval_recall_by_kind` | 2 |  |
| `hypothesis_embeddings` | 0010_embeddings.sql:7 | `view:hnsw_headroom` | 0 |  |
| `hypothesis_retest_triggers` | 0007_epistemics.sql:97 | `fn:cancel_reason_for`, `fn:novelty_for`, `fn:refresh_negative_knowledge`, `fn:scheduler_idle_report` | 0 |  |
| `interception_cas` | 0025_transport_claims.sql:467 | `fn:check_transport_claims` | 2 |  |
| `observation_embeddings` | 0010_embeddings.sql:15 | `view:hnsw_headroom` | 0 |  |
| `program_known_issues` | 0034_reports.sql:351 | `fn:report_blockers` | 0 |  |
| `redaction_failure` | 0024_secret_keying.sql:143 | **none** | 0 |  |
| `report_queue` | 0020_state_access.sql:134 | **none** | 0 |  |
| `secret_dek` | 0024_secret_keying.sql:61 | `fn:check_wire_artifact_secrecy` | 0 |  |

Verdicts:

- **`report_queue` -- load-bearing, and the cleanest instance of the defect on
  this axis.** Declared `0020_state_access.sql:134` with a CHECK
  (`state = ANY (ARRAY['queued','running','done'])`), an FK to `programs`, two RLS
  policies (`report_queue_rk2_runtime`, `report_queue_rk2_state`), a row in the
  `0020:185` program-scoping registry and a row in
  `0030_corpus_corrections.sql:116` classifying it `'derived'`. The MCP contract
  `mcp__rk2__request_report` at `src/redkraken/roster.py:722` *names it as its
  write target* -- `writes=("report_queue",)` at `:725`. There is no handler:
  `request_report` appears in `src/` only at `roster.py:536` (group membership)
  and `roster.py:722`, and `agent.py:151`'s `SERVED_MEMBERS` serves only
  `get_slate` and `pick_task` out of `sched.pick`. Nothing reads the table either
  -- zero functions, zero views, zero Python. It is a declared queue with no
  producer, no consumer and a contract pointing at it.
  Contrast the two sibling requests in the same group, which *do* have producers:
  `validation_queue` <- `request_validation`, `pending_decisions` <-
  `park_authorized_tool_run` / `rk2_ask_about_impact`.
- **`agent_sessions` -- load-bearing.** `0022_hooks_and_receipts.sql:151`. Four
  functions `UPDATE agent_sessions SET unbound_at = ...`
  (`close_startup_refusal`, `open_impact_replay`, `park_authorized_tool_run`,
  `resume_program`) and three views compute over it
  (`orchestrator_session_usage`, `lane_budget`, `program_capacity`) -- and
  `capsule.py` / `panels.py` read those views. Nothing ever inserts a row, so
  `orchestrator_session_usage` (which `check_orchestrator_rotation`,
  `open_orchestrator_session` and `orchestrator_session_spent` all consult) is
  always empty and the session-spend ceiling is never reached by anything. It also
  makes `agent_sessions_live_binding_idx` and the SDK-session correlation half of
  `check_hook_provenance` (arms 2 and 3) assertions about a table with no rows.
- **The eval store: `eval_runs`, `eval_pair_scores`, `eval_fn_attribution`,
  `eval_family_coverage`** (`0033_eval_store.sql:37,60,150,198`). 29 columns,
  27 CHECK constraints, 4 read-side functions (`eval_precision`,
  `eval_recall_by_kind`, `eval_family_coverage_of`, `eval_comparable`) -- none of
  which has a caller (s4). `src/redkraken/evaluation.py` exists and writes
  `evaluation_programs`, but never these. Load-bearing if evaluation is meant to
  be measurable from the database; a whole subsystem declared with neither end
  connected.
- **`hypothesis_embeddings`, `observation_embeddings`** (`0010_embeddings.sql:7,15`).
  Both carry HNSW indexes (`hypothesis_embeddings_hnsw`,
  `observation_embeddings_hnsw`) and are the only source of the `hnsw_headroom`
  view that `check_server_baseline` asserts on. Nothing computes an embedding.
  This is the same hole as `hypothesis_near_matches`'s stage-2 columns in s1.3(g)
  -- the semantic-dedup design has no producer.
- **`interception_cas`** (`0025_transport_claims.sql:467`). Nine columns, six
  CHECKs (`interception_cas_no_key_material`, `_window`, `_max_lifetime`,
  `_supersede_needs_retire`, `_spki_sha256_check`, `_secret_ref_shape`), a partial
  unique index `interception_cas_one_current`, ten columns on the agent read
  surface, and `receipts.interception_ca_id` FKs into it. `check_transport_claims`
  reads it. `src/redkraken/proxy.py` mentions the name but never inserts. So
  `receipts.interception_ca_id` can never be non-NULL, and every constraint on the
  CA lifecycle is decoration. Load-bearing: the design's story about *which* CA
  intercepted a flow has no recorded answer.
- **`secret_dek`** (`0024_secret_keying.sql:61`). The DEK half of a KEK/DEK
  envelope. `artifact_seal` (`src/redkraken/artifact.py:214`,
  `fn:record_proxy_exchange`) seals directly against `secret_kek` via
  `artifact_seal_kek_gen_fkey` -- there is no DEK in the path. `secret_dek_current_idx`,
  `secret_dek_check` (`seal_count <= seal_cap`), `secret_dek_dek_gen_check` and the
  rotation ceiling `seal_cap` are all unreachable. `check_wire_artifact_secrecy`
  still reads the table. Harmless-superseded rather than load-bearing, but it is a
  standing check asserting over an empty table forever.
- **`redaction_failure`** (`0024_secret_keying.sql:143`). No writer, no reader,
  no FK pointing at it. `src/redkraken/evidence.py` reads `redaction_rules` and
  `evidence_bundle_files` but never records a failure. Load-bearing if a redaction
  miss is meant to be auditable.
- **`program_known_issues`** (`0034_reports.sql:351`). Read by `report_blockers`;
  never written; on the agent read surface (five columns). A report blocker that
  can never block.
- **`hypothesis_retest_triggers`** (`0007_epistemics.sql:97`). Read by four
  functions (`cancel_reason_for`, `novelty_for`, `scheduler_idle_report`,
  `refresh_negative_knowledge`); `refresh_negative_knowledge` *updates*
  `fired_at`/`fingerprint` on rows that never exist. Load-bearing: the
  "re-test when the surface changes" input to scheduling is always empty.
- **`cross_program_exempt_fks`** (`0017_program_isolation.sql:328`). Read by
  `check_program_isolation`. Harmless: an empty exemption list is the strict
  reading, and `rk2_runtime` holds only SELECT on it.

### 3.2 The 79 seeded-only tables

These have no writer in `src/` and no `INSERT` in any SQL function; they are
populated once by a migration and read thereafter. **This is the intended shape**
for a vocabulary or a policy catalogue, and all 79 have live readers except the
four flagged below.

| table | declared | seeded by | live readers |
|---|---|---|---|
| `artifact_reference_kinds` | 20260814T050000Z__source_becomes_a_grounded_conclusion.sql:72 | 20260814T050000Z__source_becomes_a_grounded_conclusion.sql, 20260905T000000Z__v1_state_crosses_into_this_schema_as_imported.sql | 0: **none** |
| `browser_action_arguments` | 20260814T040000Z__a_browser_mission_runs_behind_the_door.sql:209 | 20260814T040000Z__a_browser_mission_runs_behind_the_door.sql | 1: `fn:open_browser_run` |
| `browser_actions` | 20260814T040000Z__a_browser_mission_runs_behind_the_door.sql:150 | 20260814T040000Z__a_browser_mission_runs_behind_the_door.sql | 4: `fn:browser_run_digest`, `fn:check_browser_runs`, `fn:open_browser_run`, `fn:record_browser_step` |
| `browser_argument_kinds` | 20260814T040000Z__a_browser_mission_runs_behind_the_door.sql:77 | 20260814T040000Z__a_browser_mission_runs_behind_the_door.sql | 1: `fn:open_browser_run` |
| `browser_ceilings` | 20260814T040000Z__a_browser_mission_runs_behind_the_door.sql:360 | 20260814T040000Z__a_browser_mission_runs_behind_the_door.sql | 2: `fn:check_browser_runs`, `fn:rk2_browser_ceilings` |
| `browser_probes` | 20260814T040000Z__a_browser_mission_runs_behind_the_door.sql:285 | 20260814T040000Z__a_browser_mission_runs_behind_the_door.sql | 3: `fn:check_browser_runs`, `fn:open_browser_run`, `fn:record_browser_step` |
| `call_risk_rules` | 0026_human_control.sql:243 | 0026_human_control.sql | 2: `fn:assess_call_risk`, `fn:check_control_surface` |
| `capabilities` | 20260817T000000Z__a_pivot_is_stamped_from_the_run_that_showed_it.sql:62 | 20260817T000000Z__a_pivot_is_stamped_from_the_run_that_showed_it.sql | 4: `fn:check_pivot_stamps`, `fn:enforce_chain_entry`, `fn:rk2_capability_vocabulary_sha256`, `fn:rk2_pivot_problem` |
| `decision_question_codes` | 20260814T020000Z__the_operator_answers_and_the_work_resumes.sql:47 | 20260814T020000Z__the_operator_answers_and_the_work_resumes.sql, 20260816T000000Z__impact_is_authorized_before_it_is_proved.sql | 0: **none** |
| `digest_facts` | 0026_human_control.sql:220 | 0026_human_control.sql | 1: `fn:check_control_surface` |
| `entity_containment` | 20260813T090000Z__a_recon_run_becomes_typed_surface.sql:153 | 20260813T090000Z__a_recon_run_becomes_typed_surface.sql | 3: `fn:check_surface_promotion`, `fn:enforce_relationship_grammar`, `fn:promote_proposal` |
| `event_table_config` | 0013_events.sql:171 | 0013_events.sql, 0022_hooks_and_receipts.sql | 7: `fn:attach_event_triggers`, `fn:check_control_surface`, `fn:check_event_coverage`, `fn:check_event_log_integrity` |
| `event_table_exempt` | 0027_migration_baseline.sql:40 | 0027_migration_baseline.sql, 0030_corpus_corrections.sql | 1: `fn:check_event_coverage` |
| `event_types` | 0013_events.sql:53 | 0013_events.sql, 0014_scheduler_event_deltas.sql | 1: `fn:enforce_event_envelope` |
| `evidence_bundle_files` | 20260821T000000Z__evidence_leaves_with_what_can_be_checked.sql:181 | 20260821T000000Z__evidence_leaves_with_what_can_be_checked.sql | 2: `fn:check_evidence_export`, `py:redkraken/evidence.py` |
| `evidence_profiles` | 0015_epistemic_corrections.sql:154 | 20260822T000000Z__a_skill_teaches_what_the_role_may_already_do.sql | 1: `fn:check_skill_registry` |
| `fixture_classes` | 0036_playbook_tests.sql:109 | 20260824T000000Z__a_playbook_earns_stable_against_fixtures_it_did_not_pick.sql, 20260826T000000Z__seven_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql | 3: `fn:check_playbook_tests`, `fn:playbook_fixture_binding`, `fn:record_playbook_test_run` |
| `fixtures` | 0036_playbook_tests.sql:81 | 20260824T000000Z__a_playbook_earns_stable_against_fixtures_it_did_not_pick.sql, 20260826T000000Z__seven_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql | 4: `fn:check_playbook_tests`, `fn:enforce_playbook_test_fixture_text`, `fn:playbook_fixture_binding`, `fn:record_playbook_test_run` |
| `impact_classes` | 20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:47 | 20260816T000000Z__impact_is_authorized_before_it_is_proved.sql | 6: `fn:check_impact_authorization`, `fn:open_impact_replay`, `fn:open_impact_task`, `fn:report_source_bundle` |
| `label_prefixes` | 0015_epistemic_corrections.sql:38 | 0015_epistemic_corrections.sql, 0020_state_access.sql | 1: `fn:free_label` |
| `lane_quota_policies` | 0037_lane_quota.sql:250 | 0037_lane_quota.sql | 3: `fn:advance_lane_quota`, `fn:check_lane_quota_closure`, `fn:force_lane_quota` |
| `lane_quota_profile_slots` | 0037_lane_quota.sql:111 | 0037_lane_quota.sql | 3: `fn:check_lane_quota_closure`, `fn:lane_quota_slots_of`, `view:effective_lane_capacity` |
| `lane_quota_profiles` | 0037_lane_quota.sql:104 | 0037_lane_quota.sql | 2: `fn:check_lane_quota_closure`, `fn:force_lane_quota` |
| `lane_quota_rules` | 0037_lane_quota.sql:260 | 0037_lane_quota.sql | 1: `fn:advance_lane_quota` |
| `lane_quota_signals` | 0037_lane_quota.sql:143 | 0037_lane_quota.sql | 2: `fn:check_lane_quota_closure`, `fn:lane_quota_signals_of` |
| `notification_channels` | 0026_human_control.sql:532 | 0026_human_control.sql | 4: `fn:check_control_surface`, `fn:due_notifications`, `fn:fan_out_decision_notification`, `fn:record_notification_attempt` |
| `observation_kinds` | 0018_vocabularies.sql:201 | 0018_vocabularies.sql, 0025_transport_claims.sql | 6: `fn:enforce_evidential_kind`, `fn:enforce_kind_provenance`, `fn:mcp_enum`, `fn:mcp_enum_described` |
| `offline_argument_kinds` | 20260814T030000Z__an_offline_tool_becomes_evidence.sql:56 | 20260814T030000Z__an_offline_tool_becomes_evidence.sql | 3: `fn:check_offline_tools`, `fn:check_skill_scripts`, `fn:open_offline_tool_run` |
| `offline_tool_arguments` | 20260814T030000Z__an_offline_tool_becomes_evidence.sql:170 | 20260814T030000Z__an_offline_tool_becomes_evidence.sql, 20260814T050000Z__source_becomes_a_grounded_conclusion.sql | 6: `fn:check_offline_tools`, `fn:check_skill_scripts`, `fn:check_source_conclusions`, `fn:open_offline_tool_run` |
| `offline_tool_outputs` | 20260814T030000Z__an_offline_tool_becomes_evidence.sql:214 | 20260814T050000Z__source_becomes_a_grounded_conclusion.sql | 3: `fn:check_skill_scripts`, `fn:open_offline_tool_run`, `fn:tool_run_artifact_is_this_runs_output` |
| `offline_tool_roles` | 20260814T030000Z__an_offline_tool_becomes_evidence.sql:228 | 20260814T030000Z__an_offline_tool_becomes_evidence.sql, 20260814T050000Z__source_becomes_a_grounded_conclusion.sql | 4: `fn:check_offline_tools`, `fn:check_skill_registry`, `fn:check_skill_scripts`, `fn:open_offline_tool_run` |
| `offline_tools` | 20260814T030000Z__an_offline_tool_becomes_evidence.sql:119 | 20260814T030000Z__an_offline_tool_becomes_evidence.sql, 20260814T050000Z__source_becomes_a_grounded_conclusion.sql | 6: `fn:check_offline_tools`, `fn:check_skill_scripts`, `fn:check_source_conclusions`, `fn:rk2_offline_tool` |
| `playbook_drop_reasons` | 20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql:123 | 20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql, 20260918T000000Z__an_edit_retires_the_evidence_that_blessed_it.sql | 0: **none** |
| `playbook_evidence` | 0032_playbooks.sql:288 | 20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql, 20260826T000000Z__seven_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql | 2: `fn:check_playbook_integrity`, `fn:playbook_evidence_unmet` |
| `playbook_outputs` | 0032_playbooks.sql:269 | 20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql, 20260826T000000Z__seven_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql | 6: `fn:check_playbook_integrity`, `fn:enforce_playbook_test_run`, `fn:playbook_candidates`, `fn:playbook_fixture_binding` |
| `playbook_references` | 20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql:104 | 20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql, 20260826T000000Z__seven_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql | 0: **none** |
| `playbook_skills` | 0032_playbooks.sql:278 | 20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql, 20260826T000000Z__seven_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql | 6: `fn:check_playbook_integrity`, `fn:check_playbook_tests`, `fn:enforce_playbook_promotion`, `fn:playbook_candidates` |
| `playbook_test_policy` | 20260824T000000Z__a_playbook_earns_stable_against_fixtures_it_did_not_pick.sql:600 | 20260824T000000Z__a_playbook_earns_stable_against_fixtures_it_did_not_pick.sql | 2: `fn:playbook_test_verdict`, `py:redkraken/evaluation.py` |
| `playbook_triggers` | 0032_playbooks.sql:261 | 20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql, 20260826T000000Z__seven_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql | 2: `fn:check_playbook_integrity`, `fn:playbooks_by_trigger` |
| `playbooks` | 0032_playbooks.sql:220 | 20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql, 20260826T000000Z__seven_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql | 18: `fn:check_playbook_integrity`, `fn:check_playbook_tests`, `fn:demote_playbooks`, `fn:enforce_playbook_test_run` |
| `program_global_tables` | 0017_program_isolation.sql:309 | 0017_program_isolation.sql, 0018_vocabularies.sql | 4: `fn:apply_state_rls`, `fn:check_program_isolation`, `fn:check_rls_coverage`, `fn:check_state_access` |
| `property_class_families` | 0018_vocabularies.sql:41 | 0018_vocabularies.sql | 3: `fn:eval_family_coverage_of`, `fn:novelty_for`, `fn:record_v1_import` |
| `property_class_vulnerability_classes` | 0018_vocabularies.sql:492 | 0034_reports.sql | 1: `view:finding_class_divergence` |
| `property_classes` | 0018_vocabularies.sql:72 | 0018_vocabularies.sql, 0025_transport_claims.sql | 6: `fn:check_playbook_integrity`, `fn:check_playbook_tests`, `fn:mcp_enum`, `fn:mcp_enum_described` |
| `purge_cascade_edges` | 0016_event_log_corrections.sql:181 | 0016_event_log_corrections.sql, 0020_state_access.sql | 2: `fn:check_event_log_integrity`, `fn:check_purge_travel` |
| `ranking_pass_functions` | 20260819T000000Z__a_chain_unlock_earns_its_place_in_the_queue.sql:779 | 20260819T000000Z__a_chain_unlock_earns_its_place_in_the_queue.sql | 1: `fn:check_task_ranking` |
| `redaction_rules` | 0034_reports.sql:328 | 0034_reports.sql | 2: `fn:check_evidence_export`, `py:redkraken/evidence.py` |
| `relationship_directions` | 20260813T090000Z__a_recon_run_becomes_typed_surface.sql:195 | 20260813T090000Z__a_recon_run_becomes_typed_surface.sql, 20260829T000000Z__eight_browser_and_client_side_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql | 3: `fn:check_surface_promotion`, `fn:enforce_relationship_grammar`, `fn:promote_proposal` |
| `report_blocks` | 0034_reports.sql:213 | 0034_reports.sql, 20260820T000000Z__a_report_is_a_projection_of_what_holds.sql | 4: `fn:chain_source_bundle`, `fn:check_report_grounding`, `fn:check_report_projection`, `fn:report_source_bundle` |
| `report_effects` | 0034_reports.sql:189 | 0034_reports.sql | 2: `fn:compute_finding_cvss`, `fn:report_source_bundle` |
| `report_mechanisms` | 0034_reports.sql:290 | 0034_reports.sql | 4: `fn:check_report_grounding`, `fn:check_report_projection`, `fn:enforce_chain_step_grounding`, `fn:report_source_bundle` |
| `report_template_blocks` | 0034_reports.sql:254 | 0034_reports.sql, 20260820T000000Z__a_report_is_a_projection_of_what_holds.sql | 4: `fn:chain_source_bundle`, `fn:check_report_grounding`, `fn:check_report_projection`, `fn:report_source_bundle` |
| `report_templates` | 0034_reports.sql:239 | 0034_reports.sql, 20260820T000000Z__a_report_is_a_projection_of_what_holds.sql | 6: `fn:chain_source_bundle`, `fn:check_evidence_export`, `fn:check_report_projection`, `fn:read_finding_report` |
| `review_gates` | 20260906T000000Z__a_person_reports_a_finding_and_lifts_a_gate.sql:72 | 20260906T000000Z__a_person_reports_a_finding_and_lifts_a_gate.sql | 2: `fn:check_finding_reporting`, `fn:clear_review_gate` |
| `risk_classes` | 0022_hooks_and_receipts.sql:52 | 0022_hooks_and_receipts.sql | 6: `fn:check_hook_provenance`, `fn:check_impact_authorization`, `fn:check_receipt_integrity`, `fn:gate_tool_call` |
| `role_skills` | 0032_playbooks.sql:204 | 20260811T150000Z__encrypted_identity_slots.sql, 20260822T000000Z__a_skill_teaches_what_the_role_may_already_do.sql | 6: `fn:check_skill_registry`, `fn:check_skill_scripts`, `fn:open_offline_tool_run`, `fn:playbook_candidates` |
| `role_task_kinds` | 0019_role_kinds.sql:59 | 0019_role_kinds.sql | 13: `fn:check_lane_quota_closure`, `fn:check_role_kind_mapping`, `fn:check_skill_registry`, `fn:claim_task` |
| `roles` | 0019_role_kinds.sql:21 | 0019_role_kinds.sql | 12: `fn:agent_runs_derive_role_columns`, `fn:check_lane_quota_closure`, `fn:check_role_kind_mapping`, `fn:check_roster_model_and_effort` |
| `runtime_table_surface` | 20260909T000000Z__the_runtime_holds_what_the_surface_declares.sql:89 | 20260909T000000Z__the_runtime_holds_what_the_surface_declares.sql, 20260912T000000Z__an_out_of_band_host_is_bound_not_declared.sql | 3: `fn:apply_runtime_grants`, `fn:check_runtime_connection`, `fn:check_runtime_privileges` |
| `runtime_verb_surface` | 20260909T000000Z__the_runtime_holds_what_the_surface_declares.sql:103 | 20260909T000000Z__the_runtime_holds_what_the_surface_declares.sql, 20260912T000000Z__an_out_of_band_host_is_bound_not_declared.sql | 1: `fn:check_runtime_privileges` |
| `scheduler_lanes` | 0012_scheduler.sql:117 | 0012_scheduler.sql | 4: `fn:check_role_kind_mapping`, `fn:check_scheduler_closure`, `view:effective_lane_capacity`, `view:lane_budget` |
| `seal_algorithms` | 20260810T173000Z__sealed_wire_artifacts.sql:61 | 20260810T173000Z__sealed_wire_artifacts.sql | 2: `fn:assert_header_slot_state`, `fn:assert_identity_slot_state` |
| `severity_unlock_weights` | 20260819T000000Z__a_chain_unlock_earns_its_place_in_the_queue.sql:466 | 20260819T000000Z__a_chain_unlock_earns_its_place_in_the_queue.sql | 2: `fn:chain_unlock_for`, `fn:check_chain_unlocks` |
| `skill_dependencies` | 20260822T000000Z__a_skill_teaches_what_the_role_may_already_do.sql:151 | 20260822T000000Z__a_skill_teaches_what_the_role_may_already_do.sql, 20260825T000000Z__the_analyst_carries_the_packs_it_reads_source_with.sql | 2: `fn:check_skill_registry`, `fn:check_skill_scripts` |
| `skill_runtime_tools` | 20260822T000000Z__a_skill_teaches_what_the_role_may_already_do.sql:175 | 20260822T000000Z__a_skill_teaches_what_the_role_may_already_do.sql | 1: `fn:check_skill_registry` |
| `skills` | 0023_scheduler_ranking.sql:113 | 20260811T150000Z__encrypted_identity_slots.sql, 20260822T000000Z__a_skill_teaches_what_the_role_may_already_do.sql | 6: `fn:check_playbook_integrity`, `fn:check_scheduler_closure`, `fn:check_skill_registry`, `fn:confidence_for` |
| `standing_checks` | 0030_corpus_corrections.sql:546 | 0030_corpus_corrections.sql, 0032_playbooks.sql | 3: `fn:assert_standing_checks`, `fn:check_check_registration`, `fn:run_standing_checks` |
| `state_read_surface` | 0030_corpus_corrections.sql:246 | 0030_corpus_corrections.sql, 0032_playbooks.sql | 4: `fn:apply_state_grants`, `fn:check_callback_admission`, `fn:check_scope_policy`, `fn:check_state_grants` |
| `surface_delta_kinds` | 20260813T140000Z__the_surface_gets_a_fingerprint.sql:304 | 20260813T140000Z__the_surface_gets_a_fingerprint.sql | 3: `fn:check_surface_fingerprint`, `fn:compute_surface_fingerprint`, `view:v_surface_deltas` |
| `surface_delta_property_classes` | 20260813T140000Z__the_surface_gets_a_fingerprint.sql:328 | 20260813T140000Z__the_surface_gets_a_fingerprint.sql | 3: `fn:check_negative_knowledge`, `fn:rk2_negative_relevant_deltas`, `view:v_surface_deltas` |
| `surface_facts` | 0032_playbooks.sql:38 | 0032_playbooks.sql, 20260826T000000Z__seven_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql | 1: `fn:check_playbook_integrity` |
| `surface_projection_sections` | 20260813T140000Z__the_surface_gets_a_fingerprint.sql:99 | 20260813T140000Z__the_surface_gets_a_fingerprint.sql | 2: `fn:check_surface_fingerprint`, `fn:rk2_surface_section_deltas` |
| `task_dependency_bases` | 20260813T235500Z__rank_by_value_cost_and_what_it_unlocks.sql:468 | 20260813T235500Z__rank_by_value_cost_and_what_it_unlocks.sql | 2: `fn:check_task_ranking`, `fn:unlock_for` |
| `task_kinds` | 0019_role_kinds.sql:50 | 0019_role_kinds.sql | 4: `fn:check_lane_quota_closure`, `fn:check_role_kind_mapping`, `fn:check_scheduler_closure`, `view:effective_lane_capacity` |
| `tool_risk_classes` | 0022_hooks_and_receipts.sql:73 | 0022_hooks_and_receipts.sql | 3: `fn:check_hook_provenance`, `fn:resolve_risk_class`, `fn:resolve_risk_class_pattern` |
| `transition_rules` | 0007_epistemics.sql:109 | 0007_epistemics.sql, 0013_events.sql | 4: `fn:check_hypothesis_promotion`, `fn:check_negative_knowledge`, `fn:enforce_finding_transition`, `fn:hypothesis_transition_refusal` |
| `transport_makeability` | 0025_transport_claims.sql:189 | 0025_transport_claims.sql | 5: `fn:check_transport_claims`, `fn:mcp_transport_makeability`, `fn:transport_evidence_guard`, `fn:transport_finding_guard` |
| `validation_packet_columns` | 20260815T180000Z__a_blind_validator_answers_from_the_packet.sql:83 | 20260815T180000Z__a_blind_validator_answers_from_the_packet.sql | 0: **none** |
| `vulnerability_classes` | 0009_findings.sql:5 | 0034_reports.sql | 3: `fn:compute_finding_cvss`, `fn:report_source_bundle`, `fn:rk2_finding_refusal` |

Four of the 79 have **no live reader either** -- seeded, then never consulted by
anything but an FK:

| table | declared | consumed only as | verdict |
|---|---|---|---|
| `artifact_reference_kinds` | `20260814T050000Z__source_becomes_a_grounded_conclusion.sql` | FK target for `artifact_references.kind`, `offline_tool_arguments.artifact_kind`, `offline_tool_outputs.reference_kind`, `tool_run_inputs.reference_kind` | harmless -- an FK domain is a consumer |
| `decision_question_codes` | `20260814T020000Z__the_operator_answers_and_the_work_resumes.sql` | FK target for `pending_decisions.question_code`, `call_risk_rules.question_code` | harmless -- but note `roster.py:730-742` hard-codes the same five codes as a Python `enum=` instead of reading them |
| `playbook_drop_reasons` | `20260823T000000Z__a_playbook_is_chosen_before_the_model_reads_it.sql` | FK target for `playbook_selections.dropped_because` | harmless |
| `playbook_references` | `20260823T000000Z__...:104` | **nothing** -- no FK points at it, no function reads it, no view selects it | dead: seeded reference material with no consumer |
| `validation_packet_columns` | `20260815T180000Z__a_blind_validator_answers_from_the_packet.sql:83` | **nothing** -- no FK, no function, no view, no Python | **load-bearing**: this is the registry of what a blind validator's packet may contain, and `src/redkraken/packet.py` builds the packet from hard-coded SQL instead of from this table |

---

## 4. Functions nobody calls

501 user-defined functions (658 in `public` minus 116 owned by `vector` /
`pgcrypto`, counted over 617 distinct names). A function counts as *called* if its
name appears applied (`name(`) in another `pg_proc.prosrc`, in a view definition,
in a CHECK constraint, in a column default, in an index definition, in an RLS
policy expression, in a `standing_checks.query`, as a `pg_trigger.tgfoid`, as one
of the two dynamic-dispatch prefixes, or as a word in any `src/**/*.py`.

**26 have no caller by any of those routes.** None of them is referenced from
`src/` at all (verified per name: `grep -rlw <name> src/redkraken --include=*.py`
returns nothing for all 26).

| function | declared | EXECUTE granted to | callers (SQL / Python / view / trigger / standing check) | tests | verdict |
|---|---|---|---|---|---|
| `add_entity` | 0021_scope_policy.sql:576 | PUBLIC, rk2_owner, rk2_runtime | none | 20 || **load-bearing** - bypassed by raw INSERT at program.py:1039 |
| `apply_computed_cvss` | 20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1851 | rk2_owner, rk2_runtime | none | 1 || **load-bearing** - computed severity never written |
| `assert_event_coverage` | 0027_migration_baseline.sql:235 | PUBLIC, rk2_owner, rk2_runtime | none | 0 || harmless - assembly-time assertion |
| `assert_role_catalogue` | 0029_roles_and_grants.sql:268 | rk2_owner, rk2_runtime | none | 0 || harmless - assembly-time assertion |
| `assert_server_baseline` | 0027_migration_baseline.sql:500 | PUBLIC, rk2_owner, rk2_runtime | none | 0 || harmless - assembly-time assertion |
| `assert_standing_checks` | 0030_corpus_corrections.sql:599 | PUBLIC, rk2_owner, rk2_runtime | none migration-time call: 0030_corpus_corrections.sql:655 | 0 || harmless - migration-time assertion only |
| `attach_actor_kind_guards` | 0026_human_control.sql:82 | rk2_owner, rk2_runtime | none migration-time call: 0026_human_control.sql:994 | 0 || harmless - DDL helper used by 9 migrations |
| `build_kill_chain` | 20260818T000000Z__a_chain_is_composed_and_stays_sound.sql:538 | rk2_owner, rk2_runtime | none | 4 || **load-bearing** - tested, never invoked |
| `compose_finding_report` | 20260820T000000Z__a_report_is_a_projection_of_what_holds.sql:461 | PUBLIC, rk2_owner, rk2_runtime | none | 3 || **load-bearing** - report projection never invoked |
| `cvss_band` | 0034_reports.sql:730 | PUBLIC, rk2_owner, rk2_runtime | none migration-time call: 0034_reports.sql:795 | 0 || harmless - superseded, no live prosrc references it |
| `eval_comparable` | 0033_eval_store.sql:307 | PUBLIC, rk2_owner, rk2_runtime | none | 0 || **load-bearing** - eval store has no writer either (s3.1) |
| `eval_family_coverage_of` | 0033_eval_store.sql:286 | PUBLIC, rk2_owner, rk2_runtime | none | 0 || **load-bearing** - eval store has no writer either (s3.1) |
| `eval_precision` | 0033_eval_store.sql:260 | PUBLIC, rk2_owner, rk2_runtime | none migration-time call: 0033_eval_store.sql:127 | 0 || **load-bearing** - eval store has no writer either (s3.1) |
| `eval_recall_by_kind` | 0033_eval_store.sql:244 | PUBLIC, rk2_owner, rk2_runtime | none migration-time call: 0033_eval_store.sql:127 | 0 || **load-bearing** - eval store has no writer either (s3.1) |
| `find_in_database` | 20260810T173000Z__sealed_wire_artifacts.sql:178 | rk2_owner, rk2_runtime | none | 8 || **load-bearing** - secret-leak sweep with no caller |
| `issue_pivot_stamp` | 20260817T000000Z__a_pivot_is_stamped_from_the_run_that_showed_it.sql:931 | rk2_owner, rk2_runtime | none | 1 || **load-bearing** - sole writer of `pivot_stamps` |
| `mark_stale_selections` | 0032_playbooks.sql:561 | PUBLIC, rk2_owner, rk2_runtime | none | 1 || **load-bearing** - sole writer of `playbook_selections.went_stale_at` |
| `mcp_enum` | 0018_vocabularies.sql:530 | PUBLIC, rk2_owner, rk2_runtime | none | 0 || **load-bearing** - roster.py hard-codes the same enums |
| `mcp_enum_described` | 0018_vocabularies.sql:546 | PUBLIC, rk2_owner, rk2_runtime | none | 0 || **load-bearing** - roster.py hard-codes the same enums |
| `mcp_transport_makeability` | 0025_transport_claims.sql:674 | PUBLIC, rk2_owner, rk2_runtime | none migration-time call: 0025_transport_claims.sql:201 | 0 || **load-bearing** - refusal never published to agent |
| `open_finding` | 20260815T120000Z__a_supported_claim_becomes_a_candidate.sql:758 | rk2_owner, rk2_runtime | none | 11 || **load-bearing** - only path hypothesis to Finding |
| `open_impact_task` | 20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1209 | rk2_owner, rk2_runtime | none | 3 || **load-bearing** - tested, never invoked |
| `playbook_funnel` | 0032_playbooks.sql:483 | PUBLIC, rk2_owner, rk2_runtime | none | 2 || **load-bearing** - funnel report never asked for |
| `read_kill_chain` | 20260818T000000Z__a_chain_is_composed_and_stays_sound.sql:797 | rk2_human, rk2_owner, rk2_runtime | none | 1 || **load-bearing** - only rk2_human verb operator CLI never calls |
| `resolve_egress_token` | 0022_hooks_and_receipts.sql:322 | PUBLIC, rk2_owner, rk2_runtime | none | 0 || harmless-superseded by `authorize_egress_request`, but still PUBLIC |
| `retire_program` | 0011_lifecycle.sql:5 | PUBLIC, rk2_owner, rk2_runtime | none migration-time call: 0002_programs.sql:13 | 3 || harmless - documented later-phase lifecycle verb |

Corrections to the mechanical "migration-time call" column above, checked by hand:

- Real migration-time calls (DDL helpers, correctly wired): `assert_standing_checks()`
  at `0030_corpus_corrections.sql:655` (`DO $$ BEGIN PERFORM ...`), and
  `attach_actor_kind_guards()` at `0026_human_control.sql:1030`,
  `0037_lane_quota.sql:763`, `20260811T130000Z__halt_at_egress.sql:227`,
  `20260818T000000Z__a_chain_is_composed_and_stays_sound.sql:889` and five more.
  Both are **harmless**: they are schema-assembly helpers, called when the schema
  is assembled.
- Not calls, only mentions inside `COMMENT ON` strings: `eval_precision` and
  `eval_recall_by_kind` at `0033_eval_store.sql:127`, `mcp_transport_makeability`
  at `0025_transport_claims.sql:201`, `retire_program` at `0002_programs.sql:13`.
- `cvss_band` at `0034_reports.sql:795,852` **was** a real call, inside
  `apply_computed_cvss` and `check_finding_reporting`. Both function bodies were
  later replaced. Confirmed dead in the live catalogue:
  `select proname from pg_proc where prosrc like '%cvss_band%'` returns **0 rows**.

### 4.1 Grants to a role that never calls

`aclexplode(proacl)` over the 501 user functions:

| role | EXECUTE on | of those, with no caller anywhere |
|---|---|---|
| `rk2_owner` | 495 | 26 |
| `rk2_runtime` | 467 | **26** |
| `rk2_human` | 56 | 1 (`read_kill_chain`) |
| `rk2_state` | 6 | 0 |
| `rk2_proxy` | 14 | 0 |
| `rk2_restore` | 1 | 0 |
| `rk2_readonly` | 0 | 0 |

Every one of the 26 orphans is granted to `rk2_runtime`, the role the harness
connects as. Eleven of them are additionally published in `runtime_verb_surface`
-- the catalogue `check_runtime_privileges()` asserts the runtime's grants
against: `apply_computed_cvss`, `assert_role_catalogue`, `attach_actor_kind_guards`,
`build_kill_chain`, `find_in_database`, `issue_pivot_stamp`,
`lane_signal_budget_fraction`, `lane_signal_hunt_backpressure`,
`lane_signal_recon_novelty_rise`, `open_finding`, `open_impact_task`,
`read_kill_chain`. (The three `lane_signal_*` are reached by dynamic dispatch and
are *not* in the 26; they are listed here only because the verb surface is the
place the discrepancy would be caught.) A verb in `runtime_verb_surface` that no
Python line names is a grant the schema asserts and the runtime never spends.

Seventeen of the 26 also carry a `PUBLIC` EXECUTE grant -- `add_entity`,
`assert_event_coverage`, `assert_server_baseline`, `assert_standing_checks`,
`compose_finding_report`, `cvss_band`, `eval_comparable`, `eval_family_coverage_of`,
`eval_precision`, `eval_recall_by_kind`, `mark_stale_selections`, `mcp_enum`,
`mcp_enum_described`, `mcp_transport_makeability`, `playbook_funnel`,
`resolve_egress_token`, `retire_program` -- these are the ones no migration ever
`REVOKE`d from `PUBLIC`. Two of them mutate state (`add_entity`,
`mark_stale_selections`) and one is `retire_program`.

### 4.2 Which are load-bearing

**Load-bearing -- a designed verb with a full test suite and no production caller:**

| function | what it is | evidence it was meant to be live |
|---|---|---|
| `open_finding` | the only way a supported hypothesis becomes a Finding | 11 references in `tests/test_database.py`, incl. `OPEN_FINDING = "SELECT open_finding($1::uuid, $2::uuid, $3, $4)"` at `:28927` and `:29509`; `docs/specs/production-harness-v2/issues/41-*.md:63` reasons about what it writes |
| `open_impact_task` | opens the task that demonstrates authorized impact | 3 test references |
| `build_kill_chain` / `read_kill_chain` | compose and read a kill chain | `tests/test_database.py:32980` `BUILD = "SELECT build_kill_chain(...)"`; `docs/specs/production-harness-v2/issues/40-*.md` is the ticket. `read_kill_chain` is the one function granted to `rk2_human` that the operator CLI never calls |
| `apply_computed_cvss` | writes the computed CVSS onto a finding | `tests/test_database.py:34556` `CVSS = "SELECT apply_computed_cvss($1::uuid)"`. `findings.severity` therefore keeps whatever `open_finding` would have written -- and `open_finding` is itself uncalled |
| `compose_finding_report` | projects a finding into a report | 3 test references; the report tables it reads (`report_blocks`, `report_template_blocks`, `report_templates`) are all seed-only |
| `add_entity` | the guarded entity creator (scope classification included) | 20 test references. `src/redkraken/program.py:1039` bypasses it with a raw `INSERT INTO entities (program_id, type, dedup_key, metadata)` |
| `mark_stale_selections` | the only writer of `playbook_selections.went_stale_at` | s1.3(e) |
| `find_in_database` | the cross-table secret-leak search; 8 test references | `rk2_owner`+`rk2_runtime` only; no CLI path in `src/` reaches it |
| `resolve_egress_token` | five migrations' comments say "the proxy refuses it (`resolve_egress_token` requires 'running')" | `src/redkraken/proxy.py` uses `authorize_egress_request` instead; the older verb is orphaned and still granted to `PUBLIC` |
| `mcp_enum`, `mcp_enum_described`, `mcp_transport_makeability` | `0018_vocabularies.sql:528` says "`mcp_enum()` is what the MCP server calls" to build the tool-schema enum from `property_classes` (57 rows) / `observation_kinds` (16 rows) / `transport_makeability` (5 rows) | `src/redkraken/roster.py` builds every enum in Python instead (`ENTITY_TYPES` at `:182`, `HYPOTHESIS_STATUSES` at `:196`, the five `question_code`s at `:733`). Two sources of truth for the same closed set, and the database's is the unread one |
| `eval_precision`, `eval_recall_by_kind`, `eval_family_coverage_of`, `eval_comparable` | the read side of the eval store | the write side does not exist either (s3.1) |
| `issue_pivot_stamp` | stamps a capability pivot from the tool run that showed it | 1 test reference; `pivot_stamps` is written by nothing else |
| `playbook_funnel` | the selection funnel report | 2 test references |

**Harmless:**

- `assert_event_coverage`, `assert_server_baseline`, `assert_role_catalogue`,
  `assert_standing_checks`, `attach_actor_kind_guards` -- schema-assembly and
  startup assertions. `0030_corpus_corrections.sql` and
  `20260810T094500Z__bounded_state_reads.sql:443` explicitly document that
  `assert_standing_checks()` is *deliberately not called* by later files. The
  `check_*` counterparts (`check_server_baseline`, `check_check_registration`,
  `check_role_catalogue`) are all registered in `standing_checks` and do run.
- `cvss_band` -- superseded leftover.
- `retire_program` -- a lifecycle verb the CLI does not expose yet; 3 test
  references, and `programs.closed_at` / `purge_after` are its only writers, so it
  is self-consistently a later phase.
- The four `evidence_profile_*` and three `lane_signal_*` functions are **not**
  orphans: they are reached by `EXECUTE format('SELECT %I($1)', ...)` from
  `hypothesis_transition_refusal` and `lane_quota_signals_of` respectively.

---

## 5. Constraints and triggers that can never fire, or that contradict another rule

### 5.1 CHECK constraints over columns nothing writes

552 CHECK/EXCLUDE constraints exist. Narrowing to *tables that do receive runtime
writes* (so a seeded catalogue's own constraints, which fire at migration time,
are excluded) and to constraints **every** referenced column of which has no live
writer: **67**. Substituting each column's declared default into the constraint
expression and evaluating it read-only
(`SELECT (<expr with defaults substituted>) IS NOT FALSE`) shows every one of them
passes -- i.e. none of them can ever fail, because the only value they will ever
see is the default. Seventeen on `scheduler_weights` are excluded as false positives
(`version_scheduler_weights` copies every column forward with a column-list-free
`INSERT ... SELECT`). The remaining 50:

| CHECK | table | referenced columns (all unwritten) | value under the defaults |
|---|---|---|---|
| `applications_entity_type_check` | `applications` | `entity_type` | passes |
| `domains_entity_type_check` | `domains` | `entity_type` | passes |
| `endpoints_entity_type_check` | `endpoints` | `entity_type` | passes |
| `eval_family_coverage_found_check` | `eval_family_coverage` | `found` | passes |
| `eval_family_coverage_gt_entries_check` | `eval_family_coverage` | `gt_entries` | passes |
| `eval_found_le_entries` | `eval_family_coverage` | `gt_entries`, `found` | passes |
| `eval_bucket_owns` | `eval_fn_attribution` | `bucket`, `owner` | passes |
| `eval_fn_attribution_bucket_check` | `eval_fn_attribution` | `bucket` | passes |
| `eval_fn_attribution_owner_check` | `eval_fn_attribution` | `owner` | passes |
| `eval_suppression_cites_the_row` | `eval_fn_attribution` | `bucket`, `near_match_id` | passes |
| `eval_gt_accounting` | `eval_pair_scores` | `gt_recallable`, `tp`, `fn_not_found`, `fn_unproven`, `fn_suppressed`, `fn_near_miss` | passes |
| `eval_own_pair_is_scorable` | `eval_pair_scores` | `fixture_kind`, `pair_clean` | passes |
| `eval_pair_scores_converted_fraction_check` | `eval_pair_scores` | `converted_fraction` | passes |
| `eval_pair_scores_duplicate_check` | `eval_pair_scores` | `duplicate` | passes |
| `eval_pair_scores_false_positive_rate_check` | `eval_pair_scores` | `false_positive_rate` | passes |
| `eval_pair_scores_fixture_kind_check` | `eval_pair_scores` | `fixture_kind` | passes |
| `eval_pair_scores_fn_near_miss_check` | `eval_pair_scores` | `fn_near_miss` | passes |
| `eval_pair_scores_fn_not_found_check` | `eval_pair_scores` | `fn_not_found` | passes |
| `eval_pair_scores_fn_suppressed_check` | `eval_pair_scores` | `fn_suppressed` | passes |
| `eval_pair_scores_fn_unproven_check` | `eval_pair_scores` | `fn_unproven` | passes |
| `eval_pair_scores_fp_check` | `eval_pair_scores` | `fp` | passes |
| `eval_pair_scores_gt_declared_check` | `eval_pair_scores` | `gt_declared` | passes |
| `eval_pair_scores_gt_recallable_check` | `eval_pair_scores` | `gt_recallable` | passes |
| `eval_pair_scores_precision_strict_check` | `eval_pair_scores` | `precision_strict` | passes |
| `eval_pair_scores_recall_strict_check` | `eval_pair_scores` | `recall_strict` | passes |
| `eval_pair_scores_tool_runs_check` | `eval_pair_scores` | `tool_runs` | passes |
| `eval_pair_scores_tp_check` | `eval_pair_scores` | `tp` | passes |
| `eval_pair_scores_unattributed_real_check` | `eval_pair_scores` | `unattributed_real` | passes |
| `eval_recallable_le_declared` | `eval_pair_scores` | `gt_declared`, `gt_recallable` | passes |
| `eval_third_party_declares_coverage` | `eval_pair_scores` | `fixture_kind`, `converted_fraction` | passes |
| `eval_third_party_has_no_precision` | `eval_pair_scores` | `fixture_kind`, `precision_strict`, `false_positive_rate`, `pair_clean` | passes |
| `finding_gate_clearances_actor_kind_check` | `finding_gate_clearances` | `actor_kind` | passes |
| `hosts_entity_type_check` | `hosts` | `entity_type` | passes |
| `hypothesis_retest_triggers_kind_check` | `hypothesis_retest_triggers` | `kind` | passes |
| `identities_entity_type_check` | `identities` | `entity_type` | passes |
| `impact_demonstrations_run_outcome_check` | `impact_demonstrations` | `run_outcome` | passes |
| `parameters_entity_type_check` | `parameters` | `entity_type` | passes |
| `playbook_selections_outcome_check` | `playbook_selections` | `outcome` | passes |
| `playbooks_baseline_check` | `playbooks` | `baseline` | passes |
| `playbooks_effects_check` | `playbooks` | `effects` | passes |
| `playbooks_path_check` | `playbooks` | `path` | passes |
| `playbooks_provenance_check` | `playbooks` | `provenance` | passes |
| `playbooks_risk_check` | `playbooks` | `risk` | passes |
| `playbooks_source_sha256_check` | `playbooks` | `source_sha256` | passes |
| `playbooks_version_check` | `playbooks` | `version` | passes |
| `secret_kek_check` | `secret_kek` | `created_at`, `retired_at` | passes |
| `services_entity_type_check` | `services` | `entity_type` | passes |
| `tasks_skill_sha256_check` | `tasks` | `skill_sha256` | passes |
| `tasks_skill_version_check` | `tasks` | `skill_version` | passes |
| `technologies_entity_type_check` | `technologies` | `entity_type` | passes |

Of these, the ones that matter are the ones whose *unreachable arm* was the point
of the constraint:

- `tasks_skill_sha256_check`, `tasks_skill_version_check` -- s1.3(a).
- `program_scope_rules_check`, `program_scope_rules_check1`,
  `program_scope_rules_check2` -- s1.3(c): the `'cidr'` arm and the tier arm are
  both unreachable.
- `playbook_selections_outcome_check` -- s1.3(e): only `'running'` is reachable.
- `hypothesis_near_matches_stage2_cols`,
  `hypothesis_near_matches_candidate_matches_action` -- s1.3(g).
- The 27 `eval_*` constraints -- an entire consistency model (`eval_gt_accounting`:
  `tp + fn_not_found + fn_unproven + fn_suppressed + fn_near_miss = gt_recallable`;
  `eval_third_party_has_no_precision`; `eval_bucket_owns`) over four tables nothing
  writes.
- `tool_runs_hook_identity_ck` is *not* in this list (its `transport` side is
  written) but is the sharper case, because it is a **live** constraint whose
  effect is to pin an entire column family to NULL -- see s5.2.

Harmless in this list: the eight `*_entity_type_check` discriminators,
`impact_demonstrations_run_outcome_check`,
`finding_gate_clearances_actor_kind_check`, `secret_kek_check`, and the
`playbooks_*` constraints (which do fire, at seed time, over 50 rows).

### 5.2 A live constraint that makes a column family unreachable

`0022_hooks_and_receipts.sql` declares both halves of the hook-provenance model
and then pins them shut:

```
ADD COLUMN transport text NOT NULL DEFAULT 'runtime'
           CHECK (transport IN ('builtin','mcp','runtime'))     -- 0022:200
tool_runs_hook_identity_ck  CHECK ((transport = 'runtime') = (tool_use_id IS NULL))
```

Because all five writers of `tool_runs` pass the literal `'runtime'` (s1.3(b)),
`tool_use_id` is forced NULL by the constraint, and with it the unique index
`tool_runs_tool_use_id_uq`, which exists so that "a retried or duplicated hook
callback cannot open a second receipt" (`0022:188-190`). The constraint is not
wrong; nothing has ever been able to exercise the other side of it.

### 5.3 Contradictory pairs

Mechanical search first: for every trigger function that `RAISE`s on a literal
comparison of `NEW.<col>`, cross-checked against every CHECK on the same table
that pins or restricts the same column -- **0 same-column contradictions**. The
contradictions in this schema are all cross-table, so they were found by walking
the guards that read another relation (49 trigger functions do).

**(a) `observations` x `receipts` -- the known pair, fixed in the tree, unfixed in
the probe.** `reject_proxy_internal_evidence()` as applied at migration 135:

```
IF l = 'proxy_internal' THEN RAISE EXCEPTION 'receipt % is lane proxy_internal
    and cannot back an observation'
```

`transport_observation_guard()` requires a `transport_parameters_observed`
observation to cite a receipt with `transport_citable = true`;
`receipts_transport_citable` requires `purpose = 'transport_measurement'`;
`receipts_transport_measurement_shape` requires that purpose to be on
`lane = 'proxy_internal'`. Unsatisfiable together. The fourth unapplied migration
rewrites the guard to `IF r.lane = 'proxy_internal' AND NOT r.transport_citable`
(`20260923T000000Z__...:475-486`) and says so at `:445-472`.

**(b) `finding_evidence` x `receipts` -- the same collision one layer up, and NOT
repaired by ticket 93.** `reject_non_agent_evidence()` (`0034_reports.sql:457`,
attached at `:479` to `finding_evidence` and to `finding_chain_step_citations`):

```
IF v_kind = 'receipt' AND coalesce(v_lane,'missing') NOT IN ('agent','replay') THEN
    RAISE EXCEPTION 'ungrounded: observation % is backed by a % receipt; evidence
        may cite the agent and replay lanes'
```

Now follow the transport claim path for a `probe_only` property class
(`transport_makeability` seeds exactly two: `transport.tls_configuration` and
`transport.certificate_trust`):

1. `transport_evidence_guard()` on `hypothesis_evidence`: for a `probe_only`
   class, a `supports` row must cite a `transport_parameters_observed` observation.
2. `transport_observation_guard()` on `observations`: such an observation must
   cite a `transport_citable` receipt.
3. `receipts_transport_measurement_shape` (both before and after ticket 93):
   `purpose = 'transport_measurement'` implies `lane = 'proxy_internal'`.
4. `transition_rules` for `machine='finding'`, `validating -> validated`:
   `min_supporting_evidence = 2`, `min_control_evidence = 1`, and
   `enforce_finding_transition()` counts those rows out of `finding_evidence`.
5. `reject_non_agent_evidence()` refuses to put that observation into
   `finding_evidence` at all, because its receipt's lane is `proxy_internal`.

So a `probe_only` transport hypothesis can reach `supported` and can never become
a `validated` Finding: the only observation that can support it is the only
observation that cannot be its evidence. This is the *same* defect as (a), on the
adjacent table, and the fix in `20260923T000000Z` touches only
`reject_proxy_internal_evidence`. `reject_non_agent_citation()`
(`0034_reports.sql:482`) has the identical rule for `finding_chain_step_citations`,
so the chain-report path is closed for the same two classes.

**(c) Triggers on tables nothing writes.** Five, all guards over seed/config
tables, all of which fire during migration and are therefore doing their job:

| trigger | on | function |
|---|---|---|
| `evidence_profiles_fn_guard` | `evidence_profiles` | `check_evidence_profile_exists` |
| `lane_quota_profile_slots_frozen` | `lane_quota_profile_slots` | `lane_quota_profile_frozen` |
| `lane_quota_signals_clockfree` | `lane_quota_signals` | `lane_quota_signal_is_clockfree` |
| `notification_channels_placeholders` | `notification_channels` | `assert_channel_placeholders` |
| `scheduler_lanes_no_unversioned_write` | `scheduler_lanes` | `scheduler_lanes_immutable` |

Verdict: harmless.

A sixth group is worth naming separately: seven triggers sit on tables of s3.1
that have never had a row, so they have never fired --
`agent_sessions_emit_event` (`emit_event`), and six `derive_program_id`
triggers on `eval_family_coverage`, `eval_fn_attribution`, `eval_pair_scores`,
`hypothesis_embeddings`, `hypothesis_retest_triggers` and `observation_embeddings`.
`check_hook_provenance()` arm 2 asserts that `agent_sessions` carries an
`ENABLE ALWAYS` `emit_event` trigger -- a standing check that passes over a table
no code path can put a row in. The other seven never-inserted tables
(`report_queue`, `interception_cas`, `secret_dek`, `redaction_failure`,
`program_known_issues`, `eval_runs`, `cross_program_exempt_fks`) carry RLS
policies and constraints but no guards at all.

---

## 6. Views and columns nothing selects

### 6.1 The 25 views

| view | declared | SELECT granted to | live readers | verdict |
|---|---|---|---|---|
| `artifact_refs` | 0020_state_access.sql:293 | rk2_owner, rk2_runtime | `fn:ready_for` || live |
| `artifacts_due_for_purge` | 0011_lifecycle.sql:15 | rk2_owner, rk2_runtime | **none** || **no reader** - see 6.1 notes |
| `current_lane_quota` | 0037_lane_quota.sql:338 | rk2_human, rk2_owner, rk2_runtime | `fn:advance_lane_quota`, `fn:force_lane_quota`, `fn:lane_signal_recon_novelty_rise`, `view:effective_lane_capacity` || live |
| `effective_lane_capacity` | 0023_scheduler_ranking.sql:215 | rk2_owner, rk2_runtime | `fn:check_scheduler_closure`, `fn:claimable_for`, `fn:identity_clamped_for`, `fn:subagent_started_for` || live |
| `finding_cited_receipts` | 0034_reports.sql:512 | rk2_owner, rk2_runtime | `fn:finding_evidence_receipts`, `fn:finding_fact_tokens`, `fn:finding_limitations`, `fn:report_source_bundle` || live |
| `finding_class_divergence` | 0018_vocabularies.sql:504 | rk2_owner, rk2_runtime | `view:report_review_signals` || live via `report_review_signals` |
| `hnsw_headroom` | 0027_migration_baseline.sql:364 | rk2_owner, rk2_runtime | `fn:check_server_baseline` || live, but over two empty tables |
| `lane_budget` | 20260813T230000Z__reserve_the_worst_case_and_reconcile_it.sql:253 | rk2_owner, rk2_runtime | `fn:budget_refusal_for`, `py:redkraken/capsule.py`, `py:redkraken/panels.py` || live |
| `lane_capacity` | 0019_role_kinds.sql:203 | rk2_owner, rk2_runtime | `fn:check_role_kind_mapping` || live |
| `managed_tables` | 0027_migration_baseline.sql:113 | rk2_owner, rk2_runtime | `fn:base_role_catalogue`, `fn:check_event_coverage`, `fn:check_runtime_connection`, `fn:enforce_always_triggers` || live |
| `orchestrator_session_usage` | 20260814T010000Z__rotate_the_orchestrator_and_resume.sql:210 | rk2_owner, rk2_runtime | `fn:check_orchestrator_rotation`, `fn:open_orchestrator_session`, `fn:orchestrator_session_spent`, `fn:rotate_orchestrator_session`, `py:redkraken/capsule.py` || live, but over an empty `agent_sessions` |
| `program_budget` | 0023_scheduler_ranking.sql:89 | rk2_owner, rk2_runtime | `fn:cancel_reason_for`, `fn:claimable_for`, `fn:lane_signal_budget_fraction`, `view:program_capacity` || live |
| `program_capacity` | 20260813T230000Z__reserve_the_worst_case_and_reconcile_it.sql:196 | rk2_owner, rk2_runtime | `fn:budget_refusal_for`, `fn:claim_task`, `fn:open_orchestrator_session`, `fn:open_validation_session`, `py:redkraken/capsule.py`, `py:redkraken/panels.py` || live |
| `program_isolation_candidates` | 0017_program_isolation.sql:147 | rk2_owner, rk2_runtime | **none** || **no reader** - DDL-time helper |
| `report_review_signals` | 0034_reports.sql:869 | rk2_owner, rk2_runtime | `fn:finding_limitations` || live |
| `runtime_relations` | 20260909T000000Z__the_runtime_holds_what_the_surface_declares.sql:140 | rk2_owner, rk2_restore, rk2_runtime | `fn:apply_runtime_grants`, `fn:check_runtime_privileges` || live |
| `runtime_verbs` | 20260909T000000Z__the_runtime_holds_what_the_surface_declares.sql:122 | rk2_owner, rk2_restore, rk2_runtime | `fn:check_runtime_privileges` || live |
| `scheduler_lane_state` | 0023_scheduler_ranking.sql:251 | rk2_owner, rk2_runtime | `fn:claimable_for`, `fn:lane_signal_hunt_backpressure`, `fn:rank_candidates`, `fn:rank_pass` || live |
| `subject_facts` | 0032_playbooks.sql:90 | rk2_owner, rk2_runtime | `fn:playbooks_by_trigger` || live |
| `v_artifacts` | 0020_state_access.sql:380 | rk2_owner, rk2_runtime | `py:redkraken/artifact.py`, `py:redkraken/packet.py` || live (agent surface) |
| `v_decision_queue` | 0026_human_control.sql:969 | rk2_human, rk2_owner | `py:redkraken/operator.py` || live (operator); one column dropped - see 6.2 |
| `v_evidence` | 0020_state_access.sql:352 | rk2_owner, rk2_runtime | `py:redkraken/packet.py` || live (agent surface) |
| `v_negative_knowledge` | 20260814T080000Z__a_refutation_is_kept_and_made_due.sql:1049 | rk2_owner, rk2_runtime | **none** || **no reader** - see 6.1 notes |
| `v_records` | 20260810T094500Z__bounded_state_reads.sql:176 | rk2_owner, rk2_runtime | `py:redkraken/packet.py`, `py:redkraken/state.py` || live (agent surface) |
| `v_surface_deltas` | 20260813T140000Z__the_surface_gets_a_fingerprint.sql:733 | rk2_owner, rk2_runtime | **none** || **no reader** - see 6.1 notes |

Four have no live reader:

| view | declared | granted to | verdict |
|---|---|---|---|
| `artifacts_due_for_purge` | `0011_lifecycle.sql:15`, replaced `20260810T173000Z__sealed_wire_artifacts.sql:139` | `rk2_runtime` | **load-bearing.** The refcount of collectable bytes. Named in `src/redkraken/proxy.py:2882` only inside a comment. Nothing selects it, and `artifacts.purged_at` has no writer (s1.3(d)): the purge path is declared end-to-end and connected at neither end. |
| `v_negative_knowledge` | `20260814T080000Z__a_refutation_is_kept_and_made_due.sql:1049`, `GRANT SELECT ... TO rk2_runtime` at `:1094` | `rk2_runtime` | **load-bearing.** 17 columns projecting refuted hypotheses and their retest state. Read only by `tests/test_database.py:16167`. `refresh_negative_knowledge` writes the underlying rows; nothing in `src/` ever surfaces them, so "what we already know is false" is computed and never told to anyone. |
| `v_surface_deltas` | `20260813T140000Z__the_surface_gets_a_fingerprint.sql:733` | `rk2_runtime` | **load-bearing.** 12 columns of what changed between two surface fingerprints. Read only by `tests/test_database.py:14978,15124,15146,15159,15249`. `compute_surface_fingerprint` and `rk2_surface_section_deltas` produce the inputs; nothing consumes the view. |
| `program_isolation_candidates` | `0017_program_isolation.sql:147` | `rk2_runtime` | harmless -- a DDL-time helper, used twice inside its own migration (`:189`, `:238`) to generate the isolation constraints. |

`finding_class_divergence` is reachable only through `report_review_signals`,
which `finding_limitations` reads -- a chain, not an orphan.

### 6.2 View columns the agent never receives

The four views the agent's connection is built around are `v_records`,
`v_evidence`, `v_artifacts` (`src/redkraken/packet.py:517,531,567`;
`src/redkraken/state.py:94,103,105`) and `v_decision_queue`
(`src/redkraken/operator.py:57`).

- `v_records`, `v_evidence` and `v_artifacts` are consumed whole -- `packet.py`
  either selects `record` (an already-built `jsonb`) or rebuilds every view column
  into one. No dropped columns.
- **`v_decision_queue.request_digest` is the one view column the reader drops.**
  `operator.py:57` selects `program, label, question_code, tool, risk_class,
  question, requested_at, deadline_at, status, answered_by, answer` -- 11 of 12.
  `request_digest` is the canonicalised request the decision was asked about
  (`0026_human_control.sql:364`, fed to `equivalence_key()` at `:404` and rendered
  into the question at `:473`). The operator sees the rendered sentence and never
  the digest it was rendered from. Minor, but it is the harness computing
  something and throwing it away at the last hop.

### 6.3 The bigger version of the same question: the agent's read surface

`state_read_surface` (`0020_state_access.sql`) is the registry `apply_state_grants`
turns into per-column `GRANT SELECT (...) TO rk2_state`. It has 454 rows, 429 of
them naming base-table columns.

**48 of those 429 columns can never hold anything but NULL or a constant.** These
are columns the harness declared the agent may read, granted, and then never
filled -- the read-side mirror of s1.

| column granted to `rk2_state` | always | `state_read_surface.added_by` |
|---|---|---|
| `applications.entity_type` | constant `'application'::text` | 33-seed |
| `artifacts.purged_at` | NULL | 33-seed |
| `domains.entity_type` | constant `'domain'::text` | 33-seed |
| `endpoints.entity_type` | constant `'endpoint'::text` | 33-seed |
| `findings.duplicate_of_finding_id` | NULL | 33-seed |
| `findings.external_ref` | NULL | 33-seed |
| `hosts.asn` | NULL | 33-seed |
| `hosts.entity_type` | constant `'host'::text` | 33-seed |
| `hypotheses.observed_fingerprint` | NULL | 33-seed |
| `hypotheses.superseded_by` | NULL | 33-seed |
| `hypothesis_near_matches.candidate_hypothesis_id` | NULL | 33-seed |
| `hypothesis_near_matches.embedding_model` | NULL | 33-seed |
| `hypothesis_near_matches.similarity` | NULL | 33-seed |
| `identities.acquired_at` | NULL | 33-seed |
| `identities.tenant_entity_id` | NULL | 33-seed |
| `interception_cas.label` | NULL | 33-seed |
| `interception_cas.not_after` | NULL | 33-seed |
| `interception_cas.not_before` | NULL | 33-seed |
| `interception_cas.program_id` | NULL | 33-seed |
| `interception_cas.retired_at` | NULL | 33-seed |
| `interception_cas.spki_sha256` | NULL | 33-seed |
| `interception_cas.subject` | NULL | 33-seed |
| `interception_cas.superseded_by` | NULL | 33-seed |
| `parameters.entity_type` | constant `'parameter'::text` | 33-seed |
| `program_known_issues.class_id` | NULL | 19 |
| `program_known_issues.entity_like` | NULL | 19 |
| `program_known_issues.note` | NULL | 19 |
| `program_known_issues.program_id` | NULL | 19 |
| `program_known_issues.source` | NULL | 19 |
| `receipts.transport_citable` | GENERATED, and false for every writable row | 33-seed |
| `receipts.transport_divergence` | GENERATED, and false for every writable row | 33-seed |
| `relationships.metadata` | constant `'{}'::jsonb` | 33-seed |
| `services.entity_type` | constant `'service'::text` | 33-seed |
| `tasks.evidence_profile_id` | NULL | 33-seed |
| `tasks.expected_information_gain` | NULL | 33-seed |
| `tasks.potential_impact` | NULL | 33-seed |
| `tasks.required_skills` | constant `'{}'::text[]` | 33-seed |
| `tasks.skill_name` | NULL | 33-seed |
| `tasks.skill_sha256` | NULL | 33-seed |
| `technologies.entity_type` | constant `'technology'::text` | 33-seed |
| `tests.supersedes_test_id` | NULL | 33-seed |
| `tool_runs.args_sha256` | NULL | 33-seed |
| `tool_runs.mcp_server` | NULL | 33-seed |
| `tool_runs.result_sha256` | NULL | 33-seed |
| `tool_runs.sdk_agent_id` | NULL | 33-seed |
| `tool_runs.sdk_agent_type` | NULL | 33-seed |
| `tool_runs.session_id` | NULL | 33-seed |
| `tool_runs.tool_use_id` | NULL | 33-seed |

Grouped: the eight `entity_type` discriminators are harmless (constant by design).
The other 40 are the columns of s1.3 -- the whole of `interception_cas` (10), the
whole of `program_known_issues` (5), all seven `tool_runs` hook columns, six
`tasks` columns, both generated `receipts` transport columns, and the scattered
always-NULL edges (`artifacts.purged_at`, `findings.duplicate_of_finding_id`,
`findings.external_ref`, `hypotheses.observed_fingerprint`,
`hypotheses.superseded_by`, `identities.tenant_entity_id`,
`identities.acquired_at`, `relationships.metadata`, `tests.supersedes_test_id`,
`hosts.asn`, the three `hypothesis_near_matches` stage-2 columns).

---

## What a gate would have to assert

Every check below is mechanical and runs against a migrated database plus the
source tree. The pattern this axis keeps producing is *declared, granted,
constrained, and never connected* -- so the gates are all of the form "a
declaration implies a producer" or "a declaration implies a consumer".

### G1. Every table has a producer, or is registered as seed-only

There is already a registry with the right shape: `0030_corpus_corrections.sql`
classifies tables (`'derived'`, `'bookkeeping'`, ...). Extend it to a
`table_provenance(table_name, kind)` where `kind IN ('runtime','seed','view')` and
assert:

```sql
-- every table declared 'runtime' must be named by an INSERT in some pg_proc body
SELECT c.relname
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN table_provenance tp ON tp.table_name = c.relname AND tp.kind = 'runtime'
 WHERE n.nspname = 'public' AND c.relkind = 'r'
   AND NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace pn ON pn.oid = p.pronamespace
                    WHERE pn.nspname = 'public'
                      AND p.prosrc ~* ('insert\s+into\s+(public\.)?' || c.relname || '\M'));
```

plus the Python half of the same question, run from the test suite: for each
`kind='runtime'` table with no SQL-function `INSERT`, require a literal
`INSERT INTO <t>` in `src/**/*.py`. **This single gate catches all 14 tables in
s3.1**, `report_queue` first.

### G2. Every column a rule depends on has a writer

For each column that appears in a CHECK expression, a generated-column
expression, an index definition, an RLS policy, or an FK constraint definition,
require at least one writer -- an `INSERT` column list, an `UPDATE ... SET`
target, or a `NEW.<col> :=` in a trigger on that table -- in `pg_proc` or in
`src/`. Exempt only:

- columns whose default is `uuidv7() | gen_random_uuid() | now() | clock_timestamp() | nextval(...) | pg_current_xact_id()`, or which are `GENERATED AS IDENTITY`;
- columns on tables registered `kind='seed'`;
- columns on an explicit `constant_by_design(table, column, reason)` allowlist --
  which is where the eight `*.entity_type` discriminators,
  `impact_demonstrations.run_outcome`, `finding_gate_clearances.actor_kind` and
  `role_skills.loads_skills` belong, each with the sentence that says why.

**Catches all 144 rows of s1.2**, and forces the 12 harmless ones to be written
down as harmless rather than merely looking harmless.

### G3. Every generated column has a row that makes it true

For each `attgenerated <> ''` column of boolean type, require a test that inserts,
through a real writer, a row for which it is `true`; and separately assert that at
least one writer sets **every** input the expression names. Mechanically:

```sql
-- inputs of a generated expression, as attnames
SELECT c.relname, a.attname, pg_get_expr(d.adbin, d.adrelid)
  FROM pg_attribute a
  JOIN pg_class c ON c.oid = a.attrelid
  JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
 WHERE a.attgenerated <> '';
```

then, for each identifier in the expression that is a column of the same table,
run G2. This is exactly ticket 93: `transport_citable` names `purpose`, and no
writer's `INSERT` column list contained `purpose` with the required value. A
stronger form -- and the one worth having -- is a *satisfying-row* test per
boolean generated column, since it also catches the constraint interaction in G6.

### G4. Every function has a caller, or a declared reason not to

For each `pg_proc` row in `public` not owned by an extension, require one of:

- a call site in another `prosrc`, a view, a CHECK, a default, an index, an RLS
  policy, a `standing_checks.query`, or a `pg_trigger.tgfoid`;
- a call site in `src/**/*.py` -- matching the bare name is sufficient, since
  every SQL statement in `src/` names the function literally;
- a resolvable dynamic dispatch: enumerate the `format('SELECT %I($1)', <prefix> || x)`
  sites (there are two, `evidence_profile_%` and the `lane_quota_signals.fn`
  column) and expand them from the catalogue table they read;
- a row in a new `deferred_verbs(proname, owner_ticket, note)` table saying which
  phase will call it.

**Catches all 26 functions in s4.** The `assert_*` schema-assembly helpers and
`retire_program` go in `deferred_verbs`; `open_finding`, `build_kill_chain`,
`apply_computed_cvss`, `add_entity` and the four `eval_*` do not, because they are
tested as though they were live.

### G5. A verb surface entry implies a caller; a grant implies a verb

```sql
-- every verb the runtime is granted must be named somewhere in src/
SELECT verb FROM runtime_verb_surface;   -- compare against a grep of src/**/*.py
```

and the converse: every function with `has_function_privilege('rk2_runtime', oid,
'EXECUTE')` must either be in `runtime_verb_surface` or be reached from one.
Also assert no orphan carries a `PUBLIC` EXECUTE grant:

```sql
SELECT p.proname
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public'
   AND EXISTS (SELECT 1 FROM aclexplode(p.proacl) a
                WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE');
```

**Catches the 11 verb-surface entries and the 17 `PUBLIC` grants in s4.1.**

### G6. Every constraint must be falsifiable

For each CHECK constraint, substitute the declared default of every referenced
column and evaluate `(<expr>) IS NOT FALSE`. If it evaluates non-FALSE **and**
every referenced column fails G2, the constraint can never fail: raise. The
implementation is four SQL statements and is what produced the 50-row table in
s5.1.

The sharper variant, which would have caught `tool_runs_hook_identity_ck`: for
each CHECK of the form `col = ANY (ARRAY[...])`, collect the set of literals any
writer can actually supply for `col` (from `INSERT ... VALUES` literals and
`UPDATE ... SET col = 'lit'`) and raise when the reachable set is a strict subset
of the declared set. That single rule flags `transport`'s `'builtin'`/`'mcp'`
arms, `program_scope_rules.pattern_kind`'s `'cidr'` arm and
`playbook_selections.outcome`'s `'produced'`/`'exhausted'` arms.

### G7. Cross-table guard satisfiability

The two contradictions in s5.3 have a common shape and can be checked
symbolically without a solver:

1. Build, per table, the set of *implications* its CHECK constraints assert, in
   the restricted form `col_a = 'x' -> col_b = 'y'` (which is how
   `receipts_transport_measurement_shape` is written).
2. Build, per trigger, the set of *requirements* and *refusals* it places on a
   referenced row, in the restricted form "row `r` of table `T` reached through
   FK `f` must / must not have `col = 'lit'`" or "must have `<generated col>` true".
3. For each table that two or more guards constrain through the same FK, chase
   the implications and raise when a required literal and a refused literal
   coincide.

Applied to `observations.receipt_id` this gives (a); applied to
`finding_evidence.observation_id -> observations.receipt_id` it gives (b), which
is still open. A cheaper approximation that catches both: **for every trigger that
requires a referenced receipt to be `transport_citable`, assert that no other
trigger on the same or a descendant table refuses that receipt's `lane`.**

### G8. Every view has a reader; every read-surface column has a writer

```sql
-- views nothing selects
SELECT viewname FROM pg_views WHERE schemaname = 'public';
-- minus: names appearing in any prosrc, any other view definition, or src/**/*.py
```

**Catches `artifacts_due_for_purge`, `v_negative_knowledge`, `v_surface_deltas`.**
A view granted to `rk2_runtime` with no reader is the strongest form of the
signal, since the grant is a claim that somebody reads it.

And the read-surface version, which is the highest-value single query on this
axis:

```sql
-- every column the agent may read must be one some writer can fill
SELECT s.table_name, s.column_name, s.added_by
  FROM state_read_surface s
 WHERE (s.table_name, s.column_name) NOT IN (<the G2 writer set>)
   AND (s.table_name, s.column_name) NOT IN (SELECT table_name, column_name FROM constant_by_design);
```

**Catches all 48 rows of s6.3.**

### G9. A contract's declared write target must have a writer and a handler

`src/redkraken/roster.py` already declares `writes=(...)` per tool contract. Two
assertions, both pure Python and both cheap:

- every table named in a `Contract.writes` tuple exists **and** has a live writer
  (G1's set);
- every tool in `roster.TOOL_GROUPS` is either in `agent.SERVED` or in an explicit
  `NOT_YET_SERVED` tuple with the ticket that will serve it.

**Catches `mcp__rk2__request_report` -> `report_queue`**, which is the one place
where the Python layer and the schema layer each declare half of a feature and
neither implements it.

---

## Summary: load-bearing vs harmless

| finding | count | verdict |
|---|---|---|
| columns nothing writes, after excluding auto-defaults and seeds | 144 | ~15, in 7 named classes, explicitly harmless (s1.4); ~40 load-bearing (s1.3); rest inert |
| generated columns | 4 | 3 fine; `receipts.transport_citable` unsatisfiable at migration 135, fixed by the 4th unapplied migration |
| tables nothing inserts into | 14 + 79 seed-only | 79 seed-only are the intended shape; of the 14, 12 load-bearing, 2 (`secret_dek`, `cross_program_exempt_fks`) superseded/inert; plus 2 seed-only tables with no consumer at all (`playbook_references`, `validation_packet_columns`) |
| functions nobody calls | 26 of 501 | 6 harmless (schema-assembly asserts, `cvss_band`, `retire_program`); 20 load-bearing, all granted to `rk2_runtime`, 11 published in `runtime_verb_surface`, 17 still granted to `PUBLIC` |
| CHECK constraints that can never fail | 50 (of 552) | ~35 load-bearing (the eval store, the task skill binding, the scope CIDR arm, the playbook funnel); the rest are constants-by-design |
| contradictory guard pairs | 2 | (a) fixed in the tree, unapplied in the probe; **(b) `finding_evidence` x `proxy_internal` receipts is open** |
| views nothing selects | 4 of 25 | 3 load-bearing, 1 (`program_isolation_candidates`) a DDL helper |
| agent read-surface columns that are always NULL/constant | 48 of 429 | 8 harmless discriminators, 40 load-bearing |
