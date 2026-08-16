---
description: Ask whether a page builds the path of a request it makes out of a segment the caller supplied, by loading the page with an encoded traversing segment and reading which route the browser's own Receipts show it asked for.
bb:category: injection
bb:outputs: ["injection.client_path"]
bb:triggers_all: ["path_parameter", "read_method", "web_surface"]
bb:skills: ["browser-evidence"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 against a new client-path leaf added by ticket 52; v1 covered this topic in prose under its client-side pack and shipped no reference text for it, so nothing is attached rather than a placeholder.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
---

# The request the page made, not the one you sent

A single-document application decides its own routes. It reads a segment out of
the address bar, builds an API path from it, and fetches that. The segment is
caller-controlled and the concatenation is unguarded, so a segment carrying a
traversal moves the request the page makes to a different route -- one the caller
never named and the page never meant to call.

Nothing about that is visible from the response to the page load. The evidence is
the request the browser made afterwards, which is why this reading is a mission
rather than an exchange.

## 1. Take the ordinary case first

Plan a mission that loads the route with the path segment carrying an ordinary
value, and read the Receipts it produced.

Every request the page makes goes through the same door and each has its own
Receipt. What is being recorded is the second one: the route the page built,
whether the segment appears in it, and where in it.

That is the control and it is a `response_differential`. A reading that has not
seen the ordinary request cannot say a later one is different, and a page that
makes no request at all has no sink here.

Complete this step with: the route the page requested, and the position of the
segment inside it.

## 2. Send the segment as an encoded traversal

Plan the same mission with the segment replaced by an encoded traversal --
`%2e%2e%2f` and its variants, so the sequence survives the browser's own URL
normalisation and arrives at the page's script as characters rather than as a
resolved path.

One spelling per mission. A mission that sent four is a mission whose Receipts
cannot say which one worked.

The subject page is the one the recon pass recorded and the traversal moves the
request the page makes, never the request the mission makes. A `navigate` that
left the recorded route is a different reading and is not this one.

## 3. Read the Receipts, and difference them

Run the step 1 Receipt list against the step 2 Receipt list. Three answers, and
they are not the same finding.

* The page requested **a different route**. The segment reached the path
  unguarded. That is the claim, and the evidence is two Receipts with two request
  lines.
* The page requested **the same route**, with the traversal encoded inside the
  segment. The page escaped it, which is the refutation, and it is a
  `response_invariant`.
* The page requested **nothing**, or errored before the fetch. Inconclusive: the
  sink was not reached.

## 4. Say what the moved request did, and what it did not

A request that moved is not a request that succeeded. Read the answer to it.

* It answered `404` or `403`: the path moved and the target refused it. That is
  still this class -- the page built a route out of caller input -- and its impact
  is what a chain would have to establish, not what this reading claims.
* It answered `200` from a route the caller could reach anyway: the same, and
  weaker still.
* It answered `200` from a route carrying the page's own session where the caller
  had none: that is the version worth reporting, and it is the one to state
  plainly rather than to leave implied.

What this is not: a filesystem. `injection.path` is a segment reaching a file or
an object store on the server, and it is a different class held by a different
Playbook. Here the server is doing exactly what its routing table says; the page
asked the wrong question.

## 5. State the claim, and state what would refute it

The Hypothesis is `injection.client_path` on the page. It is supported when the
Receipts of a mission carrying an encoded traversal show the page requesting a
route different from the one the control mission produced. It is refuted when the
two Receipt lists show the same route with the traversal encoded inside it.

Cite the Tool run and both Receipts. A rendered error message is not the finding
and neither is a screenshot of one.

## 6. One segment, one route, inside scope

This Playbook's effects are `read_only`. It changes the path of a `GET` the page
was going to make anyway.

The traversal is bounded by what it can reach: a route on the same origin, which
the scope compiler has already classified, and which the door refuses if it is
out of scope. It does not walk upward until something answers, does not enumerate
routes with a wordlist -- that is `enumerate-surface` and a recon Playbook's work
-- and does not aim the page at another host. A segment that would move the
request off the recorded origin is not sent.

A mission that hit its ceiling or was refused at the proxy is inconclusive and is
reported as inconclusive.
