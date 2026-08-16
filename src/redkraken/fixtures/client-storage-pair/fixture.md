---
description: A profile route behind an HttpOnly session cookie, served twice from one source, one variant also answering the login with the same session value so the page keeps a copy a script can read and the other answering with the cookie alone.
bb:kind: own_pair
bb:classes: ["information_disclosure.client_storage"]
bb:subject: /profile
bb:facts: ["authenticated_endpoint", "read_method", "web_surface"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 52 against the class description ticket 52 added, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# The credential the cookie was hiding, handed over anyway

`GET /` serves a sign-in page. `POST /session` checks an email and a password and
issues `session=...; HttpOnly; Path=/; SameSite=Lax`. `GET /profile` is the
subject and answers to a caller the server recognises.

Both variants set the same cookie with the same attributes, and both accept the
session value as `Authorization: Bearer`. Neither of those is the difference. The
difference is one key in the login response:

* **vulnerable** answers `{"session": "opened", "token": "s-alice-4f2c"}`, and
  the page -- byte for byte the same page on both halves -- writes that token
  into `localStorage`.
* **secure** answers `{"session": "opened"}`, and the same page stores nothing,
  because there is nothing to store.

## What the ground truth claims, and what it does not

`information_disclosure.client_storage` on the vulnerable variant, and nothing
else.

Bearer acceptance is held constant on purpose. A value nobody would honour is not
a leaked credential, it is a string; making the acceptance the difference would
be grading which credential formats the route parses rather than where the
credential ended up. So both halves honour it, and only one half ever produces
it.

The page is identical on both variants. Its script stores a token if it was given
one and does nothing if it was not, so a reading cannot separate the halves by
differencing the served document -- which is honest, because the defect is in the
answer to the login, not in the page.

`HttpOnly` is on both cookies. That is the point of the pair: the vulnerable
variant took the trouble to keep the cookie away from script and then handed the
same value to script through the front door.

`Secure` is on neither, and that is not a second finding hiding in the pair. This
fixture is served over plain HTTP, where a browser discards a `Secure` cookie
outright and neither half would authenticate at all. `session_handling.cookie_scope`
is where cookie attributes are graded, and another pair already asks it.

Nothing here is a second class: the login checks the password on both halves, the
refusal bodies are fixed strings, the profile carries the caller's own three
fields and no identifier can be substituted, and there is one account.
