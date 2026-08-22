---
description: Ask whether an activity, audit or trace view hands one caller the request data of another, by having a second Identity send one marked read and then looking for that marker in the view the first Identity is served, with the second Identity's own view as the control that says the marker was recorded at all.
bb:category: information_disclosure
bb:outputs: ["information_disclosure.log_record"]
bb:triggers_all: ["authenticated_endpoint", "multiple_test_identities", "tech_telemetry"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-05-15
bb:provenance: Written for ticket 55 as the v2 replacement for v1's logging page against a new log_record leaf added by ticket 55; the v1 page carried no attachments, and its log-forging payloads, its log-file fetching and its alerting-evasion advice are refused by step 7.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "content_match", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "content_match", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "content_match", "polarity": "supports", "min_count": 1}]
---

# Ask whose requests are in the record the application keeps

An application that keeps an activity trail keeps it about everybody. The view
that shows it was usually written to show a caller their own history, and the
filter that makes it theirs is one clause in one query. When that clause is
missing, the view is still called "your activity" and it is the whole
application's.

The subject is an authenticated read on an application a recon pass identified as
running a logging or telemetry backend, with two Identities the Program controls.
The question is whether one caller's view carries another caller's request data,
and the whole reading is six requests.

## 1. Say what the fingerprint bought, and name the view

The telemetry fingerprint is why this Playbook was selected and it is not
evidence: 018 records `technology_identified` as non-evidential, and a backend
that collects events says nothing about whether the application publishes them,
to whom, or with what in them.

Name, from the Surface rather than from a guess:

* the view -- the route that returns recent activity, audit entries or traces
* the two Identities, and which one reads and which one is read about

Complete this step with the route and the two Identity slots.

## 2. Establish the baseline, twice

Send the view through `mcp__rk2__http_request`. Then send it again, unchanged.
Both go out as whichever Identity the Task was opened under -- the step does not
choose it and there is no argument for it -- and that Identity is the one this
Playbook calls the reading Identity.

Two identical requests, because everything below compares against this one and
because an activity view is the most likely route on a target to differ between
two sends: it is a list that grows, and the second request is itself an entry in
it. Record what moved. Whatever moved for that reason is not evidence.

## 3. Have the second Identity send one marked read

One request from a second Task, opened under the other Identity: an ordinary read
the second Identity is entitled to make, carrying one unique marker in one query
parameter
-- `rk-probe-<task>` and nothing else.

A read rather than a write, and an ordinary route rather than an interesting one.
The only state this reading creates anywhere is the entry the application writes
for every request that reaches it, which is why this Playbook is `read_only`: it
stores nothing the target would not have stored for a caller who was not testing
anything.

The marker is short, is not a payload, and carries no separator, no newline, no
control character and no markup. Step 7 says why.

## 4. Read the view under the reading Identity

One request in the reading Identity's own Task: the view again, unchanged from
step 2.

Then search the body for the marker from step 3, and for the second Identity's
own name, slot or account label. Name what was found and quote the entry it sits
in.

## 5. Read the view under the second Identity, as the control

One request in the second Identity's Task: the same view. A reading that needs
two Identities is two Tasks, and steps 2 to 5 are differenced across the Receipts
the two of them produced.

This is the control and it is what makes a negative mean something. The marker
has to be here. A view that does not carry the second Identity's own marked
request is a view that did not record the request at all -- perhaps it records
writes only, perhaps it is delayed, perhaps the marker never reached it -- and
without this leg an absent marker in step 4 proves nothing about scoping.

## 6. Sort what the view carries, then state the claim

Read the entries and sort what is in them, because two of the three piles are not
findings.

* **Public metadata.** A build string, a region, a service name, a status word,
  an entry count. The application publishes these to everybody by other means. A
  reading that reports them has reported the application's own footer.
* **Another caller's request data.** A path, a query string, a parameter value, a
  header, an address or an identifier belonging to the second Identity. This is
  the class.
* **A path the view names.** An archive, an export, a download link. Naming one
  is not reaching one. Request it once, under the reading Identity, and let the
  answer decide: a path that refuses or does not exist is a string in a document
  and nothing else, and it is not part of the claim.

The Hypothesis is `information_disclosure.log_record` on the view. It is
supported when the marker from step 3 appears in the document served to the
reading Identity, the control leg shows the marker was recorded, and the two
baseline reads were invariant apart from what step 2 recorded as moving. It is
refuted when the marker is present in the control leg and absent from the reading
Identity's view -- which is what a view with its one filter clause looks like.

Anything else is inconclusive: a view whose entries cannot be attributed to a
caller, a marker absent from both legs, a route that answers the same fixed page
to both Identities.

Three neighbours are close.

* Where the extra material is a key, a token or a password rather than a record
  of a request, the class is `information_disclosure.credential_material` and the
  Playbook is `secrets` -- and if the leaked request data itself carries one, say
  so in the observation and route it there.
* Where the caller named the record it wanted and got somebody else's, the class
  is `authorization.object_ownership` and the Playbook is `object-ownership`.
  Nothing in this reading names a record: the view is asked for by itself.
* Where the internal detail arrived because a request was made to fail, the class
  is `information_disclosure.error_detail` and the Playbook is
  `exceptional-conditions`.

Cite the Artifacts, quote the entry, and name which Identity it belongs to.

## 7. The ceiling

This Playbook is `read_only` and its baseline is a session that stays stable. It
sends six requests: two baselines, one marked read, one view under each
Identity, and at most one request to a path the view named.

It does not forge a record. Nothing it sends carries a newline, a carriage
return, a log delimiter, an escape sequence, a format specifier or a structured
fragment that a log writer might read as a field of its own -- a reading that
made the application write an entry that was not true has damaged the one record
an operator will use afterwards to work out what happened.

It does not fetch the log. It does not request a log file, an archive path it
learned from anywhere but the view itself, a backup of one, or a telemetry
backend's own interface. A log lying in the served tree is a document that was
not meant to be published, which is `attack-surface`'s question and not this one.

It does not try to disappear. It does not vary its own marker to defeat a
correlation, spread its requests to stay under a threshold, strip a header that
identifies the engagement, or do anything else whose purpose is that the target's
operators see less of it. Everything this harness sends is meant to be
attributable to the engagement afterwards.

It does not read the second Identity's data anywhere except through the view. The
marked request in step 3 is one the second Identity was entitled to make.

Where the view is served to both Identities identically and carries nobody's
request data, the verdict is `refuted` and the reading is over.
