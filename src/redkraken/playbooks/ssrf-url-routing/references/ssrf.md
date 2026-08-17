# SSRF: the metadata endpoint, and the reason the reading never goes there

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The canonical page. Find a parameter that takes a URL -- a webhook, a preview, an
avatar import, a PDF source, an XML external entity, a health check. Point it
inward. The target list, in the order the page gave it:

* `169.254.169.254/latest/meta-data/iam/security-credentials/` on AWS, and the
  IMDSv2 token dance where v1 is disabled
* `metadata.google.internal/computeMetadata/v1/` with the `Metadata-Flavor`
  header, and the service-account token underneath it
* `169.254.169.254/metadata/instance?api-version=` on Azure
* `127.0.0.1` and `localhost` across a port list, to find the admin interface,
  the debug console, the unauthenticated Redis, the Elasticsearch with no auth
* `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` sweeps for internal services
* Kubernetes: the API server, the kubelet on 10250, the service account token

Then the filter bypasses: decimal and octal IP encodings, `[::]` and `[::1]`,
`0.0.0.0`, `127.1`, a DNS name that resolves to loopback, userinfo before the
real host, a `#` or `?` that a naive parser reads as part of the host, a redirect
from an allowed host, and DNS rebinding for the check-then-fetch race.

## Why the Playbook does not run it

**The credential is the point of the target list, and taking it is theft.** An
IAM role's temporary credentials, a GCP service-account token, a Kubernetes
service account -- every one of those is a live credential for the target's
infrastructure. A reading that fetches one has exfiltrated it into an Artifact,
a report and a bundle, and there is no version of that which is proportionate to
demonstrating that a URL parser was wrong.

**Port and range sweeps are network scanning through somebody else's host.** A
hundred requests to `127.0.0.1:<port>` is a port scan whose source address is the
target's own server, in its own logs, and it is the kind of automated activity
the rules of engagement in these Programs specifically exclude.

**What is reachable is not the Hypothesis.** The claim this class supports is
that the authority the route validated is not the authority it fetched. Two hosts
the Program controls prove that as completely as an internal service does. What
lies behind the target's boundary is a question about the target's network, and
it is one an operator authorises with the scope document in front of them.

**Internal services fail loudly.** A request to an unauthenticated Redis is a
command to Redis. A request to a kubelet is an API call. "Just fetching a URL"
stops being read-only the moment the URL names something that is not an HTTP
document server, and the sweep cannot know in advance which of the ports is
which.

**The bypass list is a fuzzing list.** Decimal IPs, octal IPs, `127.1`, `[::]`:
each entry exists to defeat a particular blocklist. The Playbook needs one
confusion that works, aimed at a host the Program owns, not a walk through
twenty aimed at loopback.

## What is kept

The parser-disagreement insight, which is the real content of the page and the
whole of the Playbook's step 3. Userinfo before the host, a backslash the
splitter and the fetcher read differently, prefix-versus-suffix allowlist
matching, and a redirect that the checker never sees -- these are descriptions of
how two pieces of code read one string, and they can be demonstrated entirely
against hosts the engagement controls.

Also kept: the page's list of *where* URL parameters hide, which step 1 uses --
previews, imports, webhooks, PDF sources, avatar fetches, health checks, and
proxy parameters.

## The trap in the whole technique

Blind is the normal case, and the page's answer to blind was to guess harder:
sweep more ports, time the responses, compare error strings. All of that is
inference about the target's network built from nothing, and it produces
confident reports about services nobody observed.

When the route returns nothing about what it fetched, this reading is over. The
question of whether a request left the process at all is `injection.request_forgery`
and `webhooks` asks it with a correlator, which is an arrival somebody can point
at rather than a timing difference somebody interpreted.
