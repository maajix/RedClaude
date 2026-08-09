#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# restore.sh -- the decided restore procedure (ticket 33)
#
#   ./restore.sh <dump-path-inside-container> [target-db]
#
# Ticket 07 left this open: "`ENABLE ALWAYS` breaks `pg_restore
# --disable-triggers`. A restore now either sets `app.actor_kind` and accepts a
# second event per restored row, or runs as a role allowed to turn the triggers
# off. This is a real operational cost and needs a decided answer, not a
# discovered one."
#
# The decided answer is neither of those two, because the premise turns out to
# be narrower than it looked. Measured on this corpus:
#
#   * A FULL restore into an empty database never needs triggers off at all.
#     pg_dump orders the TOC as tables -> data -> constraints -> triggers, so
#     the emit triggers do not exist while the COPY runs. Measured on the full
#     corpus with the canonical fixture loaded: 47 events and 8 entities in, 47
#     events and 8 entities out, no duplication, and all 79 user triggers come
#     back ENABLE ALWAYS (tgenabled = 'A' is dumped, unlike the database-level
#     settings above).
#
#   * `pg_restore --disable-triggers` emits `ALTER TABLE ... DISABLE TRIGGER
#     ALL`, which includes the internal RI triggers and is therefore superuser-
#     only -- measured: `permission denied: "RI_ConstraintTrigger_a_78283" is a
#     system trigger` as rk2_restore. That is true with or without ENABLE
#     ALWAYS; it is not something ENABLE ALWAYS broke.
#
#   * `SET session_replication_role = 'replica'` is NOT a substitute, and that
#     part IS ENABLE ALWAYS' doing: an ALWAYS trigger fires in replica mode by
#     definition. That is the whole point of 016.
#
#   * What DOES work under ownership alone is `ALTER TABLE ... DISABLE TRIGGER
#     USER` -- measured to succeed as rk2_owner. That is rk2_restore's door.
#
# So: DATA-ONLY RESTORE INTO A POPULATED SCHEMA IS NOT A SUPPORTED OPERATION.
# The supported restore is a full restore into a freshly provisioned empty
# database, which needs no trigger manipulation, followed by `migrate.sh up`
# and `migrate.sh verify`. Steps 3 and 4 are not decoration:
#
#   * pg_dump does NOT dump `ALTER DATABASE ... SET` (it lives in
#     pg_db_role_setting, which only pg_dumpall emits), so a restored database
#     silently comes back at maintenance_work_mem = 64MB with
#     hnsw.iterative_scan = off. Measured. `migrate.sh up` re-applies them
#     because apply_server_settings() is an end-of-run invariant, not a
#     one-shot; `migrate.sh verify` fails if it did not.
#
#   * pg_restore recreates every FOREIGN KEY in dump order, which is not the
#     order the migrations created them in, and RI triggers fire in name order.
#     MEASURED: 8 parent/child pairs come back with the NO ACTION key firing
#     before the CASCADE, which means the restored database raises a foreign-key
#     violation instead of purging a program. `migrate.sh up` repairs it --
#     enforce_fk_fire_order() rebuilt 9 constraints in one pass -- and ticket
#     35's check (d) is what makes it visible at all.
#
#   * `CREATE EXTENSION vector` is superuser-only on this image, so skipping
#     provisioning turns one error into sixteen and leaves both embedding
#     tables missing while pg_restore still exits 0. Measured.
#
# Env: CT (container), MIGRATE_ROLE, OWNER_ROLE.
# ---------------------------------------------------------------------------
set -euo pipefail

CT=${CT:-rk2-mig-db}
# `--verify-only <db>` runs step 4 alone, so the entitlement below can be tested
# on a restored database that has since been damaged. It is the same code path,
# not a copy of it.
ONLY=0
if [[ "${1:-}" == "--verify-only" ]]; then ONLY=1; DUMP=""; DB="${2:?usage: $0 --verify-only <db>}"
else DUMP="${1:?usage: $0 <dump-path-inside-container> [target-db] | --verify-only <db>}"
     DB="${2:-rk2_restored}"; fi
HERE="$(cd "$(dirname "$0")" && pwd)"
MIGRATE_ROLE=${MIGRATE_ROLE:-rk2_migrate}
OWNER_ROLE=${OWNER_ROLE:-rk2_owner}

if [[ $ONLY -eq 0 ]]; then
echo "== 1/4 provision $DB (superuser: roles, database, extension) =="
docker exec -i "$CT" psql -U postgres -q -c "DROP DATABASE IF EXISTS $DB" > /dev/null
CT="$CT" DB="$DB" "$HERE/migrate.sh" provision

echo "== 2/4 pg_restore as $MIGRATE_ROLE, objects owned by $OWNER_ROLE =="
# --no-owner --role: the dump was taken from a database whose objects are owned
# by rk2_owner, and rk2_migrate is a member, but pg_restore issues ALTER ...
# OWNER TO as the connected role. --role makes it SET ROLE first.
set +e
out="$(docker exec "$CT" pg_restore -U "$MIGRATE_ROLE" -d "$DB" \
        --no-owner --role="$OWNER_ROLE" "$DUMP" 2>&1)"
set -e
errs="$(grep -c '^pg_restore: error' <<<"$out" || true)"
# Exactly one error is expected and ignorable: COMMENT ON EXTENSION vector
# requires ownership of the extension, which belongs to the superuser that
# provisioned it. Anything else is a real failure.
other="$(grep '^pg_restore: error' <<<"$out" | grep -vc 'must be owner of extension' || true)"
printf '   pg_restore reported %s error(s), %s of them unexpected\n' "$errs" "$other"
if [[ ${other:-0} -gt 0 ]]; then
    grep -A1 '^pg_restore: error' <<<"$out" | grep -v 'must be owner of extension' | head -20
    echo "restore: unexpected errors -- refusing" >&2; exit 1
fi

echo "== 3/4 migrate.sh up (0 pending; re-applies settings and triggers) =="
CT="$CT" DB="$DB" "$HERE/migrate.sh" up 2>&1 | grep -E 'applied|upgraded|rebuilt' || true
fi

echo "== 4/4 verify, with the one exception a restore is entitled to =="
# `migrate.sh verify` is strict and stays strict: it fails a restored database.
# The tolerance lives here, in the only place that knows a restore happened.
#
# What it tolerates, and nothing else: check_event_log_integrity()'s part (d),
# `row_last_write_unaccounted`. That check compares a row's `xmin` -- the
# transaction that produced the live tuple -- with the `xact_id` recorded on its
# event. A restore rewrites every tuple in the restore's own transaction while
# the events keep the transaction ids of the writes that really happened, so the
# comparison is false for every restored row by construction. MEASURED: 13
# problems, all of that one kind, on a restore that is otherwise identical.
#
# This is the same class as the xmin = 2 exclusion 016 already carries for
# frozen tuples: the evidence has been destroyed by machinery outside the
# schema, so the row degrades to part (b) -- an event exists for it at all --
# and that is stated rather than silently passed. Parts (a), (b), (c) and (e),
# every other standing check, the server baseline and the role catalogue are
# still required to be clean, and a second kind of problem in (d) fails here.
q() { docker exec -i "$CT" psql -U postgres -d "$DB" -At -v ON_ERROR_STOP=1 "$@"; }
others="$(q -c "SELECT coalesce(string_agg(name || '=' || problems, '; '), '')
                  FROM run_standing_checks()
                 WHERE problems > 0 AND name <> 'event_log_integrity'")"
evkinds="$(q -c "SELECT coalesce(string_agg(DISTINCT problem, ','), '')
                   FROM check_event_log_integrity()")"
baseline="$(q -c "SELECT coalesce(string_agg(check_name, ', '), '')
                    FROM (SELECT check_name, ok FROM check_role_catalogue()) z
                   WHERE NOT ok")"
rc=0
[[ -n "$others"   ]] && { echo "   standing checks failed: $others" >&2; rc=1; }
[[ -n "$baseline" ]] && { echo "   role catalogue failed: $baseline" >&2; rc=1; }
case "$evkinds" in
    ""|"row_last_write_unaccounted")
        [[ -n "$evkinds" ]] && echo "   event log: xmin evidence lost to the restore, rows otherwise accounted for" ;;
    *)  echo "   event log integrity failed beyond the restore's entitlement: $evkinds" >&2; rc=1 ;;
esac
if [[ $rc -eq 0 ]]; then
    echo "   restore verified: $DB"
else
    echo "   VERIFY FAILED -- this is not a restore" >&2
    exit 1
fi
