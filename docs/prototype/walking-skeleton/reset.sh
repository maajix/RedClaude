#!/usr/bin/env bash
# Cold start, literally: drop the database, re-provision the roles, replay every
# migration from zero, then seed. The cold-start proof is worthless if it runs
# against a database that has already seen a pass, so this is the only way any
# proof in this directory begins.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA="$HERE/../schema"
CT="${CT:-rk2-t31-pg}"
DB="${DB:-rk2}"

docker exec -i "$CT" psql -U postgres -d postgres -q \
    -c "DROP DATABASE IF EXISTS $DB WITH (FORCE);" >/dev/null
( cd "$SCHEMA" && CT="$CT" DB="$DB" ./migrate.sh provision >/dev/null )
( cd "$SCHEMA" && CT="$CT" DB="$DB" ./migrate.sh up 2>&1 | tail -3 )
# DIVERGENCE D-12/33-STATE-NOCONNECT, applied here and nowhere else.
#
# Ticket 12: "`rk2_state` is the connection the agent-facing MCP server holds."
# Ticket 33's roles_and_grants.sql grants CONNECT to rk2_runtime, rk2_migrate
# and rk2_restore, and to nobody else. So on the baseline the agent-facing
# connection cannot be opened at all:
#   FATAL: permission denied for database "rk2" / User does not have CONNECT
#          privilege.
# Ticket 36 measured the same hole (`rk2_state CONNECT on database rk2 | false`,
# 1c5f829 line 35) and closed it only for `rk2_human`. Nothing on any branch
# closes it for `rk2_state`.
#
# This is NOT a fix. It is one line, outside the migrations, so that the eight
# proofs that need an agent-facing read can run at all; the divergence is
# reported and the decision belongs to ticket 33's grant set, not here. P2
# measures the hole before this line takes effect on a fresh database.
docker exec -i "$CT" psql -U rk2_migrate -d "$DB" -q -v ON_ERROR_STOP=1 \
    -c "SET ROLE rk2_owner; GRANT CONNECT ON DATABASE $DB TO rk2_state;" >/dev/null

# DIVERGENCE D-33-SCOPE-UNREADABLE, applied here and nowhere else, same rules.
#
# `program_scope_rules` and `program_scope_versions` both carry a
# `..._rk2_state` RLS policy -- the corpus intends the agent-facing role to read
# the scope document -- but no SELECT privilege is ever granted to `rk2_state`
# on either table, and a missing privilege is checked BEFORE RLS. So the read
# fails with `permission denied for table program_scope_rules` and the policy
# can never fire. This is not one table: 28 of the 60 tables that carry an
# `rk2_state` policy have no grant at all (P2 measures the number).
#
# The agent that cannot read its own scope is the agent that cannot decide
# whether a request is in scope -- and in the first live run of this skeleton
# the model did exactly the right thing and refused to send anything. The two
# tables the walking skeleton needs are granted here so the run can proceed;
# the decision belongs to ticket 33's grant set.
docker exec -i "$CT" psql -U rk2_migrate -d "$DB" -q -v ON_ERROR_STOP=1 \
    -c "SET ROLE rk2_owner;
        GRANT SELECT ON program_scope_rules, program_scope_versions TO rk2_state;" >/dev/null

docker exec -i "$CT" psql -U rk2_runtime -d "$DB" -q -v ON_ERROR_STOP=1 -f - \
    < "$HERE/seed31.sql" >/dev/null
echo "reset: migrated + seeded (with D-12/33 CONNECT workaround)"
