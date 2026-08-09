#!/usr/bin/env bash
# CI entry point: no provider network, Claude SDK, operator credential or live model.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
export CT="${CT:-rk2-startup-offline}"
export DB="${DB:-rk2_startup_offline}"
export RK_T31_CT="$CT"
export RK_T31_DB="$DB"

docker image inspect pgvector/pgvector:pg18 >/dev/null
if ! docker inspect "$CT" >/dev/null 2>&1; then
    docker run --pull=never -d --name "$CT" -e POSTGRES_PASSWORD=x \
        pgvector/pgvector:pg18 >/dev/null
fi
docker start "$CT" >/dev/null
until docker exec "$CT" pg_isready -U postgres -q; do sleep 1; done
trap 'docker stop "$CT" >/dev/null 2>&1 || true' EXIT

(cd "$ROOT/prototype/sdk-auth-probe" && python3 -m unittest -v test_auth_resolution.py)
(cd "$HERE" && python3 -m unittest -v test_startup_launch.py)
(cd "$HERE" && RK_COMPOSED_OFFLINE=1 python3 -m unittest -v test_startup_composed.py)

if command -v gitleaks >/dev/null 2>&1; then
    gitleaks dir --no-banner --redact=100 "$ROOT/prototype/sdk-auth-probe/evidence"
    for path in "$HERE"/*.py "$HERE"/*.sh "$HERE"/*.md \
                "$ROOT/prototype/schema/migrations/20260808T"*.sql \
                "$ROOT/prototype/schema/tests/capability_receipts.sql" \
                "$ROOT/prototype/schema/tests/startup_refusal.sql"; do
        gitleaks dir --no-banner --redact=100 "$path"
    done
fi
