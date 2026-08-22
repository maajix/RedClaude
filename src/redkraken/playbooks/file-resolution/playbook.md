---
description: Ask whether a path-valued parameter resolves outside the directory a route serves, by sending two arms that name two different documents outside it and one that normalises back inside, and differencing the stored responses against a baseline that was itself invariant.
bb:category: injection
bb:outputs: ["injection.path"]
bb:triggers_all: ["authenticated_endpoint", "path_valued_parameter", "read_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-04-15
bb:provenance: Written for ticket 54 as the v2 replacement for v1's file-resolution pack against the path leaf of the ticket 18 vocabulary; the pack's three pages are attached as maintainer references and their wrapper chains, their filter chains and their read-until-you-find-a-key advice are refused by step 7.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["lfi.md", "path-traversal-encoding-variants.md", "php-filter-chain-lfi-rce.md"]
---

# Ask where the read landed

Every route that serves a document by name resolves a string to a location.
Normalising the string is not the check. The check is where the resolution
landed, and a route that never asks is one that will read whatever the caller's
string points at.

The subject is an authenticated read endpoint carrying a parameter a recon pass
typed as a path. The question is whether that parameter resolves outside the
directory the route serves, and the whole reading is six requests.

## 1. Name the parameter and the directory

Read the parameter from the state view. Then say what the route is meant to
serve, from what an ordinary request returns: an export directory, a template
directory, a per-tenant bucket, a media store.

Say it before sending anything, because "outside" is meaningless without it and
because the verdict at the end is a claim about a boundary. A reading that cannot
name the boundary is not reading this class.

Then declare the ceiling, before the first arm is composed, because every arm
after this step asks the route to resolve a name the client chose:

* **mutation** -- nothing this reading sends writes. Every request is the read
  the route already offers, with one value changed.
* **cleanup** -- there is nothing to clean up, because nothing is created. If the
  route logs what it was asked for and that log is somebody's to clear, say so
  here.
* **execution** -- every value resolves to a file chosen for being dull. Nothing
  chains a stream wrapper, builds a filter chain, reaches a log in order to
  poison it, or turns a read into an execution.

If the ceiling cannot be met, stop here, record `inconclusive`, and route to an
operator. Step 8 restates all three at the end.

Complete this step with the endpoint, the one parameter, the directory and the
ceiling.

## 2. Establish the baseline, twice

Send the request through `mcp__rk2__http_request`, with the parameter naming a
document the route is meant to serve. Then send it again, unchanged. Both go out
as whichever Identity the Task was opened under: the step does not choose it and
there is no argument for it.

Two identical requests, for the reason every comparison in this corpus starts
with two: a differential measured against a baseline nobody checked is noise with
a verdict attached. If the two differ, run `compare-responses` and record what
moved; the rest compares only what held still.

## 3. Send the two arms

Two more requests. Both leave the directory, and they name two *different*
documents outside it:

* the variant names a file that exists on essentially every host of that kind
  and holds nothing sensitive -- `/etc/hostname`, `/proc/version`, a framework's
  own `VERSION` file, the application's own `README`
* the second arm names a second such file, equally dull and equally certain to
  exist

Two arms rather than one, because a single traversal that returns something has
to be compared with something. Two arms that leave the directory and land on
different documents give the comparison its subject: if the route resolved them,
the answers differ from each other, and no refusal explains that.

Choose targets that are boring on purpose. A reading whose evidence is
`/etc/shadow`, a private key, a `.env`, a cloud credential file or a session
store has read the target's secrets to prove it could read the target's secrets,
and the report then contains the thing the report is about.

Interleave with the baseline, hold everything else constant, and send two rounds
of the pair.

## 4. Send the arm that normalises back inside

One more request, and it is the control this class needs most. The parameter
carries a value that *contains* a traversal and resolves back inside the
directory: `notes/../report.txt` where `report.txt` is the document step 2 used.

A well-built route answers that request normally. A route that rejects it is
matching the syntax of the string rather than checking the resolution, which is
worth saying in the observation and is not this Hypothesis.

This arm is also what stops the most common false positive in the class: a
reading that reports the presence of `..` in an accepted value. `..` in the input
is not a finding. A read that landed outside the directory is.

## 5. Difference the stored bytes

Run `compare-responses` over the two out-of-directory arms, then over the
normalising arm and the baseline. Cite what the script returns.

Variant against variant is the differential: two names, two documents, and the
route resolved both. Normalising arm against baseline is the corroboration that
the route works and that the boundary is where step 1 said it was.

A route that refuses both out-of-directory arms with the identical body is
refuting the Hypothesis, and it refutes it whether the refusal is a 404, a 403 or
a 200 carrying the default document -- what matters is that the two arms did not
differ from each other.

## 6. Rule out the two neighbours the arms cannot separate

A response that differs between the two arms could also come from a route that
did not read a file at all: an error page that quotes the requested name, a
router that mapped the string to a different handler, a cache that keyed on it.

One more request settles it. Name a document outside the directory that does not
exist anywhere -- same shape, same depth, nonexistent leaf. If its answer matches
the arms rather than the refusal, nothing was read and the difference was the
string. If it answers like a miss, the arms read something.

## 7. State the claim, and state what would refute it

The Hypothesis is `injection.path` on the endpoint. It is supported when the two
out-of-directory arms differ from each other in both rounds, the baseline was
invariant, the normalising arm answered like an ordinary request, and the
nonexistent-leaf probe did not reproduce the arms. It is refuted when the two
out-of-directory arms are invariant against each other against a stable baseline
-- the resolution was checked, and both names landed in the same refusal.

Anything else is inconclusive: an unstable baseline, a route behind a WAF that
refuses every value containing a dot-dot, a route that answers 403 to everything
including the baseline.

Three neighbours are close.

* Where the resolution happens in the browser rather than on the server -- a
  fetch built from a fragment, a router that reads a path out of the URL -- the
  class is `injection.client_path` and the Playbook is
  `client-side-path-traversal`.
* Where the document is simply published at a path nobody linked, with no
  parameter deciding anything, the class is
  `information_disclosure.artifact_exposure` and the Playbook is
  `attack-surface`.
* Where the caller's name decides how a *stored* document is later served rather
  than which document is read, the class is `injection.stored_file` and the
  Playbook is `file-upload`.

Cite the Artifacts and the difference the script returned.

## 8. The ceiling, restated at the end

This Playbook is `read_only` and its baseline is a session that stays stable. It
sends six requests to the one endpoint the Task names, and every value it sends
resolves to a file chosen for being dull.

It does not walk the filesystem, iterate a wordlist of candidate paths, read a
credential file, read a key, read a session store, read source code to look for
secrets in it, chain a stream wrapper, build a filter chain, reach a log file in
order to poison it, or turn a read into an execution. The three attached
references are entirely about those techniques, and each says why it is out: the
property is that the resolution left the directory, and one dull file already
proves it.

Nothing here writes and nothing here needs cleaning up. Where the response side
has nothing to show -- a route that streams to a queue, discards the body, or
answers from a cache -- the verdict is `inconclusive` and it routes to an
operator rather than to a louder channel.
