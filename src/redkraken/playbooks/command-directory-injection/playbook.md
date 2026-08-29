---
description: Ask whether a value the caller supplies is concatenated into a command line, by sending one separator with a token that would print, then one payload from each of three interpreter grammars, then a bounded delay beside an inert twin, and by reading an arrival on a declared channel where nothing comes back at all.
bb:category: injection
bb:outputs: ["injection.command"]
bb:triggers_all: ["file_parameter", "multipart_request", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: approval_required
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 53 as the v2 replacement for v1's command-directory-injection pack against the command leaf of the ticket 18 vocabulary; the pack's five pages are attached as maintainer references, two describe classes graded elsewhere, and every escalation step in the other three is refused by the closing section. Rewritten for ticket 101 against the merged ledger, which carries six procedures, one refusal and one blocked reading. Two keys moved and the arrival reading stops at an Observation. The supported variant row leaves timing_differential for response_differential, because five of this slug's six executable readings close on an echo or a shape the Test's own assertions carry and only one is a timing pair, so the shipped bar made five of them unclosable; the refuted variant row follows it, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes. The pre-211 sentence that a read_only selection sends no body is gone.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["command-injection-filter-bypass.md", "ldap-injections.md", "os-command-injection.md", "shells.md", "xxe.md"]
---

# Ask whether a shell read the value

Routes that accept a file rarely handle it themselves. They shell out, to a converter, a
thumbnailer, an archiver, a virus scanner, a font renderer, and the command line is built by
formatting. The easiest thing to format into it is a value the caller supplied.

Five of the eight sections below are procedures, each ending at one Test of three to thirty-two
actions holding at least one baseline, one variant and one control, because rk2_test_spec_problem
refuses a specification performing fewer than three or leaving a role out. The arms go out with
`mcp__rk2__http_request`, are filed as one specification with `mcp__rk2__propose_test`, and
close_test_replay closes them, marking BOTH legs of a comparison -- so a differencing assertion
below names its variant against the BASELINE or against another variant and never against a control,
which then closes as the response_invariant this Playbook's supported bar asks for. Since ticket 211
an action states its own `headers` and `body` beside its `method` and `url`, so a multipart upload
is an action and not only an exploration; a body is framing rather than an effect, and this
Playbook's read_only declaration never blocked one.

Two carriers exist and the order matters. A query or path parameter is preferred, because
record_test_action compares a Receipt to its action over method, scheme, host, port and path and not
the query, so two arms differing only in a query string are indistinguishable to that guard and the
specification should move a path segment too. Where the only carrier is the multipart filename, the
arms differ in the body. In both, rk2_test_request_problem refuses a literal dot or double-dot path
segment, the encoded-dot string anywhere in a url, and whitespace, so a newline rides the url
percent-encoded and never raw.

## 1. Name the endpoint, and get the grant this Playbook cannot give itself

This Playbook's risk is approval_required and the reason is narrow enough to state exactly: every
observation it makes runs a process on somebody else's host. Nothing it sends writes, stores or
persists, and it still executes. Whether a Program's rules admit that is not this document's
judgement, and the reading does not begin without an answer. Where the scope document does not
clearly admit it, ask for the Task to be parked with `mcp__rk2__park_for_human`, naming the Task
this run is executing in `task_label` and scope_ambiguous in `question_code`. The same code covers
the out-of-band sections below on a Program whose rules say nothing about a declared channel.
Complete it with the endpoint, the carrier and the grant; it closes no Test and grades nothing.

## 2. The cheapest question, which is whether the value comes back

One request answers this and no distribution has to be reasoned about. Baseline: the route with an
ordinary value, sent twice, the two sends asserted equal, which is the noise floor. Variant: the
same value followed by a statement separator and a token that would appear in output if a shell ran
it. Control: the same characters where they cannot separate, inside a quoted region or with the
separator replaced by an inert byte of the same length, which tells a shell from an echo.

The closing assertion says the variant differs from the baseline and a second says the control
equals it. File the echo beside it as an agent-filed reflected_input edge through
`mcp__rk2__submit_mission_result`, which promote_proposal writes, naming the encoding context the
bytes came back in. Where the token or a shell-shaped error is there the reading is done and no
later section runs.

## 3. Three grammars, because one silence is not a refutation

A route ignoring a semicolon may be running an interpreter where a semicolon is an ordinary
character, so a reading that tried one family and stopped has reported the separator rather than the
route. Baseline: the plain value, twice, asserted equal. Variant: three arms, one per family -- a
statement separator, a substitution, and a newline spelled percent-encoded in the url or literal in
the body. Control: the same value carrying a percent-encoded space in the identical position, same
encoding path, same length, a byte no shell acts on.

Each closing assertion says its variant differs from the baseline, and one says the control equals
it. The family that moves identifies the interpreter as well as the defect. Stop at the first family
that moves. Refuted needs all three families sent and the value echoed back byte for byte with its
characters intact; anything less is inconclusive and says so.

## 4. Filter or sink, in exactly one probe

This section runs only where the direct separator was already refused -- a client error, a scrubbed
echo, a message naming an invalid character. Baseline: the unfiltered request the route answered
normally. Variants: two -- the refused direct form, and one inert substitution of the blocked
character, a field separator variable where a space was refused, or one concatenation quote inside a
harmless word. Control: a second identical send of the baseline, named by no differencing assertion.
Neither spelling carries whitespace or an encoded dot, so both survive the checker.

The closing assertion says the substituted variant differs from the refused variant, and a second
says the substituted variant equals the unfiltered baseline. Together they say the route filters
characters instead of escaping them, which is the finding; getting past a filter is not itself a
result. One probe, then stop. Before proposing a second, answer what observation it produces that is
not already in hand; where that answer is the same differential through another encoding, skip it.

## 5. The delay pair, interleaved

Where nothing is echoed the remaining response-side signal is duration. Baseline: the ordinary
value, sent enough times to measure how long the route takes and how much that varies, because a
timing claim against an unmeasured distribution is one sample with an opinion attached. Variant: the
ordinary value with a separator and a bounded delay appended. Control: the same value, same length,
same separator characters, with the delay replaced by a command that does nothing. Both arms carry
the separator, so a filter stripping it strips it from both. Send them alternately rather than as
two blocks, five rounds and ten requests, because backend latency drifts and a block comparison
measures the drift; where the sets overlap after five rounds, run five more and stop there.

The closing assertion says the delayed arm differs from the baseline and a second says the inert
twin equals it. A route that shells out answers a delayed conversion differently -- a gateway cut, a
partial document, a failed-conversion page -- and that is what close_test_replay reads. No assertion
kind names a duration, so where neither moves the separation between the two sampled distributions
is filed as an agent-filed timing_differential over the Receipts' own waited values and the claim
stops at an Observation. Note the route's ceiling before choosing the delay, since both arms cut off
at a fixed gateway make a live injection read as refuted. Where the arms do not separate the answer
is more samples and then inconclusive, never a longer sleep.

## 6. Where nothing comes back at all, the proof is an arrival

Where the Program has a declared and bound out-of-band channel, mint a correlator with
`mcp__rk2__mint_callback`, naming the channel in `channel` and this reading in `subject_label`, then
send two arms with `mcp__rk2__http_request`. The first replaces the separator with an inert
character of the same length and carries the correlator hostname with no metacharacter, and must
bring nothing -- an arrival there means the value was fetched as a url, not executed, which is a
different finding. The second carries the separator and one fetch. The channel's own control arrival
is read for freshness only, because a control arrival has a null subject and writes no Observation.
Nothing here is a Test. The responses do not move, so an all-equality specification writes
response_invariant on every action while this Playbook grades a supported variant on
response_differential; and the arrival is not an action, so the pair is two arms where
rk2_test_spec_problem needs three. The claim stops at the callback_interaction Observation
record_callback_interaction writes from the arrival, and grades nothing. One arrival ends the
attempt. Silence against a fresh control arrival means the value reached no shell that can reach the
network; silence from a target with no egress is inconclusive rather than refuted.

Where the carrier is a header the leased Identity owns, plan this section on a Task with no leased
Identity and say so in the step. identity.Session.inject gives a leased Identity ownership of Cookie
and of every header it declares for the origin, so a plan-stated one is dropped before the wire.
That covers a token key identifier or another header the Identity supplies.

## 7. Where the validator and the sink are two different routes

Where a confirmed pollution oracle exists on one route and a second route reads a property the first
validates, the value can be written through a channel the validating route never inspects. Baseline:
the value posted directly as the named field on route A, which the validator refuses, and that
refusal is the whole premise. Variant: the same value written under the property path, then route B
called, then one arrival. Control: the same write carrying a value with no metacharacter, then route
B called, which must produce no arrival, so the arrival belongs to the metacharacter and not to the
fetch.

The closing assertion says the accepted property-path write differs from the refused direct write,
which makes this a claim about where validation lives, and the arrival is filed beside it. Where the
framework merges the query string into the same object the whole pair is a request line and that
spelling is tried first. This section writes a property on a shared object at the target, so before
the first write ask for the Task to be parked with `mcp__rk2__park_for_human`, again naming this
run's own Task in `task_label` and this time destructive_action in `question_code`. The write half
is authorization.object_property_write, which no Playbook emits; hand it on and keep the sink half.

## 8. State the claim, and name what this Playbook will not do next

The Hypothesis is injection.command on the endpoint, proposed with `mcp__rk2__propose_finding`
naming command_injection as its `vulnerability_class`, which takes a vulnerability_classes id and
not a dotted Property class. It is supported when the token came back, or a family separated from
its inert control, or an arrival landed against a silent twin. It is refuted when the value comes
back byte for byte with every separator intact, all three families are invariant and the timing arms
do not separate. Inconclusive covers a ceiling that truncates both arms, overlapping distributions,
and a route that queues the work and answers before it runs.

Two neighbours are close. Where the value reaches a query rather than a shell the class is
injection.query_language and the Playbook is sql-injection, which is where the attached LDAP page is
graded. Where it reaches a document parser -- an XML body, an image markup document, an office
document -- the class is injection.document_parser and the Playbook is structured-injection, which
is where the attached entity page is graded.

Escalation is refused permanently and for every route once a sink is proved. No payload writes a
file into a served directory, opens a listener, starts a process that outlives the request, chains a
second command once the first has answered, enumerates the host or reads a file off it, and no
database command primitive is enabled or called, because re-enabling a feature an administrator
disabled is not undone afterwards. The verdict was already reached by the separator that echoed or
the arrival that landed, and the report argues impact from what that sink permits. Where a Program's
rules admit an impact demonstration it is a separate authorised Task with its own grant.

One further reading is blocked rather than refused, and the distinction travels with it. Carrying
command output off the target inside a resolved name needs a channel whose placement is a label and
a publisher serving wildcard subdomains; the shipped file host serves one hostname and places the
correlator in the path, so a label-varying arrival carries no correlator. The path and query form is
buildable today and refused for what it is for. Halts that are only a reading running out name no
question code and are reported through the Task's own record.

This section performs and grades nothing. 3 of 8 steps cannot be graded.
