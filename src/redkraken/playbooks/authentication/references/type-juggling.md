# Type juggling, and why it is the same question as a missing check

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## Why this note sits under `authentication`

The v1 pack filed type juggling as its own topic because the technique is
memorable: send `true` where a string was expected, send `0` where a hash was
expected, send an array where a scalar was expected, and watch a comparison
return the wrong answer.

But the technique is not the finding. The finding is that the server reached an
authenticated state without comparing the secret it holds against the secret it
was sent, and that is `authentication.credential_verification` no matter which
language's coercion rules produced it. Filing it separately produced two
Playbooks that would have proposed the same Hypothesis from the same evidence.

## The shapes that are worth sending

One per request, and each one is a *type* change rather than a value change:

* `null` and the field omitted entirely -- different, because one reaches the
  comparison with an empty operand and the other may skip the branch
* `""` -- an empty string of the right type
* `true` and `false`
* `0` and `1` as numbers, not strings
* `[]` and `["x"]`
* `{}` and `{"$ne": null}` where the backing store parses documents

The last one is a document-store operator rather than a coercion, but it
belongs in the same list because it produces the same reading: a comparison that
matched something the caller never knew.

## Why the Playbook refuses to iterate

Sending `"password"`, then `"Password1"`, then `"letmein"` is guessing. It is
bounded by the Program's rules of engagement and by `rate_limiting`, it is
noisy, and it has never once been the difference between a valid report and an
invalid one in this class. The Playbook sends each *shape* once and stops.

## What the control is for

Every one of these variants can produce a `200` on an endpoint that answers
`200` to everything. Without the wrong-secret reading stored first, "the server
accepted `true`" is a sentence about a server nobody proved authenticates. That
is why the Playbook's supported edge needs a `credential_effect` on the control
row and refuses to promote without one.

## The neighbouring classes

* A coerced comparison that decides *which account*, not whether the credential
  was right, is `authorization.object_ownership`.
* A coerced comparison inside a reset token check is
  `authentication.recovery_flow`.
* A parser that returns a stack trace for `{}` is `information_disclosure`
  through `error_detail`, and worth recording, but it is not this class.
