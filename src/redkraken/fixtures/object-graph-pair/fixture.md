---
description: An authenticated preferences-restore route served twice from one source, one variant constructing whichever type the serialised blob names and the other reading the blob into the one shape it stores, beside a counter that changes on every read and an echo route that lists the blob's fields without building anything.
bb:kind: own_pair
bb:classes: ["injection.object_graph"]
bb:subject: /preferences/restore
bb:facts: ["authenticated_endpoint", "serialized_object_parameter", "state_changing_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 54 against the object_graph class description ticket 54 added, from what the class says rather than from any Playbook's steps; the noisy counter and the echo route are the precision controls ticket 54 criterion 5 asks for.
---

# A type the caller named, and a route that built it

`POST /preferences/restore` takes a base64 blob of the form `rk1:<type>:<json>`
and answers with the preferences it restored, for a caller holding a session.
The blob is what a client stores when it saves a session, so a caller has one and
can edit it. The two variants differ in one lookup:

* **vulnerable** reads the type name out of the blob and constructs it, keeping
  the fields that type declares.
* **secure** ignores the name and reads the state into the two fields this route
  stores, whatever the blob said its type was.

No shell, no query and no template is involved. The interpreter here is the
constructor table, and what the caller supplies is not a value it compares but
the name of the thing it builds.

## What the two arms do here

Against **vulnerable**, a blob naming `AuditProbe` comes back as
`{"restored": "AuditProbe", "state": {"probe": ...}}`, and the same JSON naming
`Preferences` comes back as `{"restored": "Preferences", "state": {"theme": ...,
"density": ...}}`. Two blobs differing in one word, two different objects.
`AuditProbe` is registered on this route and is not part of any preferences
document the client writes, which is the shape of the defect: the reachable set
of types is the process's, not the route's.

Against **secure**, both blobs come back as `{"restored": "preferences",
"state": {"theme": null, "density": null}}`, byte for byte. The arms are
invariant against each other, which is this class's refutation.

A blob that does not decode, or whose JSON is not an object, gets the same fixed
`saved preferences were not readable` on both variants, and so does a type the
vulnerable variant has no constructor for. Nothing anywhere quotes the caller's
type name back inside an error: a fixture whose signal was a talkative failure
would be grading `information_disclosure.error_detail` under another name.

## The two precision controls, on both variants

`GET /preferences/live` returns a body carrying a counter that increases on every
request, so a reading that skipped its baseline has a route it can be wrong
about.

`POST /preferences/echo` takes the same blob and returns the type name it carried
beside the fields the caller sent, having built nothing. It is a decoy for the
reading that treats a type name coming back as evidence that a type was
constructed.

## What the ground truth claims, and what it does not

`injection.object_graph` on `/preferences/restore` of the vulnerable variant, and
nothing else anywhere.

No constructor here has an effect. `AuditProbe` holds a field and does nothing
with it, there is no method the blob can name, no chain, and no way to reach a
process, a file or a socket from a decoded graph -- the whole of what the caller
chooses is which of three field lists the state is read into. That is deliberate:
the property is that the caller picks the type, and a fixture that proved it by
running something would be grading `injection.command` instead. Nothing here
writes, and nothing here is served to a second caller.
