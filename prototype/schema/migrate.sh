#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# migrate.sh -- the redKrakenV2 migration runner (ticket 33)
#
#   ./migrate.sh provision  superuser, once: roles, database, extension
#   ./migrate.sh up         apply every pending migration, then finalize + verify
#   ./migrate.sh status     what is applied, what is pending, in order
#   ./migrate.sh verify     run the baseline + coverage assertions, apply nothing
#   ./migrate.sh lint       filename and ordering rules only, no database
#
# Env: CT (container, default rk2-mig), DB (database, default rk2)
#
# TWO CONNECTIONS, and this script holds exactly one of them. Everything below
# runs as rk2_migrate (RK2_MIGRATE_URL). The runtime's rk2_runtime
# (RK2_DATABASE_URL) can reach nothing in here: no DDL, no ownership, no
# session_replication_role. `up` refuses to run on a connection that is not the
# owner, and assert_runtime_connection() refuses one that is, so the two strings
# cannot be swapped without both ends failing.
#
# Why written rather than adopted: sqitch, Flyway, goose, dbmate and alembic
# all do the version table and the checksum. None of them run the two checks
# that make this corpus safe -- attach_event_triggers() as an unconditional
# finalizer, and the event-coverage assertion after every migration -- and all
# of them are an install over a network this environment does not reliably
# have. The whole runner is the 150 lines below plus one SQL function.
# ---------------------------------------------------------------------------
set -euo pipefail

CT=${CT:-rk2-mig-db}
DB=${DB:-rk2}
HERE="$(cd "$(dirname "$0")" && pwd)"
DIR="${MIGRATIONS_DIR:-$HERE/migrations}"
RUNNER_VERSION="1"
LOCK_KEY=8158253941           # arbitrary fixed advisory-lock key

# Frozen baseline: what branch `prototype/schema` itself contains, 001..016
# (ticket 32's 001..015 plus ticket 07's re-resolution, cfdc26e). Every schema
# branch is cut from that commit, so those sixteen numbers are agreed by
# construction and renaming them would only churn. A migration authored on ANY
# other branch takes a timestamp -- that is the whole line, and it is drawn
# where it is because 017/018/019 were authored on three different branches at
# the same time and only avoided collision by hand.
LEGACY_MAX=16

MIGRATE_ROLE=${MIGRATE_ROLE:-rk2_migrate}
OWNER_ROLE=${OWNER_ROLE:-rk2_owner}
RUNTIME_ROLE=${RUNTIME_ROLE:-rk2_runtime}
RESTORE_ROLE=${RESTORE_ROLE:-rk2_restore}
# The two roles the sibling corpus creates for itself: rk2_state (ticket 12,
# the agent-facing read connection) and rk2_human (ticket 28, whose MEMBERship
# is what authorises actor_kind='human'). Both are created here rather than by
# their migration, because CREATE ROLE needs CREATEROLE and rk2_migrate must
# not have it -- MEASURED: 020 fails with `permission denied to create role`
# when it is the migration that tries. Their own `IF NOT EXISTS` guards then
# no-op. Both are LOGIN here: each is a connection string in its own right, and
# a NOLOGIN role reached by SET ROLE from rk2_runtime would be a boundary the
# runtime can step back over at will.
STATE_ROLE=${STATE_ROLE:-rk2_state}
HUMAN_ROLE=${HUMAN_ROLE:-rk2_human}
PROXY_ROLE=${PROXY_ROLE:-rk2_proxy}

psql()  { docker exec -i "$CT" psql -U "$MIGRATE_ROLE" -d "$DB" -v ON_ERROR_STOP=1 "$@"; }
psql1() { psql -At "$@"; }
supersql() { docker exec -i "$CT" psql -U postgres -v ON_ERROR_STOP=1 "$@"; }
die()   { printf 'migrate: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Provisioning -- the three things a non-superuser owner cannot do for itself
# ---------------------------------------------------------------------------
# Roles are cluster-global and CREATE ROLE is superuser-only; CREATE DATABASE is
# superuser-only; and `vector` is not a trusted extension on this image
# (/usr/share/postgresql/18/extension/vector.control has no `trusted` line), so
# CREATE EXTENSION is superuser-only too. Those three are provisioning. Every
# other thing that touches this database is a migration.
#
# This is the answer to "which settings ship in the image": none of them. The
# image is stock pgvector/pgvector:pg18 and this function is the only thing
# between it and an empty database.
cmd_provision() {
    supersql -q <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$OWNER_ROLE') THEN
        EXECUTE format('CREATE ROLE %I NOLOGIN', '$OWNER_ROLE');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$MIGRATE_ROLE') THEN
        EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER IN ROLE %I', '$MIGRATE_ROLE', '$OWNER_ROLE');
    END IF;
    -- 016 creates rk2_runtime NOLOGIN if it is missing; provisioning gets there
    -- first so the role is a login role with the right attributes from the
    -- start. ALTER is unconditional: it also repairs a database whose runtime
    -- role came from 016.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$RUNTIME_ROLE') THEN
        EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER', '$RUNTIME_ROLE');
    END IF;
    EXECUTE format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS', '$RUNTIME_ROLE');
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$RESTORE_ROLE') THEN
        EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER IN ROLE %I', '$RESTORE_ROLE', '$OWNER_ROLE');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$STATE_ROLE') THEN
        EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER', '$STATE_ROLE');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$HUMAN_ROLE') THEN
        EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER', '$HUMAN_ROLE');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$PROXY_ROLE') THEN
        EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER', '$PROXY_ROLE');
    END IF;
    EXECUTE format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS', '$STATE_ROLE');
    EXECUTE format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS', '$HUMAN_ROLE');
    EXECUTE format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS', '$PROXY_ROLE');
END \$\$;

-- The one grant that lets enforcement be turned off, on the one role that never
-- runs anything. GRANT ... ON PARAMETER is PG15+; it is what makes
-- "run the restore as a role allowed to turn the triggers off" a real sentence
-- and not "become superuser".
GRANT SET ON PARAMETER session_replication_role TO $RESTORE_ROLE;
REVOKE SET ON PARAMETER session_replication_role FROM $MIGRATE_ROLE, $RUNTIME_ROLE, $STATE_ROLE, $HUMAN_ROLE, $PROXY_ROLE;

-- Ticket 28's words, kept where the role is now made. COMMENT ON ROLE needs
-- CREATEROLE + ADMIN, so it is superuser work like the CREATE itself.
COMMENT ON ROLE $HUMAN_ROLE IS
    'the operator console. Not granted to rk2_runtime or rk2_state: those are the connections a model can reach through, directly or through a handler.';
COMMENT ON ROLE $STATE_ROLE IS
    'the agent-facing read connection (ticket 12). SELECT on an enumerated surface, no write privilege anywhere.';
COMMENT ON ROLE $RUNTIME_ROLE IS
    'RK2_DATABASE_URL. DML plus EXECUTE, no DDL, no ownership, no TRUNCATE, no session_replication_role.';
COMMENT ON ROLE $PROXY_ROLE IS
    'The egress proxy. EXECUTE on capability receipt writers, no direct receipt DML.';
COMMENT ON ROLE $MIGRATE_ROLE IS
    'RK2_MIGRATE_URL. Held by ./migrate.sh and nothing else.';
SQL
    if [[ -z "$(supersql -At -c "SELECT 1 FROM pg_database WHERE datname='$DB'")" ]]; then
        supersql -q -c "CREATE DATABASE $DB OWNER $OWNER_ROLE"
    fi
    supersql -q -d "$DB" -c "CREATE EXTENSION IF NOT EXISTS vector"
    supersql -q -d "$DB" -c "ALTER SCHEMA public OWNER TO $OWNER_ROLE"
    printf 'migrate: provisioned %s (owner %s)\n' "$DB" "$OWNER_ROLE"
}

# `up` on the wrong connection string is the failure this refuses. rk2_runtime
# would get a permission error eventually; rk2_migrate-that-is-really-superuser
# would silently succeed and leave every object owned by the wrong role.
assert_owner_connection() {
    local u owner
    u="$(psql1 -c 'SELECT current_user')"
    owner="$(psql1 -c "SELECT pg_has_role(current_user, '$OWNER_ROLE', 'USAGE')")"
    [[ $owner == t ]] || die "connected as $u, which is not a member of $OWNER_ROLE -- this is not RK2_MIGRATE_URL"
    [[ "$(psql1 -c "SELECT rolsuper FROM pg_roles WHERE rolname = current_user")" == f ]] \
        || die "connected as superuser $u; migrations run as $MIGRATE_ROLE so ownership is not an accident"
}

# ---------------------------------------------------------------------------
# The ordering rule
# ---------------------------------------------------------------------------
# Identity is the filename minus .sql, and order is that identity ascending in
# C collation. Two forms are legal:
#
#   NNN_slug.sql                   the frozen ticket-32 baseline, NNN <= 015
#   YYYYMMDDTHHMMSSZ__slug.sql     everything after it
#
# The timestamp form exists because sessions author concurrently. Two agents
# both reaching for "the next number" produce the same path and a merge
# conflict at best, two different files claiming one identity at worst -- which
# is what ticket 06 (011), ticket 08 (011) and ticket 07 (012) already did once.
# A UTC timestamp is collision-free without anyone having to look at what anyone
# else picked, and '0' < '2' in C collation, so every legacy file sorts before
# every timestamped one for as long as years have four digits.
#
# The rule is enforced here, not documented: a numeric-prefixed file above
# LEGACY_MAX is refused with the git mv that fixes it.
lint() {
    local bad=0 f base
    for f in "$DIR"/*.sql; do
        base="$(basename "$f")"
        if [[ $base =~ ^([0-9]{3})_[a-z0-9_]+\.sql$ ]]; then
            if (( 10#${BASH_REMATCH[1]} > LEGACY_MAX )); then
                printf 'migrate: %s uses the frozen numeric form above %03d.\n' "$base" "$LEGACY_MAX" >&2
                printf '         Migration numbers are not assignable any more -- two sessions\n' >&2
                printf '         authoring at once cannot both take the next one. Rename:\n' >&2
                printf '           git mv migrations/%s migrations/%s__%s\n' \
                       "$base" "$(date -u +%Y%m%dT%H%M%SZ)" "${base#*_}" >&2
                bad=1
            fi
        elif [[ ! $base =~ ^[0-9]{8}T[0-9]{6}Z__[a-z0-9_]+\.sql$ ]]; then
            printf 'migrate: %s matches neither NNN_slug.sql nor YYYYMMDDTHHMMSSZ__slug.sql\n' "$base" >&2
            printf '         New migrations come from ./new_migration.sh <slug>\n' >&2
            bad=1
        fi
    done
    # A duplicate identity is impossible on one filesystem but not across a
    # merge, so say so rather than assume.
    local dupes
    dupes=$(for f in "$DIR"/*.sql; do basename "$f" .sql; done | sort | uniq -d)
    [[ -n $dupes ]] && { printf 'migrate: duplicate migration id(s): %s\n' "$dupes" >&2; bad=1; }

    # Two files may claim one legacy NUMBER without claiming one identity, which
    # is the exact collision ticket 06 and ticket 08 both produced at 011 and is
    # invisible to the identity test above: the ids differ, so the runner applies
    # both, in an order nobody chose. The number, not the filename, is what a
    # second author reaches for.
    local dupnum
    # `if`, not `[[ ]] &&`: under set -e with pipefail a loop whose last
    # iteration ends in a false test makes the whole pipeline status 1 and kills
    # the runner. Found by this line doing exactly that.
    dupnum=$(for f in "$DIR"/*.sql; do
                 base="$(basename "$f")"
                 if [[ $base =~ ^([0-9]{3})_ ]]; then printf '%s\n' "${BASH_REMATCH[1]}"; fi
             done | sort | uniq -d)
    if [[ -n $dupnum ]]; then
        local n
        for n in $dupnum; do
            printf 'migrate: two files claim legacy number %s: %s\n' "$n" \
                   "$(cd "$DIR" && echo "$n"_*.sql | tr '\n' ' ')" >&2
        done
        printf '         The numeric form is frozen at %03d and numbers are not\n' "$LEGACY_MAX" >&2
        printf '         assignable. New migrations come from ./new_migration.sh <slug>\n' >&2
        bad=1
    fi

    # ---- two content rules, both found by composing the ten sibling branches --
    #
    # (1) NO TRANSACTION CONTROL. apply_one() wraps the file and its
    #     rk2_meta.schema_migrations row in ONE transaction, which is the whole
    #     reason there is no repair state to design. A `COMMIT;` inside the file
    #     commits that transaction early and leaves the bookkeeping row in a
    #     second one -- so a failure between them applies a migration the
    #     database does not remember. MEASURED: the ticket-15 and ticket-24
    #     migrations both ship BEGIN;/COMMIT;, and psql reports only
    #     `WARNING: there is already a transaction in progress`.
    #
    # (2) NO ROLE DDL. Roles are cluster-global; CREATE ROLE needs CREATEROLE,
    #     and granting rk2_migrate CREATEROLE would let a migration mint a role
    #     and grant it -- including rk2_human, membership of which is the only
    #     thing authorising actor_kind='human'. MEASURED: ticket 12's migration
    #     fails with `permission denied to create role` and ticket 28's with
    #     `permission denied ... must have the CREATEROLE attribute` on
    #     COMMENT ON ROLE. Role creation is provisioning; see cmd_provision.
    #
    # Both are exempted for the frozen NNN_ set, which is agreed by construction
    # and whose one guarded CREATE ROLE is dead code once provisioning has run.
    for f in "$DIR"/*.sql; do
        base="$(basename "$f")"
        [[ $base =~ ^[0-9]{3}_ ]] && continue
        if grep -qiE '^[[:space:]]*(BEGIN|COMMIT|ROLLBACK|START TRANSACTION)[[:space:]]*;' "$f"; then
            printf 'migrate: %s contains transaction control.\n' "$base" >&2
            printf '         The runner already wraps every migration in one transaction with\n' >&2
            printf '         its rk2_meta.schema_migrations row. Delete the BEGIN/COMMIT.\n' >&2
            bad=1
        fi
        # anchored, so the same words inside a `--` comment do not trip it
        if grep -qiE '^[[:space:]]*(CREATE|ALTER|DROP|COMMENT ON)[[:space:]]+ROLE[[:space:]]' "$f"; then
            printf 'migrate: %s contains role DDL.\n' "$base" >&2
            printf '         Roles are provisioning, not migration: rk2_migrate has no\n' >&2
            printf '         CREATEROLE and must not get it. Add the role to cmd_provision\n' >&2
            printf '         in ./migrate.sh instead.\n' >&2
            bad=1
        fi
    done

    (( bad )) && die "filename rules failed"
    return 0
}

ids()      { for f in "$DIR"/*.sql; do basename "$f" .sql; done | LC_ALL=C sort; }
checksum() { sha256sum "$DIR/$1.sql" | cut -d' ' -f1; }

# ---------------------------------------------------------------------------
# The version table
# ---------------------------------------------------------------------------
# Created by the runner, not by a migration, because it has to exist before the
# first one. Not idempotent-by-luck: CREATE TABLE IF NOT EXISTS is the only
# statement in the whole corpus allowed to be.
#
# applied_seq is the order the runner actually applied them; id is the order the
# filenames declare. They are separate columns because they can disagree -- a
# migration authored on another branch can arrive after one that sorts later --
# and check_server_baseline() asserts they do not.
#
# MEASURED, and it changed the design: the version table does NOT live in
# `public`. Put there, it is the first thing 017's check_program_isolation()
# trips over -- `table_not_program_scoped schema_migrations` -- because every
# corpus-wide invariant in this schema enumerates public and the runner's own
# bookkeeping is not application state. Three separate registries would each
# need an exception row for it (program_global_tables, event_table_exempt, the
# RLS sweep). One schema boundary costs nothing and removes all three.
bootstrap() {
    psql -q <<'SQL'
SET ROLE rk2_owner;
CREATE SCHEMA IF NOT EXISTS rk2_meta;
CREATE TABLE IF NOT EXISTS rk2_meta.schema_migrations (
    id             text PRIMARY KEY,
    checksum       text        NOT NULL,
    applied_seq    bigint      NOT NULL GENERATED ALWAYS AS IDENTITY,
    applied_at     timestamptz NOT NULL DEFAULT now(),
    applied_by     text        NOT NULL DEFAULT current_user,
    execution_ms   integer     NOT NULL,
    runner_version text        NOT NULL
);
SQL
}

is_applied() { [[ -n "$(psql1 -c "SELECT 1 FROM rk2_meta.schema_migrations WHERE id = '$1'")" ]]; }

# Two refusals that matter more than the apply itself.
#
#   drift  -- an already-applied migration whose bytes changed. This is THE
#             failure of concurrent authorship: not two files with one name
#             (git shows you that) but one name with two contents, merged
#             quietly because the hunks did not overlap.
#   order  -- a pending migration that sorts before something already applied.
#             Nothing here is live yet, so the answer is "drop the database and
#             run from empty", not "apply it anyway and hope".
precheck() {
    local id f_ck db_ck max_applied="" out=0
    while read -r id db_ck; do
        [[ -z $id ]] && continue
        if [[ ! -f "$DIR/$id.sql" ]]; then
            printf 'migrate: %s is applied but its file is gone\n' "$id" >&2; out=1; continue
        fi
        f_ck="$(checksum "$id")"
        if [[ $f_ck != "$db_ck" ]]; then
            printf 'migrate: %s changed after it was applied\n' "$id" >&2
            printf '         db  %s\n         file %s\n' "$db_ck" "$f_ck" >&2
            out=1
        fi
    done < <(psql1 -F' ' -c "SELECT id, checksum FROM rk2_meta.schema_migrations ORDER BY id")

    max_applied="$(psql1 -c "SELECT coalesce(max(id),'') FROM rk2_meta.schema_migrations")"
    if [[ -n $max_applied ]]; then
        for id in $(ids); do
            if is_applied "$id"; then continue; fi
            if [[ $(printf '%s\n%s\n' "$id" "$max_applied" | LC_ALL=C sort | head -1) == "$id" ]]; then
                printf 'migrate: %s is pending but sorts before the applied %s\n' "$id" "$max_applied" >&2
                printf '         Out-of-order arrival, most likely a migration merged from a\n' >&2
                printf '         branch authored in parallel. Recreate the database and run\n' >&2
                printf '         ./migrate.sh up from empty.\n' >&2
                out=1
            fi
        done
    fi
    (( out )) && die "precheck failed"
    return 0
}

# The migration body and its schema_migrations row go in ONE transaction. That
# is the whole reason this is Postgres-shaped: transactional DDL means "applied"
# and "recorded" cannot come apart, so there is no repair state to design.
apply_one() {
    local id="$1" started ms
    started=$(date +%s%3N)
    {
        printf 'SELECT pg_advisory_xact_lock(%s);\n' "$LOCK_KEY"
        # Every object this migration creates is owned by rk2_owner, whichever
        # login applied it. ALTER DEFAULT PRIVILEGES is keyed to the creating
        # role, so without this line a migration applied by a second admin
        # account would create tables the runtime silently cannot read.
        printf 'SET ROLE %s;\n' "$OWNER_ROLE"
        # A migration that INSERTs into an emitting table hits 016's emit_event,
        # which RAISEs when app.actor_kind is unset. The migration IS a runtime
        # actor -- there is no model in the loop -- so the runner declares it
        # once, transaction-local, instead of every migration remembering. This
        # is what prototype/control-surface/stack.sh had to do by hand for every
        # foreign migration it composed.
        printf "SELECT set_config('app.actor_kind','runtime',true);\n"
        printf "SELECT set_config('app.actor_id','migrate:%s',true);\n" "$id"
        cat "$DIR/$id.sql"
        printf '\nINSERT INTO rk2_meta.schema_migrations (id, checksum, execution_ms, runner_version)
                VALUES (%s, %s, 0, %s);\n' \
               "$(printf "'%s'" "$id")" "$(printf "'%s'" "$(checksum "$id")")" \
               "$(printf "'%s'" "$RUNNER_VERSION")"
    } | psql -q --single-transaction > /dev/null
    ms=$(( $(date +%s%3N) - started ))
    psql -q -c "UPDATE rk2_meta.schema_migrations SET execution_ms = $ms WHERE id = '$id'"
    printf '  %-42s %6s ms\n' "$id" "$ms"
}

# ---------------------------------------------------------------------------
# The finalizer -- what removes the ordering constraint instead of writing it
# down
# ---------------------------------------------------------------------------
# Ticket 32 had to order 06 before 08 before 07 because attach_event_triggers()
# has to run after the last table exists. That constraint is not a property of
# any migration, it is a property of the END of the run, so it belongs to the
# runner. Every migration is now free to add tables in any order; the triggers
# are (re)attached once, afterwards, from event_table_config. A migration may
# still call attach_event_triggers() itself when it needs the triggers live
# before its own INSERTs -- that is redundant, never wrong.
finalize() {
    # pg_dump does not carry ALTER DATABASE ... SET, so a restored database has
    # its settings back at the defaults while schema_migrations still says the
    # settings migration is applied. Re-applying every run is what makes that
    # repairable by `migrate.sh up` instead of by remembering.
    psql -q -c "SET ROLE $OWNER_ROLE; SELECT apply_server_settings()" > /dev/null
    psql -q -c "SET ROLE $OWNER_ROLE; SELECT attach_event_triggers()" > /dev/null
    # 016 swept ENABLE ALWAYS across the triggers that existed when it ran. That
    # sweep is a one-shot; this makes it an end-of-run invariant, so a migration
    # written after 016 gets the property without having to know about it.
    local n
    n="$(psql1 -c "SET ROLE $OWNER_ROLE; SELECT enforce_always_triggers()" | tail -1)"
    [[ ${n:-0} -gt 0 ]] && printf 'migrate: %s trigger(s) upgraded to ENABLE ALWAYS\n' "$n"
    # 020 swept RLS across the program-scoped tables that existed then, and 021
    # through 026 each repeated the loop for their own. Six copies of one
    # invariant; the seventh author is the defect. Here it is once, at the end,
    # where the table set is final. Same for the agent read surface: the
    # registry is the grant, and this re-grants what the registry names.
    n="$(psql1 -c "SET ROLE $OWNER_ROLE; SELECT apply_state_rls()" | tail -1)"
    [[ ${n:-0} -gt 0 ]] && printf 'migrate: %s RLS object(s) created\n' "$n"
    n="$(psql1 -c "SET ROLE $OWNER_ROLE; SELECT apply_state_grants()" | tail -1)"
    [[ ${n:-0} -gt 0 ]] && printf 'migrate: %s table(s) re-granted to %s\n' "$n" "$STATE_ROLE"
    # A restore recreates every foreign key in dump order, which is not creation
    # order, and RI triggers fire in name order. 0 on a database that has only
    # ever been migrated; 9 on a fresh pg_restore of this corpus.
    n="$(psql1 -c "SET ROLE $OWNER_ROLE; SELECT enforce_fk_fire_order()" | tail -1)"
    [[ ${n:-0} -gt 0 ]] && printf 'migrate: %s foreign key(s) rebuilt into purge order\n' "$n"
    return 0
}

verify() {
    local list
    list="$(ids | paste -sd, - | sed "s/[^,]*/'&'/g")"
    # The corpus's own checkers, all of them, from the registry migration 33
    # created. Nine of the twelve had no caller after their own migration
    # committed, which is why four of this ticket's five defects were live.
    psql -q -c "SELECT assert_standing_checks()" > /dev/null
    psql -q -c "SELECT assert_server_baseline(ARRAY[$list]::text[])" > /dev/null
    psql -P pager=off -c \
        "SELECT check_name, CASE WHEN ok THEN 'ok' ELSE 'FAIL' END AS r, detail
           FROM check_server_baseline(ARRAY[$list]::text[])
         UNION ALL SELECT check_name, CASE WHEN ok THEN 'ok' ELSE 'FAIL' END, detail
           FROM check_role_catalogue()
         UNION ALL SELECT 'standing:' || name, CASE WHEN problems = 0 THEN 'ok' ELSE 'FAIL' END,
                          problems || ' problem(s)'
           FROM run_standing_checks()"
}

cmd_up() {
    lint
    assert_owner_connection
    bootstrap
    precheck
    local id n=0
    for id in $(ids); do
        if is_applied "$id"; then continue; fi
        apply_one "$id"; n=$((n+1))
    done
    printf 'migrate: %d applied, finalizing\n' "$n"
    finalize
    verify
}

cmd_status() {
    bootstrap
    printf '%-42s %-8s %s\n' ID STATE CHECKSUM
    local id
    for id in $(ids); do
        if is_applied "$id"; then
            printf '%-42s %-8s %s\n' "$id" applied "$(checksum "$id" | cut -c1-12)"
        else
            printf '%-42s %-8s %s\n' "$id" PENDING "$(checksum "$id" | cut -c1-12)"
        fi
    done
}

case "${1:-up}" in
    provision) cmd_provision ;;
    up)        cmd_up ;;
    status)    cmd_status ;;
    verify)    verify ;;
    lint)      lint; echo "migrate: filename rules ok" ;;
    *)         die "usage: $0 [provision|up|status|verify|lint]" ;;
esac
