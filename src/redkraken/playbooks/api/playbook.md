---
description: Ask what the limiter counts and what it counts against, by driving one declared sequence under one leased Identity and then re-driving it with a single key candidate moving -- the route as the caller spelled it, a forwarded address the caller writes, the account the attempt names, or the amount of work one legal request carries.
bb:category: rate_limiting
bb:outputs: ["rate_limiting.per_identity", "rate_limiting.per_origin", "rate_limiting.resource_cost"]
bb:triggers_all: ["api_surface", "multiple_test_identities"]
bb:skills: ["compare-responses", "enumerate-surface", "use-identity"]
bb:risk: approval_required
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-02-15
bb:provenance: Written for ticket 49 as the v2 replacement for v1's api pack, against the per-identity leaf of the ticket 18 vocabulary; the rate-limit-bypass text is the only one of the three v1 files that named a defect. Rewritten for ticket 101 against the merged ledger, which carries nine readings, one blocked and one refused for this slug. bb:outputs gains rate_limiting.per_origin and rate_limiting.resource_cost, the two emitters ticket 101 owes and the classes six of the eleven rows read; this Playbook holds the only rate_limiting category, so no other slug could carry them. bb:skills gains enumerate-surface, already held by the executing role. bb:evidence moves its refuted variant leg from response_differential to response_invariant, the kind the supported leg of the same role names, because an equalities-only sequence closes response_invariant for every variant action whichever way it settles; every section now leaves a variant action no differing assertion names.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_invariant", "polarity": "supports", "min_count": 1}]
bb:references: ["api-soap.md", "api.md", "rate-limit-bypass.md"]
---

# Ask what counts, and what it counts against

One API endpoint, one leased Identity, the same request several times. The first question is whether
the server keeps a count at all; every question after it is what the count is keyed on, and each is
answered by re-driving one sequence with a single candidate key moving. This Playbook spends
requests on purpose, so its risk floor is approval_required and the Program's grant a precondition.

Name the endpoint, the one Identity label and the exact count before the first request is sent.
Seven is the default, and the ceiling is the Test lane's rather than the target's:
rk2_test_spec_problem admits 3 to 32 actions in one specification and test_actions.ordinal is
checked against the same 32, so a section driving three sequences of N plus the two identical sends
admits N up to 10, and one driving four sequences admits N up to 7. Raise it only against a
documented published limit that is higher, record the document, and where that limit will not fit
drive the extra sequences as separate Tests over the one Hypothesis. A sequence that runs until
something happens has no refuting outcome, and gets a Program's access withdrawn.

Every reading is one Test of at least three actions holding a baseline, a variant and a control,
because rk2_test_spec_problem refuses fewer than three or a missing role. The arms go out with
`mcp__rk2__http_request` and are filed with `mcp__rk2__propose_test`. Since ticket 211 an action
states `headers` and `body` beside `method` and `url`, so a forwarded-address header and a batched
envelope ride the action itself; a wholly read_only selection may still carry one, because
authorize_egress_request reads that permission off the Tool run's own arguments. close_test_replay
settles the claim and derives each action's Observation kind from the specification alone: an action
a status_differs or body_differs assertion names, as its action or as its against, closes
response_differential, and every other action closes response_invariant. Both variant rows of
bb:evidence ask for response_invariant, so every section points its differing assertion at the
BASELINE and leaves at least one variant action named by no differing assertion, and every section
files the control row's credential_effect in role control from the Receipt of its control arm's
first send. That Observation and the timing_differential, header_policy_observed and content_match
Observations below are agent-filed and ride WITH the proposal through
`mcp__rk2__submit_mission_result`, because an edge cannot be added once a claim is past proposed.

Two things are read wrongly often enough to state here. body_equals and body_differs compare the
response body digest alone, so a volatile Date header does not defeat the comparison; a nonce inside
the body does, and the two identical sends measure that. And the layer the application answers at is
not the status line: a SOAP Fault and a GraphQL errors array both arrive as 200, so a run of Faults
reads as invariant while every request failed.

## 1. Whether repetition against one account is counted at all

Baseline, one request whose answer is confirmed to be the authenticated one and not a login redirect
or an anonymous view of the same route. The call goes out as whichever Identity the Task was opened
under; there is no argument for it. Variant, requests two to N, byte-identical, same Task, same
Identity, where the only thing moving is how many have been sent. Two controls: that first request
sent twice back to back before the sequence opens, whose difference is the noise floor no later
reading may sit below, and on a credential-verifying route one malformed value that must answer
DIFFERENTLY, saying the endpoint discriminates inputs at all. The support here is INVARIANCE, so the
specification names the sequence actions with status_equals against action one and no variant action
in a differing assertion; its single status_differs assertion names the malformed control against
action one. Every variant action therefore closes response_invariant, the kind both variant rows ask
for, and the reading settles either way -- the equalities holding is the support, one of them
failing is the refutation and says a limit engaged. Send the sequence one at a time and stop on the
first differing answer. A run of identical 401s is invariant too, which is why the control matters.

## 2. Whether the count is keyed on the route as the caller spelled it

Baseline, N identical requests to one exact spelling under one Identity, driven until the limit
engages; the ordinal it engaged at is the whole measurement. Variant, the same N under the same
Identity where each request restates the same resource differently and equivalently -- a trailing
slash, one fresh throwaway query parameter, a case change in a path segment. Control, a third run of
N at one spelling, which must still engage at the same ordinal and separates a mis-keyed counter
from an expired window; plus the two sends. status_differs naming the last action of the rotated run
against the last action of the BASELINE run is what close_test_replay closes. Two rules of the Test
lane travel with this section. rk2_test_request_problem refuses any dot or double-dot path segment
and any percent-encoded dot in a specification url, so those spellings this Playbook may SEND and
may not TEST; the trailing slash and the throwaway parameter are what it is written with. And since
ticket 214 record_test_action compares a Receipt to its action over the query, the planned header
block and the body as well as over method, scheme, host, port and path, so a decorated spelling
records as itself. Halt where the decorated spelling answers a different route or a 404.

## 3. Whether the count is keyed on an address the caller writes

Where the baseline reaches no refusal there is no limit to be mis-keyed, and the finding is a
missing limit -- section 1's reading, not this one. Baseline, the declared budget of identical
requests with no forwarded-address header, recording the ordinal at which the answer first changes
-- a 429, a Retry-After, a rate-limit header appearing, a body saying the quota is spent. Variant,
the same budget with one forwarded-address header incrementing per request. Two controls: the same
budget with that header held CONSTANT, which must still refuse at the same ordinal, and the two
identical sends. Without the constant-header arm a counter keyed on the forwarded address cannot be
told from a limiter the header's presence disabled, or from a window that expired. status_differs
naming the last action of the rotating run against the last action of the baseline run is what
close_test_replay closes. The header reaches the target: the forwarded-address names are in neither
the hop-by-hop set nor the internal prefix, and an IPv4 literal is printable. The rate-limit headers
come back too, only six response header names being stripped from the agent view, so the refusal
that did not arrive is readable and header_policy_observed is the agent-filed mechanism edge. One
further control decides whether the claim may be made at all: repeat the rotated run with an
unrelated header rotating instead, and where that also resets the counter the reading is
inconclusive. The class is `rate_limiting.per_origin`.

## 4. What one request costs, rather than how many are allowed

Baseline, k separate requests each carrying one unit of work -- one identifier, one named relation,
a page size of one -- under the same Identity, which is what the limiter is supposed to be counting
and whose Receipts carry the elapsed measurement. Variant, one request carrying many units of the
same work -- many identifiers in the query string, a repeated key, every relation at once, or a
document carrying the same operation k times under aliases or as an array -- sent twice back to
back, the pair being this arm's own noise floor. Two controls: the single-operation envelope, which
must not be refused and must answer with one result, which says the envelope is parsed at all and
attributes a k-result answer to batching rather than to an expired limiter; and the two identical
sends of one single-unit request. status_differs naming the FIRST of the two many-unit sends against
the last of the k baseline singles is what close_test_replay closes, and the second many-unit send,
named by nothing, is the variant rows' edge. timing_differential over the two Receipts is the
agent-filed mechanism edge, and where the answer counts its own results a jq or js_parse run under
`mcp__rk2__run_tool` -- or a browse run, a tool run by its own key -- carries the count as a
content_match. Stop at the declared k and never raise it: this reading proves the absence of a bound
with one oversized request, not with concurrency or a larger k. The class here is
`rate_limiting.resource_cost`.

## 5. Whether the limiter gates the value or only relabels the failure

This reading needs a leased Identity actually issued the value the endpoint verifies -- a one-time
code, a recovery code, a coupon -- and it reaches a Finding where that value rides the request line.
Baseline, wrong values submitted until the endpoint starts refusing; that refusal is what "the
limiter is up" means for everything after it. Variant, two actions: the value this Identity actually
received, whose success says the limiter relabelled the failures and never gated the verification,
and then one further WRONG value, answered exactly as the baseline refusal was -- if it succeeds the
limiter expired across the correct submission and the reading proves nothing. Control, the baseline
request sent twice unchanged before the sequence opens, whose difference is the noise floor.
status_differs naming the correct-value action against the last baseline refusal is what
close_test_replay closes; the trailing wrong value is named only by a status_equals against that
same refusal, so it closes response_invariant and carries the variant rows. credential_effect is the
mechanism edge either way. Stop after the correct submission and its trailing wrong value: no second
correct value and no exploring of the value space, and the record states that the only correct value
used was the one this Identity was issued.

## 6. Whether the failed-attempt counter is keyed to the account rather than the caller

This reading needs at least three identifiers the Program NAMES as existing and a declared count
from the application's own policy or from stepping the first series. The Task's Identity is fixed
for its whole length, which makes the caller one origin. Baseline, the declared count of failed
attempts against ONE named account, recording the ordinal at which the answer becomes a 429, a
captcha or a locked-account message. Variant, the same number spread one each across that many
different named accounts, where the ordinary refusal at the last attempt is the class. Two controls:
the same number of requests from the same caller carrying a VALID credential, or that many reads of
a cheap authenticated page, saying whether a generic per-origin limit engaged and the account
counter was never measured; and the two sends. status_differs naming the last send of the spread
series against the last of the single-account baseline series is what close_test_replay closes. Halt
the moment any account in the spread series locks, name each one touched, and send nothing further.

## 7. Propose the claim, name where a reading halts, and state what is refused

Propose it with `mcp__rk2__propose_finding`, naming auth_rate_limit_missing as its
`vulnerability_class` for sections 1, 2, 5 and 6, whose class is rate_limiting.per_identity, and
resource_exhaustion for sections 3 and 4, whose classes are rate_limiting.per_origin and
rate_limiting.resource_cost: that argument takes a vulnerability_classes id and never a dotted
Property class, and property_class_vulnerability_classes maps all three outputs onto those two. The
gate is rk2_finding_refusal, which opens nothing without the transition close_test_replay wrote.

Three halts are a person's decision, asked for with `mcp__rk2__park_for_human` carrying the Task's
own `task_label` and the `question_code` naming why. An account locking under section 6 changes the
subject, so that halt parks under destructive_action. Sections 2, 3 and 6 double the volume against
a target already known to be counting, so where the Program's grant does not name that volume the
halt parks under scope_ambiguous. An arm needing a verified value the Program never issued to a test
Identity parks under credential_needed. Every other halt is a reading that ran out -- the declared
count reached, the limit engaging, the batch's cost stepping past the control -- and none of the
five codes says that, so those go through the Task's own record with the ordinal.

One reading is blocked. A value reaching a sink in the PAGE whose cost is superlinear in its input
-- a regular expression made to backtrack, a degenerate comparator, a quadratic storage write -- is
a cost the browser pays and not the server, and no elapsed-time quantity exists over a browse run's
steps; the HTTP Receipt's own wait measures a different interval. Recorded rather than dropped: one
assertable elapsed quantity on a browse step is all it needs.

One reading is refused, permanently and by decision rather than by a gap. Deliberate exhaustion of a
live subject to measure what it costs -- an archive that expands enormously, an image whose declared
dimensions allocate gigabytes, nested entity definitions that expand multiplicatively -- can only be
read by degrading the subject, and NIST SP 800-115 grades a technique by its risk to the target. The
half that costs nothing stays in section 4: the limits read off the rejection of an oversized input.

Beyond that: this Playbook creates no objects to count, does not retry against a second Identity to
see whether a counter is shared, and does not send a sequence again. Its baseline is stable_session,
because rotating the session underneath it would turn one sequence into several. This section
proposes and refuses and runs no Test, so it grades nothing. 1 of 7 steps cannot be graded.
