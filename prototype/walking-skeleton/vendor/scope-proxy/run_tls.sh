#!/usr/bin/env bash
# PROTOTYPE: TLS interception matrix against the real target. Proxy only, no
# fixture -- everything here is about a real server's real certificate.
set -u
cd "$(dirname "$0")"

mkdir -p out

mitmdump -q -s addon.py \
    --mode regular@127.0.0.1:18080 \
    --set connection_strategy=lazy \
    --set confdir=out/ca \
    --set termlog_verbosity=info \
    >out/mitm-tls.log 2>&1 &
MITM=$!
trap 'kill "$MITM" 2>/dev/null; wait 2>/dev/null' EXIT

# Wait for the LISTENER, not for the CA file: the CA survives across runs, so
# checking for it only proves a previous run happened.
for _ in $(seq 1 60); do
    if curl -s -o /dev/null --max-time 2 --proxy http://127.0.0.1:18080 \
        --cacert out/ca/mitmproxy-ca-cert.pem https://yekta-it.de/ 2>/dev/null; then
        break
    fi
    sleep 0.25
done

python3 tls_matrix.py
RC=$?
echo
echo "=== mitmdump log (tail) ==="
tail -n 15 out/mitm-tls.log
exit $RC
