---
description: Ask whether a gRPC method checks who is calling it, by invoking the same method under two leased Identities and reading the status code the server answers each with.
bb:category: authorization
bb:outputs: ["authorization.function_access"]
bb:triggers_all: ["multiple_test_identities", "tech_grpc"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-02-15
bb:provenance: Written for ticket 49 as the v2 replacement for v1's grpc pack, against the function-access leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
---

# Ask whether the method is anyone's to call

A gRPC service is a list of methods, and the list is usually longer than the one
the client uses. Interceptors are where authorisation lives in these stacks, and
an interceptor is configured per service or per method rather than derived from
the schema -- so a method nobody's client calls is a method nobody's
interceptor was written for.

The question here is about the method, not about the message it carries. What
the method returns matters only insofar as it says the call was allowed.

## 1. Name the method and the two Identities

The subject is an endpoint the recorded surface has identified as gRPC. Read the
method from the recorded surface: the path is `/package.Service/Method` and it
is the whole of what this Playbook varies against.

Name two Identity labels. Label A is the one whose client calls this method.
Label B is the one that should not reach it.

If only one Identity is leased, the comparison has no second side and this
Playbook does not apply to the subject.

## 2. Read the status the transport carries, not the one the framing does

gRPC answers `200` at the HTTP layer for almost everything, including a refusal.
The decision is in the `grpc-status` trailer or header: `0` is OK, `7` is
PERMISSION_DENIED, `16` is UNAUTHENTICATED, `12` is UNIMPLEMENTED.

Every claim below is about that value. A run that read the HTTP status has read
the framing and not the answer, and will report every refusal as a success.

## 3. Establish the baseline and the control

Send the call through `mcp__rk2__http_request` with the request body the recorded
surface holds for this method. It goes out as whichever Identity the Task was
opened under -- the step does not choose it and there is no argument for it -- so
label A's half of this reading is the Task opened under label A. That is the
baseline: what the method answers a caller it is for.

A reading that needs two Identities is two Tasks. Label B's half is a second
Task opened under label B, and its first call is a method label B's own client
calls. That is the control, and it is what tells an enforced boundary apart from
a credential the server never accepted. The differential is made by comparing
the Receipts the two Tasks produced. Follow `use-identity`: a gRPC deployment
that carries the token in metadata rather than in a cookie will silently treat a
missing header as anonymous.

## 4. Send the variant

Label A's call, unchanged, sent from label B's Task. One variable: the Identity
that Task was opened under. Same method, same message bytes, same content type.

Do not reach for a method neither Identity calls. That is a second question --
whether the method exists for anyone -- and mixing it in makes an
UNIMPLEMENTED indistinguishable from a refusal.

## 5. Difference the two answers

Run `compare-responses` over the baseline and the variant Artifacts, and cite
the `grpc-status` on each. `0` under label B where label A was the intended
caller is the finding. `7` or `16` under label B, against a control that
returned `0`, is the boundary working.

## 6. State the claim, and state what would refute it

The Hypothesis is `authorization.function_access` on the method. It is supported
when the variant returns OK under label B and the control shows label B's
credential being accepted on its own method. It is refuted when the variant
returns PERMISSION_DENIED or UNAUTHENTICATED against a control that succeeded.

`12 UNIMPLEMENTED` is inconclusive, not refuting: it says this build does not
have the method, which is a fact about the deployment and not about who may call
it. So is a transport-level failure -- a stack that requires HTTP/2 prior
knowledge and got something else is answering about the connection.

If the message that came back carries somebody else's object, that is
`authorization.object_ownership` and this Playbook may not claim it. Record the
observation and let the scheduler decide what asks about it.

## 7. Leave the service as you found it

This Playbook reads. It calls the method it was given and does not enumerate the
service, does not send a mutating method to see what happens, and does not retry
with a forged metadata header. Its baseline is `stable_session`, so the runtime
drops it beside anything that rotates one.
