# 54 — Migrate server-side, file and disclosure Playbooks

**What to build:** Deliver production-ready Playbooks and fixtures for seven v1 topics covering server-side object processing, files, request forgery, exceptional behavior and exposed information.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** resolved

**Deviation on criterion 6, inherited from 49, 50, 51, 52 and 53:** the positive and adversarial
arrangement exists and is total; the evaluation that would grade it has not run, and cannot run
from this ticket. All seven ship `draft`. `stable` is reachable only through
`playbook_test_verdict` returning `pass` for the exact text, and an evaluation run is an Agent
run against a fixture listening on loopback, which `scope.compile_policy` and
`authorize_identity_egress_address` both refuse. Ticket 78 decided that route; ticket 84 grades
the corpus over it. What moved is the measurement: the corpus is forty-two Playbooks and forty-
three fixtures, `playbook_fixture_binding` is still total over the fixture table, and each of
the seven new fixtures is an out-of-class negative for the forty-one Playbooks that do not
output its class. The half of the criterion that is about selection is checked and holds:
`PlaybookCorpusSelectionTest` is diagonal across all forty-two subjects, and every one of the
seven is loadable by exactly one production role.

**Deviation on criterion 2:** two of the seven distinctions the criterion names are already
drawn elsewhere in the catalogue and are not redrawn here. `information_disclosure.
artifact_exposure` is `attack-surface`'s output and `information_disclosure.excess_field` is
`graphql`'s, both migrated by ticket 49. Claiming either again would break the
one-class-per-Playbook rule 051 stated and 053 restated. So `secrets`
takes a new `credential_material` leaf and `information-disclosure` takes a new
`undeclared_field` leaf, each argued against the neighbour it is not in the migration's own
comments, and the criterion's remaining five distinctions -- error detail, path resolution,
upload interpretation, document parsing and server-side request behaviour -- land on
`information_disclosure.error_detail`, `injection.path`, `injection.stored_file`,
`injection.object_graph` and `injection.url_authority`.

- [x] Deserialization, File Resolution, File Upload, SSRF/URL Routing, Exceptional Conditions, Information Disclosure and Secrets each exist as authored v2 Playbooks.
- [x] Playbooks distinguish artifact exposure, excess fields, error detail, path resolution, upload interpretation, document parsing and server-side request behavior through Property classes.
- [x] SSRF and URL-routing evidence uses configured callback or controlled local targets and cannot authorize adjacent-host discovery or third-party contact.
- [x] File and deserialization tests declare mutation, cleanup and execution ceilings before any higher-risk action.
- [x] Fixtures include secure normalization, harmless error, decoy secret and non-fetching URL controls.
- [ ] All seven exact hashes pass loadability, relevant positive recall and adversarial precision gates before stable promotion. **Partial:** loadability holds and the fixtures grade offline; the production gates wait on the route above. Ticket 78 built that route; ticket 84 grades the corpus over it.

## Comments

Implemented on 2026-08-17.

### Sixteen v1 pages, seven readings

v1 filed this material by what the payload was made of: a gadget pack, three path pages, an
upload page, a four-page SSRF pack, and three single pages of advice about errors, extra fields
and keys. A reading is none of those. What separates one reading here from the next is which
decision the target made on the caller's behalf -- which type to construct, which file to
resolve, which bytes to keep and serve back, which host to fetch, what to say when it failed,
what its own contract promised, what a string in a served document is worth. Seven decisions,
seven Playbooks.

`deserialization` absorbs the gadget pack, `file-resolution` the three path pages, `file-upload`
the upload page, `ssrf-url-routing` the four-page SSRF pack. `exceptional-conditions`,
`information-disclosure` and `secrets` are rewritten with nothing attached: all three v1 pages
were advice rather than material, and the advice -- fuzz with overlong inputs, harvest whatever
the extra fields hold, enumerate what a found key reaches -- is exactly what the Playbook
refuses.

Three of the four notes under `ssrf-url-routing` describe questions it does not grade.
`open-redirection.md` ends at `client_side.navigation`, which is `routing`'s;
`dns-rebinding.md` and `pdf-generators.md` end at `injection.request_forgery`, which is
`webhooks`'. They are attached where v1's pack put them, because the ledger records where a v1
page went rather than where its subject is graded, and each note says in its own text where its
subject is actually read.

### Five new leaves, and why each one is a leaf

Two of the seven land on leaves 018 already named and left unclaimed for thirty-five Playbooks.
`injection.path` waited because every earlier reading about a caller-supplied string was about
a browser, a query or an identity. `information_disclosure.error_detail` waited because 046
wrote a fixture for it as an out-of-class negative and no Playbook was allowed to want it.

The other five are new, each split from a neighbour that reads differently:

`injection.object_graph` is the caller choosing which type the target constructs. 018's
`document_parser` is graded on a parse offset moving; nothing here parses a document, and the
signal is a type name in the blob changing what came back.

`injection.stored_file` is neither `injection.path` nor `injection.markup`. The bytes stored are
inert and the name is basenamed on both variants; what is graded is the target serving back
what it kept, under a content type it chose.

`injection.url_authority` is a disagreement between what was checked and what was fetched.
`injection.request_forgery` is an arrival -- a request landing somewhere -- and that is
`webhooks`'. Here nothing has to arrive: two parsers of one string answering differently is the
whole claim.

`information_disclosure.undeclared_field` is about a published declaration. The target says what
its response contains, and the response contains more. 018's `excess_field` is about
entitlement -- a caller receiving a field they are not owed -- which is a different question
about the same bytes.

`information_disclosure.credential_material` is about a document meant to be published saying
something it should not. `artifact_exposure` is about a document being reachable at all. The
bundle here is served at exactly the path the shell names, on both variants.

### What tells the seven apart on the Surface

Three new facts. Two are parameter value classes -- `path_valued_parameter` and
`serialized_object_parameter` -- and one is a technology family, `tech_openapi`, mapping
`openapi`, `swagger` and `redoc` onto one fact for the reason `tech_cdn` does. `value_class` is
free text in 003, so neither parameter fact needed a schema change.

Four of the seven are an authenticated read told apart by one parameter's value class: a number
is `exceptional-conditions`, a path is `file-resolution`, a URL is `ssrf-url-routing`, and a
serialised blob on a write is `deserialization`. The remaining three key on what the route is
rather than what it takes -- a published contract, a document another document loads, and a
write that takes both a file and a name.

`file-upload` is the only Playbook in the catalogue whose trigger list needs two parameters on
one endpoint, and that is the point rather than an awkwardness. A file in a multipart body is
`command-directory-injection`: an upload that reaches a converter. An upload whose destination
the caller also names is this one. A route with the file alone matches neither, which is the
correct answer -- there is nothing to compare two retrievals of if the caller never chose a
name. `PlaybookCorpusSelectionTest`'s `surface()` writes at most one parameter per subject, so
the upload subject gets a second one from `name_the_uploaded_file()`.

### The four controls criterion 5 names, and where each one lives

Every pair holds one class, enforces everything else identically on both halves, and names in
its ground truth the neighbouring class it keeps out. The criterion asks for four specific
controls and each is in the pair that can be wrong without it:

**Secure normalization** is `path-pair`: both halves normalise the caller's name the same way,
and the secure one then compares the result against the root it is allowed to serve rather than
rejecting the strings that look like traversal. `stored-file-pair` basenames on both halves for
the same reason -- a traversal in an upload's name is nobody's finding there, because what that
pair grades is what the name makes of the bytes, not where the name resolves.

**Harmless error** is `diagnostic-detail-pair`'s `limit=0` -- a value of the right type that the
route's own rule rejects, answering identically on both variants. A reading that cannot tell it
from the two arms that are not numbers is reporting that the route validates, not that it
confesses.

**Decoy secret** is `credential-material-pair`'s `rk_sample_000000000000`: the prefix, the
length and the position of a real key, sitting in a comment that says what it is, and buying
nothing. It is why that Playbook's claim is a `credential_effect` rather than a pattern match.

**Non-fetching URL** is `url-authority-pair`'s `/render/echo`, which parses the URL, names the
host back and fetches nothing.

Beside those four, every pair carries 053's two: a noisy endpoint whose body changes on every
request, and a decoy that echoes without doing the thing.

### The second target for `error_detail`, and why 046's was not widened

`exceptional-conditions` ships a new fixture, `diagnostic-detail-pair`, rather than widening
`error-detail-pair`. That is the one place this ticket adds a fixture beyond its seven topics'
count of subjects, and the reason is what the older fixture is for. Ticket 46 wrote
`error-detail-pair` as an out-of-class negative for the authorization family: an anonymous
search route with no session, no object and no controls, whose whole job is to be a real defect
that no authorization Playbook may claim. Adding a session and three controls to it would have
destroyed exactly that. Its bytes are unchanged, its digests stay frozen in migration
`20260824T000000Z`, and `PlaybookEvaluationTest.OUT` still names it. The new pair is what a
Playbook about failure behaviour is graded on, and both ground truths say so.

Having two targets for one class has a consequence 036 makes unavoidable:
`playbook_fixture_binding` is by class alone, so `exceptional-conditions` is graded `in` on
both, and one of them serves anonymous callers. So step 2 of that Playbook sends without an
`identity_slot` where the subject takes no session, and says why: nothing in the reading is
about who asked, and a subject that answers everybody is a subject this reading can still
difference. The trigger set keeps `authenticated_endpoint` for selection, because that is what
keeps the corpus diagonal; the reading is not narrower than the class.

### Evidence, risk, and the two rows that are not like the others

Four refute with a `response_invariant` on the variant leg, which is 053's shape and for 053's
reason. The supported kinds are four: `response_differential` for `deserialization`,
`file-resolution`, `file-upload` and `ssrf-url-routing`, each answered by the target having made
a decision the caller chose; `error_detail` for `exceptional-conditions`, where the finding is
the failure text; `content_match` on all three legs of `information-disclosure`, because the
comparison is between two stored documents and what says a name is in one and not the other is a
match over an Artifact; and `credential_effect` for `secrets`, because a string that looks like a
key is nothing and the target honouring it is everything. That Playbook's control leg is a
`content_match` instead, since a decoy that never appeared in the document cannot be evidence.

`secrets` is also the one row without `use-identity`, and dropping it is deliberate. Its subject
is served to anybody and its claim is what a candidate string is worth to a caller holding
nothing else; a session in the second arm would let the route have answered because of the
session rather than because of the string.

`file-upload` is the only one that is not `read_only`. It stores an object, so it is
`mutates_object`, and it is `approval_required` because the ceiling it declares in step 1 --
what it stores, how each object is removed and by which request, and that nothing it uploads is
ever executable -- is a promise the operator has to accept before step 2 runs. Step 8 restates
the ceiling, and step 4 ends by removing all three stored objects through the target's own
route and confirming each one is gone.
`deserialization`'s ceiling is step 7: the reading writes nothing it cannot delete, and if the
only way to see a difference is to store something the client cannot remove, the verdict is
inconclusive rather than the write happening.

Criterion 3 is answered in `ssrf-url-routing` step 1: the arms go in front of an `@`, and the
authority behind it is either the Program's configured callback or a target the Program owns
and has marked as a controlled fetch destination. If the Program declares neither, the Playbook
says so and stops. It never substitutes a host that merely looks harmless, and there is no step
in it that sweeps a range, resolves a name twice or contacts a third party.
