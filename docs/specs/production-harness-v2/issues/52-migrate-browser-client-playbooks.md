# 52 — Migrate browser and client-side Playbooks

**What to build:** Deliver production-ready Playbooks and browser fixtures for eight v1 topics whose evidence depends on origin, framing, messaging, script, storage or client-side navigation behavior.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** resolved

**Deviation on criterion 6, inherited from 49, 50 and 51:** the positive and adversarial
arrangement exists and is total; the evaluation that would grade it has not run, and cannot
run from this ticket. All eight ship `draft`. `stable` is reachable only through
`playbook_test_verdict` returning `pass` for the exact text, and an evaluation run is an
Agent run against a fixture listening on loopback, which `scope.compile_policy` and
`authorize_identity_egress_address` both refuse. Ticket 78 decided that route; ticket 84
grades the corpus over it. What moved is the measurement: the corpus is twenty-eight
Playbooks and twenty-nine fixtures, `playbook_fixture_binding` is still total over the
fixture table, and each of the eight new fixtures is an out-of-class negative for the
twenty-seven Playbooks that do not output its class. The other half of the criterion -- "no
human-only reference leakage into model projections" -- is checked and holds:
`test_no_reference_text_reaches_a_shipped_projection` reads every line over forty characters
out of all nine attached references and asserts it is absent from the projection the model
receives.

**Deviation on criterion 3, on running the browser fixtures through containment:** the three
fixtures whose reading needs a browser (`client-channel-pair`, `client-path-pair` and
`markup-pair`) are written and are graded by the three Playbooks that name
`browser-evidence`, but a browser mission against them is refused for criterion 6's reason:
they listen on loopback and the egress authoriser refuses loopback. `BrowserCommandTest`
already exercises the containment path -- DOM, screenshot and network evidence bound to a
Receipt -- against `tests/browser_target.py`, and is skipped without `RK_TEST_BROWSER_IMAGE`.
So the binding this criterion asks for exists and is tested; what is missing is the same
graded run over the route 78 built, which is ticket 84's.

- [x] Browser Framing, Browser Messaging, Browser Realtime, Browser Script, Browser Storage, Client-Side Path Traversal, External Resources and Web Cache each exist as authored v2 Playbooks.
- [x] Each Playbook declares whether evidence requires browser, HTTP differential, DOM, storage, origin, framing or cache capabilities and is loadable by an appropriate role.
- [ ] Browser fixtures run through production containment and bind DOM, screenshot and network evidence to Receipts and Tool runs. **Partial:** `BrowserCommandTest` proves that binding through the real container; the loopback fixture route is the missing half. Ticket 78 built that route; ticket 84 grades the corpus over it.
- [x] Controls distinguish executable impact from reflection, browser policy from server policy and target behavior from proxy-induced protocol behavior.
- [x] Cache, realtime and external-resource tests remain scope- and budget-bound and refuse uncontrolled third-party effects.
- [ ] All eight exact hashes pass positive and out-of-class adversarial evaluation with no human-only reference leakage into model projections. **Partial:** the projections hold and the fixtures grade; the production evaluation waits on the same route. Ticket 78 built that route; ticket 84 grades the corpus over it.

## Comments

Implemented on 2026-08-16.

### Eight topics from nine v1 pages, and where the seams fell

v1 split this material by page rather than by reading, so the mapping is not one-to-one.
`browser-framing` absorbs clickjacking and CORS/XSSI, because both are the same question --
what a header declares about who may embed this document or read its answer -- asked at
step 1 and answered at step 2. `browser-script` absorbs XSS and dangling markup, because
the second is the first with the payload cut short. `browser-messaging` absorbs DOM
vulnerabilities and prototype pollution, because both are input reaching a sink through the
page's own handlers without a request. `browser-realtime`, `external-resources` and
`web-cache` each take one page. `browser-storage` and `client-side-path-traversal` take
none: v1 had no page on the first and covered the second in prose inside its client-side
pack, so both have nothing attached rather than a placeholder.

### Six new leaves, and why the browser needed them

018 split injection by the interpreter, "because the interpreter is the test", and then named
only the interpreters that live on a server. `injection.markup` was its one browser leaf and
`browser-script` is the first Playbook to claim it. The three added here are the browser's
other interpreters and they are separate leaves for 018's own stated reason -- the test is
different in each. `injection.client_channel` is the page's message and event handling, where
nothing reaches the server at all, so no response differencing can see it.
`injection.client_path` is the URL builder in the page, where the request carrying the input
is one the page makes rather than one the caller makes. `injection.foreign_resource` is the
resource loader, where the input names a host and what executes is whatever that host serves.

The other three sit in families 018 already had and add the leaf that family was missing for
a browser: `information_disclosure.client_storage`, `information_disclosure.cached_response`
and `authorization.channel_subscription`.

### What tells the eight apart on the Surface

Three new facts, and one Application kind that had been silently discarded since 003.
`web_surface` is the kind: 003 has admitted `web` since it was written, `subject_facts` never
had a branch for it, and every Surface in the corpus so far has had to call itself an `spa`
as a result. Six of this ticket's eight Playbooks trigger on it, so the kind stops being
dropped. `embedded_document` is a new `embeds` relationship read at its far end, exactly the
way `flow_step` is `redirects_to` read at its far end -- and `embeds` is the second
endpoint-to-endpoint type after 004's `redirects_to`. `tech_cdn` is a caching front end having
been fingerprinted, and it maps six vendor names onto one fact because a cache is one fact
however it was identified.

Those keep `PlaybookCorpusSelectionTest` diagonal across a table that grew from twenty rows
to twenty-eight. Six of the eight new subjects are a GET on a `web` Application, which nothing
in the previous vocabulary distinguished, so each is picked out by one further fact: what the
route carries (`path_parameter`, `url_valued_parameter`, `reflected_parameter`), what points
at it (`embedded_document`), what runs in front of it (`tech_cdn`), or whether it is behind a
session (`authenticated_endpoint`). `browser-framing` is a form write and `browser-realtime`
is on the socket, separated from 049's `realtime` by wanting a query parameter: the topic is
which channel was asked for, and a socket that takes no argument has no channel to ask for.

Two arrangement details follow from that. `embedded_document` is the second trigger fact in
that case's table that a Surface cannot carry alone, so the arrangement grew a second endpoint
-- `GET /account` on the messaging Application, embedding the subject -- beside the payment
step 51 added for `flow_step`. And the five unauthenticated-looking reads state their auth as
unknown rather than false, because `attack-surface` is `read_method` with
`unauthenticated_endpoint` and a Surface that said `false` would match it too.

### The fixtures, and what each one holds constant

Every pair holds one class, and the way to hold one class is to enforce everything else
identically on both halves. Each of the eight does that at a different place, and each ground
truth names the neighbouring class it is keeping out.

`header-policy-pair` checks a per-session CSRF token on both variants, which keeps
`session_handling.csrf` out, and issues a byte-identical cookie on both, which keeps
`session_handling.cookie_scope` out -- the difference is confined to the framing and CORS
headers. `client-storage-pair` accepts either the cookie or a bearer token on both halves, so
the difference is the login response handing the value to page script rather than the parser
that reads it back. `channel-subscription-pair` enforces the `Origin` check on both, which
keeps `session_handling.csrf` out, and its topics are streams with entitlement lists rather
than owned objects, which keeps `authorization.object_ownership` and
`authorization.tenant_isolation` out. `foreign-resource-pair` attribute-escapes on both halves,
which keeps `injection.markup` out, sets no CSP on either, which keeps
`transport.header_policy` out, and names every address under RFC 2606 `.invalid` so nothing
resolves. `cached-response-pair` checks the session before consulting the cache and never
stores a `401`, so the disclosure graded is the one between two callers who both signed in,
and renders correctly on both halves, so it is not an ownership or tenancy defect.

Two of the eight are graded on something no response body carries. `client-channel-pair` never
sends the value to the server, and `client-path-pair` differs only in the second request the
page makes, so both are pairs whose halves serve identical bytes to identical requests. That is
the honest shape of those classes rather than a gap in the fixtures, and it is why the
Playbooks that grade them name `browser-evidence`.

`cached-response-pair` and `channel-subscription-pair` are the two with two Identities, because
neither disclosure exists with one caller: what crosses is one caller receiving what was
published or rendered for another.

A fixture's `bb:facts` is what would make its grader's trigger fire, so each pair has to carry
its grader's whole `all` set and nothing enforces that but reading it. `channel-subscription-pair`
declared the session fact and not `multiple_test_identities`, which is the fact
`browser-realtime` actually keys on and which the pair's own two Identities supply; it declares
both now. The other twenty-eight carry their grader's set, three of them with one true fact
beyond it, which is how `object-ownership-pair` was already written.

### Five supported evidence kinds, which is more than any earlier ticket

The eight are answered in four different places and their evidence says so.
`header_policy_observed` on both roles for `browser-framing`, because the vulnerable target
behaves identically to the secure one and only its headers differ. `reflected_input` for
`browser-script` and `browser-messaging`, because what is claimed is that a value arrived at
an interpreter. `response_differential` for `client-side-path-traversal` and `web-cache`,
because both are about which request was made or which stored copy came back.
`credential_effect` for `browser-storage` and `browser-realtime`, because both end by
presenting something as a credential and recording that it worked. `content_match` for
`external-resources`, the one kind here whose only allowed provenance is a tool run, which is
the honest source: the finding is what the served document points at, read outside the browser.

`browser-storage` is the one whose refutation control is not a variant row. Refuting there
means showing the credential never left the cookie, and the observation that says so is the
cookie's own attributes.

`external-resources` is the one whose refutation is not a `response_invariant` either, and
that is not a stylistic choice: `response_invariant` is admissible only from a Receipt, its
sole loading role holds no `net.request`, and a Playbook whose refutation its own role cannot
produce refutes nothing. Its three rows are all `content_match`.

That is where criterion 2 is answered, and it is answered in two fields rather than one.
There is no capability named "storage" or "framing" or "cache" to declare, because a
capability in v2 is a Skill's tool groups and an observation kind's allowed provenance -- so
what a Playbook needs is stated by which Skills it names and which kinds its evidence is in.
`browser-evidence` is the browser declaration; `compare-responses` with `use-identity` is the
HTTP-differential one; `header_policy_observed` is the framing and origin one, because a
framing answer is a header and nothing else; `response_differential` on a key this run
invented is the cache one; and `analyse-source` with `content_match` is the read-the-bytes
one. The two the harness cannot do are declared by being absent and said out loud in the
text: `browser-storage` states that no action here reads Web Storage, so it reads the cookie
the storage was filled from instead.

### Risk, effects and the one Playbook web_hunter cannot load

All eight are `constrained` and `read_only`, the first ticket where that pairing covers the
whole set. Every one of these readings is answered by loading a document and reading what the
browser or the analyst then sees; nothing registers, cancels, spends or edits anything the
target owns. `autonomous` is refused for the other reason -- each puts a payload or a second
Identity somewhere, and that is an act a Program's rules of engagement bound. That is also
criterion 5's answer: `web-cache` moves to a key nobody else will ask for rather than poisoning
a shared one, `external-resources` sends nothing to any third party at all, and
`browser-realtime` subscribes and reads one frame.

Three Skill sets across the eight. `browser-evidence` alone for the three that cannot be
answered without a browser at all. `compare-responses` with `use-identity` for the four that
difference one caller against another or against a control. `analyse-source` with
`handle-untrusted-content` for `external-resources`, which is the only Playbook in this ticket
`web_hunter` cannot load: reading a served document for what it points at without executing it
is `js_analyst`'s job, and the Skill set says so.

That Skill set decides the whole shape of `external-resources`, and the first draft did not
follow it through. `js_analyst` holds `state.read`, `state.propose` and `exec.tool_run` and no
`net.request`; every registered offline tool is `network 'none'`; so the role can read stored
bytes and run tools over them and can make no request whatever. The draft told it to fetch the
route twice and then resolve every name it found, which is three things it cannot do. The
Playbook now takes both documents as Artifacts by hash, says that a Task naming one hash and
not two leaves the parameter half unanswered, and answers "does the target claim this name"
from the Program's scope and the bytes rather than from the wire. The takeability question --
does the name still resolve, and to what -- is stated as this reading's ceiling in the same
words `analyse-source` uses for reachability, because it is the same wall: source says what an
application refers to and never what answers. That also makes criterion 5 unconditional here
rather than nearly so. The draft ended by reading one out-of-scope origin's status "once"; the
Playbook now reaches nothing, which is the right number of requests to send to a third party
who never agreed to be tested.

Criterion 4's third axis is the one that needed saying twice. `browser-framing` separates
browser, server and proxy in its own step 4 and `browser-realtime` does the same for the
socket, but `web-cache` had the axis only implicitly and it is the topic where it matters
most: a stored answer served by the runtime's own proxy is indistinguishable, from the
caller's side, from a stored answer served by the target. Its step 4 now rules that out by
construction rather than by inspection -- the proxy stores nothing, and step 2's key is unique
to the run, so nothing on this side of the wire has ever seen it -- and says that the fresh key
is what makes the `Age` a claim about the target.

### Two things the tests had to be told

`PlaybookEvaluationTest` opened one Program per fixture half using the fixture id's first word
as the slug. Three of this ticket's fixtures begin `client-`, so all three resolved to one
slug, `program.run` resumed the first Program instead of opening a second, and
`evaluation_programs` -- keyed on the Program -- collided. The slug carries the whole fixture
id now.

`check_playbook_tests()` was ordered by the database's own collation, which weighs a hyphen
last and so puts `webauthn` before `web-cache`; the case comparing the whole list builds its
expectation with Python's `sorted`, which does not. The query orders `COLLATE "C"` now, so the
two agree by definition rather than by luck.

### What moved in the ledger

Seventeen rows crossed from promised to built: eight `playbook:<name>` and nine
`reference:playbooks/<topic>/references/<file>.md`, now citing `tests/test_playbook.py`
instead of `ticket:52`. The report's last line reads `built 106 promised 65 retired 52`.

Resolving this ticket came due on 48's rule for the fourth time, and moved the same example
test 49, 50 and 51 moved. `test_a_row_that_names_an_open_migration_ticket_is_promised` had
been using `playbook:browser-framing` and `ticket:52`, which stopped being a promise here; it
uses `playbook:command-directory-injection` and `ticket:53` now.
