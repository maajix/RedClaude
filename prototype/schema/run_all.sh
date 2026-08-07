#!/usr/bin/env bash
# Bring up Postgres 18 + pgvector, apply every migration from empty, seed, and
# run the check suite. Prints the group-A result table at the end.
set -euo pipefail

CT=${CT:-rk2-schema}
DB=${DB:-rk2}
IMG=${IMG:-pgvector/pgvector:pg18}
HERE="$(cd "$(dirname "$0")" && pwd)"

if ! docker inspect "$CT" > /dev/null 2>&1; then
    docker run -d --name "$CT" -e POSTGRES_PASSWORD=x "$IMG" > /dev/null
fi
docker start "$CT" > /dev/null 2>&1 || true
until docker exec "$CT" pg_isready -U postgres -q; do sleep 1; done

docker exec -i "$CT" psql -U postgres -q \
    -c "DROP DATABASE IF EXISTS $DB" -c "CREATE DATABASE $DB" > /dev/null

CT="$CT" DB="$DB" bash "$HERE/apply.sh"

psql_f() {
    docker exec -i "$CT" psql -U postgres -d "$DB" -q -v ON_ERROR_STOP=1 \
        --single-transaction < "$1" > /dev/null
}

psql_f "$HERE/tests/seed.sql"
echo "seeded"

# Not --single-transaction: group B's last checks need writes committed in one
# transaction to be visible to an integrity check in the next.
docker exec -i "$CT" psql -U postgres -d "$DB" -q -v ON_ERROR_STOP=1 \
    < <(cat "$HERE/tests/_harness.sql" "$HERE/tests/checks_a.sql" \
            "$HERE/tests/checks_b.sql") > /dev/null
docker exec -i "$CT" psql -U postgres -d "$DB" -P pager=off -c \
    "SELECT id, CASE WHEN pass THEN 'ok' ELSE 'FAIL' END AS r, left(note,80) AS note
       FROM t.results ORDER BY ord"
docker exec -i "$CT" psql -U postgres -d "$DB" -At -c \
    "SELECT count(*) FILTER (WHERE NOT pass) || ' failing of ' || count(*) FROM t.results"

psql_f "$HERE/tests/scheduler.sql"
echo "scheduler fixture and functions loaded; see README for the manual probes"
