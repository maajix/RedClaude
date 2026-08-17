# Joomla: the web services route, and the component sprawl around it

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

Fingerprint, enumerate, exploit. Pin the version from
`/language/en-GB/en-GB.xml`, `/administrator/manifests/files/joomla.xml`, or the
generator tag. Run joomscan. Enumerate third-party components by asking for
`/index.php?option=com_<name>` across a list, because the interesting defects
have always been in the components rather than in the core. Then the collected
items: injection in whichever extension is currently unpatched, `/administrator/`
with default or guessed credentials, `configuration.php` backups left with a
suffix the web server serves as text, and the template editor as a path from
administrator access to code execution.

## Why the Playbook does not run it

**Component enumeration is a wordlist by another name.** The v1 approach only
works at scale, and scale is the thing this corpus does not do. `cms` asks at
most five names, taken from what the platform publishes about itself.

**"Whichever extension is unpatched" is not a technique, it is a subscription.**
It requires a current defect feed and produces a claim the reading cannot support
from its own observations. The Playbook makes no claim of the form "this
extension is version X, which is vulnerable to Y".

**`/administrator/` is out of bounds.** Step 7 refuses administrative routes
outright, and it refuses credential guessing against them twice over: a Program
that put a site in scope did not put its administrators' accounts in scope.

**The template editor path assumes you are already in.** Everything downstream of
an administrator session is a demonstration of impact from a position this
reading is not allowed to reach.

## What the Playbook kept

Joomla 4 ships an API application at `/api/index.php/v1/`, and Joomla has always
had `?format=json`, `?format=feed` and the older `com_content` view parameters.
These are the platform's second door in the sense `cms` means: routes over the
same content table, with their own access configuration, frequently left at
whatever the installer set.

The other thing worth keeping is the page's instinct that the *view* parameter
matters -- the same component answers differently depending on which view it is
asked for, and a view somebody forgot to restrict is the classic Joomla exposure.
That still has to be shown the Playbook's way: the site's own route refuses the
caller holding nothing, the platform route answers, and the identifier from step
2 is in both documents.

## The trap

Joomla's API application is commonly deployed with authentication required and
answers `401` to everything, including routes that do not exist. When every
candidate name comes back with the same refusal, the reading has learned nothing
about scoping and the honest verdict is `refuted` on the evidence available --
not `inconclusive` dressed up as a near miss, and certainly not a sixth name.
