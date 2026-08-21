# 01 - Recon, API and protocol surface

Scope: `attack-surface`, `api`, `routing`, `deployment`, `cms`,
`information-disclosure`, `external-resources`, `grpc`, `graphql`, `realtime`,
`webhooks`. Written 2026-08-21 against the eleven `playbook.md` files as they
stand on this branch, and against web research done the same day.

Framing: everything below is for an authorized engagement, inside a Program's
declared scope, under this harness's own risk floors. Nothing here proposes
acting against a third party who has not agreed to be tested.

Two things are stated once and then assumed:

* **Verification.** Every URL in this file was fetched during this research
  pass, either by me directly or by a research subagent that reported the fetch.
  Where a page could not be retrieved, or where a claim survives only as a
  search-result listing, it is marked `[unverified]` inline and the finding does
  not rest on it. No URL, CVE, tool name or attribution here was written from
  memory.
* **Harness constraints.** Four of them shape every proposal, and they were read
  out of this repository rather than assumed:
  - `mcp__rk2__http_request` takes **method, url and headers only**. There is no
    body argument -- `roster.py` declares the contract and says so explicitly
    ("No body and no identity. Both were declared here and neither was ever
    reachable"). Header names must match `^[A-Za-z][A-Za-z0-9-]{0,63}\Z` and
    values `^[\x20-\x7e]{0,1024}\Z`, so a CR or LF in a header value is refused
    at the door.
  - The browser lane runs a **closed set of actions** (`navigate`, `wait_for`,
    `fill`, `inject`, `click`, `assert_text`, `assert_absent`, `probe`,
    `capture_dom`, `screenshot`) and a **closed set of probes** -- the migrations
    ship exactly one, `markup_injection`. A plan names a probe; it never supplies
    JavaScript.
  - Offline tools are the enum `jq`, `js_map`, `js_parse`, `js_routes`, plus
    registered Skill scripts such as `extract_paths.py`.
  - Every ordinary request is decoded and re-encoded by the interception proxy.
    `http-desync/playbook.md` records this and 025's refusal of request-framing
    claims. Anything whose primitive is byte-level framing is unusable here by
    design, and is flagged rather than proposed.

---

## What we already cover well

**The evidence contract is stronger than the field's.** Every Playbook in this
cluster names a control, a variant, a refuting outcome and an explicit
inconclusive bucket. Published bug-bounty methodology almost never does this;
the disclosed-report corpus is full of "the endpoint returned 200" claims that
this harness would refuse. `attack-surface` step 1 (request a path nobody
deployed, before any candidate) and `deployment` step 4 (apply the same
transformation to an unrestricted path) are both controls that most public
methodology omits, and both are the difference between a finding and a
catch-all route.

**Digest-differencing instead of body-reading.** `attack-surface` step 4 compares
stored Artifact digests rather than prose. `information-disclosure` takes both
directions of a set difference and treats "declared but missing" as the control
that proves the comparison is pointed at the right route. This is a genuinely
better discipline than the field's, and it is why our undeclared-field reading
will not report `_links` as a leak.

**Two-Identity differentials.** `graphql`, `grpc`, `cms` and `browser-realtime`
all hold everything fixed but the session, and all four require a control
showing the second credential works on its own surface. That control is exactly
what separates an authorization finding from an expired lease, and it is the
single most common defect in public GraphQL and gRPC writeups.

**Refusals that are correct and worth keeping.** Not registering an unclaimed
domain/bucket/package (`external-resources` step 5) is the right call and is
better than most published broken-link-hijacking advice. Not desynchronising
(`deployment` step 7) is correct given the proxy. Not claiming a CMS version as
a finding (`cms` step 7) is correct: a fingerprint is a hypothesis. Not
harvesting the contents of undeclared fields (`information-disclosure` step 7)
is the right report ethic.

**Bounded budgets.** Eight requests for `deployment`, eight for `cms`, three for
`information-disclosure`, twelve for `api`. Programs withdraw access over
unbounded sequences far more often than they do over any single technique.

**Surface vocabulary that already anticipates the modern stack.** The
`bb:triggers_all` vocabulary already carries `tech_edge_proxy`, `tech_cdn`,
`spa_surface`, `tech_build_manifest`, `graphql_surface`, `websocket_surface`,
`tech_grpc`, `tech_openapi`. The preconditions for most of what follows already
exist; the readings that consume them do not.

---

## Missing techniques (ranked by expected yield on a real bounty program)

Ranking weighs three things: how often the technique is landing in 2024-2026
disclosures, how much of it this harness can actually observe today, and how
close it is to a Playbook we already ship.

### 1. Framework internal-trust headers (`x-middleware-subrequest`, `x-now-route-matches`, `x-middleware-prefetch`, `x-forwarded-*` URL reconstruction)

Modern meta-frameworks route on headers they assume only their own edge sets.
Next.js used `x-middleware-subrequest` as a recursion guard, so sending it
externally skipped middleware entirely -- and middleware is where teams put
authn, authz, path rewrites, CSP and draft-mode gating (CVE-2025-29927; values
are `pages/_middleware` for 11.1.4-12.0.7, `middleware` or `src/middleware` for
12.2+, and `middleware:middleware:middleware:middleware:middleware` on later
15.x). `x-now-route-matches` makes Next.js misclassify an SSR response as SSG so
its `Cache-Control` flips to `s-maxage=1, stale-while-revalidate`
(CVE-2024-46982, Next.js 13.5.1-14.2.9, pages router). `x-middleware-prefetch`
returned an empty `{}` that a CDN would cache (CVE-2023-46298). Astro's Node
adapter rebuilt the request URL from `x-forwarded-proto` and `x-forwarded-port`,
so `x-forwarded-proto: x` produced a `pathname` with no leading slash and
`context.url.pathname === "/admin"` stopped matching (CVE-2025-64525); the
earlier host allowlist fell to an **empty** `x-forwarded-host`.

This is number one because it is the only high-yield family in this whole
document that our door can send **unmodified**: it is a header name and a
printable-ASCII value on a GET. No body, no framing, no browser.

Belongs in: `deployment` (as a second arm beside path spellings) and `routing`.
Arguably a new Playbook: **new playbook: `edge-trust-header`**, output
`authorization.edge_rule`.

We would have to observe: the header echoed or its effect visible in the answer
-- a status the baseline did not have, a `Cache-Control` that changed direction,
an application body where the baseline had a refusal, a `pathname`-dependent
route reached. All of that is already `response_differential` over two stored
Artifacts. We need the surface fact `tech_edge_proxy` or a framework
fingerprint, and we need the Playbook to be allowed to send a header the surface
did not record.

Sources:
- https://zhero-web-sec.github.io/research-and-things/nextjs-and-the-corrupt-middleware (March 2025, Rachid Allam and Yasser Allam, CVE-2025-29927)
- https://zhero-web-sec.github.io/research-and-things/nextjs-cache-and-chains-the-stale-elixir (January 2025, Rachid Allam, CVE-2024-46982)
- https://zhero-web-sec.github.io/research-and-things/nextjs-and-cache-poisoning-a-quest-for-the-black-hole (June 2024, CVE-2023-46298)
- https://zhero-web-sec.github.io/research-and-things/astro-framework-and-standards-weaponization (November 2025, CVE-2025-64525, bypass of CVE-2025-61925)
- https://vercel.com/blog/postmortem-on-next-js-middleware-bypass (date not shown on page; internal timeline 27 Feb / 18 Mar / 21 Mar 2025)

### 2. Double-decoding across a proxy hop (the modern 403 bypass)

Our `deployment` Playbook's five spellings -- dot segment, doubled separator,
trailing dot/space, one percent-encoded separator, matrix parameter -- are the
2019 list. The spelling that lands in 2025 is **double** encoding, because the
front end decodes once and the origin decodes again. PAN-OS CVE-2025-0108 is the
canonical shape: nginx sees `/unauth/%2e%2e/php/ztp_gate.php/PAN_help/x.css`
(no traversal, so `X-pan-AuthCheck: off`), Apache re-normalises and its
rewrite-driven internal redirect decodes a second time into `/php/ztp_gate.php`,
executed unauthenticated. The trailing fake static extension is there to satisfy
the outer rule, which our list does not contain either. Orange Tsai's Apache
work is the same class one layer down: `%3F` truncates the filesystem path after
rewriting, and `admin.php%3Fooo.php` walks past a `<Files>` directive because
`mod_authz` reads `r->filename` as a path and `mod_proxy` reads it as a URL.

Belongs in: `deployment`, step 3's spelling list.

We would have to observe: nothing new. It is one more arm in the existing
eight-request budget, and step 4's control on an unrestricted path already tells
us whether the deployment mangles the transformation everywhere.

Sources:
- https://slcyber.io/research-center/nginx-apache-path-confusion-to-auth-bypass-in-pan-os-cve-2025-0108/ (12 February 2025, Searchlight Cyber)
- https://blog.orange.tw/posts/2024-08-confusion-attacks-en/ (9 August 2024, Orange Tsai; CVE-2024-38472/38473/38474/38475/38476/38477, CVE-2024-39573, CVE-2023-38709)
- https://www.yeswehack.com/learn-bug-bounty/syntax-confusion-ambiguous-parsing-exploits (17 October 2025)

### 3. Grounded route inventory from the client bundle, then an unauthenticated replay sweep

The highest-volume API finding in 2025-2026 is not a clever payload, it is an
endpoint nobody linked. Two sources feed it. Source maps: `.map` files carry a
`sourcesContent` array holding the verbatim original files, so recovery is
decompression rather than reverse engineering, and the recovered tree names
handlers the UI never reaches (the Sentry writeup chains a recovered
`updateUserData` to `/user/update-user-data` to pre-auth password change).
Bundles without maps still yield call sites. Then the actual finding: replay
every discovered operation **with no credential** and see which ones answer.
Intruder's Autoswagger does exactly this against leaked OpenAPI documents and
reports a Microsoft MPN config endpoint leaking production DB credentials,
60,000+ Salesforce records by parameter iteration, and an unauthenticated
SQL-execution endpoint. That is API5:2023 and API1:2023 read straight off a
document the target published.

This harness is unusually well placed here and is not using it. `jsscan.py`
already ships `js_parse`, `js_routes` and `js_map`, and `analyse-source` already
insists a route is grounded in a tool run with its call site. But
`analyse-source` is loaded only by `external-resources` and `supply-chain`, and
its step 4 stops before reachability by design -- so nothing in this cluster
turns a grounded route into a request.

Belongs in: `attack-surface` step 2 (candidates come from `js_routes` output,
not from a model's reading), plus **new playbook: `undocumented-endpoint`**,
output `authorization.function_access`, whose whole subject is "a grounded route
the surface holds, asked with nothing presented".

We would have to observe: the bundle stored as an Artifact (already), a
`js_routes`/`js_map` tool run (already), and then a GET per grounded route
against the same "nothing here" control `attack-surface` step 1 already builds.
Most of the operations Autoswagger replays are POSTs with bodies, which our door
cannot send -- so the reachable half today is the GET half, and the Playbook
should say so rather than pretend otherwise.

Sources:
- https://blog.sentry.security/abusing-exposed-sourcemaps/ (31 January 2025; names `unwebpack-sourcemap` and `sourcemapper`)
- https://brackish.io/2024/07/03/javascript-source-map-vulnerabilities/ (3 July 2024; names https://github.com/denandz/sourcemapper)
- https://www.intruder.io/research/broken-authorization-apis-autoswagger (22 July 2025, Daniel Andrew; tool at https://github.com/intruder-io/autoswagger/; names CVE-2025-0589)
- https://www.assetnote.io/resources/research/contextual-content-discovery-youve-forgotten-about-the-api-endpoints `[unverified]` -- 301-redirects to https://slcyber.io/assetnote and the body could not be retrieved. The contextual-discovery principle is cited from the Intigriti and YesWeHack pieces instead.
- https://www.intigriti.com/researchers/blog/hacking-tools/testing-javascript-files-for-bug-bounty-hunters (19 December 2024, updated 8 August 2026)
- https://www.yeswehack.com/learn-bug-bounty/discover-map-hidden-endpoints-parameters (9 January 2025)

### 4. GraphQL batching and aliasing as a rate-limit and brute-force primitive

Our `graphql` Playbook explicitly hands this away: "Batching and aliasing are
likewise a different question -- how much one request can cost is
`rate_limiting.resource_cost`, and this Playbook may not claim it." The problem
is that **no Playbook in the repository outputs `rate_limiting.resource_cost`**,
even though `src/redkraken/fixtures/resource-cost-pair/` exists and its own
description names "the batched-operation abuse pattern that recurs across public
disclosures of GraphQL and JSON batch APIs". The same is true of
`rate_limiting.per_origin`: fixture present, Playbook absent, and our `api`
Playbook names the gap in step 5 and then stops.

Why it lands: aliases let one HTTP message carry dozens of independent
executions, so any limiter counting HTTP requests counts one. OWASP's cheat
sheet calls batching "a form of brute force attack, specific to GraphQL, that
usually allows for faster and less detectable exploits" and lists OTP/token
brute force, object enumeration and WAF evasion as consequences. This is also
not GraphQL-only any more: WordPress core ships `/wp-json/batch/v1` (see 8),
and Directus had an unauthenticated GraphQL alias-amplification DoS
`[unverified: GHSA-6q22-g298-grjh, seen in listing only]`.

Belongs in: **new playbook: `batched-cost`**, output
`rate_limiting.resource_cost`, sibling to `api`.

We would have to observe: a request whose single message asks for N units of
work, and an answer that shows the server did all N. That needs a **body**, and
our door has none. Today the only reachable form is a GET-based GraphQL endpoint
with the document in the query string, or a REST batch route whose operations
are query parameters. This is the clearest case in the whole document where a
harness capability -- a bodied request through the scope proxy -- is the
blocker, not the Playbook text.

Sources:
- https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html (OWASP Cheat Sheet Series, living document)
- https://portswigger.net/web-security/graphql (PortSwigger Web Security Academy, living document)

### 5. GraphQL schema recovery without introspection, and introspection-filter bypasses

Disabling introspection is the near-universal "fix", and it does not work. Field
suggestions ("There is no entry for 'productInfo'. Did you mean
'productInformation' instead?") let a dictionary-driven prober reconstruct the
reachable schema; Clairvoyance is the named tool. Separately, introspection
filters are usually regexes on `__schema{`, so inserting a newline or other
character after `__schema` gets past them, and introspection is often disabled
only for `POST application/json` while a GET or an
`application/x-www-form-urlencoded` POST still answers. A recovered schema is a
complete resolver inventory, which is the shortest path to per-field
authorization drift -- and per-field drift is exactly the class our `graphql`
Playbook already claims.

Our Playbook currently says "Introspection is not this claim... record it as
surface". That is the right verdict and the wrong stopping point: it records
introspection when it answers and has nothing to say when it does not.

Belongs in: `graphql`, as a surface-establishing step feeding
`information_disclosure.excess_field`, or a companion reading that outputs
surface facts only.

We would have to observe: an error body carrying a suggestion, matched against
the name that was asked for. That is a `content_match` over a stored Artifact
and `jq` can select it. A GET-shaped introspection probe is sendable through our
door today; the POST forms are not.

Sources:
- https://portswigger.net/web-security/graphql (names Clairvoyance and the special-character bypass verbatim)
- https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html
- https://github.com/nikitastupin/clairvoyance `[unverified: appeared in search listings, page not fetched]`

### 6. GraphQL-over-WebSocket subscription authentication bypass

Two 2026 advisories describe the same shape from opposite ends and neither is
covered by `realtime` or `browser-realtime`. Strawberry GraphQL supported both
`graphql-transport-ws` and the legacy `graphql-ws` subprotocol; the legacy
handler did not verify that `connection_init` had completed before processing
`start`, so a client selecting the legacy subprotocol via `Sec-WebSocket-Protocol`
and sending `start` immediately skipped the `on_ws_connect` authentication hook
entirely (CVE-2026-35523, <= 0.312.2, fixed 0.312.3; both subprotocols enabled by
default). `@neo4j/graphql` accepted a **pre-decoded** JWT object in subscription
`connectionParams` and never verified the signature, so any unauthenticated
client could forge `sub` and `roles` (CVE-2026-5423, published 6 August 2026).

Generalised: on any GraphQL-over-WS endpoint, the subprotocol is caller-chosen
and the two handlers are two state machines; and `connectionParams` is a
free-form JSON blob that frameworks routinely push straight into the auth
context.

Belongs in: `realtime` (the handshake half -- subprotocol selection is a
handshake variable our Playbook currently holds fixed) and `browser-realtime`
(the message half).

We would have to observe: two handshakes differing only in
`Sec-WebSocket-Protocol`, and then a message sent before `connection_init`.
The first half is a header on an upgrade request. The second half needs the
ability to **send a frame on an open socket**, which the harness does not have:
`browser_driver.py` has a hand-framed RFC 6455 client, but it is the CDP
transport, not a mission action, and no browser action or probe sends an
application message.

Sources:
- https://github.com/strawberry-graphql/strawberry/security/advisories/GHSA-vpwc-v33q-mq89 (published 4 April 2026, CVE-2026-35523)
- https://github.com/neo4j/graphql/security/advisories/GHSA-fcpg-3fw5-vc65 (published 6 August 2026, CVE-2026-5423)

### 7. Webhook SSRF: making the blind case visible, and beating the allowlist

Our `webhooks` Playbook is honest that no arrival inside the window is not a
refutation. The field has moved past that. Two techniques matter.

**Redirect-loop status cycling** turns a blind SSRF into a full read. A server
that follows redirects and only fails on JSON parsing can be pushed into an
unhandled error state by exceeding the redirect limit with progressively higher
3xx codes (301, 302, ... 310), at which point it echoes the whole buffered
response chain -- including the final 200 from a metadata endpoint that would
otherwise leak nothing. PortSwigger ranked it #3 for 2025.

**DNS-rebinding TOCTOU** beats the standard allowlist: the validator resolves
the hostname, checks the IPs are public, throws them away, and hands the
*hostname* to the HTTP client, which resolves again. An attacker-controlled
nameserver with TTL 0 answers public for the check and internal for the fetch.
The correct fix is `getpeername()` after connect, which almost nothing ships.

Belongs in: `webhooks` (step 3's window, and a second arm), and `ssrf-url-routing`.

We would have to observe: an arrival on our own declared channel is already
`callback_interaction` and `callback.py` already mints correlators as
`<correlator>.<endpoint>` (DNS) or `https://<endpoint>/<correlator>/` (path).
The redirect-loop arm additionally needs the correlator host to **answer with a
controlled redirect chain**, which is a channel capability we do not have --
today the channel records arrivals, it does not respond. The rebinding arm needs
a TTL-0 authoritative record, same story. Both are runtime features, not
Playbook prose, and the Playbook should name what it cannot do.

Sources:
- https://slcyber.io/research-center/novel-ssrf-technique-involving-http-redirect-loops/ (23 June 2025, Shubham Shah, Searchlight Cyber)
- https://portswigger.net/research/top-10-web-hacking-techniques-of-2025 (published 5 February 2026; the redirect-loop technique at #3)
- https://github.com/mlflow/mlflow/issues/24179 (reported 26 June 2026; `_validate_webhook_url()` resolves then discards, delivery re-resolves)
- https://portswigger.net/web-security/ssrf/url-validation-bypass-cheat-sheet ("2024 Edition"; fetched, but the page body renders as a payload-list stub)

### 8. The platform's batch and alternate-spelling routes (WordPress `/wp-json/batch/v1`, `?rest_route=`)

Our `cms` Playbook allows "at most five candidate route names, from that
platform's own conventions". The names that matter in 2026 are not the ones a
2019 wordlist holds. WordPress core ships a batch endpoint reachable as
`/wp-json/batch/v1` **and** as `?rest_route=/batch/v1` -- two spellings of the
same route, which is simultaneously a parallel-route question (`cms`) and an
edge-rule question (`deployment`), because a WAF rule written against
`/wp-json/` does not see `?rest_route=`. Searchlight Cyber's July 2026
pre-auth RCE in WordPress core is at that endpoint (WordPress 6.9.0-6.9.4 and
7.0.0-7.0.1, fixed 7.0.2 / 6.9.5; the researchers withheld exploit detail and
published a checker). Separately `/wp-json/wp/v2/users` still returns id,
display name and slug for every author to an unauthenticated caller by default,
with `?rest_route=/wp/v2/users`, `_embed` on posts, `/?author=1` and oEmbed as
fallbacks.

Belongs in: `cms`, step 1's five names and step 4's asking.

We would have to observe: nothing new. Two spellings of one platform route,
asked with nothing presented, compared against the application route's refusal
-- which is precisely the reading `cms` already performs. This is a content
change to the candidate list, not a mechanism change.

Sources:
- https://slcyber.io/research/wp2shell-pre-authentication-rce-in-wordpress-core (17 July 2026, Adam Kues, Searchlight Cyber; no CVE stated on the page)
- https://www.invicti.com/web-application-vulnerabilities/wordpress-rest-api-user-enumeration (page dates to the WordPress 4.7.1 era; the endpoint remains public by default)
- https://patchstack.com/whitepaper/state-of-wordpress-security-in-2025/ (14 March 2025: 7,966 new WordPress vulnerabilities in 2024, 96% in plugins, 33% not fixed before public disclosure)

### 9. Headless CMS as the CMS surface (Strapi, Directus), not WordPress/Drupal/Joomla

Our `cms` Playbook's three attached references are Drupal, Joomla and WordPress.
The platform mix a bounty program presents in 2026 is different, and the
headless products fail in ways the parallel-route framing already fits. Strapi's
public content API allowed filtering on relational fields including admin
relations, giving an unauthenticated one-bit boolean oracle against
`admin_users` that yields `resetPasswordToken` character by character
(`[unverified: CVE-2026-27886, CVSS 9.2, < 5.37.0 -- reported by a research
agent from vulert.com and securityonline.info, neither a primary vendor
advisory]`). Strapi also shipped, by default, a reflected `Origin` in
`Access-Control-Allow-Origin` beside `Access-Control-Allow-Credentials: true`
(CVE-2025-53092, published 16 October 2025, `@strapi/core` < 5.20.0). Directus
"Flows" with a manual trigger did not validate that the caller had permission to
the items in the payload, so unauthenticated callers could execute them
(CVE-2025-53889, published 15 July 2025, 9.12.0-11.8.x, fixed 11.9.0) -- and a
Directus Flow is itself a webhook/SSRF primitive once triggerable.

Belongs in: `cms` (candidate names, and the fingerprint set), and the Strapi
CORS case belongs in whichever Playbook holds `session_handling.cross_origin_read`.

We would have to observe: for the CORS default, one request carrying an `Origin`
header the target has never seen and a read of `Access-Control-Allow-Origin` and
`-Credentials` in the answer -- entirely within our door's capability, and it is
a `header_policy_observed` plus a `response_differential`. The Strapi filter
oracle needs query parameters only, so it is reachable; the iteration it implies
is not, and should not be.

Sources:
- https://www.wiz.io/vulnerability-database/cve/cve-2025-53092 (published 16 October 2025)
- https://www.miggo.io/vulnerability-database/cve/CVE-2025-53889 (published 15 July 2025, GHSA-7cvf-pxgp-42fc)
- https://vulert.com/vuln-db/CVE-2026-27886 `[unverified: secondary vulnerability-database source, no primary Strapi advisory retrieved]`
- https://securityonline.info/strapi-cms-vulnerabilities-cve-2026-27886-cve-2026-22599-admin-takeover-rce/ `[unverified: secondary source]`

### 10. gRPC server reflection, and the transcoded-vs-binary authorization differential

Our `grpc` Playbook reads `grpc-status` correctly, which is more than most
writeups manage, but it takes the method from the recorded surface and never
asks where the method list came from. Two things fill that gap. **Server
reflection**, when left enabled, hands an unauthenticated caller every service,
method and message type -- the gRPC analogue of introspection, and the fastest
route to the administrative methods no client calls, which is exactly the
population our `authorization.function_access` reading is about. **Transcoding**
is the authorization differential: when Envoy's `grpc_json_transcoder` sits
ahead of `ext_authz` in the filter chain, valid `<pkg>/<Service>` endpoints skip
the authz filter, so the same RPC is enforced over binary gRPC and unenforced
over the JSON/REST path. Related and adjacent: Envoy's `ext_authz` could be made
to emit an invalid gRPC request to the authz service, and with the very common
`failure_mode_allow: true` it then fails open (CVE-2024-23324, CVSS 7.5, fixed
1.29.1/1.28.1/1.27.3/1.26.7). And gRPC-Go accepted a `:path` without the leading
slash while authorization interceptors evaluated the non-canonical string, so
deny rules written canonically failed to match (CVE-2026-33186, published 17
March 2026, < 1.79.3, CVSS 9.1).

Belongs in: `grpc`.

We would have to observe: the transcoded arm is a plain HTTP request to a REST
path and is reachable **if** the method takes no body. The binary arm is not:
a gRPC unary call is a length-prefixed protobuf **body**, and our door sends no
body. The `:path` variant is worse -- an intercepting proxy that re-encodes will
canonicalise the pseudo-header, so CVE-2026-33186 is structurally unreachable
here, in the same family as the framing refusals. Reflection is also a bodied
call. The honest reading of our `grpc` Playbook today is that its step 3 and
step 4 describe requests the harness cannot send.

Sources:
- https://github.com/grpc/grpc-go/security/advisories/GHSA-p77j-4mvh-x3m3 (published 17 March 2026, CVE-2026-33186)
- https://explore.alas.aws.amazon.com/CVE-2024-23324.html (published 9 February 2024, Envoy `ext_authz` fail-open)
- https://github.com/envoyproxy/envoy/issues/9929 (reported 4 February 2020 against v1.13.0, closed stale; the primary artifact for the transcoder/ext_authz ordering trap -- older, still a live per-deployment misconfiguration)
- https://bhamza.me/blogpost/2024/03/04/Security-assessing-grpc-and-grpcweb-services.html (4 March 2024; gRPC-Web framing, `application/grpc-web-text`)
- https://blog.compass-security.com/2025/10/brpc-web-a-burp-suite-extension-for-grpc-web/ (21 October 2025; heuristic protobuf decoding without `.proto` files)

### 11. Protobuf without a schema: field-number confusion, deprecated-field mass assignment, unknown-field passthrough

Protobuf carries no type information on the wire, so a message can be decoded
and re-encoded keyed by **field number** with types inferred from wire types
(NCC Group's Blackbox Protobuf). That ambiguity -- varint covers int/uint/sint/
bool/enum, length-delimited covers string/bytes/embedded message/packed repeated
-- is the type-confusion primitive. Two consequences a bounty program pays for:
fields marked `[deprecated = true]` or dropped from the front end remain fully
wire-decodable and usually still bind server-side, which is mass assignment with
a schema-derived wordlist instead of guesses; and proto3 restored unknown-field
preservation in 3.5, so a gateway that unmarshals and re-marshals silently
forwards field numbers it does not know, letting a payload ride past a
validating edge into a backend whose schema does define them.

Belongs in: `grpc`, or **new playbook: `protobuf-shape`**, output
`injection.object_graph` (mass assignment) / `authorization.function_access`.

We would have to observe: a bodied request, and a registered protobuf
encode/decode tool. Neither exists. This is the highest-value gRPC content in
the document and the least reachable; it belongs on the capability roadmap, not
in a Playbook step that would be unrunnable.

Sources:
- https://github.com/nccgroup/blackboxprotobuf and https://github.com/nccgroup/blackboxprotobuf/blob/master/docs/TypeDefs.md (date not confirmed on the pages)
- https://kmcd.dev/posts/protobuf-unknown-fields/ (page indicates April 2026, originally March 2024)
- https://blogs.jsmon.sh/the-ultimate-guide-to-grpc-pentesting-breaking-binary-protocols/ (page states 13 May 2026; source of the "`[deprecated = true]` is not a security control" framing) `[lower-confidence source: an aggregator blog, not a primary researcher post]`

### 12. Webhook signature schemes: empty/default secrets, unsigned metadata, one key per tenant, replay windows

Our `webhooks` Playbook only asks whether the server fetches a URL. The other
half of webhook work is the **receiving** side, and it is a rich, currently
productive class. Svix's taxonomy of failure modes names the ones that are
exploitable rather than theoretical: **unsigned metadata** -- the timestamp and
message id travel outside the signed content, so a captured delivery replays
with a refreshed timestamp and a still-valid signature; **one key for all
destinations** -- a message signed for tenant A verifies for tenant B, which is
cross-tenant webhook forgery and is badly under-tested; ad-hoc
`hash(key + payload)` instead of HMAC, which is length-extension vulnerable;
and canonicalisation before verification, which is the raw-body-vs-parsed-body
mismatch that Express/FastAPI/Rails all invite. GitHub's own documentation
insists on `crypto.timingSafeEqual`/`secure_compare` and still ships legacy
`X-Hub-Signature` (HMAC-SHA1) beside `X-Hub-Signature-256`, so a receiver that
accepts whichever header is present is an algorithm-confusion target. And the
degenerate case is real: `new-api` defaulted its Stripe webhook secret to `""`
and the SDK verified against it (CVE-2026-41432, published 22 April 2026, CVSS
7.1, fixed 0.12.10).

Belongs in: **new playbook: `webhook-ingest`**, output `business_logic.replay`
and/or `authentication.credential_verification`.

We would have to observe: a POST **with a body** to the receiver's ingest route,
carrying a signature header we computed. The signature header is within our
header constraints; the body is not. Reachable today only where the ingest route
takes its payload in the query string, which is rare. Flag as capability-blocked.

Sources:
- https://www.svix.com/blog/common-failure-modes-for-webhook-signatures/ (date not shown on page)
- https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries (living document)
- https://hookdeck.com/webhooks/guides/webhook-security-vulnerabilities-guide (date not shown; confirms Stripe's 5-minute tolerance default and Shopify's `X-Shopify-Hmac-Sha256`)
- https://github.com/advisories/GHSA-xff3-5c9p-2mr4 (CVE-2026-41432, published 22 April 2026)

### 13. Outbound-webhook CRLF into custom header **names**

GitLab lets a user attach custom headers to outgoing webhooks and did not strip
`\r\n` from the header **name**, so a configured webhook serialises a second
complete HTTP request into the outbound stream. Because enterprises push
outbound webhook traffic through an inspecting forward proxy with pipelining,
the smuggled request is emitted as legitimate first-party traffic and reaches
internal services the webhook allowlist would have refused. Any product offering
"custom webhook headers" -- CI notifiers, Jira automation, low-code platforms --
has the same shape. PortSwigger's August 2026 work generalises the primitive:
CRLF injection reachable through a normalising intermediary becomes a desync.

Belongs in: `webhooks`, as an outbound-configuration arm.

We would have to observe: the header name field is application input, so this is
configured through the target's own UI or API, not through our door -- our door
refuses CR/LF in a header value by regex, and refuses non-alphanumeric header
names entirely. Testing it means driving the target's settings form, which is a
browser `fill` + `click`, and then reading whether the stored configuration
round-trips the injected bytes. That much is reachable. The consequence
(a smuggled request landing on a shared proxy) is squarely inside the
framing refusal and must **not** be pursued: the blast radius lands on
somebody else's connection.

Sources:
- https://gitlab.com/gitlab-org/gitlab/-/issues/550766 (reported 26 May 2025 via HackerOne report #3162711; confirmed on GitLab 18.0.1 and gitlab.com; no CVE stated on the page)
- https://portswigger.net/research/crlf-powered-desync-attacks (5 August 2026, Tom Stacey and Tobia Righi)

### 14. RSC / hydration payload as a second copy of server state

Next.js serialises every Client Component prop into the HTML as
`self.__next_f.push(...)` chunks so the page can hydrate -- including props the
component never renders. "We removed it from the UI" therefore does not remove
it from the wire. The documented case is doge.gov, where grant identifiers were
stripped from the visible page and recovered from the escaped JSON in the RSC
payload. The test is mechanical: grep the raw HTML for `__next_f`, unescape,
and diff against what the DOM shows; also check `.rsc` variants and `?_rsc=`
responses.

This is a very good fit for our `information-disclosure` Playbook's shape --
it is a set difference between two documents, in both directions -- and it needs
no OpenAPI document, which is currently a hard trigger (`tech_openapi`) that a
large fraction of real targets will not satisfy.

Belongs in: `information-disclosure`, as a second subject alongside the
contract-versus-response reading.

We would have to observe: one GET storing the HTML, one `capture_dom` browser
step storing the rendered DOM, and a `jq`/script comparison of the two name
sets. Both halves exist. The trigger would be `spa_surface` plus a framework
fingerprint rather than `tech_openapi`.

Sources:
- https://www.bswanson.dev/blog/nextjs-hydration-payload/ (23 March 2025)

### 15. Cache deception by delimiter and normalisation discrepancy

Older than three years as a concept, still landing hard. The cache and the
origin disagree about where the path ends: Spring treats `;` as a delimiter,
Rails treats `.`, OpenLiteSpeed treats a null byte, and a cache that does not
recognise the same character will store `/settings/users/list;aaa.js` under a
rule meant for static assets. Normalisation differs too -- CloudFront, Azure and
Imperva normalise before applying cache rules; Cloudflare does not. The
highest-profile instance is the ChatGPT account takeover: Cloudflare cached
everything under `/share/*` and did not decode `%2F..%2F`, while the origin did,
so `/share/%2F..%2Fapi/auth/session?cachebuster=123` was keyed as cacheable
share content and served the victim's session response.

Belongs in: `web-cache` primarily (outside this cluster), but `deployment` and
`routing` should both name the neighbour, because a tester who finds a delimiter
discrepancy while probing edge rules is one step from this class and our
`deployment` Playbook's "two neighbours are close" section already points at
`information_disclosure.cached_response`.

We would have to observe: `X-Cache`/`Age`/`CF-Cache-Status` on two requests and a
body that belongs to the other path. All within the door.

Sources:
- https://portswigger.net/research/gotta-cache-em-all (8 August 2024, Martin Doyhenard; updated 8 January 2026)
- https://portswigger.net/web-security/web-cache-deception (Web Security Academy, living document)
- https://nokline.github.io/bugbounty/2024/02/04/ChatGPT-ATO.html (4 February 2024, Harel; #9 in PortSwigger's Top 10 of 2024)

### 16. Shadow and zombie API versions, and `.well-known` as a deterministic seed

API9:2023 "Improper Inventory Management" is the OWASP category our cluster maps
to least well. Its own Scenario #1 is the pattern: `beta.api...` lacked the
rate limiting production had, enabling password-reset token brute force. The
practical reading is to replay the **same object identifier** across `/v1/`,
`/v2/` and any `beta.`/`staging.` sibling, because fixes land on the current
version only. Cheap deterministic seeds for the same question:
`/.well-known/openid-configuration` returns an authoritative enumeration of the
auth surface including issuer hostnames not otherwise discovered, and JAX-RS
stacks expose `application.wadl`, which Sam Curry's team used at BMW via
`/rest/api/application.wadl`.

Belongs in: `attack-surface` step 2 (candidate reasons), and `api` (a version
sibling is a second subject for the same identity).

We would have to observe: GETs and a digest comparison. Entirely reachable.
`/.well-known/openid-configuration` and `application.wadl` are two more
"candidates the surface implies", which is exactly the shape step 2 asks for.

Sources:
- https://owasp.org/API-Security/editions/2023/en/0xa9-improper-inventory-management/ (OWASP API Security Top 10 2023)
- https://samcurry.net/web-hackers-vs-the-auto-industry (3 January 2023; the `/rest/api/application.wadl` path is quoted in the post)

### 17. Cross-Site WebSocket Hijacking in 2026: the preconditions our Playbook does not check

Our `realtime` Playbook asks the right question and asserts the wrong world. It
opens the handshake "from a page served on a different origin" and reads
invariance as the finding -- but in a default Chrome or Edge today, a
`SameSite=Lax` session cookie is simply not attached to that cross-site
handshake, so the variant fails for a reason that has nothing to do with the
origin check, and our Playbook's own step 6 correctly calls that
`session_handling.cookie_scope` and then has nowhere to go. Include Security's
2025 reassessment is that CSWSH is browser-conditional: still exploitable in
default Chrome/Edge when the cookie is explicitly `SameSite=None` (common for
embedded apps, SSO flows and split API origins), and blocked by Firefox's Total
Cookie Protection and Safari's third-party cookie blocking regardless. And under
`SameSite=Strict`, an attacker holding any same-**site** subdomain can still
drive the handshake, because SameSite is site-scoped and not origin-scoped
(SysReptor, CVE-2024-36076: no `Origin` validation on upgrade, read/write access
to notes).

Belongs in: `realtime`.

We would have to observe: the session cookie's `SameSite` attribute, read before
the variant is sent, as a precondition rather than as an after-the-fact excuse.
That is a `Set-Cookie` on the baseline and it is already in a stored Artifact.
Serving a page from a second origin, which step 4 requires, is **not** something
this harness can do -- the browser lane navigates, it does not host.

Sources:
- https://blog.includesecurity.com/2025/04/cross-site-websocket-hijacking-exploitation-in-2025/ (17 April 2025) `[unverified: direct fetch returned HTTP 403 twice; content reported by a research agent via a text-extraction proxy of the same URL]`
- https://github.com/Syslifters/sysreptor/security/advisories/GHSA-2vfc-3h43-vghh (published 21 May 2024, CVE-2024-36076, CVSS 6.8, affected 2024.28-2024.30, fixed 2024.40)

### 18. Realtime transports below the SDK: raw Engine.IO, and pub/sub signing oracles

Two more realtime classes with no home in our cluster. A Socket.IO deployment
whose namespace middleware rejected every connection was still reachable by a
raw `ws` client at `/socket.io/?EIO=4&transport=websocket` -- the auth layer was
effective only against the official client, because the Engine.IO transport
establishes independently of namespace middleware. The generalisable move is to
drop the vendor SDK and speak the transport, and to try the `transport=polling`
long-poll path where different code handles the session. Separately, Pusher's
private channels delegate authorization to a customer endpoint that signs
`socket_id:channel_name`, and the server libraries did not validate `socket_id`
-- so a user entitled to one private channel could get the customer to sign a
string granting a different one. Any pub/sub product that signs a concatenation
of client-supplied values (Ably, Centrifugo, Socket.IO auth endpoints) has that
delimiter-injection shape.

Belongs in: `browser-realtime` (`authorization.channel_subscription` is already
the right class for the Pusher case), and `realtime` for the transport-downgrade
question.

We would have to observe: for Socket.IO, a GET to
`/socket.io/?EIO=4&transport=polling` is a plain HTTP request and **is**
reachable through our door today -- the long-poll transport is the half of this
we can actually test. For the Pusher case, the auth endpoint takes `socket_id`
and `channel_name` as form fields, which is a body; the query-string form is not
guaranteed.

Sources:
- https://github.com/socketio/socket.io/issues/4899 (reported 13 December 2023; closed by maintainers as a question, so this remains a per-application misconfiguration class rather than a patched CVE)
- https://github.com/advisories/GHSA-7v7m-pcw5-h3cg (published 20 May 2024, `pusher/pusher-php-server` < 2.2.1, CVSS 6.5, no CVE assigned)

### 19. Artefact exposure classes our candidate list does not name

`attack-surface` step 2 is right to refuse a generic wordlist and to demand a
reason per candidate. The reasons it gives -- a bundle implies a source map, a
version implies the version before it -- are good and incomplete. Four more with
current evidence behind them, each of which is a *reason*, not a wordlist entry:
a repository checkout implies `.git/config` and then `.git/index` (GreyNoise
measured this as industrialised crawling, peaking near 4,800 unique malicious
IPs per day on 20-21 April 2025); a vendor-shipped application implies its
**sample configuration** (CargoWise WebTracker's `Web.Config.Sample` carried a
static machine key, which is what made unauthenticated ViewState forgery
possible); a telemetry integration implies both a DSN in the bundle and the
maps that were published rather than uploaded; and a public build pipeline
implies artefacts (`actions/checkout` persists `GITHUB_TOKEN` into `.git/config`
in the workspace, so any later `upload-artifact` of that workspace ships it --
Artifacts v4 made them downloadable while the workflow still runs, turning an
expired-token curiosity into a race).

Belongs in: `attack-surface` step 2 and `information-disclosure`.

We would have to observe: exactly what step 5 already does -- a differing
Artifact identified by a `jq` filter. `.git/config` is INI rather than JSON, and
our only offline text tool for a non-JSON, non-JavaScript artefact is nothing at
all, so `attack-surface` correctly ends at inconclusive there today. That is a
real capability gap worth naming: a registered tool that can select a named key
out of an INI/YAML/dotenv artefact would convert several of these from
"inconclusive" to `content_match`.

Sources:
- https://www.greynoise.io/blog/spike-git-configuration-crawling-risk-codebase-exposure (28 April 2025)
- https://slcyber.io/research/cargowise-webtracker-the-keys-were-in-the-cargo (25 June 2026, Searchlight Cyber; no CVE stated on the page)
- https://unit42.paloaltonetworks.com/github-repo-artifacts-leak-tokens/ (13 August 2024, Unit 42, "ArtiPACKED")
- https://blog.gitguardian.com/fresh-from-the-docks-uncovering-100-000-valid-secrets-in-dockerhub/ (15 May 2025; 99% of detections found only in image layers, not config)

### 20. Timing as a discovery oracle (noted, and mostly out of reach)

Kettle's single-packet timing work finds hidden parameters and routes, blind
server-side injection, and reverse-proxy misrouting including scoped SSRF that a
DNS pingback cannot see -- by measuring the **order** responses arrive in rather
than absolute latency, which is what removes network jitter. It is a genuinely
important discovery primitive and this harness cannot run it: placing several
requests in one TCP packet is a framing operation, and the interception proxy
re-encodes. `timing_differential` exists as an evidence kind, so a coarse
single-request timing observation is admissible; the technique that actually
works is not. Recording the constraint is more useful than proposing a degraded
version that would produce a receipt that cannot mean what it says.

Belongs in: nowhere, today. Flagged so it is not re-proposed.

Sources:
- https://portswigger.net/research/listen-to-the-whispers-web-timing-attacks-that-actually-work (7 August 2024, James Kettle; tool: Param Miner)

---

## What in our playbooks looks stale or weak

**Several playbooks describe requests this harness cannot send.** This is the
most serious finding in the document and it is not about technique currency.
`mcp__rk2__http_request` accepts method, url and headers -- there is no body.
- `graphql` steps 2-3 send "the application's own selection... same operation
  name, same variables, same document". A GraphQL POST is a JSON body.
- `grpc` step 3 sends "the request body the recorded surface holds for this
  method". A gRPC unary call is a length-prefixed protobuf body.
- `webhooks` step 2 sends a state-changing request "with the parameter set to a
  URL" -- reachable only if the parameter is in the query string.
- `routing` steps 3-4 send "same method, same path, same body".
- `realtime` step 4 requires a page "served on a different origin"; the browser
  lane navigates and cannot host.
Before a real engagement, each of these needs either a harness capability or a
step that states its own precondition ("this reading applies where the operation
is expressible without a body") and routes to an operator otherwise.

**`api` is one Playbook doing one-twelfth of its name.** It is a per-identity
rate-limit reading. Nothing in the cluster outputs `rate_limiting.resource_cost`
or `rate_limiting.per_origin` even though both have fixtures written against
"the batched-operation abuse pattern that recurs across public disclosures" and
"the unauthenticated-endpoint abuse pattern". The most common API bug classes of
the last three years -- BOLA/BFLA on undocumented routes, version drift, mass
assignment -- have no reading in this cluster at all; `api-authorization` and
`object-ownership` cover the object half only.

**`deployment`'s spelling list is a 2019 list.** Dot segment, doubled separator,
trailing dot, one percent-encoded separator, matrix parameter. Missing: the
double-encoded dot segment (`%252e%252e`) that is the actual modern
proxy-hop bypass, the appended fake static extension that satisfies an outer
cache/auth rule, and the header arm entirely -- and the header arm is the one
our door sends best.

**`cms` is aimed at a platform mix that is aging.** Three references, all
traditional PHP CMSs. The 2026 evidence points at WordPress **plugins** (96% of
7,966 WordPress vulnerabilities in 2024 per Patchstack; 33% unfixed at
disclosure), at core REST routes with two spellings, and at headless products
(Strapi, Directus) whose failures fit our parallel-route class perfectly. The
five-name budget is fine; the names are wrong-shaped.

**`information-disclosure` is gated on `tech_openapi`.** A published OpenAPI
document is a minority condition on real targets. The same reading -- two name
sets, differenced in both directions, with the missing direction as the control
-- applies to the RSC/hydration payload versus the rendered DOM, and to a
GraphQL response versus the operation's own selection set, neither of which
needs a contract document.

**`graphql` hands away more than it keeps.** It refuses introspection ("record
it as surface"), refuses batching and aliasing ("a different question"), and
refuses mutations. What is left is one field-level differential. Each refusal
is individually defensible; together they mean the Playbook cannot make a claim
about the two GraphQL issues most likely to be present on a live target.

**`realtime` reads invariance as the finding without checking the precondition
that makes invariance meaningful.** In default Chrome and Edge a `SameSite=Lax`
cookie will not be attached cross-site at all. The Playbook needs to read
`SameSite` off the baseline `Set-Cookie` and declare the reading inapplicable
where the value is `Lax` or `Strict` and no same-site subdomain is in scope --
otherwise it will produce refutations that are about cookie policy.

**`webhooks` covers the outbound half only.** Registration-side SSRF is one of
two webhook classes; the receiving side -- signature verification, replay
tolerance, cross-tenant key reuse -- is where a large share of disclosed webhook
bugs actually sit, and nothing in the repository reads it.

**`attack-surface` step 5 dead-ends on non-JSON artefacts.** `jq` is the only
registered offline tool that can select a field, so `.git/config`, `.env`,
`web.config`, `.DS_Store` and YAML all end at inconclusive by construction. The
Playbook is honest about this, which is correct, but it caps the yield of the
single highest-volume finding class in the cluster.

**`external-resources` has the network-less role right and the trigger wrong.**
It requires `url_valued_parameter`, so a document that delegates execution to a
lapsed third-party origin **without** any parameter -- which is the common case,
and the case `broken-link-hijacking` was originally about -- does not trigger it.

**`stale_after` dates.** Six of the eleven are `2027-02-15` or `2027-03-15`.
Given how much of the 2025-2026 material above post-dates the writing of these
texts, the recon and protocol Playbooks in particular are already carrying
content that a 2027 review will find stale; the technique lists inside them
should be treated as the perishable part.

---

## Concrete change proposals per playbook

* **`attack-surface/playbook.md`** -- rewrite step 2 so candidates come from a
  `js_routes`/`js_map` tool run over a stored bundle rather than from a model's
  reading of the surface, and add four named reasons to the list it may derive:
  a repository checkout implies `.git/config`; a vendor product implies its
  shipped sample configuration; a telemetry integration implies a published
  source map; a documented version implies its sibling and its `beta.`/`staging.`
  host. Add `/.well-known/openid-configuration` and `application.wadl` as
  surface-implied candidates. In step 5, state plainly that a non-JSON artefact
  is inconclusive **because no registered tool can select from it**, and file the
  capability gap rather than leaving it as a property of the artefact.

* **`api/playbook.md`** -- add one step before the sequence that names the
  version siblings of the endpoint (`/v1/` beside `/v2/`, the `beta.` host) and
  states that a limit found on one is not a limit on the other, per API9:2023;
  and add an explicit hand-off sentence naming `rate_limiting.per_origin` and
  `rate_limiting.resource_cost` as the two classes this reading cannot make,
  with the note that neither currently has a Playbook.

* **`routing/playbook.md`** -- step 3 and step 4 both say "same body"; add the
  precondition that this reading applies only where the step is expressible
  without a body through `mcp__rk2__http_request`, and route to an operator
  otherwise. Then extend step 4's spelling list with the double-encoded dot
  segment and with one framework trust header (`x-middleware-subrequest`), since
  a step reached by skipping middleware is exactly "the step ran without the
  steps before it".

* **`deployment/playbook.md`** -- rewrite step 3's list: add `%252e%252e` as the
  double-decode arm and an appended fake static extension as the outer-rule arm,
  and add a **second family** of arms that are headers rather than spellings
  (`x-middleware-subrequest`, `x-now-route-matches`, `x-forwarded-proto: x`,
  empty `x-forwarded-host`), each with the same unrestricted-path control step 4
  already requires. Keep the eight-request ceiling by making the two families
  alternatives chosen from the fingerprint, not additions.

* **`cms/playbook.md`** -- replace the candidate-name guidance in step 1 so the
  five names are drawn from the platform's *current* conventions and must include
  both spellings where the platform serves one route two ways (WordPress:
  `/wp-json/<route>` and `?rest_route=/<route>`); add Strapi and Directus to the
  platforms the fingerprint may name, with their public content and Flow routes;
  and add one sentence to step 5 noting that a platform route reachable under a
  second spelling that the application's own spelling refuses is simultaneously
  `authorization.edge_rule` and should be recorded as an observation for
  `deployment`.

* **`information-disclosure/playbook.md`** -- add a second admissible contract
  beside the OpenAPI document, so the reading also runs where the "contract" is
  the rendered DOM and the "response" is the RSC/hydration payload embedded in
  the same HTML (`__next_f`, `?_rsc=`). The step structure -- both directions,
  missing-direction as control, names not values -- carries over unchanged; only
  step 1 and the `tech_openapi` trigger need to widen.

* **`external-resources/playbook.md`** -- drop `url_valued_parameter` from
  `bb:triggers_all` (or make step 2 explicitly optional, which the text already
  half does when it says "the parameter half is unanswered"), so a document that
  delegates execution to an unclaimed origin with no parameter involved still
  reaches this reading. Keep step 5's refusal exactly as written.

* **`grpc/playbook.md`** -- add a step between 2 and 3 that asks whether the same
  method is reachable over a **transcoded** JSON/REST path as well as over binary
  gRPC, and treat a `grpc-status 0` on one and a refusal on the other as the
  differential; and state in step 7 that the binary arm requires a request body
  the harness does not currently send, so a reading that cannot send it records
  `inconclusive` and routes to an operator rather than reporting the transcoded
  arm as the whole answer.

* **`graphql/playbook.md`** -- keep the two-Identity differential as the claim,
  but replace the flat refusal of introspection with a step that establishes the
  selection set when the client's own operation is unavailable: probe
  introspection, and where it is filtered, record whether the endpoint answers
  a suggestion-bearing error (the `content_match` that says field-suggestion
  recovery is possible) and whether GET or `x-www-form-urlencoded` is accepted
  where JSON POST is refused. Add a sentence to step 6 stating that the
  subscription transport (`graphql-ws` versus `graphql-transport-ws` over the
  websocket) is a second surface belonging to `realtime`.

* **`realtime/playbook.md`** -- insert a precondition step before step 4 that
  reads `SameSite` off the baseline's `Set-Cookie` and declares the reading
  inapplicable where the value is `Lax` or `Strict` and no in-scope same-site
  subdomain exists; add `Sec-WebSocket-Protocol` as a second handshake variable
  (legacy versus modern subprotocol) since it is a header our door can set; and
  state in step 7 that serving a page from a foreign origin is not a capability
  this harness has, so the origin arm is currently produced by a header on the
  upgrade request with all the weakness that implies, or not at all.

* **`webhooks/playbook.md`** -- add to step 3 that a window closing empty is not
  the end of the reading where the channel could have been made to *answer*
  (redirect chain, TTL-0 record), and record those as capabilities the runtime
  does not have rather than as absent evidence; and add a neighbour paragraph
  naming the receiving side -- signature verification, replay tolerance,
  cross-tenant key reuse -- as a class no Playbook currently claims.

* **Capability tickets implied by the above** (not Playbook edits, but they gate
  four of the proposals): a bodied request through the scope proxy; an offline
  tool that selects from INI/YAML/dotenv artefacts; a browser action that sends
  one application message on an open socket; and a callback channel that can
  answer as well as record.

---

## Sources consulted

PortSwigger Research and Web Security Academy
- https://portswigger.net/research/top-10-web-hacking-techniques-of-2025 (published 5 February 2026) -- the 2025 ranked list; gave the redirect-loop SSRF (#3), the Next.js stale-elixir cache chain (#7), HTTP/2 CONNECT (#9) and parser differentials (#10).
- https://portswigger.net/research/top-10-web-hacking-techniques-of-2024 -- gave Orange Tsai's Confusion Attacks (#1) and the ChatGPT wildcard cache deception (#9).
- https://portswigger.net/research/top-10-web-hacking-techniques-of-2023 -- context for which older techniques are still cited; nothing in this cluster depends on it.
- https://portswigger.net/research (index, fetched 2026-08-21) -- established what PortSwigger has published in 2026.
- https://portswigger.net/research/gotta-cache-em-all (8 August 2024, Martin Doyhenard) -- delimiter and normalisation discrepancies between cache and origin.
- https://portswigger.net/web-security/web-cache-deception -- the concrete send/observe steps for each cache-deception primitive.
- https://portswigger.net/research/listen-to-the-whispers-web-timing-attacks-that-actually-work (7 August 2024, James Kettle) -- timing as a discovery oracle; recorded as out of reach for this harness.
- https://portswigger.net/research/crlf-powered-desync-attacks (5 August 2026, Tom Stacey and Tobia Righi) -- CRLF header injection escalating to desync through a normalising proxy; the reason our webhook CRLF proposal stops at the configuration round-trip.
- https://portswigger.net/research/can-ai-do-novel-security-research (5 August 2026, James Kettle) -- the HTTP Terminator; confirms desync is where the field's energy is and therefore what our framing refusal costs us.
- https://portswigger.net/web-security/graphql -- introspection probe, the special-character filter bypass, Clairvoyance, alias-based rate-limit bypass, GraphQL CSRF.
- https://portswigger.net/web-security/websockets -- the baseline WebSocket technique catalogue our `realtime` Playbook is measured against.
- https://portswigger.net/web-security/ssrf/url-validation-bypass-cheat-sheet ("2024 Edition") -- fetched, but the page body is a payload-list stub, so it is cited as a pointer only.

Researcher and vendor research blogs
- https://blog.orange.tw/posts/2024-08-confusion-attacks-en/ (9 August 2024) -- filename/DocumentRoot/handler confusion in Apache; the `%3F` truncation and ACL bypass primitives.
- https://zhero-web-sec.github.io/research-and-things/nextjs-and-the-corrupt-middleware (March 2025) -- CVE-2025-29927 and the exact header values per version range.
- https://zhero-web-sec.github.io/research-and-things/nextjs-cache-and-chains-the-stale-elixir (January 2025) -- CVE-2024-46982, `x-now-route-matches` and `__nextDataReq`.
- https://zhero-web-sec.github.io/research-and-things/nextjs-and-cache-poisoning-a-quest-for-the-black-hole (June 2024) -- CVE-2023-46298, `x-middleware-prefetch`.
- https://zhero-web-sec.github.io/research-and-things/eclipse-on-nextjs-conditioned-exploitation-of-an-intended-race-condition (May 2025) -- CVE-2025-32421, racing the response-cache batcher.
- https://zhero-web-sec.github.io/research-and-things/astro-framework-and-standards-weaponization (November 2025) -- CVE-2025-64525, `x-forwarded-*` reconstructed into the request URL, and the empty-header bypass of the earlier fix.
- https://vercel.com/blog/postmortem-on-next-js-middleware-bypass -- confirms self-hosted was affected and platform-routed was not, which is the generalisable lesson about internal trust headers.
- https://slcyber.io/research-center/novel-ssrf-technique-involving-http-redirect-loops/ (23 June 2025, Shubham Shah) -- incrementing-status redirect loops turning blind SSRF into a full read.
- https://slcyber.io/research-center/nginx-apache-path-confusion-to-auth-bypass-in-pan-os-cve-2025-0108/ (12 February 2025) -- the double-decode-across-a-hop 403 bypass.
- https://www.slcyber.io/research/how-we-got-persistent-xss-on-every-aem-cloud-site-thrice (1 July 2025) -- prefix checks without a delimiter, and the edge worker's URL parser differing from the origin's.
- https://slcyber.io/research/wp2shell-pre-authentication-rce-in-wordpress-core (17 July 2026, Adam Kues) -- the `/wp-json/batch/v1` and `?rest_route=/batch/v1` spellings.
- https://slcyber.io/research/cargowise-webtracker-the-keys-were-in-the-cargo (25 June 2026) -- a shipped `Web.Config.Sample` as the artefact-exposure candidate class.
- https://slcyber.io/research-center/ (index, fetched 2026-08-21) -- established what Searchlight Cyber has published in 2026 and the pre-auth-research focus.
- https://www.elttam.com/blog/leaking-more-than-you-joined-for/ (page shows 18 December 2025, Alex Brown) -- ORM leaks generalised across Django, Prisma, Beego, Entity Framework, Sequelize and Ransack; belongs to `orm`, noted here because the oracle is a response-length or timing differential our evidence kinds already carry.
- https://blog.flomb.net/posts/http2connect/ (15 September 2025) -- multiplexed HTTP/2 CONNECT internal port scanning; refused here on two counts (framing, and reaching hosts under the scoped ingress).
- https://blog.doyensec.com/2026/05/25/cloudsectidbits-elbaph-alb.html (25 May 2026, Francesco Lacerenza and Mohamed Ouad) -- ALB rule shadowing, CloudFront bypass to the origin ALB, and client-controlled `X-Forwarded-For` under preserve mode.
- https://blog.doyensec.com/2024/07/02/cspt2csrf.html (2 July 2024, Maxence Schmitt) -- client-side path traversal into CSRF; we already ship `client-side-path-traversal`, and this is the current primary source for it.
- https://blog.doyensec.com/ (index, fetched 2026-08-21) -- confirmed Doyensec has no recent GraphQL/gRPC/WebSocket/webhook post, which is why those sections lean elsewhere.
- https://blog.sentry.security/abusing-exposed-sourcemaps/ (31 January 2025) -- the end-to-end source-map-to-account-takeover chain.
- https://brackish.io/2024/07/03/javascript-source-map-vulnerabilities/ (3 July 2024) -- source-map recovery tooling.
- https://www.bswanson.dev/blog/nextjs-hydration-payload/ (23 March 2025) -- `__next_f` RSC payload carrying props the UI never renders.
- https://www.greynoise.io/blog/spike-git-configuration-crawling-risk-codebase-exposure (28 April 2025) -- `.git` exposure as industrialised crawling, with measured volumes.
- https://labs.watchtowr.com/8-million-requests-later-we-made-the-solarwinds-supply-chain-attack-look-amateur/ (4 February 2025) -- abandoned S3 buckets re-registered; the strongest argument for `external-resources` step 5's refusal being right.
- https://unit42.paloaltonetworks.com/github-repo-artifacts-leak-tokens/ (13 August 2024) -- ArtiPACKED; `GITHUB_TOKEN` in `.git/config` shipped in artifacts, and the Artifacts v4 race.
- https://blog.gitguardian.com/fresh-from-the-docks-uncovering-100-000-valid-secrets-in-dockerhub/ (15 May 2025) -- secrets in image layers rather than config.
- https://blog.gitguardian.com/docker-zombie-layers/ (8 October 2024) -- unreferenced layers still pullable by digest.
- https://trufflesecurity.com/blog/how-secrets-leak-out-of-docker-images (11 September 2023) -- the deleted-but-present layer mechanism.
- https://www.securityweek.com/misconfigured-firebase-instances-expose-125-million-user-records/ (19 March 2024) -- public-by-design client config plus absent security rules.
- https://nokline.github.io/bugbounty/2024/02/04/ChatGPT-ATO.html (4 February 2024, Harel) -- wildcard cache rule plus encoded traversal into a session endpoint.
- https://blog.includesecurity.com/2025/04/cross-site-websocket-hijacking-exploitation-in-2025/ (17 April 2025) -- CSWSH preconditions per browser. `[unverified: HTTP 403 on direct fetch; reported via a text-extraction proxy]`
- https://blog.compass-security.com/2025/10/brpc-web-a-burp-suite-extension-for-grpc-web/ (21 October 2025) -- heuristic gRPC-Web decoding without `.proto` files.
- https://bhamza.me/blogpost/2024/03/04/Security-assessing-grpc-and-grpcweb-services.html (4 March 2024) -- gRPC-Web framing and reflection abuse.
- https://kmcd.dev/posts/protobuf-unknown-fields/ (page indicates April 2026, originally March 2024) -- unknown-field passthrough across a schema-skewed gateway.
- https://www.svix.com/blog/common-failure-modes-for-webhook-signatures/ (date not shown) -- the ten webhook-signature failure modes, including unsigned metadata and one-key-per-tenant.
- https://hookdeck.com/webhooks/guides/webhook-security-vulnerabilities-guide (date not shown) -- Stripe's 5-minute tolerance default and Shopify's signature header.
- https://www.yeswehack.com/learn-bug-bounty/syntax-confusion-ambiguous-parsing-exploits (17 October 2025) -- parser confusion beyond URLs (port normalisation, `file://` host form, `Content-Disposition` filename forms).
- https://www.yeswehack.com/learn-bug-bounty/discover-map-hidden-endpoints-parameters (9 January 2025) -- hidden-endpoint discovery methodology.
- https://www.intigriti.com/researchers/blog/hacking-tools/testing-javascript-files-for-bug-bounty-hunters (19 December 2024, updated 8 August 2026) -- lazily-loaded chunks never reaching proxy history unless forced.
- https://www.intigriti.com/researchers/blog/hacking-tools/ssrf-vulnerabilities-in-nextjs-targets (28 September 2025, updated 8 August 2026) -- `/_next/image?url=` and the redirect-following allowlist bypass.
- https://www.intruder.io/research/broken-authorization-apis-autoswagger (22 July 2025, Daniel Andrew) -- replaying every documented operation with no credential; names CVE-2025-0589.
- https://samcurry.net/web-hackers-vs-the-auto-industry (3 January 2023) -- `application.wadl` enumeration and mobile-derived API inventory. Older than three years next January, still the clearest primary write-up of the method.
- https://blog.criticalthinkingpodcast.io/p/motivation-and-methodology-with-sam-curry (5 April 2024) -- the `/api` proxy secondary-context method, stated by the researcher.
- https://lab.ctbb.show/research/h2-WAF-Bypasses (1 June 2026) -- out-of-process WAFs deciding on HEADERS before DATA arrives; RFC 8441 Extended CONNECT downgraded to GET before method ACLs. Both are framing-adjacent and mostly out of reach here.
- https://www.pentestpartners.com/security-blog/pwning-wordpress-graphql/ (reported 23 March 2019, published 8 May 2019) -- CMS-shipped GraphQL re-implementing authorization independently of the CMS capability system. Old; included as pattern guidance because the shape recurs in headless products.
- https://www.cloudsek.com/threatintelligence/leaked-slack-webhooks-exploit-endpoint-vulnerability-in-slack-channels (22 June 2022, updated 19 April 2023) -- the webhook URL as the whole credential. Older, still the standard reference.
- https://orca.security/resources/blog/pull-request-nightmare-github-actions-rce/ (24 September 2025) -- `pull_request_target` as a webhook-driven CI compromise; out of this cluster's scope but the same "webhook event triggers privileged work" shape.
- https://www.invicti.com/web-application-vulnerabilities/wordpress-rest-api-user-enumeration -- WordPress REST user enumeration.
- https://patchstack.com/whitepaper/state-of-wordpress-security-in-2025/ (14 March 2025) -- the plugin-versus-core split that argues against our CMS reference set.
- https://www.cyera.com/blog/cyera-research-uncovers-six-protobuf-js-vulnerabilities-impacting-the-backbone-of-data-and-ai-systems (5 June 2026) -- descriptors and schema registries treated as trusted input.

Advisories and standards
- https://owasp.org/API-Security/editions/2023/en/0x11-t10/ -- the API Security Top 10 **2023** category list. Confirmed current: there is no 2025 or 2026 API edition, and https://owasp.org/www-project-api-security/ gives 5 June 2023 as the stable release with no newer edition announced. The web Top 10 **did** get a 2025 edition (https://owasp.org/Top10/2025/0x00_2025-Introduction/), where SSRF was folded into A01 -- the two projects are routinely conflated and should not be.
- https://owasp.org/API-Security/editions/2023/en/0xa9-improper-inventory-management/ -- API9:2023, including the `beta.api...` scenario that is the shadow/zombie API pattern.
- https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html -- the batching-attack definition quoted in technique 4.
- https://github.com/grpc/grpc-go/security/advisories/GHSA-p77j-4mvh-x3m3 -- CVE-2026-33186, published 17 March 2026.
- https://explore.alas.aws.amazon.com/CVE-2024-23324.html -- CVE-2024-23324, published 9 February 2024, Envoy `ext_authz` fail-open.
- https://github.com/envoyproxy/envoy/issues/9929 -- the transcoder/`ext_authz` ordering trap, reported 4 February 2020, closed stale.
- https://github.com/strawberry-graphql/strawberry/security/advisories/GHSA-vpwc-v33q-mq89 -- CVE-2026-35523, published 4 April 2026.
- https://github.com/neo4j/graphql/security/advisories/GHSA-fcpg-3fw5-vc65 -- CVE-2026-5423, published 6 August 2026.
- https://github.com/Syslifters/sysreptor/security/advisories/GHSA-2vfc-3h43-vghh -- CVE-2024-36076, published 21 May 2024.
- https://github.com/advisories/GHSA-7v7m-pcw5-h3cg -- Pusher `socket_id` signing oracle, published 20 May 2024, no CVE assigned.
- https://github.com/advisories/GHSA-xff3-5c9p-2mr4 -- CVE-2026-41432, empty default webhook secret, published 22 April 2026.
- https://github.com/advisories/GHSA-jvhm-gjrh-3h93 -- CVE-2025-27415, Nuxt `?/_payload.json` CDN cache poisoning, published 19 March 2025.
- https://www.wiz.io/vulnerability-database/cve/cve-2025-53092 -- CVE-2025-53092, Strapi reflected-Origin CORS with credentials, published 16 October 2025.
- https://www.miggo.io/vulnerability-database/cve/CVE-2025-53889 -- CVE-2025-53889, Directus unauthenticated Flow triggering, published 15 July 2025.
- https://github.com/socketio/socket.io/issues/4899 -- raw Engine.IO bypassing namespace middleware, reported 13 December 2023.
- https://gitlab.com/gitlab-org/gitlab/-/issues/550766 -- CRLF in outbound webhook header names, reported 26 May 2025.
- https://github.com/mlflow/mlflow/issues/24179 -- resolve-then-discard webhook URL validation, reported 26 June 2026.
- https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries -- constant-time comparison guidance and the legacy SHA-1 header still shipping.
- https://github.com/orgs/community/discussions/179107 -- GitHub's `pull_request_target` secure-by-default change, enforced 8 December 2025.
- https://github.com/nccgroup/blackboxprotobuf and .../docs/TypeDefs.md -- schemaless protobuf decode/re-encode keyed by field number.

Sources that could not be retrieved, and claims left unverified
- https://www.assetnote.io/resources/research/contextual-content-discovery-youve-forgotten-about-the-api-endpoints -- 301 to https://slcyber.io/assetnote; body not retrievable. The contextual-discovery argument is cited from other fetched sources instead.
- https://blog.includesecurity.com/2025/04/cross-site-websocket-hijacking-exploitation-in-2025/ -- HTTP 403 on direct fetch.
- CVE-2026-27886 and CVE-2026-22599 (Strapi) -- only secondary vulnerability databases were retrieved, no primary Strapi advisory.
- Next.js `_buildManifest.js` as a route-table leak; `.DS_Store`; ESI abuse; `X-Original-URL`/`X-Rewrite-URL` overrides; origin-IP discovery behind a CDN; header-based API version pinning as a documented bypass; Azure APIM and Kong spec leakage; draft-mode/preview-token abuse in Next.js/Sanity/Contentful -- searched for, **no primary source retrieved**. Several of these are plausible and none is asserted here. Draft-mode preview tokens in particular look like a genuinely under-researched surface and would be worth a dedicated pass.
- The WebSearch budget for this session was exhausted at 200 calls partway through, which is why some of the above went unclosed. Everything asserted in this file rests on a page that was fetched.
