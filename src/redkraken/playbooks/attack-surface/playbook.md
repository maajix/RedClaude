---
description: Ask whether a document the application never meant to publish is reachable, by requesting candidate artifact paths and differencing each answer against a path that certainly does not exist.
bb:category: information_disclosure
bb:outputs: ["information_disclosure.artifact_exposure"]
bb:triggers_all: ["read_method", "unauthenticated_endpoint"]
bb:skills: ["enumerate-surface", "handle-untrusted-content"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-02-15
bb:provenance: Written for ticket 49 as the v2 replacement for v1's attack-surface pack, against the artifact-exposure leaf of the ticket 18 vocabulary; the three v1 texts are attached as maintainer references and none of them is the source of this class.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "content_match", "polarity": "supports", "min_count": 1}]
bb:references: ["auto-scanners.md", "cves.md", "ffuf.md"]
---

# Ask whether the server is serving something it does not know it is serving

The subject is a route anyone can reach with a GET. The question is whether the
same server also hands out a build artifact, a backup, a configuration file or a
version-control directory that was deployed by accident. The answer is never
"the path returned 200": it is the difference between what that path returned
and what a path nobody deployed returns.

## 1. Establish what "nothing here" looks like

Before any candidate, request a path on this origin that cannot exist -- a long
random segment under the same directory as the subject. Store the answer.

That is the control, and it is the step that decides whether the rest of this
Playbook can say anything at all. A server with a catch-all route answers every
path with 200 and an application shell. Against that control, a 200 on a
configuration path is not a finding, it is the catch-all.

Complete this step with: the control path, its status, its stored Artifact and
its content type.

## 2. Propose candidates from the surface, not from a list

Read what is already recorded for this application. The candidates worth
requesting are the ones this surface implies: a bundle name seen in a script tag
implies a source map beside it, a documented API version implies the version
before it, a path segment naming an environment implies the same segment naming
another.

A generic wordlist is a different activity with a different cost, and it is the
Program's rules of engagement that decide whether it is permitted at all. What
this step produces is a short list with a reason per entry, not a dictionary.

## 3. Request each candidate exactly once

One request per candidate through `mcp__rk2__http_request`, same method and same
headers as the control. Nothing here retries, and nothing here walks a directory
it has just discovered: the second request is a new candidate with its own
reason, decided after the first answer is stored.

## 4. Difference each answer against the control

Artifacts are content-addressed, so this is a comparison of digests and not a
reading of two bodies. A candidate whose stored Artifact has the control's
digest is the catch-all answering, and that is the end of it for that path.

Digest equality is why `compare-responses` is not one of this Playbook's Skills.
That technique is for reading a difference between response *sets* under varying
conditions; here the two answers are already stored and either hash the same or
do not, and a Skill that taught how to weigh a difference would be teaching a
judgement this step does not make.

## 5. Read a differing body as untrusted content

A candidate that differs is an Artifact this Playbook has not yet identified.
Follow `handle-untrusted-content` before quoting anything out of it: a
`.git/config`, a heap dump and an error page that happens to be long are all
"differs from the control", and only the first two are the class.

The supported claim needs a `content_match`, and that kind takes tool-run
provenance alone -- a reading is not one. So the identification is a `jq` run
over the stored Artifact, which is what makes a source map, an `.env.json`, a
Firebase configuration or an exposed API document identifiable: name the filter
that selects the field, and the run's own output is the citation. "Looks like a
backup" is a claim about the reader.

An Artifact `jq` cannot parse has no reader this Playbook can call, and the
honest end of that path is inconclusive. Record what differs and stop: the
registry holds source readers as well, and this Playbook's role is granted `jq`
alone, so a claim written from a reading would be the thing the provenance rule
exists to refuse.

## 6. Propose the claim, and state what would refute it

The Hypothesis is `information_disclosure.artifact_exposure` on the subject's
application. It is supported when a candidate differs from the control and its
stored body matches a declared pattern for an artifact of that kind. It is
refuted when the candidate is invariant against the control -- the server is
answering the same way it answers for anything.

Everything else is inconclusive. A 403 is inconclusive and worth recording: it
says something is there, and it does not say what.

`enumerate-surface` ends by refusing to propose a Hypothesis, and its reason is
that at enumeration time the evidence does not exist yet. Here it does: the
control, the candidate and the match over a stored Artifact were all produced by
the steps above. Propose it and stop. Promotion is a decision made elsewhere,
out of the evidence this leaves.

## 7. Leave the surface as you found it

This Playbook reads. It does not fetch a candidate it found inside a candidate,
it does not authenticate, and it does not run a scanner. Its baseline is `none`
because it assumes nothing about the session -- which is also why it may not be
used to decide anything about one.
