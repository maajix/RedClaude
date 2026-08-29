---
description: Ask whether the platform under an application ships a second route to the same records that skips the check the application's own route makes, by reading the application's route under a leased Identity and then asking a representation suffix, a platform format parameter, the platform's own route index and the platform's user namespace for the same records from a second Task this run hands on rather than opens.
bb:category: authorization
bb:outputs: ["authorization.parallel_route"]
bb:triggers_all: ["authenticated_endpoint", "read_method", "tech_cms"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-05-15
bb:provenance: Written for ticket 55 as the v2 replacement for v1's cms pack against the parallel_route leaf ticket 55 added; the pack's three platform pages are attached as maintainer references and their version tables, their plugin enumeration and their exploit lists are refused by the last section. Rewritten for ticket 101 against the merged technique ledger, which holds five executable readings and one hand-off for this slug -- cms was one of the nine thin Playbooks, at two rows, with three references that had produced nothing between them. The refuted leg moves from response_invariant to content_match, which is the kind its own role already asked for on the supported leg.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "content_match", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "content_match", "polarity": "supports", "min_count": 1}]
bb:references: ["cms-drupal.md", "cms-joomla.md", "cms-wordpress.md"]
---

# Ask whether the platform kept a second door to the same records

An application built on a content platform is two applications: one written
here, with the checks somebody thought about, and one that arrived with the
platform, serves the same store and was never part of that conversation. The
subject is an authenticated read on an application whose platform a recon pass
fingerprinted, and four spellings of that second route are worth one reading
each.

Every reading here has the same three-armed shape. Action 1, role baseline, is
the bare path from a Task holding nothing. Action 2, role control, is that url
sent again unchanged. Action 3, role variant, is the second-route spelling. The
assertions are `body_equals` on action 2 against action 1 and `status_differs`
on action 3 against action 1, so the control is named by no differing
assertion, which makes it the invariant the bar asks for while the variant
carries the differential. The claim itself is not a status: it is that both
routes serve one store, and that is a `content_match` the agent files -- from a
jq run where the document is JSON, or from a browse run where it is not,
because a browse run is a tool run and satisfies the same provenance. A model
that reads a body by eye and names the identifier has produced no Observation
at all.

The answering document is fetched with `mcp__rk2__http_request` and filed in
the role the bar names through `mcp__rk2__submit_mission_result` before the
reading is proposed with `mcp__rk2__propose_test`: an evidence edge is dropped
once a claim is past proposed, and a Test's first action moves it past that.

## 1. Say what the fingerprint bought, which is one hypothesis

This step is a lead and cannot be graded: it reads state through
`mcp__rk2__get_attack_surface` and writes nothing, because a fingerprint is why
this Playbook was selected and is not evidence for anything. Knowing which
platform answered says which route names are worth one request each, and
nothing about whether any answers. Record in the Task the platform, the
observation it was named from, the application's own route, and at most five
candidate names from published conventions.

## 2. Ask whether the user namespace shares a path space with the routes

The cheapest reading under this slug, and the one that decides whether section
5 is worth anything. It needs no Identity. Send the arms with
`mcp__rk2__http_request` and propose the reading with `mcp__rk2__propose_test`.
Action 1, role baseline, is the root-relative path of one profile name already
known to exist, taken from the application's own answers and never harvested by
enumeration. Action 2, role control, repeats it unchanged. Action 3, role
variant, is a root-relative path that is an application route name.

An application page under the variant means the namespaces are separate. A
profile page, or a profile-shaped refusal, means they share a path space and a
registered name could shadow a route. A fourth request for a name nobody holds
has to answer that nothing is there, or a profile-shaped answer cannot be told
from a shell rendered for every path.

`close_test_replay` is the writer. It takes the Observation kind from the
specification rather than the outcome, so one role writes one kind whichever
way the reading comes out, and it alone carries a Hypothesis to supported.

## 3. Ask whether a suffix or a parameter reaches a second renderer

Two readings of the same shape, one of the path and one of the query, and a
deployment can have either without the other. Both need the bare path to refuse
this caller first, because a path that answers anyway makes every spelling
meaningless. Send the arms with `mcp__rk2__http_request`, propose each reading
with `mcp__rk2__propose_test`, and close_test_replay writes the result.

In the first, action 3 appends a representation suffix content negotiation
resolves -- a json, xml or csv extension, or a trailing dot. In the second it
appends one platform-published format or view parameter. A response carrying
the object means a second renderer resolved the record under a rule the access
check did not match. Each needs a fourth request naming no renderer at all,
which has to be refused: a router answering everything, or a parameter being
ignored, has told the reading nothing.

Names come from the platform's published conventions and never from a wordlist,
at most five and each asked once. Two arms differing only in the query are held
apart by their ordinals rather than by the receipt guard, which compares path
and not query, so the arms are never re-ordered. A specification url may not
hold a dot or double-dot segment, nor `%2e` anywhere, so a json extension is
fine and a dot segment is not.

That one spelling is sent outside the Test with `mcp__rk2__http_request` and
filed with the proposal through `mcp__rk2__submit_mission_result`, which
promote_proposal writes and no Test grades.

## 4. Ask the platform's own routes for the application's records

Two Tasks, because a run acts as whichever Identity its Task was opened under
and there is no argument for it. Presenting nothing is a Task property and
never a field left out, since a leased Identity replaces any caller-set cookie.

In Task A, under the leased Identity, read the application's own route twice
unchanged and record which records came back and one identifier per record
unlikely to be a coincidence -- a slug, a reference, a title, never a bare
number. That stays in Task A: an element citing another run's Receipt is
dropped. This Task performs the half its own lease admits and leaves the other
as a `suggested_tasks` entry on `mcp__rk2__submit_mission_result`.

In Task B, holding nothing, the closing Test is one run whose arms differ in
the path. Action 1, role baseline, is the application's own route, which has to
refuse; a route answering everybody is not a parallel-route question and is
handed to `attack-surface`. Action 2, role control, repeats it unchanged.
Action 3, role variant, is the first candidate platform name that answers with
records; up to five names, one each, stopping at the first that answers.

Ask the candidate once outside the Test first and run the identifier match over
that answer. `promote_proposal` writes the `content_match` edge with the
proposal, before the Test opens, and that edge is the whole claim: a platform
route answering with a menu, an empty list or a public index is not this
finding, and one answering with a record the application's own route would not
have shown this caller is.

## 5. Register a name, and ask whether the namespace mounts at the root

This section only runs where section 2 showed the namespaces share a path
space. It asks for an account to be created, which this Playbook's effects do
not admit, so it halts first. It is a lead of this Playbook and grades nothing:
parking closes the run, and what follows runs under whatever Task the operator
opens next.

Halt through `mcp__rk2__park_for_human`, naming this run's own Task in
`task_label` and destructive_action in `question_code`, with the halt trigger
verbatim in `question`: creating an account changes state at the target.

What resumes there is three plain reads -- an unregistered root-relative path
as baseline, that path repeated as control, and the registered name as variant,
where a profile page standing where nothing did is the mount.

## 6. State the claim, and state what would refute it

The Hypothesis is `authorization.parallel_route` on the application's endpoint,
because that is the record set the claim is about, and the second route belongs
in the Observation. It is supported when the bare path refused this caller, a
second spelling answered it, the control arm was invariant against the
baseline, and at least one record identifier appears in both documents. It is
refuted when every candidate does not exist or refuses the same caller the same
way. Both legs of the variant are `content_match`, because one role writes one
kind either way.

Anything else is inconclusive -- an application route answering everybody, a
second route whose records cannot be tied to the ones served, or a document no
tool run can read. Where the second door is the same route spelled differently
and the rule that missed it is the front end, the class is
`authorization.edge_rule` and the Playbook is `deployment`. Where the
application's own route shows one caller another's record, it is
`authorization.object_ownership`; where what is exposed is a document rather
than a record, `information_disclosure.artifact_exposure`.

The gate is `rk2_finding_refusal` and what it wants is the settling transition
`close_test_replay` wrote for the Test being cited.

This section proposes no Test of its own and grades nothing. Open the claim
with `mcp__rk2__propose_finding`, citing the Artifacts, the difference the
comparison returned and the matched identifier.

## 7. The ceiling, and the reading this Playbook cannot hold

This section is a lead and cannot be graded. It records one hand-off and the
refusals the v1 pack was mostly made of. Registering a name that collides with
a live application route, and then showing the profile route outranks it, is a
real reading and is not this Playbook's. The class it produces is one no
Playbook emits and could not be declared here anyway, since every output
carries its category prefix and this one is authorization. It needs a Playbook
of its own, with different effects and a named owner.

This Playbook is read_only and its baseline is a session that stays stable. It
does not enumerate plugins, themes, modules or extensions, nor request a
version file, a changelog or a readme to name a release. It makes no claim
beginning "this platform is version X, which is vulnerable to": a version is a
fingerprint and what settles one here is two responses that were compared. It
does not write, install, upgrade, log in as an administrator, or brute-force a
user list, a login or a route name.

4 of 7 steps cannot be graded.
