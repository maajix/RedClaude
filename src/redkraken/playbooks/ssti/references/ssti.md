# Server-side template injection: the arithmetic probe and nothing past it

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The whole topic in one page. A route renders a template, and the caller's value
becomes part of the template source rather than a value passed into it -- a
welcome email built by string formatting, a report header, a notification body, a
white-label page where a customer supplies their own snippet.

The page's detection step was the polyglot:

```
${{<%[%'"}}%\
```

and the arithmetic probe, which is the one people actually use:

```
{{7*7}}   ${7*7}   <%= 7*7 %>   #{7*7}   {{7*'7'}}
```

If `49` comes back, an engine evaluated it. If `7777777` comes back, the engine
is Twig or Jinja rather than Freemarker or Smarty. Then the detection tree by
response, and the per-engine escape: Jinja through `__class__` and
`__subclasses__` to `os.popen`, Freemarker through `Execute`, Velocity through
its class tool, Twig through registered filters, ERB straight to backticks.

## The half the Playbook uses

**The arithmetic probe, its dialect variants, and the fingerprint that falls out
of the response.** That is the detection, it is complete, and it is one request
per dialect.

Three specifics the Playbook enforces that the page did not:

* **The control is the rendered form, not the absence of the payload.** Send
  `{{7*7}}` and send `{{7*7}` -- one brace short, so the engine has nothing to
  evaluate and the reflection path is otherwise identical. If both come back
  verbatim, the value is data. If the first returns `49` and the second returns
  itself, an engine evaluated. Comparing a payload against no payload compares
  two different response sizes and two different code paths.
* **`7*7` is chosen for the same reason everywhere: the output is
  distinguishable from the input.** `49` does not appear in the request. A probe
  whose result looks like its input -- `{{1+0}}` -- cannot be told apart from a
  reflection, and reflection is the thing most likely to be happening instead.
* **Reflection is the competing explanation and it must be ruled out first.**
  A route that echoes `{{7*7}}` back unchanged is reflecting, which is the
  `browser-script` reading's subject, not this one's. The Playbook's evidence
  rows are all `reflected_input` precisely because the observation is about what
  came back in place of what was sent.

## The half that stays out, and why

**Every sandbox escape.** The `__subclasses__` walk, the Freemarker `Execute`
object, the Velocity class tool, the ERB backtick. All of them exist to run code
on the target, and the verdict was reached by `49`.

There is a second reason specific to this class: the escapes are long, fragile,
version-dependent chains, and a chain that half-works leaves the target's
template context in an unknown state. The arithmetic probe evaluates a
multiplication and leaves nothing behind.

**Reading the template context.** `{{config}}` in a Flask application dumps the
application's configuration, including its secret key. It is one short payload
and it is the most tempting thing on this list; it is also the target's secrets
in this harness's evidence store, and it is refused for the same reason every
extraction in this pack is refused.

**File reads through template loaders.** Same refusal, same reason.

## The trap in the whole technique

Client-side template injection wears the same clothes. An Angular or Vue
application that interpolates a value into its own template will happily return
`49` for `{{7*7}}`, and the evaluation happened in the browser -- which is a real
finding, with real impact, belonging to `browser-script` and carrying a completely
different severity and a different fix.

The separator is where the evaluation happened, and it is answerable without
guessing: fetch the response with no JavaScript engine involved. If `49` is in
the bytes the server sent, the server evaluated it. If the raw body contains
`{{7*7}}` and only the rendered page shows `49`, the framework did, and this
reading has the wrong Playbook.

The Playbook makes that a step rather than an assumption, because the mistake is
common, it is embarrassing in a report, and it takes one request to avoid.
