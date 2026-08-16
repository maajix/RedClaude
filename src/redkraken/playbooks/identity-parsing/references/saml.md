# SAML: signature wrapping, canonicalisation, and the parts that are not findings

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## The one class this Playbook claims

`authentication.federation_trust`: the relying party acted on an identity that
was outside the region its signature verification covered. The evidence is one
document, our own, with the subject stated twice, and a session that came back
belonging to the copy the signature did not cover.

## Why wrapping keeps working

An assertion is a tree. Signature verification names a region of that tree, in
practice by an identifier in a `Reference` element. Subject extraction is done
by a second piece of code, often with an XPath expression, a different parser, or
"the first assertion in the document". Wrapping is arranging for those two to
select different nodes.

The variants worth sending, one per request:

* a second, unsigned assertion placed **before** the signed one, same document
* the signed assertion relocated under a wrapper element (`Object`, `Extensions`,
  a decoy `Response`), with a copy left in the original position
* the subject element duplicated **inside** the signed assertion
* the `Reference` identifier changed so it names the injected copy

Each of them is one edit against the document the identity provider minted for
us. None of them forges a signature, and none of them touches the provider.

## Canonicalisation is where the two parsers actually diverge

Comments inside a text node, namespace declarations moved between elements, and
whitespace are all removed or preserved differently by different
canonicalisation algorithms. That is why `<NameID>ours<!-- -->@example.com` is a
classic: the verifier canonicalises the comment away and the extractor does not,
or the reverse. Treat it as one more variant with one edit, not as a separate
technique.

## Not that: XML external entities

An assertion consumer that resolves external entities is a real finding and it
is not this class. It is `injection.template` or `information_disclosure`
depending on what comes back, and it is measured with a document that has no
valid signature at all -- so it is a different reading with a different control.

## Not that: metadata and certificate hygiene

An expired signing certificate, a metadata document served over plain HTTP, a
self-signed certificate: those are configuration statements. Record them as
surface. They become findings only when they lead to a document being accepted
that should not have been, which is the reading above.

## Not that: replay

The same unmodified assertion accepted twice is `business_logic.replay`, and it
is worth testing, but it is not one edit and it is not this class. Keeping it
out is what lets this Playbook's refutation edge be sharp: if the only difference
between two readings is that one was sent twice, the wrapping question was never
asked.

## Who the second subject may be

Always a name the Program controls. A successful variant creates a session as
whoever the injected subject names, and naming a real user of the target is an
unauthorised login attempt against a person, not a test.
