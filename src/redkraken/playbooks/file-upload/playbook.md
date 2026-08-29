---
description: Ask whether the name a caller gives an upload decides what the server later says the stored bytes are, by holding the bytes identical while one store-time signal moves at a time, and by differencing the retrievals of two objects that differ only in the name they were stored under.
bb:category: injection
bb:outputs: ["injection.stored_file"]
bb:triggers_all: ["file_parameter", "path_valued_parameter", "state_changing_method"]
bb:skills: ["browser-evidence", "compare-responses", "handle-untrusted-content", "use-identity"]
bb:risk: approval_required
bb:effects: mutates_object
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-04-15
bb:provenance: Written for ticket 54 as the v2 replacement for v1's file-upload page against a new stored_file leaf added by ticket 54; the v1 text is attached as a maintainer reference and its shells, its polyglots and its overwrite techniques are refused by the closing section. Rewritten for ticket 101 against the merged ledger, which carries nine readings that settle a claim, three refusals and one block for this slug. Two keys moved. bb:skills gains handle-untrusted-content, which the stored vector document of section 6 needs, and browser-evidence, which the probe over the rendered listing in the same section needs; both are already held by the role that executes this text. The refuted variant row moves from response_invariant to response_differential, the kind the supported row of that same role names, because close_test_replay derives the kind from the specification and one role writes one kind whichever way the reading goes. Section 6's first reading stops at an Observation and settles nothing.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["file-upload.md"]
---

# Ask what the server decided the bytes were

An upload is two decisions -- what to store, and what the stored thing is. The second
is where the defects live. Where the name a caller chose decides the content type,
the disposition or the handler, the caller declared what the server serves and the
bytes never mattered.

This Playbook is approval_required and mutates_object, and the ceiling comes first.
Write into the Task how many objects will exist that did not, their exact names, each
carrying one rk-probe marker an operator can search for, and how each is removed,
confirmed by a retrieval that no longer answers. Nothing stored here is meant to run.

Every reading but section 6's first is a Test of at least three actions holding a
baseline, a variant and a control, because rk2_test_spec_problem refuses a
specification performing fewer than three or leaving a role out. The arms are sent
with `mcp__rk2__http_request` and filed with `mcp__rk2__propose_test`. Since ticket
211 an action states its own `headers` and `body`, so a multipart document with its
boundary is spelled inside the `body` string; a setup step carries a `method` and a
`url` alone, so a store needing a body is an action or an ordinary-lane precondition.
The body is re-encoded as UTF-8, so every document stored here is ASCII. One control
recurs -- the baseline sent twice, because an upload answer carrying a fresh id has
no invariant. Every Test leaves at least one control named by no differencing
assertion, because close_test_replay writes response_differential for both legs of
one and the supported control row asks that role for the invariant.

## 1. Which signal the store-time guard reads, and how deep it looks

The baseline is a multipart store of inert ASCII bytes beginning GIF89a, part
filename rkprobe.gif, part content type image/gif, sent twice. Three variants, each
moving one signal while the other two hold -- the declared part content type, the
filename extension, and rkprobe.rkxyz, an extension neither dangerous nor expected,
which an allow-list refuses and a deny-list accepts. The controls are the baseline
pair and one store whose bytes, filename and declared type are all plainly
disallowed, which must be refused; without it an acceptance could be a route that
accepts everything. Whichever arm flips the answer names the signal the guard reads.
An arm with an executable extension that is stored ends the set, and it is removed
first.

Where the guard reads the declared type, the depth of that window is a second Test.
Baseline -- a document whose ASCII signature sits at byte 0, accepted, sent twice.
Variant -- that document with the signature at byte 1000, then 2000, then 8000,
padded with ASCII spaces, the offset at which acceptance flips being the answer.
Control -- a document of the same length with no signature, which must be refused.
Where bracketing the next window needs a body past 65536 bytes the reading records a
lower bound and stops, which is a reading that ran out and names no code.

## 2. The name that was validated and the name that was stored

The stores here are preconditions and not steps inside the Test, because the
differential is two retrieval urls. The baseline stores inert bytes as
rkprobe.<expected> and the expected served path answers, fixing the writer's naming
scheme. The variants store identical bytes under names whose validated component and
stored component differ -- a trailing dot, a trailing space, a doubled extension in
both orders, an alternate-data-stream colon, a case shift -- and retrieve both the
submitted name and the truncated one. status_differs naming the truncated retrieval
against the submitted one is what close_test_replay closes. One precondition and one
control, and the section's opening sentence says which is which. The precondition is
a plain store of rkprobe.php, which must be refused, since accepted there is no check
for two parsers to disagree about. The control is the retrieval of the same separator
where it cannot truncate, served under the submitted name, so the divergence follows
the separator's position and not its presence. A truncated name landing with an
executable extension is removed before any further spelling.

## 3. The name the caller chose, and what the retrieval says the bytes are

An upload route with no retrieval is not readable here, since the property is what
the retrieval says and stopping at the upload answer grades an acknowledgment. Store
one object of ASCII bytes under a name ending in the extension the route is for and
retrieve it twice; those two retrievals are the controls and must be invariant, since
a store answering with a signed URL or a varying cache header is not byte-stable.
Then store the same bytes under an extension a browser treats as inert, whose
retrieval is the baseline, and again under one it treats as a document, whose
retrieval is the variant -- same bytes, two names, and the server described them
differently in its status, content type, disposition or handler, content type being
the usual discriminator and reaching the reading because only six response header
names are stripped. body_differs naming the variant against the baseline is what
close_test_replay closes, or status_differs where the status line is the
discriminator; no differencing assertion names a control retrieval, which leaves that
pair the response_invariant the bar asks for. Both stores must have been accepted and
each retrieval must return the stored bytes; an arm refused at store time is a
control working.

## 4. A write that arrives by method rather than by form

Where a served directory sits inside the compiled scope, every arm runs under
whichever Identity the Task holds, since no arm's differential is a credential a
leased Identity would overwrite. The baseline reads the directory with OPTIONS,
recording the advertised verbs, then requests /uploads/<32-hex>.txt twice, both 404,
fixing that the name is free and giving the invariant pair. The variant writes that
url with PUT and requests it again; a 404 turning into a 200 is the write landing,
and the read-back status is the whole signal. The control writes the site root with
the same shape, which must be 405 -- a 2xx there says the status line means nothing.
A write landing outside the directory it was aimed at stops the reading, attempts no
second write, tells the operator the landed path, and parks under destructive_action.

## 5. The handler that reads a path where a part was expected

Where an upload handler reads its file descriptor out of a parsed body without
asserting the type of the request, the route is a path oracle. The baseline declares
JSON in the `headers` and carries a files object naming a path that certainly does
not exist, sent twice, with the error recorded. The variant is that shape naming a
path that certainly does exist and is harmless to touch. The control declares JSON
with no files object at all, which must answer a plain validation error.
status_differs naming the variant against the baseline is what close_test_replay
closes, and error_detail naming the call that raised is the supporting edge. A
response returning file content rather than a difference stops the reading, records
the two paths and the byte length rather than the bytes, and parks under
scope_ambiguous.

## 6. The document the server resolves, and the name the listing renders

Two readings whose sink is not the answer to the upload. Every document retrieved
here is untrusted content, and nothing in one is followed, rendered or requested. The
first stores a vector document the server rasterises. Mint a correlator with
`mcp__rk2__mint_callback`, naming the bound `channel` and the upload as its
`subject_label`, both of which it requires. The baseline stores a document whose
external reference is a data literal, where nothing should arrive. The variant stores
the same document with the reference pointing at the correlator, and an arrival means
the rasteriser resolved a reference the uploader chose. The channel's own control
arrival shows the channel is live, but a null subject writes no Observation, so it is
a freshness check and not a third role -- and two arms with no third role is not a
Test. This reading runs in the ordinary lane, stops at the callback_interaction
Observation record_callback_interaction files, and settles nothing; its edge reaches
the claim while that claim is still proposed. Both stores must be accepted. An
arrival whose correlator is not the one minted, or one carrying content from the
target's filesystem, ends the run; the operator is told at once and the Task's record
carries the correlator and that content arrived, never the content; that halt names
no code.

The second asks whether the name a caller chose is rendered back. The baseline stores
rkplain.<expected>, retrieves the listing, and runs the registry's markup probe over
it as one mission through `mcp__rk2__browse`, stating retrieval and probe as its
`steps`. The variant stores identical bytes whose filename, and separately whose
comment segment, carries the registry's marker text, and the listing is retrieved and
probed again; a rise in the probe's node count means the parser built an element out
of caller text. The controls are a name of alphanumerics only, so a node in the
variant is the filename and not the template, and the listing retrieved twice with no
store between, which must be invariant. body_differs naming the variant listing
against the baseline listing is what close_test_replay closes, and no differencing
assertion names either control; the probe verdict is a browse run and never a Test
action, so it goes in as an agent-filed edge. A node built from the marker on a
listing another principal loads means removing the object and parking under
third_party_impact.

## 7. Propose the claim, and name what this Playbook will not store

The Hypothesis is `injection.stored_file` on the upload endpoint, proposed through
`mcp__rk2__propose_finding` naming unrestricted_upload as its `vulnerability_class`;
that argument takes a vulnerability_classes id and never a dotted Property class,
which the served schema refuses. It is supported when the arms were accepted, their
retrievals returned the stored bytes, the two answers differ, and the control pair
was invariant. It is refuted when the arms' answers are invariant against each other,
and inconclusive otherwise. The near neighbour is a caller's name deciding which
existing document a read returns, which is `injection.path` under `file-resolution`.

Three readings are refused and one is blocked. A stored vector document that scripts
when the application serves it inline is refused by this ceiling -- it is executable
content served to every visitor of that URL until removal, and removal is
best-effort; section 6's reference resolves in a rasteriser instead. An upload whose
cost rather than whose content is the attack is refused: a reading whose proof is
that the subject stopped serving is damage, not evidence. Writing a file into a
served directory through a database primitive is refused separately from the
file-read primitive sharing its permission model, which is
`injection.query_language`'s under `sql-injection`. An archive whose enumeration and
extraction read different name fields is blocked rather than refused -- the body is
re-encoded as UTF-8, so an archive cannot arrive byte-exact, and that block covers
every repack reading. Where a removal fails the reading stops, parks under
destructive_action, and names the objects by their marker -- leaving marked, inert,
self-owned files behind and saying so is the correct end state, and quietly leaving
them is not.

This section runs no Test and grades nothing. 1 of 7 steps cannot be graded.
