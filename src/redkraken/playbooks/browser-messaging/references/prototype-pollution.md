# Prototype pollution: why this one is read and not triggered

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The client-side half of the technique. A page merges caller-controlled data into
an object with a recursive merge, a query-string parser, or a deep-clone helper
that walks keys without checking them, and one of the keys is `__proto__`:

```
?__proto__[innerHTML]=<img src=x onerror=1>
?constructor[prototype][srcdoc]=...
#__proto__.template=...
```

Every object that inherits from `Object.prototype` now carries the key. The
defect is not the assignment; it is the gadget -- somewhere later, a library
reads an option it expects to be undefined, finds the planted value, and puts it
in a sink.

The v1 page listed gadgets for the framework versions of the day and told the
reader to read the planted key back off a bare object literal in the console
afterwards.

## The half the Playbook uses

The reading, not the trigger. This is a client-channel defect in the exact sense
the attached Playbook means: the merged value never has to reach the server, the
gadget is in the bundle, and the sink is `innerHTML` or an equivalent.

So the Playbook's probe answers it where it can be driven -- a polluted key that
reaches a markup sink returns `reflected` like any other -- and the gadget
analysis is source reading.

Two things worth carrying forward from the page:

* The key spellings that matter are `__proto__`, `constructor.prototype` and
  `prototype`. A parser that blocks the first and not the second has blocked one
  spelling.
* `Object.create(null)`, a `Map`, and a merge that checks `hasOwnProperty` are
  the fixes. Seeing any of them in the merge path is the refutation and it is
  visible without running anything.

## The half that stays out, and why

**Polluting during a mission**, which is the whole of the rest of the page.

The reason is specific to how evidence works here rather than to safety. A
polluted prototype is global to the document and it does not go away: it changes
how every library in the page behaves from that moment on, including whatever
renders the result the next step waits for and whatever the probe's own
`document` traversal touches. A mission that pollutes at step three is a mission
whose steps four onward describe the pollution rather than the target. The plan
digest still matches, the result digest still gets recorded, and the evidence is
about the harness.

That is worse than a noisy finding: it is a run that looks clean and is not, and
nothing downstream can detect it.

The other exclusions are the ordinary ones. No gadget hunting by executing
candidate payloads, no server-side prototype pollution -- a different class and a
different Playbook -- and no writing a polluted value anywhere that persists.

## The trap in the whole technique

A planted key that reads back off a fresh object literal in a console is not a
finding. It proves a merge is unguarded and says nothing about whether any code
reads that key. Most polluted keys are inert forever.

The finding is the gadget: a specific place where a specific library reads a
specific option that the pollution can set, reaching a specific sink. A report
with the first half and not the second is asking the target to go find the second
half themselves, and they will correctly close it as informational.
