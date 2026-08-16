---
description: A dashboard behind a session with a cache in front of it, served twice from one source, one variant keying the cache on the address alone so one caller receives another's stored page and the other keying it on the session as well.
bb:kind: own_pair
bb:classes: ["information_disclosure.cached_response"]
bb:subject: /dashboard
bb:facts: ["read_method", "tech_cdn", "web_surface"]
bb:identities: ["alice", "bob"]
bb:provenance: Written for ticket 52 against the class description ticket 52 added, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# The right page, stored under the wrong name

`POST /session` issues a session cookie for `alice` or for `bob`. `GET /dashboard`
renders that caller's name, balance and next invoice. In front of it is a cache
with a sixty-second lifetime, which both variants publish through `X-Cache` and
`Age` so a run can tell a stored answer from a fresh one without timing it.

The difference is the key:

* **vulnerable** keys on the method and the address, so whoever asks second
  receives whatever was stored first, and `Cache-Control: public` invites
  anything else in the path to do the same.
* **secure** keys on the session as well, and says so with `Cache-Control:
  private` and `Vary: Cookie`.

The cache is a dict in this process rather than a front end somebody deployed.
What the class is about is the key, and a key is the same wrong shape whoever
holds it.

## What the ground truth claims, and what it does not

`information_disclosure.cached_response` on the vulnerable variant, and nothing
else.

The render is correct on both halves. `DASHBOARDS[caller]` is looked up by who
signed in, there is no identifier to substitute, and neither variant will render
`bob` for a request that named `alice`. What crosses is the stored copy, which is
why this is not `authorization.object_ownership` and not
`authorization.tenant_isolation`.

The session is checked before the cache is consulted, on both halves, and the
`401` is never stored. That order is the pair's other guard: a cache that answered
a caller carrying no session at all would put a missing authentication check into
the same fixture, and the disclosure graded here is the one between two callers
who both signed in.

Two accounts, because one cannot show this. A run that logs in as `alice`, reads
the dashboard twice and reports the second read as a hit has observed a cache
working. The finding is `bob` reading `alice`'s page, and it needs both.

`Cache-Control` differs between the halves and that is not a second class. It is
the same decision written down: a response keyed on the address alone is a
response that may be shared, and the vulnerable variant says so honestly. Grading
the header instead of the behaviour would be `transport.header_policy`, which is
a different pair.

Nothing here echoes what the caller sent, writes anything, or answers with a
detail from an exception.
