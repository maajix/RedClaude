# PROTOTYPE: the v2 scope proxy

Throwaway code. It exists to answer a question, not to be extended.

**Question** (historical ticket 04, “Prototype the v2 scope proxy”):
can one mitmproxy addon be the single egress path, the rate limiter, the identity
injector and the receipt producer at once — and what does that cost?

The answer is in the ticket. This file says how to run it and what each run
proved. Nothing here is meant to survive into v2 except the findings.

## Run it

Four independent runs, each one command, each self-contained. Every run wipes
`out/` first and deletes its own CA on the next wipe.

```bash
bash run_a.sh          # phase A: proxy behaviour on one host      -> 28/28
bash run_tls.sh        # TLS interception against yekta-it.de      ->   7/7
bash phase-b/run_b.sh  # phase B: containment across 3 networks    -> 10/10 x2
bash run_browser.sh    # Playwright through the proxy              -> 12/12
```

Needs: `mitmdump` on PATH (12.2.3, its own Python 3.13 venv), `python3` (3.14),
Docker Compose (v5.0.2) for phase B, Playwright (1.61.1) plus its chromium for
the browser run. The addon is **stdlib-only** on purpose: it is imported inside
mitmproxy's venv, where third-party packages are not ours to install.

`run_a.sh` and `run_tls.sh` make real requests to **yekta-it.de**, which the
operator owns and has authorised. Rate is pinned at 2 rps / burst 2 /
concurrency 2 in `config.py`.

## What is here

| file | what it is |
| --- | --- |
| `addon.py` | the mitmproxy addon: hooks, lanes, the receipt trail |
| `policy.py` | scope decisions — host, IP, excluded path, redirect target |
| `budget.py` | per-**target** token bucket + concurrency semaphore |
| `identity.py` | the cookie jar, CSRF binding, injection and capture |
| `receipts.py` | SQLite rows + content-addressed artifact blobs |
| `config.py` | hand-written targets and identities (not the real schema) |
| `fixture_app.py` | throwaway target app: login, session rotation, two CSRF styles |
| `demo_a.py` | phase A assertions |
| `tls_matrix.py` | five TLS probes + two curl probes against the real target |
| `phase-b/compose.yaml` | the containment topology under test |
| `phase-b/probe_b.py` | escape attempts from inside the agent container |
| `browser_probe.js` | Playwright: two identities, one browser, no credentials |

`fixture_app.py` exists because the real target has a CAPTCHA on login and a
closed registration, so it cannot supply two driveable authenticated identities.
The fixture supplies the login half; yekta-it.de supplies the real-TLS,
real-server half. Neither alone would have been enough.

## What each run establishes

**Phase A — 28 assertions.** Two identities against one target, in one process,
neither ever holding a cookie. The agent-side jar is empty; a cookie the agent
tries to smuggle is stripped and *recorded as an attempt* rather than dropped
silently. CSRF tokens are substituted into form bodies the agent never sees the
contents of. Excluded path, DNS-rebinding attempt and outbound redirect are all
refused. Six requests to yekta-it.de through the interceptor at 2 rps take 5.34s
— the bucket is real. 42 content-addressed blobs, with request and response
hashed **twice** per direction: `*_agent_sha` (what the agent may cite, no
credentials in it) and `*_wire_sha` (what actually crossed the wire).

**TLS matrix — 7 probes.** Direct vs proxied, against the real target. Issuer
`YR1` direct, `mitmproxy` proxied. TLS version and cipher happened to match; ALPN
did not (`h2` direct, `http/1.1` proxied) — mitmproxy negotiates its client side
independently of its server side. A client that has not been told about the run
CA fails loudly (`CERTIFICATE_VERIFY_FAILED`, curl rc=60), which is the correct
failure.

**Phase B — 10 assertions, run twice.** Three Docker networks: `agent-lane` and
`target-lane` both `internal: true`, plus an `egress` bridge the proxy alone sits
on. Agent and fixture share no network at all. From inside the agent container: no default route at all, no TCP to the
internet, and the target is **not even resolvable** — `internal: true` kills
external DNS too, which I had predicted wrong and the measurement corrected. The
provisioning lane, bound to the proxy's egress IP, is unreachable from the agent
network because Docker isolates bridges from each other. The only name that
resolves is `proxy`. Run twice: once with the compose default resolver, once with
`dns: ["127.0.0.1"]`, same result.

**Browser — 12 assertions.** One chromium, two `browserContext`s, two identity
headers: the browser is logged in as two people at once having logged in as
neither. Zero cookies in the profile, empty `document.cookie`. Double-submit CSRF
is the case that actually breaks — page JS cannot read a cookie the proxy owns —
and it is repaired proxy-side (403 `got: "(empty)"` without the repair, 200 with
it, and the page JS still never learns the token). `localStorage` does not cross
contexts, so a context per identity is enough; a profile or container per
identity is not needed.

## The findings that changed the design

1. **CSRF tokens are session-bound**, so a token captured before login is dead
   the moment login rotates the session. Storing the token is not enough; the
   proxy binds each token to the Cookie header in force when it was captured, and
   treats a mismatch as *no token*.
2. **That forces the proxy to fetch tokens itself**, which makes it a client of
   the target in its own right. Its own fetches therefore run through the same
   scope check, the same target budget and the same receipt trail, on a third
   `proxy-internal` lane. A proxy that quietly makes unmetered requests has broken
   the rule it exists to enforce.
3. **TLS interception costs certificate identity and protocol fidelity.** The
   agent cannot see the target's real certificate or its real ALPN, so no
   TLS-layer or protocol-layer finding made from behind the proxy is citable.
4. **Every runtime needs its own trust store entry** (`SSL_CERT_FILE`,
   `NODE_EXTRA_CA_CERTS`, `--cacert`, chromium's NSS db). This puts the CA in the
   image, not in a flag: `ignoreHTTPSErrors` would work but blinds the agent to
   every real certificate problem on the target.
5. **Containment is a routing fact, not a policy.** It is verified by trying to
   escape and failing, from inside the container, as a test.
6. `connection_strategy=lazy` is **mandatory**. The default opens the upstream
   socket during CONNECT, before the `request` hook — the scope check would run
   after the connection it is supposed to prevent.
7. An HTTPS host refused at CONNECT gets **no 451 body**; there is no tunnel to
   carry one. The refusal is the stronger outcome, but a client sees a transport
   error, not an explanation.

## Known gaps

Deliberate, because the prototype had answered its question by the time they
mattered:

- The proxy's own token fetch (`identity.refresh_csrf`) uses `urllib` and is not
  covered by `server_connect`'s address pin, so it does not get the same
  DNS-rebinding protection as proxied traffic.
- One identity jar in memory plus a JSON file. No lease, no expiry, no
  concurrent-hunt story.
- Scope config is hand-written dicts. The real schema is a different ticket.
- Receipts are SQLite in `out/PROTOTYPE-wipe-me.sqlite`, wiped every run.
