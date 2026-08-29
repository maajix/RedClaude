---
description: Ask which origins a served document grants authority to run inside it, by listing every reference that carries executable authority out of the stored bytes, naming the ones the Program's scope does not claim, and differencing a candidate host against a label nobody holds to see whether the reference points at a resource that was let go.
bb:category: injection
bb:outputs: ["injection.foreign_resource"]
bb:triggers_all: ["read_method", "url_valued_parameter", "web_surface"]
bb:skills: ["compare-responses", "enumerate-surface", "handle-untrusted-content"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 as the v2 replacement for v1's broken-link-hijacking page, against a new foreign-resource leaf added by ticket 52; the v1 text is attached as a maintainer reference and section 6's refusal is where this Playbook and that page part company. Rewritten for ticket 101 against the merged technique ledger, which carries three readings and one standing refusal for this slug. One frontmatter key moves and it is a repair -- analyse-source is granted to js_analyst alone, js_analyst holds no request verb, and a Playbook naming that Skill is one no hunting role can be handed, so the three Skills web_hunter holds for this reading replace it and section 1 fetches its own bytes. The effects and the risk floor are the ones already declared, since the two readings added below are Tests this role proposes and the replay lane performs.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "content_match", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "content_match", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "content_match", "polarity": "supports", "min_count": 1}]
bb:references: ["broken-link-hijacking.md"]
---

# Every script tag is a delegation

A document that loads a script from somewhere else has handed that somewhere the
same authority its own code has: the DOM, the cookies the page can read, the
requests the page can make. Usually the somewhere is a vendor the target chose.
Sometimes it is a bucket that was deleted, a package name that was unpublished, a
domain that lapsed, or a host named by a parameter the caller supplied.

This role fetches with `mcp__rk2__http_request` and reads what came back with
`mcp__rk2__run_tool`, and it also authors specifications: `mcp__rk2__propose_test`
writes a proposal, the replay lane performs the actions, and close_test_replay
settles the claim off the Test's own assertions. Sections 3 and 4 are those, and
every host they name is one the Program's scope grant covers.

## 1. List what the stored document delegates, and what the parameter adds

Fetch the route three times with `mcp__rk2__http_request`: once with no
parameter set, once with the URL-valued parameter naming a host that is not the
target's, and once with the parameter carrying a value that is not a URL. Read
each answer for the references it carries, then fetch each script those answers
name and run `js_parse` over it with `mcp__rk2__run_tool`, whose `source` is
that Artifact. Only bytes the target declared JavaScript or JSON are
filed as source, so a served document is read as the answer it is and the
analysers run over the scripts it loads, where the imports and the registration
calls are. File each list as a content_match Observation through
`mcp__rk2__submit_mission_result`, which promote_proposal writes with the
tool-run provenance that kind takes, and file it with the proposal that opens the
claim, before the Test of section 3 is proposed.

The first pass is the baseline: every `<script src>` and the imports the loaded
modules perform, `<link rel=stylesheet>`, `<link rel=preload as=script>`,
`<iframe src>` where the frame is same-origin or carries `allow` attributes, and
every service worker registration, which outlives the page. Not in the list:
images, fonts, media, and anything carrying an `integrity` hash a browser
enforces. Record which references carried `integrity` and `crossorigin`, because
a pinned digest is the target having already answered this question.

The second pass is the variant, and the reading is where the value landed. A URL
in a link's `href` is a redirect question and belongs elsewhere; a URL that
becomes a `src` on a script, a stylesheet or a same-origin frame is this one,
because the caller chose which origin runs in the target's page. The third pass
is the control: without it, an origin appearing in the variant list cannot be
told from an origin the template emits for every value. Cite the bytes the run
returned rather than a description of them.

Where the route answers only one of the three, the missing half is unanswered and
saying so is the result -- a rendering that never arrived is not a rendering that
says nothing. That halt is a reading that ran out and is reported through the
Task's own record. Where a script the document names is served from a host the
Program's scope grant does not plainly admit, do not fetch it: ask through
`mcp__rk2__park_for_human` for this Task to be parked, giving its own label in
`task_label` and scope_ambiguous in `question_code`.

## 2. Ask, for each origin, whether the target claims it

This section is a lead. It names no verb and files no result of its own; it is
the judgement a person applies to the three lists, and it is what decides which
name section 3 is worth spending requests on.

For every name the lists produced, and from the bytes rather than from the wire:
is the registrable domain one the Program's scope claims; is it a provider's own
hostname carrying a name of the target's -- a bucket, an app, an account -- and is
that name one these bytes use elsewhere; is the package name one the target
publishes, according to the manifest that named it; did the document pin it with
an `integrity` hash a browser enforces. A name the scope claims is the target
delegating to itself and is not this claim. A name outside the scope, with no
pin, on a reference that carries execution, is the candidate.

## 3. Ask whether an already-trusted host is a name nobody holds

The candidate list comes from the target's own served bytes and from nowhere
else: there is no name-resolution tool here, so a sweep is not available and is
not wanted. Propose the Test with four actions. The baseline is a host from the
same trusted-source list that is plainly in use, and the first control is that
same request repeated, asserted equal, which is what a claimed name looks like
and is the stability arm. The variant is the candidate host. The second control
is a fabricated random label under the same provider suffix, which must return
the same document as the candidate; where the grant does not admit the provider
suffix, use a path the serving host certainly does not have, which must return
the deployment's own not-found instead.

Assert that the variant's body differs from the baseline's and equals the second
control's. Both holding is the reading: the candidate is not serving the vendor's
content, and it is serving what a name nobody holds serves -- a provider's
disowning document, `NoSuchBucket`, a missing-site page, a domain-mapping or
repository not-found. close_test_replay derives response_differential for the
variant and settles the claim; the content_match edge from section 1 is what
establishes the reference came from the target's own artefacts, which is what
makes the disowning body a finding rather than a fact about somebody else's
bucket. Where the candidate's document and the deployment's own not-found are the
same document, the fingerprint proved nothing.

A candidate that does not answer at all leaves the Receipt with no stored
response, and a body assertion over that is unanswerable rather than false. The
honest verdict there is inconclusive, and it is recorded as inconclusive: this
reading is about a document that arrived, never about a name that failed to
resolve.

## 4. Ask whether the server composes an outbound URL out of raw input

Where the page server-renders share, callback or tracking links, the question is
whether it builds them for other users out of request input. Propose the Test
with four actions: the baseline is the article or product URL clean, the first
control is that request repeated and asserted equal, the variant is the same URL
with an extra parameter whose name collides with the widget's own key -- u, url,
link -- carrying a host the Program's scope covers, and the second control is
that same value under a parameter name the widget does not use.

Assert that the variant's body differs from the baseline's and that the second
control's equals it. The differing bytes are the emitted `href`, and the agent
files a reflected_input edge naming the parameter and the link it landed in. If
the second control also differs, the page is echoing the whole query string and
this is a generic reflection rather than a composed-URL defect. Read the href and
stop there: do not follow it, and do not serve anything at the destination.

## 5. State the claim, what refutes it, and what it does not settle

The Hypothesis is `injection.foreign_resource` on the page, and it becomes a
Finding through `mcp__rk2__propose_finding`, which rk2_finding_refusal admits only
where section 3's or section 4's Test settled it. This section proposes no Test of
its own and grades nothing. It is supported when the stored document grants
executable authority to an origin the Program's scope does not claim, whether that
origin was already in the document or was put there by the parameter, against the
control list of what the document delegates by default. It is refuted when every
origin with that authority is one the scope claims, or is pinned by an integrity
hash a browser enforces.

Two questions cut the list down and both are answered above: whether the
reference is reached, which page state loads it, and whether the page grants it
anything, since a script with `integrity` cannot be swapped and a sandboxed frame
with no `allow-same-origin` cannot reach the page. Whether the origin is takeable
is answered by section 3 only for a candidate the grant admits; for any other, the
report says the name was never resolved rather than letting the first fact imply
the second. Where the parameter instead makes the server fetch something, the
class is `injection.request_forgery` and belongs to the Playbook holding it.

## 6. Do not take the name

This section is a refusal and there is nothing in it to grade. It is the line
that separates the reading from the exploit, and it is not negotiable by a run
that thinks the proof would be cleaner.

Do not register the domain. Do not create the bucket. Do not publish the package.
Do not claim the account. Do not serve anything from any of them, including a
lookalike registered to demonstrate. Every one is irreversible -- a domain lasts a
year, an account name may never be released, a package name is permanent on most
registries -- every one is outside the scope the Program named, and every one
makes the tester the owner of live authority over every visitor to the target
from that moment, whether or not anything is served. Also out, for the same
reasons: scanning the third-party host for anything beyond the answer section 3
reads, and archive lookups used to argue the reference used to work, which is
evidence about the past.

The unclaimed name goes in the report as a name. What happens to it next is the
target's decision.

4 of 6 steps cannot be graded.
