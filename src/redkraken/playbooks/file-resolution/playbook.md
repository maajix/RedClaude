---
description: Ask where a path-valued parameter's read landed rather than what its string contained, by naming two different documents outside the directory a route serves, climbing to find where it roots the path, asking whether its guard strips once or to a fixed point, and asking whether the resolved name reaches a stream API at all.
bb:category: injection
bb:outputs: ["injection.path"]
bb:triggers_all: ["authenticated_endpoint", "path_valued_parameter", "read_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-04-15
bb:provenance: Written for ticket 54 as the v2 replacement for v1's file-resolution pack against the path leaf of the ticket 18 vocabulary; the pack's three pages are attached as maintainer references and their chains and their read-until-you-find-a-key advice are refused by the last section. Rewritten for ticket 101 against the merged ledger, which carries five readings and three refusals for this slug; three of the five are new. One key moved. The refuted variant row named response_invariant while the supported row of the same role names response_differential, and one role writes one kind whichever way a reading goes, so the refuted row now names response_differential too. The stored-path reading keeps bb:effects read_only by parking before its write rather than performing it.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["lfi.md", "path-traversal-encoding-variants.md", "php-filter-chain-lfi-rce.md"]
---

# Ask where the read landed

Every route that serves a document by name resolves a string to a location. Normalising the string
is not the check. The check is where the resolution landed, and a route that never asks will read
whatever the caller's string points at.

The subject is an authenticated read endpoint carrying a parameter a recon pass typed as a path, and
five readings ask five questions of it. Before the first arm, read the parameter through
`mcp__rk2__get_attack_surface` and say what the route is meant to serve because "outside" is
meaningless without it and a reading that cannot name the boundary is not reading this class.

Every request goes out through `mcp__rk2__http_request` and every specification is proposed with
`mcp__rk2__propose_test`; close_test_replay is the only writer of the transition a Finding needs
and derives both the verdict and the Observation kind from a Test's own assertions.

**Every closing Test has the same shape.** Actions 1 and 2 carry role `baseline`: the route's ordinary
request, sent twice unchanged, asserted `body_equals`. One or two carry role `control`, each asserted
`body_equals` against the action it must match or named by no assertion at all. Two carry role `variant`,
and the single `body_differs` names one against the other. Only variant actions are named by a differing
assertion, which leaves every control a `response_invariant` and every variant a `response_differential`.
A specification holds three to thirty-two actions and all three roles, or it is refused before it runs.

**One spelling wall decides where the traversal rides.** A specification url carries no path segment
that is `.` or `..` and no `%2e` anywhere, query included, and the segment rule tests the path
alone. So a traversal spelled with literal dots in the QUERY is closeable by a Test;
percent-encoded, or moved into the path, it is not, and those two spellings are leads whose product
is an agent-filed Observation. The arms then differ only in the query, which the runtime does not
compare when it binds a Receipt to an action, so record each arm's Receipt immediately after its own
send and never in a batch.

## 1. Ask where the read landed

Send the request with the parameter naming a document the route is meant to serve, then send it
again unchanged. Both go out as whichever Identity the Task was opened under: the step does not
choose it and there is no argument for it. Those two sends are actions 1 and 2 of every
specification below.

Then two requests leaving the directory and naming two DIFFERENT documents outside it:
`/etc/hostname`, `/proc/version`, a framework `VERSION` file, the application's own `README`. Both
ride the query, both spelled with literal dots. They are the two variant actions and the
`body_differs` names one against the other: a single traversal that returns something has to be
compared with something, and where the route resolved both, the answers differ as no refusal would.
Both targets are dull on purpose.

The first control CONTAINS a traversal and resolves back inside -- `notes/../report.txt`, where
`report.txt` is the baseline's document -- asserted `body_equals` against action 1. A route that
rejects it is matching the string's syntax rather than the resolution, and it stops the commonest
false positive here, reporting the presence of `..` in an accepted value. The second control is a
document outside the directory whose leaf exists nowhere, same shape and depth, and it settles what
the arms cannot: an error page quoting the name, a router that mapped the string elsewhere, a cache
that keyed on it. No assertion names it, because one would make it a `response_differential` and the
bar wants the control invariant.

Interleave with the baseline and send two rounds of the pair. Where an arm returns a document that is not
the dull file it named -- a key, a `.env`, a session store, source code -- do not store a second copy and
do not widen the read: call `mcp__rk2__park_for_human` with this run's own Task in `task_label` and
`question_code` scope_ambiguous, naming the arm, the path and the Artifact id, because whether a reading
continues against a target that has spilled credential material is a person's decision.

## 2. Ask where the route roots the path

Climb one segment at a time through `mcp__rk2__http_request` until the dull file answers, stopping
at six depths or at a plausible filesystem root: a climb that never changes is a route that does not
resolve, and further depth is a wordlist. The depth values live in the query, so every depth is
expressible in a specification.

One Test closes it. The two baseline sends are actions 1 and 2. The two variants are the winning
depth and the same depth with a leaf that certainly does not exist, `body_differs` naming one
against the other: that pair shows the answer tracks the filesystem rather than the segment count.
The control is the identical climb preceded by the directory prefix the route publishes, which says
whether a strip list or an anchored join is doing the work. `close_test_replay` writes the verdict
and both Observations.

## 3. Ask whether the guard strips once or to a fixed point

Only where the plain form was refused. The refusal is the precondition, not the obstacle: where
`../` already resolves, section 1 is the reading and this one is not.

The two variants are the plain `../<dull-file>`, which the route refuses, and `....//<dull-file>`,
which a single non-recursive replacement of `../` turns into the plain form after the check has
already run; the `body_differs` names one against the other, and that difference is the whole claim.
`..././<dull-file>` is the same defect spelled the other way and gets its own specification. The
control is `....X//<dull-file>` -- same length, same character classes, one byte no strip rule
removes -- asserted `body_equals` against the plain refusal. Where it answers like the reassembling
arm instead, the difference was length or shape.

These are query values, not path segments, so the specification's dot rule does not fire. Never
re-spell this arm with `%2e`: the reassembly it asks about happens in the target's strip rule, and
an encoding moves the question while making the Test unopenable. Halt at the accept/reject boundary
-- no climbing, no added depth, no second file -- and record the boundary in the Task's own record.
The guard and the resolver reading one string differently is `injection.parser_differential`, handed
to `browser-script`, which emits that class since ticket 101; this reading claims `injection.path`.

## 4. Ask whether the resolved name reaches a stream API

Only where a PHP runtime is already suggested by an error shape or a banner, and only as the
acceptance question: this is the one place the ceiling below admits a wrapper, admitted because the
arm discloses nothing the reading did not already hold. Name
`php://filter/convert.base64-encode/resource=` with the route's OWN served document as the resource;
if the wrapper is honoured the body is the base64 of the baseline body, this reading's own bytes in
another encoding. That arm and the same wrapper naming a resource that does not exist are the two
variants, `body_differs` naming one against the other. The control is `php://nonsuch`, a scheme PHP
does not register, which must answer like a miss. The Test closes on the differing assertion and
needs no decode.

Where the base64 is decoded for the report, `jq` cannot read it -- a filter and an input, no raw-input
flag, and this body is not JSON -- so the reader is a browse run through `mcp__rk2__browse`, a tool run
by foreign key, backing a content_match filed with the proposal through
`mcp__rk2__submit_mission_result` and written by promote_proposal. That citation settles nothing.

## 5. Ask whether a stored value becomes a later route's location

Its trigger is not `path_valued_parameter`: no path in the request resolves, which is why
single-request scanning misses it. It needs a persisted field, a second route that derives a
filesystem location from it, and three accounts the Program controls. Account A stores an ordinary
value, account B one that traverses out of the per-user directory to a dull file, account C one of
the same length and shape that traverses and comes back.

**This section is a lead of this Playbook and grades nothing.** The store is a write and this Playbook is
read_only, so do not send it here: call `mcp__rk2__park_for_human` with this Task in `task_label` and
`question_code` destructive_action, naming the field, the three values and the route. Parking closes the
run, so the write, the fetches below and the Test that closes them are graded elsewhere.

Only the derived-asset fetches are Test actions, and the accounts' asset urls have to DIFFER,
because that url difference is the whole request-line differential; where both read one url and only
the Identity differs, a run holds one Identity for its length and the reading falls back to an
agent-filed Observation. A's two fetches are the baseline pair; B's and C's are the two variants,
`body_differs` naming one against the other; A's third fetch is the control, asserted `body_equals`
against action 1. C answering like B says the route reacts to the shape of the stored string rather
than resolving it. Restore every stored value through the application's own route and read it back
before the reading is reported.

## 6. State the claim, and state what would refute it

The Hypothesis is `injection.path` on the endpoint, proposed through `mcp__rk2__propose_finding`
once close_test_replay has carried it to supported. It is supported when the two out-of-directory
arms differ from each other in both rounds, the baseline was invariant, the normalising control
answered like an ordinary request, and the nonexistent-leaf control did not reproduce the arms. It
is refuted when the two arms are invariant against each other against a stable baseline: the
resolution was checked and both names landed in one refusal, whether that refusal is a `404`, a
`403` or a `200` carrying the default document. This section runs no Test and grades nothing.

Three neighbours are close. Where the resolution happens in the browser, the class is
`injection.client_path` and the Playbook is `client-side-path-traversal`. Where a document is
published at a path nobody linked, it is `information_disclosure.artifact_exposure` and
`attack-surface`. Where the caller's name decides how a stored document is later served, it is
`injection.stored_file` and `file-upload`.

## 7. The ceiling, and the three readings this slug refuses

This Playbook is `read_only` and every value it sends resolves to a file chosen for being dull. It
does not walk the filesystem, iterate a wordlist, or read a credential file, a key, a session store
or source code. Section 4's single filter is the one wrapper admitted; the three attached references
are almost entirely about what follows it, and each refusal below travels with its reason.

Seeding a file the target writes -- a log through a recorded header, a session file through a
persisted value -- and then including it is refused before the seeding request. The schema does not
stop it, since a PHP tag passes the header value pattern, so this is a decision: the write has no
undo, it corrupts the record the target's own incident response reads, and the session-store half
rewrites other people's sessions to stay alive.

The generated filter chain and the per-character error oracle are refused before the first request;
the body limit is not the blocker and a reader must not conclude it is. The chain's precondition IS
the finding section 4 establishes, so it adds an exploit rather than a fact, and the oracle exhausts
the interpreter's memory once per request across hundreds.

Widening a proven read to the files that make the report severe -- `/proc/self/environ`, private
keys, `.env`, cloud credential files, the session directory -- is refused at the line the card draws
for cloud metadata credentials. One dull file settled the claim, and reading the process environment
to decide whether it holds a credential is reading the credential.

Where the response side has nothing to show, the verdict is `inconclusive` and is recorded in the
Task's own record. This section performs and grades nothing. 3 of 7 steps cannot be graded.
