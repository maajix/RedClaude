---
description: A document conversion route served twice from one source, one variant formatting the uploaded name into a command line and the other passing it as one argument, beside a queue depth that changes on every request and a naming route that reflects a filename without converting it.
bb:kind: own_pair
bb:classes: ["injection.command"]
bb:subject: /documents/convert
bb:facts: ["file_parameter", "multipart_request", "state_changing_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 53 against the command class description from the ticket 18 vocabulary, from what the class says rather than from any Playbook's steps; the noisy queue route and the reflecting naming route are the precision controls ticket 53 criterion 5 asks for.
---

# A filename that reached the interpreter

`POST /documents/convert` takes a multipart body with a file and returns what the
converter said, for a caller holding a session. Both variants convert, both
answer with the converter's output and both accept the same names. The difference
is how the converter is called:

* **vulnerable** formats the submitted name into a command line and hands the
  finished string to the interpreter, which splits it on `;` and acts on each
  part.
* **secure** hands the interpreter an argument list whose second element is the
  name, so the name is never split and never read as more than one word.

The interpreter is a dozen lines that understand `echo` and `sleep` and treat
everything else as the conversion. It runs nothing on the host that is not this
process, and that is exactly the point: the class turns on a caller's bytes being
parsed as a command, and a real shell would add risk without adding a property.

## What the two arms do here

Against **vulnerable**, a name ending `; echo rk-probe` puts `rk-probe` in the
response, and a name ending `; sleep 2` makes the request take about two seconds
longer than the same name ending `; sleep 0`. Both channels the class has, on one
route.

Against **secure**, all three names are filenames. The response is the same for
every one of them and the timing does not move, which is this class's refutation
-- and the conversion does succeed, which is what says the route works.

The sleep this interpreter honours is capped, and the cap is here rather than in
the reading: a fixture that could be made to hold a connection for an arbitrary
time would be a fixture that grades a reading's restraint by punishing the suite.

## The two precision controls, on both variants

`GET /documents/queue` returns a depth that changes on every request. It is the
route a timing reading gets wrong if it never measured what ordinary variation
looks like, and it changes without any payload at all.

`POST /documents/name` accepts the same multipart body, returns the submitted
filename and converts nothing. It is a decoy for the reading that treats a
reflected filename as evidence that something ran it.

## What the ground truth claims, and what it does not

`injection.command` on `/documents/convert` of the vulnerable variant, and
nothing else anywhere.

The uploaded bytes are never parsed, only the name is, so no document parser is
involved and `injection.document_parser` is false against every route. Nothing
reaches a query or a template. Nothing is stored: the file is read and discarded,
and the queue depth is the only state. Failures return one fixed sentence on both
variants, so there is no `information_disclosure.error_detail` beside the
declared class.
