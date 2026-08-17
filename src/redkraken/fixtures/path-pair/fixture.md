---
description: An authenticated export route naming a document by path served twice from one source, one variant serving whatever the normalised name resolves to and the other checking where the resolution landed before it reads, beside a counter that changes on every read and a name route that echoes the path without resolving it.
bb:kind: own_pair
bb:classes: ["injection.path"]
bb:subject: /documents/export
bb:facts: ["authenticated_endpoint", "path_valued_parameter", "read_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 54 against the path class description from the ticket 18 vocabulary, from what the class says rather than from any Playbook's steps; the noisy counter, the name route and the value that normalises back inside the base are the precision controls ticket 54 criterion 5 asks for.
---

# A name that resolved somewhere else

`GET /documents/export?file=<name>` answers with a document out of the export
directory, for a caller holding a session. Both variants join the name onto the
base and normalise the result. They differ in what happens next:

* **vulnerable** reads whatever the normalised path reaches.
* **secure** checks that the normalised path is still under the base, and
  refuses with a fixed `no such document` when it is not.

Two documents live under the base and two do not. Nothing else in this fixture
serves the latter two: `GET /vault/ledger.txt` is the same bounded `no such
route` on both variants, so the only thing that ever reaches them is the
resolution.

## What the three arms do here

Two arms leave the base -- `../vault/ledger.txt` and `../vault/keys.txt`.

Against **vulnerable** they answer with two different documents, each naming the
path it resolved to. Against **secure** they are byte for byte the same
`{"error": "no such document"}`. Invariance between those two arms is this
class's refutation, and the fact that a missing document and an out-of-base
document give the identical refusal is why the invariance means something.

The third arm is `notes/../report.txt`: a name that contains a traversal and
normalises back inside the base. It answers with `exports/report.txt` identically
on both variants, and identically on repeat. It is the secure-normalisation
control ticket 54 criterion 5 asks for -- a reading that reports it, or that
reports the presence of `..` in an accepted value, is scoring the syntax of its
own payload rather than where the read landed.

## The two precision controls, on both variants

`GET /documents/live` returns a body carrying a counter that increases on every
request, so a reading that skipped its baseline has a route it can be wrong
about.

`GET /documents/name?file=` returns the caller's name unchanged, having resolved
nothing. It is a decoy for the reading that treats its path coming back as
evidence that a path was used.

## What the ground truth claims, and what it does not

`injection.path` on `/documents/export` of the vulnerable variant, and nothing
else anywhere.

The out-of-base documents are only reachable through the parameter, which is what
keeps this apart from `information_disclosure.artifact_exposure`: nothing here is
published at a path a reading could have requested directly. Refusals are fixed
strings on both variants and never say which check failed, so nothing here is
`information_disclosure.error_detail`. Nothing writes, and the reachable set is
four constant strings, none of which is a credential.
