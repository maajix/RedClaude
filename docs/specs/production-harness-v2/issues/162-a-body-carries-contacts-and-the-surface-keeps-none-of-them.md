# 162 — A body carries contacts and the surface keeps none of them

**What to build:** The addresses a response body hands over. An Endpoint found
in a body becomes a row; an e-mail address, a telephone number or a named person
in the same body becomes nothing, and both are surface an operator needs.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] **They exist and they are not being kept.** The apex response of
      `yekta-it.de` in `rk2hunt17` is 41 KB of HTML and holds
      `info@yekta-it.de` and one telephone number written four ways —
      `0231 39814905`, `023139814905`, `+49 231 3981 4905`,
      `+49 231 39814905`. `entities` holds none of them, in that database or in
      any other this tree has produced.
- [ ] **They belong to a type that already exists, or to one this ticket
      adds.** `identities` is the closest seat and it is about slots and
      tenants, not about a mailbox printed in a footer. Decide whether a contact
      is an `identity` with a class of its own or a type beside it, and say why
      in the migration — a wrong seat here is a wrong join for every reader
      afterwards.
- [ ] **Four spellings of one number are one subject.** The four above are the
      same telephone. Storing four rows makes the count wrong and makes
      `same_as` do work a normaliser should have done. Normalise on the way in:
      E.164 where the country is known, digits otherwise, with the spelling that
      was actually seen kept beside it.
- [ ] **The parser is the runtime's, beside the one that already reads
      Endpoints.** A body is parsed for routes today. This is the same body,
      the same pass and the same Receipt, so it is one more thing that parser
      extracts rather than a second walk over the same bytes, and provenance
      stays `receipt`.
- [ ] **Scope decides whether it is kept, not the parser.** A body can name a
      mailbox at a domain nobody put in scope — a supplier, a CMS vendor, a
      person. Those are somebody else's, and a harness that files them has
      collected personal data about a third party from an engagement it was not
      given. Out of scope means dropped, and the drop is counted.
- [ ] **Checked by something that would go red.** A test that runs the parser
      over a body carrying the four spellings above plus one out-of-scope
      address, and asserts one contact row, one recorded spelling set, and the
      out-of-scope one counted as dropped rather than stored.

## Why

Recon reads a body and keeps what it has a table for. `endpoints` has one, so
`/kontakt` survives. `applications` has one, so the base URL survives. A
mailbox in the footer has none, so it is read, understood, mentioned in a
sentence, and thrown away with the sentence.

That is a real loss for the work this harness does. An e-mail address is the
login name for half the authentication surface an engagement will look at, a
telephone number is what a reset flow sends a code to, and both are the first
things a person doing this by hand writes down.

The graph made it visible: opening the apex Application and reading the response
beside the claim shows the contact block in the HTML, lit or not, and the panel
next to it lists nothing of the kind.

## Notes

Related to 159 and not the same. 159 is about the address a name resolves to and
the edge between a name and what serves it — facts the runtime already proved
and did not write down. This is about facts inside a body that nothing extracts
at all.

The scope criterion is the one to get right first. Everything else here is a
column; that one is the difference between collecting an engagement's surface
and collecting a stranger's personal data.
