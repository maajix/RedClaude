---
description: An authenticated account list served twice from one source, one variant sorting by whatever column the caller names and the other by a column from a published list, beside a counter that changes on every read and a filter route that reflects its argument without using it.
bb:kind: own_pair
bb:classes: ["injection.query_field"]
bb:subject: /accounts
bb:facts: ["authenticated_endpoint", "query_parameter", "tech_orm"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 53 against the query_field class description ticket 53 added, from what the class says rather than from any Playbook's steps; the noisy counter and the reflecting filter route are the precision controls ticket 53 criterion 5 asks for.
---

# A sort the caller chose the column for

`GET /accounts?sort=<name>` returns the account list in the requested order, for
a caller holding a session. Every account carries a `risk_score` that no route
returns and that no interface offers as a sort. The two variants differ in one
lookup:

* **vulnerable** resolves the name against the stored record at run time, so any
  column the record has can order the list -- including the one nothing shows.
* **secure** resolves it against the two names it publishes and falls back to the
  natural order for everything else.

No quote is involved anywhere and no expression is concatenated. That is the
point of the class: an ORM binds values and cannot bind an identifier, so the
part of the query that names a column is the part still built by hand.

## What the two arms do here

Against **vulnerable**, `sort=risk_score` returns the same accounts in a
different order -- an order the caller was never offered and which encodes a
value the response does not contain. `sort=risk_scare` names nothing the record
has, so the list comes back in its natural order. Two requests differing in one
character, two different orderings.

Against **secure**, both names are outside the published list, both fall back to
the natural order, and the two responses are identical. The arms are invariant
against each other, which is this class's refutation -- and `sort=name` does
reorder the list on the same variant, which is what says the parameter works.

Neither variant errors on an unknown name, deliberately. A fixture whose
refutation depended on an error message would be grading whether the target is
talkative rather than whether the caller picks the column.

## The two precision controls, on both variants

`GET /accounts/live` returns a body carrying a counter that increases on every
request, so a reading that skipped its baseline has a route it can be wrong
about.

`GET /accounts/filter?field=<name>` puts the name back in the response and
returns the natural order regardless. It is a decoy for the reading that treats a
reflected parameter as evidence that the parameter reached a query.

## What the ground truth claims, and what it does not

`injection.query_field` on `/accounts` of the vulnerable variant, and nothing
else anywhere.

Nothing here parses an expression, so `injection.query_language` is false against
every route: a `sort` value containing a quote, a comment or a second clause
names no column and produces the natural order on both halves. The hidden column
is never returned, only ordered by, which is the honest shape of this defect and
the reason the reading's evidence is a difference in order rather than a leaked
value. Nothing here writes.
