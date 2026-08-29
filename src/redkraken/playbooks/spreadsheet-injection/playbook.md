---
description: Ask whether the export writer emits a caller-chosen value into a cell without the leading apostrophe that would make it text, by fetching the export before anything is written, storing one record whose value begins with a formula character and one whose value does not, fetching the export twice more, and differencing the files so both new rows come back whole with the character before each still attached.
bb:category: injection
bb:outputs: ["injection.formula"]
bb:triggers_all: ["form_request", "reflected_parameter", "state_changing_method"]
bb:skills: ["compare-responses", "handle-untrusted-content", "use-identity"]
bb:risk: approval_required
bb:effects: mutates_object
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 53 as the v2 replacement for v1's spreadsheet-injection page, against a new formula leaf added by ticket 53 because the interpreter is the spreadsheet application on a reader's machine rather than anything the target runs; no upstream card. Rewritten for ticket 101 against the merged ledger, which carries one reading, one blocked container and one refusal for this slug and no row that reaches a Finding, which is why this document says so at the top. No mining shard targeted the slug, so the reading comes from this Playbook's own body and the OWASP page; a sweep of all 665 mined rows by text matched one, the OOXML importer, which is the blocked container named in the closing section. The shipped step 4 said the export is examined by a registered tool run and named none, and no registered tool matches a declared pattern inside one text Artifact, so the reading becomes a difference of two exports over compare-responses. Nothing in the frontmatter moved but the description and this line.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "content_match", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "content_match", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "content_match", "polarity": "supports", "min_count": 1}]
---

# Ask what the export will do on somebody else's machine

Every other reading in this category asks what the target's own interpreter does. This
one does not. The target stores a string and writes it into a file, and nothing on the
target evaluates anything. The interpreter is the spreadsheet application on the machine
of whoever opens the export, a colleague or an administrator or an analyst, and it
evaluates a cell beginning with `=`, `+`, `-` or `@` as a formula. So the defect is not
in the query, the shell or the template: the export writer emits a value the caller
chose into a cell without the leading apostrophe that would make it text.

**This Playbook produces a lead and never a Finding**, and that is a property of where
the answer lives rather than of the reading. The claim is which character stands
immediately before a marker inside a downloaded file, and the four things a Test can
assert are status_equals, status_differs, body_equals and body_differs. Since ticket 211
an action states its own headers and its own body, so the write is spellable now, and it
still does not help: the strongest assertion available over the post-write export is
that the file changed, which is true of any write at all. What carries the claim is an
offline difference of two stored Artifacts, and a Finding needs a transition from
testing to supported that only close_test_replay writes. So no step below is graded.
Each one names the verb that performs it and the runtime writer that records its result,
each ends at an Observation, the claim stays proposed, the report says exactly that, and
an operator decides what the lead is worth. No step proposes a Test, so nothing below
performs a baseline, variant or control action: the variant and control this
Playbook's bar names are Observation roles.

Every Observation is filed WITH the proposal through mcp__rk2__submit_mission_result,
which promote_proposal writes, because an edge cannot be added to a claim once it is
past proposed and this reading has nothing after the proposal to add one from. The bar
this Playbook declares is a content_match in the role variant and one in the role
control, which is what the tool runs of section 4 produce.

The subject is a state-changing endpoint taking a form body whose value a recon pass saw
reflected, together with an export route that serves it back.

## 1. Name the two routes, the field, and get the grant

This step is a lead and nothing grades its outcome. It reads the recorded surface with
mcp__rk2__get_attack_surface and writes no Observation, because naming a route is a
selection and not a reading.

Name three things: the route that stores the value, the field, and the route that
exports it. Where no export route is known this reading has no observation to make and
does not run, because the whole class lives in the file. Name the export's content type
as well, because this reading needs TEXT, a CSV or a TSV: compare-responses reads the
agent view of an Artifact, and a zip container is section 6's wall rather than a harder
version of this one.

This Playbook's risk is approval_required and its effects are mutates_object, and both
are honest rather than cautious. It stores a record. That record is a row in the
target's data, it will appear in their interface, and it may appear in somebody's inbox
or report. Ask for this Task to be parked with mcp__rk2__park_for_human, its label in
`task_label` and destructive_action in `question_code`, before the first write, name
the field and the two values, and let a person decide; a method outside GET, HEAD and
OPTIONS raises the call to approval_required under that same code at the door in any
case. A reading does not decide it by proceeding.

## 2. Fetch the export before anything is written

One mcp__rk2__http_request to the export route, as whichever Identity the Task was
opened under, and register_proxy_artifacts files the response as an Artifact against its
Receipt. This is the file without this reading's rows in it, it is what everything below
is a difference against, and it is taken FIRST because it cannot be reconstructed
afterwards. Nothing settles here: the fetch is the material the claim is later made of.

Do not read it as a response body. An export of a live application holds other people's
data, and a reading that scans it to find its own row is a reading looking at records it
has no business reading. Treat it as untrusted content, which is what
handle-untrusted-content is loaded for.

## 3. Write two records, and label them

Two more mcp__rk2__http_request sends, both as whichever Identity the Task was opened
under, since the step does not choose it, there is no argument for it, and nothing in
the claim is about who wrote the row. The variant is a value beginning with a formula
character followed by a marker unique to this reading. The control is a value beginning
with an ordinary character followed by a marker of the same length. OWASP names tab, a
carriage return, a line feed and the full-width variants alongside the four ordinary
formula characters; one of them, once, is the whole payload.

Both markers exist so the export can be searched for exactly these two rows and nothing
else. Make the records identifiable and removable in the target's own interface: a name
that says what it is, in a field a person can find. Each send returns its own Receipt.
The side effect is filed as a state_change Observation through
mcp__rk2__submit_mission_result, which promote_proposal writes, citing the Receipt of
the next section's fetch, because a later request is where a stored row becomes visible.
Nothing settles here either.

## 4. Fetch the export twice more, and difference the files

Two more mcp__rk2__http_request sends to the export route, stored as a second and a
third Artifact, with no write between them. The repeat policy is on the fetch and never
on the write: exports are generated, cached and regenerated on a schedule nobody told
this reading about, so one file is a claim about one generation of it, while a second
record is a second row somebody has to clean up.

Then two mcp__rk2__run_skill_script runs of compare-responses, in this order.
close_offline_tool_run files each run's output as its own Artifact. The first is the
control run, the third Artifact against the second, and it must answer that they are
identical; without it the lines the second run reports are as well explained by a
regeneration as by the write. Where the two disagree the export is not stable between
generations and the reading stops at inconclusive naming that. The second run is the
reading itself, the first Artifact against the second: only_in_second is the sorted list
of lines unique to the later file, and in a CSV a row is a line, so both written rows
come back whole with their leading characters attached. That list is the entire answer.

It answers two questions at once, which is why two records are written: the variant's
marker with the character immediately before it, and the control's marker with the
character immediately before it. A writer that prefixes every cell with an apostrophe,
and some do, uniformly, would otherwise look like a writer that neutralised this
particular formula. Comparing the variant's prefix against the control's separates one
value being escaped from every value being escaped, and only the first is a defence
against anything. File both readings as content_match Observations, role variant for the
formula row and role control for the ordinary row and for the identical answer, through
mcp__rk2__submit_mission_result, which promote_proposal writes. Where neither marker
appears in only_in_second, stop and report inconclusive: the export filters by date or
by owner, or the field is not in it. Do not write a third record to try again.

## 5. State the lead, and state what would refute it

The Hypothesis is `injection.formula` on the export route, and it stays proposed. The
evidence supports it when the variant's line begins with the formula character and the
control's line shows the writer added no prefix of its own, so the value goes into the
file exactly as it was stored. It refutes it when the variant's line arrives prefixed
with an apostrophe, or with its leading character stripped, while the control's does
not, which is a writer treating the formula character specifically. Each Observation is
filed with the polarity it carries, so the bar this Playbook declares is met if a
transition is ever attempted; this reading does not attempt one, and no step above
closes a Test that could.

Inconclusive covers an export no tool run can read, an export that does not contain the
stored field, an export that neither record reached, and an export that moved between
the second fetch and the third. Report the completion of this reading through this
Task's own record, together with the two rows the target has to clear, because none of
the five served question codes says that a reading finished.

One neighbour is close. Where the value is evaluated by the target itself rather than by
a reader's application, the class is `injection.template` and the Playbook is ssti. The
tell is where the evaluation happens: nothing here evaluates anything on the target, and
the response to section 3 is expected to be completely ordinary. Cite the three export
Artifact hashes, both compare-responses plan and result digests, the two values written
verbatim, and both markers with the character before each.

## 6. The ceiling, the container it cannot open, and the formula it will not write

This section performs and grades nothing. This Playbook writes exactly two records, into
one field, once. It does not sweep every field, does not repeat the write, and does not
delete anything afterwards, including its own rows, because deleting is a second
mutation and the report tells the target what to remove.

A binary container is blocked rather than dropped. Where the export is an XLSX, an ODS
or any other zip of XML, the cell sits in sheet XML inside an archive and nothing here
opens one: the registered offline tools are jq, js_map, js_parse, js_routes,
compare-responses and extract_paths, and a browse run backs a tool-run Observation but
navigates rather than unpacking a member. The dangerous half is that compare-responses
answers anyway, about flattened bytes that differ for compression and stored timestamps,
so a refutation read off that answer would be false. Halt before any tool run where the
export carries a zip, OOXML or OpenDocument content type or the stored bytes begin PK,
record the content type and the Artifact hash through this Task's own record, and say
that no tool run was opened against it. The capability that would lift this, an offline
tool extracting one named archive member as a text Artifact, also lifts the import side
of the same wall, which is `injection.document_parser`.

A formula that would act is refused, and does not resume. No HYPERLINK that sends a
cell's contents to a host, no WEBSERVICE or IMPORTXML that fetches one, no DDE or cmd
invocation, no macro. The formula character is followed by a marker and by nothing else.
What is being shown is that a cell begins with `=`; what a cell beginning with `=` could
contain is the report's argument. Every other reading in this category bounds what it
does to the target. This one would bound what it does to somebody who is not part of the
engagement at all, and no Program's rules of engagement reach the colleague who opens
the file, so a request for a live payload is parked with mcp__rk2__park_for_human, this
Task's label in `task_label` and third_party_impact in `question_code`, rather than
answered.

6 of 6 steps cannot be graded.
