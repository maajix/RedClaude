---
description: Ask whether a route's failure describes the process that had it rather than the input that caused it, and whether the same route tells an identifier that exists apart from one that does not, by moving one value at a time across three arms and closing on a Test whose own assertions carry the difference.
bb:category: information_disclosure
bb:outputs: ["information_disclosure.error_detail", "information_disclosure.identifier_oracle"]
bb:triggers_all: ["authenticated_endpoint", "quantity_valued_parameter", "read_method"]
bb:skills: ["compare-responses", "enumerate-surface", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-04-15
bb:provenance: Written for ticket 54 as the v2 replacement for v1's exceptional-conditions page against the error_detail leaf of the ticket 18 vocabulary, and rewritten for ticket 101 against the merged ledger's nine readings for this slug. The identifier_oracle leaf is added as a second output under operator decision D3, which puts the missing emitter inside this ticket; bb:triggers_all is unchanged, so the pre-auth readings are named for the surface they need rather than selected by it. Effects stay read_only and risk stays constrained, which is why the two readings that change the target are parked for a person before they run.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "error_detail", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "error_detail", "polarity": "supports", "min_count": 1}]
---
# Ask what the route says when it is surprised

A route that has decided what its inputs may be answers the same short sentence to
everything else. A route that has not decided lets the failure happen further in, and
whatever caught it says where it was: a file, a class, a query, a version, a host name.
The same route often answers a second question nobody asked: whether the identifier it
was handed exists at all.

Every arm is sent with `mcp__rk2__http_request`, and the arm that settles a claim is an
action of a Test proposed with `mcp__rk2__propose_test`. The writer of a settlement is
close_test_replay, which derives the transition and the Observation kind from the Test's
own assertions alone; an Observation filed through `mcp__rk2__submit_mission_result` is
a real edge beside it and settles nothing. Since ticket 211 an action states the header
and the body it plans, and the replay opens carrying that body. Every Test here performs
at least three actions and fills the baseline, variant and control roles, because one
missing a role is refused before it runs, and the control separates the target's
behaviour from the reading's. The error_detail rows the bar names are that kind of edge,
so each goes in WITH the proposal, in role variant, off a live send taken before the
Test: an edge cannot be added once a claim is past proposed.

## 1. Name the surface, then calibrate the route twice

Read the route and its parameter from the state view with
`mcp__rk2__get_attack_surface`, then name from the route's own behaviour rather than a
guess the type the parameter takes -- a count, a page size, an amount -- and the rule it
holds about that, a maximum, a minimum or a precision. Section 2 needs a value that
breaks each; sections 3 and 5 need one identifier that exists, two of the same shape
that do not, and a request count written first.

Arms differ in the path or the query string wherever the route offers it, and no arm
spells a dot segment or a percent-encoded dot: the replay lane refuses a specification
url carrying either, so such an arm is performable and ungradeable.

Then send the request with an ordinary value the route accepts, and send it again
unchanged. Both go out as whichever Identity the Task was opened under: the step does
not choose it and there is no argument for it, and where the subject takes no session
the reading belongs in a Task opened with no Identity. This Task performs the half its
own lease admits, and the other leaves as a `suggested_tasks` entry on
`mcp__rk2__submit_mission_result`; nothing re-leases a Task in flight. Everything below
is compared against that pair: a route that answers its own two differently is not one
this reading can difference, and that verdict is inconclusive and names the element that
moved. No differing assertion names them, so the replay writes response_invariant, which
is this Playbook's own declared control. This section closes no Test of its own and
grades nothing.

## 2. Failures of the type, against a failure of the rule

One request carrying a value of the right type that section 1's rule refuses -- a count
above the maximum, a page below the first, an amount with too many decimals -- and then
the same again, because a control that varies between its own sends is not one. Then two
variant arms whose values are not of the parameter's type at all and differ from each
other: the short words `all` and `none`.

One further pair in the same field asks which interpreter is behind it: `(1/0).zxy.zxy`
against its syntactically identical twin `(1/1).zxy.zxy`. If both raise identically the
field rejects punctuation and no evaluator was reached; the dots stay literal, which the
query string admits.

The Test names body_differs on one variant arm against the other. That assertion settles
the claim and makes both variant actions `response_differential`, while the baseline and
the rule-rejected control stay `response_invariant`. An engine or internal detail a
raise names goes in with the proposal as the variant's error_detail edge, and the Task
reopens against `ssti`, `nosql-injection` or `deserialization`.

## 3. Whether existence is distinguishable at all

Two spellings of one reading, whose question is distinguishability and never what any
record holds. Authenticated, under `use-identity`: the baseline is an identifier the
Task's own Identity created, the variant one of the same shape from outside any
plausible range, the control a second absent identifier. Pre-auth, under
`enumerate-surface`: the same three, the existing one designated by the Program. A
fourth arm carrying a malformed identifier separates "unknown" from "bad input", because
the route rejects it at its own regex before any lookup.

The Test names body_differs on the existing-identifier arm against an absent one, and
body_equals on the second absent arm against the first. The second assertion is the
whole reading: it says the difference is existence rather than the particular value.
What the existing-identifier arm says that an absent one does not -- a field name, a
count, a differently worded refusal -- goes in with the proposal as the variant's
error_detail edge. The identifier must ride the path or query for this to close; the
same oracle asked through a login body is section 5's.

Halt the moment an answer returns a record the reading did not create, and record that
as a halt and never as evidence. It and the declared count running out are readings that
ran out, not questions for a person: both go in the Task's own record.

## 4. Two carriers a Test action now states

Where the route carries a token whose decoded length is a multiple of 8 or 16 bytes, ask
whether the application tells "malformed ciphertext" apart from "ciphertext that
decrypted to somebody not allowed". Three arms: the token unmodified as the baseline;
one byte flipped in the last position of the second-to-last block, corrupting the final
block's padding, as the variant; one byte flipped in the first block, which corrupts
plaintext and leaves the padding valid, as the control, which must produce the
baseline's refusal rather than the variant's error -- a padding oracle apart from a
tampering error. The Test names status_differs on the padding flip against the
unmodified baseline and never against the first-block flip, so that control stays a
response_invariant. Both flips are spelled percent-safely, and detection is the stop:
recovery is 256 requests a byte and forging is a bypass.

Where the ciphertext is a cookie crumb this reading is planned without an identity slot,
in a Task that leases none, because a leased Identity owns Cookie and every header it
declares for the origin and replaces a planned one before the wire, so the mutated crumb
would never leave. The other half leaves as section 1's does, a `suggested_tasks` entry
on `mcp__rk2__submit_mission_result`.

The second carrier is a forwarding header, and the question is whether verbose output is
gated on one the caller writes. Three arms, each a request that already fails: the
baseline with no forwarding header, the variant with it set to the loopback literal the
application compares against, the control with it set to a routable address of the same
shape, which separates trust in the header from any reaction to its presence. The header
is neither hop-by-hop nor internally prefixed, so it forwards. The Test names
body_differs on the loopback arm against the no-header baseline and never against the
routable control, which leaves that control a response_invariant. The verbose text the
loopback arm returned goes in as the variant's error_detail edge, beside a
header_policy_observed edge naming the mechanism.

## 5. The readings that change the target, and the clock beside them

Two readings here store an object or lock an account, and this Playbook is read-only.
Before either is sent, park the Task with `mcp__rk2__park_for_human`, which wants the
label of the Task this run is executing in `task_label` beside a `question_code` of
destructive_action, quoting what the reading would change: the request may change state
at the target, and a person decides that rather than a step. Parking closes the run, so
the arms below belong to the Task a person opens next and nothing in this section is
graded here.

The first is the colliding object name. The baseline is a clean upload under a fresh
name, the variant one named after an object that exists, the control one named after an
object that does not -- without it a differing collision answer is just a differing
answer. The Test states the multipart body and the replay opens carrying it; where the
store takes the name in the path, prefer that spelling.

The second is the counter that names an account. N failed attempts against a synthetic
identifier are the baseline, N against the Program's designated identifier are the
variant, and the first answer of each series is the control: those two must agree, which
attributes a difference at the Nth to the counter and not the identifier. This reading
locks the designated account, and the report says so.

The clock rides beside them. Two series whose bodies are identical and whose durations
are not is a real reading, because Receipts carry the measurement. No assertion kind is
time-shaped, so nothing in a Test reads a duration and the series stops at a
`timing_differential` Observation on a claim that stays proposed.

## 6. Read what the arm said, and state the claim

Name in the variant's error_detail Observation which of these the arm carried, because
that quotation is the finding: a source path, a line number or a function name; an
exception class or a stack frame; a query, statement fragment or schema name; a
framework version, build string, host name or private address, quoted only far enough to
identify the leak.

Propose the claim with `mcp__rk2__propose_finding`, whose `vulnerability_class` takes a
vulnerability_classes id and never a dotted Property class: error_disclosure for
`information_disclosure.error_detail`, where the extra text is what a failure produced,
and sensitive_data_exposure for `information_disclosure.identifier_oracle`, where the
whole product is that existence was distinguishable. Either is supported when the
variant arms differ as their Test asserted, the calibration pair held, and the variant
carried something from the list above; refuted when those arms are invariant against a
stable baseline; inconclusive otherwise, most often behind a gateway that rewrites every
failure. Two neighbours are close: an always-returned field the contract never declared
is `information_disclosure.undeclared_field`, owned by `information-disclosure`, and a
key or token is `information_disclosure.credential_material`, owned by the secrets
Playbook. This section closes no Test of its own and grades nothing.

## 7. The ceiling

Outside the parked readings in section 5 this Playbook is read-only against a stable
session. It does not fuzz, does not send a wordlist, a long string, a deeply nested
document, a value chosen to consume memory or time, and does not repeat a failing
request under load. An arm a thousand characters long tests a different route, and
making the input stranger after a swallowed failure is looking for a way to hurt it.

This section performs and grades nothing. 4 of 7 steps cannot be graded.
