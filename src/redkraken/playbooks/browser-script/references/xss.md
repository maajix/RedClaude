# XSS: what the corpus grades, and what the payload list is for

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The largest page in the v1 pack. Context table -- HTML body, attribute, quoted
attribute, `<script>` block, `href`, `style`, SVG, template literal -- with a
breakout string for each; a long payload list, mostly `alert(1)` variants with
filter-evasion spellings; polyglots; encoding matrices; a section on blind XSS
with a collector callback; and the WAF-bypass folklore that accretes on any page
like this.

## The half the Playbook uses

The context table, as an explanation. One payload, from the registry.

The Playbook plants `<rk-probe id="rk-probe-marker"></rk-probe>` and asks a
browser whether the parser built an element. That single question answers the
whole context table at once, because a custom element is only constructed where
the bytes were parsed as markup, and it is constructed nowhere else. Attribute
context, script context and text context all return `escaped` or `absent`, and
which one is a matter for the next reading rather than for the verdict.

Why one payload rather than a list: an iterated payload list is a fuzzer, it is
what every scanner already sent this target this week, and the target's WAF has
seen all of it. The signal in a v1 run was almost never "the eleventh spelling
worked". It was "the value comes back unescaped", which the first probe answers.

## The half that stays out, and why

* **`alert(1)` and everything that executes.** An executing payload is a script
  running with the target's origin and the visitor's session. Against a live
  target it is an action, not an observation, and against a fixture it is
  unnecessary: the probe already distinguishes markup from text.
* **Blind XSS collectors.** A payload that phones a tester-controlled host and
  waits is data egress to a third party, on the target's behalf, on a timescale
  nobody watches. It also stores a payload in the target that a real user
  triggers later.
* **Stored variants.** Writing markup into a record other users load is the same
  problem with a longer fuse. Nothing here writes.
* **WAF bypasses.** A defeated filter is a claim about the filter. The Playbook's
  claim is about the escaping, and a target that escapes correctly is unaffected
  by anything on that list.
* **Encoding matrices.** Useful when the first probe returns `escaped` and the
  question becomes which decoder ran. That is a follow-up a person decides on,
  not a loop.

## The trap in the whole technique

Reflection is not injection, and injection is not execution. The three get
collapsed constantly, in both directions.

* A value appearing in a response body proves nothing: it may be an attribute
  value, a text node, a JSON string, or a comment. Grep cannot tell.
* An element being built proves the parser accepted markup. It does not prove a
  script would have run: a Content Security Policy with a nonce, a `sandbox`
  attribute, or a trusted-types enforcement can all stop it.
* A script running proves execution and still says nothing about impact until
  somebody asks what the origin holds.

The Playbook claims the middle one and says so at the step that reads the
verdict. Both neighbours are separate judgements and are recorded separately.
