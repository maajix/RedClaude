# Apache Tomcat: where the `/..;/` trick came from, and what it is evidence of

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The container-specific checklist. Find `/manager/html` and `/host-manager/html`;
try `tomcat:tomcat`, `admin:admin`, `tomcat:s3cret` and the rest of the shipped
list; with a manager session, upload a WAR and browse to the servlet it deploys.
Read the version off the default error page or off the shipped manual. Look for
the example servlets left enabled -- the session example, the cookie example, the
request header dump. Check for the AJP connector on 8009 and the Ghostcat file read
against it. And the path trick: `/..;/manager/html`, because a reverse proxy
matching on `/manager` does not see `/manager` in that string, while Tomcat
resolves the path parameter away and does.

## Why the Playbook does not run most of it

**The credential list is credential attack.** Trying shipped passwords against
somebody's management console is not in scope on any Program this harness runs
under, and a WAR upload is code execution on the target's host.

**The AJP connector is not the web ingress.** Ghostcat reaches a port behind the
front end. Criterion 3 of the ticket that authored `deployment` draws the line
exactly here: web and API ingress the Program scoped, and nothing underneath it.
No port scanning, no origin discovery, no second listener.

**The default error page's version string is a fingerprint.** It proposes a
hypothesis. It settles nothing, and it is never the basis of an impact claim.

**The example servlets are a different class.** A session example left enabled is
an artifact in the served tree, which is `attack-surface`'s question, not a
question about a rule at the edge.

## What the Playbook kept

The path trick, generalised, and it is the reason this page is attached to
`deployment` at all.

`/..;/manager/html` is not a Tomcat defect. It is two programs disagreeing about
what a path is: one matched the bytes, the other resolved them. Tomcat happened
to be the container where the industry noticed, because its path-parameter
handling (`;` and everything after it, per segment) differs from what a proxy's
prefix match assumes. The same disagreement produces `/admin/./config`,
`//admin/config`, a trailing dot or space on a segment, and `%2f` where the two
programs decode at different times.

So step 3's list of spellings is this page's technique with the vendor removed.
And step 4 -- the same transformation against a path nobody restricted -- is what
this page never had: without it, an arm that comes back `200` might mean the rule
was bypassed, or might mean the deployment simply serves dot segments to
everybody.

## The trap

`/..;/` is memorable, so it gets sent at things that are not Tomcat and reported
when it works. Two cautions the Playbook encodes.

First, the refusal has to have come from the front end. If the application
produced it, a second spelling getting through is the application's own check
failing, which is `authorization.function_access` and a different Playbook. Step
1 makes the reading say which program refused, from the answer's own shape,
before anything else happens.

Second, `..` in any spelling can climb out of the intended prefix rather than
land on it. The Playbook's arms are same-route rewritings that resolve to the
path already identified -- they ask whether the rule was bypassed, not whether
the tree can be walked. Walking a tree is `file-resolution`.
