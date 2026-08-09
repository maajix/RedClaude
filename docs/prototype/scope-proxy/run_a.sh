#!/usr/bin/env bash
# PROTOTYPE Phase A: everything on loopback. One command, no thinking required.
set -u
cd "$(dirname "$0")"

rm -rf out
mkdir -p out

python3 fixture_app.py 18099 >out/fixture.log 2>&1 &
FIXTURE=$!

# Two listeners, one addon. `connection_strategy=lazy` matters: the default
# `eager` opens the upstream socket during CONNECT, before the request hook,
# so an out-of-scope HTTPS host would be contacted before being blocked.
# `confdir` is per-run on purpose. The CA private key is a universal forging
# key for every client that trusts it, so it is generated fresh, lives beside
# the run's receipts, and dies with `rm -rf out`.
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
    if curl -s -o /dev/null --max-time 1 -x http://127.0.0.1:18080 http://127.0.0.1:18099/ ; then
        break
    fi
    sleep 0.25
done

python3 demo_a.py
RC=$?
echo
echo "=== mitmdump log (tail) ==="
tail -n 25 out/mitm.log
exit $RC
