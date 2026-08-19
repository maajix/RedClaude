# 50 — Migrate authentication and Identity Playbooks

**What to build:** Deliver production-ready Playbooks and fixtures for the eight v1 topics concerning authentication, sessions, federation and identity lifecycle.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** resolved

**Deviation on criterion 6, the second half:** loadability and selection are met and tested;
"grounded positive and adversarial precision gates before stable promotion" is not, and it
cannot be met from this ticket for 49's reason. All eight ship `draft`. `stable` is
reachable only through `playbook_test_verdict` returning `pass` for the exact text, and an
evaluation run is an Agent run: the fixture listens on loopback, `scope.compile_policy`
refuses an inclusion naming a loopback address and `authorize_identity_egress_address`
refuses to dial one, so the work that would grade these eight has no route to the target.
Ticket 78 decided that route; ticket 84 grades the corpus over it. What did move is the
measurement: the corpus is now sixteen Playbooks and seventeen fixtures,
`playbook_fixture_binding` is total over the fixture table, and every one of the eight new
fixtures is an out-of-class negative for the fifteen Playbooks that do not output its class,
so the adversarial half of the arrangement exists and is waiting on the runner rather than
on authorship.

**Deviation on criterion 2, on the count of names:** the criterion lists seven things to
tell apart and the vocabulary holds six classes for them. "Federation trust" and "identity
parsing" both land on `authentication.federation_trust`, because ticket 18 named the class
for the trust decision rather than for the reader that implements it, and a leaf meaning
"this one was an XML parser" would be a technique recorded as a Property. The other five
map one to one. Eight Playbooks still carry eight distinct classes: the two the criterion
does not name -- `session_handling.fixation` for `oauth` and
`authorization.tenant_isolation` for `workload-identities` -- are the seventh and eighth.
The corpus distinguishes eight things; the criterion's list is seven names for six of them.

**Deviation on criterion 4, on the word "enumeration":** the four fixture cases the
criterion names are three cases and a non-case. Session handling has three pairs
(`cookie-scope-pair`, `lifetime-pair`, `fixation-pair`), token and identity confusion has
three (`token-scope-pair`, `federation-trust-pair`, `factor-enforcement-pair`), and redirect
trust is the delivery half of `fixation-pair`, whose `/oauth/authorize` redirects to a
callback the browser did not start. Enumeration has no positive here on purpose:
`credential-verification-pair` answers an unknown account and a wrong password with the
same `401`, because account enumeration is `information_disclosure.identifier_oracle` and
would be an undeclared second class on a pair that declares
`authentication.credential_verification`. A fixture holding both would score a run wrong
for reporting the one it found. That leaf gets its own pair when a Playbook outputs it.

**Deviation on criterion 4, half of it, inherited from 49:** every topic has its positive
fixture and every fixture is `out` for the fifteen Playbooks that do not output its class,
which is total by construction. What is thinner than "independently" implies is the
authorship: all eight fixtures and all eight Playbooks were written in one pass. The rule
`playbook_fixture_binding` enforces -- no author writes their own negative -- holds on the
axis it is about, since the negative set for any of them is the material written for the
other topics. It does not hold in the sense of two different people, and no schema can make
it.

- [x] Authentication, Cookies, Identity Lifecycle, Identity Parsing, JWT/JOSE, OAuth, WebAuthn and Workload Identities each exist as authored v2 Playbooks.
- [x] Playbooks distinguish credential verification, factor enforcement, federation trust, token scope, cookie scope, session lifecycle and identity parsing through controlled Property classes.
- [x] Identity-pairing, response-comparison and flow-mapping capabilities use proxy-side Identity labels without exposing target credentials.
- [x] Fixtures include positive, secure-control and out-of-class cases for enumeration, session handling, redirect trust and token/identity confusion.
- [x] Risk effects correctly park credential-changing, session-mutating or third-party-impact actions when grants are absent.
- [ ] All eight exact hashes pass loadability, selection, grounded positive and adversarial precision gates before stable promotion. **Partial:** loadability and selection hold at the shipped text; the graded halves wait on the route above. Ticket 78 built that route; ticket 84 grades the corpus over it.

## Comments

Implemented on 2026-08-16.

### Eight topics, eight leaves, and no new vocabulary

The eight v1 topics divided into eight Property classes that ticket 18 had already named,
which is the first thing this ticket can report and the one worth the most: 49 needed one
new leaf, and this one needed none. `authentication` claims
`authentication.credential_verification`, `webauthn` claims
`authentication.factor_enforcement`, `identity-parsing` claims
`authentication.federation_trust`, `cookies` claims `session_handling.cookie_scope`,
`identity-lifecycle` claims `session_handling.lifetime`, `oauth` claims
`session_handling.fixation`, `jwt-jose` claims `authorization.token_scope`, and
`workload-identities` claims `authorization.tenant_isolation`.

Three of those assignments are the ticket's actual judgement rather than a lookup.
`identity-parsing` is a v1 topic about XML and JSON readers, and the class it lands on is
about *trust*, not parsing: a document is signed by a party the application believes, and
the defect is that one reader verified a region while another read a different region. The
parser bug is the technique; federation trust is the claim, and a Playbook is a claim.
`oauth` lands on `fixation` rather than on anything named for the protocol, because what an
OAuth flow can go wrong at, in the way a report can state, is that a session exists in a
browser that never began the flow -- and that is what `session_handling.fixation` means
whether or not an issuer was involved. `workload-identities` lands on `tenant_isolation`
because a service credential's defect is which tenant it can speak for; finding a token in a
metadata service is `information_disclosure.artifact_exposure` and is somebody else's
reading.

### The v1 breadth went to the references, not to the outputs

Eight v1 pages came across as maintainer references hanging off four of the Playbooks:
authentication has four, oauth has two, identity-parsing and jwt-jose have one each. The
other four topics shipped a README in v1 and no reference text, so they have nothing
attached rather than a placeholder file. None of these pages reaches a projection --
`test_no_reference_text_reaches_a_shipped_projection` checks every line over forty
characters against every Playbook's canonical form -- and none of them is the source of a
class on its own. `type-juggling.md` is the exception that shows the rule: it is the only
one of authentication's four that names the defect the Playbook claims, and the other three
are context about where credential checks live.

### Two pairs told apart by method, and why that is the honest split

`cookies` and `identity-lifecycle` are both about a session cookie and both fire on
`cookie_parameter`. What separates them is `read_method` against `state_changing_method`,
which is not a trick to keep the selector happy: a scope claim needs a route that will
*use* the cookie so the reading is "this credential was honoured here", and a lifetime claim
needs the route that is supposed to end the session. The same shape appears in `jwt-jose`
against `workload-identities`: one wants an endpoint that already authenticates, the other
one whose authentication nobody has established, which is where a machine-to-machine route
sits before an Identity has been leased against it.

Criterion 5's parking is read off the same sixteen subjects. `select_playbooks` is asked
for the whole catalogue at a `constrained` ceiling, and the three Playbooks that ask for
approval -- `identity-parsing`, `oauth` and `webauthn`, which are the three that post to a
route that mints identity, drive a flow through an issuer, or change a factor on an account
-- come back carrying `risk_above_ceiling` rather than coming back selected or not coming
back at all. Parked rather than absent is the part worth testing: an operator can see what
a grant would buy. The criterion's third case, "third-party-impact", has no representation
in `EFFECTS` to park, which is why `identity-parsing` and `oauth` carry the third party in
their risk instead.

The technology branch of `subject_facts` changed shape while `tech_webauthn` was being
added to it. 049 wrote it as a `CASE` over `lower(t.name)` with a matching `IN` list
beneath, which spells every technology twice; adding one meant two edits where getting only
one of them right silently produces nothing. It is a join against a table of
`(name, fact)` pairs now, so each appears once and the join is what restricts the rows. The
atom literals are still in the view's definition text, which is what `fact_not_computed`
reads, and tickets 51 to 56 add a row each.

`tenant_boundary` is the one fact this ticket needed that no shipped Playbook had used. It
was already computed by `subject_facts` and already meant what `workload-identities` needs
it to mean -- the Program holds identities in at least two organisations -- so what changed
is only that a Playbook now reads it, and `PlaybookCorpusSelectionTest` had to arrange two
`service` Identities and two `member_of` edges for the fact to be true. Arranging that at
the Program rather than at the one subject is deliberate: the fact is then true of all
sixteen subjects and cannot be what tells `workload-identities` apart, so a loose trigger
list fails.

### One new atom, spelled out

`tech_webauthn` is the only surface fact this ticket adds, and the branch that computes it
is written as a literal `WHEN 'webauthn' THEN 'tech_webauthn'` rather than assembled with
`||`. That is 049's constraint and it is worth restating: `check_playbook_integrity`'s
`fact_not_computed` rule reads the view's definition text looking for the atom's name, so a
name built by concatenation would be invisible to the rule that exists to catch a Playbook
triggering on a fact nothing produces.

### The fixtures check the credential they are not grading

Not one of the eight will issue a session, a token or an assertion for material it did not
mint. The check is spelled three ways, because the eight are shaped three ways.
`cookie-scope-pair`, `lifetime-pair` and `factor-enforcement-pair` have a login and verify
email and password with `hmac.compare_digest` exactly as `credential-verification-pair`
does. `token-scope-pair`, `federation-trust-pair` and `tenant-isolation-pair` have no login
at all and verify an HMAC over the material instead -- the signature on a token, on an
assertion, on a tenant's bearer -- which refuses a forgery for the same reason.
`fixation-pair` is the fourth shape: its callback honours a code only if it is one the
issuer half minted, a membership test rather than a secret comparison, since there is no
secret in a code the fixture published in a redirect. That was the design catch of the
ticket: a fixture that let anybody log in would hold
`authentication.credential_verification` as well as the class it declares, the binding would
mark it `in` for the `authentication` Playbook, and a run that correctly reported the
undeclared class would be scored wrong for being right. `credential-verification-pair` is
the one whose login is the subject, and it is the only one whose login is allowed to be
weak.

Three of them serve both ends of a flow and say so in their own ground truth.
`federation-trust-pair` mints the signed assertion it later re-reads, `fixation-pair` plays
client and issuer, and `token-scope-pair` issues the tokens it grades. That is the fixture
standing in for an Identity slot: a run's material has to be something it was issued rather
than something it forged, and a pair that made the run forge a signature would be grading
key recovery instead of trust.

Two details are worth naming because they are what makes the pairs age well.
`token-scope-pair` computes `exp` as an offset from request time rather than a fixed
timestamp, so the "expired" token is expired next year for the same reason it is expired
today, and the fixture does not rot. `factor-enforcement-pair` models four bypasses of one
class rather than one -- omitted receipt, weaker factor's receipt, replayed receipt, and the
control of a receipt nobody issued -- because a fixture that modelled only the omitted case
would pass a Playbook that sends one variant, and this Playbook asks for four.

### Where a Playbook's material is allowed to come from

Four of the eight need bytes rather than an outcome: `jwt-jose` edits a token,
`identity-parsing` edits a signed assertion, `cookies` reads cookie attributes, and
`identity-lifecycle` replays a session across an ending. The first drafts had each of them
capture that material out of a leased Identity's exchange, which `use-identity` forbids
twice over -- section 3 seals a target's response headers and body bytes for an Identity
call, and section 2 keeps authentication fields out of request headers -- so the four have
one rule between them now.

Material comes from a route the run drove itself with no `identity_slot`: an issuance,
refresh or assertion endpoint the target answers for a caller who has leased nothing. That
is material the target published, and editing it is a statement about the target. Where the
only copy lives inside a slot, the reading is inconclusive and says which route would have
supplied one, which is `use-identity`'s own ending for a differential it could not run. The
eight fixtures already model exactly this: `GET /tokens`, `GET /internal/tokens` and
`GET /sso/assertion` are unauthenticated issuance routes, and the material each pair grades
is material the fixture handed out.

Two of the four did not need material at all once the question was put properly.
`identity-lifecycle` drives its probe through the slot, because a call through a slot is
already a request no browser took part in, which is the whole reading; its control became
the same request with no slot rather than a forged token of the same shape. `cookies` takes
its attributes from the browser mission's own cookie jar rather than from a `Set-Cookie` it
is not allowed to see, and its step 4 is a step inside that mission rather than a raw
exchange beside it, because `browser-evidence` withholds `mcp__rk2__http_request` while it
is loaded.

### What moved in the ledger

Sixteen rows crossed from promised to built: eight `playbook:<name>` and eight
`reference:playbooks/<topic>/references/<file>.md`, now citing `tests/test_playbook.py`
instead of `ticket:50`. The report's last line reads `built 80 promised 91 retired 52`.

Resolving this ticket also came due on 48's rule -- a registered migration ticket is open,
or it is resolved and no row still cites it -- and on the same test 49 had to re-point.
`test_a_row_that_names_an_open_migration_ticket_is_promised` had been using
`playbook:oauth` and `ticket:50` as its example of a promise, which stopped being one here;
it uses `playbook:api-authorization` and `ticket:51` now. That rotation is the ledger's
self-maintenance working as designed, and the next migration ticket will move it again.
