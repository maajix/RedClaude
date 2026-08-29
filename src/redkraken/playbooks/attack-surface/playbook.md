---
description: Ask whether a document the application never meant to publish is reachable, by requesting candidate artifact paths and differencing each answer against a path that certainly does not exist.
bb:category: information_disclosure
bb:outputs: ["information_disclosure.artifact_exposure"]
bb:triggers_all: ["read_method", "unauthenticated_endpoint"]
bb:skills: ["enumerate-surface", "handle-untrusted-content"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-02-15
bb:provenance: Written for ticket 49 as the v2 replacement for v1's attack-surface pack, against the artifact-exposure leaf of the ticket 18 vocabulary; the three v1 texts are attached as maintainer references and none of them is the source of this class. Rewritten for ticket 101 against the merged ledger, which carries eleven readings, one lead and seven refusals for this slug. No frontmatter key moved, because all three evidence rows already name response_differential and so the refuted row is reachable as written.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["auto-scanners.md", "cves.md", "ffuf.md"]
---

# Ask whether the server is serving something it does not know it is serving

The subject is a route anyone can reach with a GET, and the question is whether
the same server also hands out a build artifact, a backup, a configuration file
or a listing published by accident. The answer is never "the path returned 200":
it is the difference between that and what a path nobody deployed returns.

Every reading below is one Test, sent with `mcp__rk2__http_request` and filed as
one specification with `mcp__rk2__propose_test`, the only verb that makes a Test
exist. rk2_test_spec_problem refuses a specification performing fewer than three
actions or leaving out the baseline, variant or control role, and the one that
settles a claim carries the difference in its own assertions, because
close_test_replay derives the settling transition from those alone; body_differs
and body_equals compare the stored response body digest and nothing else.

## 1. Calibrate the negative answer, per branch

Request a certainly-absent path under the branch through
`mcp__rk2__http_request`, then a second of the same shape, then the same name
with the candidates' extension, then again with each `method` the candidates
will use. The negative answer moves per directory, per extension and per method,
and a soft error page answers 200. Two certainly-absent answers that differ mean
the not-found page varies, and that branch ends inconclusive. No differencing
assertion names these actions, so close_test_replay writes response_invariant
for each, which is what licenses every differential below. This section closes
no Test and grades nothing.

## 2. Read what the deployment already shipped, offline

Run `js_routes`, `js_parse` and `js_map` over the stored bundle with
`mcp__rk2__run_tool`, and `jq` over any structured document it fetched. The
writer is promote_proposal: a route table or referenced origin as
endpoint_discovered, a recovered parameter name as parameter_discovered, both
non-evidential, and a claim about what the bundle contains as content_match,
whose provenance is a tool run alone. Nothing is sent, so what this section
produces is a proposal and it grades nothing.

## 3. Paths and routes the deployment already names

Request each derived candidate once through `mcp__rk2__http_request` with the
calibration's `method` and `headers`: a tilde or backup suffix on a served file,
a source map beside a bundle, a version-control metadata file, and the routes
robots.txt, the sitemap or a recovered route table names and nothing links.

Three controls decide whether any of it counts: the same suffixes on a filename
that does not exist, showing a hit follows the real file rather than the suffix;
a nonce appended to the source-map name, which must return the calibration
digest; and a fabricated route in no declaration, which must answer as the
calibration does. The baseline is a linked route of the same shape. Each
candidate is its own action, and each differencing assertion names that
candidate's own control on the `against` side: `body_differs` on a derived path
against the suffixed name that does not exist, `status_differs` on a
declared-only route against the fabricated one, so `close_test_replay` writes a
differential for the control as well. The Identity is held constant, because an
action names none and one replay run holds one slot for its length, and a
declared-only route answering exactly as a linked one is path disclosure rather
than access.

## 4. Services that will name their own contents

Two readings, each its own Test, and each needs the Program's scope to cover the
service itself rather than the application consuming it. A container registry:
the version handshake twice as the baseline, the repository catalogue as the
variant, a random repository name as the control, which must answer
name-unknown. An object store the application's own asset URLs name: one of
those asset keys the store demonstrably serves, sent twice, as the baseline, the
listing routes as the variant, and a 32-character random key as the control,
which must answer no-such-key rather than access-denied.

`status_differs` between the catalogue and its control is what
`close_test_replay` closes. Calling the document a catalogue or a listing is a
`content_match` filed by `promote_proposal`, off a `jq` run or off a browse
capture where the document is XML -- a browse run is itself a tool run and
satisfies that provenance. One tag list only: no manifest, no layer, no push.

## 5. Hosts and names, and whether the server tells them apart

Send each candidate host as its own `url` authority through
`mcp__rk2__http_request`: the apex or known application host as baseline, a host
generated from the observed naming scheme and a host taken from a build-variable
literal the bundle published as variants, and a 16-character random name under
the same domain as the control.

A candidate answering as that control is the wildcard rather than an
application, and a vendor CDN the bundle names is a second control separating
undeclared surface from a third party. `record_test_action` compares the host
directly, so the difference rides the request line. The same shape reads a name
space: a name the application itself links as baseline, a high-entropy name of
the same shape and length as control, and a short declared candidate set drawn
from the target's own words as variants. `body_differs` on a host and
`status_differs` on a name are what `close_test_replay` closes. The Property the
name pair would support is `information_disclosure.identifier_oracle`, which
`exceptional-conditions` emits since ticket 101, so hand that verdict there and
file this Playbook's own class here. Stop at the first discriminating name.

## 6. The bounce, and referenced origins that no longer answer

The bounce reading needs a Task leasing no Identity, because a leased Identity
owns Cookie and every header it declares for the origin, so a Task holding one
has no logged-out state to read. This Task performs the half its own lease
admits and the other leaves as a `suggested_tasks` entry on
`mcp__rk2__submit_mission_result`; nothing re-leases a Task in flight. Action
one requests a path needing no session and answers 200 with no redirect, action
two a known post-login path answering the bounce, and the control a second
public path of the same shape. status_differs naming the bounce against that
control is what close_test_replay closes, so the control carries a differential
too, and because no assertion kind is header-shaped the return-target parameter
the redirect names stays a parameter_discovered surface fact. The referenced
third-party origins from section 2 are the second reading: a referenced URL the
page uses successfully as baseline, the remaining answering origins as variants,
and as control a path that same live host certainly does not serve, so every arm
produces a Receipt. A control that does not resolve produces none, leaves its
assertion unevaluated and makes the run inconclusive, so a referenced host that
no longer answers is sent once outside the Test and stops at an agent-filed
error_detail through promote_proposal. The answering arms close on body_differs
against that control, and the class the read half would support,
`injection.unclaimed_reference`, is emitted by no Playbook and handed on;
claiming the dead resource is refused outright.

## 7. One lead, which sends nothing

Inventory which DOM source-to-sink pairs the served scripts contain by running
`js_parse` over the stored bundle with `mcp__rk2__run_tool`, against a control
sink whose argument is a literal: tracing that marks that one caller-controlled
cannot tell constants from input, and the inventory is not readable.

This is a lead. Nothing is sent, so there is no Test to close and no Finding to
reach: `promote_proposal` files it as `content_match`, an edge no writer carries
to supported, and it selects what the browse-lane and injection Playbooks may
try.

## 8. Read a differing body, then propose the claim

Follow `handle-untrusted-content` before quoting anything out of a differing
Artifact: a version-control configuration file, a heap dump and a long error
page all differ from the calibration, and only the first two are the class.
Identification is a tool run and never a reading; promote_proposal files it as
content_match and the run's output is the citation. Then propose the claim with
`mcp__rk2__propose_finding`, naming directory_listing as its
`vulnerability_class`: that argument takes a vulnerability_classes id, not a
dotted Property class, and property_class_vulnerability_classes maps this
Playbook's class to that id. The gate is rk2_finding_refusal, which opens
nothing without the transition close_test_replay wrote. The claim is supported
when a candidate differs from the calibration and its body matches a declared
pattern for an artifact of that kind, refuted when the candidate is invariant
against it. A 403 says something is there, not what, and is inconclusive. This
section proposes no Test of its own and grades nothing.

## 9. Where a reading halts, and what is refused

Two halts are a person's decision, asked for with `mcp__rk2__park_for_human`
carrying this Task's `task_label` and the `question_code` that names why. A
candidate host answering with an application the scope document does not clearly
admit parks under scope_ambiguous, before anything further is sent to it; a body
that turns out to be a credential store or third-party personal data parks under
third_party_impact, after reading stops where it was identified. The writer is
park_task_for_human. Everything else halts by running out -- a listing returned,
a catalogue answered, the first discriminating name found -- and no question
code says that, so those are reported through the Task's record.

A generic wordlist sweep is refused by corpus decision and not by capability:
the objection is volume and what a 200 is worth. Four readings are blocked by
construction. Virtual-host enumeration, because a stated Host is hop-by-hop and
the door rebuilds the wire headers from the url's own authority. Name
resolution, because no resolver exists. Query-building source inside a served
JVM artifact, because no bytecode reader exists. WebSocket handshake
fingerprinting, because the upgrade headers are dropped and any rejection read
is the plain-HTTP wording. Two are out of scope by subject: a version banner is
readable and `technology_identified` is writable, but that kind is
non-evidential and no leaf supports "the version is old"; and third-party
reconnaissance oracles put a third party in the subject position.

This section performs and grades nothing. 5 of 9 steps cannot be graded.
