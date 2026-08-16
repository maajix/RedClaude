# Verb tampering: the same route, spelled with a different method

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## The two root causes

Both produce the same symptom -- a route that refuses one method and serves
another -- and they live in different halves of the stack.

**Configuration.** The rule was written against a method rather than against the
resource. Apache's `<Limit GET>` requires a valid user for `GET` and for nothing
else; Tomcat's `<http-method>GET</http-method>` inside a `security-constraint`
does the same; the ASP.NET `<allow verbs="GET">` form has the same shape. `POST`,
`HEAD` or `PUT` to the same path skips the check entirely. The correct spelling
is the inverse: `<LimitExcept GET POST>`, `<http-method-omission>`, or a rule
with no verb in it at all.

**Code.** The check and the action read different sources. The PHP idiom is
`preg_match` against `$_POST['x']` guarding a `system()` call that uses
`$_REQUEST['x']` -- so the same value arriving as a query parameter is executed
without ever meeting the filter. Anything with a merged request bag has this
available: `$_REQUEST`, a framework that folds query and body into one map, a
router that binds parameters by name regardless of where they came from.

Configuration-based tampering is what scanners find. Code-based tampering is
what they miss, because the difference is invisible from outside until the two
requests are compared.

## What the attached Playbook does with this

Step 4 sends the same step under a different method, including `HEAD`, and reads
the outcome route afterwards. The reason it is in a workflow-order Playbook
rather than one of its own: when the flow refuses a step and a different method
of the same step is accepted, what has been shown is that the ordering rule was
enforced by something that only looked at one verb. The claim is still
`business_logic.workflow_order` -- the step ran without the steps before it --
and the method is how it ran.

Where a method reaches a route the flow does not contain at all, the claim
changes to `authorization.function_access` and belongs to whichever Playbook
holds that class. Where a method exposes a request the front and the back of the
stack parse differently, that is `transport.request_framing`.

## Reading `HEAD` honestly

`HEAD` is the most productive verb here and the easiest one to over-report.
A `200` to `HEAD` with a plausible `Content-Length` says the handler ran and
produced a body; the body itself never arrives, by definition. So `HEAD` is good
evidence that a route executed and is poor evidence of what it returned. In the
attached Playbook the outcome route settles it: `HEAD` sends the step, and the
subsequent read of the authoritative state says whether the step actually
landed.

`TRACE` is worth an `OPTIONS` mention and nothing more here. It sometimes
reflects headers a proxy added, which is interesting to a maintainer and is not a
workflow-order finding.

## Enumerating what is allowed

```
curl -i -X OPTIONS https://target/checkout/confirm
# Allow: POST,OPTIONS
```

`Allow` is a hint, not the truth: servers list what the framework registered,
which is frequently narrower or wider than what actually dispatches. The
override header `X-HTTP-Method-Override: PUT` is a third spelling, honoured by
enough middleware to be worth one request, and it is a header rather than a
method so a method-scoped rule never sees it.

## What stays out

Method fuzzing across an entire host, invented verbs sprayed at every route, and
anything aimed at a service the Program did not name. The attached Playbook
sends a handful of methods at one recorded route. The value here is in the
comparison, not in the coverage.
