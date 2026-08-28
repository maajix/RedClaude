# An active browser execution oracle is deferred

Ticket 99 asks whether the browser should deliberately cause a same-origin
resource request and use its Receipt as proof that injected markup acted. It
would work for some sinks, but it is not adopted in this release.

The existing `markup_injection` probe answers the common and decisive question
without making the planted element act: did the parser build an element, leave
the marker as text, or remove it? A fetch oracle adds value only where the DOM
read cannot reach or cannot express the effect, such as a cross-origin frame, a
document already left behind, a CSS `url()` sink, or a clobbering consequence.
That narrower coverage comes with a larger capability: the harness fabricates
an active element and causes a request the target did not initiate.

Its negative answer is also ambiguous. CSP, lazy loading, cache state, mixed
content policy, or navigation timing can suppress the request even though the
markup executed far enough to matter. A missing Receipt therefore cannot
refute execution. The positive answer would be attributable, because a fixed
relative same-origin path marker can be registry-owned and the request would be
filed as a Receipt, but that does not make the negative answer sound.

The decision is to keep the passive DOM probe and defer an active execution
oracle until a concrete playbook requires one of the otherwise unreachable bug
classes. That future ticket must name the sink it unlocks, use a registry-owned
relative same-origin marker, treat only a matching Receipt as positive, state
that absence is inconclusive, and account for the added request in the mission.
No model-authored JavaScript, second origin, CSP bypass, interception, or
page-to-driver binding is introduced by this decision.

## Consequences

- Ticket 99 has an ADR-level answer rather than an implicit omission.
- `markup_injection` remains passive and changes what the document is without
  deliberately changing what it does.
- The browser registry gains no execution-oracle action or probe in this
  release.
- A later proposal needs evidence that the added bug-class reach justifies the
  active behavior and its inconclusive negative result.
