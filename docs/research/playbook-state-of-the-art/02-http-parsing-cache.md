# 02 - HTTP integrity, parsing and cache

Scope of this review: `http-desync`, `request-parsing`, `request-integrity`,
`web-cache`, `file-resolution`, `exceptional-conditions`, `cookies`, with
`deployment` read as the adjacent holder of `authorization.edge_rule`.

Research window: material from 2023-2026 is preferred and dated per entry; a few
older techniques are included and explicitly marked as older-but-still-landing.
Everything below is written for an authorized engagement: the framing throughout
is "what can this harness observe and prove", not "how to cause impact".

Two pages could not be fetched and nothing is asserted from them: the USENIX
pages for the Mirheidari web-cache-deception measurement papers returned HTTP 403
to both the presentation URL and the PDF URL, and `blog.malicious.group` and
`cyberark.com` returned cross-host redirects that were not followed. Where a URL
below is listed but was not fetched, it says so.

## What we already cover well

**The evidence discipline is ahead of the public methodology.** Every Playbook in
this cluster states its refutation condition before it sends anything, sends a
control that distinguishes "the deployment refuses this shape everywhere" from
"this route is different", and names the neighbouring property class. Published
bug-bounty methodology almost never does this, and the cost shows: the SquidSec
write-up of November 2025 estimates that 90-95% of recent smuggling reports are
false positives that never distinguished pipelining from desync. Our control
arms are the thing that prevents that failure mode.

**`file-resolution` has the strongest control set of any traversal methodology I
found published.** Two out-of-directory arms differenced against *each other*
(not against a refusal), plus a normalising arm that resolves back inside, plus a
nonexistent-leaf probe to rule out "the error page quoted the string". The public
canon (`lfi.md`-style cheat sheets, PayloadsAllTheThings) tests none of these and
routinely reports "`..` was accepted" as a finding. Step 4's explicit statement
that `..` in the input is not a finding is correct and rare.

**`exceptional-conditions` separates a type violation from a rule violation.**
Sending a value the route's own rule rejects as a *control* and only then sending
values outside the type is the right shape, and the enumerated disclosure list in
step 5 (source path, exception class, statement fragment, version string,
internal address) is a usable evidence contract rather than "look for a stack
trace".

**`web-cache` step 2's invented cache key is the correct safety primitive, and it
is the same primitive the vendor guidance uses.** PortSwigger's own Web Security
Academy tells testers to "add a cache buster (such as a unique parameter)" so
that a poisoned entry is never served to a real user, and Doyhenard's Black Hat
2024 paper repeats it. Our Playbook arrived at the same construction
independently and states the blast-radius argument better than the sources do.

**`request-integrity`'s near-miss origin arm is the discriminator real reports
need.** Sending the trusted origin with one character changed - a different TLD,
or the trusted host as a prefix of a longer name - is what separates
"reflects anything" from "prefix/suffix match" from "correct allow list". Most
public CORS methodology sends one evil origin and stops.

**`cookies` requires the cookie to actually arrive and actually be honoured.**
Reading the browser's own jar for the declared attributes as a control and then
recording a `credential_effect` at the place the cookie reached is materially
stronger than the "missing HttpOnly" reports that dominate triage queues. The
explicit refusal to treat `HttpOnly` as the class is defensible.

**`http-desync`'s refusal is honest and mechanised.** `transport_makeability`
records `transport.request_framing` as `unmakeable` with the mechanism attached,
and `transport_claim_guard()` refuses the class at INSERT. That is a better
answer than a Playbook that pretends to smuggle through mitmproxy and reports the
proxy's own framing.

## Missing techniques (ranked by expected yield on a real bounty program)

### 1. Web cache deception through path confusion (delimiters, normalization, static rules)

Our `web-cache` Playbook tests exactly one shape: same URL, cache key omits the
caller. The dominant paying shape in 2024-2026 is the opposite - a *different*
URL that the cache classifies as a static asset and the origin resolves to the
victim's dynamic, authenticated page. Doyhenard's Black Hat USA 2024 paper
enumerates the discrepancy families: **delimiters** (`;` in Spring, `.` in Rails,
`%00` in OpenLiteSpeed, `%0a` in nginx rewrite context), **normalization**
(`/x/..%2fy` resolving differently in Apache, nginx and each CDN),
**static extension rules** (Cloudflare caching anything ending `.js`/`.css`),
**static directory rules** (`/static`, `/assets`) and **static file rules**
(`robots.txt`, `favicon.ico`). The ChatGPT account takeover of February 2024 is
the canonical bounty instance: `/share/%2F..%2Fapi/auth/session?cachebuster=123`
- Cloudflare did not decode `%2F..%2F` when computing the key, the origin did
when routing, and `Cf-Cache-Status: HIT` on a session document followed. The
Academy now names four detection primitives: path mapping discrepancies,
delimiter discrepancies, delimiter *decoding* discrepancies, and normalization
discrepancies.

Belongs in: `web-cache` (new steps), with `deployment` as the neighbour when the
same discrepancy produces an auth bypass rather than a stored response.

What our Playbook must be able to observe: (a) that the origin's *response body*
for the crafted URL is the same authenticated document as for the clean URL -
i.e. the origin normalised the path; (b) that the front end classified the
crafted URL as cacheable - from `X-Cache`/`CF-Cache-Status`/`Age`/`Cache-Control`
on the crafted URL only; (c) that a second request on that key with no session
returns the authenticated body. All three are reachable through an intercepting
proxy, because the attack is entirely in the URL string. Safety is unchanged from
today: put the run's random token in the crafted path so the key is ours.

Sources: https://portswigger.net/research/gotta-cache-em-all (Martin Doyhenard,
published 2024-08-08, updated 2026-01-08);
https://nokline.github.io/bugbounty/2024/02/04/ChatGPT-ATO.html (2024-02-04);
https://portswigger.net/web-security/web-cache-deception (Web Security Academy,
undated living page, built on the 2024 paper).

### 2. Cache poisoning of an unkeyed input, tested on a key this run owns

`web-cache` step 6 refuses unkeyed-input poisoning outright on blast-radius
grounds, and then step 2 builds the exact primitive that removes the blast
radius. That is internally inconsistent, and it costs us the highest-frequency
cache class on real programs: `X-Forwarded-Host`, `X-Forwarded-Scheme`,
`X-Host`, `X-Original-URL`, unkeyed query parameters, unkeyed port, fat GET
(body on a GET), and cache-parameter cloaking. The Academy's own instruction for
testing live sites is to add a cache buster precisely so the poisoned entry is
never served to a real user, and Doyhenard's "Cache-What-Where" section shows the
escalation path: an input the origin reflects but which is normally
unexploitable becomes site-takeover once it is stored.

Belongs in: `web-cache` (a second arm on the invented key), outputting either the
existing `information_disclosure.cached_response` or a new sibling leaf for a
stored *reflected* input.

What our Playbook must be able to observe: the reflected value in the response to
the request that carried the header, then the same reflected value in a second
request on the same invented key that did *not* carry the header, with a hit
indicator. The refutation is the second request coming back clean. It must also
observe `Vary` on the arm - a `Vary: X-Forwarded-Host` is the target keying the
input and refutes the class.

Sources: https://portswigger.net/web-security/web-cache-poisoning (Web Security
Academy, undated living page; names X-Forwarded-Host, unkeyed port, unkeyed query
string, cache parameter cloaking, normalized cache keys, cache key injection, fat
GET); https://portswigger.net/research/gotta-cache-em-all (2024-08-08).

### 3. Framework-internal header cache poisoning (the Next.js class)

A whole class of 2024-2026 cache bugs needs no CDN misconfiguration at all: the
framework itself decides cacheability from headers a caller can send.
`x-middleware-prefetch` returns an empty `{}` that gets stored (CVE-2023-46298);
`x-invoke-status`/`x-invoke-error` overwrite the status so an error page is
stored under a 200; `x-now-route-matches` makes an SSR route be treated as SSG so
`Cache-Control: s-maxage=1, stale-while-revalidate` replaces
`private, no-cache, no-store` (CVE-2024-46982, Next.js 13.5.1-14.2.9, Pages
Router); `Rsc: 1` with `_rsc=` stores an RSC payload where HTML belongs; and a
204 response poisons to a denial of service (CVE-2025-49826). The stale elixir
chain placed 7th in PortSwigger's Top 10 of 2025.

Belongs in: `web-cache` (a named header list for the poisoning arm above),
`exceptional-conditions` (the `x-invoke-status` variant is an error response
being made cacheable).

What our Playbook must be able to observe: `Cache-Control` on the arm differing
from `Cache-Control` on the baseline for the *same route* - that difference is
the finding, and it is visible in one request pair without ever storing anything
a user could reach. Plus the framework fingerprint (`x-nextjs-cache`,
`x-powered-by`, `x-vercel-*`) to decide the header list is applicable.

Sources:
https://zhero-web-sec.github.io/research-and-things/nextjs-cache-and-chains-the-stale-elixir
(Rachid Allam, January 2025, CVE-2024-46982);
https://zhero-web-sec.github.io/research-and-things/nextjs-and-cache-poisoning-a-quest-for-the-black-hole
(June 2024, CVE-2023-46298);
https://zhero-web-sec.github.io/research-and-things/nextjs-cache-poisoning-to-dos-via-a-204-response
(July 2025, CVE-2025-49826);
https://portswigger.net/research/top-10-web-hacking-techniques-of-2025
(2026-02-05, ranks the stale elixir 7th).

### 4. Cookie parser differentials: `$Version`, the cookie sandwich, and prefix bypass

Our `cookies` Playbook is entirely about *scope* (`Domain`, `Path`, `Secure`,
`SameSite`) and has no notion that the `Cookie` header is parsed by two different
grammars. Fedotkin's three-part sequence is the current state of the art: a
`Cookie` header beginning `$Version=1` flips Tomcat, Jetty and several Python
stacks into legacy RFC2109 parsing, where quoted-string values swallow following
cookies until an unescaped `"` - so a script-set `$Version` plus a trailing quote
can *sandwich* an `HttpOnly` cookie into a value the application reflects
(published 2025-01-22, affecting Tomcat 8.5.x/9.0.x/10.0.x). The same legacy mode
hides `;`, `,` and newlines inside quoted values and defeats AWS WAF
(2024-12-04). And `__Host-`/`__Secure-` prefixes fall to Unicode whitespace
prefixes that browsers keep and Django/ASP.NET strip, or to a forged `__Host-`
pair injected through legacy parsing on Java servers (2025-09-03).

Belongs in: `cookies` (a new parsing half beside the existing scope half). The
`session_handling.cookie_scope` class does not fit; this wants a sibling leaf
about the parser, not the scope.

What our Playbook must be able to observe: the target's *reflection* of a cookie
value (a tracking endpoint, an error page, a debug view) is the read channel, so
the Playbook needs a route that echoes a cookie. The safe, read-only observation
that costs nothing is narrower and still worth a step: send a `Cookie` header
whose first pair is `$Version=1` and observe whether the application's behaviour
for the *session* cookie changes at all. A behaviour change on that one byte is
the parser telling you which grammar it used. Note the proxy caveat in the last
section - this is header-value level, not framing level, so it survives
re-serialisation, but it must be confirmed that mitmproxy does not normalise or
re-order the `Cookie` header.

Sources:
https://portswigger.net/research/stealing-httponly-cookies-with-the-cookie-sandwich-technique
(Zakhar Fedotkin, 2025-01-22, updated 2025-06-30);
https://portswigger.net/research/bypassing-wafs-with-the-phantom-version-cookie
(Fedotkin, 2024-12-04, updated 2025-06-30);
https://portswigger.net/research/cookie-chaos-how-to-bypass-host-and-secure-cookie-prefixes
(Fedotkin, 2025-09-03).

### 5. Hidden caches - the ones that publish no header

`web-cache` has `tech_cdn` in `bb:triggers_all` and reads `X-Cache`,
`CF-Cache-Status` and `Age`. Golinelli and Crispo measured that 5.8% of the top
50,000 sites run a server-side cache that advertises nothing, and found 1,020
sites vulnerable to cache deception behind exactly those invisible caches. Their
detection is a timing pair over HTTP multiplexing: two requests, one cache-busted
and one not, differenced on response time, 89.6% agreement with header-based
detection. Framework caches (Next.js ISR, Varnish without `X-Varnish`, nginx
`proxy_cache` without `add_header`) are the common real-world instance.

Belongs in: `web-cache` (a precondition step), and a relaxation of the trigger set
so the Playbook can run without `tech_cdn`.

What our Playbook must be able to observe: without a hit indicator, storage has to
be inferred from an invariant that should have moved - a `Date` header that did
not advance across two sends seconds apart, an `Age` that appeared, an `ETag`
that is identical across two sends of a route whose body contains a timestamp, or
a response time that collapses on the second send. The `Date`-did-not-advance
check is the cheapest and is fully available through the proxy; the timing check
is available but noisy through it (see the last section).

Sources: https://arxiv.org/abs/2407.16303 ("Hidden Web Caches Discovery",
Matteo Golinelli and Bruno Crispo, submitted 2024-07-23, RAID 2024).

### 6. Ambiguity inside the structured body, not between carriers

`request-parsing` tests one name in two carriers (query and body). That is the
2010-era HTTP Parameter Pollution shape. The 2025 shape is ambiguity *within one
document*, and it pays because gateways and services parse the same JSON with
different libraries: Go's `encoding/json` matches field names case-insensitively
(so `action`, `ACTION` and `aCtIoN` are one field to Go and three to everyone
else), JSON and XML parsers disagree on whether the first or last duplicate key
wins, all of them silently drop unknown fields, and Go's XML parser accepts
leading and trailing garbage so a polyglot document parses differently in two
places. Trail of Bits ties this directly to CVE-2020-16250 (HashiCorp Vault AWS
IAM auth bypass) and CVE-2017-12635 (CouchDB authorization bypass). YesWeHack's
October 2025 piece generalises the same idea across URL port normalization
(`:000443`), `Content-Disposition` `filename` vs `filename*`, and Unicode named
escapes.

Belongs in: `request-parsing` (a second arm shape beside the two-carrier arm).

What our Playbook must be able to observe: the same two halves it already looks
for - what the answer *says* it accepted versus what it *produced* - but with the
arm being a body containing the same key twice, or the key in two letter cases,
or one extra unknown field. The control stays the same: the same duplication on a
name the route does not act on. Nothing here needs a new capability; it needs a
new arm and a broader trigger than `repeated_parameter_name`.

Sources:
https://blog.trailofbits.com/2025/06/17/unexpected-security-footguns-in-gos-parsers/
(Vasco Franco, 2025-06-17);
https://www.yeswehack.com/learn-bug-bounty/syntax-confusion-ambiguous-parsing-exploits
(Alex Brumen, 2025-10-17);
https://portswigger.net/research/top-10-web-hacking-techniques-of-2025
(2026-02-05, ranks "Parser Differentials: When Interpretation Becomes a
Vulnerability" 10th - https://www.youtube.com/watch?v=Dq_KVLXzxH8, a conference
recording that was not fetched).

### 7. Encoding and Unicode normalization differentials in the path

`file-resolution` step 8 refuses the encoding catalogue, and for a single-hop file
read that refusal is right - one dull file already proves the resolution left the
directory. But the modern finding is not single-hop: it is that the *edge* and the
*origin* decode differently, and the arm that proves it is an encoding variant,
not a plain `../`. `%2F..%2F` was the whole ChatGPT bug. Orange Tsai's Apache
work shows the same thing inside one server: an encoded question mark (`%3F`)
truncates `r->filename` for some modules and not others, and a `RewriteRule` in
Server Config or VirtualHost context makes Apache try the path both with and
without DocumentRoot (nine CVEs, fixed in httpd 2.4.60, 2024-07-01; ranked 1st in
PortSwigger's Top 10 of 2024). "Lost in Translation: Exploiting Unicode
Normalization" placed 4th in the Top 10 of 2025 on the same theme.

Belongs in: `deployment` primarily (it holds `authorization.edge_rule` and already
sends a "second spelling"), `file-resolution` secondarily (an encoded-variant arm
when the plain arm is refused by a filter rather than by the application), and
`web-cache` for the key-normalization case.

What our Playbook must be able to observe: which hop answered. `deployment` step 1
already asks "who refused it", and that is the right hook - the encoded variant is
only interesting when the refusal came from the edge and the second spelling
reached the origin. Distinguishing hops needs a server fingerprint (`Server`,
error-page shape, header order) recorded as part of the refusal.

Sources: https://blog.orange.tw/posts/2024-08-confusion-attacks-en/ (Orange Tsai,
2024-08-09; nine CVEs in httpd 2.4.60, 2024-07-01);
https://portswigger.net/research/top-10-web-hacking-techniques-of-2024
(2025-02-04, ranks Confusion Attacks 1st);
https://portswigger.net/research/top-10-web-hacking-techniques-of-2025
(2026-02-05, ranks Unicode normalization 4th -
https://www.youtube.com/watch?v=ETB2w-f3pM4, a recording that was not fetched);
https://nokline.github.io/bugbounty/2024/02/04/ChatGPT-ATO.html (2024-02-04).

### 8. Cookie tossing and cookie injection from a sibling origin

`cookies` asks where a cookie *goes*. The paying question in 2024-2026 is the
reverse: what a sibling subdomain can *write* into the parent's jar. A subdomain
setting `Domain=.example.com` with `Path=/api/authorize` wins the browser's
path-specificity ordering, `SameSite` gives no protection because the subdomain
satisfies the same-site definition, and JSON APIs that rely on CORS preflight
rather than a token have no defence. Snyk's November 2024 write-up chains this
into OAuth account linking - the victim's Git account links to the attacker's -
and it placed 10th in PortSwigger's Top 10 of 2024. `__Host-` is the mitigation,
and entry 4 above is why `__Host-` is not always sufficient.

Belongs in: `cookies` (an observation step, not an arm), with `oauth` as the
neighbour for the linking flow.

What our Playbook must be able to observe: whether the application's session or
CSRF cookie carries a `Domain` naming the registrable parent, whether it carries a
`__Host-` prefix, and whether any in-scope host under that parent is one whose
content a caller can influence. That is a read of the jar it already takes, plus
one scope question. The write half is out of reach and should stay out of reach:
a Playbook that sets a cookie into a shared parent domain has changed state for
every user of every sibling host.

Sources: https://labs.snyk.io/resources/hijacking-oauth-flows-via-cookie-tossing/
(Elliot Ward, 2024-11-26);
https://portswigger.net/research/top-10-web-hacking-techniques-of-2024
(2025-02-04, ranks it 10th). Older but still landing: "Cookie Crumbles: Breaking
and Fixing Web Session Integrity" (USENIX Security 2023), listed 9th in
https://portswigger.net/research/top-10-web-hacking-techniques-of-2023
(2024-02-19) at
https://www.usenix.org/conference/usenixsecurity23/presentation/squarcina - the
USENIX page was not fetched.

### 9. Cacheable error responses (CPDoS), and the "which layer answered" question

Older than the window - CCS 2019 - and still landing, because it needs no
application bug: the cache accepts a request the origin rejects, and stores the
rejection. Three variants: HTTP Header Oversize (header limits differ between
cache and origin), HTTP Meta Character (a meta character the cache forwards and
the origin refuses), HTTP Method Override (`X-HTTP-Method-Override` making the
cache store a response for a different method). CloudFront, Akamai, Azure,
CDN77, Cloudflare, Fastly, G-Core, KeyCDN and StackPath were all documented as
affected. Next.js CVE-2025-49826 (a cached 204) is the same shape in a framework.

This sits exactly in the seam between two of our Playbooks and falls through it:
`exceptional-conditions` refuses long inputs by design, and `web-cache` refuses
poisoning by design.

Belongs in: `exceptional-conditions` (one step) plus the `web-cache` poisoning
arm from entry 2 - on the invented key, a cached 4xx is a `read_only`
observation with zero blast radius.

What our Playbook must be able to observe: which layer produced the error. A 400
from the edge and a 400 from the origin look the same in a status line and differ
in `Server`, in header order, in body shape, and in whether `X-Cache` is present
at all. Recording that distinction also gives `exceptional-conditions` the thing
it currently cannot say - step 6 calls "a gateway that rewrites every 5xx into
the same page" inconclusive, when in fact that gateway is itself the observation.

Sources: https://cpdos.org/ (Hoai Viet Nguyen, Luigi Lo Iacono, Hannes Federrath;
ACM CCS 2019);
https://zhero-web-sec.github.io/research-and-things/nextjs-cache-poisoning-to-dos-via-a-204-response
(July 2025, CVE-2025-49826).

### 10. The CORS arms we do not send: `null`, scheme downgrade, and preflight-free writes

`request-integrity` sends three origins: none, trusted, untrusted, plus a
near-miss. Three arms it does not send are where current reports live.
`Origin: null` is reachable from any sandboxed iframe or `data:` URL and is
allow-listed by a surprising number of deployments that believe it means "no
origin". `Origin: http://<trusted-host>` tests whether the allow list checks the
scheme. And the whole class of writes that require no preflight - a `POST` with
`Content-Type: text/plain` or `application/x-www-form-urlencoded` - is what makes
a JSON API CSRF-able despite CORS, which is the mechanism the cookie-tossing work
above depends on. PortSwigger's 2025 nomination list also carries a
WebSocket-based route around preflight-gated CSRF ("Cross-Site WebSocket
Hijacking Exploitation ... via WebSocket-accessible GraphQL").

Belongs in: `request-integrity` (two more arms in step 3), with `realtime` keeping
`session_handling.csrf` and gaining the WebSocket neighbour.

What our Playbook must be able to observe: exactly what it already observes - the
two response header lines - for two more `Origin` values. This is the cheapest
improvement in the whole document: two requests.

Sources: https://portswigger.net/research/top-10-web-hacking-techniques-of-2025
(2026-02-05, and the nominations page below for the CSWSH entry);
https://portswigger.net/research/top-10-web-hacking-techniques-of-2025-nominations-open
(nominations list); https://labs.snyk.io/resources/hijacking-oauth-flows-via-cookie-tossing/
(2024-11-26, for the "JSON APIs rely on preflight rather than a token" mechanism);
https://osec.io/blog/2025-10-16-how-we-broke-exchanges-oauth-misconfigurations
(listed in the 2025 nominations as mixed-content CORS from insecure subdomains;
not fetched).

### 11. A desync *exposure surface* reading, without any framing

We cannot make a framing claim and should not try. We can record the
preconditions that decide whether a target is in the population Kettle
compromised, and hand that to an operator who holds a raw-socket capability.
The 2025 research makes the preconditions explicit: the target speaks HTTP/2 to
the caller but downgrades to HTTP/1.1 upstream (H2.0 desync - 24 million
Cloudflare-fronted sites); the origin honours `Expect:` (four Expect-based
variants, vanilla and obfuscated, in both 0.CL and CL.0 directions); an
early-response gadget exists (`/con` on IIS, any path answering before the body
is read); a "Mystery 400" pattern appears. CVE-2025-32094 (Akamai) and
roughly $350,000 in bounties in two weeks came out of that population. Kettle's
own advice to in-house testers is to map how requests transform across the proxy
chain first.

Belongs in: `http-desync` (rewrite of step 1 and step 4), outputting surface facts
rather than a new claim.

What our Playbook must be able to observe, all of it available through the proxy:
the negotiated protocol on the caller side (already step 1); `Alt-Svc` (already
step 1); whether the deployment answers `Expect: 100-continue` and how; whether
a `Connection:` header value is echoed or acted on; the `Server` fingerprint of
the front end; and whether a path exists that answers before a body is sent. None
of these is a framing claim - each is a header or a status the target returned.

Sources: https://portswigger.net/research/http1-must-die (James Kettle,
2025-08-06, updated 2025-10-17; 0.CL, double-desync, four Expect variants, V-H
and H-V header masking, H2.0 and H2.TE, CVE-2025-32094, HTTP Request Smuggler
v3.0); https://i.blackhat.com/BH-USA-25/Presentations/US-25-Kettle-HTTP1-Must-Die-The-Desync-Endgame-wp.pdf
(Black Hat USA 2025 whitepaper, referenced in search results, not fetched);
https://portswigger.net/blog/http-1-1-must-die-what-this-means-for-in-house-pentesters
(2025-08-06);
https://www.bugcrowd.com/blog/unveiling-te-0-http-request-smuggling-discovering-a-critical-vulnerability-in-thousands-of-google-cloud-websites/
(Paolo Arnolfo, Guillermo Gregorio, @_medusa_1_, 2024-07-17; TE.0 against Google
Cloud Load Balancer, bypassing Identity-Aware Proxy).

### 12. The error message as an oracle, not only as a disclosure

`exceptional-conditions` treats an error as a leak of internals. The 2023-2026
direction is to treat it as a *read channel* for something else. Synacktiv's PHP
filter chains turn `iconv`-driven memory exhaustion plus the `dechunk` filter into
a per-character oracle that reads a file the application never prints
(2023-03-21, ranked 4th in the Top 10 of 2023). Korchagin's "Successful Errors"
does the same for blind code injection and SSTI: an Error-Based technique where
the error message reflects the result of the injected expression, and a Boolean
Error-Based Blind technique that conditionally triggers an error instead of a
sleep - payloads for Python, PHP, Java, Ruby, NodeJS and Elixir, folded into
SSTImap 1.3.0+, and ranked 1st in PortSwigger's Top 10 of 2025.

Belongs in: mostly `ssti` and `sql-injection` for the payloads, but the
*observation contract* is `exceptional-conditions`': "a failure that quotes the
caller's own value" is currently treated as the benign case, and it is exactly
the channel these techniques need. The list in step 5 should gain a sixth item -
whether the failure quotes a *computed* value rather than the submitted one.

What our Playbook must be able to observe: the difference between an error that
echoes the input verbatim and an error that echoes something derived from it.
That is a string comparison against the value sent, which `compare-responses`
can already carry.

Sources:
https://www.synacktiv.com/publications/php-filter-chains-file-read-from-error-based-oracle
(Rémi Matasse, 2023-03-21);
https://github.com/vladko312/Research_Successful_Errors (Vladislav Korchagin,
whitepaper v1.1 last modified 2026-02-22);
https://portswigger.net/research/top-10-web-hacking-techniques-of-2025
(2026-02-05, ranks Successful Errors 1st);
https://portswigger.net/research/top-10-web-hacking-techniques-of-2023
(2024-02-19, ranks PHP filter chains 4th).

### 13. Timing as an observable, at the coarse end only

Every Playbook in this cluster differences bodies and headers. Kettle's 2024
timing work adds a fourth attribute and shows what it buys: scoped SSRF detected
from whether a hostname resolution was attempted (with an overlong 64-octet DNS
label as the amplifier), blind server-side injection detected from response-order
bias across ~50 request pairs, and - most relevant here - hundreds of
misconfigured reverse proxies found to expose alternative routes to internal
systems, in four categories including front-end rule bypass and front-end
impersonation. Param Miner carries timing as a response attribute now. The
hidden-cache work in entry 5 is the same idea applied to storage.

Belongs in: cross-cutting - `web-cache` (hidden cache detection),
`request-parsing` (proxy misrouting), `exceptional-conditions` (a failure that
takes longer is a failure that happened further in).

What our Playbook must be able to observe: a per-request duration on the receipt,
and a stated noise floor. The precise variants (single-packet attack, request
pairs synchronised by an HTTP/2 ping frame) are unreachable - see the last
section - but the coarse ones are not: a DNS resolution attempt costs hundreds of
milliseconds to seconds and survives any proxy.

Sources:
https://portswigger.net/research/listen-to-the-whispers-web-timing-attacks-that-actually-work
(James Kettle, 2024-08-07, updated 2024-11-18); https://arxiv.org/abs/2407.16303
(Golinelli and Crispo, RAID 2024).

### 14. Response-size and header-limit side channels

Lower yield than the above and included because it is where the 2025 research
went. Kaneko's cross-site ETag length leak turns a one-byte change in an `ETag`
(Node's `jshttp/etag` encodes content size in hex, so crossing `0xfff` to
`0x1000` lengthens the string) into a detectable navigation failure, by padding
the URL so that the resulting `If-None-Match` pushes the request over the header
limit and produces a 431, then reading the failure through Chromium's history
handling. Ranked 6th in the Top 10 of 2025. The general lesson for us is that
`ETag`, `Content-Length` and header-size limits are observable state that our
Playbooks currently ignore, and that a 431 or 413 from the edge is a measurement
of the edge's limits - which is also the CPDoS HHO precondition.

Belongs in: `exceptional-conditions` (record the edge's header-size and body-size
limits as surface when a 431/413 is seen), `web-cache` (record `ETag`).

Sources: https://blog.arkark.dev/2025/12/26/etag-length-leak (Takeshi Kaneko /
arkark, 2025-12-26);
https://portswigger.net/research/top-10-web-hacking-techniques-of-2025
(2026-02-05, ranks it 6th).

### 15. Raw-framing techniques listed for completeness (all currently unmakeable)

Recorded here so the corpus has the names, not because a Playbook can execute
them today. Every one is analysed in the last section.

* **0.CL, double-desync, Expect-based desync (vanilla and obfuscated), V-H/H-V
  header masking, H2.0, H2.TE.** Kettle, 2025-08-06.
* **CL.0 / TE.0.** CL.0 from Kettle 2022; TE.0 from Bugcrowd 2024-07-17 against
  Google Cloud Load Balancer, bypassing Identity-Aware Proxy.
* **Funky chunks - chunk line-terminator ambiguity.** Four variants (TERM.EXT,
  EXT.TERM, TERM.SPILL, SPILL.TERM) turning on parsers that accept a lone `\n`
  or `\rX` where only `\r\n` is valid. Affects Apache Traffic Server, Google
  Cloud Load Balancer, Imperva CDN and pound as proxies, and aiohttp, fasthttp,
  gunicorn, nginx, Jetty, Grizzly, netty, H2O, Go `net/http`, uvicorn, hypercorn,
  Ktor and uHTTPd as servers. Detected black-box by timeout probes.
  https://w4ke.info/2025/06/18/funky-chunks.html (Jeppe Bonde Weikop,
  2025-06-18), addendum https://w4ke.info/2025/10/29/funky-chunks-2.html
  (2025-10-29, listed in the nominations page, not fetched).
* **Request tunnelling via H2 to H1 downgrade, parallelised with the
  single-packet technique** - ~80% reliability instead of ~2000 sequential
  attempts, buys access-control bypass, `X-Forwarded-For` spoofing to localhost
  and path-filter evasion; fixed by AWS Application Load Balancer and Azure Front
  Door. https://www.assured.se/posts/the-single-packet-shovel-desync-powered-request-tunnelling
  (Thomas Stacey, 2025-05-12).
* **HTTP/2 CONNECT stream multiplexing** turning a misconfigured forward proxy
  into a port scanner over one connection; reliable against Envoy and Apache
  httpd. Ranked 9th in the Top 10 of 2025.
  https://blog.flomb.net/posts/http2connect/ (flomb, 2025-09-15).
* **HTTP/3 to HTTP/1 cross-protocol desync**: a single QUIC STREAM frame with
  zero payload and the FIN bit set makes HAProxy forward a `Content-Length: N`
  request with no body, and the next user's request on the pooled TCP connection
  loses its first N bytes. CVE-2026-33555, HAProxy 2.6 through 3.3.5 built with
  `USE_QUIC=1`, fixed in 3.3.6 / 3.2.15 / 3.0.19 / 2.8.20 / 2.6.25.
  https://r3verii.github.io/cve/2026/04/14/haproxy-h3-standalone-fin-smuggling.html
  (2026-04-14). Single-researcher blog; it links a HAProxy fix commit and an NVD
  record, neither of which was fetched, so treat the version list as unconfirmed
  until the vendor advisory is read.
* **Client-side / browser-powered desync.** The desync happens between the
  victim's browser and the front end, so single-server sites are exploitable and
  no proxy chain is needed - but the browser has to write the bytes.
  https://portswigger.net/research/browser-powered-desync-attacks (2022-08-10;
  older, still the basis of the CL.0 family).
* **Opossum - cross-protocol application-layer desync** by MITM-switching a
  client from implicit TLS to opportunistic TLS. Affects HTTP, FTP, POP3, SMTP,
  LMTP and NNTP; CVE-2025-49812 for the Apache Foundation.
  https://opossum-attack.com/ (Merget, Erinola, Maehren, Knittel, Hebrok,
  Brinkmann, Somorovsky, Schwenk; 2025). Requires a network position we will
  never have and should never seek on a bounty program.

## What in our playbooks looks stale or weak

**`web-cache` is one third of a cache Playbook.** It covers unkeyed *caller* and
explicitly declines unkeyed *input* and never mentions deception at all - which
is the class that pays most. Its `bb:triggers_all` requires `tech_cdn`, so it
skips hidden caches (5.8% of the top 50k) and every framework-level cache. Its
hit vocabulary is `X-Cache`/`CF-Cache-Status`/`Age` and nothing else, so a
Varnish or nginx cache configured without `add_header` is invisible to it. Step 4
says "repeat once" - two consecutive reads - which is right, but there is no
`Age` arithmetic and no TTL reasoning, so it cannot say how long a stored entry
lasts, which is the first thing a triager asks. And step 6's blanket refusal of
poisoning contradicts step 2's own safety construction.

**`request-parsing` is a 2010 technique with a 2026 evidence contract.** Two
carriers, one name. Its trigger `repeated_parameter_name` will almost never fire
on a modern JSON API, its `effects: mutates_object` restricts it to write routes
when the same claim is observable on reads, and it has no arm for duplicate keys
inside one document, letter-case collisions, or content-type confusion. Step 6's
authority-header half is correctly refused, but it is also the only place in the
corpus that mentions `X-Forwarded-Host` - which is the most common unkeyed cache
input - and it routes that observation into a Task note rather than into
`web-cache`.

**`request-integrity` is named for integrity and implements CORS reads.** It
sends four requests and omits `Origin: null` and the scheme-downgrade origin,
which are two more requests. It has no position on preflight-free writes, which
is the mechanism that makes the cookie-tossing and CSWSH families work. The name
promises more than `session_handling.cross_origin_read` delivers, and a reader
will assume request-integrity covers smuggling or signature validation.

**`cookies` has no parser.** Everything it knows about a cookie is an attribute
in the jar. It cannot see `$Version` legacy parsing, quoted-value swallowing,
`__Host-` prefix forgery, or Unicode-whitespace prefix stripping - three
PortSwigger research posts between December 2024 and September 2025, all
reachable with header-level access. It also has no notion of what a sibling
subdomain can write, which is the direction the 2024 Top 10 entry went.

**`exceptional-conditions` fuzzes nothing, which is right, and observes only one
axis, which is not.** It requires `quantity_valued_parameter`, so it never runs on
a JSON body where type confusion (string for array, object for scalar, null for
required) is the natural surprise. It records what the error *says* and not
*which layer said it*, so a gateway that rewrites every 5xx is scored
`inconclusive` when that gateway is itself a measurement. And it treats "the
failure quotes only the caller's own value" as the benign terminal case, which
closes the door on the error-as-oracle direction the field went in 2023-2026.

**`file-resolution` is strong and narrow.** `bb:triggers_all` needs a
`path_valued_parameter`, so it cannot run on a traversal that lives in the URL
path itself - which is where the ChatGPT bug, the Apache confusion attacks and
the cache-deception family all live. Its refusal of the encoding catalogue is
right for the single-hop case and wrong for the two-hop case, where the encoding
*is* the variable under test.

**`http-desync` is a correct refusal that has stopped being a reading.** Two
ordinary reads and two TLS measurements is a `transport.tls_configuration`
Playbook wearing a desync Playbook's slug. Its `bb:references` are the v1 pack's
pages and predate the entire 2025 desync literature, and its
`bb:stale_after: 2027-05-15` will let it sit through another two Top 10 cycles.
The slug itself is now misleading in a corpus where an operator picks Playbooks
by name.

## Concrete change proposals per playbook

* **`src/redkraken/playbooks/web-cache/playbook.md`** - add a step between the
  current 2 and 3, "Ask whether the front end and the origin agree what this URL
  is": on the invented key, send the route with one path-confusion variant at a
  time (`;rk-<token>.css`, `/rk-<token>.css`, `%2f..%2frk-<token>.css`,
  `?rk-<token>=1.js`), and record for each whether the origin returned the same
  authenticated body *and* whether the front end marked it cacheable. Rewrite
  step 6 so it refuses poisoning **on a shared key** and permits one unkeyed-input
  arm **on the invented key**, with the header list named
  (`X-Forwarded-Host`, `X-Forwarded-Scheme`, `X-Original-URL`,
  `x-middleware-prefetch`, `x-invoke-status`, `x-now-route-matches`) and `Vary`
  read as the refutation. Add a `Date`-did-not-advance / `Age`-appeared check to
  step 3 so the Playbook can run without a published hit indicator, and drop
  `tech_cdn` from `bb:triggers_all` in favour of a `web_surface` trigger.
* **`src/redkraken/playbooks/request-parsing/playbook.md`** - rewrite step 2 to
  offer three arm shapes rather than one: the same name in two carriers (today),
  the same key twice inside one JSON body, and the same key in two letter cases.
  Add a step 6b that hands the `X-Forwarded-Host` observation to `web-cache`
  rather than to a Task note. Broaden `bb:triggers_all` beyond
  `repeated_parameter_name`, and add a `read_method` variant of the subject so the
  Playbook is not confined to `mutates_object`.
* **`src/redkraken/playbooks/request-integrity/playbook.md`** - extend step 3 from
  two arms to four by adding `Origin: null` and `Origin: http://<trusted-host>`,
  and add a sentence to step 5's neighbour list pointing preflight-free writes
  (`text/plain`, `application/x-www-form-urlencoded`) and WebSocket-reachable
  APIs at `realtime`. Consider renaming the slug to something that says CORS,
  because the current name claims a scope the Playbook does not have.
* **`src/redkraken/playbooks/cookies/playbook.md`** - add a step 2b, "Ask which
  cookie grammar the server used": one request whose `Cookie` header begins
  `$Version=1` before the session pair, differenced against the baseline, with
  the refutation being that nothing changed. Add to step 2's record whether each
  cookie carries a `__Host-`/`__Secure-` prefix and whether `Domain` names a
  registrable parent, and add a closing observation naming any in-scope sibling
  host under that parent as cookie-tossing surface for an operator - an
  observation, explicitly not an arm.
* **`src/redkraken/playbooks/exceptional-conditions/playbook.md`** - rewrite step
  4's arms so the two type violations are chosen from the parameter's actual
  carrier: for a JSON body, an array where a scalar is expected and a null where a
  string is expected, keeping the "short and ordinary" rule. Add to step 5 a sixth
  disclosure item - a failure quoting a value *derived* from the input rather than
  the input itself - and a new step recording **which layer answered** (`Server`,
  header order, presence of a cache header) so a gateway-rewritten 5xx becomes an
  observation instead of `inconclusive`. Record any 431/413 and the limit it
  implies as surface.
* **`src/redkraken/playbooks/file-resolution/playbook.md`** - add an
  encoded-variant arm that fires only in the branch step 7 currently sends to
  `inconclusive` ("a route behind a WAF that refuses every value containing a
  dot-dot"): one arm with the same dull target written `%2e%2e%2f`, one written
  `%2f..%2f`, differenced against the plain arm's refusal. Loosen
  `bb:triggers_all` so a traversal in the URL path (no parameter) is in scope, and
  add `web-cache` to the neighbour list, because the same discrepancy that reads a
  file also produces a cache key.
* **`src/redkraken/playbooks/http-desync/playbook.md`** - rewrite step 1 from
  three recorded values to a desync **exposure surface**: negotiated protocol,
  `Alt-Svc`, HSTS (today), plus the front-end `Server` fingerprint, the answer to
  `Expect: 100-continue`, whether a `Connection:` value is echoed or acted on, and
  whether the deployment downgrades to HTTP/1.1 upstream as far as any header
  reveals. Rewrite step 6 to keep the refusal but cite the 2025 literature for
  *why the population is large*, and to name the operator capability that would be
  required. Refresh `bb:references` (they predate the 2025 desync work) and pull
  `bb:stale_after` in to 2026-08-15. Consider a slug that says what it does.
* **`src/redkraken/playbooks/deployment/playbook.md`** (adjacent, holds
  `authorization.edge_rule`) - make step 1's "who refused it" a recorded
  fingerprint rather than a note, and add encoded and Unicode-normalized spellings
  to step 3's second-spelling menu, since that is the arm the Apache confusion and
  edge-normalization families actually turn on.

## What is unreachable through an intercepting proxy, and what would have to change

The rule that produces the refusal is recorded in
`src/redkraken/migrations/0025_transport_claims.sql`: mitmproxy parses and
re-serialises every request, so `transport.request_framing` is `unmakeable` and
`transport_claim_guard()` refuses the class at INSERT; `transport.datagram_transport`
is `unmakeable` because the proxy is TCP+TLS. That is correct and none of the
below argues with it.

**Needs raw sockets - the harness cannot get within an order of magnitude today:**

* Every length-header disagreement: CL.TE, TE.CL, CL.0, 0.CL, TE.0, double
  desync. The variable under test is *which bytes the target frames*, and the
  proxy rewrites exactly those bytes. Header obfuscation (V-H / H-V masking,
  a space before the colon, a tab after the value) is normalised or rejected by
  the proxy's own parser before it reaches the wire.
* Chunk line-terminator ambiguity (funky chunks). A lone `\n` where `\r\n`
  belongs cannot survive a re-serialising parser; mitmproxy will emit `\r\n`.
* Expect-based desync. The proxy owns the 100-continue state machine, so an
  obfuscated `Expect` never reaches the front end as sent.
* HTTP/2-specific framing: H2.0, H2.TE, request tunnelling via downgrade,
  HTTP/2 CONNECT. These need control over pseudo-headers, header values
  containing CRLF, and stream framing. A proxy that terminates H2 and re-emits it
  destroys all of it.
* The single-packet attack in both its race and its timing forms. It depends on
  coalescing frames into one TCP packet (Kettle's 2024 version uses an HTTP/2
  ping frame to force the OS to do it). A proxy re-packetises, so the arrival
  ordering measured is the proxy's.
* HTTP/3 and QUIC desync (the HAProxy standalone-FIN class). No QUIC egress
  exists at all.
* Client-side / browser-powered desync. The browser must write the bytes onto a
  socket the front end reads directly; our browser lane is proxied too.
* Opossum. Requires a man-in-the-middle position on the victim's network. This one
  should stay unreachable on principle, not just on capability.

**Reachable today, and this is the larger half.** Everything in entries 1-10 and
12-14 above is URL-level, header-value-level or body-level and survives
re-serialisation intact: cache key construction, path confusion, delimiters and
encodings, static-extension and static-directory rules, unkeyed request headers,
framework-internal headers, `Vary`, `Age`, `ETag`, duplicate JSON keys, `Origin`
variants, cookie attributes, and error bodies. Two carry a caveat worth verifying
against the proxy before a Playbook depends on them: (a) the `Cookie` header - the
`$Version` techniques need the header to arrive byte-identical, including quotes
and ordering, and a re-serialising proxy may normalise or re-order pairs; (b)
oversized headers - CPDoS HHO turns on the *edge's* limit, and the proxy imposes
its own limit first, so an unreachable-by-us 431 may be the proxy's.

**Minimum harness change, if raw framing is ever wanted.** The pattern already
exists and was built for exactly this shape of problem: `transport_measurement`.
The minimum change mirrors it.

1. A third `receipts.purpose` value - call it `raw_framing_probe` - written only
   by the runtime, taken through the same scope decision, the same per-target
   concurrency slot and the same token bucket as agent traffic, exactly as
   ticket 93 did for the measurement lane. It is a purpose, not a second egress
   path, so the one-egress-path rule survives: what changes is who writes the
   bytes onto the socket.
2. New wire-side receipt columns and a generated citability column beside
   `transport_citable` - `framing_citable` - conjoining
   `purpose = 'raw_framing_probe' AND intercepted = false AND decision = 'allowed'`
   with the probe-specific facts: the exact bytes sent (hash plus a stored blob),
   the exact bytes received, the connection identity, and - the load-bearing one -
   **whether the probe's own second request on the same connection received a
   response the first request's framing explains**. Nobody may write that flag;
   the database computes it, as with `transport_citable`.
3. A `transport_makeability` row change: `transport.request_framing` moves from
   `unmakeable` to `probe_only`, with `allowed_fields` naming exactly the columns
   above and a `reason` that says a framing claim is admissible only from a raw
   probe receipt. `transport_claim_guard()` then does the enforcement for free.
4. A false-positive gate baked into the receipt, not into prose. SquidSec's
   November 2025 post is the reason: the overwhelming majority of desync reports
   are HTTP/1.1 pipelining misread as desync. The distinguishing observation is
   that the effect must appear on a connection the prober did **not** open. So the
   probe class must be two-connection by construction - connection A is
   desynchronised, connection B is the prober's own second socket, and the receipt
   records whether B (not A) received the injected effect. A one-connection probe
   is a pipelining receipt and must be non-citable by the generated column.
5. A containment rule with no exception: the probe may only poison a connection
   whose *next* consumer is the probe itself. That means the probe must be able to
   tear the socket down, and the receipt must record the teardown, because a
   desynchronised socket left in a shared front-end pool is the thing
   `http-desync` step 6 correctly refuses - "the next connection belongs to
   somebody who is not part of this engagement". No cache-key trick makes that
   safe, unlike the web-cache case. In practice this restricts the lane to
   detection primitives that terminate in a timeout or a `400` on the prober's own
   socket, and puts the confirming exploit outside the harness, with an operator.
6. For HTTP/2-specific classes, a second capability on the same lane: a raw HTTP/2
   client that can emit pseudo-headers and header values the proxy would reject.
   For HTTP/3, a QUIC egress - which is a much larger change and, given that
   `transport.datagram_transport` is `unmakeable` for the same reason, probably
   not worth it before the H1 and H2 lanes exist.

A cheaper intermediate step, and the one I would take first: keep the refusal and
build entry 11 - the exposure-surface reading. It needs no new lane, it costs four
requests, and it converts `http-desync` from a Playbook that measures TLS into one
that tells an operator whether this target is in the population that Kettle,
Bugcrowd and Assured were paid $350,000-plus against in 2024-2025.

## Sources consulted

* https://portswigger.net/research/http1-must-die - James Kettle, 2025-08-06,
  updated 2025-10-17. Primary source for 0.CL, double-desync, the four Expect
  variants, V-H/H-V header masking, H2.0 and H2.TE, early-response gadgets,
  CVE-2025-32094, HTTP Request Smuggler v3.0, and the affected-vendor list.
* https://portswigger.net/blog/http-1-1-must-die-what-this-means-for-in-house-pentesters
  - PortSwigger, 2025-08-06. Practitioner guidance: map the proxy chain, detect
  parsing discrepancies rather than surface defences, plan upstream HTTP/2.
* https://i.blackhat.com/BH-USA-25/Presentations/US-25-Kettle-HTTP1-Must-Die-The-Desync-Endgame-wp.pdf
  - Black Hat USA 2025 whitepaper for the same work. Appeared in search results;
  **not fetched**, nothing is asserted from it beyond its existence.
* https://portswigger.net/research/top-10-web-hacking-techniques-of-2025 -
  2026-02-05. The ranked 2025 list; source for Successful Errors (1st), Unicode
  normalization (4th), ETag length leak (6th), the Next.js stale elixir (7th),
  HTTP/2 CONNECT (9th) and parser differentials (10th), plus the honourable
  mention of malformed-chunk desync work.
* https://portswigger.net/research/top-10-web-hacking-techniques-of-2025-nominations-open
  - nominations list. The single highest-density source in this review: gave me
  funky chunks, the single-packet shovel, CL.0-for-C2, Opossum, Go parser
  footguns, syntax confusion, QuicDraw H3 and the CSWSH entry with URLs.
* https://portswigger.net/research/top-10-web-hacking-techniques-of-2024 -
  2025-02-04. Confusion Attacks (1st), TE.0 (3rd), WorstFit (4th), wildcard web
  cache deception on ChatGPT (9th), cookie tossing (10th), and the "Gotta cache
  'em all" honourable mention.
* https://portswigger.net/research/top-10-web-hacking-techniques-of-2023 -
  2024-02-19. PHP filter chain error oracle (4th), HTTP parser inconsistencies
  (5th), request splitting (6th), Cookie Crumbles (9th).
* https://portswigger.net/research/gotta-cache-em-all - Martin Doyhenard,
  2024-08-08, updated 2026-01-08. The cache-exploitation taxonomy: delimiters,
  normalization, static extensions, static directories, static files, key
  normalization, Cache-What-Where; and the cache-buster safety practice.
* https://portswigger.net/web-security/web-cache-deception - Web Security Academy,
  living page. The four detection primitives (path mapping, delimiter, delimiter
  decoding, normalization discrepancies) and how to confirm a hit.
* https://portswigger.net/web-security/web-cache-poisoning - Web Security Academy,
  living page. The unkeyed-input class list and the explicit instruction to add a
  cache buster when testing live sites.
* https://nokline.github.io/bugbounty/2024/02/04/ChatGPT-ATO.html - 2024-02-04.
  A disclosed bounty write-up: `%2F..%2F` decoded by the origin and not by
  Cloudflare, confirmed via `Cf-Cache-Status: HIT`, ending in account takeover.
* https://arxiv.org/abs/2407.16303 - Golinelli and Crispo, RAID 2024. Hidden
  caches on 5.8% of the top 50k, timing-pair detection at 89.6% agreement with
  header-based detection, 1,020 sites vulnerable to deception behind them.
* https://cpdos.org/ - Nguyen, Lo Iacono, Federrath; ACM CCS 2019. CPDoS and its
  three variants (HHO, HMC, HMO) and the affected CDN list. Older, still landing.
* https://blog.orange.tw/posts/2024-08-confusion-attacks-en/ - Orange Tsai,
  2024-08-09. Filename / DocumentRoot / handler confusion in Apache httpd, the
  `%3F` truncation primitive, nine CVEs fixed in 2.4.60 (2024-07-01).
* https://blog.orange.tw/ - index, checked for anything newer on parsers and
  proxies. Most recent relevant posts are WorstFit (2025-01-10) and Confusion
  Attacks (2024-08-09).
* https://zhero-web-sec.github.io/research-and-things/ - index of Rachid Allam's
  framework research, used to enumerate the Next.js cache series.
* https://zhero-web-sec.github.io/research-and-things/nextjs-cache-and-chains-the-stale-elixir
  - January 2025, CVE-2024-46982. `x-now-route-matches`, `__nextDataReq`,
  `x-nextjs-data`, SSR misclassified as SSG, stale-while-revalidate persistence.
* https://zhero-web-sec.github.io/research-and-things/nextjs-and-cache-poisoning-a-quest-for-the-black-hole
  - June 2024, CVE-2023-46298. `x-middleware-prefetch`, `Rsc: 1` with `_rsc`,
  `x-invoke-status` / `x-invoke-error`.
* https://zhero-web-sec.github.io/research-and-things/nextjs-cache-poisoning-to-dos-via-a-204-response
  - July 2025, CVE-2025-49826. A cached 204 as denial of service.
* https://zhero-web-sec.github.io/research-and-things/nextjs-and-the-corrupt-middleware
  - 2025-03-21, CVE-2025-29927. `x-middleware-subrequest` as an edge-auth bypass;
  read as context for `deployment`'s `authorization.edge_rule`.
* https://portswigger.net/research/stealing-httponly-cookies-with-the-cookie-sandwich-technique
  - Zakhar Fedotkin, 2025-01-22. `$Version` legacy parsing, quoted-value
  swallowing, Tomcat 8.5.x/9.0.x/10.0.x.
* https://portswigger.net/research/bypassing-wafs-with-the-phantom-version-cookie
  - Fedotkin, 2024-12-04. Quoted-string and octal encoding, cookie splitting,
  `$Path`/`$Domain` injection; AWS WAF bypass.
* https://portswigger.net/research/cookie-chaos-how-to-bypass-host-and-secure-cookie-prefixes
  - Fedotkin, 2025-09-03. Unicode-whitespace prefix bypass and legacy-parsing
  `__Host-` forgery; Django and ASP.NET normalisation, Java servers.
* https://labs.snyk.io/resources/hijacking-oauth-flows-via-cookie-tossing/ -
  Elliot Ward, 2024-11-26. Cookie tossing mechanics, path-specificity ordering,
  why SameSite does not help, and the `__Host-` mitigation.
* https://portswigger.net/research/browser-powered-desync-attacks - James Kettle,
  2022-08-10. Client-side desync and the CL.0 primitive. Older; still the basis
  of the 2024-2025 CL.0/0.CL family.
* https://www.bugcrowd.com/blog/unveiling-te-0-http-request-smuggling-discovering-a-critical-vulnerability-in-thousands-of-google-cloud-websites/
  - Arnolfo, Gregorio, @_medusa_1_, 2024-07-17. TE.0, the OPTIONS-based payload
  shape, Google Cloud Load Balancer, Identity-Aware Proxy bypass.
* https://w4ke.info/2025/06/18/funky-chunks.html - Jeppe Bonde Weikop,
  2025-06-18. TERM.EXT / EXT.TERM / TERM.SPILL / SPILL.TERM and the affected
  proxy and server lists; timeout-based black-box detection.
* https://w4ke.info/2025/10/29/funky-chunks-2.html - 2025-10-29 addendum. Listed
  in the PortSwigger nominations page; **not fetched**.
* https://www.assured.se/posts/the-single-packet-shovel-desync-powered-request-tunnelling
  - Thomas Stacey, 2025-05-12. Request tunnelling via H2-to-H1 downgrade,
  parallelised to ~80% reliability; AWS ALB and Azure Front Door fixes.
* https://blog.flomb.net/posts/http2connect/ - flomb, 2025-09-15. HTTP/2 CONNECT
  stream multiplexing as an internal port scanner; Envoy and Apache httpd.
* https://blog.cloudflare.com/resolving-a-request-smuggling-vulnerability-in-pingora/
  - Cloudflare, 2025-05-22. Vendor account of CVE-2025-4366: on a cache hit,
  Pingora did not consume the unread request body before connection reuse.
  Reported by James Kettle and Wannes Verwimp through the bounty programme;
  22-hour mitigation, patch on 2025-04-19.
* https://github.com/cloudflare/pingora/security/advisories/GHSA-hj7x-879w-vrp7
  and https://blog.cloudflare.com/pingora-oss-smuggling-vulnerabilities/ - both
  appeared in search results as further Pingora smuggling material; **not
  fetched**.
* https://squidhacker.com/2025/11/http-request-smuggling-in-2025-how-to-distinguish-real-desync-vulnerabilities-from-http-request-pipelining-and-stop-wasting-everyones-time/
  - Anthony Russell, 2025-11-15. The pipelining-versus-desync false-positive
  problem and the dual-connection proof requirement. Directly shaped the
  raw-lane citability design above.
* https://portswigger.net/research/listen-to-the-whispers-web-timing-attacks-that-actually-work
  - James Kettle, 2024-08-07. Ping-frame-synchronised single-packet timing,
  scoped SSRF via DNS timing and the 64-octet label, response-order bias for
  blind injection, reverse-proxy misrouting at scale, Param Miner timing support.
* https://blog.trailofbits.com/2025/06/17/unexpected-security-footguns-in-gos-parsers/
  - Vasco Franco, 2025-06-17. Go JSON case-insensitive key matching, duplicate
  key resolution, silently ignored unknown fields, XML garbage tolerance; ties to
  CVE-2020-16250 and CVE-2017-12635.
* https://www.yeswehack.com/learn-bug-bounty/syntax-confusion-ambiguous-parsing-exploits
  - Alex Brumen, 2025-10-17. Syntax confusion as a general frame; port
  normalization, `filename` vs `filename*`, `file://` host handling.
* https://blog.arkark.dev/2025/12/26/etag-length-leak - Takeshi Kaneko,
  2025-12-26. ETag length as a cross-site size oracle read through a 431 and
  Chromium history handling.
* https://www.synacktiv.com/publications/php-filter-chains-file-read-from-error-based-oracle
  - Rémi Matasse, 2023-03-21. The error-based oracle construction. Older; still
  the reference for turning an error into a read channel.
* https://github.com/vladko312/Research_Successful_Errors - Vladislav Korchagin,
  whitepaper v1.1 last modified 2026-02-22. Error-Based and Boolean Error-Based
  Blind code injection and SSTI across six languages; SSTImap 1.3.0+.
* https://opossum-attack.com/ - Merget, Erinola, Maehren, Knittel, Hebrok,
  Brinkmann, Somorovsky, Schwenk, 2025. Cross-protocol TLS desync; CVE-2025-49812
  for the Apache Foundation.
* https://r3verii.github.io/cve/2026/04/14/haproxy-h3-standalone-fin-smuggling.html
  - 2026-04-14. HTTP/3-to-HTTP/1 desync via a zero-payload QUIC STREAM frame with
  FIN; CVE-2026-33555. Single-researcher blog; the linked HAProxy fix commit and
  NVD record were **not fetched**, so the version list is unconfirmed here.
* https://www.usenix.org/conference/usenixsecurity22/presentation/mirheidari and
  https://www.usenix.org/system/files/sec22-mirheidari.pdf - the web cache
  deception measurement work. **Both returned HTTP 403 and could not be fetched**;
  nothing in this document is asserted from them.
* https://www.cyberark.com/resources/threat-research-blog/racing-and-fuzzing-http-3-open-sourcing-quicdraw
  and https://blog.malicious.group/the-quiet-side-channel-smuggling-with-cl-0-for-c2/
  - both returned cross-host redirects that were not followed; listed in the
  PortSwigger 2025 nominations page as HTTP/3 race fuzzing and CL.0 cached-redirect
  poisoning respectively. **Not fetched**; named only for completeness.
