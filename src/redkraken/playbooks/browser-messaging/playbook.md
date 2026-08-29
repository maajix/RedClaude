---
description: Ask whether a document something else embeds turns a value it never fetched into its own markup, by inventorying what the page listens for and then planting one registered probe through a field, a fragment or a polluted property path while the Receipt list shows no request carried the value.
bb:category: injection
bb:outputs: ["injection.client_channel"]
bb:triggers_all: ["embedded_document", "read_method", "web_surface"]
bb:skills: ["browser-evidence"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 as the v2 replacement for v1's dom-vulnerabilities and prototype-pollution pages, against a new client-channel leaf added by ticket 52; both v1 texts are attached as maintainer references and both describe sources this Playbook now drives. Rewritten for ticket 101 against the merged ledger, which carries four readings and one refusal for this slug. No frontmatter key moved and the evidence bar is already reachable, because the refuted and supported legs of the variant role name one kind. Two shipped paragraphs were false rather than cautious and are replaced. The fragment refusal is lifted -- ticket 99 widened the navigate url pattern so a browser-local fragment is admissible -- and the claim that no action sends a cross-document message is superseded by the listener inventory and the registry-owned dispatch, whose boundary is that a dispatch is reported as dispatched and never as matched. The whole ceiling is now stated in the preamble rather than discovered after a mission.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "reflected_input", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "reflected_input", "polarity": "supports", "min_count": 1}]
bb:references: ["dom-vulnerabilities.md", "prototype-pollution.md"]
---

# The value the server never saw

Some of what a page renders never crossed the network. A fragment, a message from the document
that framed this one, a key an attacker put on an object every other object inherits from, a
value the page kept from an earlier screen -- all of them are inputs, none of them appears in a
Receipt, and a reading built on differencing requests is blind to every one.

The subject is a document something else embeds, which is what makes it a document handed
values it did not fetch. The question is whether one of those values becomes markup.

**The ceiling, stated before any mission is planned rather than discovered after one.** A Test
action is a request and nothing else, so no browse mission is replayable as one, and
close_test_replay -- the only writer of the runtime transition from testing to supported that a
Finding needs -- writes it only for a Test's own assertions. Every section below therefore ends
at an Observation: promote_proposal files the kind the mission's own reader names,
rk2_promote_hypotheses attaches it as a real evidence edge with no filter on the cited kind,
and that edge is the whole of what this Playbook produces. The readings are legitimate and
reportable and settle nothing on their own. A hunter who needs a Finding out of this class
needs the request-lane neighbour named in the last section, not a longer mission here.

Every mission is planned as a whole through `mcp__rk2__browse`, which takes its plan as steps
and admits between one and thirty-two of them. Each reading names a baseline mission that
plants nothing, a variant mission that plants exactly one registered marker, and a control leg
that rules out the boring explanation.

## 1. Say which document is embedded, and by what

The Surface says something embeds this route. Name both ends -- the parent that loads it and
this document's own URL. A widget, a preview pane, an editor frame and a payment field are all
this shape, and each is a document whose caller is another document rather than a person.
Complete this section with the two routes and what the embedding is for. Where the parent is an
origin the scope document does not clearly admit, stop here and ask for the Task to be parked
with `mcp__rk2__park_for_human`, carrying the Task's own `task_label` and the `question_code`
scope_ambiguous, which park_task_for_human writes. This section names and grades nothing.

## 2. Load it once, planting nothing

Plan a mission that loads this document directly, top level, and ends at the markup probe.
Directly rather than framed, because a probe evaluates in the document it was run against and
one run in a parent cannot see into a child. This is the baseline every later mission is
measured against, and its verdict must be absent: the probe's marker is not already in the
page. Without it a document that happened to carry the marker string would grade as injected on
every reading. It is also the response_invariant this Playbook's control bar names, filed from
the mission's one navigate Receipt. This section files an Observation and grades nothing.

## 3. What the page listens for, before speaking to it

Plan a mission that navigates, reads the window's registered message listeners as client state,
and captures the document. The inventory is a registry-owned reading and returns each
listener's type, its capture, passive and once flags, and the script identifier, line and
column where it was registered. Zero listeners ends this section: the driver refuses a dispatch
unless the immediately preceding step is a non-empty inventory, and it refuses it twice, once
when the run is opened and once in the driver itself.

Then read the origin comparison at the position the inventory gave, offline, with js_parse
under `mcp__rk2__run_tool` over the stored bundle Artifact. An equality test and a substring
test -- an indexOf, a startsWith, an endsWith -- are different answers to one question and the
second is the weak one. The control for this leg is a listener in the same bundle that compares
with strict equality, which shows the source reading tells the two shapes apart rather than
reporting every comparison as weak. The variant is the dispatch: the single registry-owned
message body, posted same-origin, with the document captured before it and after it and a text
assertion for whatever a handler would have changed. The control is the same assertion made
absent BEFORE the dispatch, because text that was always on the page reads as a handler result
without it.

**A dispatch is reported as dispatched, never as matched.** A cross-document message returns no
handler result, so no step may claim a listener accepted the body; the before and after
documents are the only bridge between the two words and it is a weak one. What this section can
honestly claim is what the listener IS and what shape its check has. Both halves are
content_match, agent-filed, citing the browse run and the offline run -- a browse run is a tool
run by its own foreign key and the provenance check reads the kind string rather than which
binary produced it, so neither needs a second pass over the stored Artifact. This section files
Observations and grades nothing.

## 4. The field the page renders without a round trip

A live preview, a typeahead, a composer that renders as it is typed -- a field the page reads
with no request in between. Plan the variant mission as navigate, inject, wait for whatever the
page renders it into, then the markup probe and a document capture. No click. That is the whole
design of the section. Injecting, waiting, capturing and probing all declare that they reach no
network, so a run whose Receipts hold one navigate and nothing else is a run in which the value
never crossed the door. That Receipt list is the control, and it separates this class from
injection.markup: not an argument that the server did not see the value, but the absence of the
request that would have carried it. The baseline is section 2's mission, which returned absent.

The injected payload is the probe registry's own and the plan cannot choose it. The thing
planted and the thing looked for are one registry row, so a verdict cannot be arranged by
picking a marker the page was going to contain. A verdict of reflected is the claim, filed as
reflected_input from the browse run with content_match over the captured document; a verdict of
escaped is the refutation and the stronger answer, because it shows the path works and the
encoding held; absent is inconclusive and means the reading did not reach the sink. This
section files an Observation and grades nothing.

## 5. The fragment, which the browser lane now admits

A fragment never leaves the browser, which is exactly what makes it this class's source rather
than injection.markup's. Ticket 99 widened the navigate url pattern to admit one, so the
shipped refusal is lifted: the admitted charset excludes the angle brackets and the quote but
admits the percent sign, so the marker rides percent-encoded and only a sink that decodes
before writing builds the element. The baseline is a mission navigating to the same document
with an inert fragment of the same length, ending at the probe, verdict absent. The variant is
the same mission with the fragment carrying the encoded marker. The control is the same marker
in the QUERY string at the same length: if that also returns reflected the value crossed the
network and the class is injection.markup rather than this one, and the Receipt list proves
which, because navigate is the only step that reaches the network and the query, unlike the
fragment, is on the wire.

One spelling, not an encoding ladder. Two fragments both returning absent end the section: a
sink that writes the fragment without decoding sees the escapes and builds nothing, the common
outcome rather than a reason to try more. This section files an Observation and grades nothing.

## 6. The property path that pollutes what every object inherits from

Where source reading has already located a gadget whose sink is markup, the question is whether
a query-string property path reaches the object every other object inherits from and the gadget
then writes the planted value out. The baseline is a mission navigating the route with an
ordinary parameter name carrying the marker, verdict absent. The variant is the same mission
whose navigate url carries the marker under the Object.prototype property path,
percent-encoded to survive the url pattern. The control is the same marker under a plain parameter name of the
same length, which must return absent, so the element is the pollution's and not the
parameter's. Three spellings of the path matter -- the double-underscore one, the
constructor-prototype one, and the bare one -- and a parser that blocks the first and not the
second has blocked one spelling, so a run that sends only the first and reports "not
pollutable" has reported the spelling rather than the merge.

**The pollution is planted by the navigate url and NOTHING follows the probe.** That is the
discipline the shipped ceiling was protecting: a planted key on a shared ancestor is global to
the document and changes how every later step behaves, so a mission that pollutes at step three
is a mission whose steps four onward describe the pollution. One navigation, one marker, the
probe, and the plan ends. Refutation is also available without running anything, and the
reference says so: a null-prototype object, a map, or a merge that checks ownership is the fix
and is visible in source. This section files an Observation and grades nothing.

## 7. State the claim, the ceiling, and the reading this slug refuses

The Hypothesis is injection.client_channel on the document, proposed with
`mcp__rk2__propose_finding` naming xss_reflected as the class -- that argument takes a
vulnerability_classes id and not a dotted Property class, and
property_class_vulnerability_classes carries no row for this Playbook's class, so the choice is
recorded here rather than derived and finding_class_divergence stays silent for an unmapped
class. Nothing here settles it, for the reason the ceiling gives. A mission that planted the
registered probe and returned reflected, with Receipts showing no request carried the value and
a baseline mission that returned absent, is the strongest report this Playbook makes; a mission
returning escaped is the strongest refutation. Both are Observations and neither is a
transition, because close_test_replay writes that row only for a Test's own assertions and
TEST_ACTION_KINDS is the single word request. The four ledger rows behind sections 3 to 6 are
marked as reaching a Finding, and on this evidence the mark is wrong: it is the rows that want
re-reading, not a step here promising what nothing writes. Cite the plan digest, the result
digest, the step that carried the probe, the captured document's Artifact hash and the full
Receipt list.

Two neighbours are close and the Receipt list tells all three apart. Where the value crossed
the network and came back in the response, the class is injection.markup and belongs to the
Playbook holding it: the trigger there is a parameter a recon pass saw the server reflect, and
the trigger here is a document with no such parameter. Where the page built a request path out
of the value rather than rendering it, the class is injection.client_path.

One reading is refused and both its grounds travel with it, because a refusal missing half its
reason gets re-proposed with the other half fixed. Proving that a listener's origin check
accepts a forged origin needs an origin whose NAME the run chooses, and hosting a second origin
is refused by standing decision on the capability card; it also needs an observation that a
handler acted on the body, which a dispatch cannot give, its outcome being dispatched alone.
Neither ground is a capability gap this ticket can close.

This Playbook plants one inert custom element with no script, no attribute a browser acts on
and no content, and reads one verdict. It does not frame the target, host a parent document, or
write a value the page keeps for a later visitor. A mission that hit its step ceiling or was
refused at the proxy is inconclusive and is reported as inconclusive; that halt is a reading
that ran out and names no question code, so it is reported through the Task's own record.

This section proposes and grades nothing. 7 of 7 steps cannot be graded.
