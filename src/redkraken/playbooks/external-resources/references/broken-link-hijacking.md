# Broken link hijacking: find the name, do not take it

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

Crawl the target, collect every external reference, check which of the hosts are
takeable, take one, prove it. The takeable answers are well known and each has a
provider's signature:

```
NoSuchBucket / The specified bucket does not exist   S3 and friends
There isn't a GitHub Pages site here                 GitHub
Domain mapping upgrade for this domain not found     several PaaS
Repository not found / 404 from a package registry   npm, PyPI
NXDOMAIN on a CNAME target                           an expired domain
```

Then: register it, serve a file, screenshot the target loading it, attach.

## The half the Playbook uses

Everything up to and including the classification. Collect the references,
separate the ones that carry executable authority from the ones that do not,
resolve each name, and record which of them nobody currently holds.

The refinement worth stating is which references count. v1 treated a dead `<img>`
and a dead `<script src>` as the same finding, and they are not close. A script
tag, a stylesheet, a same-origin frame and a service worker registration each
grant the loaded origin the target's own privileges. An image grants nothing.
Sorting the crawl output by that distinction removes most of it.

The second refinement is `integrity`. A script tag with a subresource-integrity
hash cannot be swapped even by whoever owns the name, and a browser enforces it.
A dangling reference with a valid hash is a broken page, not a hijackable one.

## The half that stays out, and why

Registration, and it is worth being blunt about the reasons because the
temptation is a screenshot away.

* It is **irreversible**. A domain registration lasts a year, an account name may
  never be released, and a package name is permanent on most registries.
* It is **outside scope**. The Program named hosts it authorises testing against.
  A dangling third-party name is not one of them, and the fact that the target
  points at it does not put it in scope.
* It makes the tester the **owner of live authority** over every visitor of the
  target from that moment. Anything served, including nothing, is code running in
  the target's pages for real users.
* It **races**. The name being takeable is exactly what makes it interesting to
  everyone else scanning the same target, and the answer to that race is speed
  from the target, not from the tester.

Also out: registering a lookalike to demonstrate, scanning the third-party host
for anything beyond its status answer, and archive lookups used to argue the
reference used to work. The last one is evidence about the past.

## The trap in the whole technique

The crawl is long and almost none of it is a finding. A typical page references
two dozen origins, most resolve, most are vendors the target chose, and half of
the dead ones are in code paths that never render.

Three questions cut it to the real list, and the Playbook asks all three
explicitly rather than trusting the crawl: is the reference reached, is the name
actually unclaimed right now, and does the page grant the origin anything. Two
yeses out of three is a note in the report. Three is the finding.
