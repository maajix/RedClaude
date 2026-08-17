# File upload: the shell, and the two bytes that prove it without one

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The bypass catalogue, ordered by which check it defeats.

Extension checks: `shell.php5`, `shell.phtml`, `shell.php.jpg`,
`shell.jpg.php`, `shell.php%00.jpg`, `shell.php.` with a trailing dot,
`shell.pHp` for the case-sensitive list, `.htaccess` to make the server
interpret an extension it did not before, `web.config` for the IIS equivalent.

Content checks: prepend `GIF89a;`, prepend a real JPEG header and append the
payload, build a polyglot that is a valid image and a valid script at once, set
`Content-Type: image/png` in the multipart part while the bytes are anything.

Destination: `../../../var/www/html/shell.php` in the filename to place the file
where it will be served, a zip that unpacks outside its directory, a symlink in
an archive.

Then: request the uploaded path, get a shell, screenshot it. The page also
covered image parsers -- ImageMagick delegates, ImageTragick, ghostscript in a
thumbnailer -- as a second route to execution.

## Why the Playbook does not run it

**A shell is a shell.** Uploading one leaves a working remote-execution primitive
on the target's disk, in a directory the web server serves, discoverable by
anyone who guesses the name. The engagement's own cleanup is best-effort and the
window is real. No finding requires it.

**The property is decided before the payload matters.** If identical bytes stored
under two names come back described two different ways, the caller's name decided
the interpretation. That is the whole claim. `GIF89a;` and a polyglot exist to
get past a *content* check, which is a different control, and the Playbook's arms
deliberately carry content no check would object to so that only the name varies.

**Traversal in the filename is a different class.** `../../../var/www/html/` is
`injection.path` arriving through an upload, and it belongs to `file-resolution`'s
question with `file-upload`'s approval, not to this one. The Playbook's own
fixture reduces the name to its last segment on both variants for exactly this
reason.

**`.htaccess` and `web.config` reconfigure the server.** Uploading one changes
how the target serves a whole directory, for every visitor, until somebody
notices. That is a mutation with no bounded blast radius and no clean undo.

**Overwriting is destruction.** Every technique on the page that targets an
existing name -- another user's avatar, a shared asset, a config file -- destroys
data belonging to somebody who is not part of the engagement.

**Parser exploits attack a library, not the application.** ImageTragick and its
descendants are findings about a dependency version, and they are proved by
crashing or by executing. Neither is available under this ceiling.

## What is kept

The core observation, and the Playbook is built on it: on many stacks the
server's idea of what a stored file *is* comes from the name the caller chose,
not from the bytes. The page reached that conclusion and then went looking for
execution. The Playbook reaches it and stops, because a retrieval that returns
`text/html` for bytes the uploader named `.html` has already said everything the
report needs.

Also kept: the page's insistence on checking the retrieval rather than the upload
response. An upload that returns `201` has stored something; only fetching it
back says what the server thinks it stored.

## The trap in the whole technique

Acceptance is not storage and storage is not service. Three separate things, and
the page's screenshots routinely showed the first while claiming the third.

A route can accept `shell.php`, store it as `a8f3e1.bin` in an object store,
serve it from a different origin with a fixed content type and an attachment
disposition, and be entirely fine. A reading that reports the `201` has reported
that the route has an upload form.
