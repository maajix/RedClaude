# SOAP surfaces, and the three places they differ from the rest

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## Why this is a reference and not a Playbook

SOAP is a shape a surface can have, not a question anybody asks. The classes a
SOAP endpoint can hold are the ones every other endpoint can hold --
authorization, injection, document parsing, rate limiting -- and a Playbook per
transport encoding would be seven copies of each Playbook, differing in how the
body is spelled.

What is genuinely different is narrow, and it fits in this file.

## 1. The operation is not in the path

A SOAP endpoint is usually one path, and which operation is being called is in
the body or in a `SOAPAction` header. Everything in this system that keys on an
endpoint -- the deduplication cell, the subject of a Task, the specificity of a
trigger -- therefore sees one endpoint where an application has forty
operations.

The consequence for the api Playbook: a sequence of identical requests to one
path is a sequence against one operation, and it must say which. The consequence
for surface work upstream: an operation worth testing separately is worth
recording as its own entity, and the recorded parameter is what tells them
apart.

## 2. The parser is part of the attack surface

A SOAP body is XML and something parses it. That is `injection.document_parser`
and it belongs to a Playbook that declares that class, with the evidence that
class needs. It is named here because a maintainer reading "SOAP" should be
reminded that the encoding is itself an interpreter, and not because the api
Playbook may claim it -- it may not.

## 3. A fault is not an error

SOAP answers `200` with a `Fault` element for conditions other stacks answer
with a `4xx`. Anything reading statuses will read a refusal as a success.

This matters directly to the api Playbook's step 4. A sequence of `200`s that
are all Faults is invariant, and the Playbook would read invariance as "nothing
is counting" when what happened is that every request failed. The Playbook's
control step is what catches it, and it catches it only if the control checks
what the body says rather than what the status line does.

The same trap has the same shape in gRPC, where the answer is in a trailer, and
in GraphQL, where it is in an `errors` array beside a `200`. Three encodings,
one lesson: read the layer the application answers at.

## What not to carry over from v1

The v1 material leaned on requesting the service description and enumerating
operations from it. That is fine and it is surface. It is not a finding, and the
description being reachable is not `information_disclosure.artifact_exposure`
unless it turns out to be a document that was not meant to be published, which
is a question about that deployment rather than about SOAP.
