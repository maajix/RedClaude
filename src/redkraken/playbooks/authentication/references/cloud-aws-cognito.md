# Hosted identity services, and which half of them is the target

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## The split that decides scope

An application built on a hosted identity service -- Cognito, Firebase Auth,
Auth0, Entra -- has two halves and only one of them is ever in scope:

* the **provider's** endpoints: the token issuer, the user pool API, the hosted
  login page. Those belong to a vendor the Program did not authorise. Sending
  malformed credentials there is testing somebody else's product.
* the **application's** configuration and its own routes: which pool it points
  at, which client identifier it ships, whether sign-up is open, whether its own
  API checks the token it was handed.

Everything worth reporting in this family is in the second half. It is a
configuration the Program owns, reachable from material the application itself
publishes.

## What the client bundle already tells you

Identity-service clients ship their configuration to the browser by design: a
pool or project identifier, a region, a public client identifier, sometimes an
API key that the vendor documents as public. Recording those is `technology` and
`endpoint` surface for the entity graph.

Reporting a published client identifier as a leaked secret is invalid, and it is
one of the most common invalid reports in this space. The vendor's documentation
says it is public. The finding is what that identifier *reaches*.

## The configuration questions that are findings

* **open self-registration into a tenant that grants access.** If the client
  identifier admits sign-up and a fresh account lands inside an application
  tenant, that is `authorization.tenant_isolation` and the evidence is what the
  new account can read.
* **unverified attributes trusted by the application.** A self-set attribute --
  an email domain, a role, a group -- that the application reads as authority is
  `authorization.function_access`, and the reading is our own account with the
  attribute set.
* **the application not checking the audience of the token it accepts.** That is
  `authorization.token_scope` and it belongs to the `jwt-jose` Playbook, which
  has the reading for it.
* **an identity pool that hands credentials to unauthenticated callers.** The
  finding is whatever those credentials reach in the Program's own account, read
  once, never enumerated.

## What this note is doing under `authentication`

Only the first reading in the `authentication` Playbook: a hosted service is
where the "does the check even run" question is usually answered *yes*, quickly,
because the vendor implemented it. That is a useful early refutation, and it
sends the run to the configuration questions above instead of at the provider.
