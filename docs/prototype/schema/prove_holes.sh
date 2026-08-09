#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# prove_holes.sh -- ticket 33's adversarial checks.
#
# Every case below is run twice against the same database at the same moment:
# once through ticket07_event_log_integrity() (ticket 07's function, verbatim,
# from tests/ticket07_checker.sql) and once through the ticket-33 checker. The
# result that matters is where v07 says nothing.
#
# Runs on its own database (default rk2_holes) so nothing else is disturbed.
# Env: CT (container), HOLES_DB (database name).
# ---------------------------------------------------------------------------
set -uo pipefail

CT=${CT:-rk2-mig-db}
HDB=${HOLES_DB:-rk2_holes}
HERE="$(cd "$(dirname "$0")" && pwd)"
pass=0; fail=0

q()  { docker exec -i "$CT" psql -U postgres -d "$HDB" -At -v ON_ERROR_STOP=1 "$@"; }
qq() { docker exec -i "$CT" psql -U postgres -d "$HDB" -q -v ON_ERROR_STOP=1 "$@"; }

# expect <label> <expected> <actual>
expect() {
    if [[ "$2" == "$3" ]]; then printf '  ok    %-58s %s\n' "$1" "$3"; pass=$((pass+1))
    else printf '  FAIL  %-58s want=%s got=%s\n' "$1" "$2" "$3"; fail=$((fail+1)); fi
}
v07()  { q -c "SELECT count(*) FROM ticket07_event_log_integrity()"; }
# grep -c counts lines, and a refusal may name a table on more than one line
# (once in the checker output, once in the summary). The question is whether it
# is named at all.
named() { grep -q "$1" <<<"$2" && echo 1 || echo 0; }
cov()  { q -c "SELECT coalesce(string_agg(problem||':'||detail,'; '),'-') FROM check_event_coverage() WHERE problem NOT LIKE 'undecided\\_%'"; }
verify_exit() { CT="$CT" DB="$HDB" "$HERE/migrate.sh" verify > /dev/null 2>&1; echo $?; }

echo "== setup: fresh database $HDB, full corpus through ./migrate.sh =="
docker exec -i "$CT" psql -U postgres -q -c "DROP DATABASE IF EXISTS $HDB" > /dev/null 2>&1
CT="$CT" DB="$HDB" "$HERE/migrate.sh" provision > /dev/null 2>&1 \
    || { echo "provision failed"; exit 1; }
CT="$CT" DB="$HDB" "$HERE/migrate.sh" up > /dev/null 2>&1 \
    || { echo "setup failed"; exit 1; }
qq < "$HERE/tests/ticket07_checker.sql" > /dev/null
expect "baseline: v07 checker clean"                    0   "$(v07)"
expect "baseline: coverage clean"                       "-" "$(cov)"
expect "baseline: migrate.sh verify exits 0"            0   "$(verify_exit)"

# ---------------------------------------------------------------------------
echo
echo "== H1: a migration adds a table and never says whether it emits =="
echo "   (the ticket-07 failure mode, taken literally: no config row, no trigger)"
TMPD="$(mktemp -d)"; cp "$HERE"/migrations/*.sql "$TMPD/"
cat > "$TMPD/20991231T235900Z__adds_a_table_with_no_trigger.sql" <<'SQL'
-- A plausible, innocent migration: a new domain table, correct in every way
-- except that nobody decided whether it belongs in the event log.
CREATE TABLE agent_notes (
    id         uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id uuid NOT NULL REFERENCES programs(id) ON DELETE RESTRICT,
    body       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
SQL
out="$(MIGRATIONS_DIR="$TMPD" CT="$CT" DB="$HDB" "$HERE/migrate.sh" up 2>&1)"; rc=$?
expect "H1: migrate.sh up refuses the run"              1 "$rc"
expect "H1: refusal names the table"                    1 "$(named 'table_not_classified.*agent_notes' "$out")"
expect "H1: ticket 07's checker sees nothing (HOLE)"    0   "$(v07)"
expect "H1: ticket 33's checker sees it"                "table_not_classified:agent_notes" "$(cov)"
qq -c "DROP TABLE agent_notes" > /dev/null
qq -c "DELETE FROM rk2_meta.schema_migrations WHERE id LIKE '20991231%'" > /dev/null
rm -rf "$TMPD"

# ---------------------------------------------------------------------------
echo
echo "== H2: the trigger is there but switched off =="
echo "   (README of ticket 32 names this: the checker reads existence, not tgenabled)"
qq -c "ALTER TABLE relationships DISABLE TRIGGER relationships_emit_event" > /dev/null
expect "H2: ticket 07's checker sees nothing (HOLE)"    0 "$(v07)"
expect "H2: ticket 33's checker sees it"                "trigger_disabled:relationships tgenabled=D" "$(cov)"
expect "H2: migrate.sh verify exits non-zero"           1 "$(verify_exit)"
# The obvious repair is not a repair. A plain ENABLE returns tgenabled to 'O',
# not 'A', and an 'O' trigger is silent for any session that sets
# session_replication_role='replica' -- which is exactly what pg_restore does.
# So the checker keeps complaining, and it is right to.
qq -c "ALTER TABLE relationships ENABLE TRIGGER relationships_emit_event" > /dev/null
expect "H2: a plain ENABLE is NOT a restore"            "trigger_not_always:relationships tgenabled=O expected=A" "$(cov)"
qq -c "ALTER TABLE relationships ENABLE ALWAYS TRIGGER relationships_emit_event" > /dev/null
expect "H2: restored by ENABLE ALWAYS"                  "-" "$(cov)"

# ---------------------------------------------------------------------------
echo
echo "== H3: the trigger is rebuilt INSERT-only on a mutable table =="
echo "   (every UPDATE stops being logged; existence test cannot tell)"
qq -c "DROP TRIGGER relationships_emit_event ON relationships" \
    -c "CREATE TRIGGER relationships_emit_event AFTER INSERT ON relationships
        FOR EACH ROW EXECUTE FUNCTION emit_event()" > /dev/null
expect "H3: ticket 07's checker sees nothing (HOLE)"    0 "$(v07)"
# Two problems, not one: a hand-written CREATE TRIGGER is ENABLE ORIGIN, so
# rebuilding a trigger by hand silently drops ALWAYS as well. Both are named.
expect "H3: ticket 33's checker sees it"                "trigger_not_always:relationships tgenabled=O expected=A; trigger_wrong_events:relationships tgtype=5 expected=21" "$(cov)"
qq -c "SELECT attach_event_triggers()" > /dev/null
expect "H3: the finalizer alone repairs it"             "-" "$(cov)"

# ---------------------------------------------------------------------------
echo
echo "== H4: the trigger calls something else =="
qq -c "CREATE OR REPLACE FUNCTION not_emit_event() RETURNS trigger LANGUAGE plpgsql AS \$\$ BEGIN RETURN NEW; END \$\$" \
    -c "DROP TRIGGER relationships_emit_event ON relationships" \
    -c "CREATE TRIGGER relationships_emit_event AFTER INSERT OR UPDATE ON relationships
        FOR EACH ROW EXECUTE FUNCTION not_emit_event()" > /dev/null
expect "H4: ticket 07's checker sees nothing (HOLE)"    0 "$(v07)"
expect "H4: ticket 33's checker sees it"                "trigger_not_always:relationships tgenabled=O expected=A; trigger_wrong_function:relationships -> not_emit_event" "$(cov)"
qq -c "SELECT attach_event_triggers()" -c "DROP FUNCTION not_emit_event()" > /dev/null
expect "H4: restored"                                   "-" "$(cov)"

# ---------------------------------------------------------------------------
echo
echo "== H5: the trigger is gone outright =="
echo "   (the one case ticket 07 DOES catch -- shown so the comparison is honest)"
qq -c "DROP TRIGGER relationships_emit_event ON relationships" > /dev/null
expect "H5: ticket 07's checker sees it"                1 "$(v07)"
expect "H5: ticket 33's checker sees it"                "config_row_without_trigger:relationships" "$(cov)"

# ---------------------------------------------------------------------------
echo
echo "== H6: the finalizer removes the ordering constraint =="
echo "   (H5 left the trigger dropped. A migration is now applied that does NOT"
echo "    call attach_event_triggers(); the runner calls it at the end.)"
TMPD="$(mktemp -d)"; cp "$HERE"/migrations/*.sql "$TMPD/"
cat > "$TMPD/20991231T235901Z__a_migration_that_does_not_reattach.sql" <<'SQL'
-- Adds a table AND classifies it, but deliberately never calls
-- attach_event_triggers(). Under ticket 32's apply.sh this would have left both
-- this table and the trigger H5 dropped without any emitter.
CREATE TABLE agent_notes (
    id         uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id uuid NOT NULL REFERENCES programs(id) ON DELETE RESTRICT,
    body       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO event_types (id, family, subject_table, description)
     VALUES ('agent_note.created', 'row', 'agent_notes', 'a note the agent wrote');
INSERT INTO event_table_config (table_name, created_type, updated_type)
     VALUES ('agent_notes', 'agent_note.created', NULL);
SQL
out="$(MIGRATIONS_DIR="$TMPD" CT="$CT" DB="$HDB" "$HERE/migrate.sh" up 2>&1)"; rc=$?
expect "H6: run succeeds"                               0 "$rc"
expect "H6: coverage clean -- both triggers attached"   "-" "$(cov)"
expect "H6: the new table got its trigger"              1 \
       "$(q -c "SELECT count(*) FROM pg_trigger WHERE tgname='agent_notes_emit_event'")"
expect "H6: the H5 trigger came back too"               1 \
       "$(q -c "SELECT count(*) FROM pg_trigger WHERE tgname='relationships_emit_event'")"
rm -rf "$TMPD"
# back to the shipped corpus, or the checks below would be measuring this table
qq -c "DROP TABLE agent_notes" \
   -c "DELETE FROM event_table_config WHERE table_name = 'agent_notes'" \
   -c "DELETE FROM event_types WHERE id = 'agent_note.created'" \
   -c "DELETE FROM rk2_meta.schema_migrations WHERE id LIKE '20991231%'" > /dev/null
expect "H6: cleaned back to the shipped corpus"         "-" "$(cov)"

# ---------------------------------------------------------------------------
echo
echo "== H7: an applied migration is edited afterwards =="
echo "   (the real cost of concurrent authorship: one id, two contents)"
TMPD="$(mktemp -d)"; cp "$HERE"/migrations/*.sql "$TMPD/"
printf '\n-- a hunk someone merged in later\n' >> "$TMPD/013_events.sql"
out="$(MIGRATIONS_DIR="$TMPD" CT="$CT" DB="$HDB" "$HERE/migrate.sh" up 2>&1)"; rc=$?
expect "H7: refused"                                    1 "$rc"
expect "H7: names the drifted migration"                1 "$(named '013_events changed after it was applied' "$out")"
rm -rf "$TMPD"

# ---------------------------------------------------------------------------
echo
echo "== H8: a migration arrives that sorts before one already applied =="
echo "   (two sessions authoring in parallel, merged in the wrong order)"
TMPD="$(mktemp -d)"; cp "$HERE"/migrations/*.sql "$TMPD/"
cat > "$TMPD/20260101T000000Z__from_a_parallel_branch.sql" <<'SQL'
SELECT 1;
SQL
out="$(MIGRATIONS_DIR="$TMPD" CT="$CT" DB="$HDB" "$HERE/migrate.sh" up 2>&1)"; rc=$?
expect "H8: refused"                                    1 "$rc"
expect "H8: names both ids"                             1 "$(named 'sorts before the applied' "$out")"
rm -rf "$TMPD"

# ---------------------------------------------------------------------------
echo
echo "== H9: the next session reaches for a number =="
echo "   (017 is past the freeze; 016 is not, but it is taken -- and two files"
echo "    claiming one number have two ids, so the identity test cannot see it)"
TMPD="$(mktemp -d)"; cp "$HERE"/migrations/*.sql "$TMPD/"
echo "SELECT 1;" > "$TMPD/017_more_scheduler.sql"
out="$(MIGRATIONS_DIR="$TMPD" CT="$CT" DB="$HDB" "$HERE/migrate.sh" lint 2>&1)"; rc=$?
expect "H9: lint refuses 017 (past the freeze)"         1 "$rc"
expect "H9: prints the git mv that fixes it"            1 \
       "$(named 'git mv migrations/017_more_scheduler.sql' "$out")"
rm -f "$TMPD/017_more_scheduler.sql"
echo "SELECT 1;" > "$TMPD/016_more_scheduler.sql"
out="$(MIGRATIONS_DIR="$TMPD" CT="$CT" DB="$HDB" "$HERE/migrate.sh" lint 2>&1)"; rc=$?
expect "H9: lint refuses a second 016"                  1 "$rc"
expect "H9: names both files claiming 016"              1 \
       "$(named 'two files claim legacy number 016: 016_more_scheduler.sql 016_ticket07_fixes.sql' "$out")"
rm -rf "$TMPD"

# ---------------------------------------------------------------------------
echo
echo "== H10: applying twice =="
out="$(CT="$CT" DB="$HDB" "$HERE/migrate.sh" up 2>&1)"; rc=$?
expect "H10: second run is a no-op, not an error"       0 "$rc"
expect "H10: 0 applied"                                 1 "$(named 'migrate: 0 applied' "$out")"

# ---------------------------------------------------------------------------
echo
echo "== H11: maintenance_work_mem is asserted, not assumed =="
qq -c "ALTER DATABASE $HDB SET maintenance_work_mem = '64MB'" > /dev/null
expect "H11: verify refuses the default 64MB"           1 "$(verify_exit)"
qq -c "ALTER DATABASE $HDB SET maintenance_work_mem = '256MB'" > /dev/null
# a session-level SET must NOT satisfy the assertion: the value has to come from
# the settings migration, not from whoever happened to connect
expect "H11: restored"                                  0 "$(verify_exit)"
expect "H11: a session SET reports source=session"      "session" \
       "$(q -q -c "SET maintenance_work_mem='512MB'" -c "SELECT source FROM pg_settings WHERE name='maintenance_work_mem'")"

# ---------------------------------------------------------------------------
echo
echo "== H12: hnsw headroom is measured against the actual row count =="
expect "H12: capacity at 256MB / 1536 dims"             38937 \
       "$(q -c "SELECT DISTINCT capacity_rows FROM hnsw_headroom")"
qq -c "ALTER DATABASE $HDB SET maintenance_work_mem = '4MB'" > /dev/null
expect "H12: capacity at 4MB"                           608 \
       "$(q -c "SELECT DISTINCT capacity_rows FROM hnsw_headroom")"
qq -c "ALTER DATABASE $HDB SET maintenance_work_mem = '256MB'" > /dev/null

# ---------------------------------------------------------------------------
echo
echo "== H13: session_replication_role=replica is what turns the log off =="
echo "   (one SET and every emit trigger stops firing -- so it is asserted,"
echo "    not shipped, and the assertion has to see the session value)"
expect "H13: a session can turn the triggers off"       "replica" \
       "$(q -q -c "SET session_replication_role='replica'" -c "SELECT current_setting('session_replication_role')")"
expect "H13: check_server_baseline sees the session"    "f" \
       "$(q -q -c "SET session_replication_role='replica'" \
                -c "SELECT ok FROM check_server_baseline() WHERE check_name='session_replication_role'")"
expect "H13: and passes in a normal session"            "t" \
       "$(q -c "SELECT ok FROM check_server_baseline() WHERE check_name='session_replication_role'")"

echo
printf '%d passed, %d failed\n' "$pass" "$fail"
exit $(( fail > 0 ))
