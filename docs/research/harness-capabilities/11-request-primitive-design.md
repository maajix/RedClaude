# 11 - What a request primitive must carry

Written against this worktree. Every claim about our own code carries
`file:line` and was read there; where a fact could not be found the text says
"not found". Every external claim carries a URL that was fetched, and where a
page would not fetch, or came back paraphrased rather than quoted, this
document says so rather than dressing the gap up.

Framing throughout is authorized testing of a Program's own scope. Nothing
below proposes a field whose only use is against a target nobody authorized.
The whole point of the exercise is the opposite: to work out the smallest
request surface that can find real bugs and to write down, field by field, what
each addition costs us in auditability.

## What ours carries today, and what that forbids

`mcp__rk2__http_request` is a `Contract` with exactly three arguments
(`src/redkraken/roster.py:738-767`):

| argument | shape | constraint |
| --- | --- | --- |
| `method` | string, required | enum of seven: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS (`roster.py:743-747`) |
| `url` | string, required | `^https?://` (`roster.py:748`) |
| `headers` | object, optional | names `^[A-Za-z][A-Za-z0-9-]{0,63}\Z`, values `^[\x20-\x7e]{0,1024}\Z` (`roster.py:753-757`) |

There is no fourth. The schema is served closed -- `additionalProperties:
false` (`roster.py:412-421`) -- and the gate re-checks the same statement
afterwards, refusing any name the contract does not declare
(`roster.py:1393-1395`). The contract itself records why the two missing fields
are missing (`roster.py:758-765`): "the child has no store, so it cannot name a
body the door could send, and the runtime opens the Tool run with the identity
already chosen and the capability already minted".

The chain from the tool call to the socket is short and every link drops
something:

* the handler passes exactly three values through
  (`src/redkraken/_launch.py:627-635`), and coerces the headers to a
  `dict[str, str]` (`_launch.py:768-778`);
* `_spend` calls `proxy.spend` (`_launch.py:706-714`), whose signature has no
  body parameter (`src/redkraken/proxy.py:3897-3907`);
* `_through` sends it with `client.request(method, url, headers={...})` on
  plain HTTP (`proxy.py:3968`) and `client.request(method, origin_form(url),
  headers=carried)` inside the tunnel (`proxy.py:3987`), where `carried` is
  again a dict (`proxy.py:3995-4006`);
* what comes back is truncated to `packet.DEFAULT_EXCERPT`, which is 4096 bytes
  (`src/redkraken/packet.py:60`), with `byte_size` and `truncated` alongside it
  (`_launch.py:725-735`).

So the primitive forbids, today: any bytes after the headers; two headers with
the same name, or any control over the order they go in; any choice of HTTP
version, because ALPN is pinned to `http/1.1` on the door's client
(`proxy.py:1999-2005`, `proxy.py:2017-2020`) and on the certificate the door
presents (`src/redkraken/tls.py:77-81`), and the request line is written
`HTTP/1.1` literally (`proxy.py:2701`); any timeout other than the door's 30
seconds (`proxy.py:322`, and `spend`'s unused `timeout` parameter at
`proxy.py:3905`); any redirect policy, because the door deliberately does not
follow one and only records where it pointed (`proxy.py:3014-3033`); any cookie
control beyond a `Cookie` header that a bound Identity overwrites
(`src/redkraken/identity.py:319-329`); and any repetition, because one call is
one exchange and the connection is closed in a `finally`
(`proxy.py:2507-2528`).

The important half of this section is what already exists on the far side of
the boundary. The gap is the contract and the in-container client, not the
door:

* **The door already reads request bodies.** `_body` refuses a chunked body,
  reads `Content-Length` and caps it at `CEILING`
  (`proxy.py:2394-2409`); `CEILING` is 32 MiB (`proxy.py:328`).
* **It already re-measures and re-frames.** `content-length` and
  `transfer-encoding` are hop-by-hop here (`proxy.py:288-303`), stripped from
  what arrives, and a measured `Content-Length` is added back when there is a
  body (`proxy.py:2693-2694`).
* **It already writes headers in order, with duplicates.** The forward loop is
  `putheader` per pair rather than a mapping, and the comment says why: "a
  caller who sent two `Cookie` lines would have one of them dropped on the wire
  while the Receipt named both" (`proxy.py:2508-2521`).
* **It already hashes the body as part of the message.** `transcript` is the
  start line, the headers and the body concatenated (`proxy.py:789-798`), and
  `sent`, `wire_sent` and `wire_received` are built from it
  (`proxy.py:2829-2831`), stored (`proxy.py:2886-2887`) and named on the
  Receipt by hash (`proxy.py:3054-3061`).
* **The approval machinery already reads a `body` argument that does not
  exist.** `canonical_request` emits `body_keys` from `p_args -> 'body'` when
  it is a JSON object
  (`src/redkraken/migrations/0026_human_control.sql:183-186`) and
  `identity_slot` from `p_args ->> 'identity_slot'` (same file, `:178`).

Two of our three "missing" fields are therefore not missing from the system.
They are missing from the one statement that decides what a model may say.

## Field by field

### Body

**What it is.** Bytes after the headers, framed by `Content-Length` or
`Transfer-Encoding`. RFC 9112 §6.3 states the precedence and the danger in one
place: "If a message is received with both a Transfer-Encoding and a
Content-Length header field, the Transfer-Encoding overrides the Content-Length.
Such a message might indicate an attempt to perform request smuggling (Section
11.2) or response splitting (Section 11.1) and ought to be handled as an error."
§11.2 defines the class: "Request smuggling ... is a technique that exploits
differences in protocol parsing among various recipients to hide additional
requests (which might otherwise be blocked or disabled by policy) within an
apparently harmless request."

**Which bug classes need it.** Everything whose reading is a document sent to
the server. GraphQL, gRPC, JSON APIs, SQL and NoSQL injection through a POST
body, deserialization, SSTI, mass assignment, file upload, webhook
registration, and every authentication test that has to submit credentials.
OWASP's mass assignment cheat sheet gives the canonical shape: appending
`&isAdmin=true` to a body that carried `userid`, `password`, `email`. In our
corpus this is not a hypothetical: `playbooks/graphql/playbook.md:43` and
`playbooks/grpc/playbook.md:50` instruct the agent to send a document it has no
argument to carry.

**What it would cost us.**

1. *The gate's forbidden-name scan is shaped against structured bodies.*
   `_forbidden_argument` walks every argument at every depth and refuses
   `password`, `token`, `secret`, `authorization`, `sql`, `statement` and nine
   other names (`roster.py:229-244`, `roster.py:1291-1321`). A `body` declared
   as an `object` carrying `{"username": ..., "password": ...}` -- the single
   most common POST in web testing -- would be denied by the gate. A `body`
   declared as a `string` is never scanned at all, because `_scan` returns
   immediately for anything that is not a `Mapping`, `list` or `tuple`
   (`roster.py:1334-1335`). That is a strong argument for a raw string body in
   phase 1 and for `free_text` plus an `OPEN_ARGUMENTS` entry
   (`roster.py:545-555`, `roster.py:1773-1774`) if a structured body is ever
   wanted.
2. *The approval digest cannot tell two raw bodies apart.* `canonical_request`
   derives `body_keys` only from an object body (`0026:183-186`), sets
   `reusable: true` for this tool (`0026:172`), and `equivalence_key` is the
   sha256 of that document (`0026:193-196`). Two different string bodies to the
   same path template therefore produce the same key, so one human approval
   covers both. This is a hole that opens the moment a raw body exists, and it
   is named again under "Write safety".
3. *Desync testing stays out of reach, by construction.* The door strips both
   length headers (`proxy.py:288-303`) and re-measures
   (`proxy.py:2693-2694`), and refuses a chunked body outright with the reason
   written down: "a proxy that re-chunks is recording bytes that differ from
   the ones it read" (`proxy.py:2394-2402`). A body whose declared framing
   disagrees with its bytes cannot survive this door. That is a cost for the
   `http-desync` playbook and a safety property for everything else, and it
   should be stated as a deliberate refusal rather than discovered as a bug.
4. *Bytes in the model's context.* The door's ceiling is 32 MiB
   (`proxy.py:328`); a tool argument is a different thing from a stored
   artifact and wants a far smaller bound.

Sources:
- [RFC 9112 §6.3, §11.2](https://www.rfc-editor.org/rfc/rfc9112.html)
- [PortSwigger: HTTP request smuggling](https://portswigger.net/web-security/request-smuggling)
- [OWASP Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html)
- [mitmproxy HTTP API: `raw_content` vs `content`](https://docs.mitmproxy.org/stable/api/mitmproxy/http.html)
- [Burp message editor: raw and hex views](https://portswigger.net/burp/documentation/desktop/tools/message-editor)

### Content type

**What it is.** The header that tells the server how to parse the bytes, held
separately from the bytes themselves. Burp treats this as a body *encoding*
rather than a header edit: "You can change the encoding of any request body.
Choose from the following options: Toggle body encoding, Form URL-encoded,
Multipart, JSON." mitmproxy treats it as a gate on the parsed views:
`urlencoded_form` is "set to an empty MultiDictView" when "the content-type
indicates non-form data".

**Which bug classes need it.** The bugs are in the mismatch, so the field
matters most when it is *wrong*. CSRF through simple content types: the Fetch
Standard's CORS-safelisted request-header rule is "If mimeType's essence is not
`application/x-www-form-urlencoded`, `multipart/form-data`, or `text/plain`,
then return false", and OWASP restates it as "For a request to be deemed
simple, it must have one of the following content types". A framework that
parses JSON out of a `text/plain` body has a CSRF hole; CVE-2022-41919 in
Fastify (GHSA-3fjj-p79j-c9hh) is exactly that, incorrect Content-Type parsing
that "could potentially be used to invoke routes that only accepts
`application/json`". XML bodies reach XXE, "an attack against applications that
parse XML input". Sending JSON as form data and form data as JSON is how
parser-confusion and filter-bypass findings are made.

**What it would cost us.** Almost nothing. `content-type` is not in
`HOP_BY_HOP` (`proxy.py:288-303`), so a header the agent sets is forwarded
unchanged. It should not become its own argument: making it a header keeps one
statement of one field, keeps the existing name and value patterns
(`roster.py:753-757`) doing the constraining, and keeps "send a body with no
Content-Type at all" expressible, which is itself a test case. The one thing
the contract must *not* grow is a settable `Content-Length`: the door owns that
number (`proxy.py:2693-2694`) and an argument for it would be a promise the
door drops.

Sources:
- [Fetch Standard, CORS-safelisted request-header](https://fetch.spec.whatwg.org/)
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [Fastify GHSA-3fjj-p79j-c9hh / CVE-2022-41919](https://github.com/fastify/fastify/security/advisories/GHSA-3fjj-p79j-c9hh)
- [OWASP XXE Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html)
- [Burp message editor: body encoding](https://portswigger.net/burp/documentation/desktop/tools/message-editor)
- [mitmproxy HTTP API: `urlencoded_form`](https://docs.mitmproxy.org/stable/api/mitmproxy/http.html)

### Multipart

**What it is.** A body of parts, each with its own `Content-Disposition` and
optional `Content-Type`, separated by a caller-chosen boundary. RFC 7578 §4.1
requires that "the boundary delimiter MUST NOT appear inside any of the
encapsulated parts", and §4.2 says "For form data that represents the content
of a file, a name for the file SHOULD be supplied as well, by using a
`filename` parameter of the Content-Disposition header field."

**Which bug classes need it.** File upload validation. PortSwigger's academy
material names the primitives a tester has to control: per-part Content-Type
that "is implicitly trusted by the server", double extensions such as
`exploit.php.jpg`, traversal sequences in the filename, and separator tricks
such as `exploit.asp;.jpg` and `exploit.asp%00.jpg`. RFC 7578 §7 is the same
observation from the defender's side: "do not use the file name blindly ... and
do not use directory path information that may be present." Our
`playbooks/file-upload/playbook.md:8` declares `bb:effects: mutates_object` and
has nothing to send.

**What it would cost us.** A raw string body plus a `Content-Type` header
carrying the boundary gets multipart in phase 1 with no new machinery at all,
at one real cost: the model has to spell `\r\n` between parts exactly, and a
JSON string argument can carry `\r\n` but cannot carry arbitrary bytes. That
puts binary uploads and null-byte filename tricks out of reach until a
`body_encoding: base64` field exists. Deliberately not proposed: a structured
`multipart` argument. It would be a second parser beside the target's, and the
whole value of the field is that the tester controls bytes the target's parser
disagrees about.

Sources:
- [RFC 7578 §4.1, §4.2, §7](https://www.rfc-editor.org/rfc/rfc7578.html)
- [PortSwigger: file upload vulnerabilities](https://portswigger.net/web-security/file-upload)
- [mitmproxy HTTP API: `multipart_form`](https://docs.mitmproxy.org/stable/api/mitmproxy/http.html)

### Header order and duplicates

**What it is.** The wire is an ordered list of field lines that may repeat a
name; a dictionary is not. RFC 9110 §5.3 is explicit: "The order in which field
lines with the same name are received is therefore significant to the
interpretation of the field value; a proxy MUST NOT change the order of these
field line values when forwarding a message." It also says "a sender MUST NOT
generate multiple field lines with the same name ... unless that field's
definition allows multiple field line values to be recombined as a
comma-separated list" -- which is precisely why sending them anyway is a test.

**Which bug classes need it.** Request smuggling, where the front end and back
end disagree about which of two framing headers wins
(RFC 9112 §6.3 above; PortSwigger's CL.TE is "The front-end server uses the
`Content-Length` header and the back-end server uses the `Transfer-Encoding`
header"). Cache poisoning, which "relies on manipulation of unkeyed inputs,
such as headers" against a cache key that is "a predefined subset of the
request's components". WAF bypass through parameter and header pollution, where
"WAFs must make security decisions without fully simulating the application's
parsing behavior".

**What it would cost us.** Less than it looks. `headers` is declared as an
`object` (`roster.py:753`), and a JSON object cannot repeat a key; the gate
reads `value.keys()` (`roster.py:1418`) and the handler casts to a dict
(`_launch.py:768-778`). But an *array* argument with an `items_pattern` is
already expressible by today's `Argument` (`roster.py:377-378`), so a
`header_lines: ["Name: value", ...]` argument constrained by one pattern per
line needs no new roster machinery -- only a decision. The cost is on the
client side: `proxy.spend` and `_through` take a `Mapping` and hand it to
`http.client` as a mapping (`proxy.py:3904`, `3968`, `3987`, `3995-4006`), so
both would have to carry an ordered sequence. The door already wants that: its
own forward loop is `putheader` per pair for exactly this reason
(`proxy.py:2508-2521`).

Two things stay refused whatever we do, and should be said out loud. Header
values are bounded to printable ASCII with no trailing newline, and the
contract explains that the pattern ends at `\Z` because "a trailing newline is
exactly the character a header value would smuggle a second request in with"
(`roster.py:749-752`). And the control headers are applied last, so a caller
naming one is naming a value this hop overwrites (`proxy.py:3956-3960`).

Every serious tool has the same two layers here, which is the strongest
argument that we need both: a normalized view and a raw one. Burp names the
failure mode of the normalized layer, listing what HTTP/2 normalization
destroys -- "Any capital letters in header names are converted to lowercase",
"If present, the `Connection` header is stripped" -- and provides the Inspector
as the escape hatch, where each header "has its own entry ... split into
distinct Name and Value fields" and can be reordered with "the arrow buttons at
the bottom of the list". mitmproxy folds by default -- "Multiple headers are
folded into a single header as per RFC 7230" -- and provides `get_all`, which
"does not fold multiple headers into a single one", over a `fields:
tuple[tuple[KT, VT], ...]`. Caido offers a `Raw` view that "Represents the data
exactly as it was transmitted."

Not verified: whether Burp's Inspector permits two entries with the same name.
The pages fetched do not say, so no claim is made.

Sources:
- [RFC 9110 §5.3 Field Order](https://www.rfc-editor.org/rfc/rfc9110.html)
- [PortSwigger: web cache poisoning](https://portswigger.net/web-security/web-cache-poisoning)
- [Ethiack: bypassing WAFs with parameter pollution](https://blog.ethiack.com/blog/bypassing-wafs-for-fun-and-js-injection-with-parameter-pollution)
- [Burp: HTTP/2 normalization in the message editor](https://portswigger.net/burp/documentation/desktop/http2/http2-normalization-in-the-message-editor)
- [Burp: modifying requests using the Inspector](https://portswigger.net/burp/documentation/desktop/tools/inspector/modify-requests)
- [mitmproxy Headers and MultiDict](https://docs.mitmproxy.org/stable/api/mitmproxy/coretypes/multidict.html)
- [Caido: request and response view modes](https://docs.caido.io/app/guides/request_response_modes)

### Cookies

**What it is.** A jar, or a header, or both. Burp keeps "a shared cookie jar"
that "stores all of the cookies issued by websites you visit" and is "shared
between all of Burp's tools". mitmproxy exposes cookies as a derived view:
"Modifications to the MultiDictView update `Request.headers`, and vice versa."

**Which bug classes need it.** Session fixation, which OWASP's testing guide
describes as "the insecure practice of preserving the same value of the session
cookies before and after authentication". Cookie scope weaknesses, which RFC
6265 §8.5 and §8.6 state plainly: "Cookies do not provide isolation by port"
and "Cookies do not provide integrity guarantees for sibling domains (and their
subdomains)". CSRF and `SameSite`, where the current draft
(draft-ietf-httpbis-rfc6265bis-21, still an Internet-Draft and **not** an RFC)
says Lax "provides reasonable defense in depth against CSRF attacks that rely
on unsafe HTTP methods (like POST), but does not offer a robust defense against
CSRF as a general category of attack".

**What it would cost us.** Sending a cookie is already possible: `Cookie`
matches the header name pattern. What is not possible is *observing* one. The
door strips `set-cookie` and `set-cookie2` from every agent-visible response
(`proxy.py:348-357`, `proxy.py:645-651`), so an agent can never read a cookie's
`Secure`, `HttpOnly`, `SameSite` or `Domain` attributes -- which is most of
what `playbooks/cookies/playbook.md` is about. And when an Identity is bound,
the door owns the name: `Session.inject` removes any `Cookie` the agent sent
and appends the jar's (`identity.py:319-329`), with the jar's values also
feeding the response-redaction list (`identity.py:331-351`). A provisioned
Identity may not declare a static `cookie` header at all
(`identity.py:37-47`).

So the honest cost statement is: a cookie *argument* buys nothing that the
`Cookie` header does not already buy, and the real gap is a redacted
`Set-Cookie` projection -- name and attributes visible, value digested -- so
that cookie-attribute findings are reachable without lifting the strip. That is
a proxy change, not a contract change.

Sources:
- [RFC 6265 §8.4, §8.5, §8.6](https://www.rfc-editor.org/rfc/rfc6265.html)
- [draft-ietf-httpbis-rfc6265bis-21 (Internet-Draft, no RFC number)](https://www.ietf.org/archive/id/draft-ietf-httpbis-rfc6265bis-21.txt)
- [OWASP WSTG: testing for session fixation](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/06-Session_Management_Testing/03-Testing_for_Session_Fixation)
- [Burp sessions settings and cookie jar](https://portswigger.net/burp/documentation/desktop/settings/sessions)
- [mitmproxy HTTP API: cookies](https://docs.mitmproxy.org/stable/api/mitmproxy/http.html)

### Redirects

**What it is.** Whether the client follows a 3xx, how many times, and what it
carries across the hop. RFC 9110 §15.4 defines the class -- "further action
needs to be taken by the user agent" -- and the method rules matter: §15.4.4
(303 See Other) exists "primarily to allow the output of a POST action to
redirect to a GET request", while §15.4.8 (307) and §15.4.9 (308) both say "The
user agent MUST NOT change the request method when automatically following the
redirect."

**Which bug classes need it.** SSRF filter bypass, where "It is sometimes
possible to bypass filter-based defenses by exploiting an open redirection
vulnerability". Credential leakage across a hop: curl CVE-2022-27776 is the
clean example, "curl might leak authentication or cookie header data on HTTP
redirects to the same host but another port number", fixed in 7.83.0 by
extending the same-host check to port and protocol. And access-control testing,
where a 302 to a login page and a 200 with the resource are different answers
that a following client collapses into one.

**What it would cost us.** The door must keep not following, and its comment
already argues the case: following "would spend a capability on a URL the
caller never asked for, and the caller is going to come back through this same
fence anyway, where the new URL is canonicalised ... and decided on its own"
(`proxy.py:756-786`, `proxy.py:3014-3033`). A follow therefore belongs to the
in-container client, re-entering the door once per hop, so that every hop earns
its own scope decision and its own Receipt -- which is what
`redirected()` already writes the link for (`proxy.py:756-786`, recorded in
`notes` at `proxy.py:3074`). Two costs: the client must drop `Authorization`
and `Cookie` on a host, port or scheme change (curl's bug is the reason), and a
303 rewriting a POST into a GET produces a request the Tool run did not
declare -- which the door already tolerates, because its method binding exempts
the safe set for exactly this reason
(`migrations/20260810T214500Z__capability_proxy_egress.sql:240-255`).

Burp's shape is worth copying: follow-redirects there is not a boolean but
"Never", "On-site only", "In-scope only", "Always", with a separate switch for
whether cookies set in the redirect response are resubmitted. "In-scope only"
is the setting our scope model already computes for free.

Sources:
- [RFC 9110 §15.4, §15.4.4, §15.4.8, §15.4.9](https://www.rfc-editor.org/rfc/rfc9110.html)
- [curl CVE-2022-27776](https://curl.se/docs/CVE-2022-27776)
- [PortSwigger: SSRF](https://portswigger.net/web-security/ssrf)
- [Burp Repeater settings: follow redirects](https://portswigger.net/burp/documentation/desktop/settings/tools/repeater)

Not confirmed, and therefore not cited as normative: a sentence in RFC 9110's
security considerations about forwarding `Authorization` across a redirect, and
the WHATWG Fetch step that deletes `Authorization` on a cross-origin redirect.
Both pages truncated before those sections on every fetch attempt.

### HTTP version

**What it is.** Which wire protocol carries the message. RFC 9113 §8.2.2: "An
endpoint MUST NOT generate an HTTP/2 message containing connection-specific
header fields." §8.3: "Pseudo-header fields are header fields that begin with
the ':' character." §8.1.1: "A malformed request or response that is detected
MUST be treated as a stream error of type PROTOCOL_ERROR."

**Which bug classes need it.** HTTP/2 downgrade desync. PortSwigger's research
defines it verbatim: "HTTP/2 downgrading is when a front-end server speaks
HTTP/2 with clients, but rewrites requests into HTTP/1.1 before forwarding them
on to the back-end server", and the mechanism is that "the back-end receiving a
downgraded request doesn't have access to this data, and must use the CL or TE
header. This leads to two main types of vulnerability: H2.TE and H2.CL." (The
page does not carry standalone one-line definitions of H2.TE and H2.CL
separately; the sentence above is the whole of what it says in one place.) The
second class is requests that HTTP/1 cannot express at all: Burp calls these
"kettled" and documents them as requests "that are impossible to accurately
represent using HTTP/1 syntax without losing information", giving the example
that "it's technically possible to add a newline character inside a header
value in HTTP/2", along with "Inject colons into header names" and "Inject
arbitrary spaces or newlines within the method and path".

**What it would cost us.** More than any other field on this list, and the code
says so directly. ALPN is pinned to `http/1.1` in three places with the reason
written down: the door offers only `http/1.1` to the agent (`tls.py:77-81`) and
tells the target the same, because "everything above this speaks HTTP/1.1 and
nothing here can read a frame of anything else" (`proxy.py:1999-2005`,
repeated on the verification-downgrade path at `proxy.py:2017-2020`). Beyond
the transport, the *evidence format* is HTTP/1 text: `transcript` writes a
start line, `Name: value` lines and a blank line (`proxy.py:789-798`), the
artifact content type is `message/http` (`proxy.py:317`), and the response
transcript is reconstructed as `HTTP/1.1 {status} {reason}`
(`proxy.py:2831`). An HTTP/2 exchange would need a second artifact encoding and
would change what `intercepted` and the transport-divergence columns mean
(`proxy.py:3075-3079`). This is its own ticket, not a field on this contract.

Note for the record: our door is an HTTP/2-to-HTTP/1.1 downgrade point itself,
for any client that would have negotiated h2 (`tls.py:77-81`). That is a
property an auditor should be able to read off the Receipt, and `intercepted`
is already on every one (`proxy.py:3065`).

Sources:
- [RFC 9113 §8.1.1, §8.2.2, §8.3](https://www.rfc-editor.org/rfc/rfc9113.txt)
- [PortSwigger research: HTTP/2, the sequel is always worse](https://portswigger.net/research/http2)
- [Burp: working with HTTP/2](https://portswigger.net/burp/documentation/desktop/http2)
- [Burp: performing HTTP/2-exclusive attacks](https://portswigger.net/burp/documentation/desktop/http2/performing-http2-exclusive-attacks)
- [mitmproxy protocols](https://docs.mitmproxy.org/stable/concepts/protocols/)

Caido's documentation does not describe HTTP version selection on any page
fetched; that is recorded as undocumented rather than absent.

### Timeout

**What it is.** How long the client waits, and what it reports when it gives
up. Burp Repeater exposes a streaming-connection timeout "set to 600 seconds
(10 minutes)" by default; Turbo Intruder separates a per-response `timeout`
(default 10 seconds) from a whole-run `idleTimeout`. mitmproxy documents no
request timeout at all on the pages fetched, and instead exposes
`timestamp_start` ("Headers received") and `timestamp_end` ("Last byte
received").

**Which bug classes need it.** Time-based blind injection, where "Delaying the
execution of a SQL query also delays the HTTP response" and "You can determine
the truth of the injected condition based on the time taken to receive the HTTP
response". Also every denial-of-service-adjacent observation where the finding
*is* the delay.

**What it would cost us.** Little, and one thing that is not obvious. The
plumbing exists: `spend` already takes a `timeout` parameter that `_launch`
never passes (`proxy.py:3905`), the door's own target timeout is 30 seconds
(`proxy.py:322`), and the evidence side is already there -- `waited_ms` is
computed and written on every allowed Receipt (`proxy.py:3053`,
`migrations/0005_artifacts_and_provenance.sql:58`). The non-obvious cost is
that an egress budget slot is held while the request is in flight and released
only when the socket closes (`proxy.py:2533-2539`, `proxy.py:2548-2578`), so a
caller-chosen timeout is a caller-chosen hold on a Program-wide resource. Any
exposed timeout must be bounded *below* the door's, not above it.

Sources:
- [PortSwigger: blind SQL injection](https://portswigger.net/web-security/sql-injection/blind)
- [Burp Repeater settings](https://portswigger.net/burp/documentation/desktop/settings/tools/repeater)
- [Turbo Intruder settings](https://github.com/PortSwigger/turbo-intruder/blob/master/docs/settings.md)
- [mitmproxy HTTP API: timestamps](https://docs.mitmproxy.org/stable/api/mitmproxy/http.html)

### Repetition, connection reuse and parallelism

**What it is.** Sending the same request many times, sending several at once,
and controlling which TCP connection each one goes down. Burp's grouped send
makes the topology an explicit choice -- one connection where "Repeater
establishes a connection to the target, sends the requests from all of the tabs
in the group, and then closes the connection", or a fresh connection per
request -- and makes the parallel case protocol-specific: HTTP/1 "uses last-byte
synchronization ... but the last byte of each request in the group is
withheld", HTTP/2 "sends the group using a single packet attack". Turbo
Intruder exposes `concurrentConnections` (default 50) and
`requestsPerConnection` (default 100). Caido's Automate exposes "# of workers"
and a "Delay (ms) between requests", and a payload-free mode with a "Number of
payloads to generate" field for pure repetition.

**Which bug classes need it.** Race conditions: "The single-packet attack
enables you to completely neutralize interference from network jitter by using
a single TCP packet to complete 20-30 requests simultaneously", against a "race
window" during which "The application transitions through a temporary
sub-state". Connection-state attacks: "Some proxies only apply this whitelist
to the first request sent over a given connection", and "The front-end uses the
first request's Host header to decide which back-end to route to, then routes
all subsequent requests down the same back-end connection". Our
`playbooks/race-conditions/playbook.md:8` declares `bb:effects:
mutates_object` and has no way to send two requests at once.

**What it would cost us.** This is the one field on the list that is not a
contract question at all. The door opens a connection, sends one request and
closes it in a `finally` (`proxy.py:2494-2528`), so same-connection sequencing
and last-byte withholding are not expressible through it at any argument count.
Repetition is also the field that spends the shared budget fastest:
`reserve_egress_slot` takes one request's worth under a row lock and refuses
with a reason and a retry time
(`migrations/20260811T170000Z__egress_budget_at_the_door.sql:235`), so a
`repeat: 30` argument is thirty budget draws, thirty Receipts and up to sixty
artifacts from one tool call. The recommendation is that repetition and racing
become a separate tool with its own contract, its own risk class and its own
budget accounting, not a field here.

Sources:
- [PortSwigger research: smashing the state machine](https://portswigger.net/research/smashing-the-state-machine)
- [PortSwigger: race conditions](https://portswigger.net/web-security/race-conditions)
- [PortSwigger research: browser-powered desync attacks](https://portswigger.net/research/browser-powered-desync-attacks)
- [Burp: sending grouped HTTP requests](https://portswigger.net/burp/documentation/desktop/tools/repeater/send-group)
- [Turbo Intruder settings](https://github.com/PortSwigger/turbo-intruder/blob/master/docs/settings.md)
- [Caido: repeating requests with no payload](https://docs.caido.io/app/guides/automate_null)
- [Caido: avoiding rate-limiting protections](https://docs.caido.io/app/guides/automate_rate_limiting)

## The identity question

**Settled: `identity_slot` is a property of the Tool run, not an argument, and
the contract should continue to refuse it.**

The reason is not taste. Every layer below the contract already treats it as a
Tool-run property, and four of them would have to be rewritten to make it an
argument:

1. `resolve_egress_identity` reads it out of the Tool run's own row:
   `SELECT nullif(btrim(tr.args ->> 'identity_slot'), '') ... FROM tool_runs tr
   WHERE tr.id = v_auth.tool_run_id`
   (`migrations/20260811T150000Z__encrypted_identity_slots.sql:437-438`), then
   requires a live, unreleased, unexpired lease held by *this* agent run
   (same file, `:439-453`).
2. The proxy takes the Identity from the capability resolution, never from the
   request: `AUTHORIZE` selects `identity_entity_id` and `identity_label`
   alongside the Program and Tool run (`proxy.py:948-952`), and the handler
   binds whatever came back (`proxy.py:1174-1181`).
3. The receipt trigger re-checks the same key a third time, refusing an allowed
   agent Receipt whose Identity does not match `tr.args ->> 'identity_slot'`
   (`20260811T150000Z:764-780`).
4. The lease itself is granted to the *agent run* when the Task is claimed, on
   the same clock as the task lease, with the reason written down: two clocks
   "would admit a live task lease beside a dead identity lease, and the agent
   would read the proxy's refusal to inject as the TARGET changing behaviour"
   (`migrations/0023_scheduler_ranking.sql:958-968`).

And the risk decision is taken before the child exists. `net_borrowed_identity`
escalates any non-empty `identity_slot` to `approval_required` with the
question code `credential_needed`
(`migrations/0026_human_control.sql:266-268`), assessed by `assess_call_risk`
(`0026:280-311`) against the digest built at open. An argument named at call
time would let a model move outside the digest a human already answered, which
is the one thing the control surface exists to prevent -- and it is the same
sentence the contract already gives for withholding it (`roster.py:760-765`).

**But the field is broken in the other direction, and that is the real
defect.** The runtime opens every egress Tool run with the slot hardcoded
empty:

```
proxy.TOOL,
json.dumps({"url": claimed.url, "method": claimed.method, "identity_slot": ""}),
```

(`src/redkraken/execution.py:1935-1942`). So today no agent-issued request can
carry an Identity at all, however many playbooks ask for one. The capability
exists end to end -- provisioning, keying, sealing, injection, response
redaction -- and nothing ever names a slot. Fixing `identity_slot` means
teaching `_authorize` to write the slot the Task's hypothesis was paired
against, not adding an argument.

**What the 29 playbooks should say instead.** They currently write sentences
like "Send the call as label A through `mcp__rk2__http_request`, with
`identity_slot` set" (`playbooks/grpc/playbook.md:50`; the same instruction
appears at `playbooks/graphql/playbook.md:43`,
`playbooks/ssrf-url-routing/playbook.md:50`,
`playbooks/deserialization/playbook.md:71`, `playbooks/logging/playbook.md:46`,
`playbooks/browser-storage/playbook.md:28`,
`playbooks/identity-lifecycle/playbook.md:29,41` and 22 others). Every one of
them should be rewritten to the form:

> This reading runs as whichever Identity the Task was opened under; you do not
> choose it and there is no argument for it. A reading that needs two
> Identities is two Tasks, and the differential is made by comparing their
> Receipts.

That sentence is true of the system as designed, it is executable, and it says
the thing the corpus is actually reaching for -- the Identity differential --
without asking for a field. `playbooks/identity-lifecycle/playbook.md:41`, "Send
the same read with no `identity_slot` at all", becomes "the unauthenticated
half of the differential is a Task opened with no Identity".

One naming hazard worth recording while this area is open: the served tool is
`mcp__rk2__http_request` (`roster.py:738`) and the Tool run is opened under
`proxy.TOOL`, which is `mcp__rk2__net_request` (`proxy.py:332`,
`execution.py:1935`). Every per-call risk rule is written against the second
name (`0026:260-268`), and the static floor covers both only through the
`mcp__rk2__*` glob (`migrations/0022_hooks_and_receipts.sql:100`). A future
ticket that opens a Tool run per agent call under the served name would
silently stop all three `net_*` rules from firing.

## Write safety

The corpus is mostly read-only by design. Counting `bb:effects` across the 50
playbooks: 37 `read_only`, 8 `mutates_object`, 4 `mutates_session`, 1
`mutates_account` (`playbooks/webauthn/playbook.md:8`). The vocabulary is
`playbook.py:96` and the floor that stops a Playbook understating itself is
`playbook.py:107-112`, enforced at load (`playbook.py:453-457`).

RFC 9110 §9.2.1 is the standard's own version of this distinction: methods are
safe "if their defined semantics are essentially read-only", "the client does
not request, and does not expect, any state change on the origin server", and
"the GET, HEAD, OPTIONS, and TRACE methods are defined to be safe". Crucially
it also gives the reason a harness should care: safety "allows a user agent to
apply appropriate constraints on the automated use of unsafe methods when
processing potentially untrusted content". And it warns against treating the
method as sufficient: "it is common for Web-based content editing software to
use actions within query parameters, such as `page?do=delete`". §9.2.2 defines
idempotence, and lists "PUT, DELETE, and safe request methods" as idempotent.

We already enforce half of the rule, at the door. An unsafe method is refused
unless it matches the method the Tool run was authorized for, exactly; safe
methods pass, because subresources and redirects share one capability and
"a safe method is the one thing a caller who already holds the capability gains
nothing by substituting"
(`migrations/20260810T214500Z__capability_proxy_egress.sql:240-255`; the same
check is in `0039_proxy_capabilities.sql:61-66`).

**The proposed rule, in one sentence:** *a request may carry a body only if the
Tool run that authorized it was opened as body-bearing, and a Tool run is
opened as body-bearing only when the Playbooks selected for its Task declare
effects above `read_only`.*

Where each half is enforced:

1. **At Tool-run open (`execution.py:1929-1944`).** The runtime already writes
   `url` and `method` into `tool_runs.args` from the claimed Task. It should
   also write `body_allowed`, derived from the maximum `bb:effects` of the
   Playbooks it selected for that Task -- false when every selected Playbook is
   `read_only`. This is the point where the risk class is computed
   (`assess_call_risk`, `0026:280-311`) and where a human is asked, so it is the
   point where the answer should be recorded.
2. **At the door**, beside the method binding it mirrors
   (`20260810T214500Z:240-255`). A request that arrives with a body when
   `v_args ->> 'body_allowed'` is not true is refused before the socket, with a
   blocked Receipt like every other refusal (`proxy.py:3138-3160`,
   `BLOCKED` at `proxy.py:1029-1031`). The door is the right place because it is
   the place that already re-decides everything against live policy and cannot
   be bypassed by a client that ignores its instructions.
3. **In the approval digest (`0026:170-186`).** Add `body_sha256` to
   `canonical_request`, or mark a call with a non-object body
   `reusable: false`. Today `body_keys` is empty for a raw string body
   (`0026:183-186`) while `reusable` stays `true` (`0026:172`), so two entirely
   different bodies to one path template share one `equivalence_key`
   (`0026:193-196`) and one human approval covers both. That is the single
   sharpest safety defect a body argument would open, and it is a four-line
   migration to close.

What this does *not* do, deliberately: it does not try to decide whether a GET
is a write. RFC 9110 §9.2.1 says that judgement cannot be made from the method,
and a harness that pretended otherwise would be claiming a guarantee it does
not have. What the rule buys is the narrower and honest property: a run whose
whole Playbook selection is read-only cannot put bytes in front of a parser.

The external framing for all of this is OWASP's LLM06 Excessive Agency, whose
root causes are "excessive functionality; excessive permissions; excessive
autonomy" and whose mitigations name our exact case: "Avoid the use of
open-ended extensions where possible (e.g., run a shell command, fetch a URL,
etc.) and use extensions with more granular functionality", "Utilise
human-in-the-loop control to require a human to approve high-impact actions
before they are taken", and "Implement authorization in downstream systems
rather than relying on an LLM to decide if an action is allowed or not". The
last of those is a description of what `authorize_egress_request` already is.

Sources:
- [RFC 9110 §9.2.1 Safe Methods, §9.2.2 Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html)
- [OWASP Top 10 for LLM Applications, LLM06:2025 Excessive Agency](https://github.com/OWASP/www-project-top-10-for-large-language-model-applications/blob/main/2_0_vulns/LLM06_ExcessiveAgency.md)
- [Burp: project scope settings, "Drop all out-of-scope requests"](https://portswigger.net/burp/documentation/desktop/settings/project/scope)

(The canonical `genai.owasp.org` page for LLM06 returned HTTP 403 and did not
fetch; the OWASP repository source of record was used instead.)

## Recording and redaction

**What the receipt must hold: nothing new.** A bodied request needs no new
column. `receipts` describes a request with `method`, `scheme`, `host`, `port`,
`path`, `query_sha256` and four artifact hashes
(`migrations/0005_artifacts_and_provenance.sql:39-65`, the hashes at `:59-62`),
and the body is already inside the bytes those hashes name: `transcript` is
start line plus headers plus body (`proxy.py:789-798`), `sent` and `wire_sent`
are built from it with the body included (`proxy.py:2829-2830`), and the
artifact rows carry `byte_size` and `content_type: message/http`
(`proxy.py:3081-3084`, `proxy.py:317`). A `request_body_sha256` column would be
a second hash of bytes already hashed, and two statements of one fact can
drift.

What *is* missing on the record is the same thing that is missing from the
approval digest: the args of the Tool run are where "which body was authorized"
would live, and `tool_runs.args` is a `jsonb` column that already carries
`url`, `method` and `identity_slot` (`0005:26`, `execution.py:1936-1942`).

**What the artifact store must hold.** The store is content-addressed by the
plaintext hash with the ciphertext on disk (`src/redkraken/artifact.py:1-12`),
and an artifact is either `agent_visible` or `credential_bearing` and never
both (`0005:9-18`). The existing rule for the two views of one exchange carries
over to bodies unchanged: the agent view and the wire view are hashed
separately, only the wire view is encrypted, and the wire view is made unique
per exchange by an internal exchange line so that two exchanges with identical
bytes do not collide on one row (`proxy.py:801-821`). A request body makes the
request side of that pair meaningful for the first time, and the machinery is
already symmetric (`proxy.py:2907-2935`).

**What must never be stored, and the one gap.** Today's redaction is
response-only: `project_identity_response` drops headers carrying an injected
secret and replaces the secret's renderings in the body with `[redacted]`
(`proxy.py:659-698`, `proxy.py:346`), searching eight spellings of each value
including URL-quoted, base64, urlsafe-base64 and hex (`proxy.py:701-728`). The
request side gets no such treatment: `sent` and `wire_sent` use the same `body`
object (`proxy.py:2829-2830`), which is correct while the only injected
material is headers. It stops being correct the day an agent can put bytes in a
body, because an agent that read a token out of one response artifact can
write it into the next request. The proposal is to run the same
`_renderings`-based scrub over the agent-visible *request* artifact using the
bound session's `secrets(url)` (`identity.py:331-351`), so the request pair
behaves like the response pair: exact bytes sealed, redacted bytes readable,
both hashed, the difference on the record.

The external guidance agrees on the list and on the shape. OWASP's logging
cheat sheet names what must never be logged: "Authentication passwords",
"Access tokens", "Session identification values (consider replacing with a
hashed value if needed to track session specific events)", "Encryption keys and
other primary secrets", "Bank account or payment card holder data". ASVS 7.1.1
is the requirement form: "Verify that the application does not log credentials
or payment details. Session tokens should only be stored in logs in an
irreversible, hashed form." OpenTelemetry's HTTP conventions give the same
answer for headers -- "Instrumentations SHOULD require an explicit
configuration of which headers are to be captured. Including all request
headers can be a security risk" -- and for query strings recommends a
key-preserving redaction, "the query string key SHOULD still be preserved, e.g.
`https://www.example.com/path?color=blue&sig=REDACTED`". Our `query_sha256`
(`proxy.py:743-754`) is the stricter version of the same instinct and its
docstring says so: "a digest rather than the string, because a query carries
identifiers, tokens and occasionally a credential somebody pasted".

One thing our design does that the external guidance does not have a name for,
and which is the reason a bodied request can be evidence at all: the record is
honest about incomplete redaction. `project_identity_response` says it plainly
-- "an exchange whose redaction was incomplete is one an auditor can still see
whole" (`proxy.py:679-682`) -- because the wire view is sealed rather than
discarded.

For reference on size ceilings, since a body is the first argument that can be
large: nginx defaults `client_max_body_size` to 1 MiB and answers 413 above it;
Apache defaults `LimitRequestBody` to 0 (unlimited) with a 2 GiB maximum; RFC
9110 §15.5.14 defines 413 as "the server is refusing to process a request
because the request content is larger than the server is willing or able to
process". mitmproxy's `body_size_limit` is the closest precedent for a
client-side ceiling: "Byte size limit of HTTP request and response bodies",
default None. Our door's 32 MiB (`proxy.py:328`) is a store-and-hash ceiling,
not an argument ceiling, and the two should not be the same number.

Sources:
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP ASVS v4.0.3 V7 Error Handling and Logging](https://raw.githubusercontent.com/OWASP/ASVS/v4.0.3/4.0/en/0x15-V7-Error-Logging.md)
- [OpenTelemetry HTTP span semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/http-spans/)
- [RFC 9110 §15.5.14 (413 Content Too Large)](https://www.rfc-editor.org/rfc/rfc9110.txt)
- [nginx ngx_http_core_module: client_max_body_size](https://nginx.org/en/docs/http/ngx_http_core_module.html)
- [Apache httpd 2.4 core: LimitRequestBody](https://httpd.apache.org/docs/2.4/mod/core.html)
- [mitmproxy options: body_size_limit, stream_large_bodies](https://docs.mitmproxy.org/stable/concepts/options/)

## Proposed contract

Phase 1 is what a bodied request needs and nothing else. Every phase-1 field is
expressible with today's `Argument` type (`roster.py:328-346`) and passes
today's compile checks (`roster.py:1766-1786`).

| field | kind | constraint | phase | note |
| --- | --- | --- | --- | --- |
| `method` | string, required | `enum` of the existing seven (`roster.py:743-747`) | 1, unchanged | TRACE is deliberately not added: it is safe per RFC 9110 §9.2.1 but nothing in the corpus asks for it |
| `url` | string, required | `pattern` `^https?://` (`roster.py:748`) | 1, unchanged | the door canonicalises and re-decides it anyway (`proxy.py:2369-2393`) |
| `headers` | object | names `^[A-Za-z][A-Za-z0-9-]{0,63}\Z`, values `^[\x20-\x7e]{0,1024}\Z` (`roster.py:753-757`) | 1, unchanged | carries `Content-Type`; must never carry `Content-Length`, which the door owns (`proxy.py:2693-2694`) |
| `body` | string | `bounds=(0, 65536)`, no `pattern` | **1** | a string and not an object, because the gate's forbidden-name scan skips non-containers (`roster.py:1334`) and would otherwise deny any login body (`roster.py:229-244`); `bounds` alone makes it `constrained` so no `OPEN_ARGUMENTS` entry is needed (`roster.py:348-356`, `roster.py:1771-1774`) |
| `body_encoding` | string | `enum=("text", "base64")` | 2 | needed for binary uploads and null-byte filename tests; without it a JSON string cannot carry arbitrary bytes |
| `header_lines` | array | `items_pattern` `^[A-Za-z][A-Za-z0-9-]{0,63}: [\x20-\x7e]{0,1024}\Z` | 2 | ordered, duplicate-capable headers; expressible today (`roster.py:377-378`) but needs `spend`/`_through` to carry a sequence instead of a mapping (`proxy.py:3904`, `3968`, `3987`) |
| `timeout_ms` | integer | `bounds=(1000, 25000)` | 2 | ceiling deliberately below the door's 30 s (`proxy.py:322`) because the wait holds an egress slot (`proxy.py:2548-2578`) |
| `follow_redirects` | integer | `bounds=(0, 5)` | 2 | performed by the in-container client re-entering the door, one Receipt per hop; must drop `Authorization` and `Cookie` on host, port or scheme change |
| `http_version` | -- | -- | not proposed | ALPN is pinned in three places with a stated reason (`tls.py:77-81`, `proxy.py:1999-2005`, `proxy.py:2017-2020`) and the artifact format is HTTP/1 text (`proxy.py:789-798`, `proxy.py:317`). Its own ticket |
| `repeat` / `parallel` | -- | -- | not proposed | one call is one budget draw (`20260811T170000Z:235`) and the door closes the connection per request (`proxy.py:2507-2528`). Racing belongs to a separate tool with its own risk class |
| `identity_slot` | -- | -- | **never** | a property of the Tool run; see "The identity question" |

Two implementation notes that the table cannot carry:

* **`bounds` on a string does not serialise correctly today.** `Argument.schema`
  emits `minimum`/`maximum` for `bounds` (`roster.py:372-373`), which is JSON
  Schema for numbers, while the gate measures `len(value)`
  (`roster.py:1432-1436`). A string `body` with `bounds` would be checked by
  the gate and not by the served schema, which breaks the arrangement the
  docstring states -- "the schema is the pair's promise and the gate is ours"
  (`roster.py:358-366`). `schema()` needs to emit `maxLength`/`minLength` when
  `kind == "string"`. This is a two-line fix and it is a prerequisite, not a
  follow-up.
* **`writes` needs no change.** The contract already declares
  `writes=("receipts", "artifacts", "artifact_refs")` (`roster.py:741`), which
  is exactly what a bodied request writes.

## Sources consulted

Specifications:
- [RFC 9110, HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html) ([text](https://www.rfc-editor.org/rfc/rfc9110.txt)) -- §5.3 field order, §9.2.1 safe, §9.2.2 idempotent, §15.4/15.4.4/15.4.8/15.4.9 redirects, §15.5.14 413
- [RFC 9112, HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html) -- §6.3 message body length, §11.2 request smuggling
- [RFC 9113, HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.txt) -- §8.1.1, §8.2.2, §8.3
- [RFC 7578, multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578.html) -- §4.1, §4.2, §7
- [RFC 6265, HTTP State Management](https://www.rfc-editor.org/rfc/rfc6265.html) -- §8.4, §8.5, §8.6
- [draft-ietf-httpbis-rfc6265bis-21](https://www.ietf.org/archive/id/draft-ietf-httpbis-rfc6265bis-21.txt) -- an Internet-Draft, not an RFC; cited only for SameSite
- [RFC 6585](https://www.rfc-editor.org/rfc/rfc6585.txt) -- 429 and 431 are here, not in RFC 9110
- [Fetch Standard](https://fetch.spec.whatwg.org/) -- CORS-safelisted request-header

Tooling documentation:
- Burp Suite: [message editor](https://portswigger.net/burp/documentation/desktop/tools/message-editor), [Repeater settings](https://portswigger.net/burp/documentation/desktop/settings/tools/repeater), [grouped sends](https://portswigger.net/burp/documentation/desktop/tools/repeater/send-group), [HTTP/2](https://portswigger.net/burp/documentation/desktop/http2), [HTTP/2 normalization](https://portswigger.net/burp/documentation/desktop/http2/http2-normalization-in-the-message-editor), [HTTP/2-exclusive attacks](https://portswigger.net/burp/documentation/desktop/http2/performing-http2-exclusive-attacks), [Inspector](https://portswigger.net/burp/documentation/desktop/tools/inspector/modify-requests), [Intruder attack types](https://portswigger.net/burp/documentation/desktop/tools/intruder/configure-attack/attack-types), [Intruder resource pools](https://portswigger.net/burp/documentation/desktop/tools/intruder/configure-attack/resource-pool), [sessions and cookie jar](https://portswigger.net/burp/documentation/desktop/settings/sessions), [project scope](https://portswigger.net/burp/documentation/desktop/settings/project/scope), [target scope](https://portswigger.net/burp/documentation/desktop/tools/target/scope), [task settings and throttling](https://portswigger.net/burp/documentation/desktop/settings/project/tasks)
- [Turbo Intruder settings](https://github.com/PortSwigger/turbo-intruder/blob/master/docs/settings.md)
- Caido: [Replay](https://docs.caido.io/app/quickstart/replay), [Automate](https://docs.caido.io/app/quickstart/automate), [multiple payloads](https://docs.caido.io/app/guides/automate_multiple), [no-payload repetition](https://docs.caido.io/app/guides/automate_null), [rate limiting](https://docs.caido.io/app/guides/automate_rate_limiting), [view modes](https://docs.caido.io/app/guides/request_response_modes)
- mitmproxy: [HTTP API](https://docs.mitmproxy.org/stable/api/mitmproxy/http.html), [MultiDict](https://docs.mitmproxy.org/stable/api/mitmproxy/coretypes/multidict.html), [options](https://docs.mitmproxy.org/stable/concepts/options/), [protocols](https://docs.mitmproxy.org/stable/concepts/protocols/), [event hooks](https://docs.mitmproxy.org/stable/api/events.html)

Bug classes and research:
- [PortSwigger: HTTP request smuggling](https://portswigger.net/web-security/request-smuggling), [advanced smuggling](https://portswigger.net/web-security/request-smuggling/advanced)
- [PortSwigger research: HTTP/2](https://portswigger.net/research/http2)
- [PortSwigger research: smashing the state machine](https://portswigger.net/research/smashing-the-state-machine), [race conditions](https://portswigger.net/web-security/race-conditions)
- [PortSwigger research: browser-powered desync attacks](https://portswigger.net/research/browser-powered-desync-attacks)
- [PortSwigger: web cache poisoning](https://portswigger.net/web-security/web-cache-poisoning), [file upload](https://portswigger.net/web-security/file-upload), [SSRF](https://portswigger.net/web-security/ssrf), [blind SQL injection](https://portswigger.net/web-security/sql-injection/blind)
- [Ethiack: bypassing WAFs with parameter pollution](https://blog.ethiack.com/blog/bypassing-wafs-for-fun-and-js-injection-with-parameter-pollution)
- [curl CVE-2022-27776](https://curl.se/docs/CVE-2022-27776)
- [Fastify GHSA-3fjj-p79j-c9hh / CVE-2022-41919](https://github.com/fastify/fastify/security/advisories/GHSA-3fjj-p79j-c9hh)

Safety, redaction and governance:
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP ASVS v4.0.3 V7](https://raw.githubusercontent.com/OWASP/ASVS/v4.0.3/4.0/en/0x15-V7-Error-Logging.md)
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP XXE Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html)
- [OWASP Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html)
- [OWASP WSTG: session fixation](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/06-Session_Management_Testing/03-Testing_for_Session_Fixation)
- [OWASP LLM06:2025 Excessive Agency](https://github.com/OWASP/www-project-top-10-for-large-language-model-applications/blob/main/2_0_vulns/LLM06_ExcessiveAgency.md)
- [OpenTelemetry HTTP spans](https://opentelemetry.io/docs/specs/semconv/http/http-spans/)
- [nginx core module](https://nginx.org/en/docs/http/ngx_http_core_module.html), [Apache httpd 2.4 core](https://httpd.apache.org/docs/2.4/mod/core.html)
- [Atmail bug bounty terms](https://www.atmail.com/bug-bounty-terms/) -- "automated tooling must not exceed 5 requests per second per host"
- [Intigriti: understanding rate limiting](https://kb.intigriti.com/en/articles/5678905-understanding-rate-limiting)

Pages that would not fetch, recorded so nothing here rests on them:
`https://genai.owasp.org/llmrisk/llm06-excessive-agency/` (HTTP 403);
`https://hackerone.com/23andme_bbp` (JavaScript shell, no policy text, so no
per-program request rate is quoted from it);
`https://portswigger.net/burp/documentation/desktop/settings/project/resource-pool`,
`https://portswigger.net/burp/documentation/desktop/settings/project/sessions`
and several `docs.caido.io` paths (HTTP 404). RFC 9110's security
considerations and the WHATWG Fetch redirect algorithm truncated before the
relevant steps on every attempt, so no claim is made about either regarding
`Authorization` on cross-host redirects; the curl CVE is cited for that
behaviour instead. A Caido "Update Content-Length" setting appears in search
snippets but is on no page that fetched, so it is not claimed. A claim that
JA4H fingerprints header order is not supported by the FoxIO primary
documentation that was read, so RFC 9110 §5.3 is cited for header-order
significance instead.
