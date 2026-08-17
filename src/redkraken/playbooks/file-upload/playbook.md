---
description: Ask whether the name a caller gives an upload decides how the server later serves it back, by storing identical bytes twice under names that differ only in extension, retrieving both, and differencing the two stored retrievals against a retrieval that was itself invariant.
bb:category: injection
bb:outputs: ["injection.stored_file"]
bb:triggers_all: ["file_parameter", "path_valued_parameter", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: approval_required
bb:effects: mutates_object
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-04-15
bb:provenance: Written for ticket 54 as the v2 replacement for v1's file-upload page against a new stored_file leaf added by ticket 54; the v1 text is attached as a maintainer reference and its shells, its polyglots and its overwrite techniques are refused by step 7.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["file-upload.md"]
---

# Ask what the server decided the bytes were

An upload is two decisions: what to store, and what the stored thing is. The
second one is where the defects live. If the name the caller chose is what later
decides the content type, the disposition or the handler, then the caller
declared what the server serves, and the bytes never mattered.

The subject is a state-changing endpoint that takes a file and takes a
destination name a recon pass typed as a path. The question is whether that name
decides how the stored bytes come back, and the whole reading is seven requests.

## 1. Get approval, and say what will exist afterwards

This Playbook is `approval_required` and `mutates_object`. Before anything is
sent, write down, in the Task:

* how many objects will exist that did not exist before -- three, on the plan
  below
* the exact names they will be stored under, all three carrying the same
  `rk-probe` marker so an operator can find them by search
* how each one is removed, and by which request
* what happens if removal fails: the names go to the operator, and the reading
  does not store a fourth object to work around the third

That is the mutation, cleanup and execution ceiling this class needs declared
first. The execution part of it is short and absolute: nothing stored by this
reading is meant to run, and step 7 says what that rules out.

Do not start until the Task carries an approval.

## 2. Name the two parameters and the retrieval

Read both parameters from the state view: the one that carries the file, and the
one that carries the destination name. They are often not in the same place --
the bytes in a body, the name in a query or a JSON field beside it.

Then find how a stored object is fetched back. An upload route with no retrieval
is not readable by this Playbook: the property is about what the *retrieval*
says, and a reading that stops at the upload response is grading an acknowledgment.

Complete this step with the two parameters and the retrieval route.

## 3. Store the control, and retrieve it twice

Store one object: the ASCII bytes `rk-probe-<task>` under a name ending in the
extension the route is for -- `.pdf` on a document route, `.png` on an avatar
route, `.csv` on an import route. Retrieve it, then retrieve it again.

Two identical retrievals, because everything after this compares retrievals. A
store that returns a signed URL, a fresh id or a varying cache header is not
byte-stable, and a differential measured against a retrieval nobody checked is
noise with a verdict attached.

Record the retrieval's status, its content type, its disposition and its length.
Those four are what the comparison is about.

## 4. Store the two arms

Two more objects, and they are as close to each other as this class allows: the
same bytes as the control, stored under two names that differ only in extension.

* the variant ends in an extension a browser treats as a document -- `.html`,
  `.svg`, `.xhtml`
* the second arm ends in an extension a browser treats as inert -- `.txt`

Same bytes in all three. That is the whole design of this reading: if the
retrievals differ, nothing about the content explains it, because there is
nothing about the content to explain it with.

The bytes are ASCII and carry no markup, no script, no macro and no header of any
format. A reading that uploads a working shell to see whether it runs has broken
the ceiling step 1 declared and has left a working shell on the target.

Retrieve both. Then send the removal request for all three objects and confirm
each one is gone.

## 5. Difference the stored retrievals

Run `compare-responses` over the variant retrieval and the second arm's
retrieval, then over the two control retrievals. Cite what the script returns.

Variant against arm is the differential: same bytes, two names, and the server
described them differently. What counts is any of the content type, the
disposition, the status or the handler that answered -- and the content type is
the usual one, because it is what tells a browser to interpret rather than
download.

Control against control says the retrieval is stable, which is what makes the
first comparison mean anything.

## 6. Rule out the name that never got used

A difference between the two retrievals could come from the *storage* rather than
from the interpretation: a route that rejected one extension outright, stored
nothing, and answered the retrieval from a placeholder.

The upload responses settle it. Both arms must have been accepted, and the
retrieval of each must return the bytes that were stored. If one arm was refused
at upload, the finding is that the route allows one extension and not another,
which is a control working, and it is not this Hypothesis.

## 7. State the claim, and state what would refute it

The Hypothesis is `injection.stored_file` on the upload endpoint. It is supported
when the two arms' retrievals differ, both uploads were accepted, both retrievals
returned the stored bytes, and the two control retrievals were invariant. It is
refuted when the two arms' retrievals are invariant -- same status, same content
type, same disposition -- which is what a route that stores under its own name
and serves everything opaquely looks like.

Anything else is inconclusive: a route with no retrieval, a retrieval behind a
CDN that normalises headers, a store that never returns the object to its own
uploader.

Two neighbours are close.

* Where the caller's name decides which *existing* document a read returns rather
  than how a stored one is served, the class is `injection.path` and the Playbook
  is `file-resolution`.
* Where the uploaded name reaches a converter, a thumbnailer or an antivirus
  invocation as part of a command, the class is `injection.command` and the
  Playbook is `command-directory-injection`.

Cite the Artifacts, the difference the script returned, and the removal receipts.

## 8. The ceiling, restated at the end

This Playbook is `approval_required` and `mutates_object` because it stores three
objects, and it stores nothing else.

It does not store executable content, a web shell, a polyglot, a document with a
macro, an archive that unpacks outside its directory, a file that overwrites an
existing one, a file under another caller's name, or a file large enough to
matter. It does not fetch a stored object as another Identity. It does not try to
make anything run: the property is what the server *says* the bytes are, and the
retrieval already said it.

Every object it stored is removed in step 4, by the route the target itself
offers. If removal fails, the reading stops, names the objects and routes to an
operator -- leaving three marked, inert, self-owned files behind and saying so is
the correct end state, and quietly leaving them is not.
