---
description: Ask whether the build published the application's dependency boundary alongside its bundles, by reading the shell for the bundles it actually loads, following each bundle's own source-map pointer, and sorting the manifest's names into the ones the public already has and the ones that exist only inside the organisation.
bb:category: information_disclosure
bb:outputs: ["information_disclosure.dependency_manifest"]
bb:triggers_all: ["read_method", "spa_surface", "tech_build_manifest"]
bb:skills: ["analyse-source", "handle-untrusted-content"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-05-15
bb:provenance: Written for ticket 55 as the v2 replacement for v1's supply-chain page against a new dependency_manifest leaf added by ticket 55, and rewritten for ticket 101 against the merged ledger's three readings for this slug. The change of substance is that content_match now names the binary that produces it -- js_parse for a bundle's pointer, js_map for a manifest index, jq where the manifest is plain JSON, all with tool_run provenance. Repaired again in review, where the body named a fetch verb and a park verb the executing role does not hold -- analyse-source is granted to js_analyst alone, which holds state.read, state.propose and exec.tool_run and nothing else, so every byte read here is now an Artifact an earlier run stored, the one reading that needs a request is proposed as a Test the replay lane performs, and a halt is written into the Task's own record. The v1 page's dependency-confusion publishing, its registry probing and its version-to-CVE tables stay refused.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "content_match", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "content_match", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "content_match", "polarity": "supports", "min_count": 1}]
---

# Ask what the build shipped beside the bundle

A build that publishes a source map or a manifest beside its bundles publishes
the names its authors wrote. Most of those names are public and say nothing.
The ones that are not are the organisation's own dependency boundary, and the
finding is that a caller presenting nothing at all was served them.

The role that reads this Playbook sends nothing. It analyses source somebody
else fetched, so every byte it reads is an Artifact an earlier run already
stored: `mcp__rk2__get_artifact` takes one by the hash the Task names, and
`mcp__rk2__run_tool` and `mcp__rk2__run_skill_script` are what read it. Those
runs are what content_match is allowed to cite. Bytes the target declared
JavaScript or JSON are what `js_parse` and `js_map` read; a served document is
not source, and the only program that opens one here is the skill script of
section 1, which looks for path-shaped and url-shaped literals and nothing else.
The agent files each content_match through `mcp__rk2__submit_mission_result`,
where it becomes a real evidence edge that settles nothing on its own.

A reading that needs bytes nobody has stored is not fetched here. It is proposed
as a Test with `mcp__rk2__propose_test`, the replay lane sends the actions, and
close_test_replay derives the transition and the Observation kind from the
Test's own assertions alone. This role holds no request verb and no park verb,
so a halt is written into the Task's own record and a person reads it there.

Order is not free. Every edge this Playbook names has to arrive with the
proposal, because rk2_promote_hypotheses drops an edge naming a claim that is
past proposed and the first recorded Test action makes it that, so sections 1, 2
and 4 all run before the Test of section 3 is proposed. Every Test holds at least
three actions and fills all three roles -- baseline, variant and control.

## 1. Read the shell for the bundles it actually loads

Take the stored document Artifact by the hash the Task names with
`mcp__rk2__get_artifact` -- the application's own page as an earlier run was
served it, presenting nothing at all, because the claim is about a caller who
holds nothing -- and run `extract_paths.py` over it with
`mcp__rk2__run_skill_script`, naming `analyse-source` as the skill and giving
`source` that Artifact. Its urls array is the shell's own script list, and that
list is the reading's scope.

That list is a scope and not a claim, which is why nothing here is graded. A
file this origin serves and the shell never loads is a different claim from one
the shell loads on every page, and the difference is reported rather than
flattened. Take at most three bundles, preferring the entry bundle.

Where a bundle the shell names is served from a host the Program's scope grant
does not plainly admit, do not name it in any specification below. Write the
host into the Task's own record with the reason the grant is unclear, and let a
person decide which of those hosts this Program covers before a later Task is
opened against it. This role cannot park a Task and does not pretend to.

## 2. Follow each bundle's own pointer

Take each bundle Artifact the same earlier run stored and run `js_parse` over
it with `mcp__rk2__run_tool`, whose `source` is that Artifact. The program
reports the Artifact's size, its shape, the source map it points at and its
string literals. Follow only the pointer it reports.

Guessing is the failure mode this step exists to prevent. A path assembled by
appending a map or manifest suffix to a bundle URL is not a pointer the build
wrote, and section 6 says whose question that is. This step also grades
nothing: it turns three Artifacts into at most three paths the application
itself named.

## 3. Ask the origin for the manifest inside one Test

The whole differential is which path is requested, so it rides the request line
and a Test action carries it. Section 4 indexes the manifest before this Test
is proposed, for the reason the preamble gives. Propose one Test with
`mcp__rk2__propose_test`: the baseline is a bundle path the shell named, the
variant is the pointer path that bundle wrote, and the control is a path of the
same shape and depth on this origin that nothing named.

The Test asserts status_differs on the control against the variant, which is
what separates a published manifest from an origin that answers everything, and
status_equals 200 on the baseline, because an origin that does not serve the
bundle the shell named cannot make a refusal on the control mean anything. A
status_equals assertion states a status and names no second action, so the
baseline carries no differential and the one comparison this Test makes is the
control against the variant. Bundle and map paths carry dots without carrying
dot segments, and none is percent-encoded, so the replay lane admits them.
close_test_replay writes the transition and the response kinds from those
assertions.

## 4. Sort the names, because two of the three piles are not findings

Take the manifest Artifact the same earlier run stored at the pointer path and
index it with `js_map`, whose `map` is that Artifact, or with `jq` where the
manifest is plain JSON, giving `filter` the sources expression -- both through
`mcp__rk2__run_tool`. Sort what comes back into three piles. Public package
names and public registry hosts are one pile and are not a finding. The
application's own file paths are the second and are not a finding either. The
third is the names that exist only inside the organisation -- an internal
registry host, a scoped private package, a repository path, a build server --
and that pile is the reading.

The control is the manifest's own tie to this application and it is not
optional: at least one indexed name has to be a file this origin serves, or a
path matching a bundle from step 1. A manifest whose names tie to nothing here
may have been copied from a template, vendored, or left by another deployment,
and a boundary claim about the wrong organisation is worse than no claim. A
second control is reported separately and never collapsed into the first -- for
each bundle whose manifest carried a private name, whether the shell embedded
that bundle -- because a file nothing loads is not a file that is running.

Each pile is filed as content_match citing the run that indexed it, which is
what its tool_run provenance means, in the roles the bar names and with the
proposal that opens the claim. A tool run produces a proposal rather than a
settled Hypothesis, so this section grades nothing.

## 5. State the claim, and state what would refute it

Propose the claim with `mcp__rk2__propose_finding`. The Hypothesis is
`information_disclosure.dependency_manifest` on the origin. It is supported
when a private name was indexed out of a manifest the application's own bundle
pointed at, the tie control held, and the Test closed as it asserted. It is
refuted when every indexed name belongs to the public piles, which is what a
build that stripped its private names before publishing looks like -- a
refutation that is a tool run and not a response, which is why the refuted row
names content_match and not a response kind. Anything else is inconclusive: a
pointer that answered nothing, a manifest that tied to no file here, an index
that returned no sources at all.

Quote the private name, say which manifest carried it, and say whether the
shell loads the bundle it belongs to. A credential in a manifest is said
immediately rather than at the end of a sort, and it goes to `secrets` as
information_disclosure.credential_material. Seven stored Artifacts are the
ceiling for one origin -- the document, three bundles, three pointers -- and
this Playbook does not walk a bundle directory.

This section carries the proposal and closes no Test of its own, so it grades
nothing.

## 6. The ceiling

A version in a manifest is a fingerprint. No output of this Playbook contains
the sentence that package X is at version Y and is therefore vulnerable,
because that claim needs a Test this reading did not run.

Two readings are named here and performed nowhere. The library-and-version
inventory of the served bundles is out of scope as an output, though it is a
fair selector for what to read next, because technology_identified is not
evidential and settles nothing whatever it says -- and it has no control, since
an inventory is not a comparison. Guessing at a manifest by appending a map, a
JSON suffix or a build directory to a path no bundle named goes with it, as
`attack-surface`'s question about information_disclosure.artifact_exposure.

Turning a harvested private name into a demonstration is refused, whether by
asking a public registry whether the name is unclaimed or by publishing under
it. Those names are reported so that somebody who owns the account can claim
them; claiming a third-party resource is not a reading. The neighbouring class
for unclaimed references is the most likely place for this to be re-proposed,
and the reachable half of that work is an inventory of outbound authorities
owned by `external-resources`.

This section performs nothing and grades nothing.

5 of 6 steps cannot be graded.
