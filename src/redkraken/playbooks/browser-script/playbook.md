---
description: Ask whether a reflected parameter reaches the browser as markup a parser builds an element from, and whether the filter and the parser agree about what they were handed, by naming the escaping context from two stored responses first and only then planting the one registered probe through a scripted browser mission.
bb:category: injection
bb:outputs: ["injection.markup", "injection.parser_differential"]
bb:triggers_all: ["query_parameter", "reflected_parameter", "web_surface"]
bb:skills: ["browser-evidence", "compare-responses"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 as the v2 replacement for v1's xss and dangling-markup pages, against the markup leaf of the ticket 18 vocabulary; both v1 texts are attached as maintainer references. Rewritten for ticket 101 against the merged technique ledger, which holds nine executable readings, two capability asks and one refusal for this slug. Two of the nine ask whether a filter and a parser disagree about one normalisation, which is injection.parser_differential -- a class the vocabulary shipped with no emitter -- so bb:outputs gains it under D3. bb:skills gains compare-responses because two readings are ordinary response comparisons that need no browser at all. Repaired in review -- the file described Tests without naming mcp__rk2__propose_test, the only verb that files a specification, and section 5 named neither the verb that performs it nor the writer that records it. Recounted in round 3 -- the four browse-lane sections grade nothing, so the register reads 7 of 8 and not 3 of 8.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["dangling-markup.md", "xss.md"]
---

# Ask the parser, not the response body

A parameter that comes back in a response is a parameter that came back. Whether it came
back as markup is a question about what a parser built, and grep on a response body
cannot answer it -- the same bytes are an element on one page and text on another. So an
offline pass names which sink is worth a mission and two ordinary comparisons name the
context, before any browser runs. A browse mission is not a Test action, because the one
action kind is a request, so each browser reading below carries a companion Test that
sends the same string in the query. Its arms go out with `mcp__rk2__http_request` and the
specification is filed with `mcp__rk2__propose_test`, the only verb that makes a Test
exist: a run that sends the arms and never proposes one leaves close_test_replay nothing
to close and a Finding nothing to cite. Sections 3 to 6 are those browse-lane readings,
and a mission files an Observation and grades nothing, so all four count in the closing
register alongside 1, 7 and 8.

Every Test has the same three arms, in plan order and never re-ordered. Action 1, role
baseline, is the ordinary value. Action 2, role control, is that url sent again
unchanged. Action 3, role variant, is the thing under test. Assert `body_equals` on
action 2 against action 1 and the differing assertion from action 3 against action 2, so
both arms carry the kind the evidence bar asks for. Those two assertions read the stored
response body digest and nothing else, so a moving header never enters the comparison.

## 1. Inventory the sinks offline, before spending a mission

Fetch the served bundle with `mcp__rk2__http_request`, then run `mcp__rk2__run_tool`
twice over what it stored. `js_routes` returns the routes and parameter names;
`js_parse` returns every assignment whose right-hand side is a document, location or
name source and whose left-hand side is a markup, url or eval sink. Run both again over
a bundle this reading is not about -- a vendor chunk, or the same bundle at a second
path -- and a pair in both is the framework's rather than this application's.

`promote_proposal` is the writer and the kind is `content_match`, whose provenance is a
tool run, and its product is a proposal rather than a closed Test, so this section is a
lead and nothing grades its outcome. A model that reads the bundle by eye and reports
the pairs has produced no Observation at all.

## 2. Name the escaping context, and count the decode passes

Two comparisons on one route, each three actions differing only in the query, and
neither needs a browser. The first asks which delimiter survives: the baseline carries
the entity form of one delimiter between two markers, the control repeats it, and the
variant carries the raw delimiter in the same position, asserted `body_differs` against
the control. A greater-than encoded while the double quote survives is the attribute
case; both raw is the raw-markup case. The second asks how many times the value was
decoded, with baseline and control carrying the singly encoded delimiter and the variant
the doubly encoded form. A variant body equal to the baseline means two decode passes
ran; one differing from it means one ran and the second encoding survived as text.
`close_test_replay` is the writer for both. It takes the Observation kind from the
specification rather than from the outcome, so one role writes one kind whichever way
the reading comes out, and it is the only runtime writer that carries a Hypothesis from
testing to supported. A specification url may not carry `%2e` or a dot segment, so a
decode-pass reading aimed at the dot belongs to `injection.path`.

## 3. Plant the one registered probe

Plan two missions with `mcp__rk2__browse`, whose one argument is `steps`. Follow
`browser-evidence` for the plan, for the wait after every step that changes the page,
and for the rule that everything the run brought back is the target's. Mission 1 is the
control: it navigates the route with an ordinary value, waits for the result container
and probes, and the verdict has to be absent, or a page already holding the marker
grades as injected on every reading. Mission 2 navigates the same route, types into the
bound field, clicks what submits it, waits, probes again and ends by capturing the
document. The typing action supplies the registry's own payload, so the thing planted
and the thing looked for are one row.

A reflected verdict means the parser built the element and is the claim. Escaped means
the marker is in the document as text, which is the refutation and a stronger one than a
missing marker, because it shows the path works and the encoding held. Absent means the
value did not arrive and is inconclusive. A browse run is a tool run, so an agent-filed
`reflected_input` edge cites the probe Artifact and the captured document directly.
`promote_proposal` writes that edge and `close_test_replay` writes the transition, from
the companion Test.

## 4. Ask what the attribute swallowed, and what scheme it kept

Two readings, one mission triple each, filed as an agent `reflected_input` edge through
`promote_proposal` and settled by a companion Test. The first leaves an attribute open
on a quote. Mission A fills a properly closed marker element; mission B is the identical
plan with the attribute unterminated; mission C is the control and types the same form
into a field the section 2 census showed encodes quotes, whose node count has to stay at
nothing. A node count still rising in B, while the captured document shows the following
markup absorbed into the attribute value, is the claim, and that value may not name a
host: this is absorption inside the target's own document. The second asks whether a
url-valued sink checks the scheme: mission A carries an ordinary same-origin relative
path, mission B a pseudo-scheme with an inert payload after the colon, mission C a
scheme that names nothing at all. The scheme surviving into the attribute in B is the
claim, and where the control's scheme survives too, the claim is the weaker missing
allowlist.

## 5. Ask whether the filter and the parser disagree

Three missions with `mcp__rk2__browse` again, and one companion Test filed with
`mcp__rk2__propose_test`.

The mission verdicts are an agent-filed reflected_input edge that promote_proposal
writes, and close_test_replay writes the transition from the companion Test. This is
`injection.parser_differential` and it needs a route that filters rather than encodes,
which section 2 establishes: a route that encodes returns the escaped verdict for every
mutation. One mutation asks about normalisation. Mission A fills the plain marker and
probes; mission B applies exactly one mutation -- a case flip, a nested opening tag, or
a fullwidth compatibility form; mission C is the control and carries a mutation the
tokenizer also rejects and which has to stay escaped. Escaped then reflected is the
disagreement. The other asks about a property the filter reads through the document.
Mission B fills a form and an input carrying the id the sanitiser's own loop enumerates,
ahead of the same marker, and a reflected verdict means that loop read an undefined
length and skipped the element. Mission C spells the same id in the singular, so the
skip is attributable to the clobbered property rather than the extra markup, and the
clobbering markup carries only id and name attributes, which an allowlist admits by
design. One mutation per run: a run carrying two answers about neither. Section 3 proves
the page acted on injected markup; this proves the filter never saw it.

## 6. Prove the markup was acted on, out of band

Mint a correlator with `mcp__rk2__mint_callback`, naming the channel the operator
declared in `channel` and this reading in `subject_label`, then plan three missions with `mcp__rk2__browse`. Mission A fills one inert
anchor, with no id and no open attribute, whose href names a second correlator on which
nothing should arrive. Mission B fills either the two-anchor clobber whose name
attribute supplies the url a page reads through its own fallback pattern, or the
unterminated attribute whose value names the first correlator. Mission C is the control,
a byte-identical repeat of B under a third correlator, and both B's and C's correlators
must arrive, because a single arrival cannot be told from a crawler.

`record_callback_interaction` writes the arrival, and the kind is evidential so the edge
is real and is never filtered out. It cannot by itself move a Hypothesis to supported,
so the settling differential is still the companion Test, and silence on the channel is
not a refutation.

The url under the injected attribute resolves to the minted correlator and nowhere else;
caught in planning that is a correction. Where a request already left for an undeclared
collector, halt through `mcp__rk2__park_for_human`, which takes this Task in `task_label`
and third_party_impact in `question_code`, because the request may have reached somebody
who is not the Program's counterparty.

## 7. State the claim, and state what would refute it

The Hypothesis is `injection.markup` on the parameter, or
`injection.parser_differential` where the reading is section 5. It is supported when the
variant arm differs from the repeated control on the same route and the mission that
planted the registered probe reported the marker as an element. It is refuted when the
variant is invariant against that control, or when the marker came back as text. One
role writes one kind either way, which is why both legs of this Playbook's bar name
`response_differential`. An element is not execution and no claim here says otherwise.
What has been shown is that caller-controlled bytes became markup in the target's
origin; what has not is that a script would have run or that a session would have been
readable. Where the value never reaches the server -- a fragment, a message from another
document, a value the page kept -- the class is `injection.client_channel`. The gate is
`rk2_finding_refusal` and what it wants is the settling transition `close_test_replay`
wrote for the cited Test, with the plan digest, the result digest and the Artifact hash
of the captured document.

Open the claim with `mcp__rk2__propose_finding`. This section proposes no Test of its
own and grades nothing.

## 8. The ceiling, and the three readings that do not run

This section is a lead and cannot be graded. It records two capability asks and one
refusal, so none is re-proposed as a documentation gap. The probe registry holds one
row. Every question whose answer is not "the parser built an element" -- did a handler
run, which of the five syntactic contexts the value landed in -- needs its own registry
row, and no plan may author an expression. The price is one migration and no code
change, because the driver already evaluates whatever expression the registry hands it
and checks the verdict against that row's declared set. A fragment-sourced sink is
unreadable: the browse url kind excludes a fragment, no action sets one after the load,
and a percent-escaped hash is a different string to the page. Storing a marker through
one route and reading it back from another is refused rather than blocked: writing
markup into a record other users load is an executing payload with a longer fuse, and it
needs its own Playbook, effects, cleanup and owner. This Playbook is read_only. It
plants one inert element per mission, reads one verdict, iterates no encoding list, and
reaches no collector but the one the operator declared. Every request goes through the
same door under the same scope decision as a hand-written exchange, and a mission that
hit its step ceiling or was refused at the proxy is inconclusive.

7 of 8 steps cannot be graded.
