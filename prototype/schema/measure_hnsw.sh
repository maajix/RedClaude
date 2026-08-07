#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# measure_hnsw.sh -- why maintenance_work_mem is in a migration (ticket 33)
#
# Builds an HNSW index over 20 000 rows of vector(1536) -- the shape of
# hypothesis_embeddings -- at several maintenance_work_mem values and reports,
# for each: whether pgvector printed the spill NOTICE and at how many tuples,
# how long the build took, and how big the index is.
#
# The number in the settings migration is the smallest one that clears 20 000
# rows here. Nothing about it is inherited; re-run this and it re-derives.
#
# Runs on its own database (default rk2_bench). Env: CT, BENCH_DB, ROWS.
# ---------------------------------------------------------------------------
set -euo pipefail

CT=${CT:-rk2-mig-db}
BDB=${BENCH_DB:-rk2_bench}
ROWS=${ROWS:-20000}
SETTINGS=${SETTINGS:-32MB 64MB 128MB 256MB}

q() { docker exec -i "$CT" psql -U postgres -d "$BDB" -v ON_ERROR_STOP=1 "$@"; }

echo "== building a ${ROWS}-row vector(1536) corpus in $BDB =="
docker exec -i "$CT" psql -U postgres -q \
    -c "DROP DATABASE IF EXISTS $BDB" -c "CREATE DATABASE $BDB" > /dev/null
q -q -c "CREATE EXTENSION vector" \
     -c "CREATE TABLE emb (id int PRIMARY KEY, program_id int NOT NULL, v vector(1536))"
# VOLATILE on purpose. An inline uncorrelated `SELECT array_agg(random()) FROM
# generate_series(1,1536)` is folded into an InitPlan and evaluated ONCE, so
# every row gets the same vector, the HNSW graph degenerates and the whole
# measurement is meaningless. The distinct count printed below is the guard.
q -q -c "CREATE FUNCTION rand_vec(dim int) RETURNS vector LANGUAGE sql VOLATILE AS
         \$\$ SELECT array_agg(random())::vector FROM generate_series(1, dim) \$\$"
q -q -c "INSERT INTO emb
         SELECT g, g % 20, rand_vec(1536) FROM generate_series(1,$ROWS) g"
q -At -c "SELECT count(*) || ' rows, ' || count(DISTINCT v) || ' distinct vectors' FROM emb"

printf '\n%-10s %-9s %-14s %-10s %s\n' SETTING SPILLED 'SPILL@TUPLES' BUILD_S INDEX_SIZE
for s in $SETTINGS; do
    out=$(q -q -c "SET maintenance_work_mem = '$s'" \
                 -c "DROP INDEX IF EXISTS emb_hnsw" \
                 -c "\timing on" \
                 -c "CREATE INDEX emb_hnsw ON emb USING hnsw (v vector_cosine_ops)" 2>&1)
    tuples=$(grep -oE 'after [0-9]+ tuples' <<<"$out" | grep -oE '[0-9]+' || true)
    ms=$(grep -oE 'Time: [0-9.]+ ms' <<<"$out" | tail -1 | grep -oE '[0-9.]+' || echo 0)
    size=$(q -At -c "SELECT pg_size_pretty(pg_relation_size('emb_hnsw'))")
    printf '%-10s %-9s %-14s %-10s %s\n' "$s" \
        "$([[ -n $tuples ]] && echo yes || echo no)" "${tuples:--}" \
        "$(awk -v m="$ms" 'BEGIN{printf "%.1f", m/1000}')" "$size"
done

echo
echo "== the spill message, verbatim, at the pgvector default of 64MB =="
q -c "SET maintenance_work_mem = '64MB'" -c "DROP INDEX IF EXISTS emb_hnsw" \
  -c "CREATE INDEX emb_hnsw ON emb USING hnsw (v vector_cosine_ops)" 2>&1 \
  | grep -A1 -i 'no longer fits' || echo "(no spill notice at 64MB -- unexpected)"

echo
echo "== hnsw.iterative_scan: a filtered k-NN query on the index =="
# Ticket 08's stage-2 suppression shape: k nearest WITHIN one program. With the
# pgvector default (off) the index returns ef_search candidates and only then
# applies the filter, so the query silently returns fewer rows than asked for.
q -q -c "SET maintenance_work_mem='256MB'" -c "DROP INDEX IF EXISTS emb_hnsw" \
     -c "CREATE INDEX emb_hnsw ON emb USING hnsw (v vector_cosine_ops)" > /dev/null
for mode in off relaxed_order; do
    # One -c, not three: psql sends a multi-statement -c as a single query and
    # prints only the last result, so the two SETs do not echo "SET" into $n.
    n=$(q -At -c "SET enable_seqscan = off; SET hnsw.iterative_scan = '$mode';
        SELECT count(*) FROM (
            SELECT id FROM emb WHERE program_id = 7
             ORDER BY v <=> (SELECT v FROM emb WHERE id = 1) LIMIT 10) s")
    printf '  hnsw.iterative_scan=%-14s rows returned for LIMIT 10: %s\n' "$mode" "$n"
done

echo
echo "== settings that CANNOT ship as a migration (postmaster context) =="
# This is the boundary of the whole "settings ship as a migration" decision, so
# it is measured rather than asserted from the docs. `|| true` because psql
# exits non-zero on these -- the ERROR *is* the result.
for pv in "wal_level=logical" "shared_buffers=512MB" "max_connections=200"; do
    printf '  ALTER DATABASE ... SET %-16s -> ' "${pv%%=*}"
    { docker exec -i "$CT" psql -U postgres -d "$BDB" -c \
        "ALTER DATABASE $BDB SET ${pv%%=*} = '${pv##*=}'" 2>&1 || true; } | head -1
done
echo "  ^ postmaster-context GUCs: image / command line only, never a migration."

docker exec -i "$CT" psql -U postgres -q -c "DROP DATABASE IF EXISTS $BDB" > /dev/null
echo "done"
