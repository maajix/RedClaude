#!/usr/bin/env bash
# ===========================================================================
# The whole of ticket 33, executed. Nine passes, in this order, because each
# one depends on the state the previous one left:
#
#   1  the corpus applies from empty, in one order, on one server
#   2  running it again is a no-op and still verifies
#   3  the canonical fixture applies on top of the full corpus, and the check
#      suite (groups A, B, C and capability group K) runs against it
#   4  the numbering rule is a check, not a comment: break it, watch it fire
#   5  a migration that raises leaves nothing recorded
#   6  a migration that arrives out of order is refused
#   7  a deliberately wrong server setting fails the startup assertion, and
#      `up` repairs it
#   8  a migration that adds a table without triggers, RLS, grants or a
#      classification fails the run rather than shipping
#   9  a dump/restore round trip verifies, and a damaged one does not
#  10  rebuild from empty, so the tree is left green
#
# One container, stopped at the end. Nothing here touches rk2-schema.
# ===========================================================================
set -uo pipefail

CT=${CT:-rk2-mig-db}
DB=${DB:-rk2}
IMG=${IMG:-pgvector/pgvector:pg18}
HERE="$(cd "$(dirname "$0")" && pwd)"
FAILED=0

say()  { printf '\n=== %s\n' "$*"; }
ok()   { printf '  PASS  %s\n' "$*"; }
bad()  { printf '  FAIL  %s\n' "$*"; FAILED=$((FAILED+1)); }

psqlq() { docker exec -i "$CT" psql -U postgres -d "$DB" -At -c "$1"; }

if ! docker inspect "$CT" > /dev/null 2>&1; then
    docker run -d --name "$CT" -e POSTGRES_PASSWORD=x "$IMG" > /dev/null
fi
docker start "$CT" > /dev/null 2>&1
until docker exec "$CT" pg_isready -U postgres -q; do sleep 1; done

rebuild() {
    docker exec -i "$CT" psql -U postgres -q -c "DROP DATABASE IF EXISTS $DB" > /dev/null 2>&1
    CT="$CT" DB="$DB" "$HERE/migrate.sh" provision > /dev/null 2>&1
    CT="$CT" DB="$DB" "$HERE/migrate.sh" up > "$HERE/.last_up.log" 2>&1
}

# ---- 1 ---------------------------------------------------------------------
say "1  apply the corpus from empty"
if rebuild; then
    n=$(psqlq "SELECT count(*) FROM rk2_meta.schema_migrations")
    tb=$(psqlq "SELECT count(*) FROM managed_tables")
    ck=$(psqlq "SELECT count(*) FROM standing_checks")
    pr=$(psqlq "SELECT coalesce(sum(problems),0) FROM run_standing_checks()")
    ok "$n migrations, $tb managed tables, $ck standing checks, $pr problems"
    [[ $pr -eq 0 ]] || bad "standing checks are not silent"
else
    bad "corpus did not apply"; tail -n 5 "$HERE/.last_up.log"
fi

# ---- 2 ---------------------------------------------------------------------
say "2  running it again is a no-op"
out=$(CT="$CT" DB="$DB" "$HERE/migrate.sh" up 2>&1)
if grep -q "^migrate: 0 applied" <<< "$out"; then ok "0 applied, verify still green"
else bad "second run was not a no-op"; grep -E "applied|ERROR" <<< "$out" | head -n 3; fi

# ---- 3 ---------------------------------------------------------------------
say "3  the fixture and the check suite"
docker exec -i "$CT" psql -U postgres -d "$DB" -q -v ON_ERROR_STOP=1 \
    --single-transaction < "$HERE/tests/seed.sql" > /dev/null 2>&1 \
    && ok "canonical fixture applies on the full corpus (defect 1)" \
    || bad "fixture did not apply"
docker exec -i "$CT" psql -U postgres -d "$DB" -q -v ON_ERROR_STOP=1 \
    < <(cat "$HERE/tests/_harness.sql" "$HERE/tests/checks_a.sql" \
            "$HERE/tests/checks_b.sql" "$HERE/tests/checks_c.sql") > /dev/null 2>&1 \
    || bad "existing check suite did not execute"
docker exec -i "$CT" psql -U postgres -d "$DB" -q -v ON_ERROR_STOP=1 \
    < "$HERE/tests/capability_receipts.sql" > /dev/null 2>&1 \
    || bad "capability receipt checks did not execute"
docker exec -i "$CT" psql -U postgres -d "$DB" -q -v ON_ERROR_STOP=1 \
    < "$HERE/tests/startup_refusal.sql" > /dev/null 2>&1 \
    || bad "startup refusal checks did not execute"
docker exec -i "$CT" psql -U postgres -d "$DB" -P pager=off \
    -c "SELECT id, CASE WHEN pass THEN 'ok' ELSE 'FAIL' END AS r, left(note,60) AS note
          FROM t.results WHERE id LIKE 'M%' OR NOT pass ORDER BY ord"
tot=$(psqlq "SELECT count(*) FROM t.results")
fail=$(psqlq "SELECT count(*) FROM t.results WHERE NOT pass")
[[ "$tot" == "97" ]] || bad "expected 97 checks, got $tot"
[[ "$fail" == "0" ]] && ok "$tot checks, 0 failing" || bad "$fail of $tot failing"

# ---- 4 ---------------------------------------------------------------------
say "4  the numbering rule fires"
cp "$HERE/migrations/20260807T191300Z__ticket33_corpus_fixes.sql" \
   "$HERE/migrations/017_late_legacy_number.sql"
CT="$CT" DB="$DB" "$HERE/migrate.sh" lint > /dev/null 2>&1 \
    && bad "lint accepted a legacy number past the freeze" \
    || ok "lint refuses 017_late_legacy_number.sql (frozen at 016)"
rm -f "$HERE/migrations/017_late_legacy_number.sql"
printf 'SELECT 1;\n' > "$HERE/migrations/nope.sql"
CT="$CT" DB="$DB" "$HERE/migrate.sh" lint > /dev/null 2>&1 \
    && bad "lint accepted a name matching no rule" \
    || ok "lint refuses nope.sql"
rm -f "$HERE/migrations/nope.sql"
printf 'BEGIN;\nSELECT 1;\nCOMMIT;\n' > "$HERE/migrations/20990101T000000Z__txn.sql"
CT="$CT" DB="$DB" "$HERE/migrate.sh" lint > /dev/null 2>&1 \
    && bad "lint accepted transaction control inside a migration" \
    || ok "lint refuses a migration that commits its own transaction"
printf 'CREATE ROLE rk2_sneaky;\n' > "$HERE/migrations/20990101T000000Z__txn.sql"
CT="$CT" DB="$DB" "$HERE/migrate.sh" lint > /dev/null 2>&1 \
    && bad "lint accepted role DDL inside a migration" \
    || ok "lint refuses role DDL (rk2_migrate has no CREATEROLE, by design)"
rm -f "$HERE/migrations/20990101T000000Z__txn.sql"
CT="$CT" DB="$DB" "$HERE/migrate.sh" lint > /dev/null 2>&1 \
    && ok "lint is silent on the corpus" || bad "lint is not silent on the corpus"

# ---- 5 ---------------------------------------------------------------------
say "5  a migration that raises records nothing"
cat > "$HERE/migrations/20990101T000100Z__half_applied.sql" <<'SQL'
CREATE TABLE ticket33_partial (id uuid PRIMARY KEY DEFAULT uuidv7());
DO $$ BEGIN RAISE EXCEPTION 'deliberate failure, after a CREATE TABLE'; END $$;
SQL
CT="$CT" DB="$DB" "$HERE/migrate.sh" up > /dev/null 2>&1
rec=$(psqlq "SELECT count(*) FROM rk2_meta.schema_migrations WHERE id LIKE '20990101T000100Z%'")
tbl=$(psqlq "SELECT count(*) FROM pg_class WHERE relname = 'ticket33_partial'")
[[ "$rec" == "0" && "$tbl" == "0" ]] \
    && ok "neither the table nor the version row survived (apply and record are one transaction)" \
    || bad "partial state survived: row=$rec table=$tbl"
rm -f "$HERE/migrations/20990101T000100Z__half_applied.sql"

# ---- 6 ---------------------------------------------------------------------
say "6  a migration that arrives out of order is refused"
cat > "$HERE/migrations/20260807T190050Z__backdated.sql" <<'SQL'
SELECT 1;
SQL
out=$(CT="$CT" DB="$DB" "$HERE/migrate.sh" up 2>&1)
grep -q "sorts before the applied" <<< "$out" \
    && ok "$(grep -m1 'sorts before the applied' <<< "$out" | sed 's/^migrate: //')" \
    || bad "a backdated migration was accepted"
rm -f "$HERE/migrations/20260807T190050Z__backdated.sql"

# ---- 7 ---------------------------------------------------------------------
say "7  a wrong server setting fails the startup assertion"
docker exec -i "$CT" psql -U postgres -q -c \
    "ALTER DATABASE $DB SET maintenance_work_mem = '16MB'" > /dev/null
out=$(CT="$CT" DB="$DB" "$HERE/migrate.sh" verify 2>&1)
grep -q "maintenance_work_mem" <<< "$out" \
    && ok "verify names maintenance_work_mem = 16MB" \
    || bad "verify accepted a wrong setting"
CT="$CT" DB="$DB" "$HERE/migrate.sh" up > /dev/null 2>&1 \
    && ok "up repaired it -- the settings are a finalizer, not a one-shot" \
    || bad "up did not repair the setting"

# ---- 8 ---------------------------------------------------------------------
say "8  a migration that adds a table wrongly fails the run"
cp "$HERE/tests/999_drift_probe.sql" "$HERE/migrations/20990101T000200Z__drift_probe.sql"
out=$(CT="$CT" DB="$DB" "$HERE/migrate.sh" up 2>&1)
for want in "standing check event_coverage FAILED" "standing check state_grants FAILED" \
            "standing check program_isolation FAILED" "standing check purge_reachability FAILED"; do
    grep -q "$want" <<< "$out" && ok "$want" || bad "not reported: $want"
done
grep -q "standing check rls_coverage FAILED" <<< "$out" \
    && bad "rls_coverage should have been healed by the finalizer, not reported" \
    || ok "rls_coverage was healed by the finalizer before verify ran"
rm -f "$HERE/migrations/20990101T000200Z__drift_probe.sql"

# ---- 9 ---------------------------------------------------------------------
say "9  dump and restore, and what a restore is entitled to"
# Pass 8 deliberately left an applied migration whose file is gone and two
# drift-probe tables behind, so the round trip starts from a rebuild and the
# fixture, not from that.
rebuild
docker exec -i "$CT" psql -U postgres -d "$DB" -q -v ON_ERROR_STOP=1 \
    --single-transaction < "$HERE/tests/seed.sql" > /dev/null 2>&1
docker exec "$CT" pg_dump -U postgres -d "$DB" -Fc -f /tmp/rk2_run_all.dump 2>/dev/null
out=$(CT="$CT" "$HERE/restore.sh" /tmp/rk2_run_all.dump rk2_roundtrip 2>&1)
grep -q "restore verified" <<< "$out" \
    && ok "full restore into a fresh database verifies" \
    || { bad "restore did not verify"; grep -E 'FAIL|error|failed' <<< "$out" | head -n 3; }
grep -q "foreign key(s) rebuilt into purge order" <<< "$out" \
    && ok "$(grep -m1 'rebuilt into purge order' <<< "$out" | sed 's/^migrate: //')" \
    || bad "the restore did not need the FK order repair -- check it is still reached"
src=$(psqlq "SELECT count(*) FROM events")
dst=$(docker exec -i "$CT" psql -U postgres -d rk2_roundtrip -At -c "SELECT count(*) FROM events")
[[ "$src" == "$dst" ]] && ok "$src events in, $dst out -- ENABLE ALWAYS did not double-log the restore" \
                       || bad "event count changed across the restore: $src -> $dst"
# and the entitlement is one named check, not a blanket pass
docker exec -i "$CT" psql -U postgres -d rk2_roundtrip -q -c \
    "SET session_replication_role='replica'; DELETE FROM entities WHERE label='EP2'" > /dev/null 2>&1
CT="$CT" "$HERE/restore.sh" --verify-only rk2_roundtrip > /dev/null 2>&1 \
    && bad "a damaged restore still verified" \
    || ok "delete one row behind the triggers and the same verify refuses it"
docker exec -i "$CT" psql -U postgres -q -c "DROP DATABASE IF EXISTS rk2_roundtrip" > /dev/null 2>&1

# ---- 10 --------------------------------------------------------------------
say "10  rebuild from empty"
if rebuild; then
    n=$(psqlq "SELECT count(*) FROM rk2_meta.schema_migrations")
    pr=$(psqlq "SELECT coalesce(sum(problems),0) FROM run_standing_checks()")
    ck=$(psqlq "SELECT count(*) FROM standing_checks")
    [[ "$pr" == "0" ]] && ok "$n migrations, $ck standing checks, 0 problems" \
                       || bad "standing checks not silent after rebuild"
else
    bad "rebuild failed"; tail -n 5 "$HERE/.last_up.log"
fi
rm -f "$HERE/.last_up.log"

printf '\n%s\n' "-------------------------------------------"
[[ $FAILED -eq 0 ]] && printf 'run_all: everything passed\n' \
                    || printf 'run_all: %d FAILURES\n' "$FAILED"
docker stop "$CT" > /dev/null 2>&1
exit $FAILED
