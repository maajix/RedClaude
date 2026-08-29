---
description: Ask whether an activity, audit or trace view hands one caller the request data of another, by having a second Identity send one marked read and then looking for that marker in the view the first Identity is served, with the second Identity's own view as the leg that says the marker was recorded at all.
bb:category: information_disclosure
bb:outputs: ["information_disclosure.log_record"]
bb:triggers_all: ["authenticated_endpoint", "multiple_test_identities", "tech_telemetry"]
bb:skills: ["browser-evidence", "compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-05-15
bb:provenance: Written for ticket 55 as the v2 replacement for v1's logging page against a new log_record leaf added by ticket 55; the v1 page carried no attachments, and its log-forging payloads, its log-file fetching and its alerting-evasion advice are refused by the closing section. Rewritten for ticket 101 against the merged ledger, which carries four readings here and grades none of them as reaching a Finding -- two refused by this Playbook's own decision and two that stop at an Observation. One key moved. bb:skills gains browser-evidence, because the HTML view is read by a browse run and the shipped text named the kind that run produces without naming the run. bb:evidence is unchanged and stays content_match on all three legs, which is what both lanes actually file; it is also a bar no closing writer produces, and the rewrite states that in the body as a standing defect rather than swapping in a kind no step of this Playbook can reach.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "content_match", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "content_match", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "content_match", "polarity": "supports", "min_count": 1}]
---

# Ask whose requests are in the record the application keeps

An application that keeps an activity trail keeps it about everybody. The view that shows it was
usually written to show a caller their own history, and the filter that makes it theirs is one
clause in one query. Where that clause is missing, the view is still called "your activity" and it
is the whole application's.

The subject is an authenticated read on an application a recon pass identified as running a logging
or telemetry backend, with two Identities the Program controls. The fingerprint is why this Playbook
was selected and it is not evidence: technology_identified is recorded as non-evidential, and a
backend that collects events says nothing about whether the application publishes them, to whom, or
with what in them. Name from the recorded surface rather than from a guess the route that returns
recent activity, audit entries or traces, and the two labels -- which one reads and which one is
read about. Reading under two Identities is reading two Tasks, because which Identity a call goes
out under is a property of the Tool run and never an argument of it.

Open with two identical sends of the view under the reading label, before anything is marked. An
activity view is the likeliest route on a target to differ between two sends: it is a list that
grows, and the second request is itself an entry in it. Whatever moved for that reason is not
evidence, and where the two sends already differ the whole reading is unreadable and stops there.
The marker used below is one opaque correlator token -- no separator, no newline, no control
character, no markup -- and that constraint is not a matter of taste; the closing section is where
it comes from.

State one thing at the top so no step reads as more than it is. Every section here is a LEAD. This
Playbook files Observations and closes no Test, and section 3 gives the reason in full rather than
leaving a reader to find it in a failure.

## 1. The marked read, and the search that reads it back out of JSON

This lane needs the view to answer JSON. One request goes out from the second label's Task: an
ordinary read that label is entitled to make, carrying one unique marker in one query parameter of a
route it may reach. Then the view again under the reading label. Then a jq run under
`mcp__rk2__run_tool` over the stored view Artifact, filtering for entries whose text contains the
marker.

Three legs decide what the result means, and without them the search says nothing. The two opening
sends must match, or the view moves on its own and no later comparison is readable. The second
label's OWN view must carry the marker, which is what says the entry was recorded at all rather than
not recorded anywhere. And a second jq run must find nothing at all for a nonce that was never
planted, which is what rules out a view echoing its own filter argument back into the page.

The product is one content_match filed through promote_proposal citing the jq run -- supporting
where the marker is in the reading label's view, refuting where it is absent while the planting
label's own view carries it, which is what one intact filter clause looks like. It goes in WITH the
proposal through `mcp__rk2__submit_mission_result`, because an edge cannot be added once a claim is
past proposed. Halt where the view served to the reading label carries a key, a token or a password
rather than a record of a request: stop reading the view, request no path the view names, and route
the material to the credential-material reading instead. Record the Receipt labels, the tool run
label and its exit code, the view Artifact digest, the marker value and which label the leaked entry
belongs to, and never the material itself. Where that first jq run exits 5 the view was not JSON,
and section 2 is the lane.

## 2. The same reading where the view answers HTML

The browser lane is the reader here. Under the reading label, one run navigates to the view, waits
for its list container, asserts the marker absent and captures the page: that is the before-reading
and it is one tool run. Then the marked read goes out from the second label's Task exactly as in
section 1. Then a second run navigates again, waits again, asserts the marker present, asserts a
never-planted nonce absent, and captures the page.

The paired present-and-absent assertion inside one run is what makes this a reading rather than two
captures and an offline comparison, and the never-planted nonce is the same echo control section 1
uses. The other control is unchanged: the second label's own view must show its own marker. The run
is driven with `mcp__rk2__browse`, and the five actions it uses are shipped enum members rather than
model-authored script.

The product is again one content_match, filed through promote_proposal citing the browse run. That
is admissible and not a stretch: a browse run is a tool run by its own foreign key, content_match
takes tool_run provenance, and the check on provenance reads the kind string rather than which tool
produced the run. Prefer this lane only where the view is HTML. Where a JSON representation of the
same view exists -- an API route behind the page, or an Accept-negotiated variant -- section 1 is
cheaper and its Artifact is easier for a later reader to re-read.

## 3. Why neither reading closes a Test, and what the Observations are still for

Both lanes stop at an Observation, and neither can carry the Hypothesis to supported on its own. The
reason is not the evidence kind and not the browser lane: it is the Identity pair. The two arms that
carry the whole differential -- the view under the reading label, and the same view under the label
that planted the marker -- differ only in which Identity sent them, and one Test run holds exactly
one Identity for its whole length. The run leases one, and every allowed Receipt of that run must
match it or carry none. So the two arms are two runs, and no single run's Receipt can settle the
claim.

rk2_finding_refusal will not open a Finding without a hypothesis_transitions row carrying
from_status testing and to_status supported, joined through test_run_receipts to the very run the
Finding cites. close_test_replay is the only writer of that row and derives it from one Test's own
assertions. Two runs cannot produce one, so there is no arrangement of these arms that opens a
Finding, and no step below should be written as though there were.

What the Observations ARE is real. rk2_promote_hypotheses writes a hypothesis_evidence edge from an
agent-supplied observation id with no filter on the cited kind, so a content_match from either lane
hangs off the Hypothesis and is visible to every later reader. An edge is not a transition. Record
the Hypothesis as carrying supporting evidence rather than as supported, name this section as the
reason, and hand the view, both marker values and every Artifact digest to the operator, so a person
decides whether it is worth a Program report. bb:evidence names content_match on all three legs,
which is exactly what both lanes file and is honest about this Playbook's product; it is also a bar
no closing writer produces, and that is a standing defect this section states rather than hides.

The three legs are named here and not only in the frontmatter, because a bar whose roles
live nowhere in the body is a bar no reader can check. The before-reading of either lane --
the view read under the reading label while no marker has been planted -- is the baseline.
The same view read after the planting label sent its marked read is the variant, and that is
the leg a supporting content_match fills where the marker is there and a refuting one fills
where it is absent. The planting label's own view is the control, and its content_match is
the supporting one that says the marker was recorded at all. What this Playbook lacks is not
a role but a Test, because the baseline and the variant differ only in Identity and one Test
run holds one Identity for its whole length.

## 4. What is refused, what a halt is asked for with, and what this Playbook never does

Two readings are refused here, permanently and by decision rather than by a gap. The first is making
the application write a record that is not true -- a value carrying a log delimiter, a newline, an
escape sequence, a format specifier or a structured fragment, so the writer reads it as a field of
its own. The reason is the sentence this Playbook was written with: a reading that made the
application write an entry that was not true has damaged the one record an operator will use
afterwards to work out what happened. Two neighbours fall to the same sentence and are named here so
they are not re-proposed one at a time -- fetching the log itself, which is the attack-surface
question and not this one, and alerting evasion, meaning varying the marker, spreading requests
under a threshold, or stripping the engagement header.

The second is a terminated statement planted in a header the application concatenates into an
analytics or audit insert, its second half resolving a correlator-bearing name so that an arrival on
the declared out-of-band channel is the only proof available on a sink that never reaches a
response. That reading is harness-reachable and such an arrival does carry a bar, so this is a
refusal and not a gap: it needs exactly the structured fragment the paragraph above forbids, and
this Playbook is read_only. Its home is the query-language Playbook, as an operator-directed step at
one named header and never a sweep. It is recorded with its reason so a later reader hands it over
rather than re-deriving it, and so the refusal is not mistaken for the older claim that nothing
could write its evidence.

Two halts are a person's decision, asked for with `mcp__rk2__park_for_human` carrying the label of
the Task this run is executing in `task_label` beside the `question_code` that names why. Requesting
a path found inside another caller's record addresses something the grant does not clearly admit, so
that halt parks under scope_ambiguous, before the request rather than after it. Where the entries
the view hands over belong to real users rather than to the Program's own test accounts, the reading
has read somebody who is not the Program's counterparty, and continuing parks under
third_party_impact. Every other halt here is a reading that ran out or a standing refusal, and none
of the five codes says that, so those go through the Task's own record.

Beyond that: this Playbook plants one opaque token in one query parameter and reads two views. It
does not fetch a log, does not write a second marker to see which one lands, does not vary the
marker to see what is filtered, and does not send anything a writer could read as structure.
`mcp__rk2__propose_finding` is not a step of it, because no reading in it reaches the transition
that call is gated on. Every section here is a lead, this one included. 4 of 4 steps cannot be
graded.
