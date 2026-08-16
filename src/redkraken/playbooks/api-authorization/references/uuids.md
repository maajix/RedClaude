# UUIDs: what the version tells you, and what it does not

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## The layout

```
123e4567-e89b-12d3-a456-426655440000
xxxxxxxx-xxxx-Mxxx-Nxxx-xxxxxxxxxxxx
```

`M` is the version. `N`'s most significant bits are the variant, and variant 1
(`8`, `9`, `a`, `b`) is what modern systems emit. The all-zero UUID is the nil
one, and applications reach for it as a default far more often than they mean
to.

## The versions that matter to a reading

* **v4** -- random. 122 bits of it. Nothing is recoverable from the value and
  there is no shortcut to the next one.
* **v1** -- time and node. The 60-bit timestamp counts 100-nanosecond intervals
  since 1582-10-15, the clock sequence is a per-boot random, and the node is
  usually the generating host's MAC address. A v1 identifier states when it was
  made and, often, on what.
* **v7** -- a Unix millisecond prefix and random after it. Ordered, and ordered
  is the point: two identifiers minted close together share a prefix.

The version digit is the one place worth looking, and it takes a second. What
it changes is whether "the identifier is unguessable" is an assumption anybody
should be relying on.

## Why this is attached to a state-transition Playbook

Not as an attack. This Playbook needs two objects of the same kind in different
states, and it needs to know which identifiers name real objects. Reading the
version tells the maintainer whether the target's own list route is the only way
to get them -- with v4 it is -- and stops a run from wandering into guessing
identifiers when the state view already holds the answer.

## What an unguessable identifier is not

An identifier nobody can guess is not an authorisation check. Every reading in
this corpus arrives holding real identifiers, from the state view or from the
target's own list route, so the guessability of the value never enters the
claim. A target whose only defence is that the identifier was hard to find has
the same defect it would have with sequential integers, and this corpus reports
it the same way.

The mirror of that: a v1 or v7 identifier is not itself a finding either. A
recoverable timestamp becomes one when it lets a caller reach something --
`information_disclosure.identifier_oracle` where the difference tells you an
object exists, `authorization.object_ownership` where the object comes back.
The identifier is the route in, and the class is named by what came back.
