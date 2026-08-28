---
description: A dashboard page loading a widget from an asset host, served twice from one source, one variant still referencing a provider slot that answers NoSuchBucket and the other referencing a host the application holds.
bb:kind: own_pair
bb:classes: ["injection.unclaimed_reference"]
bb:subject: /dashboard
bb:facts: ["read_method", "unauthenticated_endpoint", "web_surface"]
bb:identities: []
bb:provenance: Written for ticket 100 against the class description this migration adds, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# A reference the application still publishes, and what the name answers

`GET /dashboard` returns a page with `<script src="https://<asset host>/widget.js">`.
`GET /assets/manifest` states the same host as data, so a reading does not have
to parse markup. `GET /assets/status` reports what the application got the last
time it fetched that host.

The variants differ in which host that is, and in what the host says about
itself:

* **vulnerable** references `legacy-assets-4f2c.fixture.invalid`, and the status
  route reports `upstream_status: 404` with the provider's own body --
  `<Code>NoSuchBucket</Code>` naming the bucket.
* **secure** references `assets.fixture.invalid`, and the status route reports
  `upstream_status: 200` and the asset's size.

`GET /provider/<host>` serves the provider's half so the report is checkable
rather than asserted: the held name returns the script, and every other name
returns the unclaimed-namespace error.

## Nothing here is claimable, on purpose

The provider is a route on this same fixture. There is no registrar, no bucket
and no namespace to take, which is the only honest way to grade this class:
**the reading is the reference plus the provider's answer, and claiming the
resource is refused.** A fixture that could be claimed would be a fixture that
rewards claiming it.

## The control

The `secure` half's manifest and status, which have the same shape, the same
keys and the same route names as the vulnerable half's. The difference is one
host name and one upstream status, so a run that reports a finding without
naming both has reported that two ports exist.

## What is not here

`injection.foreign_resource` is the neighbouring class and it is about an origin
the application does not control *serving content to it*. Here nothing is
served: the point is that nobody answers for the name at all, and that anybody
could become the one who does.

`information_disclosure.dependency_manifest` is a manifest that discloses what
is installed. This manifest discloses nothing an attacker did not already read
off the page; what it carries is the reference, not a version list.

Nothing here resolves DNS, reads a registrar, or reaches a real provider. The
whole reading is inside one process, because the class is about what the
reference and the answer say together.

## Ground truth

* **vulnerable** holds `injection.unclaimed_reference`. The page and the
  manifest both point at a provider slot, and the provider answers that the slot
  is not held.
* **secure** holds nothing this catalogue declares. The referenced host is held
  and serves the asset.
