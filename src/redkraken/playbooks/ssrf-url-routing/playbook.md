---
description: Ask whether the authority a route validates is the authority it fetches, by moving one thing at a time between two hosts the Program controls and closing on a Test whose own assertions carry the difference between what was checked and what was opened.
bb:category: injection
bb:outputs: ["injection.url_authority"]
bb:triggers_all: ["authenticated_endpoint", "read_method", "url_valued_parameter"]
bb:skills: ["compare-responses", "handle-untrusted-content", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-04-15
bb:provenance: Written for ticket 54 as the v2 replacement for v1's ssrf-url-routing pack against a new url_authority leaf added by ticket 54, and rewritten for ticket 101 against the merged ledger's fourteen readings for this slug. Six are procedures here and eight are named in the closing section with the reason each is out, which is the change of shape. The refuted variant kind is response_differential rather than an invariant, because close_test_replay reads the Observation kind off the Test specification and not off the outcome, so a Test that named a differing assertion writes that kind whichever way it went.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["dns-rebinding.md", "open-redirection.md", "pdf-generators.md", "ssrf.md"]
---
# Ask whether the checker and the fetcher read the same URL

A route that fetches a URL a caller supplied has two pieces of code reading it:
the one that decides whether it is allowed and the one that opens the connection.
A defect exists wherever they disagree. Every reading below makes them disagree
about one thing, with both ends of the URL on hosts the Program controls.

Arms are sent with `mcp__rk2__http_request`, and an arm that settles a claim is an
action of a Test proposed with `mcp__rk2__propose_test`. The writer of a
settlement is close_test_replay, which derives the transition and the Observation
kind from the Test's assertions alone; an Observation filed through
`mcp__rk2__submit_mission_result` is a real evidence edge beside it and settles
nothing. That kind is read off the specification and not the outcome, so a Test
naming a differing assertion writes response_differential whether the arms
differed or not, which is why refuting this Playbook carries the kind that
supports it. Every Test holds at least three actions and fills all three roles --
baseline, variant and control. Since ticket 211 an action states the header and
the body it plans, while a setup or cleanup step still carries a method and a url
and nothing else.

## 1. Name the two hosts the Program allows

Read the route and its URL-valued parameter from the state view with
`mcp__rk2__get_attack_surface`, then name two hosts the Program has confirmed may
be pointed at, on different registrable domains, each answering a marked path.

Nothing else goes in that parameter: not loopback, not a link-local address, not
an RFC 1918 range, not a service address behind the target's boundary, not a port
list, not a metadata authority. Section 7 says where those readings go. No arm
spells a dot segment or a percent-encoded dot either, which the replay lane
refuses in a specification url. This step reads state and grades nothing.

## 2. Establish that the parameter is dereferenced at all

Before any confusion is spent on the parameter, ask whether it is fetched. The
baseline is an ordinary allowed URL sent twice unchanged, which is the shape of an
answer carrying a fetched document and the proof the route is byte-stable; every
section below reuses that pair. The variant is one controlled host on a path that
certainly answers and then a path that certainly does not, and the control is a
string that is not a URL at all, rk-not-a-url.

The Test names body_differs on the answering path against the missing one and
nothing else, which says the value was dereferenced and the outcome reached the
caller while leaving rk-not-a-url named by no differing assertion, the
response_invariant this Playbook's bar asks of the control role. That arm is a
precondition and not an assertion: a non-URL answering exactly as a failed fetch
is a route that validated and never fetched, and such a candidate is out before
the Test is proposed.

## 3. Put the two hosts where two parsers disagree

This is the claim the Playbook is named for. A prefix-matching validator looks for
the allowed host anywhere in the string; an RFC 3986 parser reads the authority
after the last userinfo separator. Two arms differ only in which controlled host
follows that separator: https://<allowed-host>@<controlled-a>/rk-probe and
https://<allowed-host>@<controlled-b>/rk-probe. Where userinfo is filtered,
substitute one named position at a time.

The baseline is that invariant pair; the control is the allowed URL sent once more
beside the arms, which must still answer, so an arm's refusal is the arm's and not
the route falling over. The Test names body_differs on one arm against the other
-- a difference between two marked documents, which a route that fetched neither
cannot produce -- and body_equals on the control against the baseline.

## 4. Ask what else the two readings disagree about

Only the scheme moves in the first. The baseline is http against the controlled
host, which works, sent twice; the variants are ftp and then dict against that
same authority, one per request; the control is rk-probe://<controlled-host>/, a
scheme no client library implements, whose failure gives the shape of unsupported
so it can be told from rejected by policy. The Test names body_differs on the ftp
arm against the http baseline and never against that control, which leaves the
control a response_invariant, and body_equals between the two baseline sends; the
report says which schemes answered.

The second is decoding depth, because a validator that reads the URL once and a
fetcher that decodes it again are two readings of one string. Encode one reserved
character in the controlled authority once, twice and three times -- `%40`,
`%2540`, `%252540`, or the same ladder on `%23`, `%3f`, `%2f` -- one depth per
request, never the dot. The baseline is the literal URL sent twice; the control is
an encoded value at the same depth decoding to something harmless on the same
host, which shows a decoding happened rather than the filter missing a longer
string. That Test names body_differs on the first depth fetched against the
literal baseline, and body_equals on the control against the depth beside it.

The third is the target's own redirector, where the check runs before the hop and
the fetch after it. The baseline is that redirector pointing at another allowed
path, sent twice: its content proves redirects are followed at all. The variant is
the same redirector with its destination set to controlled-host-a and then
controlled-host-b, differing only in which marked document the hop lands on. The
control is the parameter set directly at a controlled host with no redirector,
which must be refused -- that shows the redirector and not a permissive allowlist
doing the work. The Test names body_differs between the two hops and body_equals
on the direct control against the baseline, which leaves that control a
response_invariant.

## 5. The renderer, the correlator, and the person who approves it

A server-side renderer is a fetching engine inside the target's network, and a
document it converts can name a URL. Accepting that document is a write, since
stored markup renders again whenever anyone exports it, so park the Task first
with `mcp__rk2__park_for_human`, which carries that Task's label in `task_label`
beside a `question_code` of destructive_action, naming the route and what would be
stored. Parking closes the run, and nothing in this section is graded here. A
read-only selection still carries that document, because a body is framing rather
than an effect and the replay lane declares it from the Test specification itself.

Mint the address with `mcp__rk2__mint_callback`, naming the declared channel in
`channel` and this reading in `subject_label`, and embed it exactly as returned. The baseline is the document with
the reference removed, the variant the document carrying
https://<endpoint>/<correlator>/probe.txt, the control that reference-free
document submitted again. All three answer alike, which is the point and also this
reading's ceiling: no arm is named by a differing assertion, so nothing closes
response_differential, the variant row of this Playbook's bar goes unmet, and the
reading stops at an Observation on a claim that stays proposed. What carries it
arrives out of band. record_callback_interaction writes the arrival as
callback_interaction, evidential with callback provenance, and the channel's own
control arrival is minted subjectless inside the window, writing no Observation,
though without it a dead tunnel and an uninteresting target are one silence.

Silence is not a refutation: a window closing with a fresh control arrival and no
subject arrival is inconclusive, and a per-submission correlator is what makes any
arrival attributable, since exports fire from background jobs and retries. Stop
there, recording the correlator, the channel, the arrival's byte size and that the
document stays stored.

## 6. Difference the stored bytes, and state the claim

Run `compare-responses` over the two stored Artifacts with
`mcp__rk2__run_skill_script`, whose `first` and `second` are the two arms, and
cite what it returns. This section reads what the Test already settled and grades
nothing of its own. A differing assertion reads the response body digest alone,
so a volatile header changes nothing; an identifier stamped inside the BODY is the
real hazard, and where the route stamps one, difference a path that does not carry
it.

Propose the claim with `mcp__rk2__propose_finding`. The Hypothesis is
`injection.url_authority` on the route and the parameter. It is supported when the
arms differ as the Test asserted and the baseline pair was invariant; refuted when
the arms are invariant against each other while that baseline held; inconclusive
otherwise -- a route that answered neither arm, a baseline that moved, an arm
refused before the fetcher. Where the question is instead whether a request left
the process at all, answered by an arrival and not a response, the class is
injection.request_forgery and the reading belongs to the webhooks Playbook.

## 7. The ceiling, restated at the end

Eight readings are named here and performed nowhere.

Out of scope. The cloud metadata index, whose response SHAPE is a fair reading but
not this one, because pointing the target at a link-local address is refused here
at all; it belongs to `kubernetes`, which owns
information_disclosure.workload_metadata. The blind fetch proved by an arrival
alone, which is `webhooks` work under the neighbour rule above.

Refused. Internal addresses written decimal, octal, short-form or IPv6-mapped,
which read whether a denylist compares strings or resolved addresses, and a short
named port list against one internal authority: both are reconnaissance behind
somebody else's host, which an operator authorises rather than a reading takes.
DNS rebinding, which needs an authoritative nameserver we operate and a position
between two resolutions; a public rebinding service is no substitute, since it
routes the target's DNS through a third party nobody chose.

Blocked. The escalating chain of 3xx codes, because no tool contract is a
programmable responder and the channel receives arrivals without choosing a status
code. The renderer's engine-private element naming a local path, because the
produced document is stored and what is missing is a reader for it -- differencing
two renders is no substitute, since a renderer's output differs on every render.
Backend selection by a caller-written Host, blocked by construction rather than
policy: host is hop-by-hop at our own door, dropped and rebuilt from the authority
the door decided.

This section performs nothing and grades nothing. 4 of 7 steps cannot be graded.
