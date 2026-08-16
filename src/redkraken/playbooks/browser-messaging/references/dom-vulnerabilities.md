# DOM vulnerabilities: the sources this harness can drive, and the ones it cannot

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

A source-and-sink table, which is the right way to think about this class and is
worth restating.

Sources -- where caller-controlled data enters the page without the server:

```
location.hash / .search / .href / .pathname
document.referrer
window.name
postMessage event.data
localStorage / sessionStorage
IndexedDB
a WebSocket message
```

Sinks -- where it becomes markup or code:

```
innerHTML / outerHTML / insertAdjacentHTML
document.write / writeln
eval / Function / setTimeout with a string
element.src / .href on a javascript: URL
jQuery $(), .html(), .append()
Range.createContextualFragment
```

Plus advice to read the bundle, follow the taint, and confirm in a browser.

## The half the Playbook uses

The taxonomy, and one source out of the seven.

A field the page reads without a round trip is a source in exactly the sense the
table means. It is not in v1's list because v1 was thinking about URLs, but a
live preview that renders as you type is the same shape: caller bytes, no server,
a sink. It is also the only one of them a mission built from the registered
actions can drive, because `inject` types into a field and no action here writes
a fragment, a `window.name`, a storage entry or a message.

The other thing kept is the reason the browser is not optional. Every one of
these sinks is invisible in the response body -- the response is a bundle, and
the value never appears in it at all. A reading built on differencing requests
finds nothing here, and correctly so: there is nothing in the requests.

## The half that stays out, and why

* **`location.hash`.** `navigate` refuses a URL carrying a fragment. That is a
  deliberate rule from the browser slice, not an oversight: a fragment never
  leaves the browser, so the Receipt for the navigation would not match the URL
  the plan asked for, and a mission whose plan and Receipts disagree cannot be
  used as evidence of anything.
* **`postMessage`.** Sending one means running as a second origin. This Program
  has scope over one, and there is no action that posts a message.
* **`document.referrer` and `window.name`.** Both are set by the page you
  arrived from, which is the same second-origin problem.
* **Storage sources.** Nothing here writes storage, and there is no probe that
  reads it.
* **Model-authored JavaScript in the page.** There is exactly one way to evaluate
  an expression in a document here, and it is naming a registered probe. A plan
  that could supply source could read the cookie jar, fetch anything same-origin
  and return whatever verdict it preferred, which would make every other control
  in the browser slice decorative.

## The trap in the whole technique

Source-and-sink analysis over a minified bundle produces a list of candidate
flows, and a candidate flow is not a defect. Bundlers inline, frameworks
sanitise on the way into `innerHTML`, and a `document.write` behind a feature
flag that has been off for two years is dead code with a scary name.

So a listener read out of source is a listener. The Playbook says that in its own
words at the step that names the undriveable sources: a flow nobody drove is
`inconclusive`, never `supported`, and reporting a grep hit as a finding is how
this class earns its reputation for noise.
