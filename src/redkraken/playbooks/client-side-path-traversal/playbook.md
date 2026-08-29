---
description: Ask whether a page builds the path of a request it makes out of a segment the caller supplied, by reading the served bundle for a route the code composes, loading the page with an encoded traversing segment, and differencing the request lines the browser's own Receipts recorded; every reading here stops at an Observation, because the differential lives in a mission or a tool run and the only kind of Test action is a request.
bb:category: injection
bb:outputs: ["injection.client_path"]
bb:triggers_all: ["path_parameter", "read_method", "web_surface"]
bb:skills: ["browser-evidence", "compare-responses"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 against a new client-path leaf added by ticket 52; v1 covered this topic in prose under its client-side pack and shipped no reference text for it, so nothing is attached rather than a placeholder. Rewritten for ticket 101 against the merged ledger, whose three readings for this slug are all observation_only -- the differential lives in a browse mission or in a tool run and TEST_ACTION_KINDS admits a request alone, so no section closes a Test and none promises a Finding. One key moved. bb:skills gains compare-responses, which the two-request half of the cache-key lead needs and which the executing role already holds; the source-reading Skill the bundle census would otherwise name is not one that role loads, so the census is written as the two granted programs and nothing else. bb:outputs is unchanged, the census producing a precondition rather than a class. The refuted variant row moves from response_invariant to response_differential, the kind the supported row of that same role names.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
---

# The request the page made, not the one the mission sent

A single-document application decides its own routes. It reads a segment out of
the address bar, builds an API path from it, and fetches that. The segment is
caller-controlled and the concatenation is unguarded, so a segment carrying a
traversal moves the request the page makes -- one the caller never named and
the page never meant to call.

None of that is visible in the answer to the page load. The evidence is the
request the browser made afterwards, which is why every reading below is a
mission or a tool run rather than an exchange, and why every one of them stops
at an Observation. A browse run is not a Test action, the one action kind a
specification admits being a request, and close_test_replay is the only writer
of a transition from testing to supported. The Observations here are real edges
on the Hypothesis, filed in the baseline, variant and control roles the bar
names through `mcp__rk2__submit_mission_result`, which promote_proposal writes.
None of them opens a Finding, and no section here promises one.

## 1. Read the bundle the application serves, before spending a mission

The routes a page composes are readable in the JavaScript the application
serves, and reading them first turns a traversal mission from a spray into an
aimed reading. Fetch the served bundles with `mcp__rk2__http_request`, then run
`mcp__rk2__run_tool` over what they stored. `js_routes` returns the request
paths the code composes, and the baseline is that list with every path marked
as a constant or as a concatenation and every concatenated segment marked with
the source it is built from. The variant is `js_map` over the same bundles,
resolving each composed path back to its authoring position and keeping only
those whose segment traces to a caller-reachable source -- a route parameter, a
query string, a fragment. Those are the routes a mission is worth spending on.

Two controls. The same two runs over a bundle the application serves that
composes no route at all, a vendor chunk or a polyfill, which must return none,
since a list of every path-shaped literal in a bundle is the tool's ordinary
output and not a finding. And the same bundle fetched twice with the two runs
compared, invariant, so a chunk name that rotates per deploy is not read as a
changed route set.

The kind is content_match, whose provenance is a tool run, and its product is
the precondition of the claim rather than the claim -- that a composition sink
exists on this subject at all. No tool run is a Test action, so this section is
a lead and grades nothing. Its refutation is worth as much as its support,
since a bundle whose every request path is a constant refutes this Playbook's
premise here at the cost of two tool runs and no request past fetching the
bundle. The Skill that reads source as source is not one this role loads, so
the census is those two programs and nothing else; a model that reads the
bundle by eye has produced no Observation at all. A bundle the door refuses, a
parse failure returned in place of a route list, or a bundle past what one run
will read ends the census with the tool's own failure text recorded, and that
halt is a reading that ran out.

## 2. The mission that moves the request the page makes

Plan one mission with `mcp__rk2__browse` whose `steps` navigate to the recorded
route with the segment carrying the ordinary value the page's own links use,
wait for the settled state, and capture the document. Read the mission's
Receipts and record the second one's request line -- the route the page built,
and the position of the segment inside it. That is the baseline. A page that
issues no same-origin sub-request has no sink here and the reading ends.

The variant is the identical mission with only the segment replaced by one
encoded traversal spelling, `%2e%2e%2f` and its case-shifted and double-encoded
forms, so the sequence survives the browser's own normalisation and arrives at
the page's script as characters rather than as a resolved path. One spelling
per mission -- a mission that sent four is a mission whose Receipts cannot say
which one worked. The control is a third mission byte-identical to the
baseline, run separately, whose Receipts must name the route the baseline's
named. Without that pair a differing request line is a page choosing its own
route from a cache-busting segment, a rotating shard or a feature flag, and not
a traversal at all.

The comparison is over the request lines the Receipts recorded and never over
the document the page loaded, because the differential is in the request the
page made and not in the answer it got. A route the control mission did not
name is that differential. The same route with the traversal still encoded
inside the segment is the refutation, and it is filed under the kind the
support carries, because the bar asks the variant role for one kind whichever
way the reading comes out and the reading is one difference of two request
lines either way. Nothing requested, or an error before the fetch, is
inconclusive and says so.

A Receipt naming a host that is not the recorded origin is where this stops.
Send no further spelling, do not widen the segment, and ask for the Task to be
parked with `mcp__rk2__park_for_human`, which is refused without both of its
values: the label of the Task this run is executing in `task_label`, and
scope_ambiguous in `question_code`, because a route the page was steered onto
is not a route the scope document was read against. A mission that hit its step
ceiling or was refused at the door is inconclusive and is recorded as
inconclusive, which is a reading that ran out and names no code.

## 3. The moved request that a shared cache keys as public

Where an edge keys on an extension or on a static path prefix, the route the
page was steered onto may be one an unauthenticated caller reads afterwards.
The baseline is a plain GET of the static-looking path, /v1/token.css being the
shape, sent twice back to back with `mcp__rk2__http_request` and invariant;
without that pair a later difference is an origin varying its own error page.
It goes out from a Task holding no leased Identity, because a leased one owns
Cookie and every header it declares and would put a credential on the one
request whose whole point is carrying none. The egress verb states a `method`,
a `url`, `headers` and a `body` and no identity at all.

The variant is the mission of section 2 with its traversal segment ending in
that static-looking suffix, so the page's own authenticated fetch lands on the
keyed path, followed by the same unauthenticated GET again. An answer now
carrying the authenticated document is that answer stored under a key anyone
can reach, filed as a state_change Observation in the variant role beside the
mission's own request-line differential in the control role. The control is a
sibling static-looking path the mission never steered onto, which must stay
refused -- answered otherwise, the path was public already and the traversal
proved nothing.

This is the client half of a chain and not the whole of it. What this Playbook
claims is `injection.client_path` and it stops at the moved request line; an
authenticated answer served to a caller who did not authenticate is
`information_disclosure.cached_response`, which web-cache owns, and the two are
two claims rather than one. It is also the one place this Playbook's read_only
effects are not the whole truth, since priming a shared cache changes state at
the edge for whoever reads it next, so the priming mission is not sent on this
Playbook's own authority -- ask for it first with `mcp__rk2__park_for_human`,
carrying the label of the Task this run is executing in `task_label` and
destructive_action in `question_code`. Where the unauthenticated GET returns a
document belonging to another principal the run stops whole, the operator is
told at once with the cache key, no field of the document is read, and the halt
is parked the same way, with third_party_impact for the code.

## 4. State the claim, state the ceiling, and name what this is not

The Hypothesis is `injection.client_path` on the page, and what carries it is
the Observations the sections above file, in the roles the bar names. What
those Observations cannot do is close it. A Finding is opened against a closed
Test run, a Test action is a request, and a reading whose whole differential
lives in a mission or in a tool run therefore reaches the evidence and stops
there. This Playbook does not call `mcp__rk2__propose_finding`, which is
refused for the transition it cannot cite. The claim, both Receipt lists
verbatim, the spelling sent and the route the page requested go into the Task's
own record, which is also where a reading that ran out is reported.

What this is not is a filesystem. A segment reaching a file or an object store
on the server is `injection.path`, a different class held by a different
Playbook. Here the server does exactly what its routing table says, and the
page asked the wrong question. A rendered error message is not the reading and
neither is a screenshot of one.

One segment, one route, on the origin the recon pass recorded. The traversal
does not walk upward until something answers, does not enumerate routes from a
wordlist, which is a recon Playbook's work, and is not aimed at another host; a
segment that would move the request off the recorded origin is not sent. Every
mission goes through the same door and under the same scope decision as a
hand-written exchange.

This section runs no Test and grades nothing. 4 of 4 steps cannot be graded.
