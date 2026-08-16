---
description: A webhook registration that verifies the URL it is given and returns what the verification saw, served twice from one source, one variant reaching an internal address the caller named and the other refusing any host outside its allow list.
bb:kind: own_pair
bb:classes: ["injection.request_forgery"]
bb:subject: /webhooks
bb:facts: ["state_changing_method", "url_valued_parameter"]
bb:identities: []
bb:provenance: Written for ticket 49 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# A registration that fetches whatever it is told to

`POST /webhooks` with `{"url": ...}` registers a webhook and verifies it by
requesting it once, then returns what the verification saw. `DELETE
/webhooks/{id}` removes it, on both variants, so a run that writes has somewhere
to put it back.

The variants differ in one decision, taken before anything is fetched:

* **vulnerable** verifies whatever host the caller named, including
  `169.254.169.254` and a cluster-internal service, and returns the document
  that came back.
* **secure** answers `400` for any host outside its allow list, and never
  fetches.

An allowed host answers identically on both variants -- `201`, and a
verification that reports the connection was refused -- so the pair differs only
where the class says it should.

## The fetch is resolved in process

There is no socket. The "network" is a dict in `app.py` mapping two internal
hostnames to the documents they serve, and the vulnerable variant resolves the
caller's URL against it.

This is a deviation and it is deliberate. A fixture that really made outbound
requests would send traffic wherever a test pointed it, which is the behaviour
under study rather than something a test suite should do. What the class
requires is that the caller chooses the destination and learns the answer, and a
resolved map has both.

The consequence for whoever grades against this fixture: there is no
out-of-band channel here. A run cannot earn a callback observation from this
target, because nothing here calls back. What it can show is the response
differential -- an internal document returned to an anonymous caller on one
variant and a refusal on the other.

## What the ground truth claims

`injection.request_forgery` on the vulnerable variant, and nothing else.

The route is anonymous by design and carries no session at all, so
`authorization.*` and `session_handling.*` are not gaps in this file -- there is
no caller here to check anything against. The URL is parsed and compared, never
concatenated into a query, a template, a shell or a path on this host, so the
rest of the injection family against this fixture is a false positive. The
refusal bodies are fixed sentences and the identifiers are handed out rather
than guessed, so `information_disclosure.error_detail` and
`information_disclosure.identifier_oracle` are false positives too.

## This fixture mutates, and says so

Registering writes. The registry is in process and cleared when the process
starts, so a repeat never inherits the previous one's rows, and `DELETE` is
there because a Playbook that registers something should be able to remove it.
A run against this fixture is not a read-only run and a Playbook that describes
itself that way here has described its intention rather than its requests.
