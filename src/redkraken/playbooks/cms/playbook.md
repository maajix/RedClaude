---
description: Ask whether the platform under an application ships a second route to the same records that skips the check the application's own route makes, by reading the application's route under a leased Identity and then asking the platform's route for the same records with nothing presented at all.
bb:category: authorization
bb:outputs: ["authorization.parallel_route"]
bb:triggers_all: ["authenticated_endpoint", "read_method", "tech_cms"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-05-15
bb:provenance: Written for ticket 55 as the v2 replacement for v1's cms pack against a new parallel_route leaf added by ticket 55; the pack's three platform pages are attached as maintainer references and their version tables, their plugin enumeration and their exploit lists are refused by step 7.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "content_match", "polarity": "supports", "min_count": 1}]
bb:references: ["cms-drupal.md", "cms-joomla.md", "cms-wordpress.md"]
---

# Ask whether the platform kept a second door to the same records

An application built on a content platform is two applications. One was written
here: routes somebody designed, with the checks that somebody thought about. The
other arrived with the platform, serves the same store, and was never part of
that conversation.

The subject is an authenticated read on an application whose platform a recon
pass has fingerprinted. The question is whether the platform's own route reaches
the same records without the check the application's route makes, and the whole
reading is eight requests.

## 1. Say what the fingerprint bought, which is one hypothesis

A fingerprint is why this Playbook was selected and it is not evidence for
anything. 018 records `technology_identified` as non-evidential precisely here:
knowing which platform answered says which route names are worth one request
each, and says nothing about whether any of them answers, what it returns, or
whether the deployment left it reachable.

So write down, in the Task, what the fingerprint licenses:

* the platform the recon pass named, and the observation it was named from
* at most five candidate route names, from that platform's own conventions
* that nothing below is claimed until two responses have been compared

A reading that reports the platform, its version, or a defect published against
that version has reported a fingerprint. No version appears anywhere in this
Playbook's output, and step 7 says why.

Complete this step with the platform, the application's route and the five names.

## 2. Establish the baseline, twice

Send the application's own route through `mcp__rk2__http_request`. Then send it
again, unchanged. Both go out as whichever Identity the Task was opened under:
the step does not choose it and there is no argument for it.

Two identical requests, because everything after this is a comparison against
this one. A route that carries a request id, a cursor or a rendered timestamp is
not byte-stable, and a comparison that does not know that reads noise as a
finding.

Then read the answer and write down two things: which records came back, and the
identifier each one carries. One identifier is enough, and it should be the one
least likely to be a coincidence -- a slug, a reference, a title -- rather than
`1`.

## 3. Ask the application's route with nothing presented

One request: the same route, same everything, from a Task opened with no
Identity. The half of this comparison that presents nothing is a Task opened
under no Identity at all, not a call that left a field out, and what is
differenced is the two Receipts.

This is the check the reading is about. It has to refuse. A route that answers
the same records to a caller holding nothing is not a parallel-route question at
all -- there is no second door, because the first one is open -- and the reading
stops here, records `inconclusive`, and hands the route to `attack-surface`.

## 4. Ask the platform's routes, once each

Up to five requests, one per candidate name from step 1, each carrying nothing.
No session, no header, no parameter beyond what the name itself needs.

One request per name and no second attempt. This is not a scan: the names came
from a platform's published conventions rather than from a wordlist, there are
at most five of them, and a name that answers `404` is a name that is done.

Stop at the first route that answers with records. The rest of the reading is
about that one route, and asking the other four afterwards would be asking
questions whose answers change nothing.

## 5. Difference the refusals, and match the records

Run `compare-responses` over the platform route's answer and the refusal step 3
produced. Cite what the script returns.

Two outcomes matter and they are not the same claim.

* The platform route **refuses too**, and the two refusals are invariant against
  each other. The platform's door has the application's check. That is the
  refutation.
* The platform route **answers**. Then the comparison that carries the claim is
  not between two responses but between two documents: the identifier from step 2
  and the platform route's body. Name the identifier, quote where it appears, and
  say which record it is.

The second one is the observation the Hypothesis rests on. A platform route that
answers with something -- a menu, an empty list, a public index -- is not this
finding. A platform route that answers with a record the application's own route
would not have shown to this caller is.

## 6. State the claim, and state what would refute it

The Hypothesis is `authorization.parallel_route` on the application's endpoint,
because that is the record set the claim is about; the platform route is where it
was reached and belongs in the observation.

It is supported when the application's route refused the caller holding nothing,
a platform route answered that same caller, at least one record identifier
appears in both documents, and the two baseline reads were invariant. It is
refuted when every candidate route either does not exist or refuses the same
caller the same way -- which is what a deployment that put its platform behind
the application's own check looks like.

Anything else is inconclusive: an application route that answers everybody, a
platform route that answers with records this reading cannot tie to the ones the
application served, a front end that rewrites both answers into the same page.

Three neighbours are close.

* Where the second door is the same route spelled differently and the rule that
  missed it is the deployment's front end, the class is `authorization.edge_rule`
  and the Playbook is `deployment`.
* Where there is no second route and the application's own route shows one
  caller another caller's record, the class is
  `authorization.object_ownership` and the Playbook is `object-ownership`.
* Where what the platform route exposes is a document rather than a record --
  a backup, an export, a configuration file -- the class is
  `information_disclosure.artifact_exposure` and the Playbook is
  `attack-surface`.

Cite the Artifacts, the difference the script returned, and the matched
identifier.

## 7. The ceiling

This Playbook is `read_only` and its baseline is a session that stays stable. It
sends eight requests: two baselines, one unauthenticated read of the
application's route, and at most five platform names asked once each.

It does not enumerate plugins, themes, modules or extensions. It does not request
a version file, a changelog or a readme in order to name a release. It does not
run any technique published against a platform version, and it makes no claim
that begins "this platform is version X, which is vulnerable to" -- a version is
a fingerprint, a fingerprint is a hypothesis, and the only thing that settles one
here is two responses that were actually compared.

It does not write, install, upgrade, log in as an administrator, or touch an
administrative route at all. It does not brute-force a user list, a login or a
route name, and it does not send a second request to a name that answered `404`.

Where the deployment answers every platform name with the same page, the verdict
is `inconclusive` and it routes to an operator. A reading that responds by trying
a sixth name has started scanning, and this Playbook does not have a scan in it.
