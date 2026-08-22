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
- [ ] **The reader is an offline tool a child runs, not a runtime parser.**
      Nothing in the runtime parses a body: Entities arrive as `new_entities`
      in a child's proposal. The shape to copy is `src/redkraken/jsscan.py` —
      staged into `/input`, run by the container's own interpreter, registered
      as `offline_tools.analyser`, importing nothing outside the standard
      library — which already pulls "every path-shaped literal" out of a source
      Artifact. This is the same job on an HTML Artifact, so it is a sibling
      tool and the Playbook that tells a child when to reach for it.
- [ ] **The scripts the page loads are named, and are candidates themselves.**
      An HTML body carries `<script src=...>`, `<link>` and inline blocks, and
      each named source is an Artifact this harness can fetch and hand to
      `jsscan`. Today the analyser exists and nothing enumerates what to point
      it at. Listing them is most of the value of reading the body at all — the
      contacts are the easy half.
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

A child reads a body and proposes what it has a word for. `endpoints` is a word,
so `/kontakt` survives. `applications` is a word, so the base URL survives. A
mailbox in the footer is not, so it is read, understood, mentioned in a
sentence, and thrown away with the sentence.

That is a real loss for the work this harness does. An e-mail address is the
login name for half the authentication surface an engagement will look at, a
telephone number is what a reset flow sends a code to, and both are the first
things a person doing this by hand writes down.

The graph made it visible: opening the apex Application and reading the response
beside the claim shows the contact block in the HTML, lit or not, and the panel
next to it lists nothing of the kind. Reading it there is not the answer,
though — a display that finds something the surface does not hold is a display
that has to be read by a person every time.

## Notes

Related to 159 and not the same. 159 is about the address a name resolves to and
the edge between a name and what serves it — facts the runtime already proved
and did not write down. This is about facts inside a body that nothing extracts
at all.

The scope criterion is the one to get right first. Everything else here is a
column; that one is the difference between collecting an engagement's surface
and collecting a stranger's personal data.
