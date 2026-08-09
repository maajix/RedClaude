#!/usr/bin/env bash
# PROTOTYPE: Playwright through the scope proxy. One command.
set -u
cd "$(dirname "$0")"

rm -rf out
mkdir -p out

python3 fixture_app.py 18099 >out/fixture.log 2>&1 &
FIXTURE=$!

mitmdump -q -s addon.py \
    --mode regular@127.0.0.1:18080 \
    --mode regular@127.0.0.1:18081 \
    --set connection_strategy=lazy \
    --set confdir=out/ca \
    --set termlog_verbosity=info \
    >out/mitm.log 2>&1 &
MITM=$!

cleanup() { kill "$FIXTURE" "$MITM" 2>/dev/null; wait 2>/dev/null; }
trap cleanup EXIT

for _ in $(seq 1 40); do
    curl -s -o /dev/null --max-time 1 -x http://127.0.0.1:18080 \
        http://127.0.0.1:18099/ && break
    sleep 0.25
done

# The identities have to exist before a browser can borrow them.
python3 - <<'PY'
import re, urllib.parse, urllib.request
PROV = "http://127.0.0.1:18081"
FIX = "http://127.0.0.1:18099"
for identity, user, password in (("userA", "alice", "alice-pw-9f3c"),
                                 ("userB", "bob", "bob-pw-27ae")):
    client = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROV}),
        urllib.request.HTTPCookieProcessor())
    req = urllib.request.Request(f"{FIX}/login")
    req.add_header("X-RedKraken-Identity", identity)
    body = client.open(req, timeout=15).read().decode()
    token = re.search(r'name="csrf_token" value="([^"]+)"', body).group(1)
    data = urllib.parse.urlencode(
        {"user": user, "password": password, "csrf_token": token}).encode()
    req = urllib.request.Request(f"{FIX}/login", data=data, method="POST")
    req.add_header("X-RedKraken-Identity", identity)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    print(f"  provisioned {identity} ->", client.open(req, timeout=15).status)
PY

NODE_PATH=/home/majix/.npm-global/lib/node_modules node browser_probe.js
RC=$?
echo
echo "=== receipts for browser traffic ==="
python3 - <<'PY'
import json, sqlite3
con = sqlite3.connect("out/PROTOTYPE-wipe-me.sqlite")
for row in con.execute(
    "SELECT identity, method, path, status_code, notes FROM receipts "
    "WHERE path LIKE '/xhr%' ORDER BY ts_arrival"
):
    notes = json.loads(row[4] or "{}")
    print(f"  {row[0]} {row[1]} {row[2]} -> {row[3]} "
          f"double_submit={notes.get('double_submit')!r}")
PY
exit $RC
