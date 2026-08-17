---
description: One process serving a front end in front of an application, with a rule that refuses one path, one variant matching that rule against the bytes it was handed and the other against the path those bytes resolve to, beside an unrestricted path that serves every spelling and a route whose body counts requests.
bb:kind: own_pair
bb:classes: ["authorization.edge_rule"]
bb:subject: /admin/config
bb:facts: ["read_method", "tech_edge_proxy", "web_surface"]
bb:identities: []
bb:provenance: Written for ticket 55 against the edge_rule class description ticket 55 added, from what the class says rather than from any Playbook's steps; the unrestricted path that serves every spelling and the counting route are the precision controls, and the served-by header is what lets a reading say which of the two programs answered.
---

# Two programs, one path, two opinions about what it says

The application behind this fixture has no access control at all. `/admin/config`
returns its configuration to whoever reaches it, which is not the defect and is
not unusual: the deployment's answer was to put the rule in front, and the front
end refuses `/admin/config` before the application ever sees it.

Both variants run that front end. They differ in one line of it:

* **vulnerable** matches the rule against the request path as it arrived --
  the bytes, spelled exactly as `/admin/config`.
* **secure** resolves the path first -- dot segments, empty segments, matrix
  parameters, percent-encoded separators, trailing dots and spaces -- and
  matches the rule against what it resolves to.

The application resolves the same way on both variants, because it always did.
The defect is not that the application is careless: it is that two programs
disagreed about what a path is, and the one holding the rule is the one that
was wrong.

Every response says which program produced it, in `X-Served-By`. A real
deployment rarely says so this plainly; this one does because the claim this
class is about is *which* program answered, and a fixture that made that
unknowable would be grading a reading's guesswork.

## What the two arms do here

Against **vulnerable**, `GET /admin/config` is `403` from `edge`, and
`GET /admin/./config` is `200` from `application` carrying the configuration.
The same holds for `//admin/config`, `/admin;v=1/config`, `/admin%2fconfig` and
`/admin/config.` -- five spellings the rule does not recognise and the
application does.

Against **secure**, every one of those six requests is the same `403` from
`edge`, byte for byte. That invariance is this class's refutation.

## The two precision controls, on both variants

`GET /public/index` is `200` from `application`, and so is every one of the six
spellings of it. It is the unrestricted path a reading needs in order to tell
"the rule was bypassed" from "this deployment happens to serve dot segments":
a transformation that fails here fails everywhere and proves nothing about the
rule.

`GET /status` answers with a counter that increases on every request, so a
reading that skipped its baseline has a route it can be wrong about.

## What the ground truth claims, and what it does not

`authorization.edge_rule` on `/admin/config` of the vulnerable variant, and
nothing else anywhere.

No spelling here escapes the path space the application serves. `..` resolves the
way the application resolves it and reaches no file outside the four routes this
fixture has, so nothing here is `injection.path`. The application performs no
check of its own, so a bypass here is never
`authorization.function_access` -- there is no function-level rule inside to
get past. No session exists anywhere in this fixture and no identity is issued,
so no response carries anybody's data. No response caches, varies or stores
anything, so this is not `information_disclosure.cached_response`. No refusal
names a rule, a pattern or a server build, which is deliberate: a fixture whose
`403` explained itself would be grading
`information_disclosure.error_detail`. Nothing here writes.
