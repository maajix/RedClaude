# 05 - Injection and server-side

Scope: the nine playbooks `sql-injection`, `nosql-injection`, `ssti`,
`command-directory-injection`, `structured-injection`, `spreadsheet-injection`,
`deserialization`, `file-upload`, `ssrf-url-routing`.

All techniques below are described for an authorized engagement with a named
scope and a program-controlled callback host. Every proposal is written to stay
inside the harness's existing evidence contract: a claim is only worth adding if
the playbook can *observe* it.

Provenance note: pages marked **[fetched]** were retrieved and read during this
research. Pages marked **[listing]** appeared in a search-result index or in a
fetched page's link table but were not themselves retrieved, so only their
title, author and URL are asserted, not their contents. The watchTowr SOAPwn
whitepaper PDF was fetched but returned unparseable binary; its details below
come from the PortSwigger index entry and a secondary commentary, and are
flagged as such.

## What we already cover well

* **Matched controls.** Every playbook in this cluster pairs a variant with a
  control that is the same length, the same character class and the same shape.
  `sql-injection` step 3 (true clause vs false clause, both carrying the quote),
  `ssti` step 2 (one-character-shorter closing delimiter), `nosql-injection`
  step 3 (operator key vs plain nested key), `structured-injection` step 2
  (structural character vs inert character of the same length),
  `command-directory-injection` step 4 (both arms carry the separator). This is
  better discipline than almost every public methodology, and it is exactly what
  kills the "the WAF answered differently" false positive.
* **Baseline invariance as a precondition, not an afterthought.** Sending the
  baseline twice and refusing to grade an unstable route is rare and correct.
* **Repeat policies with a stated floor and a stated ceiling.**
  `command-directory-injection` step 4 ("five rounds... a third five is not a
  measurement, it is a route being hammered until it agrees") is the right
  instinct, and the ssti second round with a *different* arithmetic result is
  the correct guard against a page that merely contains `49`.
* **Filter-vs-sink disambiguation.** `sql-injection` step 5 and
  `deserialization` step 5 both send a probe that looks equally hostile but
  cannot resolve. That single request is the difference between an accepted
  report and the commonest false positive in each class.
* **Neighbour routing.** Each playbook names the two or three adjacent classes
  and the tell that separates them. This is what stops a client-side template
  evaluation being filed as SSTI.
* **Two-program-controlled-hosts SSRF.** `ssrf-url-routing` proving authority
  confusion by differencing *two* hosts we own, rather than by hitting
  `169.254.169.254`, is a genuinely better proof than what most public writeups
  show, and it is safe by construction.
* **Honest refusals with reasons.** Every step 6/7/8 says what is out and why,
  and distinguishes "we are not allowed" from "this proves nothing new".
* **Formula injection framed correctly.** `spreadsheet-injection` is the only
  public treatment I have seen that models the interpreter as being on the
  *reader's* machine and that adds a second record to separate "this value was
  escaped" from "every value is escaped".

## Missing techniques (ranked by expected yield on a real bounty program)

### 1. Error-based and boolean-error-based SSTI / code injection

Since Kettle's 2015 SSTI work the community has had two modes: rendered output
and time-based blind. Vladislav Korchagin's *Successful Errors* adds two more,
and it took first place in PortSwigger's Top 10 of 2025. Error-based: make the
injected expression's *result* become part of an exception message the app
prints verbosely, e.g. `getattr("", OUTPUT)` in Python, `call_user_func(OUTPUT)`
in PHP, `File.read(OUTPUT)` in Ruby, `require(OUTPUT)` in Node. Boolean
error-based blind: use a divide-by-zero pattern such as `1/(OUTPUT)` so that an
error fires only when a condition is true, and read the difference in status
code, content length, encoding or headers. There is also a generic
language-fingerprint payload, `(1/0).zxy.zxy`, whose error text names the
runtime. Coverage claimed: Python, PHP, Java, Ruby, NodeJS, Elixir; Jinja2,
Twig, Freemarker, Velocity, Dust.JS, SpEL, OGNL.

Why it finds bugs today: our current probe needs the parameter to be *reflected*
and needs the evaluated result to reach the body. Most real SSTI sinks are not
reflected — an email subject, a PDF template, a notification body, a filename
template, a report title. Error-based turns all of those into readable sinks
without any sandbox escape, and boolean error-based works when errors are
suppressed.

Belongs in: `ssti` (both modes), and the generic `(1/0)`-style language
fingerprint also belongs in `command-directory-injection` as a non-shell code
injection tell.

What our playbook must observe: the response's *error text* as a first-class
observation kind (`error_detail` already exists in `structured-injection`'s
evidence contract but not in `ssti`'s), plus a boolean differential on status /
length / headers. Both are response-difference channels. No collaborator needed.

Sources: https://github.com/vladko312/Research_Successful_Errors (report v1.1,
22 February 2026) **[fetched]**;
https://portswigger.net/research/top-10-web-hacking-techniques-of-2025
(5 February 2026) **[fetched]**; https://github.com/vladko312/SSTImap
**[fetched]**.

### 2. ORM leak: relational filter traversal and operator injection over query strings

Alex Brown's *Leaking More Than You Joined For* (elttam) took second place in
the 2025 list. Where a search/filter API forwards user-controlled key names into
an ORM, the attacker can traverse relations and query fields that were never
meant to be readable: Django's `created_by__user__username__contains` double
underscore traversal, Prisma's `{"resetToken": {"not": "E"}}`, the *same* Prisma
operator delivered as a query string via the extended parser
(`resetToken[not]=E`) or via a cookie (`Cookie: resetToken=j:{"not":"E"}`),
Sequelize symbol-operator mapping, Ransack global attribute filtering, Beego
filter expressions, and Microsoft OData `$filter` / `$expand`. Ordering
operators (`gt`, `lte`, `startswith`) leak character ordering, so a password
reset token or a password hash falls out one character at a time from response
length differences alone.

Why it finds bugs today: it is a *feature* on almost every list endpoint with a
rich filter API, it needs no quote, no metacharacter and no engine-specific
syntax, and CVEs kept landing through 2025 (Harbor CVE-2025-30086 via Beego,
Strapi CVE-2023-34235, Directus CVE-2025-64748).

Belongs in: primarily `orm` (`injection.query_field`, outside this cluster's
read set — verify the trigger set there), with a directly-affecting change to
`nosql-injection`: our operator playbook triggers only on `json_request`, so
`resetToken[not]=E` in a query string and the `j:`-prefixed cookie form are
currently unreachable.

What our playbook must observe: a response differential on a *paged list*
(count, length, membership of a row we own), against a control that is a
non-operator key of the same shape. Response-difference only.

Sources: https://www.elttam.com/blog/leaking-more-than-you-joined-for/
(18 December 2025) **[fetched]**.

### 3. Argument injection without shell metacharacters

Our `command-directory-injection` is built entirely around shell metacharacters
(separator, substitution, newline) and a bounded sleep. That misses the class
that is currently landing: the application uses `execve`/`execFile`/`ProcessBuilder`
with *no shell at all*, and the untrusted string still lands as an argument.
Anything starting with `-` or `--` is parsed as an option by the callee. Trail
of Bits documented `go test -exec`, `git show --format/--output`, `ripgrep
--pre`, and `fd -x` as full RCE from an allowlisted command name. Git in
particular exposes `--upload-pack`, `--receive-pack`, `core.fsmonitor` and
`core.gitProxy` through unsanitised clone URLs, which is reachable through
repository-integration features in a lot of bounty scope.

Orange Tsai and splitline's *WorstFit* adds the Windows leg: fullwidth and
currency characters are best-fit mapped to `"`, `\` and `/` by ANSI APIs *after*
escaping, so `escapeshellarg()` is not a defence. It produced PHP-CGI
CVE-2024-4577, Excel CVE-2024-49026, Subversion CVE-2024-45720, Perforce
CVE-2024-8067, and argument splitting in curl, OpenSSL, Perl, PostgreSQL,
TortoiseGit and RStudio.

Belongs in: `command-directory-injection` (rewrite), with a second trigger set
so it is not restricted to `file_parameter` + `multipart_request`.

What our playbook must observe: an *observably inert* flag whose only effect is
a different response — a long-form flag the binary rejects (non-zero exit, error
text naming the binary), or a flag that changes the output format of a value the
route already returns. That is a response/`error_detail` channel, not timing,
and it is strictly safer than a sleep.

Sources: https://blog.trailofbits.com/2025/10/22/prompt-injection-to-rce-in-ai-agents/
(22 October 2025, Will Vandevanter) **[fetched]**;
https://blog.orange.tw/posts/2025-01-worstfit-unveiling-hidden-transformers-in-windows-ansi/
(10 January 2025, Orange Tsai and splitline) **[fetched]**;
https://www.fastly.com/blog/back-to-basics-os-command-injection
(15 July 2025, updated September 2025, Matthew Mathur) **[fetched]**.

### 4. XXE, which we currently refuse outright

`structured-injection` step 7 forbids *any* doctype or entity declaration, "not
even one whose replacement is a literal string". That removes the single
highest-paying vulnerability in the document-parser class from the harness. The
technique set is mature but still lands: internal entity expansion, external
`SYSTEM` entities, parameter entities, XInclude when the doctype is stripped,
and — critically for a harness that wants to avoid a collaborator — the
error-based local-DTD technique (Arseniy Sharoglazov, ranked #7 in PortSwigger's
2018 list), which repurposes a DTD already present on the target's filesystem to
redefine an entity so that the *parse error* carries the file contents. Carrier
formats matter as much as the technique: SVG, DOCX, XLSX, SOAP and SAML all
reach XML parsers through routes that never look like "an XML endpoint".

Why it still finds bugs: parser defaults improved but SVG/office-document
ingestion and SOAP/SAML endpoints frequently use a differently-configured
parser than the main API.

Belongs in: `structured-injection` (a new step), with a trigger widened beyond
`xml_request`, and a hand-off from `file-upload` for SVG/DOCX/XLSX carriers.

What our playbook must observe: with a literal internal entity, whether the
replacement text appears where the entity reference was — pure response
difference. With the local-DTD variant, the parser error text. With a
`SYSTEM` entity pointed at our *own* callback host, an arrival receipt, which
this harness already records.

Sources: https://portswigger.net/web-security/xxe/blind **[listing]** (PortSwigger
Web Security Academy page on blind XXE, local-DTD technique credited to Arseniy
Sharoglazov); https://portswigger.net/research/the-fragile-lock (10 December
2025, Zakhar Fedotkin) **[fetched]** for the SAML/XML-parser leg.

### 5. SSRF response oracles: redirect loops and status-code escalation

Shubham Shah (Searchlight Cyber) published a technique that converts *blind*
SSRF into full response disclosure: serve the fetcher a redirect chain whose
status codes increment on each hop. The target application followed redirects
normally and failed silently on JSON parse errors at low redirect counts, but
once the status codes reached the 305-310 range it dumped the entire redirect
chain — headers and bodies — bypassing its own response filtering. The
underlying client was libcurl; the bug was the application's error handling at
the redirect threshold.

Why this matters for us specifically: every hop can be hosted on a
program-controlled host. It is the rare SSRF escalation that is completely
compatible with our "two hosts we own" ceiling, and it directly addresses what
`ssrf-url-routing` step 6 currently calls "the commonest inconclusive here" —
the route that fetches and tells the caller nothing.

Belongs in: `ssrf-url-routing` (new step), and it also upgrades the hand-off to
`webhooks` from "give up" to "try the oracle first".

What our playbook must observe: the body of the final arm, and the difference
between arms at different redirect depths. Response difference only, given a
controlled redirect host.

Sources: https://slcyber.io/research-center/novel-ssrf-technique-involving-http-redirect-loops/
(23 June 2025, Shubham Shah) **[fetched]**.

### 6. Deserialization severity by runtime: Marshal / pickle / unserialize are RCE by presence

Our `deserialization` playbook asks one good question — who chose the type — and
that is the right question for Java, Jackson polymorphic typing and .NET, where
exploitability depends on the classpath. It is the *wrong ceiling* for Ruby and
Python. Luke Jahnke's Ruby 4.0 universal chain works unchanged from Ruby 3.3
through 4.0.6, needs no application-specific gems, and relies on foundational
language behaviours (Hash calling `hash` on keys during load, C-level failure
tolerance in `Time` deserialization) that cannot be patched away gadget by
gadget. His stated conclusion: "Marshal.load on untrusted input is command
execution, on the current release, with no dependencies." Trail of Bits'
retrospective shows the same cycle across `Marshal`, `YAML.load`/Psych, JSON and
Oj, and Include Security showed Rails-scoped chains in 2024.

Why it changes our reporting: for these runtimes, *demonstrating that a
caller-supplied blob reaches the sink* is the whole finding, at critical
severity, without any gadget. That is exactly what our type-swap differential
already proves — but the playbook currently reports it as a neutral
`injection.object_graph` with impact left as an argument.

Belongs in: `deserialization` (severity/impact step), plus a YAML branch: the
format list in step 1 has no entry for YAML, and `YAML.load`, SnakeYAML and
`yaml.load` without `SafeLoader` are all live sinks.

What our playbook must observe: nothing new — the existing differential suffices.
The change is in the claim, not the probe.

Sources: https://www.elttam.com/blog/ruby-4-0-universal-rce-deserialization-gadget-chain
(14 August 2026, Luke Jahnke) **[fetched]**;
https://blog.trailofbits.com/2025/08/20/marshal-madness-a-brief-history-of-ruby-deserialization-exploits/
(20 August 2025) **[fetched]**;
https://blog.includesecurity.com/2024/03/discovering-deserialization-gadget-chains-in-rubyland/
(March 2024, Alex Leahu) **[listing]**;
https://github.com/thezdi/presentations/blob/main/2023_Hexacon/whitepaper-net-deser.pdf
(Piotr Bazydło, *Exploiting Hardened .NET Deserialization*, ranked #2 in
PortSwigger's Top 10 of 2023) **[listing]**.

### 7. Filename and handler confusion on upload and retrieval

`file-upload` currently tests exactly one thing: same bytes, two extensions,
does the retrieval's content type change. That misses the entire modern
filename-parsing surface. Orange Tsai's *Confusion Attacks* showed three
primitives in Apache alone: filename confusion (`/admin.php%3Fooo.php` truncates
at the encoded `?` in `mod_rewrite` and bypasses `Files` directives while PHP-FPM
still executes the file — CVE-2024-38474/38473/38475), DocumentRoot confusion
(source disclosure of a PHP file requested through an absolute path —
CVE-2024-38472, CVE-2024-39573), and handler confusion (a CGI `Location` header
plus CRLF sets `Content-Type: application/x-httpd-php` on an arbitrary resource
— CVE-2024-38476, CVE-2023-38709). Add WorstFit best-fit mapping of Unicode to
`/` and `\` inside filenames, and the classic set our playbook never sends:
double extension, trailing dot, trailing space, `;`, null byte, and a path
separator in the multipart `filename` parameter.

Belongs in: `file-upload` (a new step between the current 4 and 5), with the
retrieval-side handler question staying in `file-resolution`.

What our playbook must observe: the retrieval's status, handler, content type and
disposition — all four are already recorded in step 3. This is a pure extension
of the existing comparison to more name shapes. Response difference only.

Sources: https://blog.orange.tw/posts/2024-08-confusion-attacks-en/
(9 August 2024, Orange Tsai) **[fetched]**;
https://blog.orange.tw/posts/2025-01-worstfit-unveiling-hidden-transformers-in-windows-ansi/
(10 January 2025) **[fetched]**.

### 8. Parser differentials as a first-class class

joernchen's OffensiveCon 2025 talk *Parser Differentials: When Interpretation
Becomes a Vulnerability* took tenth place in the 2025 list and used YAML as the
case study: two implementations of the same format disagree about duplicate
keys, merge tags and error recovery, and the gap between them is the bug.
DarkForge Labs then published a concrete PoC in which one YAML document returns a
*different value for the same key* under Go `yaml.v3`, Ruby Psych, JS-YAML and
PyYAML `safe_load` simultaneously, with no parser raising an error. PortSwigger's
*The Fragile Lock* is the same shape in SAML: attribute pollution (`ID` vs
`samlp:ID`), namespace confusion between REXML and Nokogiri, and void
canonicalisation producing a valid digest over empty content. Gareth Heyes'
*Splitting the Email Atom* is the same shape again in email addresses
(RFC 2047 encoded-word, malformed punycode, Unicode overflow), and it produced
verified-domain bypasses at GitHub, Zendesk and GitLab.

Why it finds bugs: every stack has at least two parsers for the same bytes — WAF
and app, validator and consumer, signature checker and claim reader.

Belongs in: **new playbook: `parser-differential`**, or a widened
`structured-injection` covering YAML and JSON alongside XML. Either way it needs
its own output class; `injection.document_parser` does not describe "two
consumers read this differently".

What our playbook must observe: two *different* responses from the same bytes
sent through two paths (e.g. two content-types, two encodings, two field
spellings), or one response that proves the second consumer read a value the
first did not. Response difference only.

Sources: https://www.youtube.com/watch?v=Dq_KVLXzxH8 (joernchen, OffensiveCon
2025) **[listing]**;
https://blog.darkforge.io/yaml/merge/parser/differential/research/2026/02/11/YAML-Merge-Tags-and-Parser-Differentials.html
(11 February 2026, DarkForge Labs) **[fetched]**;
https://portswigger.net/research/the-fragile-lock (10 December 2025, Zakhar
Fedotkin) **[fetched]**;
https://portswigger.net/research/splitting-the-email-atom (7 August 2024,
Gareth Heyes) **[fetched]**.

### 9. Unicode normalization and best-fit as a shared filter-bypass layer

Ryan and Isabella Barnett's *Lost in Translation: Exploiting Unicode
Normalization* placed fourth in the 2025 list. The pattern is that a WAF or
validator sees one string and the backend, after NFKC normalization or Windows
best-fit mapping, sees another — fullwidth `＜` becoming `<`, high codepoints
modulo-ing down to ASCII, `¥` becoming `\`. WorstFit is the Windows-native
version of the same idea, and *Splitting the Email Atom* is the RFC-encoding
version.

Belongs in: **a shared skill**, not one playbook. Every playbook in this cluster
has a "rule out the filter" or "encoding ladder" step
(`sql-injection` 5, `structured-injection` 4, `command-directory-injection` 7)
and each currently improvises its own single probe.

What our playbook must observe: a variant that is byte-different but
normalisation-equivalent to a refused payload, reproducing the refused payload's
*sink* behaviour rather than its rejection. Response difference only.

Sources: https://www.youtube.com/watch?v=ETB2w-f3pM4 (Ryan and Isabella Barnett,
ranked #4 in PortSwigger's Top 10 of 2025) **[listing]**;
https://blog.orange.tw/posts/2025-01-worstfit-unveiling-hidden-transformers-in-windows-ansi/
(10 January 2025) **[fetched]**;
https://portswigger.net/research/splitting-the-email-atom (7 August 2024)
**[fetched]**.

### 10. Server-side prototype pollution, detected from response shape

Gareth Heyes' technique set is older than three years in origin (February 2023)
but is still landing on Node/Express targets and is *unusually* well suited to
this harness because every detection method is a deliberate, non-destructive
response difference: polluting `json spaces` reformats JSON output; polluting
`parameterLimit` makes the app silently drop extra query parameters, visible
through reflection; polluting `content-type`/charset changes how the body is
parsed; `status` override produces an unusual code such as 510. None of these
break the application, which is the whole point of the paper.

Belongs in: **new playbook: `prototype-pollution`** (server-side). It is not
`injection.object_graph` — no type is chosen and nothing is reconstructed — and
it is not `injection.query_operator`.

What our playbook must observe: JSON whitespace in the response body, a dropped
query parameter, or an anomalous status code, each against an unpolluted
baseline and a same-shape control key that is not `__proto__`.

Sources: https://portswigger.net/research/server-side-prototype-pollution
(15 February 2023, updated 28 March 2023, Gareth Heyes) **[fetched]**.

### 11. XSLT injection

No playbook in the cluster mentions XSLT. Where a user-controlled value lands
inside a stylesheet, or where a stylesheet itself is user-supplied, the engine
gives local file read, SSRF, processor/version disclosure and — via extension
functions in several common configurations — RCE. libxslt kept producing CVEs
through 2025 (CVE-2025-10911 use-after-free, CVE-2025-11731 type confusion in
`exsltFuncResultComp()`, both DoS), and a 2025 academic study of open-source
projects reported six CVEs from directly exploitable XSLT injection.

Belongs in: `structured-injection` (a branch alongside XPath).

What our playbook must observe: the safe probe is `system-property('xsl:vendor')`
and `system-property('xsl:version')` — read-only, no file, no network, and the
vendor string in the response body *is* the proof that the value became
stylesheet. Response difference only.

Sources: the libxslt CVE identifiers and the 2025 study above came from search
result summaries only, not from fetched pages; treat CVE numbers as needing
confirmation against https://nvd.nist.gov before they appear in a report.
Supporting listing: https://hacktricks.wiki/en/pentesting-web/xslt-server-side-injection-extensible-stylesheet-language-transformations.html
**[listing]**.

### 12. Archive extraction: Zip Slip, symlink entries and TOCTOU

`file-upload` step 8 refuses "an archive that unpacks outside its directory"
without ever asking whether the route extracts archives at all. Zip Slip is old
(2018) but kept landing in 2025: CVE-2025-3445 in Go's `mholt/archiver`
(`archiver.Unarchive()` following crafted symlinks), and 7-Zip CVE-2025-11001 /
CVE-2025-11002 fixed in 25.00 (July 2025) for symlink entries writing outside
the extraction directory.

Belongs in: `file-upload` (a new, separately approved step) or **new playbook:
`archive-extraction`**, because the mutation profile is different enough from
"store three marked objects" to deserve its own ceiling.

What our playbook must observe: the safest observation is the application's own
*listing* of extracted entries — if the app shows the stored path and it still
contains a traversal component, the extractor did not normalise. Response
difference only, no write outside the sandbox.

Sources: https://research.jfrog.com/vulnerabilities/archiver-zip-slip/
**[listing]** (CVE-2025-3445, mholt/archiver); 7-Zip CVE-2025-11001/11002 and
the 25.00 fix appeared in search-result summaries only — confirm against the
vendor advisory before citing in a report.

### 13. Error/oracle-based SQL injection without sleeping and without extraction

`sql-injection` has exactly one channel: a boolean differential. It explicitly
refuses time-based and out-of-band, which is right, but it has no *error* channel
at all — and the error channel is both faster and more convincing to a triager.
A type-cast or conversion error (`CAST`, `::int`, implicit numeric coercion,
`XMLTYPE`, `CONVERT`) fires on the true arm and not the false arm, and the
resulting engine-named error is a much stronger artifact than a length delta.
Korchagin's boolean-error primitive is the same idea generalised. The direction
of travel in this class is also worth noting: Paul Gerste's DEF CON 32 work
moved SQL injection down to the *wire protocol* — a >4GB string overflowing a
PostgreSQL protocol message length and writing into the next value, plus an
equivalent against MongoDB — which is not safely testable but is the reason a
"parameterised queries everywhere" answer from a program is not a full
refutation.

Belongs in: `sql-injection` (new step, before the filter probe).

What our playbook must observe: `error_detail` — which is not in
`sql-injection`'s `bb:evidence` contract today. Response difference only.

Sources: https://media.defcon.org/DEF%20CON%2032/DEF%20CON%2032%20presentations/DEF%20CON%2032%20-%20Paul%20Gerste%20-%20SQL%20Injection%20Isn%27t%20Dead%20Smuggling%20Queries%20at%20the%20Protocol%20Level.pdf
(DEF CON 32, August 2024, Paul Gerste; ranked #2 in PortSwigger's Top 10 of
2024) **[listing]**;
https://portswigger.net/research/top-10-web-hacking-techniques-of-2024
(4 February 2025) **[fetched]**;
https://github.com/vladko312/Research_Successful_Errors **[fetched]**.

### 14. The single-packet timing attack, as a replacement for our sampling loop

`command-directory-injection` step 4 uses five interleaved rounds of ten requests
and compares two distributions. James Kettle's 2024 work makes that
substantially better: coalescing HTTP/2 request frames into a single TCP packet
(using a ping frame as a sacrificial packet to force OS-level coalescing) removes
network jitter entirely and resolves sub-millisecond differences on live
internet targets. He explicitly applies it to detecting blind server-side
injection in JSON, SQL and parameter parsing, and to server-side parameter
pollution via `%23` and `%21`.

Why it matters here: with sub-millisecond resolution, the "bounded delay" our
command playbook asks for can shrink from seconds to the cost of a slower code
path — which removes the connection-pool risk step 5 rightly worries about.

Belongs in: **a shared skill** used by `command-directory-injection`,
`sql-injection` and `deserialization`.

What our playbook must observe: paired-request arrival timing, which requires
harness support for sending two requests in one packet. Timing channel, no
collaborator.

Sources: https://portswigger.net/research/listen-to-the-whispers-web-timing-attacks-that-actually-work
(7 August 2024, updated 18 November 2024, James Kettle) **[fetched]**.

### 15. SOAP / WSDL-driven client proxies (.NET)

Piotr Bazydło's *SOAPwn* placed fifth in the 2025 list. Where a .NET application
builds a SOAP client proxy from a WSDL document whose URL the caller influences,
the attacker controls what the client does with the request — including,
according to secondary commentary on the paper, a `soap:address` with a `file://`
scheme that turns the outbound SOAP body into an arbitrary file write.

Caveat: the whitepaper PDF was fetched but returned unparseable binary. The
title, author, URL and ranking are from PortSwigger's index page; the `file://`
`soap:address` mechanism is from a third-party commentary and should be verified
against the paper before it is relied on.

Belongs in: `ssrf-url-routing` (a WSDL/service-descriptor branch — the route
takes a URL and a *client* is built from what comes back) with a hand-off to
`file-upload` for the write leg.

What our playbook must observe: the minimum safe proof is an arrival at our own
callback host, i.e. the .NET client fetched our WSDL. That alone is reportable
and needs nothing else.

Sources: https://watchtowr.com/wp-content/uploads/SOAPwnwatchtowr_soappwn-research-whitepaper_10-12-2025.pdf
(Piotr Bazydło; **fetch returned unparseable binary**);
https://portswigger.net/research/top-10-web-hacking-techniques-of-2025
(5 February 2026) **[fetched]** for title/author/rank;
https://dev.to/latentbreach/portswiggers-top-10-web-hacking-techniques-of-2025-a-deep-dive-25k6
**[fetched, secondary commentary — treat as unverified]**.

### 16. PHP filter-chain sinks, and the error oracle as a no-collaborator channel

Rémi Matasse's error-based oracle uses `php://filter` chains with `iconv`
conversions that amplify data size until PHP's `memory_limit` is hit, and the
`dechunk` filter which drops output when the first character is hexadecimal —
giving a pure binary oracle from the response alone. Around fifteen PHP
filesystem functions are affected (`file_get_contents`, `readfile`, `file`,
`fopen`, `md5_file`, `sha1_file`, `hash_file`, `getimagesize`, `parse_ini_file`,
`copy`), and no out-of-band channel is required. This was ranked #4 in the 2023
list and the tooling has continued to develop since.

Belongs in: `file-resolution` for the read primitive (outside this cluster's read
set), but the *sink discovery* belongs here: `file-upload` and
`ssrf-url-routing` both handle parameters that may be a full URI passed to one
of those functions, and neither currently probes for a stream wrapper.

What our playbook must observe: response difference between a `php://filter`
chain that triggers the memory error and one that does not, against a plain-value
baseline. Response difference only.

Sources: https://www.synacktiv.com/en/publications/php-filter-chains-file-read-from-error-based-oracle
(21 March 2023, Rémi Matasse) **[fetched]**;
https://portswigger.net/research/top-10-web-hacking-techniques-of-2023
(19 February 2024) **[fetched]**.

### 17. CRLF injection into headers, and its desync consequence

`structured-injection` names "a line-oriented sink" and a CRLF probe, then
concedes in step 6 that a silent 200 is the common case and it has no in-band
signal. Tom Stacey and Tobia Righi's 2026 work supplies exactly that signal:
where injected CRLF reaches an upstream request, an injected `Expect: asdf`
produces a 417 and an injected `Transfer-Encoding: x` produces a 501 —
deterministic, harmless status codes that confirm header injection without
touching another user's connection. Their primary target was nginx configurations
using `$uri` in `proxy_pass` (which URL-decodes CRLF before forwarding), plus
OpenResty and Tengine.

Belongs in: `structured-injection` (replace the "silent 200 is inconclusive"
outcome with these probes), with the desync escalation staying in `http-desync`.

What our playbook must observe: the status code of the arm. Response difference
only, single connection, no cross-user effect.

Sources: https://portswigger.net/research/crlf-powered-desync-attacks
(5 August 2026, Tom Stacey with Tobia Righi) **[fetched]**.

### 18. Template-engine sandboxes are not a mitigation, and should not be argued as one

Our `ssti` step 7 refuses sandbox escapes, correctly. The report-side
consequence needs stating: a triager who replies "the engine is sandboxed" is
not describing a fix. Jinja2 needed CVE-2025-27516 (sandbox breakout via the
`|attr` filter reaching `str.format`, fixed in 3.1.6), preceded by the 3.1.5 fix
for indirect `str.format` execution; Jinjava needed CVE-2025-59340 (sandbox
bypass through JavaType deserialization, fixed in 2.8.1).

Belongs in: `ssti` (the impact argument in step 7).

What our playbook must observe: nothing new. This is report language, not a probe.

Sources: https://github.com/advisories/GHSA-cpwx-vrp4-4pq7 (CVE-2025-27516,
Jinja2) **[listing]**; CVE-2025-59340 (Jinjava) appeared in search-result
summaries only — confirm against the GitHub Advisory Database before citing.

## What in our playbooks looks stale or weak

* **`ssti` has one detection mode and the wrong trigger.**
  `bb:triggers_all: ["authenticated_endpoint", "reflected_parameter", "tech_template"]`
  means the playbook can only ever run where recon already saw reflection. Blind
  SSTI — the majority of real sinks — is structurally unreachable. It also has
  `bb:baseline: none`, so it has no invariance check, and its evidence contract
  has only `reflected_input`, no `error_detail`. Its engine list omits SpEL,
  OGNL, Handlebars, Nunjucks, Pug, Mako and Smarty.
* **`structured-injection`'s blanket doctype refusal removes the class's main
  vulnerability.** The stated reason — "a declaration handed to a parser whose
  expansion behaviour is the thing nobody has measured yet" — is a good reason to
  forbid *expansion*, not to forbid a literal internal entity whose replacement
  is a fixed string and which cannot resolve anything. As written, the harness
  cannot report XXE at all.
* **`structured-injection` triggers only on `xml_request`.** XXE and XSLT reach
  parsers through SVG and office-document uploads, SOAP endpoints, SAML
  assertions, and JSON endpoints that also accept `application/xml` — none of
  which recon will have flagged as `xml_request`.
* **`nosql-injection` triggers only on `json_request` and only tests one
  operator.** The 2025 state of the art delivers the same operator through query
  strings (`field[not]=x`), through cookies (`j:{...}`), and against Prisma,
  Sequelize, Strapi, Beego and OData rather than MongoDB. `$regex` as a boolean
  character oracle is absent.
* **`sql-injection` has no error channel** and requires `query_parameter`, so
  SQLi in a JSON body is out of reach. Its step 6 says LDAP filter injection
  lands in `injection.query_language` and belongs here, but there is no LDAP step
  anywhere: no `*` wildcard-widening probe, no `)(` filter-closing probe, no
  attribute-name variant. That is a promise the cluster does not keep.
* **`command-directory-injection` is upload-only and shell-only.** Its trigger set
  is `file_parameter` + `multipart_request`, so command injection in a hostname,
  a filter string, a conversion option or a git URL is unreachable. Its whole
  model is shell metacharacters plus a sleep, which is the 2015 model; argument
  injection into `execve` has no step. It mentions `cmd.exe` ignoring semicolons
  but not best-fit ANSI mapping, which is the current Windows primitive.
* **`file-upload` grades one property with one probe.** Same bytes, two
  extensions. No filename parsing shapes, no content sniffing, no
  `Content-Type` versus extension disagreement, no magic-byte/extension
  mismatch, no archive, no image or document parser, no path traversal on write,
  no second identity retrieving the object. Step 4 says removal happens in step
  4 and step 8 says "removed in step 4" — but the numbered heading order is
  store, retrieve, difference, rule out, claim, ceiling, so the cleanup
  reference should be checked.
* **`ssrf-url-routing` triggers on `read_method` only.** Fetchers reached by POST
  — webhook configuration, import-by-URL, avatar-by-URL, PDF render, SSO metadata
  URL, WSDL — are excluded. It refuses redirect *chains* (step 3 allows one
  redirect), which is precisely the primitive in the highest-ranked 2025 SSRF
  technique. It references `pdf-generators.md` and `dns-rebinding.md` but has no
  step for either.
* **`deserialization`'s format list has no YAML entry**, and its impact model is
  runtime-neutral where the runtimes are not.
* **`spreadsheet-injection` is CSV-and-leading-character only.** It does not
  consider XLSX exports where the writer emits a *formula-typed cell* rather than
  a text cell (a stronger finding, and one where an apostrophe prefix is not even
  the relevant control), nor the `\t` / `\r` prefix variants that get past a
  leading-character filter.
* **Every playbook improvises its own filter-bypass probe.** Three different
  one-shot "encoding ladder" steps exist with three different rules. Unicode
  normalization and Windows best-fit are the current bypass primitives and appear
  in none of them.
* **Staleness dates.** Seven of the nine carry `bb:stale_after: 2027-03-15` or
  `2027-04-15`. Given that the top technique in this cluster (error-based SSTI)
  was published after these were written, the review cadence is too slow for the
  injection category specifically.

## Concrete change proposals per playbook

* **`sql-injection/playbook.md`** — add a step between the current 4 and 5:
  "Ask the engine to fail". Send a third arm whose clause forces a type-cast or
  conversion error in the named dialect, held against the same control; add
  `error_detail` to `bb:evidence`; treat an engine-named error with a stable
  control as `supported` in its own right. Separately, rewrite step 6's LDAP
  sentence into a real branch or delete the claim, and widen `bb:triggers_all`
  so a JSON body parameter qualifies.
* **`nosql-injection/playbook.md`** — rewrite step 1 and `bb:triggers_all` to
  cover query-string bracket operators (`field[not]=x`), the `j:`-prefixed cookie
  form, and non-Mongo query builders (Prisma, Sequelize, Strapi, Beego, OData
  `$filter`); add a step 3b that uses `$regex`/`startswith` as a *bounded* boolean
  oracle against a field on an identity we own, never another user's.
* **`ssti/playbook.md`** — add a step 2b, "If nothing is reflected, make it
  fail": the error-based and boolean-error-based modes, with the generic
  language-fingerprint probe; add `error_detail` to `bb:evidence`; set
  `bb:baseline: stable_session`; drop `reflected_parameter` from
  `bb:triggers_all` so blind sinks are reachable; extend the engine/delimiter
  list in step 1 to SpEL, OGNL, Handlebars, Nunjucks, Pug, Mako and Smarty; add
  one sentence to step 7 stating that "the engine is sandboxed" is not a fix,
  with the Jinja2/Jinjava CVEs as the argument.
* **`command-directory-injection/playbook.md`** — add a step 3b, "Ask whether it
  was a shell at all": argument injection via a leading `-`/`--` flag that the
  callee rejects observably, with a same-length control that is not a flag; add a
  Windows best-fit variant (fullwidth quote, `¥`) to the family list in step 4;
  widen `bb:triggers_all` beyond `file_parameter` + `multipart_request` so
  non-upload parameters are reachable. This step is strictly *lower* risk than
  the existing timing step and should be tried before it.
* **`structured-injection/playbook.md`** — rewrite step 7's absolute doctype
  refusal into a graded one: permit a single internal entity whose replacement is
  a literal string (no `SYSTEM`, no parameter entity, no nesting, no recursion)
  and grade its expansion; add a step for the error-based local-DTD variant; add
  an XSLT branch whose only probe is `system-property('xsl:vendor')`; replace the
  "silent 200 is inconclusive" outcome for line-oriented sinks with the `Expect:
  asdf` → 417 and `Transfer-Encoding: x` → 501 probes; widen `bb:triggers_all`
  beyond `xml_request` to cover SVG/DOCX/XLSX carriers and content-type override.
* **`spreadsheet-injection/playbook.md`** — extend step 4 so the tool run also
  reports the *cell type* when the export is XLSX (a formula-typed cell is a
  strictly stronger finding than a text cell beginning with `=`), and add the
  `\t` and `\r` prefix variants to step 2's variant so a leading-character filter
  is distinguishable from real escaping.
* **`deserialization/playbook.md`** — add YAML to the format signature list in
  step 1 (`YAML.load`, SnakeYAML, `yaml.load` without a safe loader, and the
  `!!python/object` / `!!ruby/object` tag shapes); add a severity clause to step 6
  stating that for Ruby `Marshal`, Python `pickle` and PHP `unserialize`, a
  supported verdict is critical on its own because a universal, dependency-free
  chain exists for the current release — with the elttam citation — while for
  Java/Jackson/.NET the severity depends on the classpath and stays as argued.
* **`file-upload/playbook.md`** — add a step 4b that keeps the bytes constant and
  varies the *name shape* rather than only the extension: double extension,
  trailing dot, trailing space, `;`, `%3F` truncation, path separator in the
  multipart `filename`, and a best-fit Unicode character that maps to `/` or `\`;
  add a step that sends the same bytes with a `Content-Type` that disagrees with
  the extension, to separate sniffing from naming; and reconcile the cleanup
  cross-reference between step 4 and step 8.
* **`ssrf-url-routing/playbook.md`** — add a step 5b for the blind case: a
  program-controlled redirect chain with incrementing 3xx status codes, which is
  the current best answer to "the route fetches and tells the caller nothing" and
  stays entirely inside the two-controlled-hosts ceiling; widen `bb:triggers_all`
  beyond `read_method` so POST-based fetchers (webhook config, import-by-URL,
  render-to-PDF, WSDL/metadata URL) are reachable; add a WSDL/service-descriptor
  branch whose sole proof is an arrival receipt on our own host.

## Detection channels

Our harness records receipts for its own callback channel, so an out-of-band
interaction is admissible evidence — but only when the destination is a host the
program controls. The split:

**Needs an out-of-band interaction channel (attacker-controlled DNS/HTTP):**

* XXE with an external `SYSTEM` or parameter entity (the local-DTD error variant
  below is the no-collaborator alternative).
* Blind SSRF where the response never returns anything (the redirect-loop oracle
  below is the alternative *if* the fetcher returns any body at all).
* SOAP/WSDL client-proxy construction — proof is the fetch of our WSDL.
* DNS rebinding, by definition (two answers for one name from our own resolver).
* Ruby/Java gadget chains that stage from a remote host — out of scope for us
  regardless.
* SMTP header injection where the message goes somewhere we cannot read.

**Works with timing alone:**

* OS command injection via a bounded sleep (our current step 4).
* Blind SQL injection via a database sleep (currently refused, and correctly).
* ORM leak character extraction via database collation comparison delays.
* Single-packet timing to detect hidden parameters, slower code paths and
  server-side parameter pollution — sub-millisecond, and the reason a large sleep
  is no longer necessary.
* PHP filter-chain oracle, partially: the memory-limit path is slower as well as
  differently-answered.

**Works from response differences alone (preferred, and the bulk of the value):**

* Boolean SQL injection (our current model), and error-based SQLi via type-cast
  errors.
* Error-based and boolean-error-based SSTI / code injection — the #1 technique of
  2025 and entirely in-band.
* ORM leak via `startswith` / ordering operators — response length and membership.
* NoSQL / query-builder operator injection, including `$regex` and `not`.
* Server-side prototype pollution via `json spaces`, `parameterLimit`, charset and
  status override.
* PHP filter-chain error oracle (`dechunk` + `iconv` memory error).
* Error-based XXE via a local DTD, and internal entity expansion.
* XSLT `system-property('xsl:vendor')` reflected into the output.
* Parser differentials — the whole class is "two responses that should have been
  one".
* CRLF header injection confirmed by `Expect: asdf` → 417 or
  `Transfer-Encoding: x` → 501.
* File upload: retrieval status, handler, content type and disposition.
* SSRF authority confusion between two controlled hosts (our current model), and
  the redirect-loop status-escalation oracle.
* Argument injection confirmed by a rejected-flag error.
* Formula injection: the observation is inside a downloaded artifact, not a
  response, but it is still in-band and reproducible.

Practical consequence: of the eighteen gaps above, thirteen are provable from
response differences alone, three from timing, and only two genuinely require the
callback channel. The harness's evidence contract is not the limiting factor —
the playbooks' step lists are.

## Safety limits worth keeping

Every technique below would execute code, write files, or destroy data on a live
target. Each is paired with the minimal proof a bounty triager still accepts.

* **SSTI sandbox escape / object-graph walk to a runtime.** Substitute:
  arithmetic evaluation in the engine's delimiters (current step 2), plus the
  error-based or boolean-error-based oracle. Both prove the caller writes template
  source. Keep refusing `__subclasses__`, class loaders, config dumps and secret
  key reads.
* **Deserialization gadget chains and payload generators (ysoserial and
  successors, `Gem::SafeMarshal` escapes, ObjectDataProvider, phar).**
  Substitute: the type-name differential with an inert standard-library type,
  plus the nonexistent-type probe. For Ruby/Python/PHP, cite the published
  universal chain as the impact argument rather than running one.
* **Full OS command execution, listeners, staged payloads.** Substitute: a
  bounded sleep whose ceiling is well under any gateway timeout, an echoed token,
  or — better, and newly proposed — an argument-injection flag whose only effect
  is an error the callee prints. Keep refusing anything that outlives the request.
* **XXE file read and SSRF via `SYSTEM` entities.** Substitute: a single internal
  entity with a literal replacement to prove expansion; the local-DTD error
  variant with an entity whose target does not exist, so the error shape is the
  proof and no file content is read. Keep refusing entity expansion bombs
  (billion laughs) absolutely — that is a denial of service, not a proof.
* **XSLT extension functions (`java:`, `exsl:document`, EXSLT file writes).**
  Substitute: `system-property('xsl:vendor')` and `system-property('xsl:version')`.
  Vendor string in the body proves the stylesheet was ours.
* **Archive extraction traversal (Zip Slip, symlink entries).** Substitute: read
  the application's own listing of extracted entry paths and show the traversal
  component survived normalisation. Never overwrite a file that existed before;
  never write outside the extraction directory without a named, tested cleanup
  route and an explicit grant.
* **Image/document converter RCE (Ghostscript `-dSAFER` escapes reached through
  ImageMagick or LibreOffice).** Substitute: a benign EPS/SVG/PostScript file
  whose only effect is a version banner or a distinctive parse error in the
  response. Proving the pipeline reaches Ghostscript is the finding; running code
  in it is not needed.
* **Protocol-level query smuggling (>4GB PostgreSQL/MongoDB message overflow).**
  Substitute: none that is safe — a 4GB request is an availability event.
  Report the driver/library version if it is disclosed, and note the class in the
  report's impact section without probing.
* **Prototype pollution that breaks the app** (polluting `status` into a
  server-wide error, or polluting a prototype that persists across requests).
  Substitute: `json spaces` and `parameterLimit`, both of which are cosmetic and
  self-reverting on process restart. Never pollute a key the process will reuse
  for other users if the runtime does not reset it.
* **CRLF/desync exploitation against other users' connections.** Substitute:
  single-connection `Expect: asdf` → 417 and `Transfer-Encoding: x` → 501. Never
  send a desync probe that could capture another user's request.
* **Cloud metadata retrieval (IMDS, GCP `Metadata-Flavor`, Azure `Metadata: true`,
  Kubernetes and Consul service addresses).** Substitute: the current two
  program-controlled hosts differential. Keep this refusal exactly as written —
  it is the single most likely way an authorized test becomes an incident.
* **Formula payloads that act (`HYPERLINK`, `WEBSERVICE`, `IMPORTXML`, DDE,
  macros).** Substitute: the formula character plus an inert marker, which is
  what `spreadsheet-injection` already does. Keep it.
* **Enumerating other users' data through a widened query** (`$ne` results, ORM
  `startswith` extraction of someone else's reset token). Substitute: run the
  oracle against a field on an identity we lease, and report that the operator was
  honoured. `nosql-injection` step 5 already states this rule; the ORM-leak
  addition must inherit it verbatim.
* **Storing anything executable** (web shell, polyglot, macro-bearing document).
  Substitute: identical inert ASCII bytes under different names. `file-upload`
  already has this right; the name-shape expansion must not weaken it.

## Sources consulted

* https://portswigger.net/research/top-10-web-hacking-techniques-of-2025
  (5 February 2026) **[fetched]** — the ranked 2025 list; supplied the titles,
  authors and URLs for the ten techniques this document builds on.
* https://portswigger.net/research/top-10-web-hacking-techniques-of-2024
  (4 February 2025) **[fetched]** — Apache confusion attacks, protocol-level
  SQLi, WorstFit, PDF.js.
* https://portswigger.net/research/top-10-web-hacking-techniques-of-2023
  (19 February 2024) **[fetched]** — PHP filter chains, hardened .NET
  deserialization, SMTP smuggling, HTTP parser inconsistencies.
* https://github.com/vladko312/Research_Successful_Errors (report v1.1,
  22 February 2026, Vladislav Korchagin) **[fetched]** — the error-based and
  boolean-error-based SSTI/code-injection payload shapes, engine coverage and
  detection signals; the top-ranked technique of 2025.
* https://github.com/vladko312/SSTImap **[fetched]** — the four detection modes
  (rendered, error-based, boolean-error blind, time blind) and the engine list.
* https://www.elttam.com/blog/leaking-more-than-you-joined-for/
  (18 December 2025, Alex Brown) **[fetched]** — ORM leak across Django, Prisma,
  Beego, Sequelize, Ransack, Strapi, OData; the query-string and cookie delivery
  forms our `nosql-injection` triggers miss.
* https://slcyber.io/research-center/novel-ssrf-technique-involving-http-redirect-loops/
  (23 June 2025, Shubham Shah, Searchlight Cyber) **[fetched]** — the
  incrementing-status redirect loop that turns blind SSRF into full response
  disclosure using only hosts the tester controls.
* https://blog.trailofbits.com/2025/10/22/prompt-injection-to-rce-in-ai-agents/
  (22 October 2025, Will Vandevanter) **[fetched]** — argument injection through
  `go test -exec`, `git show --format/--output`, `ripgrep --pre`, `fd -x`; why
  allowlisting a command name is not a control.
* https://blog.orange.tw/posts/2025-01-worstfit-unveiling-hidden-transformers-in-windows-ansi/
  (10 January 2025, Orange Tsai and splitline) **[fetched]** — Windows best-fit
  mapping producing argument injection past `escapeshellarg()`, path traversal
  and filename smuggling; PHP-CGI CVE-2024-4577 and the surrounding CVE set.
* https://blog.orange.tw/posts/2024-08-confusion-attacks-en/
  (9 August 2024, Orange Tsai) **[fetched]** — filename, DocumentRoot and handler
  confusion in Apache, with the concrete request shapes a file-upload playbook
  should be sending.
* https://portswigger.net/research/listen-to-the-whispers-web-timing-attacks-that-actually-work
  (7 August 2024, updated 18 November 2024, James Kettle) **[fetched]** — the
  single-packet timing attack; the basis for replacing our five-round sampling
  loop and for shrinking the sleep in the command playbook.
* https://portswigger.net/research/splitting-the-email-atom
  (7 August 2024, Gareth Heyes) **[fetched]** — encoded-word, punycode and
  Unicode-overflow parser confusion in email addresses; verified-domain bypasses
  at GitHub, Zendesk and GitLab.
* https://portswigger.net/research/server-side-prototype-pollution
  (15 February 2023, updated 28 March 2023, Gareth Heyes) **[fetched]** — the
  non-destructive detection methods (`json spaces`, `parameterLimit`, charset,
  status override) that make this class safe for an automated harness.
* https://portswigger.net/research/the-fragile-lock
  (10 December 2025, Zakhar Fedotkin) **[fetched]** — SAML attribute pollution,
  namespace confusion between REXML and Nokogiri, and void canonicalisation;
  the strongest current example of a parser differential with a critical outcome.
* https://portswigger.net/research/crlf-powered-desync-attacks
  (5 August 2026, Tom Stacey with Tobia Righi) **[fetched]** — the safe CRLF
  confirmation probes (`Expect: asdf` → 417, `Transfer-Encoding: x` → 501) that
  fix our line-oriented-sink blind spot.
* https://www.synacktiv.com/en/publications/php-filter-chains-file-read-from-error-based-oracle
  (21 March 2023, Rémi Matasse) **[fetched]** — the `iconv`/`dechunk` memory-limit
  oracle and the fifteen PHP sink functions; a file-read primitive that needs no
  collaborator.
* https://blog.trailofbits.com/2025/08/20/marshal-madness-a-brief-history-of-ruby-deserialization-exploits/
  (20 August 2025) **[fetched]** — the Ruby deserialization sink inventory
  (`Marshal.load`, `YAML.load`/Psych, JSON, Oj) and the 2024 chain timeline.
* https://www.elttam.com/blog/ruby-4-0-universal-rce-deserialization-gadget-chain
  (14 August 2026, Luke Jahnke) **[fetched]** — a universal, dependency-free chain
  working from Ruby 3.3 to 4.0.6; the citation that makes "reaches Marshal.load"
  a critical finding without running anything.
* https://blog.darkforge.io/yaml/merge/parser/differential/research/2026/02/11/YAML-Merge-Tags-and-Parser-Differentials.html
  (11 February 2026, DarkForge Labs) **[fetched]** — a single YAML document
  yielding four different values across Go yaml.v3, Psych, JS-YAML and PyYAML
  `safe_load` with no parser erroring.
* https://owasp.org/Top10/2025/A05_2025-Injection/ **[fetched]** — the 2025
  injection category: 37 mapped CWEs, moved from #3 to #5, ~62,445 CVEs and
  ~1.4M occurrences; useful for framing severity in a report, not for technique.
* https://www.fastly.com/blog/back-to-basics-os-command-injection
  (15 July 2025, updated September 2025, Matthew Mathur) **[fetched]** —
  defender-side detection of command injection, including that WAFs specifically
  watch for interactsh/oast domains; relevant to why an in-band probe beats a
  collaborator probe on a WAF-fronted target.
* https://dev.to/latentbreach/portswiggers-top-10-web-hacking-techniques-of-2025-a-deep-dive-25k6
  **[fetched, secondary]** — third-party commentary on the 2025 list; used only
  for the SOAPwn mechanism, which is flagged as unverified above.
* https://watchtowr.com/wp-content/uploads/SOAPwnwatchtowr_soappwn-research-whitepaper_10-12-2025.pdf
  (Piotr Bazydło) — **fetch returned unparseable binary**; only title, author and
  ranking are asserted.
* https://www.youtube.com/watch?v=Dq_KVLXzxH8 (joernchen, *Parser Differentials:
  When Interpretation Becomes a Vulnerability*, OffensiveCon 2025) **[listing]** —
  video not transcribed; the YAML case-study framing comes from the PortSwigger
  index entry and the DarkForge PoC above.
* https://www.youtube.com/watch?v=ETB2w-f3pM4 (Ryan and Isabella Barnett, *Lost
  in Translation: Exploiting Unicode Normalization*) **[listing]** — video not
  transcribed; ranked #4 in the 2025 list.
* https://media.defcon.org/DEF%20CON%2032/DEF%20CON%2032%20presentations/DEF%20CON%2032%20-%20Paul%20Gerste%20-%20SQL%20Injection%20Isn%27t%20Dead%20Smuggling%20Queries%20at%20the%20Protocol%20Level.pdf
  (DEF CON 32, August 2024, Paul Gerste) **[listing]** — protocol-level query
  smuggling; not fetched, cited for the "parameterised queries is not a full
  refutation" point only.
* https://github.com/thezdi/presentations/blob/main/2023_Hexacon/whitepaper-net-deser.pdf
  (Piotr Bazydło, *Exploiting Hardened .NET Deserialization*) **[listing]** —
  ranked #2 in the 2023 list; not fetched.
* https://blog.includesecurity.com/2024/03/discovering-deserialization-gadget-chains-in-rubyland/
  (March 2024, Alex Leahu) **[listing]** — Rails-scoped Ruby gadget chains; not
  fetched.
* https://research.jfrog.com/vulnerabilities/archiver-zip-slip/ **[listing]** —
  CVE-2025-3445, symlink Zip Slip in Go `mholt/archiver`; not fetched.
* https://github.com/advisories/GHSA-cpwx-vrp4-4pq7 **[listing]** —
  CVE-2025-27516, Jinja2 sandbox breakout via `|attr`; not fetched.
* https://portswigger.net/web-security/xxe/blind **[listing]** — PortSwigger Web
  Security Academy page on blind XXE and the local-DTD error technique credited
  to Arseniy Sharoglazov; not fetched directly.
* https://hacktricks.wiki/en/pentesting-web/xslt-server-side-injection-extensible-stylesheet-language-transformations.html
  **[listing]** — XSLT server-side injection reference; not fetched. Lower-tier
  source, listed for completeness only.

### Search-budget note

The WebSearch budget for this session was exhausted (200/200) before three
planned searches could run: current LDAP filter-injection research, current
MongoDB-specific operator research beyond the elttam ORM paper, and a direct
search for the watchTowr SOAPwn blog post. The LDAP gap is called out above as
an unkept promise in `sql-injection` step 6 rather than as a sourced technique,
and the SOAPwn mechanism is flagged as unverified. Everything else here rests on
a page that was fetched and read.
