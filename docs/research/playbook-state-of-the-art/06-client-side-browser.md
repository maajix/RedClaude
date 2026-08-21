# 06 - Client-side and browser

Scope of this review: `browser-script`, `browser-framing`, `browser-messaging`,
`browser-storage`, `browser-realtime`, `client-side-path-traversal`, plus the
`browser-evidence` Skill they lean on. Adjacent Playbooks are named where a
technique already has a home (`cookies`, `realtime`, `external-resources`).

Everything below is written for an authorized engagement: the techniques are
listed as things our readings must be able to *observe and prove*, and every
proposal keeps the harness's read-only, one-origin, one-marker posture unless it
says otherwise in as many words.

Research window: material from 2023-2026 is preferred. Where a technique is older
and still landing, that is said explicitly.

## What we already cover well

* **Epistemics.** Every one of the six Playbooks separates *supported*,
  *refuted* and *inconclusive*, and every one of them names the control that
  makes the variant readable. That is better than almost any public client-side
  methodology, which typically reports a payload and a screenshot.
* **Provenance of the marker.** `browser-script` and `browser-messaging` plant a
  registry-owned probe rather than a plan-chosen literal. This removes the single
  most common false positive in DOM testing -- a marker that was already on the
  page.
* **The Receipt list as evidence of a negative.** `browser-messaging` step 4 uses
  the *absence* of a request to separate `injection.client_channel` from
  `injection.markup`. That is a genuinely strong idea and it is not something the
  public literature does.
* **Client-side path traversal exists at all.** Most harnesses have no CSPT
  reading. Ours has one, it differences two Receipt lists, and it correctly
  refuses to call a moved request a filesystem traversal.
* **Header policy is read, not guessed.** `browser-framing` reads
  `frame-ancestors`, `X-Frame-Options` and `SameSite` as served, with a
  foreign-`Origin` control. Correct method for the question it asks.
* **Layer attribution.** `browser-framing` step 4 and `browser-realtime` step 4
  both say which layer produced the answer and where the proxy stops. Very few
  methodologies admit their own instrument's limits in the finding.

## Missing techniques (ranked by expected yield on a real bounty program)

### 1. postMessage and cross-document messaging

A `message` listener that does not check `event.origin`, or that checks it with a
weak regex, and then routes `event.data` into `innerHTML`, `eval`,
`location`, a token store or a privileged action, is still one of the highest-paid
client-side classes on every platform. The surface has grown, not shrunk: payment
frames, chat widgets, editors, SSO brokers and design-tool embeds all talk over
`postMessage`. The mirror-image bug -- a page that *sends* a token with
`targetOrigin: "*"` -- leaks credentials to any frame that can get itself
embedded. `browser-messaging` names this source and then refuses it outright
("No action here sends one, because sending one means holding a second origin"),
which retires the class before it is tested. That refusal is wrong on the facts:
a `postMessage` can be sent from the *same* origin (an opener or a sibling frame
under our own control) and still exercise a listener with no origin check, and
the listener inventory itself is observable without sending anything.
Belongs in: `browser-messaging` (rewrite step 3).
Must observe: the set of registered `message` listeners on the document; the
handler source; the data shape each accepts; the DOM delta after one message; and
the `targetOrigin` argument of every outbound `postMessage`.
Sources: <https://www.yeswehack.com/learn-bug-bounty/introduction-postmessage-vulnerabilities> (2021-08-25, older but the class still lands);
<https://portswigger.net/burp/documentation/desktop/tools/dom-invader> (DOM Invader logs, modifies and replays web messages and auto-probes listeners -- the capability we lack).

### 2. CSPT with a write sink (CSPT2CSRF), and stored/DOM-based CSPT sources

Doyensec's CSPT2CSRF is the reason CSPT stopped being a curiosity. The front end
attaches the session, the CSRF token and the `SameSite` context to a request whose
*path* the attacker moved; the token is valid, so the token defence is irrelevant,
and because the request originates from the application's own page, `SameSite` is
irrelevant too. The sink method matters more than anything: a moved `GET` is a
weak finding, a moved `POST`/`PUT`/`PATCH`/`DELETE` is an account-affecting one.
Sources are also broader than a path parameter -- fragment, query, and stored
values that a later page reads back. Our Playbook is `read_method`-triggered,
only ever moves a `GET`, and grades a moved request that answers `404` as "still
this class", which will be triaged as informational on a real program.
Belongs in: `client-side-path-traversal` (rewrite steps 2-4; drop the
`read_method` trigger).
Must observe: the method, path, headers and body of every request the page makes,
before and after; whether a CSRF token/`Authorization` header rode along; and the
response to the moved request. A canary segment that proves the reflection reached
the path is the confirmation step Doyensec's tooling uses.
Sources: <https://blog.doyensec.com/2024/07/02/cspt2csrf.html> (2024-07-02, Maxence Schmitt; Mattermost and Rocket.Chat);
<https://blog.doyensec.com/2025/03/27/cspt-resources.html> (2025-03-27, resource index: CSPT->JSONP->XSS, CSPT->open redirect->XSS, CSPT->stored ID);
<https://github.com/doyensec/CSPTBurpExtension> (source = reflected query parameter, sink = path of a later request, confirmed by canary token; explicitly cannot find DOM-based or stored CSPT without the canary);
<https://swisskyrepo.github.io/PayloadsAllTheThings/Client%20Side%20Path%20Traversal/> (sink taxonomy and encoding-level WAF bypass).

### 3. DOM clobbering

Named in none of our six Playbooks. It is the technique that converts "I can
inject inert HTML" -- which is exactly the verdict `browser-script` returns -- into
code execution, and it works precisely where CSP blocks script: named `id`/`name`
attributes shadow JavaScript globals, `form` and nested-`id` structures build
multi-level property chains, and `HTMLCollection` entries are not writable, so a
library's own assignment to its escape function silently fails. Kevin Mizu's 2025
Beamer chain is the modern shape: clobber to disable an escaper, use a
node-removal gadget to erase the clobbering node, then let the now-unescaped value
reach an `iframe src`. Gareth Heyes's older work is still the primitive
reference and still lands. Payloads are inert markup, which fits our
"plant one element that changes what the document is, not what it does" posture
better than anything else on this list.
Belongs in: new playbook `browser-clobbering`, with `browser-script` step 5
handing off to it.
Must observe: which global names the page reads before defining (the source
inventory), the DOM after injection, and the resulting property value -- plus,
for impact, the network Receipt of any resource the clobbered value caused to load.
Sources: <https://portswigger.net/research/dom-clobbering-strikes-back> (2020-02-06, updated 2020-07-07, Gareth Heyes -- older, still the primitive reference);
<https://mizu.re/post/under-the-beamer> (2025-09-07, Kevin Mizu; clobbering + node-removal gadget defeats a DOMPurify-sanitised path in Beamer);
<https://portswigger.net/research/hijacking-service-workers-via-dom-clobbering> (2022-11-29, clobbering a CDN host into `importScripts()`);
<https://portswigger.net/burp/documentation/desktop/tools/dom-invader> (auto-detects DOM clobbering).

### 4. CSP as a graded artefact, and CSP bypass via allowlist, gadget and nonce

`browser-framing` reads exactly one CSP directive (`frame-ancestors`). Nothing in
the cluster reads `script-src`, `object-src`, `base-uri`, `style-src`, whether
`strict-dynamic` is set, whether the nonce changes per response, or which
allowlisted third-party hosts serve a JSONP endpoint or a script gadget. This is
the single cheapest addition here: it is one header read, it is directly
reportable on its own (a missing `object-src`/`base-uri` under an allowlist
policy is a finding on many programs), and it is the gate on every impact claim
`browser-script` currently declines to make. The 2025 exploitation shapes are all
about the allowlist, not the syntax: an allowlisted telemetry host used as an
exfiltration API, a leaked nonce replayed out of disk cache, an allowlisted
library that turns a DOM property into a script URL.
Belongs in: `browser-framing` (add a step) or new playbook `browser-policy`; the
verdict must be readable by `browser-script`.
Must observe: the whole `Content-Security-Policy` (and `-Report-Only`) header per
response, the nonce value across two responses to the same route, every host in
each directive, and whether the page loads a script from a host it allowlists.
Sources: <https://portswigger.net/research/hunting-nonce-based-csp-bypasses-with-dynamic-analysis> (2021-09-17, Gareth Heyes; input-element gadget that steals `querySelector` and controls a script URL -- older, still landing);
<https://jorianwoltjer.com/blog/p/research/nonce-csp-bypass-using-disk-cache> (Jorian Woltjer; CSS-leaks the nonce from a `<meta>` CSP, then forces bfcache to fall back to disk cache to replay it -- page did not print a date I could read, nominated in PortSwigger's 2025 list);
<https://lab.ctbb.show/writeups/bypassing-csp-new-relic-custom-events-cspt> (2025-10-31, Justin Gardner; allowlisted `bam.eu01.nr-data.net` used as an exfil sink, read back with NRQL, chained from a CSPT).

### 5. Prototype pollution: source detection, then gadget

`browser-messaging` explicitly declines to trigger pollution ("read out of the
source rather than triggered") on the grounds that a planted key persists for the
whole document. That is true and it is solvable: pollute as the *last* action of a
mission, because a fresh `navigate` gives a fresh realm. Without a source test we
cannot distinguish a library that merges query parameters into an options object
from one that does not, and the source test is a single read of an inherited
property. The gadget half is where the impact is, and the 2024-2026 record shows
gadgets are far more widespread than the classic `innerHTML`/`script.src` pair --
including gadgets that reach `document.cookie`, and including sanitiser
*downgrade*, where polluting a config key makes DOMPurify itself permissive.
Belongs in: new playbook `browser-prototype-pollution` (split out of
`browser-messaging`).
Must observe: whether `({}).<key>` is set after a navigation carrying
`?__proto__[key]=value` (and the `constructor.prototype` and JSON-body variants);
then which sink the polluted key reaches, evidenced by a DOM delta or a network
Receipt for a URL the tester did not name.
Sources: <https://portswigger.net/research/widespread-prototype-pollution-gadgets> (2022-06-22, updated 2022-10-28, Gareth Heyes; `fetch` body, `Object.defineProperty`, Google Analytics `hitCallback`, GTM `sequence`->eval, Adobe DTM `cspNonce`/`trackingServerSecure`);
<https://ieeexplore.ieee.org/document/11023488/> ("Follow My Flow: Unveiling Client-Side Prototype Pollution Gadgets from One Million Real-World Websites", IEEE -- I could not fetch the page, so venue and date are unconfirmed; search summary reports 133 zero-day gadgets and a `fbevents.js` gadget reaching `document.cookie`);
<https://www.usenix.org/conference/usenixsecurity24/presentation/cornelissen> ("GHunter: Universal Prototype Pollution Gadgets in JavaScript Runtimes", USENIX Security '24 -- page returned 403, cited from the USENIX listing);
<https://github.com/cure53/DOMPurify/wiki/Attack-Classes-&-Bypass-History> (CVE-2024-45801 and CVE-2026-41238: prototype pollution weakening DOMPurify's own config).

### 6. Sanitiser fingerprinting and mutation XSS

`browser-script` grades `escaped` as a refutation and calls it "the stronger
refutation". When a sanitiser sits in the path, `escaped` is where the work
*starts*. DOMPurify has had a continuous bypass stream through 2024-2026 --
nesting-based mXSS, template-literal reassembly under `SAFE_FOR_TEMPLATES`,
rawtext/RCDATA breakouts, prototype-pollution config downgrade, and an
engine-deferred mutation where Chrome re-clones a `<selectedcontent>` subtree
*after* sanitisation. Every one of those needs the same two facts: which sanitiser,
at which version, with which config. Those are recoverable from a running page.
Application-level sanitisers and post-sanitisation string edits (a very common
pattern) are the other half.
Belongs in: `browser-script` (rewrite step 4's `escaped` branch).
Must observe: the sanitiser's identity and version string, its live config
(`ALLOWED_TAGS`/`ALLOWED_ATTR`/hooks/`SAFE_FOR_TEMPLATES`), the string as it went
in, and the serialised DOM as the browser finally built it -- the *difference*
between those last two is the mXSS evidence.
Sources: <https://github.com/cure53/DOMPurify/wiki/Attack-Classes-&-Bypass-History> (bypass history incl. CVE-2024-45801, CVE-2024-47875, CVE-2025-26791, CVE-2026-0540, CVE-2026-41238 (3.0.1-3.3.3, fixed 3.4.0), CVE-2026-47423 (3.4.4, `<selectedcontent>`, fixed 3.4.5));
<https://github.com/advisories/GHSA-vhxf-7vqr-mrjg> (CVE-2025-26791, DOMPurify < 3.2.4);
<https://blog.criticalthinkingpodcast.io/p/hackernotes-ep-111-how-to-bypass-dompurify-with-k-vin-mizu> (2025-02-21, Kevin Mizu: namespace switching, `forceKeepAttr`, `uponSanitizeAttribute`, Unicode `.toUpperCase()` tricks, and the practical trick of breakpointing on `<!-->` in the bundle to dump the live config);
<https://portswigger.net/research/bypassing-dompurify-again-with-mutation-xss> (Michal Bentkowski; the canonical mXSS-vs-sanitiser writeup -- older, still the reference).

### 7. Sink context taxonomy: URL-scheme and function-construction sinks

Modern frameworks have genuinely fixed the HTML-text and non-URL-attribute
contexts. What they have not fixed is the URL-scheme context (`href`/`src`/
`formaction` taking `javascript:`, `data:`, `blob:`), the function-construction
context (`eval`, `new Function`, `setTimeout(string)`, template compilers), and
anything outside the framework's own render path. React only recently began
rejecting `javascript:` URLs; Vue has no native URL validation. Our probe answers
one question -- "did the parser build an `rk-probe` element" -- so a value that
lands in `href` is graded `escaped` or `absent`, i.e. a *refutation*, when it is
actually a live sink. This is a correctness bug in our reading, not just a gap.
Belongs in: `browser-script` (rewrite steps 4-5); the same taxonomy should gate
`browser-messaging`'s verdict.
Must observe: which of the five sink contexts the value landed in (HTML text,
attribute, URL attribute, JS-URL, function construction), and the attribute name
and node it landed on -- not merely whether an element exists.
Sources: <https://flatt.tech/research/posts/why-xss-persists-in-this-frameworks-era/> (2025-07-08, canalun / GMO Flatt Security; the five-sink taxonomy, plus HackerOne #1675516, #1379400, #2611305, #2279346 and CVE-2021-20323 as worked examples);
<https://lab.ctbb.show/research/CVE-2025-59840-unusual-xss-technique-toString-gadget-chains> (2025-12-01, Nick Copi / 7urb0; Vega 5.33.0, implicit `toString` coercion drives a gadget chain into `window.eval`).

### 8. CSS injection as a complete attack class

`<style>` is allowed by DOMPurify's defaults, needs no `script-src` grant, and in
2025-2026 is a full exfiltration primitive: attribute-selector brute force,
ligature-font width oracles, `@container` measurement, keylogging via select
elements, CSP-nonce theft, UI spoofing and click hotwiring. Fontleak reports
~1,000 characters per minute and a 2,400-character extraction. Our probe
vocabulary cannot express "the page accepted a stylesheet the caller supplied",
and `browser-script`'s reading would score a `<style>` payload as `escaped`
or `absent`.
Belongs in: new playbook `browser-css-injection` (or a second probe verdict in
`browser-script`).
Must observe: that a caller-supplied `<style>` or `style` attribute survived into
the document, and -- the decisive evidence -- the network Receipts for the
selector-triggered resource loads, which are our proof that the CSS *ran* rather
than merely parsed.
Sources: <https://portswigger.net/research/css-the-bomb-inside-your-inbox> (2026-08-06, Gareth Heyes; CSS gadgets, CSS mutation via CSSOM hex-escape reassembly, CSS hotwiring, font-height oracle; webmail clients and CSP-locked pages);
<https://adragos.ro/fontleak/> (2025-04-16, Dragos Albastroiu; OpenType GSUB ligatures + `@container`, Chrome/Firefox/Safari, defeats DOMPurify defaults because `style` is allowed);
<https://blog.arkark.dev/2025/09/08/asisctf-quals> (2025-09-08, CSS exfiltration with no network requests, via quirks-mode-relaxed MIME checks -- listed in PortSwigger's 2025 nominations; not fetched).

### 9. Cookie tossing, cookie prefix bypass, and cookie-forced self-XSS

A cookie set by a sibling subdomain is sent to the parent origin, and the parent
cannot tell where it came from. That turns "we have an XSS on a marketing
subdomain" into session fixation, OAuth flow hijack and forced self-XSS on the
main application. `__Host-` is the defence and it is rarely used; and in 2025 it
was shown to be bypassable through browser/server parsing discrepancies -- Unicode
whitespace before the prefix that Django/ASP.NET normalise away, and Java stacks
that fall back to legacy RFC 2109 parsing on `$Version=1`. Our `cookies` Playbook
reads scope; nothing asks whether a foreign-set cookie is *accepted and acted on*.
Belongs in: `cookies` (add a step) with `browser-storage` referencing it; not a
new Playbook.
Must observe: the browser's cookie jar per origin, which cookies the target
accepts on a route, whether `__Host-`/`__Secure-` prefixes are used and honoured,
and the server's behaviour when two cookies of the same name arrive.
Sources: <https://portswigger.net/research/cookie-chaos-how-to-bypass-host-and-secure-cookie-prefixes> (2025-09-03, Zakhar Fedotkin; Unicode whitespace prefix and `$Version=1` legacy parsing; Chrome/Firefox vs Safari differences, Django/ASP.NET/Tomcat/Jetty);
<https://labs.snyk.io/resources/hijacking-oauth-flows-via-cookie-tossing/> (2024-11-26, Elliot Ward; GitPod, CVE-2024-21583, fixed by adopting the `__Host-` prefix).

### 10. Clickjacking that survives the framing headers

`browser-framing` is built on the premise that framing headers decide the
question. Three 2025 results break that premise. DoubleClickjacking uses no frame
at all -- `window.open`, a decoy double-click, `window.opener.location` -- so
`X-Frame-Options`, `frame-ancestors` and `SameSite` are all bypassed by
construction. SVG-filter clickjacking applies filter pipelines to framed
cross-origin content to build AND/OR/NOT/XOR gates on pixel colour, giving
multi-step interactive attacks and data exfiltration. DOM-based extension
clickjacking hides the password manager's own injected autofill UI. Our reading
also cannot say the thing that decides a clickjacking report's severity: whether
there is a one-click state change worth stealing.
Belongs in: `browser-framing` (rewrite steps 4-5, add an impact step).
Must observe: for the header claim, what we already take; for the impact claim,
the set of one-click state-changing controls on the page and whether any
confirmation step intervenes. Framing the target from a second origin is out of
scope for this harness and should stay refused -- but DoubleClickjacking needs no
second origin's *frame*, only a second window, which changes the calculus.
Sources: <https://www.evil.blog/2024/12/doubleclickjacking-what.html> (2024-12, Paulos Yibelo; Salesforce and Slack named);
<https://lyra.horse/blog/2025/12/svg-clickjacking/> (2025-12-04, Lyra Rebane; the post states X-Frame-Options and `frame-ancestors` do not prevent the SVG filter attack; Firefox and Chromium, Safari inconsistent);
<https://marektoth.com/blog/dom-based-extension-clickjacking/> (2025-08-09, updated 2026-01-14, Marek Toth, DEF CON 33; all 11 password managers tested vulnerable in default config, ~40M installs; 1Password and LastPass listed unfixed at time of writing).

### 11. Service workers and the Cache API

A service worker is the most durable client-side foothold there is: registration
survives sessions, the Cache API lets an attacker rewrite the cached copy of any
same-origin page, and `Service-Worker-Allowed` can widen scope. It is also a sink
in its own right -- a controllable `importScripts()` URL. None of the six
Playbooks mentions workers. On a real program the reportable, non-destructive
version of this is: does the origin register a service worker, what scope, is any
part of its registration URL caller-controlled, and does the site permit
registration from a path an attacker could reach.
Belongs in: new playbook `browser-worker`.
Must observe: the registered service worker's script URL and scope, the
`Service-Worker-Allowed` header, whether a caller-controlled value reaches the
registration or `importScripts` URL, and the Cache API key list.
Sources: <http://swcacheattack.secpriv.wien/> (Squarcina, Calzavara, Maffei; "The Remote on the Local: Exacerbating Web Attacks Via Service Workers Caches", WOOT'21, May 2021 -- older, and still the clearest statement of why an XSS anywhere on the origin is a persistent compromise);
<https://portswigger.net/research/hijacking-service-workers-via-dom-clobbering> (2022-11-29, Gareth Heyes; query-parameter and DOM-clobbered `importScripts` host).

### 12. Self-XSS escalation

Programs routinely close self-XSS as won't-fix. Slonser's 2025 work makes that
triage wrong: a credentialless iframe loads without the victim's credentials but
remains same-origin with a regular iframe on the same page, so a login-CSRF into
the *attacker's* account inside the credentialless frame executes the stored
self-XSS payload with reach into the victim's authenticated frame. Variants cover
CAPTCHA (relay via WebSocket) and `X-Frame-Options` (`fetchLater`). This changes
how our harness should grade a stored value that only the owner renders.
Belongs in: `browser-script` (step 5's "what was not shown" needs a clause) and
whichever Playbook covers login CSRF.
Must observe: whether login CSRF is possible on the target, and whether the
stored self-XSS value renders in a page that can be framed. The escalation itself
needs a second origin and stays out of scope; the *precondition pair* is
observable and is what makes the report worth filing.
Sources: <https://blog.slonser.info/posts/make-self-xss-great-again/> (2025-06-13, Slonser; credentialless iframes + login CSRF, `fetchLater` variant, requires spring-2025-era browser support).

### 13. WebSocket beyond the handshake

`browser-realtime` stops at the upgrade response and says so honestly; `realtime`
covers the origin check. What neither can do is read a frame, which means we
cannot prove that a hijacked or cross-authorised socket actually carries data --
and "the handshake was accepted" is a much weaker report than "here is the other
tenant's message". The 2025 exploitation writing focuses on GraphQL-over-WebSocket,
where the subscription transport sidesteps the preflight that protects the HTTP
API. This is an infrastructure gap (our proxy does not carry the upgrade), not
just a Playbook gap, and it should be recorded as such.
Belongs in: `browser-realtime` (step 4 should name the infrastructure limit as a
tracked gap, not a design choice) plus a proxy capability ticket.
Must observe: frames sent and received on the socket, with a Receipt per frame.
Nothing in the harness captures this today.
Sources: <https://blog.includesecurity.com/2025/04/cross-site-websocket-hijacking-exploitation-in-2025/> (2025-04, Include Security -- the site returned HTTP 403 to our fetch, so this is cited from PortSwigger's 2025 nomination listing, which describes it as CSWSH via GraphQL bypassing preflight CSRF protections).

### 14. XS-Leaks / cross-site side channels

Two of the ten techniques in PortSwigger's 2025 list are XS-Leaks, which is the
clearest signal available that side channels became a mainstream exploitation
primitive rather than a CTF genre. Salvatore Abello uses Chrome's connection-pool
prioritisation as an oracle for cross-domain redirect hostnames; Takeshi Kaneko
chains ETag length variation into a 431 and reads the result off
`history.length`. Both need an attacker origin, so they sit outside our current
posture -- but the *defensive* half is observable from one origin and is
reportable: does the target set `Cross-Origin-Opener-Policy`,
`Cross-Origin-Resource-Policy`, and does it honour Fetch Metadata
(`Sec-Fetch-Site`/`Sec-Fetch-Dest`).
Belongs in: `browser-framing` as an added header read now; a full
`browser-xsleak` Playbook only if the Program's scope ever grants a second origin.
Must observe: `COOP`, `COEP`, `CORP`, `Vary`, and whether the route's response
differs by `Sec-Fetch-Site`.
Sources: <https://portswigger.net/research/top-10-web-hacking-techniques-of-2025> (2026-02-05, updated 2026-02-06; ranks 8 and 6);
<https://blog.arkark.dev/2025/12/26/etag-length-leak> (2025-12-26, Takeshi Kaneko / arkark; ETag hex-boundary length change -> oversized `If-None-Match` -> Node.js 431 -> `history.length` oracle, Chromium);
<https://blog.babelo.xyz/posts/cross-site-subdomain-leak/> (Salvatore Abello -- 403 to our fetch; described in the PortSwigger entry above);
<https://xsleaks.dev/> (the XS-Leaks wiki; category and defence taxonomy, last modified 2024-12-17).

### 15. Third-party widget and browser-extension permission surface

Where a Program's scope includes an embedded third-party widget or a browser
extension, the delegated-permission path is high-yield and almost never tested: a
chat widget embedded in thousands of sites inherits the host page's granted
camera/microphone/display-capture permissions, so one XSS in the widget vendor
scales across every embedding site. Our `external-resources` Playbook lists
foreign origins with executable authority, which is the right neighbour, but it
does not read the `allow` attribute on the iframes that delegate permissions.
Belongs in: `external-resources` (add a step reading iframe `allow`/`sandbox`),
not a new Playbook.
Must observe: every `<iframe>`'s `src`, `allow` and `sandbox` attributes, and the
Permissions-Policy header of the top document.
Sources: <https://albertofdr.github.io/post/permission-hijacking-2025/> (2025-07-21, Alberto Fernandez de Retana; LiveChat one-click XSS via `markdown-to-jsx` `formaction`, Glassix CSP bypass via local-scheme iframe document);
<https://marektoth.com/blog/dom-based-extension-clickjacking/> (2025-08-09; the extension-side mirror of the same problem).

### 16. Holding a redirect open to steal an OAuth code

A small, very transferable client-side primitive: if you can stop or delay the
navigation that consumes an OAuth callback, the `code` stays in a URL you can
still read. Methods include `data:`/`about:` protocol quirks, URL-length overflow
that makes the server error instead of redirect, exhausting Chrome/Firefox's
200-navigations-per-10-seconds limit, `sandbox` without `allow-forms`, and
tripping a WAF so an error page renders instead of the redirect. It converts
several "unexploitable" OAuth findings into account takeover.
Belongs in: the `oauth` Playbook, with `browser-evidence` supplying the mission.
Must observe: the full navigation chain with per-hop Receipts, and the URL of the
document that is loaded when the chain halts.
Sources: <https://lab.ctbb.show/research/stopping-redirects> (2025-12-04, Jorian Woltjer).

## What in our playbooks looks stale or weak

* **`browser-script`'s three-word verdict is too coarse to be correct.**
  `reflected`/`escaped`/`absent` collapses five sink contexts into one bit. A
  value in `href="javascript:..."` grades `absent`; a value that a sanitiser
  neutralised and a value that a sanitiser *mutated* both grade `escaped`. Worse,
  `escaped` is graded as a *refutation*, so the harness will close exactly the
  cases where mXSS work begins.
* **`browser-script` has no path to an impact claim, ever.** Step 5 declines
  execution, CSP and session-readability. All three are refusals of things we
  never built the instruments for, and the result is that our best XSS finding is
  "caller bytes became an element", which many programs triage as informational.
  A safe execution oracle exists and we do not use it: an inert element whose
  *attribute* causes a resource fetch produces a Receipt at our own proxy. No
  script runs, and the Receipt proves the browser acted on attacker-built markup.
* **`browser-messaging` refuses its two most productive sources.** Fragments are
  refused on a Receipt-fidelity argument -- but a fragment is part of the plan and
  can be recorded in the plan digest even though it never crosses the network;
  the Receipt simply does not carry it, which is a documentation problem, not an
  evidence problem. `postMessage` is refused on a second-origin argument that does
  not hold for same-origin senders.
* **`browser-messaging`'s trigger is too narrow.** `embedded_document` means the
  Playbook only fires on documents something frames. Most DOM XSS is on ordinary
  top-level pages reading `location.hash` or `localStorage`.
* **`browser-messaging` folds prototype pollution into a markup question.** Its
  `bb:references` names `prototype-pollution.md`, its prose declines to trigger
  pollution, and its only verdict is about `rk-probe` in the DOM. Pollution whose
  gadget reaches `document.cookie` or `fetch` is invisible to that reading.
* **`browser-framing` does two unrelated things.** Framing policy and CORS
  credentialed reflection are one Playbook because they are both response headers.
  They have different triggers, different impact and different neighbours. It also
  reads only one CSP directive while sitting on the whole header.
* **`browser-framing`'s model is now falsified.** "What the target tells the
  browser" no longer decides the framing question -- DoubleClickjacking and
  extension clickjacking both work against a page with perfect headers.
* **`browser-storage` names its own blind spot and stops there.** "This harness
  has no action that reads Web Storage" is honest, but the `cookies` Playbook
  reads "the browser's own jar", so the browser tier evidently can read *some*
  client state. The asymmetry looks accidental. `localStorage`,
  `sessionStorage` and IndexedDB are where SPAs put tokens.
* **`client-side-path-traversal` is capped at the weakest half of the class.**
  `read_method` trigger, `GET`-only sink, no stored or fragment sources, no
  canary, and an explicit statement that a moved request answering `404` is still
  the finding. CSPT2CSRF -- the reason the class is paid -- is out of reach.
* **`browser-realtime` presents an infrastructure limit as a methodological
  virtue.** "The connection does not continue past the door" is a proxy that does
  not do WebSocket. It should be a tracked gap.
* **Nothing in the cluster reads a policy the browser now enforces by default.**
  No `COOP`/`COEP`/`CORP`, no Permissions-Policy, no Fetch Metadata, no Trusted
  Types, no `sandbox` attribute. Some of these change what an exploit can do:
  Chrome made `document.domain` immutable in Chrome 115 (2023-05-30 announcement),
  so same-site sibling escalation now needs an `Origin-Agent-Cluster: ?0` opt-out,
  which is itself an observable and reportable fact.
* **All six carry `bb:status: draft` and `bb:stale_after: 2027-03-15`.** Fine, but
  the CSPT and sanitiser material dates faster than that; those two should carry a
  shorter horizon.

## Concrete change proposals per playbook

* **`browser-script/playbook.md`** -- rewrite step 4 to report a *sink context*
  (HTML text, attribute, URL attribute, JS-URL, function construction) alongside
  the verdict, and to split `escaped` into `encoded` (refutation) and `sanitised`
  (which routes to a sanitiser-identification step); add a new step between the
  current 4 and 5 that records the CSP as served, the sanitiser name/version/config
  if one is present, and an inert *attribute-driven fetch* probe whose Receipt is
  the execution-adjacent evidence step 5 currently declines to seek.
* **`browser-framing/playbook.md`** -- split the CORS half out, then rewrite step 4
  so that the header reading is the *first* of two claims and add a new step that
  inventories one-click state-changing controls and records whether any
  confirmation intervenes, so the finding carries impact; extend step 1's header
  list to the full `Content-Security-Policy`, `Permissions-Policy`,
  `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` and
  `Origin-Agent-Cluster`, and add the DoubleClickjacking case to step 5 as a claim
  the header evidence explicitly does not refute.
* **`browser-messaging/playbook.md`** -- rewrite step 3 to stop refusing
  `postMessage` and fragments: add a listener-inventory action (enumerate `message`
  listeners, their handler source and their origin checks) and a same-origin
  message send, and record the fragment in the plan digest with a note that no
  Receipt carries it rather than refusing `navigate`; broaden `bb:triggers_all`
  off `embedded_document`; move the prototype-pollution material out to its own
  Playbook rather than leaving a class it declines to test in
  `bb:references`.
* **`browser-storage/playbook.md`** -- rewrite step 4 from "this harness has no
  action that reads Web Storage" into a step that *does* read it: add a storage
  read to the mission action set (`localStorage`, `sessionStorage`, IndexedDB
  database names) and make the claim "the credential is in a store any script on
  this origin can read", which is the claim a report needs; add a cross-reference
  step to `cookies` for the tossing/prefix question.
* **`browser-realtime/playbook.md`** -- rewrite step 4 so the sentence "no
  application frame is sent" is labelled an instrument limitation with a tracked
  gap, not a scope decision, and add a step that records what the handshake
  response says about subprotocol and transport (GraphQL-over-WebSocket in
  particular) so a later frame-capable run has a starting point.
* **`client-side-path-traversal/playbook.md`** -- rewrite step 1 and the
  `bb:triggers_all` to admit non-`GET` sinks and non-path sources (fragment,
  query, stored), and add a step after the current step 3 that records the *method,
  headers and body* of the moved request together with whether the application's
  CSRF token or `Authorization` header rode along -- that pairing is the
  CSPT2CSRF claim; add a canary-segment confirmation to step 2 so a DOM-based or
  stored CSPT can be found at all.

New Playbooks worth opening, in the order I would open them:
`browser-clobbering`, `browser-prototype-pollution`, `browser-policy` (CSP as its
own graded artefact), `browser-css-injection`, `browser-worker`. Cookie tossing
belongs in the existing `cookies` Playbook and iframe permission delegation in the
existing `external-resources` Playbook; neither needs a new file.

## What the browser evidence Skill would have to capture

The Skill today gives ten actions (`navigate`, `wait_for`, `fill`, `inject`,
`click`, `assert_text`, `assert_absent`, `probe`, `capture_dom`, `screenshot`),
five evidence channels (DOM snapshot, screenshot, assertion outcome, probe JSON,
whole-mission console log) and one Receipt per request. It has no scripted
evaluation, no storage read, no listener enumeration, no per-response header
artefact, no fragment navigation, no second origin and no WebSocket.

| Technique | What must be captured for the finding to be provable | Captured today? |
|---|---|---|
| postMessage | inventory of `message` listeners + handler source; the message sent (step-attributed); DOM delta after it; `targetOrigin` of every outbound send | **No.** Needs a listener-enumeration probe and a `send_message` action. `capture_dom` gives the delta only. |
| CSPT2CSRF | method + path + headers + body of every page-originated request, before and after, plus the response | **Partial.** Receipts carry requests, but the Playbook only differences the request *line*; the Skill must expose method/headers/body per Receipt and a canary echo. |
| DOM clobbering | globals the page reads before defining; DOM after injecting `id`/`name` markup; the resulting property value; Receipt of any resource the clobbered value loaded | **Partial.** DOM and Receipts yes; the "global read before define" inventory and the property read need a new probe. |
| CSP / nonce / allowlist | the full CSP header per response; the nonce across two responses to the same route; hosts per directive | **No.** Response headers are not a Skill artefact; the Skill has no header capture at all. Receipts may hold them -- if so, say so explicitly and cite them. |
| Prototype pollution | inherited-property read after a polluting navigation; then the sink evidence (DOM delta or a Receipt for a URL the plan never named) | **No.** Needs a `probe prototype_pollution` returning the inherited value. Run it as the last step of a mission so the polluted realm dies with the navigation. |
| Sanitiser / mXSS | sanitiser name + version + live config; the input string; the serialised DOM the browser finally built; the diff between the last two | **Partial.** `capture_dom` gives the output; identity/version/config need a probe or a bundle-analysis Skill run. |
| Sink context taxonomy | which context the value landed in, the attribute name and the node -- not just "an element exists" | **No.** The probe's three-word vocabulary cannot express it; needs an extended verdict schema. |
| CSS injection | that a caller-supplied `<style>`/`style` survived into the DOM, plus **the Receipts for the selector-triggered resource loads** | **Partial.** DOM yes; the Receipts already exist and are the right evidence -- what is missing is a Playbook that reads them for this purpose. |
| Cookie tossing / prefixes | per-origin cookie jar; which cookie the target accepted; prefix presence; duplicate-name behaviour | **Partial.** The `cookies` Playbook implies a jar read exists; it is not documented in the Skill's action list, which is itself a defect. |
| Clickjacking (impact half) | the inventory of one-click state-changing controls and whether a confirmation intervenes; a screenshot of each | **Partial.** `screenshot` and `capture_dom` give the raw material; nothing enumerates actionable controls. Framing from a second origin stays refused. |
| Service worker / Cache API | registered SW script URL and scope, `Service-Worker-Allowed`, whether a caller value reaches the registration or `importScripts` URL, Cache API keys | **No.** Needs a worker/cache probe; the SW's own fetches must also be reconciled against Receipts. |
| Self-XSS escalation | that login CSRF is possible and that the self-XSS-rendering page is framable | **Partial.** Both are header/form observations another Playbook can take; nothing joins them. |
| WebSocket frames | one Receipt per frame sent and received | **No.** Proxy-level gap, not a Skill gap. Record as a tracked limitation. |
| XS-Leaks (defensive half) | `COOP`, `COEP`, `CORP`, `Vary`, and response variation by `Sec-Fetch-Site` | **No.** Same missing header-artefact problem as CSP. |
| Widget permission delegation | every iframe's `src`, `allow`, `sandbox`; the top document's `Permissions-Policy` | **Partial.** `capture_dom` holds the iframe attributes; the header does not. |
| Stopping redirects | the full navigation chain with a Receipt per hop and the URL of the document loaded when the chain halts | **Partial.** Receipts cover the hops; `navigate`'s outcome keys report `document_loaded`/`http_status` but not the final URL after a redirect chain. |

Three cross-cutting additions would unlock most of the table at once:

1. **A response-header artefact per Receipt**, or an explicit statement in the
   Skill that Receipts carry headers and how to cite them. CSP, COOP/CORP,
   Permissions-Policy, `Service-Worker-Allowed` and cookie prefixes all die on
   this one gap.
2. **An extended probe verdict schema** -- a probe should be able to return a
   structured record (sink context, node, attribute, sanitiser identity, property
   value) rather than one of three words. The registry-owned-payload discipline
   is preserved; only the return type widens.
3. **A `read_client_state` action** covering `localStorage`, `sessionStorage`,
   IndexedDB names, the cookie jar, registered service workers and registered
   `message` listeners. All are reads. None plant anything. Between them they
   close `browser-storage`'s stated blind spot, half of `browser-messaging`, and
   all of the worker Playbook.

## Sources consulted

* <https://portswigger.net/research/top-10-web-hacking-techniques-of-2025> (2026-02-05, updated 2026-02-06) -- the ranked 2025 list; supplied the two XS-Leak entries (ranks 8 and 6) and their authors.
* <https://portswigger.net/research/top-10-web-hacking-techniques-of-2025-nominations-open> -- the full nomination pool; the single richest index of 2025 client-side research and the source of most URLs below.
* <https://blog.doyensec.com/2024/07/02/cspt2csrf.html> (2024-07-02, Maxence Schmitt) -- CSPT2CSRF source/sink model, why SameSite and CSRF tokens do not help, Mattermost and Rocket.Chat.
* <https://blog.doyensec.com/2025/03/27/cspt-resources.html> (2025-03-27) -- CSPT tool and escalation index (CSPT->JSONP->XSS, CSPT->open redirect->XSS).
* <https://github.com/doyensec/CSPTBurpExtension> -- passive source/sink detection plus canary-token confirmation; explicitly cannot find DOM-based or stored CSPT without the canary.
* <https://swisskyrepo.github.io/PayloadsAllTheThings/Client%20Side%20Path%20Traversal/> -- CSPT sink taxonomy and encoding-level WAF bypass.
* <https://portswigger.net/research/dom-clobbering-strikes-back> (2020-02-06, updated 2020-07-07, Gareth Heyes) -- the clobbering primitive reference: form/child chains, duplicate-id collections, anchor credentials, iframe `contentWindow`.
* <https://mizu.re/post/under-the-beamer> (2025-09-07, Kevin Mizu) -- modern clobbering + node-removal gadget chain defeating a sanitised path in Beamer.
* <https://portswigger.net/research/hijacking-service-workers-via-dom-clobbering> (2022-11-29, Gareth Heyes) -- clobbering a CDN host into `importScripts()`.
* <https://portswigger.net/research/widespread-prototype-pollution-gadgets> (2022-06-22, updated 2022-10-28, Gareth Heyes) -- the canonical client-side gadget list and the source/gadget split.
* <https://ieeexplore.ieee.org/document/11023488/> -- "Follow My Flow: ... Client-Side Prototype Pollution Gadgets from One Million Real-World Websites"; **not fetched** (empty response), cited for its existence only.
* <https://www.usenix.org/conference/usenixsecurity24/presentation/cornelissen> -- "GHunter: Universal Prototype Pollution Gadgets in JavaScript Runtimes", USENIX Security '24; **not fetched** (HTTP 403), cited from the USENIX listing.
* <https://github.com/cure53/DOMPurify/wiki/Attack-Classes-&-Bypass-History> -- DOMPurify's own bypass history; supplied CVE-2024-45801, CVE-2024-47875, CVE-2025-26791, CVE-2026-0540, CVE-2026-41238, CVE-2026-47423 and their attack classes.
* <https://github.com/advisories/GHSA-vhxf-7vqr-mrjg> -- CVE-2025-26791, DOMPurify < 3.2.4, `SAFE_FOR_TEMPLATES` mXSS.
* <https://blog.criticalthinkingpodcast.io/p/hackernotes-ep-111-how-to-bypass-dompurify-with-k-vin-mizu> (2025-02-21, Kevin Mizu) -- practical DOMPurify bypass methodology and the config-extraction technique a running-browser harness could reuse.
* <https://portswigger.net/research/bypassing-dompurify-again-with-mutation-xss> (Michal Bentkowski) -- the reference mXSS-versus-sanitiser writeup; older, still the model.
* <https://flatt.tech/research/posts/why-xss-persists-in-this-frameworks-era/> (2025-07-08, canalun, GMO Flatt Security) -- the five-sink taxonomy and why React/Vue only close two of them; several disclosed HackerOne reports as worked examples.
* <https://lab.ctbb.show/research/CVE-2025-59840-unusual-xss-technique-toString-gadget-chains> (2025-12-01, Nick Copi) -- Vega 5.33.0 implicit-`toString` gadget chain into `window.eval`.
* <https://portswigger.net/research/hunting-nonce-based-csp-bypasses-with-dynamic-analysis> (2021-09-17, Gareth Heyes) -- nonce-CSP script gadgets; older, still landing.
* <https://jorianwoltjer.com/blog/p/research/nonce-csp-bypass-using-disk-cache> (Jorian Woltjer; page date not readable, nominated in the 2025 list) -- CSS-leaked nonce replayed out of disk cache after forcing bfcache to fall back.
* <https://lab.ctbb.show/writeups/bypassing-csp-new-relic-custom-events-cspt> (2025-10-31, Justin Gardner) -- CSP allowlist turned into an exfiltration API, chained from a CSPT.
* <https://portswigger.net/research/css-the-bomb-inside-your-inbox> (2026-08-06, Gareth Heyes) -- CSS gadgets, CSS mutation, CSS hotwiring, font-height oracle; the current state of the art for JS-free client-side attack.
* <https://adragos.ro/fontleak/> (2025-04-16, Dragos Albastroiu) -- ligature-font plus `@container` text exfiltration; defeats DOMPurify defaults because `style` is allowed.
* <https://blog.arkark.dev/2025/09/08/asisctf-quals> (2025-09-08) -- CSS exfiltration with no network requests; listed in the 2025 nominations, **not fetched**.
* <https://portswigger.net/research/cookie-chaos-how-to-bypass-host-and-secure-cookie-prefixes> (2025-09-03, Zakhar Fedotkin) -- Unicode-whitespace and `$Version=1` bypasses of `__Host-`/`__Secure-`.
* <https://labs.snyk.io/resources/hijacking-oauth-flows-via-cookie-tossing/> (2024-11-26, Elliot Ward) -- cookie tossing into an OAuth flow; GitPod, CVE-2024-21583.
* <https://www.evil.blog/2024/12/doubleclickjacking-what.html> (2024-12, Paulos Yibelo) -- frameless clickjacking via `window.opener.location` and a double-click; defeats XFO, `frame-ancestors` and SameSite by construction.
* <https://lyra.horse/blog/2025/12/svg-clickjacking/> (2025-12-04, Lyra Rebane) -- SVG filter pipelines as logic gates over framed cross-origin content.
* <https://marektoth.com/blog/dom-based-extension-clickjacking/> (2025-08-09, updated 2026-01-14, Marek Toth, DEF CON 33) -- password-manager autofill UI hidden in the DOM; 11 extensions tested, ~40M installs.
* <http://swcacheattack.secpriv.wien/> (Squarcina, Calzavara, Maffei; WOOT'21, May 2021) -- service worker Cache API poisoning as persistent same-origin compromise; older, still the clearest statement.
* <https://blog.slonser.info/posts/make-self-xss-great-again/> (2025-06-13, Slonser) -- credentialless iframes plus login CSRF turn self-XSS into a real finding.
* <https://blog.includesecurity.com/2025/04/cross-site-websocket-hijacking-exploitation-in-2025/> (2025-04) -- CSWSH in 2025; **not fetched** (HTTP 403), described via the PortSwigger nomination entry.
* <https://blog.arkark.dev/2025/12/26/etag-length-leak> (2025-12-26, Takeshi Kaneko) -- ETag length -> 431 -> `history.length` XS-Leak oracle on Chromium.
* <https://blog.babelo.xyz/posts/cross-site-subdomain-leak/> (Salvatore Abello) -- connection-pool prioritisation as a cross-origin redirect oracle; **not fetched** (HTTP 403), described via the PortSwigger entry.
* <https://xsleaks.dev/> (wiki, last modified 2024-12-17) -- XS-Leak attack and defence taxonomy.
* <https://albertofdr.github.io/post/permission-hijacking-2025/> (2025-07-21, Alberto Fernandez de Retana) -- delegated browser permissions hijacked at scale through embedded support widgets.
* <https://lab.ctbb.show/research/stopping-redirects> (2025-12-04, Jorian Woltjer) -- five ways to hold a redirect open so an OAuth code stays readable.
* <https://www.yeswehack.com/learn-bug-bounty/introduction-postmessage-vulnerabilities> (2021-08-25) -- postMessage vulnerability classes and listener-enumeration tooling; older, and the class still pays.
* <https://portswigger.net/burp/documentation/desktop/tools/dom-invader> -- the capability baseline a browser-driving harness is measured against: DOM XSS sinks with context and sanitisation, web-message logging/replay, prototype pollution sources and gadgets, DOM clobbering.
* <https://developer.chrome.com/blog/document-domain-setter-deprecation> (2023-05-30) -- `document.domain` immutable from Chrome 115; `Origin-Agent-Cluster: ?0` is the opt-out and therefore an observable.
* <https://developer.mozilla.org/en-US/docs/Web/API/HTML_Sanitizer_API> -- Sanitizer API / `setHTML()`; MDN currently marks it "Limited availability ... not Baseline", so a target relying on it is not yet the common case. (Secondary blog sources claiming a specific Chrome/Firefox shipping version were not corroborated by MDN and are therefore not relied on here.)
