# XXE: attached here, graded by structured-injection

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The XML external entity page, filed in v1 beside the command pack because both
ended in "and then you read a file off the host". A route accepts XML, the parser
it uses resolves entity declarations, and the caller supplies the declaration:

```xml
<!DOCTYPE r [ <!ENTITY x SYSTEM "file:///etc/passwd"> ]>
<r>&x;</r>
```

The page covered the in-band form (the entity's contents come back in the
response), the error-based form (the parser complains and quotes what it read),
the blind out-of-band form with a parameter entity fetching an external DTD, and
the SSRF pedigree -- `http://` in a `SYSTEM` identifier makes the parser a
request client on the target's network. It also noted the delivery routes that
are easy to miss: SOAP bodies, SVG uploads, XLSX and DOCX (both are zip archives
full of XML), and any endpoint that will accept `text/xml` even though its
documentation says JSON.

## Where it is graded in v2, and why not here

`injection.document_parser` is the class, and `structured-injection` is the
Playbook that claims it. A live XXE finding is recorded there.

The file lives here because the disposition ledger records a reference under the
v1 pack it shipped in, and moving it would make the ledger describe a v1 tree
that never existed.

## The half the Playbook uses

Three things travel to `structured-injection`:

* **The content-type probe comes first.** A route documented as JSON that answers
  a `text/xml` body has already told you something before any entity is
  declared. It is one request, it changes nothing, and it decides whether the
  rest of the reading is worth running.
* **The declaration is the control's twin.** The neutralised control is the same
  document with the same `<!DOCTYPE>` and an entity that resolves to a literal
  string rather than a `SYSTEM` identifier. Same size, same nesting, same parse
  path; only the resolution differs. A control that drops the doctype altogether
  compares two documents and proves nothing.
* **A parser error naming a path or an entity is `error_detail`,** and it is the
  observation the reading usually gets. In-band echo is rarer than the page
  suggested.

## The half that stays out, and why

**Reading files.** `file:///etc/passwd` is the canonical payload and the Playbook
does not send it. What is being asked is whether the parser resolves external
entities; a `SYSTEM` identifier pointing at a host the operator controls answers
that without pulling somebody's `/etc/shadow`, their cloud instance metadata, or
their application's own configuration into this harness's evidence store. Once
the answer is yes, reading a real file adds impact to the report and adds nothing
to the verdict.

**The out-of-band DTD chain.** Two hops, a hosted DTD, an exfiltration parameter
entity. It is the standard blind technique and it is out because it requires
standing up external infrastructure inside a reading and because a resolver hit
already proves resolution.

**Billion laughs and quadratic blowup.** Entity expansion denial of service is a
different question, it is destructive, and no Program's rules of engagement here
admit it.

## The trap in the whole technique

Modern parsers mostly have this off. `libxml2` since 2.9, .NET since 4.5.2, most
Java parsers once `FEATURE_SECURE_PROCESSING` is set: external entities do not
resolve by default, and a reading that finds nothing has usually found a current
parser rather than a careful developer.

Which is why the interesting surface is the one the page listed last: the SVG
upload, the XLSX import, the SOAP endpoint kept alive for one old client. Those
paths are often served by an older library, or by a parser configured once in
2016 and never revisited, and they are where the reading should be pointed.
