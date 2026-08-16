# Sign-up, login and register: three routes, and only one of them is the Playbook

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## The one class this Playbook claims

`authentication.credential_verification` on the login route: the server reaches
an authenticated state without having compared the secret. Everything else the
v1 text covered is written down here so the next maintainer does not fold it
back in.

## Not that: registration

Registering accounts is an account mutation against the target's production data
and most Programs bound it explicitly. The v2 Playbook does not register: it
leases an Identity through a slot, which is the operator's decision rather than
the run's.

Where registration itself is defective -- an email that is never verified, a
role field the client can set, a username that collides with an existing account
-- those are real findings and they are not this class. A client-set role is
`authorization.function_access`. An unverified email that grants access to a
domain-scoped tenant is `authorization.tenant_isolation`.

## Not that: username enumeration

"This account does not exist" versus "wrong password" is a `response_differential`
and it is `information_disclosure.identifier_oracle` in the ticket 18 vocabulary.
It is a common report, it is frequently accepted at low severity, and it is not
what the Playbook above measures. Keeping it separate matters because the
enumeration reading wants *many* accounts and the verification reading wants
*one*, sent five ways.

Timing is the same story with a worse signal-to-noise ratio. A timing difference
across a network, without a repeat count and a distribution, is not evidence.

## Not that: password policy

A target that accepts `123456` has a weak policy. It is a configuration
statement, there is no differential behind it, and reporting it consumes the
Program's triage budget on something they chose.

## What the login route is good for besides this class

It is the cheapest place to learn the shape of the session: what the session
artifact is, which cookie carries it, what attributes the server scopes it with,
whether a second factor is asked for. Those readings feed `session_handling` and
`authentication.factor_enforcement`, and the run should record them from the
control response it already has rather than sending more requests for them.
