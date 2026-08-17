---
description: An operational endpoint reachable on the application's own ingress and served twice from one source, one variant answering with the replica, namespace, node, image, run-as identity and peer address underneath the process and the other answering with a health verdict, beside a public build route and a route whose body counts requests.
bb:kind: own_pair
bb:classes: ["information_disclosure.workload_metadata"]
bb:subject: /healthz
bb:facts: ["read_method", "tech_orchestrator", "unknown_auth_endpoint"]
bb:identities: []
bb:provenance: Written for ticket 55 against the workload_metadata class description ticket 55 added, from what the class says rather than from any Playbook's steps; the public build route, the second operational route that answers with a verdict and the counting route are the precision controls.
---

# The answer meant for the platform, on the door meant for callers

`GET /healthz` exists because something underneath this application needs to know
whether the replica is alive. It was never meant for the caller in front, and on
this deployment it is on the same ingress as everything else, reachable with
nothing presented.

The two variants differ in what it answers:

* **vulnerable** answers with the workload: the replica name, the namespace,
  the node, the image and the registry it came from, the identity the process
  runs as, and the address of a peer.
* **secure** answers with a verdict, `{"status": "ok"}`, and nothing else.

Both bodies are byte-stable across repeated requests. There is a counter in this
fixture and it is deliberately not here: a subject that moved between two sends
would make every comparison a reading performs ambiguous, and the place to keep
a reading honest about that is a route of its own.

## What the two arms do here

Against **vulnerable**, one request holding nothing returns
`web-7d9f8c-4kq2p`, `acme-prod`, `ip-10-40-3-118`,
`registry.acme.internal/acme/web:2026.8.3`, `web-runner` and `10.40.3.22:8080`.
Every one
of those is a fact about the thing running the application rather than about the
application, and that is the whole class.

Against **secure**, the same request returns `{"status": "ok"}`, twice, byte for
byte. Nothing in it names a replica, a namespace, a node, an image, an identity
or an address. That is this class's refutation.

## The three precision controls, on both variants

`GET /version` answers `{"build": "2026.8.3", "commit": "a1b2c3d"}` on both
variants. It is public metadata -- the same string the application would print
in its own footer -- and it is the decoy for a reading that reports an
operational route answering as though answering were the finding.

`GET /readyz` answers `{"status": "ok"}` on both variants. It is a second
operational route, reachable by the same conventions, that carries nothing about
the workload: a reading that stops at the first name that answers, rather than
the first name that answers with a workload fact, gets it wrong here.

`GET /metrics/live` answers with a counter that increases on every request, on
both variants. A reading that skipped its baseline has a route it can be wrong
about.

## What the ground truth claims, and what it does not

`information_disclosure.workload_metadata` on `/healthz` of the vulnerable
variant, and nothing else anywhere.

Nothing here is a credential. `web-runner` is the name of a run-as identity and
not a token; no key, secret, password or bearer string appears on either
variant, so this fixture is not `information_disclosure.credential_material`
and a reading that reported one would be reporting something that is not there.
No route fails, and no body is a stack trace, an exception or a parser message,
so this is not `information_disclosure.error_detail`. Every route here is a
route the process answers rather than a file lying in a served tree, so this is
not `information_disclosure.artifact_exposure`. No address named in any body is
reachable from this fixture -- `10.40.3.22:8080` is a string, and there is
nothing behind it -- which is deliberate: a fixture that rewarded resolving what
it printed would be teaching a reading to leave the scope it was granted.
Nothing here writes, no identity is issued, and no response carries anybody's
data.
