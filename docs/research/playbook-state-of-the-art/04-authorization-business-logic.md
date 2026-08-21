# 04 - Authorization and business logic

Scope of this note: the six playbooks `api-authorization`, `object-ownership`,
`payment-workflows`, `race-conditions`, `orm` and `logging`, read on 2026-08-21,
against public research from roughly 2023 to 2026.

Two research constraints apply to everything below and are stated once.

* The session's WebSearch budget was exhausted part-way through (200/200 calls),
  so the later half of the work is direct WebFetch of URLs already in hand.
  Some intended sources (Salt Labs, Doyensec, Assetnote, and individual
  HackerOne/Bugcrowd/Intigriti disclosure pages) were never reachable and are
  not cited. Nothing below is attributed to a page that was not read, except
  where the line says explicitly "search result only, not fetched".
* One fetch failed outright: `https://cablej.io/blog/bypassing-payments-using-webhooks/`
  returns a TLS certificate that does not match the host. The same article was
  read on the author's other domain (`lightningsecurity.io`) and is cited there.

## What we already cover well

The six playbooks are unusually strong on *evidential discipline*, and that is
worth naming before listing what is missing, because most of the additions below
have to inherit it rather than replace it.

* **Controls are mandatory and named.** `object-ownership` step 2 forces the
  "label B against label B's own object" control, `race-conditions` step 3
  forces the sequential control before any concurrency, `payment-workflows` step
  3 forces an allowed mutation that lands before the forbidden one is sent, and
  `logging` step 5 forces the second identity's own view. This is exactly the
  "benchmark before you conclude" that James Kettle's race work insists on
  ("if you skip the benchmark step, you'll miss vulnerabilities"), generalised
  to every class in the cluster. Most public methodology writeups do not do this.
* **The 404-vs-403 control.** `api-authorization` step 3's "nonexistent control"
  is the single best step in the cluster and it is genuinely rare in public
  methodology. An application that answers `404` for a missing object and `404`
  for a forbidden transition has told you nothing, and almost no public IDOR
  writeup controls for it.
* **The claim lives in the after-state, not the status line.** `api-authorization`
  step 5, `payment-workflows` step 5 and `race-conditions` step 5 all refuse to
  treat a `200` or a `500` as the finding and go back to the authoritative read.
  This is the correct reading of both BOLA and limit-overrun bugs and it is what
  keeps the harness from filing noise.
* **Named neighbour classes.** Every playbook routes adjacent readings elsewhere
  (`object_ownership` vs `state_transition` vs `function_access`; `query_field`
  vs `query_language` vs `query_operator`; `log_record` vs `credential_material`).
  That taxonomy discipline maps cleanly onto OWASP API Security Top 10 2023's
  split of API1 (BOLA) / API3 (BOPLA) / API5 (BFLA).
* **The ORM playbook already refuses the "quotes only" mistake.** Step 1's list
  (`sort`, `order_by`, `fields`, `filter`, `include`, `expand`, `embed`, plus
  double-underscore / dot / bracket compounds) is precisely the surface elttam's
  ORM-leak research operates on, and the real-name-versus-fictional-name control
  in step 3 is a better detector than the error-message hunting most writeups do.
* **The refusals are real and mostly correct.** No log forging, no log fetching,
  no alerting evasion (`logging` step 7), no purchase that captures funds
  (`payment-workflows` step 7), no racing a payout (`race-conditions` step 7),
  no blind extraction loop (`orm` step 5). Those are the right lines for an
  authorized engagement and the proposals below keep all of them.

## Missing techniques (ranked by expected yield on a real bounty program)

### 1. Cross-tenant BOLA, with a second tenant rather than a second user

`object-ownership` leases two Identities and asks whether the server checks the
object against the caller. On a multi-tenant SaaS target the higher-paying
question is whether it checks the object against the caller's *organisation*,
which is a different clause in a different place: the tenant filter lives in the
query layer, in a background job, in a cache key, or in a token claim nobody
re-validates. Two users inside one tenant will not reveal a missing
`WHERE tenant_id = ?`, because both are inside it. This is the highest-impact
SaaS class and OWASP has kept BOLA at API1 since the list existed. The tenant
selector is usually a separate carrier from the session: a subdomain, a leading
path segment, an `X-Tenant-Id`-style header, an `org_id` body field, or a claim
in the JWT that the API accepts but never compares to the object.

Belongs in: `object-ownership` (a tenant arm), with the tenant-selector variant
in `api-authorization`; the class `authorization.tenant_isolation` already
exists but is claimed by `workload-identities`, which only covers machine-to-
machine credentials plus a tenant header. A user-identity tenant playbook is
either a second output on `object-ownership` or **new playbook: `tenant-isolation`**.

Our playbook would have to observe: which Identity slots belong to which tenant
(a tenant label on the Identity, not just a slot name), the tenant selector
parameter as its own surface fact (the existing `tenant_boundary` fact is close),
and an object identifier known to belong to tenant A read from tenant A's own
authoritative view.

Sources: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/ (2023 edition);
https://securityboulevard.com/2025/12/tenant-isolation-in-multi-tenant-systems-architecture-identity-and-security/ (2025-12-30)

### 2. Mass assignment / BOPLA on the write side

Nothing in the harness writes a property the caller was never offered. `orm`
step 7 refuses it explicitly and correctly ("it writes, this Playbook does not,
and it belongs to a reading that declares that") -- but no such reading exists.
OWASP merged mass assignment and excessive data exposure into API3:2023 (BOPLA)
precisely because the write side keeps paying: `role`, `is_admin`, `verified`,
`status`, `approved`, `owner_id`, `tenant_id`, `balance`, `price` accepted on a
PUT/PATCH that was written for a profile update. The modern shape is not a flat
`isAdmin=true` guess: it is a round-trip (GET the object, resend its own JSON
with one property added), a property nested one level down inside an object the
endpoint does accept, an alternate casing or snake/camel spelling, a JSON Merge
Patch, or a GraphQL mutation input object where the input type is wider than the
UI. OWASP's own example is a marketplace host adding `total_stay_price`.

Belongs in: **new playbook: `mass-assignment`**, emitting a new leaf under
`authorization` (the vocabulary has no object-property leaf today; `injection.
object_graph` is deserialization and is not this).

Our playbook would have to observe: an authoritative GET of the object whose
body can be re-sent, the set of properties the response contains versus the set
the request is documented to accept, and an after-state read under the owner's
own Identity showing the property persisted rather than merely being echoed.

Sources: https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/ (2023 edition)

### 3. Broken function-level authorization over HTTP: verb swap and admin siblings

`authorization.function_access` is claimed by `grpc` only. There is no HTTP
playbook that asks "may this caller call this operation at all". The two things
that land are trivially cheap: change the method on a path the caller may
already `GET` (`GET` to `POST`/`PUT`/`PATCH`/`DELETE`, or an override header
where the framework honours one), and walk to the administrative sibling of a
route you can reach (`/api/v1/users/me` implying `/api/v1/users`, `/api/admin/...`).
OWASP's API5:2023 scenario is exactly a `GET`-to-`POST` swap on `/api/invites/new`
creating an administrator. PortSwigger's access-control material adds the
URL-matching discrepancies (case, trailing slash, added extension) that get past
a front-end rule while the back end still routes.

Belongs in: **new playbook: `function-authorization`** emitting
`authorization.function_access` for HTTP surfaces, sibling to `grpc`. Some of
the URL-spelling half overlaps `deployment` (`authorization.edge_rule`) and
`cms` (`authorization.parallel_route`), so the new playbook should read the
method axis and route the spelling axis to those.

Our playbook would have to observe: the method set the route advertises (from
`OPTIONS`, from an OpenAPI fact, or from the state view), a second Identity at a
lower privilege level *within the same tenant* (a role label, which we do not
currently model), and a safe verb ordering that never sends `DELETE` at another
identity's object.

Sources: https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/ (2023 edition);
https://portswigger.net/web-security/access-control (undated Web Security Academy topic, read 2026-08-21)

### 4. Carrier and shape variation of the object identifier after a refusal

`object-ownership` step 3 holds everything constant except the session, and step
5 calls the reading refuted when the variant is invariant. That is sound as far
as it goes, and it is where most of today's IDOR reports actually begin rather
than end. The bugs that pay come from re-spelling the identifier once the plain
swap is refused: move the ID from the path to a body field or a query parameter
the same handler also reads, send the parameter twice (the check reads the first
occurrence and the handler reads the last), wrap the value in a one-element JSON
array or an object, send it with a type the parser coerces, or append a second
comma-separated value. Our `request-parsing` playbook owns exactly this
mechanism (`injection.parameter_precedence`) but asks it about a filter, not
about an authorization decision, and the two playbooks never meet.

Belongs in: `object-ownership` (a step 3b that varies the carrier, once each,
under label B), citing `request-parsing` as the neighbour for the parsing claim.

Our playbook would have to observe: every carrier the same endpoint accepts for
the same logical parameter (the Surface already records parameters per carrier),
and a refusal baseline strong enough that a single success is attributable.

Sources: https://portswigger.net/web-security/access-control (read 2026-08-21);
https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/ (2023 edition)

### 5. Blind and second-order IDOR, verified through the owner's view

`object-ownership` is `read_only` and its evidence is a `response_differential`:
the variant must return the object's content. A large fraction of real IDOR is
blind. Label B's write is accepted, the response is a bare `204`, and the only
proof is that label A's own view changed. Equally common: the read is refused
inline but the same object surfaces later in an export, a PDF, a digest email,
a report, a webhook, or the activity view. `api-authorization` already has the
right machinery (pristine read, after-state read as the owner) and
`object-ownership` does not.

Belongs in: `object-ownership` (an after-state read under label A when the
variant is a write, or when the variant's body is empty), with a pointer to
`logging` for the case where the object appears in an activity view.

Our playbook would have to observe: label A's authoritative read of the same
object before and after, and the fact that the variant was a write (so the
playbook's `effects` become conditional: `read_only` for the read arm,
`mutates_object` for the blind arm, which the runtime scheduler must be able to
express).

Sources: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/ (2023 edition);
https://portswigger.net/web-security/access-control (read 2026-08-21)

### 6. Multi-endpoint races, and the payment TOCTOU in particular

`race-conditions` only knows one shape: the same request twice. Kettle's 2023
work is mostly about the other shapes, and the multi-endpoint collision is the
one with the money in it: send the cart-modification and the checkout-confirm so
they collide, and the item is added after the price is validated and before the
order is written. The same shape covers email-change racing email-confirmation
(demonstrated against GitLab), and permission-change racing the operation the
permission guards. This is a *different sub-state* being exploited, not a
counter being over-run, and our playbook's counter-only framing cannot express it.

Belongs in: `race-conditions` (a second variant arm for two different routes),
and the cart case additionally in `payment-workflows`.

Our playbook would have to observe: two routes that touch one record, the record
that is common to both (Kettle's "same operational key" filter), and one
authoritative read afterwards that shows the inconsistent end state rather than
a count.

Sources: https://portswigger.net/research/smashing-the-state-machine (2023-08-09, updated 2023-09-18);
https://portswigger.net/web-security/race-conditions (Web Security Academy, read 2026-08-21)

### 7. GraphQL alias and array batching as a network-free limit overrun

This is the most important entry for our specific harness, because it produces
race-class impact through an intercepting proxy that re-encodes requests. One
HTTP request carrying N aliased fields, or a JSON array of N operations, becomes
N resolver invocations inside one transaction boundary. That defeats per-request
rate limits, defeats per-request OTP attempt counters, and in many
implementations over-runs a limit that a proper single-packet race would be
needed to over-run at the HTTP level. OWASP's GraphQL cheat sheet calls out that
batching enables enumeration, brute-forcing authentication codes, and appearing
to a WAF as a single request. PortSwigger teaches the alias form as the standard
rate-limit bypass.

Belongs in: `race-conditions` (as the substitute arm when the surface is
GraphQL, since it is the same invariant question with a different emitter) and
referenced from `graphql`.

Our playbook would have to observe: `graphql_surface` plus a single-use or
counted action reachable as a mutation, the counter route, and the server's
handling of an array-form POST body (accepted or rejected) as its own control.

Sources: https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html (read 2026-08-21);
https://portswigger.net/web-security/graphql (read 2026-08-21)

### 8. ORM operator injection and relation traversal, as a bounded oracle

`orm` reads which *name* the caller chose and then stops, refusing to "sort your
way through the column". The class that is actually landing right now is one
step past that: the caller controls the *operator* as well as the field, so
`password__startswith=a`, `email__contains=`, a regex, or a `gt`/`lt` comparison
against collation order turns the filter into a character-at-a-time oracle over
a column the API never returns. elttam's follow-up (PortSwigger's #2 technique
of 2025) generalises this beyond Django: Beego's expression parser lets
`email__password__startswith` collapse to `password__startswith` and defeat a
field denylist, Entity Framework / OData `$expand` pulls in associated entities'
fields, and Prisma is reachable by putting a JSON object where a string was
expected (`{"not": "value"}`) via URL, body or cookie. Our playbook's
fictional-name control is a good detector; what is missing is the operator axis
and a bounded, declared way to demonstrate impact.

Belongs in: `orm` (a step between today's 4 and 5), keeping the refusal of full
extraction but replacing "record the difference and stop" with "confirm one
boolean or one character, state the extraction rate, stop".

Our playbook would have to observe: the framework fact (already required), the
operator suffix syntax for that framework, a response signal that separates true
from false (length, status, or timing), and a declared request budget for the
oracle so the report can say what it cost.

Sources: https://www.elttam.com/blog/plormbing-your-django-orm/ (2024-06-23, Alex Brown);
https://www.elttam.com/blog/leaking-more-than-you-joined-for/ (2025-12-18, Alex Brown);
https://portswigger.net/research/top-10-web-hacking-techniques-of-2025 (2026-02-05, ranks it #2)

### 9. Payment provider webhook forgery and replay

`payment-workflows` reads the total the target computes from the caller's own
request. The other half of every payment integration is the callback the
provider sends, and it is routinely unauthenticated: no signature check, no
replay window, no re-fetch of the charge from the provider's own API. Jack
Cable's 2018 write-up is old and still describes the live failure mode; a 2026
measurement found 1,542 of 6,000 scanned applications answering 2xx to a
Stripe-shaped checkout-completed event sent with no signature header at all
(the authors caveat that a 2xx does not prove the account was credited). Our
`webhooks` playbook exists but emits `injection.request_forgery`, which is the
outbound direction, not the inbound-trust direction.

Belongs in: `payment-workflows` (an inbound-callback arm) or a new leaf under
`authentication`; the safe substitute in the safety section below is mandatory.

Our playbook would have to observe: a callback path (from JS, from docs, from
the path list), the response to an unsigned probe carrying a *non-granting*
payload, and the account's own authoritative balance/entitlement read before and
after to prove nothing was actually credited.

Sources: https://lightningsecurity.io/blog/bypassing-payments-using-webhooks/ (2018-03-13, Jack Cable; the cablej.io copy fails TLS);
https://securityscanner.dev/blog/stripe-webhook-signature-bypass-1500-apps (2026-05-05)

### 10. Coupon, discount and credit logic beyond a single number

`payment-workflows` moves exactly one number and forbids a second. Discount
logic is where the domain-specific flaws live and it is rarely one number: the
same code applied twice in sequence, two codes submitted where the UI allows one
(via a repeated parameter or an array), a code applied to an order and then the
order downgraded, a code applied after a partial refund, a referral credit that
survives the referred account's deletion, a store credit spent and refunded to a
different instrument. PortSwigger files these under domain-specific logic flaws
and flawed assumptions about user behaviour; OWASP's API6:2023 covers the
automation half.

Belongs in: `payment-workflows` (a second variant shape: same number, different
*sequence* of operations), overlapping `routing` (`business_logic.workflow_order`)
for the ordering half.

Our playbook would have to observe: the published terms (the invariant, which
step 1 already demands), the authoritative total, and the ability to run a short
declared sequence of operations rather than exactly one edit.

Sources: https://portswigger.net/web-security/logic-flaws (read 2026-08-21);
https://owasp.org/API-Security/editions/2023/en/0xa6-unrestricted-access-to-sensitive-business-flows/ (2023 edition)

### 11. Currency, rounding and unit confusion

A sub-case worth its own step because the invariant is different. Send a
currency the account does not hold and see which side of the conversion the
server trusts; send a minor-unit value where a major-unit was expected (or the
reverse); send a fractional quantity where rounding is done per line and
truncation per order; send a price with more decimal places than the currency
has. The finding is still the authoritative total, so it inherits our existing
evidence contract exactly. `payment-workflows` step 4 already lists "a currency
the account does not hold" in passing but the playbook offers no way to read the
conversion, which is where the defect is.

Belongs in: `payment-workflows`.

Our playbook would have to observe: the currency/locale parameter as its own
surface fact, and a total route that states currency as well as amount.

Sources: https://portswigger.net/web-security/logic-flaws (read 2026-08-21)

### 12. Single-endpoint races with differing values, partial construction, deferred collisions

The remaining Kettle classes our `race-conditions` cannot express. Single-endpoint
collision: two parallel requests to one route carrying *different* values, so one
request's user ID pairs with the other's token (the Devise password-reset case).
Partial construction: an object built in several writes has an exploitable middle
state where a field is still null or empty, and a request that matches the
uninitialised value (`param[]=`, a nil) authenticates against it. Deferred
collision: the conflicting operations are processed by a batch job much later, so
the two requests need not be simultaneous at all -- which is the class most
likely to be reachable through our re-encoding proxy, because it needs no timing
precision whatsoever.

Belongs in: `race-conditions` (three named variant shapes with the same
sequential control), and the deferred shape should be flagged as the one to try
first given our transport constraints.

Our playbook would have to observe: two parameter values that differ, a route
that creates an object in stages (a signup, an invite, an import), and a way to
re-read the object between stages.

Sources: https://portswigger.net/research/smashing-the-state-machine (2023-08-09);
https://portswigger.net/web-security/race-conditions (read 2026-08-21)

### 13. GraphQL relation traversal, global-node access, and mutation-side gaps

`graphql` asks one selection under two identities and differences the documents.
Three current bypasses live outside that. First, reaching an object you may not
query directly by traversing to it from one you may (`me { organization { members
{ email } } }`): the resolver on the edge is checked, the resolver on the node is
not, which OWASP's cheat sheet calls out as "enforce authorization checks on both
edges and nodes". Second, a schema-wide `node(id:)` / `nodes(ids:)` field that
takes an opaque global ID and hands back any object type, bypassing the
per-type entry points where the checks were written. Third, mutations whose
authorization was never written because the query side had it.

Belongs in: `graphql` for the field-level half; `object-ownership` should gain a
GraphQL arm (the object identifier is an argument, and the class is the same
`authorization.object_ownership`).

Our playbook would have to observe: the schema (introspection, or field
suggestions where introspection is off), the relation edges from an object the
Identity owns, and the same two-Identity control the REST arm uses.

Sources: https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html (read 2026-08-21);
https://portswigger.net/web-security/graphql (read 2026-08-21)

### 14. Framework and edge authorization bypass via internal headers and URL spelling

Authorization written in a middleware or at an edge is bypassable when the
application trusts an internal marker or when two components disagree about what
the URL says. The 2025 example everyone hit is Next.js CVE-2025-29927: adding
`x-middleware-subrequest` makes the middleware, and therefore the auth check in
it, not run. The older forms still land: `X-Original-URL` / `X-Rewrite-URL`
against a front-end path rule, and case, trailing-slash or extension variants
that the proxy rule misses and the router still resolves. Orange Tsai's Apache
"confusion attacks" (PortSwigger's #1 technique of 2024) is the deep version of
the same idea.

Belongs in: `deployment` (`authorization.edge_rule`) already owns the edge half;
the framework-internal-header half wants a step there or in the proposed
`function-authorization`. Our cluster's job is only to route it correctly.

Our playbook would have to observe: the framework and version fact, the fact that
a route is refused for the current Identity, and a header-injection arm that is
one header per request against a stable refusal baseline.

Sources: https://portswigger.net/research/top-10-web-hacking-techniques-of-2024 (2025-02-04, ranks Orange Tsai's confusion attacks #1);
https://blog.orange.tw/posts/2024-08-confusion-attacks-en/ (2024-08, search result only, not fetched);
https://jfrog.com/blog/cve-2025-29927-next-js-authorization-bypass/ and https://securitylabs.datadoghq.com/articles/nextjs-middleware-auth-bypass/ (2025, search results only, not fetched; both describe the `x-middleware-subrequest` bypass and the fixed versions 12.3.5 / 13.5.9 / 14.2.25 / 15.2.3)

### 15. Predictable identifiers as the enabling step

Every playbook in this cluster assumes the object identifier of the other
Identity is already known. On a real program that is the hard part, and it is
also a finding in its own right when the identifier is guessable: sequential
integers behind a base64 or hex wrapper, a hash of a sequential integer, and
UUIDv1, whose first three groups are a timestamp and whose last two are stable
per host -- so an attacker who can cause a UUID before and after the victim's
can interpolate ("sandwich attack"). OWASP's API1 guidance recommends GUIDs,
which is exactly why the version of the GUID matters. Our `api-authorization`
already lists `uuids.md` as a reference, so the knowledge is in the tree but no
step acts on it.

Belongs in: `object-ownership` (a step 1b that classifies the identifier before
the comparison, and records "identifier is predictable" as its own observation).

Our playbook would have to observe: several identifiers of the same object type
issued to our own Identity, their encoding, and (for UUIDs) the version nibble
and the node/clock-sequence groups.

Sources: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/ (2023 edition, recommends unpredictable GUIDs);
https://book.hacktricks.xyz/pentesting-web/uuid-insecurities and https://github.com/Lupin-Holmes/sandwich (search results only, not fetched; describe UUIDv1 structure and the sandwich tool)

### 16. Unrestricted access to sensitive business flows, at bounded scale

OWASP added API6:2023 for the flows that are individually authorized and
catastrophic in bulk: scalping limited stock, mass account creation for referral
credit, booking and cancelling to move a price, consuming a shared tenant quota.
Our harness has `rate_limiting.per_identity` (the `api` playbook), which asks
whether repetition is bounded at all, but nothing asks whether the *flow* is
protected in the way the business needs, which is a different question with a
different invariant (the business rule, not a 429).

Belongs in: **new playbook: `business-flow-abuse`**, or an arm of
`payment-workflows`; it should reuse the `api` playbook's declared-budget
discipline.

Our playbook would have to observe: the flow's own published limit (one per
customer, N per household, stock count), the authoritative counter, and a
declared small N with an explicit stop, because the honest version of this
reading demonstrates absence of a control rather than exhausting the resource.

Sources: https://owasp.org/API-Security/editions/2023/en/0xa6-unrestricted-access-to-sensitive-business-flows/ (2023 edition)

### 17. The audit view as a discovery oracle, and the unlogged action as a finding

`logging` asks one good question (does the activity view carry another caller's
request data) and stops. Two adjacent readings are cheap once we are already
there. First, the view is a *discovery* instrument even when correctly scoped:
it names internal route paths, job names, admin actor emails, and object
identifiers that feed every other playbook in this cluster, and the harness
should promote those to the Surface rather than discard them. Second, on SaaS
programs with a compliance story, a security-relevant action that produces *no*
audit entry (a permission grant, an API key issue, a data export, an SSO config
change) is itself a reportable control gap; OWASP has carried the category since
A09:2021. That reading is the exact mirror of the current one: perform an
entitled action as label B and show the view is silent, with a second entitled
action that does appear as the control.

Belongs in: `logging` (a promotion step and a coverage-gap arm). The coverage-gap
arm must stay firmly on the "did the target record it" side and must never turn
into evasion, which step 7 already forbids and should keep forbidding.

Our playbook would have to observe: the set of actions the view does record (the
control), one security-relevant action the Identity is entitled to perform, and
a delay tolerance, because audit pipelines are asynchronous.

Sources: https://owasp.org/Top10/A09_2021-Security_Logging_and_Monitoring_Failures/ (2021 edition; the page redirected and its body could not be fetched, so nothing beyond the category's existence and name is claimed here);
https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/ (2023 edition, for the excess-property half of what a view returns)

### 18. Race hygiene: warming, session locks, and retry distribution

Not a bug class, a validity requirement, and our `race-conditions` playbook
currently has none of it. Three specific things. Connection warming: send an
inconsequential request on the connection first, because the first request on a
new connection pays a server-side setup cost that dwarfs the race window and
makes a negative meaningless. Session locking: many frameworks serialise
requests that share a session, so a "refuted" reading may only mean the two
copies were never concurrent; the check is to re-run with two distinct session
tokens for the same account where the target allows it. Retry distribution: a
real race is 50/50 or otherwise stable across retries while a random error is
not, so a single pair that shows nothing is not a refutation.

Belongs in: `race-conditions` (a step 4a and a stated retry policy).

Our playbook would have to observe: per-request send and receive timestamps
recorded by the proxy, whether the two copies shared a connection, and whether
the target's session handling serialises them.

Sources: https://portswigger.net/web-security/race-conditions (read 2026-08-21);
https://portswigger.net/research/smashing-the-state-machine (2023-08-09)

## What in our playbooks looks stale or weak

* **`race-conditions` cannot say how its pair is emitted.** Step 4 says "send two
  identical copies of the action at once through the same slot" and nothing
  about jitter, connection reuse, warming, retries, or what "at once" means for
  a request that traverses an intercepting proxy. Against a target where the
  race window is a single database round trip, an unsynchronised pair will
  simply be refuted, and the playbook has no way to distinguish "no race" from
  "we never raced". This is the single weakest step in the cluster.
* **`race-conditions` is limited to one class.** "Replay" as its only output
  covers Kettle's limit-overrun and nothing else; three of the five classes he
  named are not expressible. The two-request cap is right for money and wrong
  for a coupon: limit overrun on a non-money item usually needs more than two
  copies to land at all.
* **`object-ownership` treats a single refusal as a refutation.** No carrier
  variation, no method variation, no after-state read, no identifier
  classification, no tenant dimension, and no GraphQL arm. It is a correct
  reading of the 2015 version of the bug.
* **`payment-workflows` is one number, one order.** No coupon sequence, no
  currency, no inbound callback, no capture-window TOCTOU. Step 4's "one edit
  per reading" is the right discipline and the wrong granularity: the modern
  defects are sequences of individually legal operations.
* **`orm` stops one step before the impact.** The name-versus-fictional-name
  control is excellent and then the playbook forbids the operator axis entirely.
  As written it would have found the *shape* of elttam's Django finding and not
  the finding. It also cannot express the Prisma type-coercion case, because it
  only sends names in a query parameter and never a JSON object where a string
  was expected.
* **`orm`'s six-request repeat policy is expensive and its trigger is narrow.**
  `tech_orm` requires a technology fingerprint that black-box recon often will
  not have; the filter-syntax facts (a double underscore, a bracket, a `$`) are
  the better trigger and are observable from the surface itself.
* **`logging`'s trigger is too narrow.** `tech_telemetry` gates the playbook on a
  backend fingerprint that step 1 then correctly says is not evidence. Plenty of
  applications have an activity or audit view with no fingerprintable telemetry
  stack. The presence of an activity-shaped route is the real precondition.
* **`logging` places its marker in a query parameter only.** Audit trails
  commonly record actor, target, body fields and user-agent rather than the
  query string, so a negative reading may only mean the marker was in a field
  the view does not record. The marker should go where the control leg shows the
  view actually records.
* **`api-authorization` is excellent and under-used.** Its four-call structure
  (owner control, foreign-owner control, nonexistent control, variant) is the
  best pattern in the cluster and only `api-authorization` uses it. The
  nonexistent control in particular belongs in `object-ownership`.
* **The vocabulary has no object-property leaf.** With `injection.object_graph`
  meaning deserialization, there is nowhere to file a mass-assignment finding,
  which is probably why no playbook attempts one.
* **`multiple_test_identities` is one flat fact.** It cannot say whether the
  second Identity is a second user in the same tenant, a lower-privileged role
  in the same tenant, or a user in a different tenant. Those are three different
  experiments and today the runtime cannot tell a playbook which one it has.

## Concrete change proposals per playbook

* **`src/redkraken/playbooks/object-ownership/playbook.md`** -- add a step 1b
  ("classify the identifier": encoding, sequence, UUID version, recorded as an
  observation not a claim), a step 3b ("re-spell the identifier": one request
  each moving the ID to another carrier the endpoint accepts, duplicating the
  parameter, and wrapping it in a one-element array, all under label B against a
  stable refusal baseline), a step 4b ("read the after-state as label A") for
  blind and write-shaped variants, and rewrite step 2 to add
  `api-authorization`'s nonexistent-identifier control so a `404` cannot be
  mistaken for a decision. Add a tenant arm or split it into `tenant-isolation`.
* **`src/redkraken/playbooks/api-authorization/playbook.md`** -- add a step 3d
  that sends the same transition under a *lower-privileged role in the same
  tenant* and under a *changed method* on the same path, so the playbook can
  route a `function_access` finding with evidence instead of only naming it as a
  neighbour; and add a tenant-selector arm (same transition, second tenant named
  in the selector, own session unchanged) that routes to
  `authorization.tenant_isolation`.
* **`src/redkraken/playbooks/payment-workflows/playbook.md`** -- rewrite step 4
  from "one number moved" to "one declared shape", with four named shapes: the
  existing single-number edit, a coupon sequence (same code twice, two codes in
  one order, code then downgrade), a currency or minor-unit substitution read
  against the total's stated currency, and an inbound provider-callback probe
  that carries a deliberately non-granting payload. Keep step 7's refusal to
  complete a purchase unchanged; extend it to cover the callback arm.
* **`src/redkraken/playbooks/race-conditions/playbook.md`** -- add a step 4a
  ("warm the connection and check for a session lock") and rewrite step 4 to
  name four variant shapes: the existing identical pair, a multi-endpoint pair
  (two routes over one record), a single-endpoint pair carrying different
  values, and a deferred pair (two operations minutes apart that a batch job
  reconciles). State a retry policy (a refutation needs the pair repeated, and a
  50/50 outcome distribution is the positive signal) and a GraphQL substitute
  arm (N aliases in one request) for surfaces where the transport cannot
  synchronise. Raise the cap from two to a declared N for non-money items while
  keeping the money refusal absolute.
* **`src/redkraken/playbooks/orm/playbook.md`** -- add a step 3b that varies the
  *operator* as well as the field (`__startswith`, `__contains`, `__gt`, a regex
  suffix, or the framework's equivalent) against the same fictional-name control,
  and a step 5 rewrite that permits a bounded oracle: confirm one boolean or one
  leading character, record the request cost and the extraction rate the defect
  implies, and stop. Add a JSON-object-where-a-string-was-expected arm for
  Prisma-shaped stacks, and widen the trigger from `tech_orm` alone to the
  filter-syntax surface facts.
* **`src/redkraken/playbooks/logging/playbook.md`** -- add a step 3b that places
  the marker in whichever carrier the control leg proves the view records (body
  field, actor name, user-agent) rather than only a query parameter; add a step
  6b that promotes route paths, job names and object identifiers found in the
  view to the Surface as discovery rather than as a claim; and add a coverage-gap
  arm (an entitled security-relevant action that produces no entry, against an
  entitled action that does) with an explicit restatement of step 7's refusal of
  anything resembling evasion. Widen the trigger from `tech_telemetry` to the
  presence of an activity-shaped route.
* **Adjacent file `src/redkraken/playbooks/graphql/playbook.md`** -- add a
  relation-traversal arm (reach an object from an edge you own) and a
  `node(id:)`/`nodes(ids:)` arm, and route object-level findings to
  `authorization.object_ownership` rather than reporting them as excess fields.
* **Adjacent file `src/redkraken/playbooks/workload-identities/playbook.md`** --
  keep it as the machine-credential reading, and add a line routing
  user-identity cross-tenant findings to the new tenant playbook so the two do
  not both try to own `authorization.tenant_isolation`.
* **New playbook `src/redkraken/playbooks/mass-assignment/playbook.md`** -- GET
  the object, resend its own body with one property added, read the after-state
  under the owner, with a nonexistent-property control that separates "accepted
  and stored" from "accepted and ignored"; needs a new object-property leaf in
  the vocabulary.
* **New playbook `src/redkraken/playbooks/function-authorization/playbook.md`** --
  the HTTP sibling of `grpc`: method swap and administrative-sibling route,
  against a same-tenant lower-privilege Identity, emitting
  `authorization.function_access`.
* **New playbook `src/redkraken/playbooks/tenant-isolation/playbook.md`** (or a
  second output on `object-ownership`) -- the same request, same session, second
  tenant named in whichever carrier selects the tenant, with the owning tenant's
  own read as the control.

## What needs two identities, and what the harness must provide

Three different pairings are needed and the harness currently models one.

**Needs two users in the same tenant (what we have today).** Today's
`object-ownership`, today's `api-authorization` foreign-owner control, today's
`logging`, today's `graphql` field diff, the blind-IDOR after-state read, the
carrier-variation arm, and the relation-traversal arm.

**Needs two roles in one tenant (admin/owner versus member/viewer).** The
proposed `function-authorization` playbook, the method-swap arm of
`api-authorization`, the mass-assignment role-escalation arm, the
administrative-sibling route walk, and the logging coverage-gap arm (because the
action whose audit entry is missing is usually an administrative one).

**Needs two tenants (two separate organisations the Program provisioned).**
Cross-tenant BOLA, the tenant-selector arm, tenant-scoped cache and audit leaks,
and any reading whose impact statement is "another customer's data".

**Needs only one identity.** ORM leak and its operator oracle, price and
currency edits, coupon sequences, limit-overrun races, business-flow abuse, and
the inbound webhook probe.

What the harness has to hand the agent for a reading to be admissible:

1. **Tenant and role labels on Identity slots.** A slot needs to say which tenant
   it belongs to and what role it holds inside it, and the surface-fact
   vocabulary needs to distinguish `second_user_identity`,
   `second_role_identity` and `second_tenant_identity` where it today has only
   `multiple_test_identities`. Without this the runtime cannot schedule the
   right experiment and a playbook cannot state which one it ran.
2. **An owned-object inventory per Identity.** The victim object must be named
   from label A's own authoritative read, not guessed, and the report must be
   able to cite that read. This is what makes "we accessed another user's
   object" admissible rather than "we accessed an object".
3. **The nonexistent-identifier generator.** A well-formed identifier of the same
   shape that names nothing, per object type, so the `404`-versus-`403` control
   is cheap enough that every playbook uses it.
4. **Per-request send and receive timestamps from the proxy, plus connection
   identity.** Race readings are not admissible without evidence that the two
   copies were actually concurrent and whether they shared a connection.
5. **A concurrency emitter with a declared N.** The runtime, not the model, should
   emit the parallel group, so the footprint is bounded and recorded.
6. **A raw-request escape hatch, or an explicit statement that there is none.**
   See the safety section: several techniques need bytes the proxy re-encodes.
7. **A program-controlled mailbox and a program-controlled second tenant.** Every
   invitation, referral, password-reset and callback reading needs a destination
   that belongs to the engagement.
8. **The published rules as data.** `payment-workflows` step 1 already demands an
   invariant from the target's own published numbers; the mission packet should
   carry them (plan limits, coupon terms, stock counts) rather than making each
   run re-derive them.

## Safety limits worth keeping

Every technique below would, executed literally, move money, destroy data, or
touch a party outside the engagement. Each gets a substitute that produces the
same evidential claim.

* **Racing a withdrawal, payout, transfer or refund.** Real money moves and it
  may not be recoverable. Substitute: race a non-money single-use item (a coupon,
  an invite, a seat) and report the class; where the only single-use action is
  monetary, stop at the sequential control and report that the invariant exists
  and was not tested. `race-conditions` step 7 already says this and it must
  survive the rewrite.
* **Completing a purchase to prove a price defect.** Substitute: the
  authoritative computed total, quote or invoice preview, which exists before
  capture. `payment-workflows` step 7 already says this.
* **Forging a payment-provider webhook that credits an account.** This creates
  fraudulent entitlements and may corrupt the merchant's reconciliation.
  Substitute: send the callback with a payload that names a non-existent
  event/charge identifier and cannot grant anything, and read only the
  authentication decision (does an unsigned request reach the handler at all)
  plus the account's own unchanged balance as proof nothing was credited. If the
  program supplies provider test-mode keys, use those instead and say so.
* **A refund, chargeback or subscription cancellation as a test step.** Notifies
  a merchant and a payment processor and appears in someone's books. Substitute:
  read the refund quote or the cancellation preview; if the target offers no
  preview, the reading stops.
* **Sending `DELETE` or a destructive verb during a function-authorization
  sweep.** Substitute: order the verbs from safest to least safe, run the
  destructive verb only against an object the testing Identity created for the
  purpose, and never against another Identity's or another tenant's object. A
  `405` versus `403` distinction is usually available from `OPTIONS` and from
  non-destructive verbs alone.
* **Writing into another tenant.** Substitute: cross-tenant readings are read
  only. Where a write is the only way to show impact, write into a second object
  the *same* Identity owns, and demonstrate the missing tenant clause by showing
  the cross-tenant read succeeded.
* **Mass assignment that re-parents an object to another tenant or user**
  (`owner_id`, `tenant_id`, `account_id` pointed at a real third party). This
  steals a real record. Substitute: point the property at a second object the
  testing Identity owns, or at a well-formed nonexistent identifier, and show
  the property was accepted and stored.
* **Self-escalation via mass assignment (`role: admin`).** Acceptable on a
  harness-owned account, but it is a privilege the engagement then holds.
  Substitute discipline rather than refusal: do it on the testing account only,
  record it, and reverse it through the target's own route if one exists; never
  escalate a second tenant's account.
* **Full extraction through an ORM oracle.** Dumping a password hash or a column
  is bulk exfiltration of real user data. Substitute: confirm one boolean or one
  leading character, state the request cost and the implied extraction rate, and
  stop. `orm` step 5's refusal stays; only its ceiling moves.
* **The UUID sandwich attack in its usual form** (issue password resets around
  the victim's to bracket the timestamp). This sends real password-reset mail to
  a real person. Substitute: bracket using objects the harness itself creates in
  its own accounts, and classify the identifier from those; never trigger a
  reset for an address the engagement does not control.
* **Business-flow abuse at real scale** (mass registration, stock exhaustion,
  booking-and-cancelling to move a price). This is the abuse itself. Substitute:
  a small declared N that shows the control is absent, an explicit stop, and a
  report that states what an unbounded actor could do rather than doing it.
* **Consuming a shared or another tenant's quota** (seats, API credits, stock).
  Substitute: measure against our own tenant's quota only, and name the quota
  spent in the report the way `race-conditions` step 7 already names the coupon.
* **Real invitations to real addresses during limit-overrun testing.**
  Substitute: invite an address the engagement controls, and revoke it.
* **Log forging, log fetching, and alerting evasion.** Keep `logging` step 7
  exactly as it stands. The new coverage-gap arm asks whether the target recorded
  an action; it never tries to make the target not record one, never varies a
  marker to defeat correlation, and never strips an engagement-identifying
  header.
* **Byte-level race framing through our proxy (the harness-specific limit).**
  The single-packet attack requires HTTP/2 multiplexing with the final frame of
  each request withheld and then released so the operating system coalesces them
  into one TCP packet (roughly 20-30 requests, bounded by the ~1500-byte packet
  limit). An intercepting proxy that terminates and re-encodes requests will
  re-frame them, and the synchronisation is lost; RyotaK's first-sequence-sync
  extension is further out of reach still, since it manipulates TCP sequence
  numbers, uses IP fragmentation, and needs iptables-level control to suppress
  RSTs. Neither is a safety refusal, it is a capability we do not have.
  Substitutes, in the order to try them: the deferred-collision shape (needs no
  timing precision at all), the GraphQL alias/batch shape (N operations inside
  one request, so the concurrency is the server's), and a plain parallel group
  with warming plus retries, which still lands on targets whose race window is a
  network round trip rather than a microsecond. If we want the real technique,
  the harness would need a raw-socket sending mode that bypasses the intercepting
  proxy for a declared request group, with the proxy recording rather than
  rewriting, and per-request timestamps captured at the socket. There is a
  precedent in the tree to build on rather than invent: ticket 93
  (`docs/specs/production-harness-v2/issues/93-take-the-unintercepted-transport-measurement.md`,
  status resolved) already establishes an unintercepted lane in which the proxy
  process opens the connection itself under the same scope decision, the same
  per-target concurrency slot and the same token bucket, and writes a receipt
  with `intercepted = false`. That lane exists to measure TLS, not to emit
  frames, but it is the same shape a synchronised race group would need and it
  settles the scope-and-budget questions such a group would otherwise reopen.

## Sources consulted

Fetched and read:

* https://portswigger.net/research/top-10-web-hacking-techniques-of-2025 (published 2026-02-05) -- ranked list for 2025; source of the ORM-leak follow-up at #2 and the Next.js cache chain at #7, and evidence that no pure access-control research made the 2025 top ten.
* https://portswigger.net/research/top-10-web-hacking-techniques-of-2024 (published 2025-02-04) -- ranked list for 2024; Orange Tsai's Apache confusion attacks at #1 and three OAuth/cache access-control entries at #8, #9, #10.
* https://portswigger.net/research/top-10-web-hacking-techniques-of-2023 (published 2024-02-19) -- ranked list for 2023; confirms Kettle's race-condition work took #1.
* https://portswigger.net/research/smashing-the-state-machine (2023-08-09, updated 2023-09-18, James Kettle) -- the five race classes (limit overrun/object masking, multi-endpoint, single-endpoint, deferred, partial construction), the predict-probe-prove methodology, connection warming, session-based locking, and the benchmark-first discipline.
* https://portswigger.net/research/the-single-packet-attack-making-remote-race-conditions-local (2023-10-18, James Kettle) -- exact client-side requirements of the single-packet attack: HTTP/2 multiplexing, withheld final fragments, OS coalescing into one TCP packet, ~1500-byte soft limit, 20-30 requests.
* https://portswigger.net/blog/new-techniques-and-tools-for-web-race-conditions (2023-08-10, Emma Stocks) -- tooling context: Burp Repeater parallel send and Turbo Intruder gained single-packet support.
* https://flatt.tech/research/posts/beyond-the-limit-expanding-single-packet-race-condition-with-first-sequence-sync/ (2024-08-02, RyotaK, GMO Flatt Security) -- first sequence sync; 10,000 requests in ~166ms, and the TCP sequence manipulation, IP fragmentation and iptables control it needs, which is what puts it out of our transport's reach.
* https://portswigger.net/web-security/race-conditions (Web Security Academy, read 2026-08-21) -- the teaching version of the above with the observables per class, plus connection warming and session-lock bypass as explicit steps.
* https://portswigger.net/web-security/access-control (read 2026-08-21) -- verb tampering, parameter-based controls, `X-Original-URL`/`X-Rewrite-URL`, URL-matching discrepancies, referer-based controls, multi-step process bypass.
* https://portswigger.net/web-security/logic-flaws (read 2026-08-21) -- domain-specific logic flaws, unconventional input, flawed assumptions about which parameters stay constant.
* https://portswigger.net/web-security/graphql (read 2026-08-21) -- alias-based rate-limit bypass, schema recovery via field suggestions when introspection is off, IDOR through query arguments.
* https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html (read 2026-08-21) -- "enforce authorization checks on both edges and nodes", batching as an enumeration and brute-force multiplier, unintended `node`/`nodes` object access.
* https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/ (2023 edition) -- BOLA definition, the vehicle-VIN and shop-revenue scenarios, and the GUID recommendation that makes UUID version a live question.
* https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/ (2023 edition) -- BOPLA, the merge of mass assignment and excessive data exposure, and the `total_stay_price` and `blocked: false` scenarios.
* https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/ (2023 edition) -- BFLA, the GET-to-POST swap on an invites endpoint, administrative path guessing.
* https://owasp.org/API-Security/editions/2023/en/0xa6-unrestricted-access-to-sensitive-business-flows/ (2023 edition) -- scalping, ticket price manipulation and referral fraud as an API risk class distinct from rate limiting.
* https://www.elttam.com/blog/plormbing-your-django-orm/ (2024-06-23, Alex Brown) -- the four preconditions for an ORM leak, the operator suffixes, relation traversal via double underscores, the affected projects elttam lists (Strapi CVE-2023-22894, CVE-2023-36472, CVE-2024-29181, Label Studio, Ghost, Payload CMS, Ransack), and the `plormber` tool.
* https://www.elttam.com/blog/leaking-more-than-you-joined-for/ (2025-12-18, Alex Brown) -- the generalisation: Beego expression-parser denylist bypass, `gt`/`lt` collation oracles, OData `$expand`, Prisma type coercion from JSON in URL, body or cookie.
* https://lightningsecurity.io/blog/bypassing-payments-using-webhooks/ (2018-03-13, Jack Cable) -- unauthenticated payment-provider callbacks; older than our three-year window and still the live failure mode.
* https://securityscanner.dev/blog/stripe-webhook-signature-bypass-1500-apps (2026-05-05) -- 1,542 of 6,000 scanned applications answered 2xx to an unsigned Stripe-shaped event across 17 candidate paths, with the authors' own caveat that a 2xx does not prove a credit.
* https://securityboulevard.com/2025/12/tenant-isolation-in-multi-tenant-systems-architecture-identity-and-security/ (2025-12-30, SSOJet) -- concrete tenant-isolation failure modes: missing `WHERE tenant_id`, background jobs without tenant context, unvalidated tenant claims, shared SSO metadata and keys, session scope across subdomains.
* https://zhero-web-sec.github.io/research-and-things/nextjs-cache-and-chains-the-stale-elixir (2025-01, Rachid Allam) -- CVE-2024-46982: SSR responses misclassified as SSG and cached, exposing authenticated users' data; adjacent to this cluster and belongs to `web-cache`, noted here because its impact reads as a cross-user authorization failure.

Failed or unfetched, and named as such:

* https://cablej.io/blog/bypassing-payments-using-webhooks/ -- fetch failed, TLS certificate does not match the host; read on `lightningsecurity.io` instead.
* https://owasp.org/Top10/A09_2021-Security_Logging_and_Monitoring_Failures/ -- returned only a redirect notice; nothing beyond the category's existence is claimed from it.
* https://blog.orange.tw/posts/2024-08-confusion-attacks-en/, https://jfrog.com/blog/cve-2025-29927-next-js-authorization-bypass/, https://securitylabs.datadoghq.com/articles/nextjs-middleware-auth-bypass/, https://samcurry.net/web-hackers-vs-the-auto-industry, https://book.hacktricks.xyz/pentesting-web/uuid-insecurities, https://github.com/Lupin-Holmes/sandwich -- seen in search results with titles and summaries but not fetched; used only for the narrow facts attributed to them above.
* Intended and never reached, because the session's web-search budget ran out: Salt Labs, Doyensec, Assetnote/Searchlight, and individual HackerOne, Bugcrowd and Intigriti disclosure pages. The ranked list above is therefore grounded in vendor-neutral research and standards rather than in disclosed-report volume, and a follow-up pass over public disclosures would be the right way to re-rank items 9 through 17 by observed payout.
