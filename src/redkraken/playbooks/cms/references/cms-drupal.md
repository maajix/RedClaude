# Drupal: JSON:API as the parallel route, and the exploit chain around it

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

Version first, exploit second. Read `CHANGELOG.txt`, `core/CHANGELOG.txt` or the
generator tag to pin a release. Run droopescan for the module list. Then the
named chains: the Drupalgeddon form-API defects, where a request whose parameter
name is itself a render array gets the render pipeline to evaluate a callback, so
one crafted `POST` to a registration or comment form ends in command execution.
Around them the smaller items -- `/user/1` to confirm the admin account exists,
`/node/1` upward to walk content by identifier, `/user/password` to enumerate
which addresses are registered, `/sites/default/files/` for whatever the site
wrote there, and default credentials on `/user/login`.

## Why the Playbook does not run it

**The chains are code execution with no smaller setting.** A render-array payload
that reaches the callback runs a command on the host. There is no inert version
of it, so no `read_only` reading can contain it, and a Program that granted web
testing did not grant this.

**A release number is not an exposure.** `CHANGELOG.txt` says which tarball was
unpacked. It does not say which patches the distributor backported, which modules
are enabled, or whether the vulnerable route is reachable. Step 1 of the Playbook
records the fingerprint and then requires two compared responses before anything
is claimed.

**Walking `/node/1` upward is enumeration by identifier.** That question --
does the application serve a record to a caller who names it and should not have
it -- already has a Playbook (`object-ownership`) with a control leg that says
what the caller was entitled to. Doing it here would be the same claim with worse
evidence.

**`/user/password` as a registration oracle is an attack on the site's users.**
Probing whether an address has an account puts other people's data in the
reading's output for no gain the Playbook can act on.

## What the Playbook kept

The structural insight the page had without stating it: Drupal ships its own web
services, and they read the same node store the theme does. `/jsonapi/node/...`
and the older `/rest/` endpoints are routes somebody enabled once, that outlive
the person who enabled them, and whose access rules are a separate configuration
from the ones the site's own pages use. That is exactly the shape `cms` is about
-- one store, two doors, one conversation about permissions.

`/jsonapi/` publishes its own resource index, which is where step 1's candidate
names should come from. Five names, one request each, and a name that answers
`404` is finished.

## The trap

Drupal's access system is per-entity and per-field, so a JSON:API response is
frequently a *partial* one: the route answers `200`, the collection is there, and
the entries are the ones the anonymous role may see, with restricted fields
stripped. That is the platform working. The finding needs a specific record --
the identifier written down in step 2, from the answer the leased Identity got --
to appear in the anonymous document. Anything less is the reading mistaking a
correctly filtered list for an open door.
