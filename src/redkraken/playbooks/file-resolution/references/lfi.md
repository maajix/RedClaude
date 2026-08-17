# Local file inclusion: the read that becomes an execution, and the line before it

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The full escalation ladder, in order. Confirm the read with `/etc/passwd`. Widen
it: `/etc/shadow`, `~/.ssh/id_rsa`, `~/.aws/credentials`, `.env`, `.git/config`,
`web.config`, `application.properties`, the framework's own settings module,
the session directory under `/var/lib/php/sessions`. Read `/proc/self/environ`
for the environment, `/proc/self/cmdline` for the arguments, `/proc/self/fd/N`
for whatever the process has open.

Then the turn from read to run: poison a log file by putting PHP into a header
that the access log records, include the log; poison a session file by putting
PHP into a session-stored value, include the session; upload anything at all and
include it; use `/proc/self/environ` where a `User-Agent` lands in it. The page
closed with the wrapper list -- `php://filter`, `php://input`, `data://`,
`expect://`, `zip://`, `phar://` -- and a note that `allow_url_include` turns
the whole thing remote.

## Why the Playbook does not run it

**The ladder starts after the finding.** Every rung above "a document outside the
directory came back" is escalation. The Hypothesis is that the resolution left
the boundary, and one dull file already settled it; `/etc/hostname` and
`/etc/shadow` are the same evidence for that claim and only one of them is a
report a triager can safely receive.

**The target's secrets are not evidence.** A reading that proves a file read by
reading a private key has taken the private key. It is now in an Artifact, in a
report, in a bundle, and in whatever a triager forwards it to. The finding was
provable without it.

**Log poisoning writes to the target.** It puts attacker-controlled content into
a file the operations team relies on, at a size and position nobody chose,
usually with no way to remove it. It also corrupts the record the target's own
incident response would read afterwards.

**Session poisoning attacks a shared object.** The session store is other
people's sessions in the same directory, and a technique that writes into it to
be included is one restart away from mattering to somebody who is not in the
engagement.

**`/proc/self/environ` is credential material by construction.** The environment
of a running web process is where the database password, the signing key and the
cloud token live. Reading it is reading them.

## What is kept

The idea that the interesting question is where the resolution landed, not what
the string contained. The page's own confirmation step -- one file, outside the
directory, chosen for existing everywhere -- is exactly what the Playbook's step
3 does, twice, with two dull files instead of one because two answers can be
differenced and one cannot.

Also kept: the observation that a route which refuses `..` but serves
`notes/../report.txt` is doing string matching rather than resolution checking.
The page used that to pick a bypass. The Playbook uses it as its control.

## The trap in the whole technique

`/etc/passwd` coming back is not always a file read. A route that maps the
parameter into a template name, a route with a catch-all handler, and a route
behind a proxy that normalises the path can all produce a response that changes
when the parameter changes, and a reading that treats any change as a read will
report all three.

That is why the Playbook sends a fourth value: a path outside the directory whose
leaf does not exist anywhere. A route that really resolves answers that one like
a miss. A route that is doing something else answers it like the others, and the
difference was never a read.
