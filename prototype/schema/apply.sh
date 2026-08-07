#!/usr/bin/env bash
# Apply every migration in order to the container database, each in its own
# transaction, stopping on the first error.
set -euo pipefail

CT=${CT:-rk2-schema}
DB=${DB:-rk2}
DIR="$(cd "$(dirname "$0")" && pwd)/migrations"

for f in "$DIR"/*.sql; do
    printf '== %s\n' "$(basename "$f")"
    docker exec -i "$CT" psql -U postgres -d "$DB" \
        -v ON_ERROR_STOP=1 --single-transaction -q < "$f"
done
echo "all migrations applied"
