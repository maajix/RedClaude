---
description: An account record the caller owns, edited through one PATCH, served twice from one source, one variant writing every property the body names and the other writing two and naming the ones it refused.
bb:kind: own_pair
bb:classes: ["authorization.object_property_write"]
bb:subject: /account
bb:facts: ["authenticated_endpoint", "body_parameter", "json_request", "scim_surface", "state_changing_method"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 100 against the class description this migration adds, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# The caller owns the object and not every property of it

The same application exposes `GET /scim/v2/ServiceProviderConfig` on both
variants, with the SCIM 2.0 ServiceProviderConfig schema and PATCH support. That
stable capability document is why this fixture presents the application-scoped
`scim_surface`; it is a trigger/control fact and not the property-write
differential graded below.

`POST /session` issues a session for `alice`. `GET /account` returns her record.
`PATCH /account` writes what the body names.

Every request in this fixture is `alice` editing `alice`'s own record. There is
no second user, no second identifier and no route that reaches another row. The
ownership question is answered `yes` on both variants and on every request, so
it cannot be what a differing answer read.

The variants differ in one place:

* **vulnerable** binds the whole body onto the record. A `PATCH` carrying
  `{"display_name": "A", "role": "admin", "credit": 5000, "verified": true}`
  returns the record with all four written.
* **secure** binds `display_name` and `email`. Anything else is `403`, and the
  answer lists what it refused and what it would have taken.

## Why both halves are here

A pair whose secure half answered `200` and silently dropped the extra keys
would be unreadable: nothing in the response would say the write was refused
rather than performed and reverted, and a run would have to guess from a field
it cannot see the history of. So the secure half refuses out loud.

A pair that differed only in the response body of a `GET` would grade a run for
reading a record. The reading here is a write and its after-state.

## The control

The `display_name` write, which both variants accept and both variants reflect.
It is what says the route works, the session is real and the body was parsed --
so a refusal on `role` is a decision about that property and not about the
request.

## What is not here

`authorization.object_ownership` is the object named by the request, and this
fixture never names another one. `information_disclosure.excess_field` is the
read half -- a field coming back that should not have -- and both variants here
return the same field list. `injection.object_graph` is which *type* a payload
reconstructs, and nothing here deserializes into a class.

Nothing here escalates through a second route, a role endpoint or an admin
console. The escalation, if a report wants one, is a consequence of the write
and is not served by this fixture.

## Ground truth

* **vulnerable** holds `authorization.object_property_write`. A property the
  application owns -- `role`, `credit`, `verified` -- is set by a body the
  caller wrote, on an object the caller does own.
* **secure** holds nothing this catalogue declares. Two properties are writable
  and the rest are refused by name.
