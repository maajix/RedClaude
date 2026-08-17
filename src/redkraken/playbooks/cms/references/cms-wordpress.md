# WordPress: the second door the platform ships, and the scan around it

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

A tour of the tooling. Point WPScan at the host with an API token so it can look
every plugin version up against a defect database. Read the version out of the
generator meta tag, `/readme.html`, or a stylesheet's version query string.
Enumerate users through `/?author=1` and watch the redirect land on the author
slug, or take the whole list from `/wp-json/wp/v2/users`. Enumerate plugins by
asking for `readme.txt` under every name in a wordlist, then match version to
exploit. Try `wp-config.php.bak`, `.wp-config.php.swp`, and the rest of the
backup-suffix list. Use `xmlrpc.php` for password guessing in batches, because
`system.multicall` lets one request carry many attempts.

## Why the Playbook does not run it

**The version-to-defect step is the fingerprint fallacy in its purest form.** A
generator tag is a string the platform prints. It is edited, cached, stale, or
lying, and even when it is true it says nothing about whether the deployment
applied a backport, disabled the affected component, or sits behind a rule that
never lets the route through. The Playbook's step 1 writes the fingerprint down
as a hypothesis and settles nothing with it, which is criterion 2 of the ticket
that authored it.

**Plugin enumeration is a scan.** Asking for a thousand `readme.txt` paths is
the scanning behaviour this corpus refuses everywhere else, and dressing it in a
platform's name does not change what it is. The Playbook asks at most five route
names, each once, and they come from the platform's own published conventions
rather than from a list.

**`xmlrpc.php` multicall is credential attack and amplification.** Batched
password guessing against somebody else's login is out of scope on every Program
this harness will ever run under, and the same endpoint has a pingback method
whose whole purpose is making the target send a request somewhere else.

**User enumeration is a finding the page never actually made.** The v1 text
collected usernames as input to the next attack. If an author list is genuinely
not meant to be public, that is a disclosure claim with its own class and its own
evidence, and it is not a step on the way to a login attempt.

## What the Playbook kept

One idea, and it is the whole of `cms`.

The REST namespace is a second route to the same store. `/wp-json/wp/v2/posts`
reads the posts table; so does the theme. They are two programs over one set of
records, written at different times by different people, and only one of them was
part of the conversation about who may read what. When the namespace answers a
caller holding nothing with a record the site's own route would have refused --
a draft, a private post, a pending revision, a field the theme never renders --
that is `authorization.parallel_route`, and it is proved by an identifier
appearing in two documents rather than by a version number.

`/wp-json/wp/v2/` is also the honest place to get the candidate names for step 1:
the platform publishes its own route index, so the reading does not have to
guess.

## The trap

The namespace answering is not the finding. It is designed to answer -- a
published post is public and serving it is correct behaviour. The finding
requires the application's own route to have refused this caller first (step 3)
and the same record to come back anyway (step 5). A reading that reports
`/wp-json/wp/v2/posts` returning published posts has reported a website.
