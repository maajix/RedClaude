# 55 — Migrate platform and supply-chain Playbooks

**What to build:** Deliver production-ready Playbooks and fixtures for five v1 topics that reason about deployed platforms, orchestration, logging and dependency boundaries.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** resolved

**Deviation on criterion 1:** three of the five ship no `playbook_references` rows at all. `cms`
carries three and `deployment` two, which is where v1 put its attachments; `kubernetes`, `logging`
and `supply-chain` had v1 pages that were advice rather than material, and the advice is precisely
what each Playbook's ceiling refuses. Attaching a page whose instructions the Playbook contradicts
would make the attribution misleading rather than attributable. What carries the attribution for
all five instead is `bb:provenance`, which names the v1 page each one replaces and says what was
refused; the expiry half of the criterion is `bb:stale_after`, which all five carry.

**Deviation on criterion 6, inherited from 49, 50, 51, 52, 53 and 54:** the positive and
adversarial arrangement exists and is total; the evaluation that would grade it has not run, and
cannot run from this ticket. All five ship `draft`. `stable` is reachable only through
`playbook_test_verdict` returning `pass` for the exact text, and an evaluation run is an Agent
run against a fixture listening on loopback, which `scope.compile_policy` and
`authorize_identity_egress_address` both refuse. Ticket 78 is where that route is decided.
What moved is the measurement: the corpus is forty-seven Playbooks and forty-eight fixtures,
`playbook_fixture_binding` is still total over the fixture table, and each of the five new
fixtures is an out-of-class negative for the forty-six Playbooks that do not output its class.
The half of the criterion that is about selection is checked and holds:
`PlaybookCorpusSelectionTest` is diagonal across all forty-seven subjects, and every one of the
five is loadable by exactly one production role.

- [x] CMS, Deployment, Kubernetes, Logging and Supply Chain each exist as authored v2 Playbooks with attributable source references and expiry.
- [x] Version or technology fingerprints create hypotheses only and can never confirm applicability or impact without exact configuration and Test evidence.
- [x] Kubernetes and deployment checks remain limited to explicitly scoped web/API ingress and do not expand into infrastructure discovery.
- [x] Logging and supply-chain fixtures distinguish public metadata from credential/artifact exposure and runtime reachability.
- [x] Stale upstream knowledge or expired verification prevents stable selection until reevaluated.
- [ ] All five exact hashes pass role loadability, matching selection and positive/adversarial fixture promotion gates. **Partial:** loadability and selection hold at the shipped text; the promotion gates wait on the route above. Ticket 78 closes it.

## Comments

Implemented on 2026-08-17.

### Ten v1 pages, five readings

v1 filed this material by product: a three-page CMS pack, a two-page deployment pack, and three
single pages about clusters, logs and dependencies. A reading is none of those. What these five
share is that each is selected by a FINGERPRINT -- the recon pass named a platform, a proxy, an
orchestrator, a telemetry service, a bundler -- and a fingerprint is the weakest evidence in this
system. So each of the five is built around what its fingerprint bought and what it did not.

`cms` absorbs the three platform pages and `deployment` the two server pages. `kubernetes`,
`logging` and `supply-chain` are rewritten with nothing attached: all three v1 pages were advice
rather than material, and the advice -- enumerate the cluster, forge a log line, publish a
package under a private name -- is exactly what the Playbook refuses.

One of the two notes under `deployment` describes work it refuses outright.
`http-attacks-tls-attacks.md` is a transport audit, its subject is the `transport` family 018
named, and 018 records that no transport claim can be settled through the scope proxy at all. It
is attached where v1's pack put it, because the ledger records where a v1 page went rather than
where its subject is graded, and the note says so in its own text.

### Criterion 2 is already in the schema, and the documents restate it

018 records `technology_identified` with `is_evidential = false`, so a fingerprint cannot appear
on a Hypothesis transition however badly a reading wants it to. The migration does not have to
add anything for criterion 2; what the five documents add is the discipline above the schema.
Each names, in its own step 1, what the fingerprint bought -- which route conventions exist as
names, which normalisation rules are worth trying, which manifest paths a builder tends to write
-- and each says in its ceiling that a version, an image tag, a namespace or a package version
is a fingerprint and never a claim. `supply-chain` says it as a sentence its output may not
contain: "package X is at version Y, which is vulnerable to".

### Five new leaves, and why each one is a leaf

None of the five lands on a leaf 018 already named.

`authorization.parallel_route` is two routes over one store where the check lives on only one of
them. 018's `function_access` is one route and a caller who is wrong for it; here both routes
were meant to be published and the defect is which side of the store the check sits on.

`authorization.edge_rule` is further from `function_access` still: nothing in it is about
identity. The same anonymous caller sends the same path twice, spelled two ways, and two hops
normalise it differently.

`information_disclosure.workload_metadata` is neither `error_detail` nor `artifact_exposure`.
The route succeeded and was meant to answer; what it returned describes the platform underneath
rather than the application.

`information_disclosure.log_record` is the third thing in the `excess_field` neighbourhood after
054's `undeclared_field`, and the only one about a second caller. The fields are ones the view is
supposed to carry; the defect is whose requests are in it.

`information_disclosure.dependency_manifest` is the third thing in the `artifact_exposure`
neighbourhood after 054's `credential_material`. The manifest was published on purpose and holds
no credential; what should not be in it is a list of names describing a private dependency
boundary. The test is "does the public already have this name", which neither neighbour can ask.

### What tells the five apart on the Surface

Five new facts, all of them technology families, all `application` scope: `tech_cms`,
`tech_edge_proxy`, `tech_orchestrator`, `tech_telemetry` and `tech_build_manifest`, each mapping
several fingerprint names onto one fact for the reason `tech_cdn` does. That is unusual for this
corpus -- most facts say what a route takes -- and it is what these readings are: the second door
belongs to the platform, and the recon pass found it by naming the platform.

`tech_edge_proxy` and `tech_cdn` stay separate and `varnish` stays with the CDN. `web-cache` asks
what a cache stored and handed to the next caller; `deployment` asks whether two hops disagree
about what a path spells. A target can have either without the other.

The rest of each triple is what keeps the five off each other and off their neighbours. `cms` and
`logging` are authenticated reads separated by which platform is under them, and
`information-disclosure` -- the other authenticated no-parameter read -- is separated from both by
`tech_openapi`. `kubernetes` and `supply-chain` both hold nothing: `attack-surface` needs
`unauthenticated_endpoint`, which is a positive answer rather than the unknown `kubernetes` keys
on, and `secrets` needs `embedded_document`, which a bundle's `sourceMappingURL` comment is not.
`deployment` is the only `web_surface` reading here.

### Criterion 4, and the two fixtures built around it

`log-record-pair` serves four things from one view: metadata the application publishes to
everybody -- a build string and a region -- which is in both variants and is not a finding;
request records belonging to a second caller, which is the class and is in one variant only; the
name of an archive the view points at, which answers `404` on both, so a reading that claims the
archive is exposed has claimed something it never observed; and a credential-shaped string in the
reading Identity's own seeded entry, in both variants, honoured by no route here.

`dependency-manifest-pair` does the same over four piles: package names the public registry
already serves, in both maps; two scoped packages and an internal registry host, in one map only;
`/static/legacy.js`, a bundle the origin serves that the shell never embeds; and the same
credential-shaped string, in the comment that opens the bundle both variants serve. The third is
the runtime-reachability control, and step 4 of the Playbook is where it is spent -- the reading
has to say whether the code a manifest describes is demonstrably running or merely published, and
never collapse the second into the first.

The fourth pile in each is the credential half of the criterion, and it is a control rather than a
class because of where it sits: `rk_sample_000000000000` is identical on both variants of both
fixtures, so it can never be the difference either pair grades, and nothing in either fixture
honours it. 054 defines `information_disclosure.credential_material` as a credential the target
HONOURS, which is what keeps `credential-material-pair` the only target for that class while
still giving a reading somewhere to be wrong about the distinction criterion 4 names. A log entry
carrying a token that worked, or a `sourcesContent` with a live key in it, would make two targets
answer one question and 036's binding would grade both Playbooks on both.

### Criterion 3, and why it is a property of the fixtures as much as the documents

`kubernetes` step 6 and `deployment` step 7 both say it: every address, namespace, peer, node,
image or upstream name a body carries is something to name in the finding and nothing to send a
request to. `kubernetes` sends five requests and `deployment` eight, all to the Program's own
ingress.

The fixtures make that checkable rather than promised. `edge-rule-pair` runs its front end and
its application in one handler on one origin, so there is no infrastructure to wander off to.
`workload-metadata-pair` answers with a pod name, a namespace, a node, an image and a peer
address, and serves nothing at any of them -- a reading that resolves what it read finds a `404`
and has learned that the discipline was the point.

### Criterion 5 is already enforced, by two migrations

`stale_after` on all five is `2027-05-15`, later than 054's. 023's selector emits the selection
reason `expired` past that date and 024 requires re-evaluation before a Playbook can be stable
through it. That makes criterion 5 structural rather than advisory: these five are the readings
whose upstream knowledge rots fastest -- a platform's route conventions, a proxy's normalisation
rules, an orchestrator's endpoint names -- and none of them can be stably selected past its date
until somebody looks again.

### Evidence, and the two Playbooks that difference nothing

Two refute with a `response_invariant` and three with a `content_match`. `cms` and `deployment`
send a second request differing in one thing -- the session dropped, the path spelled another way
-- so their refutation is that request answering exactly as the first did. The other three read a
body and ask what is in it, so their refutation is a match over the Artifact finding nothing from
the list the document names; a `response_invariant` there would be a claim about an arm that was
never sent.

`supply-chain` is the only Playbook in the ticket without `compare-responses`. Its skills are
`analyse-source` and `handle-untrusted-content`, which is what it does: parse a shell for what it
loads, follow a pointer a bundle wrote, sort names out of a manifest. That also makes it the only
one `js_analyst` can load; the other four are `web_hunter`'s.

`deployment` carries `compare-responses` alone. It presents no identity and reads status lines
rather than documents, so a skill for either would be a claim about work it does not do.
