# Reading an API surface, and why this Playbook claims one class

Maintainer notes. Nothing here reaches a model: the projection is built from the
frontmatter and the body of `playbook.md`. Written fresh for v2; the v1 text is
not in this repository.

## Why the api Playbook is a rate-limiting Playbook

The v1 api topic was three files: a general note on reading an API surface, a
SOAP note, and a rate-limit bypass note. Only the third named a defect. The
other two are knowledge about what an API *is*, which in this system is surface:
it decides what gets recorded and which Playbooks become selectable, and it is
not a claim about anything.

So the topic migrated as one Playbook claiming the one class its material named,
and the surface half went where surface belongs -- `enumerate-surface` and the
entity graph. A Playbook called "api" that claimed six classes because the
topic was broad would be the v1 mistake with v2 metadata on it.

## What reading the surface produces, and for whom

An API's specification -- an OpenAPI document, a schema endpoint, a client
bundle -- is a source of endpoints, parameters and value classes. Those are
entities, parameters and observations. Two of them decide whether this Playbook
is ever selected at all: the application being typed `api`, and the parameters
being typed well enough that another Playbook can find an object identifier or a
URL-valued field.

That is the honest relationship between this reference and this Playbook. The
surface work is upstream of it and is a different role's Task.

## Undocumented does not mean undefended

A route absent from the specification is a route the specification did not
mention. It is not evidence that nobody thought about who may call it, and a
report built on "it was not in the specification" is a report about the
specification.

The same holds in the other direction: a route the specification marks as
requiring a scope is not thereby enforcing one. Both are worth recording as
surface, and neither is a claim.

## Version prefixes

An older prefix beside a current one is a common finding shape and a common
invalid report. The version prefix is surface. Whether the older one enforces
what the newer one does is `authorization.function_access` or
`authorization.object_ownership` on a specific route, tested by a Playbook that
declares that class, with two identities and a control.

## Why the risk floor is approval_required

This is the only Playbook in the ticket 49 set whose method is to spend
requests. Every other one sends a handful and reads the difference; this one
sends a declared sequence and reads whether the sequence was counted. That is
the same activity a program's rules of engagement bound, so the decision to run
it belongs to whoever holds the Program rather than to the scheduler, and
`approval_required` is how this corpus spells that.
