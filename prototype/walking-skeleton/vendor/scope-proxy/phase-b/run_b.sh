#!/usr/bin/env bash
# PROTOTYPE Phase B: containment as a routing fact. One command.
set -u
cd "$(dirname "$0")"

rm -rf out
mkdir -p out
chmod 777 out   # mitmproxy image runs as its own uid; throwaway dir, throwaway perms

docker compose down -v --remove-orphans >/dev/null 2>&1
docker compose up -d >out/compose.log 2>&1 || { cat out/compose.log; exit 1; }
trap 'docker compose down -v --remove-orphans >/dev/null 2>&1' EXIT

echo "=== waiting for the proxy to bind both lanes ==="
for _ in $(seq 1 80); do
    if [ -f out/ca/mitmproxy-ca-cert.pem ] && \
       curl -s -o /dev/null --max-time 2 --proxy http://172.31.250.10:18081 \
            http://fixture:18099/ 2>/dev/null; then
        break
    fi
    sleep 0.5
done

echo
echo "=== runtime provisions the identities from the HOST ==="
echo "    (over the proxy's egress address, which the agent has no route to)"
python3 provision_b.py
PROV_RC=$?

echo
echo "=== the agent tries to get out ==="
docker compose exec -T agent python3 /probe_b.py
A_RC=$?
docker compose exec -T agent-hardened python3 /probe_b.py
B_RC=$?

echo
echo "=== receipts written by the containerised proxy ==="
python3 - <<'PY'
import sqlite3
from pathlib import Path
db = Path("out/PROTOTYPE-wipe-me.sqlite")
if not db.exists():
    print("  no receipts db"); raise SystemExit
con = sqlite3.connect(db)
for row in con.execute(
    "SELECT decision, lane, identity, method, host, path, status_code, "
    "substr(reason,1,44) FROM receipts ORDER BY ts_arrival"
):
    print("  " + " | ".join("" if c is None else str(c) for c in row))
PY

echo
echo "=== proxy log (tail) ==="
docker compose logs --no-log-prefix proxy 2>/dev/null | tail -n 12

echo
echo "=== summary ==="
echo "  provisioning rc=$PROV_RC  agent rc=$A_RC  agent-hardened rc=$B_RC"
[ "$PROV_RC" -eq 0 ] && [ "$A_RC" -eq 0 ] && [ "$B_RC" -eq 0 ]
