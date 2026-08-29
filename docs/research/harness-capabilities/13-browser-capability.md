# 13 - The browser lane

Written against this worktree at the commit this file was added. Every claim
about our own code carries `file:line` and was read there; where a fact could
not be found in the tree it says "not found". Every external claim carries a URL
that was fetched, and where a page would not fetch it says so.

Framing throughout is authorized testing of a Program's own scope. Nothing here
proposes a primitive whose only use is against a target nobody authorized.

Shorthand: **the browser migration** is
`src/redkraken/migrations/20260814T040000Z__a_browser_mission_runs_behind_the_door.sql`.

## What our browser lane can do today

One command drives it: `rk browser run` (`src/redkraken/cli.py:1135-1201`,
handler `cli.py:2629`, orchestration `src/redkraken/browser.py:129-303`). It
opens a Tool run under the name `mcp__rk2__browse` (browser migration:731-732),
mints one egress capability through the same gate every request uses
(`browser.py:224-240, 347-351`), starts a container holding a headless Chromium
(`browser.py:354-405`), walks the plan, files what came back, and closes the run
in one transaction (`browser.py:254-283`).

**The action set is closed by the database, not by the driver.** Ten rows in
`browser_actions` (browser migration:186-207), their arguments in
`browser_action_arguments` (browser migration:229-252), their argument
*vocabulary* in `browser_argument_kinds` (browser migration:103-124). A step
naming an eleventh action is refused before a container starts, and the driver
would refuse it again (`src/redkraken/browser_driver.py:668-670`).

| Action | Driver | Registry row | Outcome keys (the only thing the digest sees) | Stored evidence |
| --- | --- | --- | --- | --- |
| `navigate` | `browser_driver.py:502-529` | migration:187-188 | `http_status`, `document_loaded`, plus `scope_class` | none of its own. `scope_class` is *not* the container's to report; the host reads it off the Receipt the door wrote (`browser.py:466-480`) and writes `unrecorded` when no Receipt names the destination (`browser.py:121`) |
| `wait_for` | `browser_driver.py:531-541` | migration:189-190 | `matched` | none |
| `fill` | `browser_driver.py:543-563` | migration:191-192 | `matched` | none |
| `inject` | `browser_driver.py:565-568` | migration:193-195 | `matched` | none. The typed string is the probe's own `payload`, never the plan's (browser migration:285-306) |
| `click` | `browser_driver.py:570-592` | migration:196-197 | `matched` | none. The one action flagged `submits`, and therefore the only way a mission's capability acquires POST (browser migration:779, 948-949) |
| `assert_text` | `browser_driver.py:594-595` | migration:198-199 | `matched` | none - the assertion lives inside the result digest and nowhere else |
| `assert_absent` | `browser_driver.py:597-598` | migration:200-201 | `matched` | none |
| `probe` | `browser_driver.py:609-646` | migration:202-203 | `verdict`, checked against the probe's own declared set | the probe's whole JSON return, as `probe-{ordinal}.json` (`browser.py:112`) |
| `capture_dom` | `browser_driver.py:648-653` | migration:204-205 | `captured` | `document.documentElement.outerHTML` as `dom-{ordinal}.html` (`browser.py:110`) |
| `screenshot` | `browser_driver.py:655-661` | migration:206-207 | `captured` | a viewport PNG as `screenshot-{ordinal}.png` (`browser.py:111`) |

Three things come back that are not an action:

* **The console**, always, whether or not the mission finished:
  `Runtime.consoleAPICalled` and `Log.entryAdded` flattened one JSON object per
  line into `console.jsonl` (`browser_driver.py:699-729`, `browser.py:104`).
* **A per-step request count**, from `Network.requestWillBeSent` and
  `Network.webSocketWillSendHandshakeRequest` (`browser_driver.py:99-105,
  671-684`), recorded with the step (`browser.py:79, 445-463`) and reconciled
  against the door's Receipts by `check_browser_runs`, which faults when counted
  requests exceed Receipts (browser migration:1362-1370).
* **A Receipt per request**, written by the door and not by the browser
  (`src/redkraken/proxy.py:1-35`), because every byte the page fetches crosses
  the loopback shim (`browser_driver.py:148-281`) to the door.

What bounds it: `browser_ceilings`, one row, changed only by migration -
180s per mission, 10s per step, 32 steps, 1024MB, 2 CPU, 8MiB per artifact,
1280x800 viewport (browser migration:386-387), carried into the container as
`isolation.Ceilings` (`browser.py:389-397`).

What is *deliberately* narrow, and each of these is a wall a client-side reading
walks into:

1. **Outcome values are a three-word vocabulary.** A boolean, an integer below
   100000, or a lowercase word of at most 32 characters -
   `rk2_browser_outcome_word` (browser migration:710-719). A URL, an attribute
   name, a version string or a hash cannot be written in it, and a value outside
   it is a `check_browser_runs` fault (browser migration:1405-1412). This is the
   reason a richer *verdict* cannot simply be returned in an outcome today.
2. **`navigate` takes no fragment.** The `url` kind refuses one by pattern, with
   the reason stated on the row: a fragment never leaves the browser, so a
   Receipt could not match it (browser migration:104-110). Every fragment-source
   DOM XSS reading dies here.
3. **JavaScript only ever comes from `browser_probes`.** A plan names a probe;
   the row holds the source, and `Runtime.evaluate` is called on that text and
   nothing else (`browser_driver.py:609-621`, browser migration:271-306). One
   probe is registered: `markup_injection`, which plants
   `<rk-probe id="rk-probe-marker"></rk-probe>` and answers
   `reflected` / `escaped` / `absent` (browser migration:315-336). Every value a
   plan supplies crosses into the page as a `Runtime.callFunctionOn` argument,
   never as spliced text (`browser_driver.py:458-482`).
4. **A probe may not read stored client state.** `check_browser_runs` faults any
   probe whose source matches `document.cookie`, `localStorage`,
   `sessionStorage` or `indexedDB` (browser migration:1382-1389).
5. **Four CDP domains are enabled**: `Page`, `Runtime`, `Network`, `Log`
   (`browser_driver.py:794-802`). Not `Storage`, not `DOMStorage`, not
   `DOMDebugger`, not `ServiceWorker`, not `CacheStorage`, not `DOM`.
6. **No agent can start any of this.** There is no `Contract` for a browser in
   `src/redkraken/roster.py:592-850` - searched, **not found**; the only name
   `mcp__rk2__browse` appears under in the tree is the migration that mints it
   (browser migration:732). `run_tool`'s enum is four offline binaries
   (`roster.py:784`), while `browser-evidence/SKILL.md:63` instructs the hunter
   to "Start the mission through `mcp__rk2__run_tool`". Doc 10 recorded this
   already (`docs/research/harness-capabilities/10-agent-tooling-state-of-the-art.md:336-343`);
   it is restated here because every proposal below is worth nothing until it is
   fixed.

What the Skill tells an agent to capture is consistent with the above and adds
discipline rather than capability: write the plan first
(`skills/browser-evidence/SKILL.md:14-27`), put a `wait_for` after everything
that changes the page (`SKILL.md:29-59`), run it once behind the door
(`SKILL.md:61-71`), treat all five returned channels as the target's words
(`SKILL.md:73-99`), cite the run and not the rendering (`SKILL.md:109-117`), run
the plan twice before a difference is a finding (`SKILL.md:119-130`), and stop
on a mission that did not close (`SKILL.md:132-137`).

One capability the record already has and the Skill never mentions: **the
door stores both directions of every allowed exchange as an Artifact** - a whole
HTTP message, headers included, content type `message/http`
(`proxy.py:317, 789-798`), named on the Receipt as `request_agent_sha` /
`response_agent_sha` (`proxy.py:3054-3062`) and exposed to an agent as packet
fields (`migrations/20260815T180000Z__a_blind_validator_answers_from_the_packet.sql:186-187`,
reader at `src/redkraken/packet.py:873-910`). Response *headers* are therefore
already on the record for every request a browser mission makes. Two limits:
`Set-Cookie`, `WWW-Authenticate`, `Authentication-Info` and their proxy
equivalents are wire-only and are dropped from the agent view
(`proxy.py:340-357, 659-698`), and the query string is stored only as a digest
(`proxy.py:743`, Receipt field `query_sha256`).

## What a client-side finding needs

Per bug class, the minimum the browser must observe or do. The "must observe"
column is taken from `docs/research/playbook-state-of-the-art/06-client-side-browser.md`
and not re-derived; line references point at where that file states it.

| Class | Minimum the browser must observe or do (06-client-side-browser.md) | Our lane |
| --- | --- | --- |
| **DOM XSS / sink context** (`:178-196`, table row `:482`) | which of the five contexts the value landed in - HTML text, attribute, URL attribute, JS-URL, function construction - plus the attribute name and node | `markup_injection` answers one question: did the parser build an `rk-probe` element (browser migration:315-336). A value landing in `href` grades `escaped` or `absent`, i.e. a refutation. `capture_dom` holds the raw material; nothing reads context out of it. Also: no fragment source, per browser migration:104-110 |
| **Prototype pollution** (`:133-155`, `:480`) | read `({}).<key>` after a navigation carrying `?__proto__[key]=value`; then the sink, evidenced by a DOM delta or a Receipt for a URL nobody named | navigation with a query is expressible; the *read* is not - it needs a probe row that does not exist, and the answer ("is this inherited property set") fits the outcome vocabulary as a boolean, so only the probe is missing |
| **DOM clobbering** (`:87-110`, `:478`) | which globals the page reads before defining; the DOM after injecting `id`/`name` markup; the resulting property value; the Receipt of any resource the clobbered value loaded | injection of inert markup is exactly what `inject` does; the DOM is `capture_dom`; the Receipt exists. The two reads - the global-name inventory and the resulting property - need probes |
| **postMessage** (`:42-63`, `:476`) | the set of registered `message` listeners and handler source; the message sent, step-attributed; the DOM delta after it; the `targetOrigin` of every outbound send | none of it. No listener enumeration (needs `DOMDebugger.getEventListeners`, a domain we do not enable, `browser_driver.py:800`), and no action sends a message |
| **CSP / COOP / CORP / Permissions-Policy** (`:111-132`, `:307-327`, `:479`, `:495-498`) | the whole CSP and CSP-Report-Only header per response; the nonce across two responses to one route; every host per directive | the *record* has this: response transcripts per Receipt (`proxy.py:317, 789-798, 3054-3062`). The Skill never says so, and no Playbook reads it. This is a citation gap, not a capture gap - and the research file asks for exactly that statement (`:495-498`) |
| **Storage** (`:217-234`, `:257-273`, `:484`, `:503-507`) | per-origin cookie jar with prefixes and duplicate-name behaviour; `localStorage` / `sessionStorage` / IndexedDB names | nothing, and a probe may not do it (browser migration:1382-1389). Needs an action, not a probe |
| **Service workers / Cache API** (`:257-273`, `:486`) | registered script URL and scope, `Service-Worker-Allowed`, whether a caller value reaches the registration or `importScripts` URL, the Cache API key list | nothing. `Service-Worker-Allowed` is in the response transcript; the rest needs the `ServiceWorker` and `CacheStorage` domains |
| **CSPT / CSPT2CSRF** (`:64-86`, `:477`) | method, path, headers and body of every page-originated request before and after; whether a CSRF token or `Authorization` rode along; the response to the moved request; a canary proving the reflection reached the path | the closest thing we have to complete. Receipts carry method, host, path and both transcripts (`proxy.py:3044-3062`); the canary lands in the path, which is recorded verbatim, and *not* in the query, which is only a digest (`proxy.py:743`) |

Two classes the research file itself marks as out of this lane: WebSocket frames
are a proxy gap, not a browser gap (`:291-306`), and everything needing a second
origin - clickjacking from a frame, XS-Leaks, self-XSS escalation - stays
refused (`:235-256`, `:274-290`, `:307-327`).

## The primitives other surfaces expose

**Chrome DevTools Protocol.** Every gap in the table above except the two
out-of-lane ones maps onto a CDP domain we do not enable
(`browser_driver.py:800` enables `Page`, `Runtime`, `Network`, `Log`):

| Domain / method | What it gives | Which of our gaps it closes |
| --- | --- | --- |
| `DOMStorage.getDOMStorageItems` (+ `domStorageItem*` events); domain marked experimental | all key/value pairs of one storage area | `browser-storage`'s blind spot |
| `Storage.getCookies` (stable); `Storage.getStorageKey`, `getSharedStorageEntries`, `getTrustTokens` (experimental) | the cookie jar; storage keys | cookie tossing and prefix reads |
| `Network.getCookies` / `getAllCookies` (deprecated) / `setCookie` | per-URL jar | same |
| `CacheStorage.requestCacheNames`, `requestEntries`, `requestCachedResponse` (experimental) | cache names, entries and a cached response body | the Cache API half of the worker class |
| `ServiceWorker` domain (experimental): `enable`, `unregister`, `updateRegistration`, `startWorker`, events `workerRegistrationUpdated`, `workerVersionUpdated`; `ServiceWorkerRegistration` carries `registrationId`, `scopeURL`; `ServiceWorkerVersion` carries `scriptURL`, `status`, `runningStatus` | registered script URL and scope, without touching the site | the worker inventory |
| `DOMDebugger.getEventListeners` | "Returns event listeners of the given object" - type, `useCapture`, handler, node | the `message`-listener inventory postMessage work starts from |
| `Network.responseReceivedExtraInfo` / `requestWillBeSentExtraInfo` (experimental) | raw, unfiltered headers as the network stack saw them | a second, in-browser account of headers our door already records |
| `Network.getSecurityIsolationStatus` (experimental) | COEP/COOP isolation status | the defensive half of XS-Leaks |
| `Network.getResponseBody` | the body served for one request | a subresource body without a second fetch |
| `Page.getFrameTree` (stable), `Page.getResourceTree` (experimental) | the frame tree and its resources | iframe `src`/`allow`/`sandbox` inventory |
| `Page.javascriptDialogOpening` (stable) | "Fired when a JavaScript initiated dialog (alert, confirm, prompt, or onbeforeunload) is about to open" | the classic execution oracle - and one we should not want, see below |
| `Page.addScriptToEvaluateOnNewDocument` (stable), `Runtime.addBinding` + `Runtime.bindingCalled` (event experimental) | run code before the page's own; a page-to-driver callback channel | powers to refuse explicitly, not to adopt |
| `Page.setBypassCSP` (stable) | turns the target's CSP off | a power to refuse: a finding proved with CSP off is not a finding |

**Playwright.** `BrowserContext` gives `cookies()`, `addCookies()`,
`clearCookies()`, `storageState()`, `setStorageState()`, `addInitScript()`,
`route()` / `unroute()` / `routeFromHAR()` / `routeWebSocket()`,
`serviceWorkers()`, and events `request`, `response`, `requestfailed`,
`requestfinished`, `console`. That is our whole missing read set plus a request
interception layer we would not want, because interception inside the browser is
a second place a request could be rewritten after the door decided on it.

**Puppeteer** exposes the raw protocol rather than a curated subset:
`page.createCDPSession()` returns a `CDPSession` used "to talk raw Chrome
Devtools Protocol", with `send()` and `on()`. Any domain above is one call away.

**Agent-facing browser servers.** Playwright MCP exposes 50+ tools - navigate,
click, type, fill form, evaluate JavaScript, snapshot, screenshot, network
request inspection, cookie get/set/delete/clear/list, localStorage,
sessionStorage, storage state, route/mock, offline toggle - and states plainly
that it "is **not** a security boundary". Chrome DevTools MCP exposes
`navigate_page`, `list_network_requests`, `get_network_request`,
`list_console_messages`, `evaluate_script`, `take_snapshot`, `take_screenshot`,
`performance_start_trace`, `lighthouse_audit` and heap tooling, with `--isolated`
for a temporary profile, and warns that it "exposes content of the browser
instance to the MCP clients allowing them to inspect, debug, and modify any data
in the browser". Both are the same shape: an open `evaluate` verb, an open
storage surface, and no record of what the browser did. Our lane trades the open
verbs for a closed action set and a Receipt per request; the trade is right, and
it is the *reads* it also gave up that this document is about.

**How security tools use them.** Nuclei's headless protocol is a template
language over `navigate`, `waitload`, `waitdom`, `waitidle`, `waitstable`,
`click`, `text`, `keyboard`, `select`, `files`, `script`, `extract`,
`getresource`, `screenshot`, plus request manipulation (`setmethod`, `addheader`,
`setheader`, `deleteheader`, `setbody`) and `waitdialog`, which detects a
triggered XSS by trapping `alert`/`confirm`/`prompt` and is described as giving
a "high level of accuracy and a low rate of false positives". Burp's
browser-powered scanning uses an embedded Chromium for coverage a raw crawler
cannot reach: dynamically generated UI, JavaScript event handlers that send
requests, and complex login flows. DOM Invader is the capability baseline for
the classes we cannot express: DOM XSS with "both the XSS context and how your
input is being sanitized", "Log, modify, and resend web messages", automatic
identification of "sources of client-side prototype pollution" and of
"controllable gadgets that are passed to dangerous sinks", and automatic DOM
clobbering detection.

Sources: <https://chromedevtools.github.io/devtools-protocol/tot/DOMStorage/>;
<https://chromedevtools.github.io/devtools-protocol/tot/Storage/>;
<https://chromedevtools.github.io/devtools-protocol/tot/CacheStorage/>;
<https://chromedevtools.github.io/devtools-protocol/tot/ServiceWorker/>;
<https://chromedevtools.github.io/devtools-protocol/tot/DOMDebugger/>;
<https://chromedevtools.github.io/devtools-protocol/tot/Network/>;
<https://chromedevtools.github.io/devtools-protocol/tot/Page/>;
<https://chromedevtools.github.io/devtools-protocol/tot/Runtime/>;
<https://playwright.dev/docs/api/class-browsercontext>;
<https://pptr.dev/api/puppeteer.cdpsession>;
<https://github.com/microsoft/playwright-mcp>;
<https://github.com/ChromeDevTools/chrome-devtools-mcp>;
<https://docs.projectdiscovery.io/templates/protocols/headless>;
<https://portswigger.net/burp/documentation/scanner/browser-powered-scanning>;
<https://portswigger.net/burp/documentation/desktop/tools/dom-invader>.

## Proposed additions

Ranked by how many refused bug classes each unblocks per unit of new power. The
first two grant no new power at all.

**1. A Contract that starts a mission.** Action: a model-facing verb minting the
Tool run `mcp__rk2__browse` already named in the migration (browser
migration:732), taking a plan of declared actions and an optional identity slot,
exactly as `open_browser_run` already accepts them (browser migration:761-1010).
Returns: the run label, plan digest, result digest, step outcomes and Artifact
labels - what `browser.py:206-215, 281-289` already assembles. **Act.** Risk:
this is the whole browser lane becoming reachable by a model, so every ceiling,
the closed action set and the plan digest are load-bearing from that day. It
grants no capability the lane does not already have under an operator's hand,
and until it exists `SKILL.md:63` instructs a call `roster.py:784` refuses.

**2. Say, in the Skill, that response headers are already on the record.**
Action: none - a Skill and Playbook change pointing at the Receipt's
`response_agent_sha` and the `message/http` transcript behind it
(`proxy.py:317, 789-798, 3054-3062`; packet fields at
`20260815T180000Z__a_blind_validator_answers_from_the_packet.sql:174-187`).
Returns: CSP, CSP-Report-Only, COOP, COEP, CORP, Permissions-Policy,
`Service-Worker-Allowed`, `Vary` and cookie *attributes*, per response, already
hashed and citable. **Read.** Risk: none new; the one honest caveat is that
`Set-Cookie` and the authentication headers are wire-only and absent from that
view (`proxy.py:340-357`), so a cookie-prefix reading must say it is reading the
request side and the target's behaviour, not the raw `Set-Cookie`. This closes
the research file's first cross-cutting ask (`06-client-side-browser.md:495-498`)
for the price of a paragraph.

**3. Per-probe declared outcome keys.** Action: none new; widen `browser_probes`
so a row declares its own outcome keys the way `browser_actions` does (browser
migration:162-164), each value still a word from `rk2_browser_outcome_word`
(browser migration:710-719). Returns: a `probe` step whose digest-visible answer
is, say, `verdict=reflected, sink=url_attribute, attribute=href` instead of one
word - while the probe's full JSON stays an Artifact as it already does
(`browser_driver.py:639-645`). **Read.** Risk: low and bounded - the vocabulary
still refuses timestamps, nonces and identifiers, so the digest cannot be made
to carry per-run noise. This is the research file's second cross-cutting ask
(`:499-502`) and it is the enabler for the sink-context taxonomy, sanitiser
fingerprinting and the clobbering property read.

**4. A `read_client_state` action.** Action: one action with a `kind` argument
over a closed set - `local_storage`, `session_storage`, `indexeddb_names`,
`cookies`, `service_workers`, `message_listeners` - implemented over
`DOMStorage.getDOMStorageItems`, `Storage.getCookies`, the `ServiceWorker`
domain and `DOMDebugger.getEventListeners`, with the domains enabled beside the
four in `browser_driver.py:794-802`. Returns: one JSON Artifact per step, shaped
like a probe's (`browser_driver.py:484-498`), plus a counted outcome
(`entries`, a small integer, which the vocabulary admits). **Read - and this is
the point.** It plants nothing, sends nothing and changes no state; it is the
browser answering what the page already holds. It needs no new offensive power
and it is the third cross-cutting ask (`:503-507`), closing `browser-storage`,
half of `browser-messaging` and all of the worker class at once. Two risks, both
answerable in the design rather than by declining it:
* *Credential re-exposure.* The door strips `Set-Cookie` from the agent view on
  purpose (`proxy.py:340-357`), and an Identity's value is injected at the door
  and never handed to the browser (`browser.py:8-11`, `cli.py:1193-1199`). A jar
  read that returned values would put back exactly what those two lines remove.
  So: cookies return name, domain, path, `httpOnly`, `secure`, `sameSite` and
  prefix, and never a value. The same argument does *not* apply to
  `localStorage`, whose contents are the application's own data and the thing
  the finding is about - but they are the target's words, and
  `SKILL.md:73-99` is the rule for reading them.
* *Probe parity.* `check_browser_runs` today faults a probe that touches
  `document.cookie` or the storages (browser migration:1382-1389). That check
  must keep meaning what it means: the new action is the sanctioned path and
  probes stay out, so the check narrows to probes rather than being relaxed.

**5. A fragment in `navigate`.** Action: widen the `url` kind (browser
migration:104-110) to admit a fragment. Returns: nothing new; the same outcome
keys. **Act**, but the weakest kind: a fragment never leaves the browser, so the
Receipt and the scope decision are over the same URL they are over today, and
`_classified` already matches on host and path alone (`browser.py:466-480`). The
migration's stated reason for refusing one - that the Receipt would not match -
is satisfied by classifying the URL without its fragment, which is what the code
already does. Risk: low. Without it, every fragment-source DOM XSS reading is
unavailable, which is a large share of the class.

**6. A `send_message` action.** Action: post one registry-owned message body to
the page from the same origin, the way `inject` types a registry-owned payload
(`browser_driver.py:565-568`). Returns: `matched`, with the DOM delta coming
from a following `capture_dom`. **Act**, and the first action that fabricates an
event the target did not cause. Risk: real but bounded - the body is owned by a
migration-written registry exactly as a probe's payload is (browser
migration:285-306), and same-origin only, which is the point
`06-client-side-browser.md:42-63` makes against our current refusal. It should
not ship before 3 and 4, because without a listener inventory it is a message
sent into the dark.

**7. A navigation-chain outcome.** The final URL after a redirect chain cannot
be an outcome value (browser migration:710-719 admits no URL), so the honest
form is a Receipt-side reading: the hops are already there, one Receipt each
(`proxy.py:3014-3034` records the link between them). **Read.** Risk: none new.
This is what `06-client-side-browser.md:344-357` and `:491` need.

**8. WebSocket frames.** Out of this lane: the door does not carry the upgrade,
so no browser action can fix it (`06-client-side-browser.md:291-306`). Record as
a proxy ticket, not a browser one.

Explicitly **not** proposed, and each for a reason worth writing down:
`Page.setBypassCSP` (a finding proved with the target's CSP disabled is not a
finding); `Runtime.addBinding` / `Runtime.bindingCalled` (a page-to-driver
channel is a way for target content to speak to the harness outside the five
declared channels of `SKILL.md:73-99`); `Page.javascriptDialogOpening` as an XSS
oracle (it is the honest one, and it costs running an attacker's script in a
real session - the next section is about whether we can avoid that); and
in-browser request interception (`route()` in Playwright), because a request
rewritten inside the browser after the door decided on it is the second egress
path this harness does not have.

## The execution oracle question

The proposal in `06-client-side-browser.md` is to prove that a browser *acted*
on attacker-controlled markup without running script, by having an inert element
fetch a resource so the interaction lands in a Receipt (the mechanic the file
leans on repeatedly - `:103-105` for clobbering, `:209-212` for CSS injection, where
it calls the Receipts "our proof that the CSS *ran* rather than merely parsed").

**It works here, and the machinery it needs already exists.**

1. Every request the page makes crosses the shim to the door. Chromium is
   pointed at `127.0.0.1:3128` (`browser_driver.py:68-69, 748-763`), and
   `--proxy-bypass-list=<-loopback>` defeats Chromium's implicit loopback bypass
   so even a request aimed at the driver's own debugger goes to the door
   (`browser_driver.py:132-140`). Chromium's own documentation confirms both
   halves of that: loopback names are bypassed implicitly, and `<-loopback>` is
   the rule that undoes it.
2. The door decides before any packet leaves. Scope is re-decided per request
   against the current policy, and the name is resolved only *after* the
   capability is spent and the scope check passes, "because a DNS query is
   itself egress" (`proxy.py:47-56`).
3. A refusal is still a record. `_refuse` writes a blocked Receipt carrying
   method, scheme, host, port, **path**, `query_sha256`, `scope_class` and the
   reason (`proxy.py:3138-3197`), and `write_blocked_receipt` attributes it to
   the Tool run by resolving the capability
   (`migrations/20260811T170000Z__egress_budget_at_the_door.sql:153-212`).
4. An allowed one carries more: the request and response transcripts as
   Artifacts (`proxy.py:3044-3062`).
5. The reconciliation already exists: the driver counts `requestWillBeSent`
   per step (`browser_driver.py:671-684`) and `check_browser_runs` faults when
   counted requests exceed Receipts (browser migration:1362-1370).

So the oracle is: `inject` a registry-owned payload containing an inert element
with a resource URL, `wait_for`, and read the Receipt list. Five conditions,
each of which changes the design:

* **The marker goes in the path, never the query.** A blocked Receipt stores no
  transcript, and the query survives only as a digest (`proxy.py:743`;
  Receipt field `query_sha256`). The path is stored verbatim
  (`proxy.py:3180`), so `/rk-oracle/<marker>` is readable and
  `?rk=<marker>` is not.
* **The URL should be relative to the target's own origin.** An absolute URL at
  a host outside scope is refused before DNS, so nothing leaves this machine
  (`proxy.py:47-56`) - but if the injection is *stored*, the same element sits
  in the target's page beaconing every later visitor at a host we named. A
  relative path keeps the request on the target's own origin, where it is
  in-scope, earns an allowed Receipt with a status and a transcript, and where a
  stored copy costs the target one 404 rather than a third-party callout.
* **It is a step away from the posture the current probe was written to hold.**
  The `markup_injection` payload is justified in as many words: `rk-probe` has
  "no script, no attribute a browser acts on and no content, so planting it
  changes what the document IS without changing what it DOES" (browser
  migration:333-338). An element that fetches *does* something. It is still not
  script, it is still one GET, it is still to the target's own origin, and the
  capability a read-only plan holds cannot POST anyway (browser migration:779,
  948-949, 1320-1327) - but the sentence above stops being true, and that is an
  ADR-level decision rather than a migration nobody discusses.
* **The answer arrives as a Receipt, not as a verdict.** No outcome key can
  carry a URL (browser migration:710-719), so the oracle does not move the
  result digest; the mission's own record says only that a step matched. The
  agent reads it from `get_receipts`, and only for Receipts staged into its
  packet (`packet.py:873-909`). If proposal 3 lands, the probe can also return a
  digest-visible word - but the *proof* is the door's row.
* **Attribution slips, and false negatives are real.** A fetch may start after
  the step window the driver counts in (`browser_driver.py:671-684`), so the
  request may be counted against a later step; the Receipt is still there and
  still carries the marker. And a load can fail to happen for reasons that are
  not "the markup was inert": CSP can block an `img` from loading an external
  resource, as PortSwigger's dangling-markup page states, and an element that is
  lazy-loaded or never inserted fetches nothing. A negative from this oracle is
  therefore inconclusive, not a refutation.

**Verdict: it works, and its added value is narrower than it looks.** For markup
injected into the document the mission is looking at, `markup_injection` already
answers "did the parser build an element" by reading the DOM (browser
migration:315-336), and does it without any element acting. The oracle earns its
keep exactly where that read cannot go: injection into a cross-origin frame or a
document the mission has navigated away from, CSS and `style` contexts where the
sink is a `url()` load and there is no element to count
(`06-client-side-browser.md:197-216`), clobbering impact where the question is
whether a clobbered value became a resource URL (`:103-105`), and any case where a
second, page-independent channel is wanted - the door's row is not something the
target's page produced. Recommend it as a second registry probe with a relative
same-origin path marker, after proposals 2 and 3, and not as a replacement for
the DOM read.

## Isolation and egress

What must hold whenever this harness renders a target's content, and what our
tree does about it today.

**One peer, and no second route.** The container is attached to a per-run
adapter network whose only peer is the door, with DNS pointed at a blackhole so
no name resolves inside (`src/redkraken/isolation.py:55, 753-754, 786-792`).
Chromium is given the shim as its proxy and the shim relays to the door
(`browser_driver.py:268-281`); the shim decides nothing and holds no policy,
scope, identity or allowlist (`browser_driver.py:13-24`). Chromium cannot be
made to send the capability header itself - `--proxy-server` ignores credentials
in the URL, which Chromium's own proxy documentation states ("Chrome does not
implement this, and will not use any credentials embedded in the proxy
settings") - which is why the shim exists at all.

**Process isolation, honestly stated.** Chromium ran `--no-sandbox` because the
container drops every capability and the two together were thought to need a
capability set it does not have. Ticket 174 measured that and it was not so: the
blocker was the engine's default seccomp profile alone, which gates `clone` into
a new namespace, `unshare` and `chroot` on capabilities `--cap-drop ALL` removes.
Chromium now runs sandboxed under `src/redkraken/browser_seccomp.json`, and the
container's own capability set is still empty. Site Isolation still
puts cross-site documents in different renderer processes inside the container,
which is what Chromium's Site Isolation page describes as its defence against
compromised renderers, UXSS and Spectre - but with the OS sandbox off, a
renderer compromise is code running as uid 65534 inside our container, and the
container is the only boundary left. That container is `--cap-drop ALL`,
`no-new-privileges=true`, `--read-only`, `--user 65534:65534`, `--pull never`,
`--entrypoint ""` and `--rm` (`isolation.py:165-212`), with scratch on a
`nosuid,nodev,noexec` tmpfs (`isolation.py:810-811`) and memory, CPU, pids and
output ceilings from the registry (`browser.py:389-397`). The external practice
this should be measured against is Playwright's: running as root "will disable
the Chromium sandbox", `seccomp_profile.json` "is needed to run Chromium with
sandbox", and for untrusted sites they recommend a separate user together with
that profile; Puppeteer's troubleshooting page says running without a sandbox is
"strongly discouraged". **Our tree runs unprivileged and sandboxed inside a
hardened container; the seccomp profile that lets Chromium's own sandbox start
is `src/redkraken/browser_seccomp.json`, and ticket 174 is where the measurement
behind it is written down.**

**Profile lifetime.** The profile lives at `/work/profile`
(`browser_driver.py:62`), which is a bind mount of a per-run staging directory
the supervisor creates with `mkdtemp` and removes with `rmtree` in a `finally`
(`isolation.py:784, 867`). Nothing survives a mission: no cookie jar, no
cache, no service worker registration, no `localStorage`. That is the right
default and it is also why any client-state read has to happen *inside* the
mission that produced the state. It is the opposite of what the agent-facing
servers default to - Playwright MCP and Chrome DevTools MCP both persist a
profile unless told `--isolated`.

**The debugger port.** Bound to `127.0.0.1` (`browser_driver.py:66-69, 751-752`)
and reachable from nowhere else, because the container's network has exactly one
peer. This matters: a CDP endpoint has no authentication of its own, so anything
that can reach it can drive the browser - which is why the driver also sets
`--proxy-bypass-list=<-loopback>`, so a page asking for
`http://127.0.0.1:9222/json/new?url=...` is a request that goes to the door and
is refused there by name rather than a second network path
(`browser_driver.py:132-140`).

**What must never leave the machine.** The capability, which is written into the
plan file and never into the container's environment "where a page that could
read the process table would find it" (`browser.py:8-11`), and which the door
takes off the request before any other line reads it (`proxy.py:6-13`). An
Identity's value, which the door injects and the browser is never given
(`cli.py:1193-1199`). Target-issued credential headers, which are wire-only and
sealed rather than agent-visible (`proxy.py:340-357, 659-698`). And any request
the scope compiler denies, which is refused before a name is resolved
(`proxy.py:47-56`) - the property that makes an out-of-scope oracle URL a row in
our database rather than a packet on the wire.

**What an operator must never do.** Point this lane at a browser profile that is
not the per-run one, connect it to an already-running browser (the
`--browser-url` / extension modes both agent-facing servers offer), or expose
the debugger on anything but loopback. Playwright MCP's own README says it "is
**not** a security boundary"; ours is one only because of the container, the
one-peer network and the door, and each of those three is a line in the tree
above rather than a property of the browser.

## Sources consulted

Our own tree, read at the lines cited above:
`src/redkraken/browser.py`, `src/redkraken/browser_driver.py`,
`src/redkraken/roster.py`, `src/redkraken/proxy.py`,
`src/redkraken/isolation.py`, `src/redkraken/packet.py`,
`src/redkraken/cli.py`, `src/redkraken/skills/browser-evidence/SKILL.md`,
`src/redkraken/migrations/20260814T040000Z__a_browser_mission_runs_behind_the_door.sql`,
`src/redkraken/migrations/20260811T170000Z__egress_budget_at_the_door.sql`,
`src/redkraken/migrations/20260815T180000Z__a_blind_validator_answers_from_the_packet.sql`,
`src/redkraken/migrations/20260922T050000Z__a_bad_wait_fails_more_missions_than_a_bad_selector.sql`,
`docs/research/playbook-state-of-the-art/06-client-side-browser.md`,
`docs/research/harness-capabilities/10-agent-tooling-state-of-the-art.md`.

External, each fetched successfully unless said otherwise:

* <https://chromedevtools.github.io/devtools-protocol/tot/DOMStorage/> - `getDOMStorageItems` and the `domStorageItem*` events; domain marked experimental.
* <https://chromedevtools.github.io/devtools-protocol/tot/Storage/> - `getCookies` (stable), `getStorageKey`, `getSharedStorageEntries`, `getTrustTokens` (experimental).
* <https://chromedevtools.github.io/devtools-protocol/tot/CacheStorage/> - `requestCacheNames`, `requestEntries`, `requestCachedResponse`; experimental.
* <https://chromedevtools.github.io/devtools-protocol/tot/ServiceWorker/> - the domain's methods and events, and the fields of `ServiceWorkerRegistration` and `ServiceWorkerVersion`; experimental.
* <https://chromedevtools.github.io/devtools-protocol/tot/DOMDebugger/> - `getEventListeners`, "Returns event listeners of the given object".
* <https://chromedevtools.github.io/devtools-protocol/tot/Network/> - `getResponseBody`, the cookie methods, `responseReceivedExtraInfo` / `requestWillBeSentExtraInfo` (experimental, raw headers), `getSecurityIsolationStatus` (experimental).
* <https://chromedevtools.github.io/devtools-protocol/tot/Page/> - `javascriptDialogOpening`, `setBypassCSP`, `getFrameTree`, `getResourceTree` (experimental), `addScriptToEvaluateOnNewDocument`, `frameRequestedNavigation` and `navigatedWithinDocument` (both experimental).
* <https://chromedevtools.github.io/devtools-protocol/tot/Runtime/> - `evaluate`, `callFunctionOn` with `arguments`/`returnByValue`, `addBinding`, `bindingCalled` (experimental), `consoleAPICalled`, `exceptionThrown`.
* <https://playwright.dev/docs/api/class-browsercontext> - `cookies()`, `storageState()`, `addInitScript()`, `route()`, `routeWebSocket()`, `serviceWorkers()`, and the `request`/`response`/`console` events.
* <https://playwright.dev/docs/docker> - "`seccomp_profile.json` is needed to run Chromium with sandbox"; running as root "will disable the Chromium sandbox"; separate user recommended for untrusted websites; `--ipc=host` recommended for Chromium.
* <https://pptr.dev/troubleshooting> - "Running without a sandbox is strongly discouraged."
* <https://pptr.dev/api/puppeteer.cdpsession> - `page.createCDPSession()`; "used to talk raw Chrome Devtools Protocol".
* <https://github.com/microsoft/playwright-mcp> - 50+ tools including evaluate, storage and route groups; persistent profile by default with `--isolated` for a temporary one; "Playwright MCP is **not** a security boundary".
* <https://github.com/ChromeDevTools/chrome-devtools-mcp> - `list_network_requests`, `get_network_request`, `list_console_messages`, `evaluate_script`, `take_snapshot`, performance tracing; `--isolated`; "exposes content of the browser instance to the MCP clients allowing them to inspect, debug, and modify any data in the browser".
* <https://docs.projectdiscovery.io/templates/protocols/headless> - the headless action set, `script` with matchers, and `waitdialog` as the XSS oracle.
* <https://portswigger.net/burp/documentation/scanner/browser-powered-scanning> - why an embedded browser reaches coverage a raw crawler cannot.
* <https://portswigger.net/burp/documentation/desktop/tools/dom-invader> - sink context and sanitisation, web message log/modify/resend, prototype pollution sources and gadgets, DOM clobbering detection.
* <https://portswigger.net/web-security/cross-site-scripting/dangling-markup> - an injected non-script element causing an outbound request as the proof, and CSP preventing "tags like `img` from loading external resources".
* <https://chromium.googlesource.com/chromium/src/+/HEAD/net/docs/proxy.md> - the implicit loopback bypass, the `<-loopback>` rule that undoes it, and that Chrome "will not use any credentials embedded in the proxy settings".
* <https://www.chromium.org/Home/chromium-security/site-isolation/> - cross-site documents always in a different process; the compromised-renderer, UXSS and Spectre threat model.
* <https://chromium.googlesource.com/chromium/src/+/main/docs/design/sandbox.md> - the renderer sandbox model; it notes renderers run sandboxed "unless the `--no-sandbox` command line has been specified" and does not state the consequences, so no consequence is attributed to it here.
* <https://developer.chrome.com/blog/chrome-headless-shell> - `chrome-headless-shell` (what our image runs, `browser_driver.py:57`) is the lightweight old headless with fewer features, recommended for screenshotting and scraping, versus `--headless=new`, "the actual Chrome browser", recommended where authenticity matters. Relevant to any proposal above that depends on a feature the shell may not carry.
