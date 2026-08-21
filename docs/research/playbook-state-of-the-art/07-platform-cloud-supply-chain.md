# 07 - Platform, cloud and supply chain

Scope of this note: `supply-chain`, `kubernetes`, `deployment`, `secrets`,
`workload-identities`, `external-resources`, `cms`. Everything below is written
for an authorized engagement with a Program-defined scope, and every technique is
described so that a scope compiler can refuse the ones that leave it.

Research method note: the WebSearch budget for this session was exhausted partway
through, so most sources below were retrieved with direct fetches of primary
pages (blog posts, vendor documentation, repositories). Where a URL was surfaced
by search but the page itself was not fetched, the entry says so. One page,
`labs.cloudsecurityalliance.org/research/cloud-security-global-namespace-hijacking-systemic-risk-v1-c/`,
answered `403` and is not relied on.

## What we already cover well

* **Build metadata as a boundary leak.** `supply-chain` reads the shell for the
  bundles it actually loads, follows only the pointer the bundle itself writes,
  and sorts names into public / private / credential. The "the shell loads it"
  versus "the origin serves it" distinction is stronger than most published
  methodology, which reports a source map and stops.
* **A credential candidate is not a credential.** `secrets` requires a paired
  request with the credential omitted, and requires the four or five candidates
  that did nothing to appear in the report. That is exactly the control a triager
  needs to tell a finding from a regex hit.
* **Delegation inventory with integrity awareness.** `external-resources`
  enumerates what carries executable authority, excludes what a browser pins with
  `integrity`, and asks whether the reference is reached at all. Correct, and
  correctly offline.
* **Two programs, one path.** `deployment` isolates the single variable (the
  spelling) and demands a control transformation on an unrestricted path. Most
  public "403 bypass" content does neither.
* **Record-identifier matching.** `cms` insists the platform route return an
  identifier the application's own route served, instead of accepting "an
  endpoint answered".
* **Operational endpoints on the application's ingress.** `kubernetes` is the
  right small reading for `/metrics`, `/actuator`, `/debug/vars`, pod and image
  names leaking to the internet, and it measures the counter drift first.
* **Refusals that survive contact with a real engagement.** No publishing, no
  claiming, no desync, no version-to-CVE claims, no use of a working credential
  beyond the first proof, redaction at export. These are the parts that let this
  harness run against a live Program at all, and nothing below should weaken them.

## Missing techniques (ranked by expected yield on a real bounty program)

### 1. Dangling DNS on an in-scope hostname, read to the provider's fingerprint

A subdomain of the target still has a CNAME (or an A record to a released
address) pointing at a provider resource that no longer exists: an S3 bucket, an
Azure App Service or Front Door endpoint, a Netlify site, a Heroku app, a SaaS
tenant. Anybody who creates a resource with that name receives the target's
traffic, a valid TLS certificate, and cookies scoped to `*.target.com`. This is
still the highest-volume paid cloud finding in bounty programs, and the providers
themselves now publish the failure mode: AWS documents S3, CloudFront and Elastic
Beanstalk as the common dangling targets, and notes that its March 2026 account
regional namespaces for S3 do not apply to existing buckets and are not the
default. The whole finding is observable without claiming anything: the record
chain plus the provider's own "no such bucket / no such app / not found" body.
Playbook: **new playbook: `resource-takeover`** (companion to `external-resources`,
which names unclaimed origins but is structurally unable to check them).
Must observe: the DNS chain for an in-scope name (CNAME target, NXDOMAIN versus
answer), the HTTP status and body served for that Host, and a per-provider
fingerprint table with the claim path documented rather than exercised.
Sources: https://github.com/EdOverflow/can-i-take-over-xyz (community fingerprint
list, actively maintained); https://aws.amazon.com/blogs/security/threat-tactic-spotlight-subdomain-takeover/
(2026-06-16); https://learn.microsoft.com/en-us/azure/security/fundamentals/subdomain-takeover
(page date 2026-07-20).

### 2. Live credential triage at scale, with proof-of-existence instead of use

The credential that pays is rarely the one with an in-scope use site. It is an
AWS key, a Slack bot token, an npm or Artifactory token, a database URL, sitting
in a bundle, a workflow artifact, a container layer or a public commit. Volume is
not the constraint: 28.65 million new hardcoded secrets landed in public GitHub
commits in 2025 (+34% year over year), and roughly 70% of secrets confirmed valid
in 2022 were still valid in January 2025, still above 64% a year later. Our
`secrets` playbook stops at "no in-scope use site, route to operator", which is
where most of the money is. The industry answer to "prove it without using it" is
provider-side validation: GitHub's own secret scanning "may contact the secret's
issuing service to determine if the credential has been revoked", and the partner
programme reports the secret to the issuer for revocation. A bounty triager will
accept: the exact location and commit/artifact, the prefix and issuer, the
redacted value, and a statement that the reporter did not exercise it.
Playbook: **`secrets`** (extend the class beyond "document an SPA embedded"), with
a triage step that classifies issuer, blast radius by key type, and a
non-exercising proof path.
Sources: https://blog.gitguardian.com/the-state-of-secrets-sprawl-2026/ (2026-03-17);
https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning
(validity checks and partner alerts); https://github.com/trufflesecurity/trufflehog
(what "verified" means: an API call such as AWS `GetCallerIdentity`);
https://github.com/streaak/keyhacks (the minimal read-only call per provider, and
why each one is still traffic to a third party).

### 3. SSRF that reaches a metadata or container-credential endpoint, in its 2026 forms

`ssrf-url-routing` settles "the checker and the fetcher disagree" and explicitly
refuses metadata endpoints, so this harness can never state the impact that turns
a medium into a critical. The current shape of the technique is not "fetch
169.254.169.254": on AWS only 49% of EC2 instances enforced IMDSv2 as of the
October 2025 measurement (32% in 2024, and only 14% for instances older than two
years), so IMDSv1 is still reachable on roughly half the fleet; where IMDSv2 is
enforced, the attack needs `PUT` plus a token header, which a plain URL parameter
cannot do but a header-injection or full-request-control primitive can. ECS
delivers task-role credentials over plain `GET` at `169.254.170.2` with no token
header at all. GCP requires `Metadata-Flavor: Google`; Azure requires
`Metadata: true` and refuses any request carrying `X-Forwarded-For`. Those three
facts are the whole modern decision tree, and they are what decides whether an
SSRF is worth escalating.
Playbook: **`ssrf-url-routing`** (a graduated, credential-free reachability step)
or **new playbook: `cloud-metadata`**.
Must observe: whether the fetcher lets the caller control method and headers; a
differential between a link-local target and a control host that the reading
already knows the answer for; and a stop rule that reports reachability from a
non-credential path (instance id, metadata root listing) and never retrieves,
stores or replays a credential.
Sources: https://blog.christophetd.fr/imdsv2-enforcement/ (2024-03-28, updated
2025-01-08); https://www.datadoghq.com/state-of-cloud-security/ (October 2025
edition, IMDSv2 enforcement figures); https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html
(`169.254.170.2` credential endpoint); https://docs.cloud.google.com/compute/docs/metadata/querying-metadata
(`Metadata-Flavor: Google` mandatory); https://learn.microsoft.com/en-us/azure/virtual-machines/instance-metadata-service
(`Metadata: true` required, `X-Forwarded-For` refused).

### 4. Workflow injection reachable from a fork (pwn requests and expression injection)

If the Program scopes its GitHub organisation, the highest-severity finding
available is usually a workflow that runs attacker-influenced text in a
privileged context. `pull_request_target` runs with the base repository's token
and secrets; an unquoted `${{ github.head_ref }}` or PR title in a `run:` step is
shell injection with no fork approval needed. This is not historical: Orca
published fresh exploitable cases in Microsoft, Google and Nvidia repositories in
September 2025, and a December 2025 chain starting from `${{ github.head_ref }}`
in `angular/dev-infra` reached a bot token and then the repository's private key.
Every precondition is readable from public files: the trigger, the checkout ref,
`permissions:`, and whether previous fork PRs ran without approval.
Playbook: **new playbook: `ci-workflow-exposure`**.
Must observe: workflow YAML fetched as an artifact and parsed offline (trigger,
`runs-on`, `permissions`, `secrets: inherit`, unquoted expressions in `run:`), plus
run history metadata. The claim is the reachable sink, never a PR that fires it.
Sources: https://securitylab.github.com/resources/github-actions-preventing-pwn-requests/
(2021-08-03, still the canonical definition); https://orca.security/resources/blog/pull-request-nightmare-part-2-exploits/
(2025-09-30); https://adnanthekhan.com/posts/angular-compromise-through-dev-infra/
(2026-03-03); https://docs.github.com/en/actions/reference/security/secure-use
(GitHub's own untrusted-input and pinning guidance).

### 5. Abandoned storage the application itself still fetches from

A bundle, an installer, an update manifest or an IaC template names a bucket or
CDN origin that no longer exists. watchTowr re-registered about 150 such
abandoned S3 buckets for $420.85 and logged more than 8 million requests over two
months, for Windows/Linux/macOS binaries, VM images, CloudFormation templates and
SSL VPN configuration. The predictable-name variant is the same class from the
other side: AWS service buckets follow patterns such as `cf-templates-{hash}-{region}`
and `aws-glue-assets-{account-id}-{region}`, which Aqua showed could be claimed
ahead of the victim ("Bucket Monopoly", fixed by AWS by June 2024, but the naming
habit persists in customer tooling). Our `external-resources` reading already
produces the candidate list and then cannot check it.
Playbook: **`external-resources`** (the reachability half) and **`supply-chain`**
(names harvested from manifests, lockfiles and templates the target serves).
Must observe: for each referenced storage host, the status and body for a plain
`GET` (a provider "no such bucket" page versus content), and whether the
reference is reached at runtime.
Sources: https://labs.watchtowr.com/8-million-requests-later-we-made-the-solarwinds-supply-chain-attack-look-amateur/
(2025-02-04); https://www.aquasec.com/blog/bucket-monopoly-breaching-aws-accounts-through-shadow-resources/
(2024-08-09).

### 6. Public workflow artifacts and CI logs that carry tokens

Artifacts uploaded by public-repository workflows are downloadable by anyone for
up to 90 days, and they routinely contain a `.git/config` with the persisted
`GITHUB_TOKEN` (because `actions/checkout` persists credentials by default) or an
environment dump from a linter or crash reporter. Unit 42 named the pattern
ArtiPACKED; Praetorian turned a token found in a public debug artifact into a
supply-chain path against GitHub's own CodeQL, where the token was live for only
one to two seconds after upload. The exposure is the finding; the race is not
something a harness should run.
Playbook: **new playbook: `ci-workflow-exposure`** (or a `secrets` source type).
Must observe: the public artifact listing for a scoped repository, the archive
fetched and scanned offline for credential shapes and `.git/config`, and the
upload step in the workflow that produced it.
Sources: https://unit42.paloaltonetworks.com/github-repo-artifacts-leak-tokens/
(2024-08-13, Yaron Avital); https://www.praetorian.com/blog/codeqleaked-public-secrets-exposure-leads-to-supply-chain-attack-on-github-codeql/
(2025-03-26, John Stawinski).

### 7. Self-hosted runner exposure on a public repository

GitHub's own documentation says self-hosted runners "should almost never be used
for public repositories", because a fork PR can reach them and runners are
non-ephemeral by default. Praetorian reached TensorFlow's runners because
approval was only required for first-time contributors; Synacktiv documented the
same pattern with the passive indicators spelled out. All the preconditions are
public metadata: `runs-on: [self-hosted, ...]` in the YAML, repeated runner names
across jobs (non-ephemeral), "Cleaning the repository" in logs (shared workdir),
and fork PRs whose workflows ran without approval.
Playbook: **new playbook: `ci-workflow-exposure`**.
Must observe: workflow labels, job logs and run history, all read-only. No PR,
no job, no payload.
Sources: https://www.praetorian.com/blog/tensorflow-supply-chain-compromise-via-self-hosted-runner-attack/
(2024-01-15, Adnan Khan and John Stawinski); https://www.synacktiv.com/en/publications/github-actions-exploitation-self-hosted-runners
(2024-07-17, Hugo Vincent); https://docs.github.com/en/actions/reference/security/secure-use.

### 8. Presigned URL and SAS token over-scope

A signed storage URL in a bundle, an email template or a support article is a
bearer credential with a shape our `secrets` candidate list does not match: no
vendor prefix, just a long query string. Wiz's Microsoft AI case is the canonical
one: a SAS URL published on GitHub was scoped to the whole storage account with
full control rather than to one blob, exposing 38TB for about three years. The
modern read is: does the signature grant more than the object it appears to
share, and when does it expire. Determining "more" without reading another
tenant's data is a scoping question, not an exfiltration one.
Playbook: **`secrets`** (a signed-URL candidate class with its own control),
neighbouring `attack-surface`.
Must observe: query-string signature parameters (permissions, resource type,
expiry) parsed offline, and one bounded request that distinguishes
object-scoped from container-scoped without enumerating contents.
Sources: https://www.wiz.io/blog/38-terabytes-of-private-data-accidentally-exposed-by-microsoft-ai-researchers
(September 2023; URL surfaced by search, page not fetched in this session).

### 9. Public and writable object storage, including S3-compatible providers

Still paying, still common, and moving to new providers. Datadog's October 2025
measurement puts about 1% of S3 buckets as effectively public (down from 1.5%),
which on a large estate is still several buckets. The newer edge is
S3-compatible storage at smaller clouds: Wiz found providers whose buckets are
publicly listable through S3 ACLs, whose access keys have no recognisable prefix
(so secret scanners miss them), and one whose API returns the secret key on
demand rather than only at creation. The externally observable facts are listing,
readability, and whether an object can be overwritten (which must not be tested
by overwriting).
Playbook: **`attack-surface`** for the served-tree half, **`secrets`** for keys,
**new playbook: `resource-takeover`** for namespace questions.
Must observe: bucket host and name from the target's own bytes, the listing
response, and object readability with nothing presented.
Sources: https://www.datadoghq.com/state-of-cloud-security/ (October 2025);
https://www.wiz.io/blog/s3-clones-in-the-neoclouds (2026-07-31, Scott Piper).

### 10. Kubernetes control surfaces on a scoped host

Our `kubernetes` playbook only reads operational routes on the application's own
web ingress and refuses everything underneath. Where a Program scopes a host or
range rather than a URL, three surfaces are worth one read each. The API server
treats unauthenticated requests as `system:anonymous` in `system:unauthenticated`,
and anonymous access is enabled by default unless the authorization mode is
`AlwaysAllow` or `--anonymous-auth=false` is set (Kubernetes v1.34 makes the
per-endpoint anonymous configuration stable). The kubelet on 10250 answers
`/pods` and `/runningpods` to anonymous callers when misconfigured; Aqua found
287,000 kubelet APIs reachable from the internet, and of the exploitable ones, 15
of 27 returned ServiceAccount tokens. The ingress-nginx admission controller
(IngressNightmare, CVE-2025-1974, CVSS 9.8) is unauthenticated on the pod
network, and Wiz observed more than 6,500 clusters exposing it to the internet.
Playbook: **`kubernetes`** (a second reading, gated on a non-web scoped host).
Must observe: one unauthenticated `GET` per candidate (`/version`, `/api`,
`/pods`), the status, and whether the body describes cluster objects. Reading a
ServiceAccount token out of `/pods` is a stop-and-report, not a next step.
Sources: https://kubernetes.io/docs/reference/access-authn-authz/authentication/
(anonymous request defaults, v1.34 configurable authenticator);
https://www.aquasec.com/blog/kubernetes-exposed-exploiting-the-kubelet-api/
(2024-07-15, Michael Katchinskiy and Assaf Morag);
https://www.wiz.io/blog/ingress-nginx-kubernetes-vulnerabilities (2025-03-24);
https://kubernetes.io/blog/2025/03/24/ingress-nginx-cve-2025-1974/ (2025-03-24,
Tabitha Sable).

### 11. CI-to-cloud OIDC trust conditions

Federation replaced long-lived keys, and the misconfiguration moved into the
trust policy: a `sub` condition of `repo:org/*`, a condition on `pull_request`
refs, or a missing audience check lets a workflow that should not deploy mint
production credentials. GitHub now documents that repositories created after
15 July 2026 emit an immutable subject containing owner and repository IDs, which
exists precisely because name-based subjects could be matched again after an
organisation or repository was renamed; trust policies written against the old
form are the population worth reading. Datadog measures the adjacent problem:
12.2% of third-party integration roles are dangerously overprivileged, up from
10%.
Playbook: **`workload-identities`** (currently only tenant headers, which needs
two provisioned tenants and therefore almost never fires).
Must observe: the role ARN or workload identity pool named in a public workflow,
IaC or log; `permissions: id-token: write`; and the trust condition itself where
the Program publishes its IaC. Minting a token from a repository we control is
only in scope if the Program owns that repository.
Sources: https://docs.github.com/en/actions/concepts/security/openid-connect
(claims, immutable subject format for repositories created after 2026-07-15);
https://www.datadoghq.com/state-of-cloud-security/ (October 2025, integration role
privilege figures).

### 12. Registry namespace claimability: dependency confusion, repojacking, slopsquatting

Our `supply-chain` reading produces a list of internal package names and then
refuses to ask whether the public registry serves them, which is the difference
between "a manifest leaked names" (low) and "an unclaimed public name resolves
ahead of your internal one" (high). Three current variants: classic dependency
confusion on a private scope that is unregistered publicly; repojacking, where a
renamed or deleted GitHub namespace referenced by an install script or action can
be recreated (Aqua measured 2.95% of a 1.25M-name sample as vulnerable); and
slopsquatting, where LLM-suggested package names do not exist at all (19.7% of
recommended packages across 16 models, and 58% of hallucinated names recur across
runs, which is what makes them registrable targets). Existence is a `GET` that
answers `404`. Publishing is never part of it.
Playbook: **`supply-chain`** (rewrite the "does not touch a registry" ceiling into
a scope-gated existence read).
Must observe: for each private name, the public registry's response code only,
plus the old-namespace redirect state for GitHub references.
Sources: https://www.aquasec.com/blog/github-dataset-research-reveals-millions-potentially-vulnerable-to-repojacking/
(2023-06-21, Ilay Goldman and Yakir Kadkoda); https://socket.dev/blog/slopsquatting-how-ai-hallucinations-are-fueling-a-new-class-of-supply-chain-attacks
(2025-04-08, Sarah Gooding).

### 13. Container images the target publishes

Images are the leakiest artefact class we do not read at all. GitGuardian scanned
15 million Docker Hub images and 16 million layers and confirmed 100,000 valid
secrets, with 97% present only in layers rather than in the manifest, including
more than 7,000 valid AWS keys. If a Program scopes its registry namespace, the
finding is an image the target published whose layers carry a live credential;
the tag and digest already appear in the workload metadata our `kubernetes`
playbook reads.
Playbook: **`supply-chain`** (an image-artifact source) or the same new
`ci-workflow-exposure` file.
Must observe: image reference (registry, repository, tag or digest), manifest and
layer blobs fetched once, scanned offline. Nothing is pushed, tagged or deleted.
Sources: https://blog.gitguardian.com/fresh-from-the-docks-uncovering-100-000-valid-secrets-in-dockerhub/
(2025-05-15, Guillaume Valadon).

### 14. Unpinned mutable references, and manifest confusion

A workflow that references a third-party action by tag inherits whatever that tag
points at later: the March 2025 `tj-actions/changed-files` compromise moved tags
v1 through v45.0.7 to a commit that printed runner secrets into logs of some
23,000 repositories, and Wiz's guide records two further March 2026 cases
(a force-pushed action tag set and short-lived malicious package versions). GitHub
states that pinning to a full-length commit SHA "is currently the only way to use
an action as an immutable release". The registry-side sibling is manifest
confusion: npm publishes the manifest independently of the tarball and never
fully validates one against the other, so declared dependencies and scripts can
differ from what is installed.
Playbook: **new playbook: `ci-workflow-exposure`** for the pinning read;
**`supply-chain`** for the manifest/lockfile read.
Must observe: every third-party reference in a scoped workflow and whether it is a
tag, branch or SHA; and, for a published package of the target's, whether the
registry manifest matches the tarball's own `package.json`.
Sources: https://www.wiz.io/blog/github-actions-security-guide (2026-04-15,
lessons from tj-actions and the March 2026 incidents);
https://www.cisa.gov/news-events/alerts/2025/03/18/supply-chain-compromise-third-party-tj-actionschanged-files-cve-2025-30066-and-reviewdogaction
(2025-03-18; URL surfaced by search, page not fetched in this session);
https://www.vlt.io/blog/the-massive-hole-in-the-npm-ecosystem (2023-06-27, Darcy
Clarke; originally published at blog.vlt.sh, now redirected).

## What in our playbooks looks stale or weak

* **`supply-chain` stops one question short of the finding.** Reading only
  pointer-named source maps, with a hard refusal to ask any registry anything,
  means the output is always "here are some private names" and never "here is an
  unclaimed name your build will resolve". It also ignores the artefacts that
  carry today's leaks: lockfiles, SBOMs, IaC templates, workflow files, images.
* **`secrets` is scoped to the case that pays least.** "A document another
  document embeds, served by a single-page application" excludes commits,
  artifacts, container layers and CI logs. Requiring an in-scope use site excludes
  cloud and SaaS keys, which are the ones with real blast radius. The playbook
  currently routes its best inputs to an operator with no triage vocabulary
  attached.
* **`kubernetes` refuses the cluster so completely that it cannot describe one.**
  The refusal is right for a web-ingress Task, but there is no second reading for
  a Program that scopes a host or range, so an anonymous API server or an open
  kubelet is invisible to us by construction.
* **`workload-identities` fires almost never.** It needs the Program to hold
  identities in two tenants and to have provisioned a service credential. Modern
  workload identity is federated: the interesting artefact is a trust condition,
  not a tenant header.
* **`external-resources` names a class it cannot settle.** Step 4 admits the
  third question ("is the origin takeable") is unanswerable in that role, and no
  other playbook answers it either, so `injection.foreign_resource` reports stop
  at "unclaimed, probably".
* **`deployment` has no cloud edge in it.** It models "front end and application",
  which is right for path normalisation, but a modern edge also has an alternate
  domain claim, an origin reachable directly, and cache behaviour. The last of
  those is `web-cache`'s; the first two are nobody's.
* **`cms` is fine and slightly off-topic for this cluster.** Its shape (platform
  ships a second door) generalises well to platform consoles such as Argo CD,
  Jenkins or Grafana, but those belong to `attack-surface`, and nothing says so.
* **No playbook models a repository, a pipeline or a registry as a subject.**
  Every trigger vocabulary here is HTTP-surface shaped (`spa_surface`,
  `web_surface`, `tech_orchestrator`). Half of this cluster's yield lives behind a
  provider API, and there is no surface precondition that can express it.

## Concrete change proposals per playbook

* **`src/redkraken/playbooks/supply-chain/playbook.md`** - rewrite step 6's "It
  does not touch a registry" into a scope-gated step 6a: for each private name
  from step 3's second pile, one `GET` to the public registry recording only the
  status code, refused unless the scope compiler admits the registry host; keep
  the publishing refusal exactly as it is. Add a step 2b that reads lockfiles,
  SBOM documents and IaC templates the origin serves, and a step 3 pile for
  storage and registry hosts the manifest names, handing those to
  `resource-takeover`.
* **`src/redkraken/playbooks/kubernetes/playbook.md`** - add a step 7 alternative
  reading, gated on a Task whose subject is a scoped host rather than a web
  ingress: one unauthenticated `GET` each to the API server `/version` and `/api`,
  the kubelet `/pods` on 10250, and the read-only 10255 port, with a stop-and-
  report rule the moment a body contains a ServiceAccount token, and no second
  request to anything learned from those bodies.
* **`src/redkraken/playbooks/deployment/playbook.md`** - add a step that
  identifies the edge product from its own answer and asks the one cloud-edge
  question that is read-only: does the origin answer the same request directly
  when the Program scopes it, and does the edge accept an alternate domain it
  cannot prove ownership of. Leave the desync and TLS refusals untouched.
* **`src/redkraken/playbooks/secrets/playbook.md`** - rewrite step 2 to accept
  candidates from any stored artefact (commit, workflow artifact, container layer,
  CI log, signed URL), and add a step 3b "issuer triage" for candidates with no
  in-scope use site: classify issuer and blast radius, redact, report immediately
  for rotation, and state in the report that the credential was not exercised.
  Add signed storage URLs (SAS, presigned) as a candidate shape with their own
  scope-parsing control.
* **`src/redkraken/playbooks/workload-identities/playbook.md`** - add a step 0
  federation reading: where the Program scopes a repository or IaC, record the
  identity provider, audience and subject condition of each cloud role a pipeline
  assumes, and report a subject condition that admits more repositories, refs or
  events than the workflow needs. Keep the "never harvest a token" rule; minting a
  token is only allowed from a repository the Program owns.
* **`src/redkraken/playbooks/external-resources/playbook.md`** - rewrite step 4's
  third question so it hands off explicitly: emit the unresolved origin list as
  input to `resource-takeover` with the reference type and pin status attached,
  instead of ending the reading at "not answered here".
* **`src/redkraken/playbooks/cms/playbook.md`** - add one line to step 6's
  neighbours: where the second door is a platform console shipped beside the
  application (Argo CD, Jenkins, Grafana, a Kubernetes dashboard), the class is
  `information_disclosure.artifact_exposure` and the Playbook is `attack-surface`,
  so the reading does not silently expand into infrastructure.
* **New file `src/redkraken/playbooks/resource-takeover/playbook.md`** - one
  reading: resolve an in-scope name, follow the CNAME chain, fetch the provider's
  answer once, match it against a fingerprint table, and report the record plus
  the fingerprint. Claiming anything is refused in the ceiling, in the same voice
  as `external-resources` step 5.
* **New file `src/redkraken/playbooks/ci-workflow-exposure/playbook.md`** - one
  reading over a scoped repository's public metadata: workflow triggers and
  checkout refs, unquoted expressions in `run:` steps, `permissions` and
  `secrets: inherit`, `runs-on` labels and runner-name repetition, third-party
  action pinning, and the artifact listing. Entirely read-only: no pull request,
  no comment, no branch, no cache write, no dispatch.

## Scope and legality limits

Per technique, the asset each request actually touches, so the scope compiler can
refuse what the Program did not grant.

* **Dangling DNS fingerprint read** - the DNS query touches the target's zone; the
  HTTP request goes to a third-party provider's edge but carries the target's
  hostname. Usually acceptable under a wildcard-domain scope; refuse where the
  Program lists exact hosts only.
* **Abandoned bucket / CDN reference check** - the request goes to the provider's
  host (`*.s3.amazonaws.com`, a CDN edge) for a name the target published.
  Third-party infrastructure, target-owned name. Gate on the Program listing the
  storage host or accepting provider-hosted assets.
* **Metadata and container-credential reachability via SSRF** - every request goes
  to the target's own application; the metadata service lives inside the target's
  cloud account. In scope wherever the SSRF endpoint is, but retrieving or
  replaying a credential is out of bounds regardless of scope.
* **GitHub organisation reads (workflows, run history, artifacts)** - requests go
  to `api.github.com` and `github.com`, which are GitHub's assets; the data is the
  target's. Only in scope when the Program names the organisation or its
  repositories. GitHub's own infrastructure is never the subject.
* **Public registry existence checks (npm, PyPI, Maven, crates)** - the request is
  to the registry operator. Almost always outside a Program's scope; treat as
  refused unless the Program explicitly lists it.
* **Container registry pulls (Docker Hub, GHCR, ECR public)** - the registry is a
  third party, the image is the target's. In scope only when the Program names
  the registry namespace.
* **Credential validity checks at a vendor (AWS STS, Slack, Stripe, Google)** -
  the request is to the vendor, using a credential nobody granted us. Out of scope
  in effectively every Program, and this is the one place where common bounty
  practice and a defensible harness disagree. Report and let the issuer or the
  target validate.
* **Kubernetes API server, kubelet, etcd, dashboards** - the target's own assets,
  but on non-web ports. Refuse unless the Program's scope includes hosts or
  ranges and does not restrict itself to web and API ingress.
* **SaaS tenant claims (Zendesk, Statuspage, Heroku, Netlify, Azure resources)** -
  the resource belongs to the SaaS provider; only the name is the target's.
  Reading the "no such account" page is a read of the provider. Creating the
  tenant is an act against the provider and is never in scope.
* **Almost always out of scope, name them as refusals:** public package registries;
  GitHub, GitLab and CI providers as infrastructure; cloud provider control planes
  (AWS, Azure, GCP APIs, which run their own programmes and prohibit third-party
  testing); other customers' resources that happen to share a provider; any
  domain or namespace the target does not own; and anything reached by resolving
  an address found in a leaked document.

## Safety limits worth keeping

Every technique below would create or seize something in the real world. Each has
a proof-of-existence substitute that settles the same question.

* **Registering a dangling CNAME target** (S3 bucket, Azure App Service name,
  Netlify site, Heroku app, GitHub Pages repository). Substitute: the record
  chain, the provider's error body quoted, the provider's own documentation of
  the claim path cited. Note that `can-i-take-over-xyz` suggests claiming
  discreetly with a harmless file on a hidden path; that is the community norm and
  it is still an irreversible act against a third party, so the harness does not
  take it.
* **Registering a lapsed domain** named by a script tag or an email record.
  Substitute: the reference, its authority (script versus image), and the
  registration status as reported by WHOIS-style metadata, without buying it.
* **Publishing a package under an internal name** (dependency confusion).
  Substitute: the private name from the manifest plus the public registry's `404`,
  and nothing uploaded, reserved or scoped.
* **Claiming a renamed GitHub namespace** (repojacking). Substitute: the reference
  in the target's own code and the old namespace's current redirect or `404`.
* **Pre-creating predictably named service buckets** (Bucket Monopoly).
  Substitute: name the pattern and the regions it would apply to, from the
  target's own template, and create nothing.
* **Registering a hallucinated or typosquat package name** (slopsquatting).
  Substitute: report the non-existent dependency the target's code or docs
  reference.
* **Opening a pull request that triggers a workflow.** A branch name or PR title
  carrying an injection payload is the attack, not a proof. Substitute: the
  workflow file, the sink, and run history showing fork PRs ran unapproved.
* **Writing a GitHub Actions cache, uploading an artifact, dispatching a
  workflow, or pushing a tag or image.** All are writes into the target's build.
  Substitute: the misconfiguration read from public metadata; the escalation is
  described in prose and not performed.
* **Using a leaked credential beyond the single in-scope proof, and using it at
  the vendor at all.** Substitute: redacted value, issuer, location, and an
  immediate report so rotation can start.
* **Retrieving credentials from a metadata service through an SSRF.**
  Substitute: a non-credential metadata path that proves reachability, then stop.
* **Reading another tenant's data to prove a signed URL is over-scoped.**
  Substitute: the signature's own permission and resource parameters, parsed
  offline.
* **Claiming a SaaS tenant to prove a dangling record.** Substitute: the
  provider's "no such account" fingerprint.

## Sources consulted

Fetched and verified in this session unless noted.

* https://labs.watchtowr.com/8-million-requests-later-we-made-the-solarwinds-supply-chain-attack-look-amateur/ (2025-02-04) - scale and traffic profile of abandoned S3 buckets still referenced by installers, package managers and CI.
* https://www.aquasec.com/blog/bucket-monopoly-breaching-aws-accounts-through-shadow-resources/ (2024-08-09) - predictable AWS service bucket names, the Shadow Resource concept, AWS fix by June 2024.
* https://aws.amazon.com/blogs/security/threat-tactic-spotlight-subdomain-takeover/ (2026-06-16) - AWS's own description of dangling DNS to S3, CloudFront and Elastic Beanstalk, and the March 2026 S3 account regional namespaces with their limits.
* https://learn.microsoft.com/en-us/azure/security/fundamentals/subdomain-takeover (page date 2026-07-20) - Azure's affected service list, `asuid` domain verification, alias records, DNS name reservation windows.
* https://github.com/EdOverflow/can-i-take-over-xyz - the per-provider fingerprint corpus and the community's proof-of-concept norm.
* https://www.wiz.io/blog/ingress-nginx-kubernetes-vulnerabilities (2025-03-24) - IngressNightmare CVEs, unauthenticated admission controller, over 6,500 clusters exposing it publicly.
* https://kubernetes.io/blog/2025/03/24/ingress-nginx-cve-2025-1974/ (2025-03-24) - the project's own framing: pod-network reachability, no credentials needed, cluster-wide Secret access.
* https://www.aquasec.com/blog/kubernetes-exposed-exploiting-the-kubelet-api/ (2024-07-15) - kubelet `/pods` and `/runningpods` under anonymous access, 287,000 internet-reachable kubelets, ServiceAccount tokens returned.
* https://kubernetes.io/docs/reference/access-authn-authz/authentication/ - anonymous request defaults, `system:anonymous`, the v1.34 stable configurable anonymous authenticator.
* https://blog.christophetd.fr/imdsv2-enforcement/ (2024-03-28, updated 2025-01-08) - the IMDSv2 enforcement timeline and why region defaults do not eliminate IMDSv1.
* https://www.datadoghq.com/state-of-cloud-security/ (October 2025 edition) - IMDSv2 enforcement at 49%, public S3 at about 1%, long-lived keys, overprivileged third-party integration roles at 12.2%.
* https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html - the `169.254.170.2` container credentials endpoint and the iptables guidance for blocking IMDS from containers.
* https://docs.cloud.google.com/compute/docs/metadata/querying-metadata - `Metadata-Flavor: Google` is mandatory; recursive listing and OAuth token endpoints exist.
* https://learn.microsoft.com/en-us/azure/virtual-machines/instance-metadata-service - `Metadata: true` required, requests with `X-Forwarded-For` refused, proxies unsupported.
* https://securitylab.github.com/resources/github-actions-preventing-pwn-requests/ (2021-08-03) - the original definition of pwn requests and the safe two-workflow pattern; older, still the reference.
* https://orca.security/resources/blog/pull-request-nightmare-part-2-exploits/ (2025-09-30) - current exploitable `pull_request_target` cases and the public signals that reveal them.
* https://adnanthekhan.com/posts/angular-compromise-through-dev-infra/ (2026-03-03) - expression injection to cache poisoning to bot token to repository control, and how November 2025 cache changes affected the technique.
* https://www.praetorian.com/blog/tensorflow-supply-chain-compromise-via-self-hosted-runner-attack/ (2024-01-15) - self-hosted runner reachability from fork PRs, and the public metadata that showed it.
* https://www.synacktiv.com/en/publications/github-actions-exploitation-self-hosted-runners (2024-07-17) - passive indicators of non-ephemeral runners and the `.git/config` token exposure.
* https://unit42.paloaltonetworks.com/github-repo-artifacts-leak-tokens/ (2024-08-13) - ArtiPACKED: tokens in public workflow artifacts, 90-day download window.
* https://www.praetorian.com/blog/codeqleaked-public-secrets-exposure-leads-to-supply-chain-attack-on-github-codeql/ (2025-03-26) - a token in a public debug artifact, valid for one to two seconds, and a deliberately bounded proof.
* https://www.wiz.io/blog/github-actions-security-guide (2026-04-15) - consolidated list of externally observable Actions misconfigurations and the March 2025 and March 2026 incidents.
* https://docs.github.com/en/actions/reference/security/secure-use - GitHub's own guidance: untrusted inputs, SHA pinning as the only immutable reference, self-hosted runners not for public repositories.
* https://docs.github.com/en/actions/concepts/security/openid-connect - OIDC claims and the immutable subject format for repositories created after 2026-07-15.
* https://www.cisa.gov/news-events/alerts/2025/03/18/supply-chain-compromise-third-party-tj-actionschanged-files-cve-2025-30066-and-reviewdogaction (2025-03-18) - the tj-actions tag-moving compromise; URL surfaced by search, page not fetched here.
* https://www.vlt.io/blog/the-massive-hole-in-the-npm-ecosystem (2023-06-27) - manifest confusion: npm manifests are published independently of tarballs and never fully validated against them.
* https://www.aquasec.com/blog/github-dataset-research-reveals-millions-potentially-vulnerable-to-repojacking/ (2023-06-21) - repojacking mechanics and the 2.95% measured rate; older but still landing wherever install scripts reference GitHub by name.
* https://socket.dev/blog/slopsquatting-how-ai-hallucinations-are-fueling-a-new-class-of-supply-chain-attacks (2025-04-08) - hallucinated package names: 19.7% of recommendations, 58% recurring across runs.
* https://blog.gitguardian.com/the-state-of-secrets-sprawl-2026/ (2026-03-17) - 28.65M new public-commit secrets in 2025, validity persistence above 64%, 28% of incidents outside code repositories.
* https://blog.gitguardian.com/fresh-from-the-docks-uncovering-100-000-valid-secrets-in-dockerhub/ (2025-05-15) - 15M images scanned, 100,000 valid secrets, 97% present only in layers.
* https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning - validity checks contact the issuing service; partner alerts route secrets to issuers for revocation. The model for proving a key exists without a tester using it.
* https://github.com/trufflesecurity/trufflehog - what "verified" means in practice and the AWS `GetCallerIdentity` example.
* https://github.com/streaak/keyhacks - the minimal read-only validation call per provider; useful as a taxonomy of issuers, not as an authorization to send those calls.
* https://www.wiz.io/blog/s3-clones-in-the-neoclouds (2026-07-31) - S3-compatible providers: publicly listable buckets, unrecognisable key formats, secret keys retrievable from the API.
* https://www.wiz.io/blog/38-terabytes-of-private-data-accidentally-exposed-by-microsoft-ai-researchers (September 2023) - over-scoped SAS URL with full control; URL surfaced by search, page not fetched here.
* https://owasp.org/www-project-top-10-ci-cd-security-risks/ (v1.0, October 2022) - the canonical CI/CD risk vocabulary: PPE (CICD-SEC-4), dependency chain abuse (SEC-3), credential hygiene (SEC-6), artifact integrity (SEC-9). Older, still the framework triagers recognise.
* https://securitylabs.datadoghq.com/articles/npm-worm-compromises-popular-npm-packages/ (2026-08-04) - current npm worm behaviour: credential harvesting from CI runners, cloud APIs and Kubernetes secrets, exfiltration via public repositories. Context for why a leaked CI token must be reported immediately.
* https://securitylabs.datadoghq.com/articles/coordinated-github-api-enumeration/ (2026-07-08) - coordinated abuse of stolen GitHub tokens, and the detection signals a defender has.
* https://labs.cloudsecurityalliance.org/research/cloud-security-global-namespace-hijacking-systemic-risk-v1-c/ - returned HTTP 403 and could not be read; no claim in this note depends on it.
