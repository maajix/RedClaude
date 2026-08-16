# GraphQL, and the four claims a maintainer keeps confusing

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## The one class this Playbook claims

`information_disclosure.excess_field`: a field is returned to an Identity that
should not receive it. The evidence is two Identities querying the same
selection against the same object and getting different documents back, with
the second Identity's authentication proved by a control.

That is the whole Playbook. The rest of this file is the material that is *not*
that, kept beside it so the next maintainer does not fold it in.

## Not that: introspection is reachable

The schema being queryable is surface. It is what makes the Playbook selectable
-- the `graphql_surface` fact -- and it is a `technology_identified` style
observation rather than a finding.

Reporting introspection as a vulnerability is one of the highest-volume invalid
reports in this whole space. The schema is documentation. If a field named in it
returns data the caller should not have, the finding is that field, and the
Playbook above is what shows it.

When introspection is disabled, the Playbook is not blocked -- it is a Playbook
about a selection the client already makes. Field names come from the
application's own traffic, which is a better source anyway because it names the
selections that are actually served.

## Not that: aliasing and batching

One document carrying two hundred aliased copies of one field, or one request
carrying an array of documents, is a cost claim: the server does two hundred
units of work for one unit of request. The class is
`rate_limiting.resource_cost` and the evidence is a timing or a cost
differential, not a disclosure.

It is out of scope here for a second reason beyond the class: the honest version
of that test is a deliberate load, and a deliberate load needs the same
approval a rate-limit sequence needs.

## Not that: nested depth as a finding

Deep recursion through cyclic relationships is the same cost claim wearing a
different shape. Same class, same approval, same reason it is not here.

## Not that: a mutation that should have been refused

That is `authorization.function_access` or `authorization.object_ownership`
depending on whether the refusal should have keyed on the operation or on the
object, and it is a mutating test. This Playbook declares `read_only` and it
means it: every request it sends is a query.

## The trap worth carrying forward

GraphQL answers `200` with an `errors` array. A response can be a refusal, a
partial success, or a total failure, and the status line says the same thing in
all three cases.

The Playbook's step that reads the difference must read the `data` and `errors`
members, not the status. A comparison that finds "both returned 200" has found
nothing, and a comparison that treats an `errors`-only document as a successful
empty result has inverted the finding. The same trap has the same shape in SOAP
faults and gRPC trailers.

## Partial data is the interesting case

The most common true positive shape here is a document that carries `data` for
the fields the caller may see, `null` for one it may not, and an entry in
`errors` naming it. That is a correctly behaving server.

The finding is the case where the second Identity gets a value where the first
Identity's document had a `null` with an error beside it, or vice versa. Which
is to say: the null-versus-value difference is the signal, and it lives inside
the response body at a path the write-up has to name.
